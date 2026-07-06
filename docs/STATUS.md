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

## Open UI items (post-review, need a look in real Chrome)
- **Scale labels** switched from string tokens to date-fns formatter functions
  (+ ru locale); week = week-start date, day = day number. Verified as code; the
  embedded preview browser doesn't render SVAR scale cells, so **visual confirmation
  is pending in Chrome**.
- Grid columns restored (задача / исполнитель / длительность) — rendered OK.
- Explicit `start`/`end` window (±2 days) so a ~3-week plan fills the view (day/week
  scales) — no large empty margins.
- Agent replies shortened to a 1–2 sentence summary (details stay in Applied changes).

## Not started
- **Deployment** — frontend → Vercel, backend → Render; `docker-compose.yml`;
  `docs/ROADMAP_TO_PRODUCTION.md`; `docs/demo.gif`.

## Next step
**Deploy.** Prepare deploy config (Dockerfiles, docker-compose, `vercel.json` /
`render.yaml`, CORS/env wiring), then connect Vercel/Render accounts and set the
production `OPENROUTER_API_KEY` (owner action — external accounts + secret).

## Run locally
- Backend: `cd apps/backend && uvicorn app.main:app --port 8000` (`.env` from `.env.example` + your key).
- Frontend: `cd apps/frontend && npm run dev` (Node 20+), proxies `/api` + `/ws` to `:8000`.
- Tests: `cd apps/backend && pytest -m "not live"` (offline) · `pytest tests/test_agent_scenarios.py` (live gate).
