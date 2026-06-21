# DocAssist

[English](README.md) · [Русский](README.ru.md) · [Українська](README.uk.md)

[![CI](https://github.com/txltedxgod/docassist/actions/workflows/ci.yml/badge.svg)](https://github.com/txltedxgod/docassist/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-async-009688?logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-pgvector-4169E1?logo=postgresql&logoColor=white)
[![Ruff](https://img.shields.io/badge/lint-ruff-261230?logo=ruff&logoColor=white)](https://github.com/astral-sh/ruff)
![mypy](https://img.shields.io/badge/types-mypy-2A6DB2?logo=python&logoColor=white)
![License: MIT](https://img.shields.io/badge/License-MIT-3DA639.svg)

A production-grade **RAG (retrieval-augmented generation) assistant** over your
own documents. Upload PDFs, Word, Markdown or text files; DocAssist extracts,
chunks and embeds them into **pgvector**, then answers your questions over a
streaming API — with inline **citations and source download links**. It ships
with a minimal web dashboard and a **Telegram bot** as a second interface to the
same backend.

## Highlights

- **Async end-to-end** — FastAPI + SQLAlchemy 2.0 (asyncpg); ingestion never blocks requests.
- **Real vector search** — pgvector cosine similarity, token-bounded context, inline citations with source download links.
- **Streaming UX** — answers stream over Server-Sent Events; a buffered JSON mode is also available.
- **Resilient** — retries with exponential backoff around the LLM, a uniform error envelope, structured JSON logging.
- **Two front-ends, one backend** — web dashboard and an aiogram 3 Telegram bot.
- **Built to maintain** — Alembic migrations, typed (mypy) and linted (ruff), green CI on every push, unit + integration tests against a real Postgres.

---

## What it is & why

Most "chat with your docs" demos collapse the moment you put real traffic on
them: synchronous ingestion blocks requests, there is no retry logic around the
LLM, deletes leave orphaned vectors, and there are no tests. DocAssist is built
the other way around — a clean layered service with background ingestion, proper
error handling, migrations, structured logging and a real test suite, so it can
actually be deployed and maintained.

## Architecture

```mermaid
flowchart LR
    subgraph Clients
        UI[Web dashboard]
        TG[Telegram bot]
    end
    UI -->|HTTP / SSE| API
    TG -->|HTTP| API

    subgraph App[FastAPI app]
        API[API routes] --> SVC[Services]
        SVC --> REPO[Repositories]
        REPO --> DB[(PostgreSQL + pgvector)]
        API -. enqueue .-> Q[[Ingestion queue]]
        Q --> SVC
    end

    SVC -->|embeddings / chat| LLM[(OpenAI-compatible API)]
```

**Request flow (chat):** embed question → cosine search in pgvector → assemble a
token-bounded context → prompt the LLM → stream tokens back over SSE with the
list of sources → persist the conversation.

**Ingestion flow:** `POST /documents` validates and stores the file, returns
`202 Accepted`, and enqueues a job. Background workers extract text → chunk
(~800 tokens, 100 overlap) → embed → store, updating the document status
(`pending → processing → ready | failed`).

## Project layout

```
app/
  api/          # FastAPI routers, dependencies, exception handlers
  core/         # config, logging, exceptions, retry
  db/           # async engine, declarative base
  models/       # SQLAlchemy ORM models
  repositories/ # data access layer
  schemas/      # Pydantic request/response models
  services/     # extraction, chunking, embeddings, llm, retrieval, ingestion, queue, rag
  static/       # vanilla HTML/CSS/JS dashboard
bot/            # aiogram 3 Telegram interface
alembic/        # migrations
tests/          # pytest suite (unit + integration)
```

## Tech stack

- **Python 3.12**, **FastAPI** (async), **Uvicorn**
- **PostgreSQL + pgvector**, **SQLAlchemy 2.0** (asyncpg) + **Alembic**
- **OpenAI-compatible** chat & embeddings API (via `httpx`)
- **aiogram 3** Telegram bot
- **structlog** structured logging
- **pytest / pytest-asyncio**, **ruff**, **mypy**, **pre-commit**
- **Docker** (multi-stage, non-root) + **docker-compose**

## Quick start (docker compose)

```bash
git clone https://github.com/txltedxgod/docassist.git
cd docassist
cp .env.example .env          # then set OPENAI_API_KEY (and TELEGRAM_BOT_TOKEN if you want the bot)
docker compose up --build
```

- Dashboard: <http://localhost:8000>
- Interactive API docs: <http://localhost:8000/docs>

The `app` service runs `alembic upgrade head` automatically before serving.

## Running locally (without Docker)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
# Start Postgres+pgvector however you like, then:
alembic upgrade head
make run        # API at http://localhost:8000
make bot        # Telegram bot (separate terminal)
```

## API

All errors share a uniform envelope: `{ "code", "message", "detail" }`.

### Upload a document

```bash
curl -F "file=@whitepaper.pdf" http://localhost:8000/documents
# 202 Accepted -> { "id": 1, "status": "pending", ... }
```

### List / inspect / delete documents

```bash
curl http://localhost:8000/documents
curl http://localhost:8000/documents/1
curl http://localhost:8000/documents/1/download -o original.pdf
curl -X DELETE http://localhost:8000/documents/1     # cascades to chunks
```

### Ask a question (streaming SSE, default)

```bash
curl -N -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the retention policy?"}'
# event: meta    -> { "conversation_id": 1 }
# event: sources -> [ { "position": 1, "filename": "whitepaper.pdf", "download_url": "..." } ]
# event: token   -> { "content": "The" }
# event: done    -> { "conversation_id": 1 }
```

### Ask a question (buffered JSON)

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the retention policy?", "stream": false}'
```

### Conversation history

```bash
curl http://localhost:8000/conversations
curl http://localhost:8000/conversations/1
curl -X DELETE http://localhost:8000/conversations/1  # cascades to messages
```

## Environment variables

| Variable | Default | Description |
| --- | --- | --- |
| `OPENAI_API_KEY` | — | API key for the OpenAI-compatible endpoint (required). |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Base URL of the LLM/embeddings API. |
| `LLM_MODEL` | `gpt-4o-mini` | Chat-completions model. |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Embeddings model. |
| `EMBEDDING_DIM` | `1536` | Embedding dimension (must match the model). |
| `DATABASE_URL` | `postgresql+asyncpg://...` | Async DB URL used by the app. |
| `DATABASE_URL_SYNC` | `postgresql+psycopg://...` | Sync DB URL used by Alembic. |
| `STORAGE_DIR` | `./var/storage` | Where uploaded originals are stored. |
| `MAX_UPLOAD_MB` | `25` | Maximum upload size. |
| `UPLOAD_ALLOWED_EXTENSIONS` | `pdf,docx,txt,md` | Accepted file types. |
| `CHUNK_SIZE_TOKENS` / `CHUNK_OVERLAP_TOKENS` | `800` / `100` | Chunking parameters. |
| `RETRIEVAL_TOP_K` | `5` | Chunks retrieved per query. |
| `MAX_CONTEXT_TOKENS` | `3000` | Token budget for the assembled context. |
| `LLM_MAX_RETRIES` / `LLM_BACKOFF_BASE` / `LLM_BACKOFF_MAX` | `4` / `0.5` / `8.0` | Retry policy for upstream calls. |
| `INGESTION_WORKERS` | `2` | Background ingestion concurrency. |
| `PUBLIC_BASE_URL` | `http://localhost:8000` | Used to build source download links. |
| `TELEGRAM_BOT_TOKEN` | — | Enables the Telegram bot when set. |
| `API_BASE_URL` | `http://localhost:8000` | API URL the bot talks to. |
| `LOG_JSON` / `LOG_LEVEL` | `true` / `INFO` | Structured logging controls. |

## Running the tests

The suite uses a real Postgres + pgvector database (only the LLM/embedding
network boundary is faked) so vector search and cascade deletes are genuinely
exercised.

```bash
docker run -d --name docassist-test -p 5432:5432 \
  -e POSTGRES_USER=docassist -e POSTGRES_PASSWORD=docassist \
  -e POSTGRES_DB=docassist_test pgvector/pgvector:pg16

export TEST_DATABASE_URL=postgresql+asyncpg://docassist:docassist@localhost:5432/docassist_test
make check        # ruff + mypy + pytest
```

## Limitations & roadmap

- Storage is local-disk; an S3-compatible backend is the next step for
  horizontal scaling.
- The ingestion queue is in-process (per replica). For multi-replica deploys,
  swap it for a shared broker (Redis/RQ, Celery or arq).
- Re-ranking and hybrid (keyword + vector) search are planned.
- Auth is out of scope for this version; put it behind a gateway for now.

## License

MIT — see [LICENSE](LICENSE).
