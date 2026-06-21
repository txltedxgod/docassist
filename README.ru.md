[English](README.md) · [Русский](README.ru.md) · [Українська](README.uk.md)

# DocAssist

Production-grade **RAG-ассистент по вашим документам**. Загружайте PDF, Word, Markdown или текст; DocAssist извлекает, разбивает на чанки и строит эмбеддинги в **pgvector**, а затем отвечает на вопросы через стриминговый API — с инлайн-**источниками и ссылками на скачивание**. В комплекте — минималистичный веб-дашборд и **Telegram-бот** как второй интерфейс к тому же бэкенду.

> _Сюда можно добавить скриншот или GIF дашборда._
>
> `![DocAssist dashboard](docs/screenshot.png)`

---

## Что это и зачем

Большинство демок «чат с документами» разваливаются под реальной нагрузкой: синхронная ингестия блокирует запросы, нет ретраев вокруг LLM, удаление оставляет осиротевшие векторы, а тестов нет вовсе. DocAssist построен по-другому — это чистый слоистый сервис с фоновой ингестией, нормальной обработкой ошибок, миграциями, структурным логированием и настоящими тестами, чтобы его можно было действительно деплоить и поддерживать.

## Архитектура

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
        API -. enqueue .-> Q[[Очередь ингестии]]
        Q --> SVC
    end

    SVC -->|embeddings / chat| LLM[(OpenAI-совместимый API)]
```

**Поток запроса (chat):** эмбеддинг вопроса → cosine-поиск в pgvector → сборка контекста по бюджету токенов → запрос в LLM → стриминг токенов по SSE вместе со списком источников → сохранение диалога.

**Поток ингестии:** `POST /documents` валидирует и сохраняет файл, возвращает `202 Accepted` и ставит задачу в очередь. Фоновые воркеры извлекают текст → чанкинг (~800 токенов, overlap 100) → эмбеддинги → сохранение, обновляя статус документа (`pending → processing → ready | failed`).

## Структура проекта

```
app/
  api/          # FastAPI-роутеры, зависимости, обработчики исключений
  core/         # конфиг, логирование, исключения, ретраи
  db/           # асинхронный engine, declarative base
  models/       # SQLAlchemy ORM-модели
  repositories/ # слой доступа к данным
  schemas/      # Pydantic-схемы запросов/ответов
  services/     # extraction, chunking, embeddings, llm, retrieval, ingestion, queue, rag
  static/       # ванильный HTML/CSS/JS дашборд
bot/            # Telegram-интерфейс на aiogram 3
alembic/        # миграции
tests/          # pytest-сьют (unit + интеграция)
```

## Стек

- **Python 3.12**, **FastAPI** (async), **Uvicorn**
- **PostgreSQL + pgvector**, **SQLAlchemy 2.0** (asyncpg) + **Alembic**
- **OpenAI-совместимый** API чата и эмбеддингов (через `httpx`)
- **aiogram 3** Telegram-бот
- **structlog** структурное логирование
- **pytest / pytest-asyncio**, **ruff**, **mypy**, **pre-commit**
- **Docker** (multi-stage, non-root) + **docker-compose**

## Быстрый старт (docker compose)

```bash
git clone https://github.com/txltedxgod/docassist.git
cd docassist
cp .env.example .env          # затем укажите OPENAI_API_KEY (и TELEGRAM_BOT_TOKEN, если нужен бот)
docker compose up --build
```

- Дашборд: <http://localhost:8000>
- Интерактивная документация API: <http://localhost:8000/docs>

Сервис `app` автоматически выполняет `alembic upgrade head` перед запуском.

## Запуск локально (без Docker)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
# Поднимите Postgres+pgvector любым удобным способом, затем:
alembic upgrade head
make run        # API на http://localhost:8000
make bot        # Telegram-бот (отдельный терминал)
```

## API

Все ошибки имеют единый формат: `{ "code", "message", "detail" }`.

### Загрузка документа

```bash
curl -F "file=@whitepaper.pdf" http://localhost:8000/documents
# 202 Accepted -> { "id": 1, "status": "pending", ... }
```

### Список / просмотр / удаление документов

