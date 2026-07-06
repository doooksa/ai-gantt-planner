import { create } from "zustand";

import * as api from "../api/client";
import type { Plan } from "../types/plan";

interface PlanState {
  plan: Plan | null;
  loading: boolean;
  waking: boolean; // backend cold-starting (Render free tier sleeps when idle)
  error: string | null;
  wsConnected: boolean;
  selectedTaskId: string | null;

  bootstrap: () => Promise<void>;
  refresh: () => Promise<void>;
  selectTask: (id: string | null) => void;
  undo: () => Promise<void>;
  resetDemo: () => Promise<void>;
  uploadExcel: (file: File) => Promise<void>;
  connectWs: () => void;
  setError: (e: string | null) => void;
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

// Current WebSocket reconnect delay; grows on each failed attempt, resets on open.
let wsBackoffMs = 1000;

export const usePlanStore = create<PlanState>((set, get) => ({
  plan: null,
  loading: false,
  waking: false,
  error: null,
  wsConnected: false,
  selectedTaskId: null,

  // Initial load, resilient to a cold backend. On a free Render instance the
  // first request after idle can take ~30 s while the container spins up; we
  // retry with backoff and flag `waking` so the UI can show a "waking" loader
  // instead of an error.
  bootstrap: async () => {
    set({ loading: true });
    const deadline = Date.now() + 60_000; // give the cold start up to a minute
    let attempt = 0;
    for (;;) {
      try {
        const plan = await api.getPlan();
        set({ plan, loading: false, waking: false, error: null });
        return;
      } catch (e) {
        if (Date.now() >= deadline) {
          set({
            loading: false,
            waking: false,
            error:
              "Не удалось связаться с сервером. Обновите страницу — возможно, " +
              "бесплатный инстанс ещё просыпается.",
          });
          return;
        }
        // First failure likely means the backend is asleep — show the loader.
        set({ waking: true });
        attempt += 1;
        await sleep(Math.min(3000, 1000 + attempt * 500));
      }
    }
  },

  refresh: async () => {
    set({ loading: true });
    try {
      const plan = await api.getPlan();
      set({ plan, loading: false });
    } catch (e) {
      set({ error: (e as Error).message, loading: false });
    }
  },

  selectTask: (id) => set({ selectedTaskId: id }),

  undo: async () => {
    try {
      await api.undo();
      await get().refresh();
    } catch (e) {
      set({ error: (e as Error).message });
    }
  },

  resetDemo: async () => {
    try {
      await api.resetDemo();
      await get().refresh();
    } catch (e) {
      set({ error: (e as Error).message });
    }
  },

  uploadExcel: async (file) => {
    try {
      await api.uploadExcel(file);
      await get().refresh();
    } catch (e) {
      set({ error: (e as Error).message });
    }
  },

  // {version, diff} broadcast on every mutation -> just re-fetch the plan so the
  // Gantt reflects changes from any source (chat, another tab, undo, upload).
  // Reconnect with exponential backoff (1s → 2s → 4s … capped at 30s) so a
  // sleeping/redeploying backend does not hammer the server, and resets to fast
  // reconnects once a connection succeeds.
  connectWs: () => {
    try {
      const ws = new WebSocket(api.wsUrl());
      ws.onopen = () => {
        set({ wsConnected: true });
        wsBackoffMs = 1000; // healthy connection -> reset backoff
      };
      ws.onmessage = () => void get().refresh();
      ws.onclose = () => {
        set({ wsConnected: false });
        const delay = wsBackoffMs;
        wsBackoffMs = Math.min(wsBackoffMs * 2, 30_000);
        setTimeout(() => get().connectWs(), delay);
      };
      ws.onerror = () => ws.close();
    } catch {
      /* ignore; reconnect handled on close */
    }
  },

  setError: (e) => set({ error: e }),
}));
