[English](README.md) · [Русский](README.ru.md) · [Українська](README.uk.md)

# DocAssist

Production-grade **RAG-асистент за вашими документами**. Завантажуйте PDF, Word, Markdown або текст; DocAssist витягує текст, розбиває на чанки та будує ембединги у **pgvector**, а потім відповідає на запитання через стрімінговий API — з інлайн-**джерелами та посиланнями на завантаження**. У комплекті — мінімалістичний веб-дашборд і **Telegram-бот** як другий інтерфейс до того самого бекенду.

> _Сюди можна додати скриншот або GIF дашборда._
>
> `![DocAssist dashboard](docs/screenshot.png)`

---

## Що це і навіщо

Більшість демо «чат із документами» розвалюються під реальним навантаженням: синхронна інгестія блокує запити, немає ретраїв навколо LLM, видалення лишає осиротілі вектори, а тестів немає взагалі. DocAssist побудований інакше — це чистий шаруватий сервіс із фоновою інгестією, належною обробкою помилок, міграціями, структурним логуванням і справжніми тестами, щоб його дійсно можна було деплоїти й підтримувати.

## Архітектура

```mermaid
flowchart LR
    subgraph Clients
        UI[Веб-дашборд]
        TG[Telegram-бот]
    end
    UI -->|HTTP / SSE| API
    TG -->|HTTP| API

    subgraph App[FastAPI app]
        API[API routes] --> SVC[Services]
        SVC --> REPO[Repositories]
        REPO --> DB[(PostgreSQL + pgvector)]
        API -. enqueue .-> Q[[Черга інгестії]]
        Q --> SVC
    end

    SVC -->|embeddings / chat| LLM[(OpenAI-сумісний API)]
```

**Потік запиту (chat):** ембединг запитання → cosine-пошук у pgvector → збирання контексту за бюджетом токенів → запит до LLM → стрімінг токенів через SSE разом зі списком джерел → збереження діалогу.

**Потік інгестії:** `POST /documents` валідує та зберігає файл, повертає `202 Accepted` і ставить задачу в чергу. Фонові воркери витягують текст → чанкінг (~800 токенів, overlap 100) → ембединги → збереження, оновлюючи статус документа (`pending → processing → ready | failed`).

## Структура проєкту

```
app/
  api/          # FastAPI-роутери, залежності, обробники винятків
  core/         # конфіг, логування, винятки, ретраї
  db/           # асинхронний engine, declarative base
  models/       # SQLAlchemy ORM-моделі
  repositories/ # шар доступу до даних
  schemas/      # Pydantic-схеми запитів/відповідей
  services/     # extraction, chunking, embeddings, llm, retrieval, ingestion, queue, rag
  static/       # ванільний HTML/CSS/JS дашборд
bot/            # Telegram-інтерфейс на aiogram 3
alembic/        # міграції
tests/          # pytest-сьют (unit + інтеграція)
```

## Стек

- **Python 3.12**, **FastAPI** (async), **Uvicorn**
- **PostgreSQL + pgvector**, **SQLAlchemy 2.0** (asyncpg) + **Alembic**
- **OpenAI-сумісний** API чату та ембедингів (через `httpx`)
- **aiogram 3** Telegram-бот
- **structlog** структурне логування
- **pytest / pytest-asyncio**, **ruff**, **mypy**, **pre-commit**
- **Docker** (multi-stage, non-root) + **docker-compose**

## Швидкий старт (docker compose)

```bash
git clone https://github.com/txltedxgod/docassist.git
cd docassist
cp .env.example .env          # потім вкажіть OPENAI_API_KEY (і TELEGRAM_BOT_TOKEN, якщо потрібен бот)
docker compose up --build
```

- Дашборд: <http://localhost:8000>
- Інтерактивна документація API: <http://localhost:8000/docs>

Сервіс `app` автоматично виконує `alembic upgrade head` перед запуском.

## Запуск локально (без Docker)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
# Підніміть Postgres+pgvector у будь-який зручний спосіб, потім:
alembic upgrade head
make run        # API на http://localhost:8000
make bot        # Telegram-бот (окремий термінал)
```

## API

Усі помилки мають єдиний формат: `{ "code", "message", "detail" }`.

### Завантаження документа

```bash
curl -F "file=@whitepaper.pdf" http://localhost:8000/documents
# 202 Accepted -> { "id": 1, "status": "pending", ... }
```

### Список / перегляд / видалення документів

```bash
curl http://localhost:8000/documents
curl http://localhost:8000/documents/1
curl http://localhost:8000/documents/1/download -o original.pdf
curl -X DELETE http://localhost:8000/documents/1     # каскадно видаляє чанки
```

### Запитання (стрімінг SSE, за замовчуванням)

```bash
curl -N -X POST http://localhost:8000/chat \\
  -H "Content-Type: application/json" \\
  -d '{"question": "Яка політика зберігання даних?"}'
