import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev: proxy API + WebSocket to the FastAPI backend on :8000, so the frontend
// talks to same-origin paths (/api, /ws) and CORS/URLs stay simple.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
      "/ws": { target: "ws://localhost:8000", ws: true },
    },
  },
});
