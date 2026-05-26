# VOR / B7

Приложение для загрузки ВОР и отчетов Б.7, сопоставления работ, ручного подтверждения соответствий и сборки сводов по неделям/месяцам.  
Backend сделан на FastAPI, frontend - на Streamlit.

## Структура проекта

```text
.
├── backend/
│   ├── .env
│   └── app/
│       ├── api/        # FastAPI-роуты
│       ├── db/         # подключение к БД
│       ├── models/     # SQLAlchemy-модели
│       ├── schemas/    # Pydantic-схемы
│       └── services/   # бизнес-логика
├── frontend/
│   └── app.py          # Streamlit-интерфейс
└── requirements.txt
```

## Что нужно для запуска

- Python 3.10+.
- PostgreSQL.
- Настроенный файл `backend/.env`.

Минимально важные переменные в `backend/.env`:

```env
DATABASE_URL=postgresql://USER:PASSWORD@HOST:PORT/DB_NAME
JWT_SECRET_KEY=your-secret-key
AUTH_SEED_ADMIN_LOGIN=admin
AUTH_SEED_ADMIN_PASSWORD=admin123
AUTH_SEED_ADMIN_FULL_NAME=Administrator
```

Для OCR/PDF через Qwen нужны также:

```env
QWEN_VL_API_URL=...
QWEN_VL_TOKEN=...
QWEN_VL_MODEL=Qwen/Qwen3-VL-235B-A22B-Instruct
```

Важно: backend читает `.env` из текущей рабочей папки. Поэтому API нужно запускать именно из папки `backend`.

## Первый запуск

Из корня проекта:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Запуск backend

Открой первый терминал:

```powershell
cd C:\Users\MaBOY\Desktop\vor_b7_final
.\.venv\Scripts\Activate.ps1
cd backend
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Проверка:

- API health: <http://127.0.0.1:8000/health>
- Swagger-документация: <http://127.0.0.1:8000/docs>

При старте backend сам создает таблицы через SQLAlchemy и создает seed-admin, если такого пользователя еще нет.

## Запуск frontend

Открой второй терминал:

```powershell
cd C:\Users\MaBOY\Desktop\vor_b7_final
.\.venv\Scripts\Activate.ps1
streamlit run frontend/app.py
```

Streamlit обычно откроется здесь:

<http://localhost:8501>

Frontend ходит в backend по адресу:

```python
http://127.0.0.1:8000
```

Этот адрес сейчас жестко задан в `frontend/app.py`.

## Вход в приложение

Логин администратора берется из переменных:

- `AUTH_SEED_ADMIN_LOGIN`, если задан;
- иначе используется `admin`.

Пароль берется из:

- `AUTH_SEED_ADMIN_PASSWORD`;
- иначе используется `admin123`.

Если в базе уже есть пользователь с таким логином, пароль при следующем старте автоматически не перезаписывается.

## Основной сценарий работы

1. Войти в Streamlit.
2. Создать или выбрать проект.
3. Загрузить ВОР из Excel или PDF.
4. Загрузить отчеты Б.7 из Excel или PDF.
5. Открыть вкладку сопоставления и проверить найденные соответствия.
6. При необходимости вручную подтвердить спорные строки.
7. Собрать свод по выбранным отчетам и скачать CSV.
