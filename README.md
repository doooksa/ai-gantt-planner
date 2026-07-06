# AI Gantt Planner

Interactive Gantt chart + an LLM chat agent that edits the project plan in
natural language. Import/export Excel. The agent never writes to the database
directly — it only translates natural language into structured operations
through **MCP tools**; the backend validates every operation, applies it
atomically, and **deterministically recomputes the schedule**. Task dates are
always *derived*, never stored.

> Status: **Phases 1–3 complete and gated locally; deploy config added.** The
> full demo scenario (chat edits → applied changes → live Gantt/WS update → undo,
> plus Excel and the task modal) runs end-to-end against `uvicorn :8000` + Vite
> `:5173`. Deployment manifests for Vercel (frontend) and Render (backend) are in
> the repo; see [§6](#6-deployment). Demo gif to follow.

<!-- TODO: demo.gif -->

---

## 1. Architecture

```
                    ┌─────────────────────────────────────────────────────┐
  Browser           │  FastAPI process (one)                              │
 ┌────────┐  REST   │   ┌───────────────┐        ┌──────────────────────┐ │
 │ React  │◄──────► │   │  REST routes  │        │  MCP server (/mcp,    │ │
 │  +SVAR │  SSE    │   │  /api/*       │        │  streamable HTTP)     │ │
 │  Gantt │◄──────► │   │  /api/chat    │        │  get_plan             │ │
 │  +chat │   WS    │   └──────┬────────┘        │  validate_patch       │ │
 └────────┘◄──────► │          │                 │  apply_patch          │ │
             /ws    │   ┌──────▼────────┐  MCP    │  undo_last            │ │
                    │   │  agent loop   │◄───────►│  (client over HTTP)   │ │
                    │   │  (llm/agent)  │  tools  └──────────┬───────────┘ │
                    │   └──────┬────────┘                    │             │
                    │          │ OpenRouter             ┌────▼──────────┐  │
                    │          ▼ (openai SDK)           │  services.py  │  │
                    │      ☁ LLM                        │  (one path)   │  │
                    │                                   └────┬──────────┘  │
                    │                     ┌──────────────────▼───────────┐ │
                    │                     │ domain: scheduler/validators │ │
                    │                     │ patches · storage (SQLite)   │ │
                    │                     └──────────────────────────────┘ │
                    └─────────────────────────────────────────────────────┘
```

Both the REST routes and the MCP tools go through **one `services.py` layer**, so
an edit made by the agent and an edit made by the user behave identically and
both broadcast `{version, diff}` over the WebSocket.

## 2. How MCP is used

The LLM is **not the source of truth** and has **no direct access to the data**.
It can only call four MCP tools:

| Tool | Purpose |
|---|---|
| `get_plan()` | current plan with computed dates |
| `validate_patch(patch)` | dry-run: diff + errors, **not applied** |
| `apply_patch(patch)` | apply atomically, recompute, broadcast, return diff |
| `undo_last()` | revert to the previous snapshot |

Why a tools layer instead of letting the LLM write to the DB: every mutation is
**validated** (existence, cycles, durations), **atomic** (one bad op rolls back
the whole patch), and the schedule is **deterministically recomputed** by code,
not the model. The model's job is just NL → structured `Patch`; correctness is
the backend's job. This is what makes the system robust to the choice of model
(see [Model selection](#8-model-selection)).

## 3. How the agent works

Loop (`apps/backend/app/llm/agent.py`, max 10 iterations):

1. `list_tools()` from the MCP server → convert schemas to OpenAI tools format
   (`mcp_openai_bridge.py`).
2. user message → `chat.completions` with tools → `tool_calls`
   → `session.call_tool()` → results fed back → repeat until a final text answer.
3. Guidance: read the plan first (`get_plan`), check with `validate_patch`, then
   `apply_patch`; mass edits are **one** patch with a selector (e.g.
   `by_assignee`), not N calls.

The agent is transport-agnostic: it takes a connected MCP `ClientSession` and an
OpenAI-compatible client, so the whole loop is unit-tested offline with a fake
LLM, and the live 10-command gate runs against a real model.

## 4. Excel format

Import columns (case-insensitive, whitespace-normalized headers), first sheet
only, `read_only=True`:

```
задача, описание, исполнитель, длительность, предшественники
```

- **предшественники** — task *names*, comma-separated, resolved to ids;
  an unknown name is a clear user error.
- **длительность** — integer ≥ 1; an invalid value errors with the **row number**.
- **Export** adds computed `дата начала`, `дата конца`.

See `examples/sample_plan.xlsx` (same as the demo seed).

## 5. Local setup

### Backend (works today)

```bash
cd apps/backend
python -m venv .venv
.venv/Scripts/activate            # Windows;  source .venv/bin/activate on *nix
pip install -r requirements.txt
cp ../../.env.example .env         # then put your OPENROUTER_API_KEY in .env
uvicorn app.main:app --reload --port 8000
```

- Offline tests: `pytest -m "not live"` (63 passed).
- Live agent gate (needs `OPENROUTER_API_KEY`): `pytest tests/test_agent_scenarios.py`.

### Frontend (Phase 3) — **requires Node.js 20+**

```bash
cd apps/frontend
npm install
npm run dev            # http://localhost:5173, proxies the API to :8000
```

### docker-compose

```bash
cp .env.example apps/backend/.env      # then set OPENROUTER_API_KEY
docker compose up --build              # backend + frontend (nginx)
# open http://localhost:5173
```

The frontend container (nginx) serves the built SPA and reverse-proxies `/api`
and `/ws` to the backend container, so the browser talks **same-origin** —
mirroring the Vercel+Render topology as closely as a single host allows.

> ⚠️ **Not run-verified locally.** The Docker daemon was unavailable in the dev
> environment where these files were authored, so `docker compose up` was **not
> executed end-to-end here.** The compose file passes `docker compose config`
> (syntax/interpolation validated) and the Dockerfiles follow the standard
> Python-slim / node-build→nginx patterns, but a first run on a machine with a
> running daemon may still need a tweak. The non-Docker local setup above **is**
> verified (63 tests green, frontend builds, demo scenario passes).

## 6. Deployment

Frontend → **Vercel**, backend → **Render**. Manifests are committed:

| File | Role |
|---|---|
| `render.yaml` | Render Blueprint — backend as a Docker web service, `healthCheckPath: /api/health` |
| `apps/backend/Dockerfile` | backend image (binds Render's `$PORT`) |
| `apps/frontend/vercel.json` | Vercel build + SPA rewrites |
| `apps/frontend/Dockerfile` + `nginx.conf` | only for docker-compose, not for Vercel |

**Environment variables**

*Backend (Render):*

| Var | Example | Notes |
|---|---|---|
| `OPENROUTER_API_KEY` | `sk-or-…` | secret; set in dashboard |
| `LLM_MODEL` | `anthropic/claude-haiku-4.5` | default |
| `FRONTEND_ORIGIN` | `https://ai-gantt-planner.vercel.app` | CORS allowlist; **comma-separated** list allowed for Vercel preview URLs |
| `DATABASE_URL` | `sqlite:///./gantt.db` | ephemeral on free tier (see roadmap) |

*Frontend (Vercel):*

| Var | Example | Notes |
|---|---|---|
| `VITE_API_BASE` | `https://ai-gantt-api.onrender.com` | backend origin; `VITE_API_URL` accepted as an alias. WS auto-derives `wss://` from an `https` base |

**Cold start.** Render's free tier sleeps after ~15 min idle; the first request
then takes ~30 s. The frontend handles this: initial load retries with backoff
behind a **"Сервер просыпается…"** loader, and the WebSocket auto-reconnects
every 2 s — so a sleeping backend degrades to a short wait, not an error.

**Step-by-step click-through** (Render then Vercel) is in
[docs/DEPLOY.md](docs/DEPLOY.md).

## 7. Excel + API reference

```
GET  /api/plan                GET  /api/health
POST /api/upload-excel        POST /api/undo
GET  /api/export-excel        POST /api/reset-demo
POST /api/chat  (SSE)         WS   /ws   → {version, diff}
```
CORS origin comes from `FRONTEND_ORIGIN`.

## 8. Model selection

The model is chosen with the single env var `LLM_MODEL` (OpenRouter id). The
default is **`anthropic/claude-haiku-4.5`**.

Measured on the Phase 2 gate — the 10 reference commands
(`apps/backend/tests/test_agent_scenarios.py`):

| Model | Correctness | Stability | Time / full run |
|---|---|---|---|
| **`anthropic/claude-haiku-4.5`** (default) | **10 / 10** | **5 / 5 runs** | ~86–104 s |
| `anthropic/claude-sonnet-4.5` | **10 / 10** | 1 run (control) | ~140 s |

Both models pass every command. Haiku 4.5 matches Sonnet 4.5's correctness at
roughly **1.5× lower latency and cost**, so it is the default.

**Takeaway:** correctness comes from the tools/validation/scheduler layer, not
from the model — so the architecture is **robust to the choice of model**.
Upgrading is a **one-variable change**: set `LLM_MODEL=anthropic/claude-sonnet-4.5`
(or any OpenRouter model) in `.env`; no code changes.

> Note: an earlier `.env` used `anthropic/claude-3.5-haiku`, which returns
> HTTP 404 ("No endpoints found") on OpenRouter — the correct current id is
> `anthropic/claude-haiku-4.5`.

## 9. AI assistants usage

This project was built with Claude Code (Opus 4.8), tracked per phase in
[docs/AI_USAGE.md](docs/AI_USAGE.md): what was delegated, what the model got
wrong and how it was fixed, and what was verified by hand. Highlights:

- Domain, scheduler, validators, patches, Excel I/O, storage, and the full MCP +
  agent backend were generated with Claude Code, then gated by tests.
- The frontend (Gantt board, chat panel, task modal, toolbar) and the whole
  deployment layer (Dockerfiles, nginx, compose, `render.yaml`, `vercel.json`,
  cold-start handling) were generated with Claude Code.
- Notable fixes made in-dialogue: `offset_days` to keep dates derived while
  supporting shifts; refusing shifts before the earliest date; documenting the
  op-payload catalog in tool descriptions (fixed agent flakiness prompt-only);
  date-fns scale formatters (SVAR's string tokens aren't date-fns); sizing the
  Gantt to content height to drop empty rows and widening the window so the last
  task label isn't clipped.
- Honesty on verification: `docker compose up` could **not** be run in the dev
  environment (no Docker daemon), so it's labeled *not verified locally* rather
  than presented as tested — see [docs/AI_USAGE.md](docs/AI_USAGE.md) and
  [docs/STATUS.md](docs/STATUS.md).

## 10. Known limitations

- **Calendar days**, not working days (working-day scheduling is on the roadmap).
- Excel round-trip does not preserve a manual shift (`offset_days`) — the 5-column
  format has no place for it; structure is preserved (documented + tested).
- Single project, no auth, no drag-and-drop field editing (out of scope by spec).
- Agent SSE streams events (`tool`/`applied`/`message`/`done`), not token-by-token.

## 11. Roadmap

See [docs/ROADMAP_TO_PRODUCTION.md](docs/ROADMAP_TO_PRODUCTION.md).
