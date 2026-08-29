# AdaptED — Setup & Run Guide

This guide gets AdaptED (and the **OBE Mapping Agent**) running on your machine from a
clean checkout. Follow it top to bottom. Commands are shown for both **PowerShell
(Windows)** and **bash (macOS/Linux/Git-Bash)**.

- [1. Prerequisites](#1-prerequisites)
- [2. Get the code & install dependencies](#2-get-the-code--install-dependencies)
- [3. Set up PostgreSQL + pgvector](#3-set-up-postgresql--pgvector)
- [4. Configure environment (`.env`)](#4-configure-environment-env)
- [5. Do I need an API key?](#5-do-i-need-an-api-key)
- [6. Run the backend API](#6-run-the-backend-api)
- [7. Run the web UI](#7-run-the-web-ui)
- [8. Use the OBE Mapping Agent](#8-use-the-obe-mapping-agent)
- [9. Run the tests](#9-run-the-tests)
- [10. Troubleshooting](#10-troubleshooting)

---

## 1. Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| **Python** | 3.12+ | `python --version` |
| **uv** | latest | Dependency manager — [install](https://docs.astral.sh/uv/getting-started/installation/) |
| **PostgreSQL** | 14+ | With the **pgvector** extension available |
| **Git** | any | To clone the repo |

Install **uv** if you don't have it:

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```
```powershell
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

---

## 2. Get the code & install dependencies

```bash
git clone https://github.com/0NJS0/AdaptEd.git
cd AdaptEd
uv sync
```

`uv sync` creates a virtual environment in `.venv/` and installs everything from
`pyproject.toml` / `uv.lock`. Prefix commands with `uv run` to use it (no manual
`activate` needed).

---

## 3. Set up PostgreSQL + pgvector

PostgreSQL with **pgvector** is the only supported database (the app fails fast at startup
if it can't reach one).

**Option A — Docker (quickest):**

```bash
docker run --name adapted-db -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=adapted \
  -p 5432:5432 -d pgvector/pgvector:pg16
```

**Option B — existing PostgreSQL:** create a database and enable the extension:

```sql
CREATE DATABASE adapted;
\c adapted
CREATE EXTENSION IF NOT EXISTS vector;
```

> The app also runs `CREATE EXTENSION IF NOT EXISTS vector` on startup, so you only need
> the extension to be *installed* (available) in your PostgreSQL, not pre-created.

Your connection string will look like:

```
postgresql+psycopg://postgres:postgres@localhost:5432/adapted
```

---

## 4. Configure environment (`.env`)

Copy the template and edit it:

```bash
cp .env.example .env
```
```powershell
Copy-Item .env.example .env
```

Set at least `DATABASE_URL`:

```dotenv
# --- Database (required) ---
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/adapted

# --- LLM (optional — see section 5) ---
LLM_PROVIDER=mock            # mock = fully offline, no key needed
OPENROUTER_API_KEY=          # only needed when LLM_PROVIDER=openrouter
LLM_MODEL=openrouter/free
EMBED_PROVIDER=mock          # mock = deterministic offline embeddings

# --- Security ---
SECRET_KEY=change-me-to-a-long-random-string
```

Generate a strong `SECRET_KEY`:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

---

## 5. Do I need an API key?

**No — not to try the platform, and not for the OBE agent's core function.**

| What you want to do | LLM provider | API key needed? |
|---------------------|--------------|-----------------|
| Explore the app / run the whole pipeline deterministically | `mock` | ❌ No |
| **OBE agent: extract, validate, suggest, summarize** | `mock` | ❌ No — all deterministic & offline |
| OBE agent: *optional* LLM "polish" of the summary | `openrouter` | ✅ Yes |
| Real AI-generated lessons / quizzes / grading | `openrouter` | ✅ Yes |
| Real vector embeddings for RAG | `openrouter` | ✅ Yes |

**The OBE Mapping Agent's validation and mapping are 100% deterministic** — they never
call an LLM, so they work with no key at all. A key is only needed if you turn on the
optional summary "polish", or if you want the *other* agents to produce real AI content.

### How to use an API key (OpenRouter)

1. Create a free account at **https://openrouter.ai/** and generate an API key
   (Dashboard → **Keys** → *Create key*).
2. Put it in your `.env` and switch the provider on:

   ```dotenv
   LLM_PROVIDER=openrouter
   OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
   LLM_MODEL=meta-llama/llama-3.1-8b-instruct:free   # any model you have access to

   # optional: real embeddings for RAG
   EMBED_PROVIDER=openrouter
   EMBED_MODEL=nvidia/nemotron-3-embed-1b:free
   EMBEDDING_DIM=2048        # must match the embed model's output dimension
   ```
3. Restart the API. The key is read from `.env` only — **never commit `.env`** (it is
   already in `.gitignore`).

> Any OpenAI-compatible endpoint works — point `OPENROUTER_BASE_URL` at it and set
> `OPENROUTER_API_KEY` accordingly.

---

## 6. Run the backend API

```bash
uv run uvicorn adapted.main:app --port 8001 --reload
```

- API docs (Swagger): **http://localhost:8001/docs**
- Health check: **http://localhost:8001/health**

Database tables are created automatically on startup.

---

## 7. Run the web UI

In a second terminal:

```bash
uv run streamlit run src/adapted/ui/app.py
```

Open **http://localhost:8501**. The UI talks to the API at `ADAPTED_API_URL`
(default `http://localhost:8001`); override it if your API runs elsewhere:

```bash
ADAPTED_API_URL=http://localhost:8001 uv run streamlit run src/adapted/ui/app.py
```
```powershell
$env:ADAPTED_API_URL="http://localhost:8001"; uv run streamlit run src/adapted/ui/app.py
```

Register a **teacher** account in the UI to see the **OBE Mapping** page.

---

## 8. Use the OBE Mapping Agent

### From the web UI (easiest)

1. Sign in as a **teacher**.
2. Sidebar → **OBE Mapping**.
3. **Upload** a course outline (`.pdf`, `.docx`, `.txt`, `.md`) and click **Analyze outline**.
4. Review the tabs: **CO ↔ PO Matrix**, **Findings**, **Suggested fixes**, **Summary**
   (downloadable as Markdown). Your file is never stored or modified.

The optional **"Polish summary with LLM"** checkbox uses your configured LLM provider —
leave it off to stay fully offline.

### From the API

Get a teacher token (register/login returns `access_token`), then:

```bash
# analyze an outline file
curl -X POST http://localhost:8001/obe/analyze \
  -H "Authorization: Bearer <TEACHER_JWT>" \
  -F "file=@/path/to/CourseOutline.docx"

# quick-check a single Course Outcome
curl -X POST http://localhost:8001/obe/suggest \
  -H "Authorization: Bearer <TEACHER_JWT>" -H "Content-Type: application/json" \
  -d '{"description":"Design a solution for a complex engineering problem using UML."}'
```

`/obe/analyze` returns `{ extraction, report, suggestions, summary_markdown }`.

---

## 9. Run the tests

```bash
uv run pytest -q
```

- `test/test_obe.py` runs fully offline (no database) and covers the OBE reference data,
  rules, mapper, extractor, and the end-to-end extract → validate → summarize pipeline.
- `test/test_obe_agent.py` imports the model layer, so it needs `DATABASE_URL` set; it
  **skips automatically** if no database is configured.

Run only the offline OBE tests:

```bash
uv run pytest test/test_obe.py -q
```

---

## 10. Troubleshooting

| Symptom | Fix |
|---------|-----|
| `DATABASE_URL is not set` at startup | Set `DATABASE_URL` in `.env` (section 4). |
| `Cannot reach PostgreSQL at …` | Is PostgreSQL running and reachable on the host/port? Check credentials. |
| `CREATE EXTENSION … vector` fails | Install pgvector in your PostgreSQL, or use the `pgvector/pgvector` Docker image (section 3). |
| OBE analyze returns *"No extractable text"* | The PDF is a scanned image — OCR is not supported. Use a text-based PDF/DOCX. |
| `401 Not authenticated` on `/obe/*` | Include a valid **teacher** JWT: `Authorization: Bearer <token>`. |
| UI can't reach the API | Confirm the API is up on port 8001 and `ADAPTED_API_URL` matches. |
| Want real AI content | Set `LLM_PROVIDER=openrouter` + `OPENROUTER_API_KEY` (section 5). |
