# Roadmap to production

This is a test-assignment build: Phases 1–3 are complete and gated, and the app
deploys to Vercel + Render. This document lists what a real production version
would need beyond the assignment scope, and why each item was consciously
deferred rather than missed. It is organized into five areas: **scheduler**,
**data & multi-user**, **AI safety**, **files**, and **deployment & CI**.

**Design stance (why this roadmap is incremental, not a rewrite):** correctness
lives in the deterministic backend — validators + topological scheduler + atomic
patches — not in the LLM. The model only turns natural language into a structured
`Patch`; the backend validates and recomputes. Every item below extends that
spine rather than reworking it.

---

## 1. Scheduler

Today: existence check → cycle detection (topological sort) → forward pass, in
**calendar days**, recomputed deterministically after every mutation.

- **Working days & calendars.** Move from calendar days to working days: skip
  weekends, per-team holiday calendars, per-assignee working hours. This is a
  localized change in `domain/scheduler.py` (the forward pass), deliberately
  isolated so it swaps in without touching validation or storage.
- **Resource leveling.** The model derives earliest dates from dependencies
  only; it does not stop one person holding two overlapping tasks. Add a leveling
  pass, or at minimum an over-allocation warning surfaced in the UI (this also
  makes the "кто самый загруженный" answer actionable).
- **Milestones & date constraints.** Support zero-duration milestones and
  "must-start-on / no-earlier-than" constraints, which a pure forward pass can't
  express yet.
- **Critical path & slack.** Compute the critical path and per-task slack so the
  UI can highlight what actually moves the end date.

## 2. Data & multi-user

Today: single project in SQLite, `version` bump per mutation, snapshots for undo.

- **Durable database.** SQLite on Render's ephemeral disk resets on each
  deploy/restart. Move to managed Postgres (Render/Neon). Storage is already
  behind `storage/db.py`, so this is a driver swap plus migrations (Alembic).
- **Multi-project & multi-user.** Single-project by spec. Real use needs a
  `Project` entity, per-project plans, and row-level scoping — plus **auth**
  (OIDC / magic link) and **authorization** (who may edit which project), both
  explicitly out of scope here.
- **Concurrent editing.** `version` is broadcast but the client only re-fetches.
  Add optimistic-concurrency rejection ("plan changed under you") and, for live
  co-editing, a shared realtime layer (see §5).
- **Snapshot retention.** Undo keeps snapshots with no pruning; add a retention
  window and a redo stack.

## 3. AI safety

The core guardrail already exists: **the LLM cannot write to the database.** It
can only emit a structured `Patch` that the backend validates, applies
atomically, and recomputes. Production hardens this further.

- **Dry-run before apply (already in place, extend it).** `validate_patch` is a
  no-write dry run returning the diff + errors; the agent is instructed to
  validate before `apply_patch`, and `apply_patch` is atomic (one bad op rolls
  back the whole patch). Production should **surface the dry-run diff to the user
  for confirmation on destructive ops** (delete / mass-reassign) instead of
  applying immediately, and require an explicit confirm step in the UI.
- **Prompt-injection resistance.** Because the model's only effect is a
  schema-checked `Patch` that the backend re-validates (existence, cycles,
  durations), injected instructions **cannot corrupt the schedule or reach the
  DB**. Remaining risk is that injection could still drive *valid but unwanted*
  edits. Mitigations: treat plan text / imported Excel content as untrusted (it
  already only becomes data, never tool authority); constrain which ops a session
  may apply; cap patch size and blast radius; add a confirmation gate for
  mass/destructive selectors (`by_assignee` touching many tasks).
- **Evaluation set.** Grow the 10-command gate
  (`tests/test_agent_scenarios.py`) into a real eval suite: adversarial and
  ambiguous phrasings, multi-step edits, injection attempts, and
  should-refuse cases (e.g. "delete everything"). Run it in CI against a cheap
  model on a schedule, track a pass-rate over time, and gate model/prompt changes
  on it. This is what lets the model be swapped safely (the point of the
  tools/validation layer).
- **Cost, quota & observability.** `/api/chat` calls a paid model with no
  per-user quota — add rate limiting and a token budget. Log every agent turn
  (tool calls, patches, validation errors) to a trace store so bad edits are
  debuggable; today logs are local only.

## 4. Files (Excel I/O)

Today: import/export the 5-column format (openpyxl, first sheet, `read_only`),
export adds computed start/end; clear per-row errors.

- **Round-trip fidelity.** The 5-column format has no place for a manual shift
  (`offset_days`), so a round-trip loses it (documented + tested). A richer
  export (extra column or a metadata sheet) would preserve it.
- **Robustness & scale.** Larger files, multiple sheets, streaming import, and
  stricter validation messages with cell references.
- **More formats.** CSV and MS Project / `.mpp` import-export as follow-ups.

## 5. Deployment & CI

Today: `render.yaml` (backend, Docker) + `vercel.json` (frontend) + a
`docker-compose` for local; the frontend already handles Render's cold start
(retry/backoff loader + WS backoff).

- **CI/CD.** Run `pytest -m "not live"` + `tsc` on every PR; run the live agent
  gate (real tokens) on a schedule. Block deploys on red.
- **Health, metrics, alerting.** `/api/health` exists; add readiness vs.
  liveness, request metrics, and error-rate alerts. An uptime pinger doubles as a
  keep-warm to remove the ~30 s cold start (or move to a paid always-on tier).
- **Realtime scaling.** `/ws` uses an in-process event bus, so it's single-
  instance. Horizontal scaling needs a shared bus (Redis pub/sub) and sticky
  sessions, or a hosted realtime service.
- **End-to-end tests.** Playwright for the full chat → Gantt → undo loop;
  property-based tests for the scheduler (random DAGs vs. a reference
  implementation); load tests for `/api/chat` and `/ws` fan-out.
