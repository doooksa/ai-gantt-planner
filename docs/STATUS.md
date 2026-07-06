# Project status

_Snapshot of where the AI Gantt Planner stands._

## Done (gated)

### Phase 1 — domain (no UI)
Models, deterministic scheduler (topo-sort + forward pass, calendar days), validators
(Russian messages), atomic patch engine, Excel import/export (openpyxl), SQLite storage
with undo snapshots, seed.
**Gate: `pytest` green.**

### Phase 2 — MCP + agent
FastMCP server with exactly 4 tools (`get_plan` / `validate_patch` / `apply_patch` /
`undo_last`) mounted at `/mcp` over streamable HTTP; MCP→OpenAI bridge; agent loop
(≤10 iterations, validate→apply, atomic); shared `services.py` for MCP + REST;
FastAPI REST + SSE `/api/chat` + WebSocket `/ws` (`{version, diff}` broadcast).
**Gate: 10-command live agent gate — 5/5 stable on `anthropic/claude-haiku-4.5`**
(control run on `claude-sonnet-4.5` also 10/10). Offline suite: `pytest -m "not live"`
→ 63 passed.

### Phase 3 — frontend
Vite + React + TS + Zustand + `@svar-ui/react-gantt`: GanttBoard, ChatPanel (SSE stream
+ Applied-changes block + Undo), TaskModal (all fields + predecessors + dependents),
Toolbar (Excel import/export, undo, reset, version, WS status).
**Gate: full local demo scenario verified end-to-end** (chat edit → applied changes →
live Gantt/WS update → undo; task modal; mass reassign).

### Phase 4 — deployment config + polish (this session)
- **Deploy manifests:** backend + frontend Dockerfiles, `nginx.conf` (SPA +
  reverse-proxy /api /ws /mcp), `docker-compose.yml`, `render.yaml` (Docker web
  service, health check), `apps/frontend/vercel.json` (vite + SPA rewrites).
- **Prod CORS:** `FRONTEND_ORIGIN` parses into a list (prod + Vercel preview).
- **Render cold start:** `bootstrap()` retry/backoff + "Сервер просыпается…"
  loader; **WebSocket reconnect now uses exponential backoff** (1s→30s, reset on
  open). Client accepts `VITE_API_URL` alias; WS derives `wss://` from an https
  base.
- **UI polish (verified in preview via DOM):**
  - Empty space under tasks removed — the board is sized to its content height
    (`wrapH` 664→395, gap below SVAR = 0), scrolls for larger plans.
  - Last task label no longer clipped — right window margin widened (`+2`→`+5`
    days) so SVAR's right-of-bar label ("Demo") has room.
- **Docs:** `ROADMAP_TO_PRODUCTION.md` restructured into scheduler / data &
  multi-user / AI safety (dry-run, prompt-injection, eval-set) / files /
  deploy & CI; `DEPLOY.md` step-by-step; README §5–6 + §9.

**Verified here:** `pytest -m "not live"` → 63 passed (incl. after CORS change),
`tsc -b` clean, cold-start loader + compact Gantt confirmed live via DOM,
`docker compose config` valid, no console errors.

## Blocked / not verified here (owner action)
- ⚠️ **`docker compose up` not run.** Docker CLI is installed (v29.2.1) but the
  daemon was unreachable in this environment — Docker Desktop was launched and
  the daemon polled repeatedly over several minutes; `docker version` against the
  server timed out and the `dockerDesktopLinuxEngine` pipe never appeared (likely
  needs WSL2/GUI). Compose + Dockerfiles are written to the docs and pass
  `docker compose config`, but a first real `up` may need a tweak. **Owner: run
  `docker compose up --build` on a machine with a running daemon.**
- **Live deployment** — external accounts + `OPENROUTER_API_KEY` (owner);
  follow `docs/DEPLOY.md`.
- **`docs/demo.gif`** — record on the running app.

## Environment note
The `.venv` was recreated this session — the old one pointed at a Python 3.12 that
no longer exists after the project moved; rebuilt on Python 3.13.2.

## Next step
**Deploy** using `docs/DEPLOY.md` (owner: connect Vercel + Render, set
`OPENROUTER_API_KEY`), then record `docs/demo.gif`.

## Run locally
- Backend: `cd apps/backend && uvicorn app.main:app --port 8000` (`.env` from `.env.example` + your key).
- Frontend: `cd apps/frontend && npm run dev` (Node 20+), proxies `/api` + `/ws` to `:8000`.
- Tests: `cd apps/backend && pytest -m "not live"` (offline) · `pytest tests/test_agent_scenarios.py` (live gate).
