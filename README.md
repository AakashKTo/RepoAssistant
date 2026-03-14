# Repo Understanding Assistant

A full-stack, AI-powered system that clones any public GitHub repository, runs a multi-stage analysis pipeline, and lets you explore the codebase and ask questions — all locally, with no external API keys required.

---

## ✨ Features

| Feature | Details |
|---------|---------|
| **Repo Analysis** | Tech stack, startup workflow, CI/CD pipelines, FastAPI route map |
| **RAG Q&A** | Chat with the codebase — answers grounded in real file content |
| **File Tree** | Browse every scanned file directly in the dashboard sidebar |
| **Source Viewer** | Click any file to open a syntax-highlighted drawer (500 KB cap) |
| **Job Tracking** | Real-time progress page (cloning → embedding → done) |
| **Parallel Embedding** | Files fan-out across Celery workers via Chroma HTTP API |
| **Recent Repos** | Homepage remembers your last analyzed repositories |

---

## 🏗️ Architecture

```
Browser (Next.js 15)
  │
  ▼
FastAPI 0.111  ──►  Celery Workers (threads)
  │                      │
  │              ┌───────┴────────┐
  │           Clone           Embed batches
  │           (git)           (Ollama → Chroma)
  │
  ├── PostgreSQL   (snapshot metadata + job state)
  ├── ChromaDB     (vector embeddings, HTTP server)
  └── Redis        (Celery broker + result backend)

AI Engine: Ollama running locally
  - LLM:    llama3  (or any model via OLLAMA_MODEL env var)
  - Embed:  nomic-embed-text
```

### Key API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/analyze` | Submit a repo URL for analysis |
| `GET`  | `/api/jobs/{job_id}` | Poll job status |
| `GET`  | `/api/snapshots/{id}` | Fetch full analysis results |
| `GET`  | `/api/snapshots/{id}/files/{path}` | Serve raw file content from the cloned repo |
| `POST` | `/api/chat` | Stream a RAG answer from Ollama |
| `GET`  | `/api/config` | Return active model names from settings |

---

## 📦 Requirements

- Python 3.11+
- Node.js 18+ & npm
- Git
- Docker & Docker Compose
- [Ollama](https://ollama.com) running locally with:

```powershell
ollama pull llama3
ollama pull nomic-embed-text
```

---

## 🛠️ Setup

### 1. Clone & configure

```powershell
git clone https://github.com/AakashKTo/RepoAssistant.git
cd repoAssistant
```

Copy and edit the environment file (optional — defaults work for local dev):

```powershell
# Key env vars (all have sensible defaults):
# OLLAMA_MODEL=llama3
# OLLAMA_BASE_URL=http://host.docker.internal:11434
# EMBED_MODEL=nomic-embed-text
# DATABASE_URL=postgresql://...
# CHROMA_HOST=localhost  CHROMA_PORT=8001
# REDIS_URL=redis://localhost:6379/0
```

### 2. Start infrastructure

```powershell
docker-compose up -d
```

This boots **PostgreSQL**, **ChromaDB**, and **Redis**.

### 3. Start backend

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Apply DB migrations
python -m alembic upgrade head

# FastAPI server
python -m uvicorn agent.app.main:app --port 8000 --reload

# Celery workers (new terminal, same venv)
.venv\Scripts\celery.exe -A agent.app.worker.celery_app worker --loglevel=info --pool=threads -c 4

# Optional: Celery beat for hourly repo cleanup
.venv\Scripts\celery.exe -A agent.app.worker.celery_app beat --loglevel=info
```

### 4. Start frontend

```powershell
cd frontend
npm install
npm run dev
```

Open **http://localhost:3000** — paste any public GitHub URL and go.

---

## 🗂️ Project Layout

```
repo-assistant/
├── agent/
│   └── app/
│       ├── main.py               # FastAPI app + all routes
│       ├── worker.py             # Celery tasks (clone, embed, finalize)
│       ├── config.py             # Pydantic settings
│       ├── database.py           # SQLAlchemy models + session
│       ├── models.py             # Pydantic response models
│       ├── storage.py            # Snapshot filesystem helpers
│       └── services/
│           ├── analyzer.py       # Orchestrates the analysis pipeline
│           ├── rag.py            # Chroma ingest + streaming chat
│           ├── scanner.py        # File-count + language stats
│           ├── tech_stack.py     # Framework/package-manager detection
│           ├── startup.py        # Install/run command detection
│           ├── route_map_fastapi.py  # AST route extraction
│           ├── repo_filters.py   # Ignore lists + analyzable-file filter
│           ├── github_url.py     # URL parsing + ref resolution
│           ├── git_ops.py        # git clone / checkout helpers
│           └── jobs.py           # Job CRUD wrapper
├── frontend/
│   └── src/app/
│       ├── page.tsx              # Home — submit URL, recent repos
│       ├── job/[job_id]/         # Real-time job progress page
│       └── dashboard/[snapshot_id]/  # Results, file tree, Q&A
├── docs/
│   ├── ARCHITECTURE.md
│   └── WORK_PLAN.md
├── tasks/
│   ├── todo.md
│   └── lessons.md
├── docker-compose.yml
└── requirements.txt
```

---

## 🔧 Configuration Reference

All settings live in `agent/app/config.py` and are read from environment variables.

| Env Var | Default | Description |
|---------|---------|-------------|
| `OLLAMA_MODEL` | `llama3` | LLM used for Q&A |
| `OLLAMA_BASE_URL` | `http://host.docker.internal:11434` | Ollama API base |
| `EMBED_MODEL` | `nomic-embed-text` | Embedding model |
| `DATABASE_URL` | `postgresql://...localhost:5432/repoassistant` | Postgres DSN |
| `CHROMA_HOST` | `localhost` | ChromaDB host |
| `CHROMA_PORT` | `8001` | ChromaDB port |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis / Celery broker |
| `DATA_DIR` | `data` | Root dir for cloned repos + snapshots |

---

## 🤝 Contributing

PRs welcome. Run `npx tsc --noEmit` from `frontend/` and `pip install -r requirements.txt` before submitting.
