from fastapi import FastAPI, UploadFile, File, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from datetime import datetime
import shutil
import psycopg2
import pdfplumber
from fastapi.middleware.cors import CORSMiddleware
import os  # Для удаления временного файла

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # или ["*"] для всех
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# JWT конфиг
SECRET_KEY = "fsdsdfsdfdsfsdfsd1231@sdf"
ALGORITHM = "HS256"

# БД конфиг
DB_CONFIG = {
    "dbname": "fitrack_db",
    "user": "postgres",
    "password": "0000",
    "host": "localhost",
    "port": "5432"
}

# Авторизация по Bearer-токену
security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("id")
        family_id = payload.get("familyId")
        if not user_id or not family_id:
            raise HTTPException(status_code=401, detail="Invalid token payload")
        return {"user_id": user_id, "family_id": family_id}
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


# ✅ Нормализация строки PDF с учетом знака
def normalize_row(row):
    try:
        date_str, amount_str, operation, details = row

        date = datetime.strptime(date_str.strip(), "%d.%m.%y").date()

        currency = "USD" if "USD" in amount_str else "KZT"
        is_negative = "-" in amount_str

        amount_clean = amount_str.replace("₸", "").replace("USD", "").replace(",", ".").replace(" ", "").replace("-", "").strip()
        amount = float(amount_clean)

        if is_negative:
            amount = -amount

        action = '-' if amount < 0 else '+'

        return {
            "date": str(date),
            "amount": amount,
            "currency": currency,
            "type": operation.strip(),
            "description": details.strip(),
            "action": action
        }
    except Exception as e:
        print(f"❌ Ошибка нормализации строки: {row} | Ошибка: {e}")
        return None


def get_user_cash(user_id):
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT cash FROM \"user\" WHERE id = %s", (user_id,))
            result = cur.fetchone()
            if result:
                return result[0]
            else:
                raise HTTPException(status_code=404, detail="User not found")
    finally:
        conn.close()


def update_user_cash(user_id, new_cash):
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE \"user\" SET cash = %s WHERE id = %s", (new_cash, user_id))
            conn.commit()
    finally:
        conn.close()

def insert_transactions_with_cash_update(data, user_id, family_id):
    if not data:
        print("⚠️ Нет данных для вставки")
        return

    cash = get_user_cash(user_id)
    print(f"💰 Начальный баланс: {cash}")

    total_delta = sum(item["amount"] for item in data)
    print(f"📊 Суммарная дельта: {total_delta}")

    if cash + total_delta < 0:
        raise HTTPException(status_code=400, detail="Недостаточно средств для импорта всех транзакций")

    conn = psycopg2.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            for item in data:
                amount = item["amount"]
                cash += amount

                transaction = {
                    "category": item["category"],
                    "amount": amount,
                    "action": item["action"],
                    "cashAfter": cash,
                    "createdAt": item["createdAt"],
                    "updatedAt": item["updatedAt"],
                    "userId": user_id,
                    "familyId": family_id
                }

                cur.execute("""
                    INSERT INTO "transaction" (category, amount, action, "cashAfter", "createdAt", "updatedAt", "userId", "familyId")
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    transaction["category"],
                    transaction["amount"],
                    transaction["action"],
                    transaction["cashAfter"],
                    transaction["createdAt"],
                    transaction["updatedAt"],
                    transaction["userId"],
                    transaction["familyId"]
                ))

            cur.execute("UPDATE \"user\" SET cash = %s WHERE id = %s", (cash, user_id))
            conn.commit()
            print(f"✅ Успешно вставлено, новый баланс: {cash}")
    except Exception as e:
        conn.rollback()
        print(f"❌ Ошибка при вставке: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при вставке транзакций")
    finally:
        conn.close()


import os  

@app.post("/parse-pdf/")
async def parse_pdf(file: UploadFile = File(...), user=Depends(get_current_user)):
    temp_path = "temp.pdf"
    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        file.file.close()

        parsed_data = []
        total_rows = 0

        with pdfplumber.open(temp_path) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                if not tables:
                    continue
                for table in tables:
                    for row in table:
                        total_rows += 1
                        if row and len(row) == 4:
                            norm = normalize_row(row)
                            if norm:
                                try:
                                    created_at = datetime.strptime(norm["date"], "%Y-%m-%d")
                                except ValueError:
                                    continue
                                parsed_data.append({
                                    "category": norm["description"],
                                    "amount": norm["amount"],
                                    "action": norm["action"],
                                    "createdAt": created_at,
                                    "updatedAt": created_at,
                                })

        insert_transactions_with_cash_update(parsed_data, user["user_id"], user["family_id"])

        return {
            "status": "ok",
            "parsed_rows": total_rows,
            "inserted": len(parsed_data)
        }

    except HTTPException as e:
        raise e  

    except Exception as e:
        print(f"❌ Unexpected server error: {e}")
        raise HTTPException(status_code=500, detail="Unexpected server error during PDF parsing.")

    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception as e:
                print(f"⚠️ Could not delete temp file: {e}")

