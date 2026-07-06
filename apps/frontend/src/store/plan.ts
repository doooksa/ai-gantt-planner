import { create } from "zustand";

import * as api from "../api/client";
import type { Plan } from "../types/plan";

interface PlanState {
  plan: Plan | null;
  loading: boolean;
  error: string | null;
  wsConnected: boolean;
  selectedTaskId: string | null;

  refresh: () => Promise<void>;
  selectTask: (id: string | null) => void;
  undo: () => Promise<void>;
  resetDemo: () => Promise<void>;
  uploadExcel: (file: File) => Promise<void>;
  connectWs: () => void;
  setError: (e: string | null) => void;
}

export const usePlanStore = create<PlanState>((set, get) => ({
  plan: null,
  loading: false,
  error: null,
  wsConnected: false,
  selectedTaskId: null,

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
  connectWs: () => {
    try {
      const ws = new WebSocket(api.wsUrl());
      ws.onopen = () => set({ wsConnected: true });
      ws.onmessage = () => void get().refresh();
      ws.onclose = () => {
        set({ wsConnected: false });
        setTimeout(() => get().connectWs(), 2000); // auto-reconnect
      };
      ws.onerror = () => ws.close();
    } catch {
      /* ignore; reconnect handled on close */
    }
  },

  setError: (e) => set({ error: e }),
}));
