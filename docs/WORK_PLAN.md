# Work Plan

## Phase 0: Bootstrap local agent (done)
- [x] FastAPI server
- [x] Repo URL parsing (GitHub)
- [x] Background job manager (in-memory)
- [x] Clone repo (public) using git
- [x] Basic repo scan saved to snapshot

## Phase 1: Deterministic repo signals (done)
- [x] Deterministic tech stack detection (Node/Python/CI/Infra)
- [x] GitHub Actions parsing (jobs + steps)
- [x] Startup/entrypoint recommendations (Node scripts, Python frameworks, Docker Compose)

## Phase 2: Workflow understanding (current)
- [x] FastAPI route map extraction (static AST, best-effort)
- [ ] Express route map extraction (later)
- [ ] Middleware/auth detection (later)
- [ ] Request lifecycle summary (route -> handler -> key calls)

## Phase 3: Index + retrieval for Q&A
- [ ] Chunking
- [ ] Lexical search
- [ ] Evidence pack generator
- [ ] Ask endpoint returns evidence + citations

## Phase 4: Local LLM via Ollama
- [ ] Evidence-first prompts
- [ ] Workflow JSON schema + citations
- [ ] Q&A with citations + confidence labels

## Phase 5: UI
- [ ] Minimal UI
- [ ] Results tabs + evidence viewer
- [ ] Chat Q&A