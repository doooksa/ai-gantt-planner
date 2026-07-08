# Project status

_Snapshot of where the AI Gantt Planner stands._

## ✅ READY FOR SUBMISSION — 2026-07-08

All three phases complete and gated; **deployed and verified live**. Only
`docs/demo.gif` remains (a recording, no code).

- **Live:** [frontend (Vercel)](https://ai-gantt-planner-three.vercel.app) ·
  [backend (Render)](https://ai-gantt-api.onrender.com/api/health) ·
  [Swagger](https://ai-gantt-api.onrender.com/docs)
- **Prod agent gate — 10/10** reference commands passed against the live Render
  backend (per-command 3.4–6.7 s), plus a focused chat run (Applied changes +
  Undo confirmed). Model: `anthropic/claude-haiku-4.5` via OpenRouter.
- **Offline CI (GitHub Actions):** green — `pytest -m "not live"` (63) + frontend build.
- **Reproducibility:** fresh `git clone` from GitHub + README §5 followed verbatim
  → backend 63 passed, servers up, frontend serves & proxies; sample_plan.xlsx
  (downloaded from GitHub) imports cleanly via the API.
- **MCP self-connection** uses an in-process transport (no host-header/proxy issues
  on Render); errors are unwrapped; `/api/health` reports the deployed commit.
- **UI/UX pass:** dark theme (SVAR WillowDark) + single accent, floating-card
  panels, Applied-changes icons, day/week gridlines, synchronized row↔bar hover,
  dates inside wide bars. Desktop-first; mobile is a deliberate roadmap item.
- **README** is in Russian; the roadmap covers frontend/UX (mobile deferral,
  sync-hover, remaining UI ideas).

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

## Remaining / not verified here
- **`docs/demo.gif`** — the one open deliverable. Record the running app
  (chat edit → Applied changes → live Gantt/WS update → Undo; Excel; task modal).
- ⚠️ **`docker compose up` not run.** The Docker daemon was unreachable in the dev
  environment. Compose + Dockerfiles pass `docker compose config`, but a first
  real `up` may need a tweak. (Not on the critical path — prod runs on
  Render/Vercel directly, verified live.)

## Deployment — done & verified
Live on **Vercel** (frontend) + **Render** (backend), `OPENROUTER_API_KEY` set on
Render. Verified live: health, plan, Excel export, CORS matches the Vercel origin,
and the **10-command agent gate passed 10/10** against prod. Follow
`docs/DEPLOY.md` to reproduce the setup.

## Environment note
The `.venv` was recreated this session — the old one pointed at a Python 3.12 that
no longer exists after the project moved; rebuilt on Python 3.13.2.

## Next step
Record `docs/demo.gif` on the running app. Everything else is done, gated, and
live.

## After moving this folder (read first if paths look broken)

A move breaks environment-specific absolute paths. To recover:

1. **Recreate the backend venv** — it is gitignored and its scripts hardcode the
   old path, so it will not work after a move:
   ```bash
   cd apps/backend
   rm -rf .venv
   python -m venv .venv
   .venv/Scripts/python -m pip install -r requirements.txt   # *nix: .venv/bin/python
   .venv/Scripts/python -m pytest -m "not live"              # expect 63 passed
   ```
   (Last rebuilt on Python 3.13.2; the old venv pointed at a since-removed 3.12.)
2. **Frontend** — `node_modules` may survive a move, but if `npm run dev`/`tsc`
   misbehaves: `cd apps/frontend && rm -rf node_modules && npm install`.
3. **`<repo-parent>/.claude/launch.json`** (used by the preview tool, lives one
   level above this repo) contains **absolute** paths to `node.exe` and the repo;
   update them to the new location, or just run the frontend with `npm run dev`.
4. Everything else (source, git history, deploy manifests, docs) is
   path-independent and travels with the folder. Remote is intact:
   `origin → github.com/doooksa/ai-gantt-planner` (branch `main`, all work pushed).

## Run locally
- Backend: `cd apps/backend && uvicorn app.main:app --port 8000` (`.env` from `.env.example` + your key).
- Frontend: `cd apps/frontend && npm run dev` (Node 20+), proxies `/api` + `/ws` to `:8000`.
- Tests: `cd apps/backend && pytest -m "not live"` (offline) · `pytest tests/test_agent_scenarios.py` (live gate).
