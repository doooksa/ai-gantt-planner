import type { ChatEvent, ChatMessage, Plan } from "../types/plan";

// Empty base -> same-origin; the Vite dev server proxies /api and /ws to :8000.
// VITE_API_BASE is canonical; VITE_API_URL is accepted as an alias. Trailing
// slash trimmed so `${BASE}/api/...` never doubles up.
const BASE = (
  (import.meta.env.VITE_API_BASE as string | undefined) ??
  (import.meta.env.VITE_API_URL as string | undefined) ??
  ""
).replace(/\/$/, "");

async function errText(r: Response): Promise<string> {
  try {
    const j = await r.json();
    return j.detail || j.error || r.statusText;
  } catch {
    return r.statusText;
  }
}

async function jget<T>(path: string): Promise<T> {
  const r = await fetch(BASE + path);
  if (!r.ok) throw new Error(await errText(r));
  return r.json();
}

async function jpost<T>(path: string): Promise<T> {
  const r = await fetch(BASE + path, { method: "POST" });
  if (!r.ok) throw new Error(await errText(r));
  return r.json();
}

export const getPlan = () => jget<Plan>("/api/plan");
export const undo = () => jpost("/api/undo");
export const resetDemo = () => jpost("/api/reset-demo");
export const exportExcelUrl = () => BASE + "/api/export-excel";

export async function uploadExcel(file: File): Promise<unknown> {
  const fd = new FormData();
  fd.append("file", file);
  const r = await fetch(BASE + "/api/upload-excel", { method: "POST", body: fd });
  if (!r.ok) throw new Error(await errText(r));
  return r.json();
}

/** POST /api/chat and parse the SSE stream, invoking onEvent per event. */
export async function streamChat(
  message: string,
  history: ChatMessage[],
  onEvent: (ev: ChatEvent) => void,
): Promise<void> {
  const r = await fetch(BASE + "/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, history }),
  });
  if (!r.ok || !r.body) throw new Error(await errText(r));

  const reader = r.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let i: number;
    while ((i = buf.indexOf("\n\n")) >= 0) {
      const frame = buf.slice(0, i);
      buf = buf.slice(i + 2);
      for (const line of frame.split("\n")) {
        if (line.startsWith("data: ")) {
          try {
            onEvent(JSON.parse(line.slice(6)) as ChatEvent);
          } catch {
            /* ignore malformed frame */
          }
        }
      }
    }
  }
}

export function wsUrl(): string {
  if (BASE) return BASE.replace(/^http/, "ws") + "/ws";
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${location.host}/ws`;
}
