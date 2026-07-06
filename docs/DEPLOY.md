# Deploy — step by step (Render + Vercel)

Order matters a little: deploy the **backend first** to get its URL, then the
**frontend**, then come back and set the backend's `FRONTEND_ORIGIN` to the
frontend URL. Plan ~15 minutes. You need: a GitHub repo with this code, an
[OpenRouter](https://openrouter.ai) API key, a Render account, a Vercel account.

> Prerequisite: push this repo to GitHub (both Render and Vercel deploy from it).

---

## Part A — Backend on Render

1. Go to **dashboard.render.com** → **New +** → **Blueprint**.
2. **Connect** your GitHub account and pick this repository. Render detects
   [`render.yaml`](../render.yaml) and shows a service named **`ai-gantt-api`**.
3. Click **Apply**. Render starts building the Docker image from
   `apps/backend/Dockerfile`.
4. It will pause because `OPENROUTER_API_KEY` and `FRONTEND_ORIGIN` are marked
   "set in dashboard". Open the **`ai-gantt-api`** service → **Environment** →
   **Add / edit** these:
   - `OPENROUTER_API_KEY` = your OpenRouter key (`sk-or-…`).
   - `FRONTEND_ORIGIN` = `http://localhost:5173` **for now** (temporary — you'll
     change it in Part C once you have the Vercel URL).
   - `LLM_MODEL` and `DATABASE_URL` are already filled from `render.yaml` — leave
     them.
5. Click **Save, rebuild and deploy**. Wait for **Live** (first build ~3–5 min).
6. Copy the service URL, e.g. `https://ai-gantt-api.onrender.com`.
7. **Verify:** open `https://ai-gantt-api.onrender.com/api/health` in a browser
   → you should see `{"status":"ok"}`. (If it hangs a few seconds, that's the
   free-tier cold start — normal.)

---

## Part B — Frontend on Vercel

1. Go to **vercel.com/new** → **Import** this GitHub repository.
2. **Important — set the root directory.** In *Configure Project*, set
   **Root Directory** = `apps/frontend`. Vercel then picks up
   [`vercel.json`](../apps/frontend/vercel.json) and auto-detects **Vite**
   (build `npm run build`, output `dist`) — leave those as detected.
3. Expand **Environment Variables** and add:
   - `VITE_API_BASE` = your Render URL from Part A, step 6
     (e.g. `https://ai-gantt-api.onrender.com`) — **no trailing slash**.
4. Click **Deploy**. Wait for the build to finish (~1–2 min).
5. Copy your frontend URL, e.g. `https://ai-gantt-planner.vercel.app`.

> Why `VITE_API_BASE` matters: it's baked in at **build time**. If you change it
> later you must **redeploy** the frontend (Vercel → Deployments → ⋯ → Redeploy).
> The WebSocket URL is derived automatically — an `https://` base yields
> `wss://…/ws`.

---

## Part C — Wire CORS back to the frontend

1. Back in **Render** → `ai-gantt-api` → **Environment**.
2. Set `FRONTEND_ORIGIN` = your Vercel URL from Part B, step 5
   (e.g. `https://ai-gantt-planner.vercel.app`) — **no trailing slash**.
   - To also allow Vercel preview deployments, use a comma-separated list, e.g.
     `https://ai-gantt-planner.vercel.app,https://ai-gantt-planner-git-main-you.vercel.app`.
3. **Save** → Render redeploys (~1 min).

---

## Part D — Smoke test the live app

Open your Vercel URL and check:

1. The Gantt board loads the seed plan (if the backend was asleep you'll see the
   **"Сервер просыпается…"** loader for ~30 s first — expected).
2. In the chat, send: **`Увеличь длительность Design до 5 дней`** → an
   *Applied changes* block appears and the Gantt shifts live (that's the
   WebSocket working over `wss://`).
3. Click **Undo** → the change reverts.
4. **Export Excel** downloads a file; **Reset demo** restores the seed.

If chat fails with an auth error, re-check `OPENROUTER_API_KEY` on Render.
If the board loads but chat/WS is blocked (CORS error in the browser console),
re-check `FRONTEND_ORIGIN` exactly matches the Vercel origin (scheme + host, no
trailing slash).

---

## Notes & gotchas

- **Cold starts** are inherent to Render's free tier. Options: upgrade to a paid
  instance, or add an uptime pinger hitting `/api/health` every ~10 min to keep
  it warm.
- **Data is ephemeral** on the free tier — any plan edits reset on the next
  deploy/restart (SQLite lives on the container disk). Durable Postgres is in the
  [roadmap](ROADMAP_TO_PRODUCTION.md).
- **Redeploys:** backend redeploys on push automatically (`autoDeploy: true`).
  Frontend redeploys on push too; but remember a `VITE_API_BASE` **change**
  needs a manual redeploy since it's compiled in.