```bash
curl http://localhost:8000/documents
curl http://localhost:8000/documents/1
curl http://localhost:8000/documents/1/download -o original.pdf
curl -X DELETE http://localhost:8000/documents/1     # каскадно удаляет чанки
```

### Вопрос (стриминг SSE, по умолчанию)

```bash
curl -N -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "Какая политика хранения данных?"}'
# event: meta    -> { "conversation_id": 1 }
# event: sources -> [ { "position": 1, "filename": "whitepaper.pdf", "download_url": "..." } ]
# event: token   -> { "content": "Политика" }
# event: done    -> { "conversation_id": 1 }
```

### Вопрос (буферизованный JSON)

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "Какая политика хранения данных?", "stream": false}'
```

### История диалогов

```bash
curl http://localhost:8000/conversations
curl http://localhost:8000/conversations/1
curl -X DELETE http://localhost:8000/conversations/1  # каскадно удаляет сообщения
```

## Переменные окружения

| Переменная | По умолчанию | Описание |
| --- | --- | --- |
| `OPENAI_API_KEY` | — | Ключ к OpenAI-совместимому API (обязательно). |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Базовый URL LLM/эмбеддингового API. |
| `LLM_MODEL` | `gpt-4o-mini` | Модель чат-комплитишенов. |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Модель эмбеддингов. |
| `EMBEDDING_DIM` | `1536` | Размерность эмбеддинга (должна совпадать с моделью). |
| `DATABASE_URL` | `postgresql+asyncpg://...` | Асинхронный URL БД для приложения. |
| `DATABASE_URL_SYNC` | `postgresql+psycopg://...` | Синхронный URL БД для Alembic. |
| `STORAGE_DIR` | `./var/storage` | Где хранятся оригиналы загруженных файлов. |
| `MAX_UPLOAD_MB` | `25` | Максимальный размер загрузки. |
| `UPLOAD_ALLOWED_EXTENSIONS` | `pdf,docx,txt,md` | Допустимые типы файлов. |
| `CHUNK_SIZE_TOKENS` / `CHUNK_OVERLAP_TOKENS` | `800` / `100` | Параметры чанкинга. |
| `RETRIEVAL_TOP_K` | `5` | Сколько чанков извлекать на запрос. |
| `MAX_CONTEXT_TOKENS` | `3000` | Бюджет токенов для собранного контекста. |
| `LLM_MAX_RETRIES` / `LLM_BACKOFF_BASE` / `LLM_BACKOFF_MAX` | `4` / `0.5` / `8.0` | Политика ретраев для внешних вызовов. |
| `INGESTION_WORKERS` | `2` | Параллелизм фоновой ингестии. |
| `PUBLIC_BASE_URL` | `http://localhost:8000` | Используется для ссылок на скачивание источников. |
| `TELEGRAM_BOT_TOKEN` | — | Включает Telegram-бота, когда задан. |
| `API_BASE_URL` | `http://localhost:8000` | URL API, к которому обращается бот. |
| `LOG_JSON` / `LOG_LEVEL` | `true` / `INFO` | Настройки структурного логирования. |

## Запуск тестов

Сьют использует настоящую БД Postgres + pgvector (фейками заменена только сетевая граница LLM/эмбеддингов), поэтому векторный поиск и каскадные удаления проверяются по-настоящему.

```bash
docker run -d --name docassist-test -p 5432:5432 \
  -e POSTGRES_USER=docassist -e POSTGRES_PASSWORD=docassist \
  -e POSTGRES_DB=docassist_test pgvector/pgvector:pg16

export TEST_DATABASE_URL=postgresql+asyncpg://docassist:docassist@localhost:5432/docassist_test
make check        # ruff + mypy + pytest
```

## Ограничения и планы

- Хранилище — локальный диск; следующий шаг — S3-совместимый бэкенд для горизонтального масштабирования.
- Очередь ингестии — внутрипроцессная (на реплику). Для мульти-реплика замените её на общий брокер (Redis/RQ, Celery или arq).
- Ре-ранкинг и гибридный (keyword + векторный) поиск — в планах.
- Авторизация вне рамок этой версии; пока что ставьте сервис за шлюз.

## Лицензия

MIT — см. [LICENSE](LICENSE).
