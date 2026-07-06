import { useEffect, useRef, useState } from "react";

import { streamChat } from "../api/client";
import { usePlanStore } from "../store/plan";
import type { ChatMessage, Diff, TaskDiff } from "../types/plan";

interface Turn {
  role: "user" | "assistant";
  content: string;
  applied: Diff[];
  pending: boolean;
}

const SUGGESTIONS = [
  'Перенеси задачу "Frontend" на 3 дня позже.',
  "Все задачи Ivan переназначь на Maria.",
  "Увеличь длительность Design до 5 дней.",
];

function summarizeTaskDiff(td: TaskDiff): string {
  const name = td.after?.name ?? td.before?.name ?? td.id;
  if (td.change === "added") return `добавлена «${name}»`;
  if (td.change === "removed") return `удалена «${name}»`;
  const b = td.before!;
  const a = td.after!;
  const parts: string[] = [];
  if (b.assignee !== a.assignee)
    parts.push(`исполнитель ${b.assignee ?? "—"} → ${a.assignee ?? "—"}`);
  if (b.duration_days !== a.duration_days)
    parts.push(`длительность ${b.duration_days} → ${a.duration_days} дн.`);
  if (b.start !== a.start) parts.push(`начало ${b.start} → ${a.start}`);
  if (JSON.stringify(b.predecessor_ids) !== JSON.stringify(a.predecessor_ids))
    parts.push("зависимости изменены");
  return `«${name}»: ${parts.length ? parts.join("; ") : "обновлена"}`;
}

function AppliedChanges({ diffs, onUndo }: { diffs: Diff[]; onUndo: () => void }) {
  const rows = diffs.flatMap((d) => d.tasks);
  const warnings = diffs.flatMap((d) => d.warnings);
  if (!rows.length && !warnings.length) return null;
  return (
    <div className="applied">
      <div className="applied-head">
        <span>Применённые изменения</span>
        <button className="undo-btn" onClick={onUndo}>
          ↶ Отменить
        </button>
      </div>
      <ul>
        {rows.map((td, i) => (
          <li key={i} className={`chg chg-${td.change}`}>
            {summarizeTaskDiff(td)}
          </li>
        ))}
      </ul>
      {warnings.map((w, i) => (
        <div key={i} className="warn">
          ⚠ {w}
        </div>
      ))}
    </div>
  );
}

export function ChatPanel() {
  const refresh = usePlanStore((s) => s.refresh);
  const undo = usePlanStore((s) => s.undo);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const scroller = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scroller.current?.scrollTo(0, scroller.current.scrollHeight);
  }, [turns, status]);

  function patchLastAssistant(patch: Partial<Turn>) {
    setTurns((prev) => {
      const next = [...prev];
      for (let i = next.length - 1; i >= 0; i--) {
        if (next[i].role === "assistant") {
          next[i] = { ...next[i], ...patch };
          break;
        }
      }
      return next;
    });
  }

  async function send(text?: string) {
    const message = (text ?? input).trim();
    if (!message || busy) return;
    setInput("");
    setBusy(true);
    setStatus(null);

    const history: ChatMessage[] = turns.map((t) => ({ role: t.role, content: t.content }));
    setTurns((prev) => [
      ...prev,
      { role: "user", content: message, applied: [], pending: false },
      { role: "assistant", content: "", applied: [], pending: true },
    ]);

    const applied: Diff[] = [];
    try {
      await streamChat(message, history, (ev) => {
        if (ev.type === "tool") setStatus(`Инструмент: ${ev.name}…`);
        else if (ev.type === "applied") applied.push(ev.diff);
        else if (ev.type === "message") patchLastAssistant({ content: ev.text });
        else if (ev.type === "done")
          patchLastAssistant({
            content: ev.text,
            applied: ev.applied?.length ? ev.applied : applied,
            pending: false,
          });
        else if (ev.type === "error")
          patchLastAssistant({ content: "Ошибка: " + ev.error, pending: false });
      });
    } catch (e) {
      patchLastAssistant({ content: "Ошибка: " + (e as Error).message, pending: false });
    } finally {
      setBusy(false);
      setStatus(null);
      void refresh(); // ensure the Gantt reflects the result (WS also triggers this)
    }
  }

  return (
    <div className="chat">
      <div className="chat-head">Чат-агент</div>
      <div className="chat-log" ref={scroller}>
        {turns.length === 0 && (
          <div className="chat-hint">
            <p>Опишите правку плана на русском. Например:</p>
            {SUGGESTIONS.map((s) => (
              <button key={s} className="suggestion" onClick={() => void send(s)}>
                {s}
              </button>
            ))}
          </div>
        )}
        {turns.map((t, i) => (
          <div key={i} className={`msg msg-${t.role}`}>
            <div className="bubble">
              {t.content || (t.pending ? <span className="typing">…</span> : "")}
            </div>
            {t.role === "assistant" && t.applied.length > 0 && (
              <AppliedChanges diffs={t.applied} onUndo={() => void undo()} />
            )}
          </div>
        ))}
        {status && <div className="chat-status">{status}</div>}
      </div>
      <form
        className="chat-input"
        onSubmit={(e) => {
          e.preventDefault();
          void send();
        }}
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Сообщение агенту…"
          disabled={busy}
        />
        <button type="submit" disabled={busy || !input.trim()}>
          {busy ? "…" : "▶"}
        </button>
      </form>
    </div>
  );
}
