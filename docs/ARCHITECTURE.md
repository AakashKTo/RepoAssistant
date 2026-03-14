# Architecture

## Goal

Analyze any public GitHub repository and produce:

- **Deterministic outputs** (no LLM required): tech stack, startup commands, CI/CD config, FastAPI route map, file-language breakdown
- **RAG Q&A**: chat with the codebase, answers grounded in real file chunks via ChromaDB + Ollama
- **UI**: paste URL → track progress → explore results + file tree → ask questions

---

## Components

### 1. FastAPI Backend (`agent/app/`)

- **`main.py`** — all HTTP routes
  - `POST /api/analyze` — validate repo URL, create snapshot + job, dispatch Celery task
  - `GET  /api/jobs/{id}` — poll job status
  - `GET  /api/snapshots/{id}` — full analysis JSON
  - `GET  /api/snapshots/{id}/files/{path}` — serve raw file content (500 KB cap)
  - `POST /api/chat` — streaming RAG answer via SSE
  - `GET  /api/config` — return active model names from settings
- **`worker.py`** — Celery tasks
  - `run_analysis_task` — clone repo, run deterministic pipeline, fan-out embedding batches
  - `embed_batch_task` — embed a batch of files into ChromaDB
  - `finalize_analysis_task` — write results JSON, mark job done
  - `cleanup_old_repos_task` — scheduled hourly cleanup of clones older than 2 hours

### 2. Analysis Pipeline (`services/`)

Run in order inside `analyze_snapshot()`:

| Step | Module | Output |
|------|--------|--------|
| Clone | `git_ops.py` | Repo on disk at `data/repos/<id>/` |
| Scan | `scanner.py` | File counts, language histogram |
| Tech stack | `tech_stack.py` | Frameworks, package managers, infra |
| Startup | `startup.py` | Install + run commands |
| Route map | `route_map_fastapi.py` | AST-extracted FastAPI routes |
| Embed | `rag.py` + Celery | File chunks → ChromaDB |

### 3. RAG Layer (`services/rag.py`)

- Files are split by type: `code`, `document`, `other`
- Each type gets its own ChromaDB collection → queried in parallel at chat time
- Ollama (`nomic-embed-text`) generates embeddings; `llama3` synthesizes answers
- Streaming via SSE (`sse-starlette`)

### 4. Storage

| Store | Usage |
|-------|-------|
| PostgreSQL | Snapshot metadata, job state |
| ChromaDB (HTTP) | Vector embeddings per snapshot |
| Redis | Celery broker + result backend |
| Filesystem | Cloned repos (`data/repos/`), result JSON (`data/snapshots/`) |

### 5. Frontend (`frontend/src/app/`)

| Page | Path | Purpose |
|------|------|---------|
| Home | `/` | URL input, recent repos list |
| Job | `/job/[job_id]` | Real-time progress polling |
| Dashboard | `/dashboard/[snapshot_id]` | Results, file tree, Q&A chat |

---

## Key Principles

- **Deterministic extractors first, LLM second.** Tech stack / startup / routes never hallucinate.
- **Snapshots are reproducible.** Each snapshot locks to a specific commit SHA.
- **Graceful degradation.** If route-map extraction fails (non-FastAPI repo), it returns `present: false` — no crash.
- **Local-first.** Zero external API calls. Ollama runs on the host; everything else in Docker.