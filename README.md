## Сервис парсинга выписок Kaspi Bank

Этот репозиторий содержит небольшой сервис на **FastAPI** для парсинга PDF‑выписок из Kaspi Bank и сохранения транзакций в PostgreSQL.

Основные обязанности сервиса:
- **принимать PDF‑файл выписки** (через HTTP POST `/parse-pdf/`);
- **распарсить таблицы из PDF** с помощью `pdfplumber`;
- **нормализовать транзакции** (дата, сумма, валюта, описание, признак прихода/расхода);
- **обновить баланс пользователя** и сохранить операции в таблицу `"transaction"` в PostgreSQL.

### Стек
- **Python 3.10+**
- **FastAPI**
- **pdfplumber**
- **psycopg2**
- **PostgreSQL**
- **JWT** (аутентификация через Bearer‑токен)

### Структура
- `parser.py` — основной файл FastAPI‑приложения с эндпоинтом `/parse-pdf/`;
- `main.py` — альтернативная/старшая версия приложения (может быть использована по желанию);
- `.gitignore` — настройки игнора для репозитория.

### Подготовка окружения

```bash
python -m venv .venv
source .venv/Scripts/activate  # Windows (Git Bash/PowerShell)
pip install -r requirements.txt
```

> Если у вас ещё нет `requirements.txt`, его можно собрать командой:
> `pip freeze > requirements.txt`

### Переменные окружения и БД

В коде сейчас конфигурация вынесена в константы:
- `DB_CONFIG` — параметры подключения к PostgreSQL;
- `SECRET_KEY`, `ALGORITHM` — настройки JWT.

Для продакшена рекомендуется:
- вынести эти значения в `.env` и не коммитить его в репозиторий;
- использовать переменные окружения или библиотеку `python-dotenv`.

### Запуск сервиса

Запуск приложения (используя `parser.py` как основной модуль):

```bash
uvicorn parser:app --reload
```

После запуска эндпоинт будет доступен по адресу:

- `POST /parse-pdf/` — принимает `multipart/form-data` с полем `file` (PDF выписка) и заголовком `Authorization: Bearer <jwt>`.

### Пример запроса (curl)

```bash
curl -X POST "http://localhost:8000/parse-pdf/" \
  -H "Authorization: Bearer <JWT_TOKEN>" \
  -F "file=@statement.pdf"
```

В ответ сервис вернёт JSON с количеством распарсенных строк и вставленных транзакций.