# event: meta    -> { "conversation_id": 1 }
# event: sources -> [ { "position": 1, "filename": "whitepaper.pdf", "download_url": "..." } ]
# event: token   -> { "content": "Політика" }
# event: done    -> { "conversation_id": 1 }
```

### Запитання (буферизований JSON)

```bash
curl -X POST http://localhost:8000/chat \\
  -H "Content-Type: application/json" \\
  -d '{"question": "Яка політика зберігання даних?", "stream": false}'
```

### Історія діалогів

```bash
curl http://localhost:8000/conversations
curl http://localhost:8000/conversations/1
curl -X DELETE http://localhost:8000/conversations/1  # каскадно видаляє повідомлення
```

## Змінні оточення

| Змінна | За замовчуванням | Опис |
| --- | --- | --- |
| `OPENAI_API_KEY` | — | Ключ до OpenAI-сумісного API (обов'язково). |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Базовий URL LLM/ембедингового API. |
| `LLM_MODEL` | `gpt-4o-mini` | Модель чат-комплішенів. |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Модель ембедингів. |
| `EMBEDDING_DIM` | `1536` | Розмірність ембединга (має збігатися з моделлю). |
| `DATABASE_URL` | `postgresql+asyncpg://...` | Асинхронний URL БД для застосунку. |
| `DATABASE_URL_SYNC` | `postgresql+psycopg://...` | Синхронний URL БД для Alembic. |
| `STORAGE_DIR` | `./var/storage` | Де зберігаються оригінали завантажених файлів. |
| `MAX_UPLOAD_MB` | `25` | Максимальний розмір завантаження. |
| `UPLOAD_ALLOWED_EXTENSIONS` | `pdf,docx,txt,md` | Дозволені типи файлів. |
| `CHUNK_SIZE_TOKENS` / `CHUNK_OVERLAP_TOKENS` | `800` / `100` | Параметри чанкінгу. |
| `RETRIEVAL_TOP_K` | `5` | Скільки чанків витягувати на запит. |
| `MAX_CONTEXT_TOKENS` | `3000` | Бюджет токенів для зібраного контексту. |
| `LLM_MAX_RETRIES` / `LLM_BACKOFF_BASE` / `LLM_BACKOFF_MAX` | `4` / `0.5` / `8.0` | Політика ретраїв для зовнішніх викликів. |
| `INGESTION_WORKERS` | `2` | Паралелізм фонової інгестії. |
| `PUBLIC_BASE_URL` | `http://localhost:8000` | Використовується для посилань на завантаження джерел. |
| `TELEGRAM_BOT_TOKEN` | — | Вмикає Telegram-бота, коли заданий. |
| `API_BASE_URL` | `http://localhost:8000` | URL API, до якого звертається бот. |
| `LOG_JSON` / `LOG_LEVEL` | `true` / `INFO` | Налаштування структурного логування. |

## Запуск тестів

Сьют використовує справжню БД Postgres + pgvector (фейками замінено лише мережеву межу LLM/ембедингів), тож векторний пошук і каскадні видалення перевіряються по-справжньому.

```bash
docker run -d --name docassist-test -p 5432:5432 \\
  -e POSTGRES_USER=docassist -e POSTGRES_PASSWORD=docassist \\
  -e POSTGRES_DB=docassist_test pgvector/pgvector:pg16

export TEST_DATABASE_URL=postgresql+asyncpg://docassist:docassist@localhost:5432/docassist_test
make check        # ruff + mypy + pytest
```

## Обмеження та плани

- Сховище — локальний диск; наступний крок — S3-сумісний бекенд для горизонтального масштабування.
- Черга інгестії — внутрішньопроцесна (на репліку). Для кількох реплік замініть її на спільний брокер (Redis/RQ, Celery або arq).
- Ре-ранкінг і гібридний (keyword + векторний) пошук — у планах.
- Авторизація поза межами цієї версії; поки що ставте сервіс за шлюз.

## Ліцензія

MIT — див. [LICENSE](LICENSE).
