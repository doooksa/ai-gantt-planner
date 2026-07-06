import { useRef } from "react";

import { exportExcelUrl } from "../api/client";
import { usePlanStore } from "../store/plan";

export function Toolbar() {
  const plan = usePlanStore((s) => s.plan);
  const wsConnected = usePlanStore((s) => s.wsConnected);
  const undo = usePlanStore((s) => s.undo);
  const resetDemo = usePlanStore((s) => s.resetDemo);
  const uploadExcel = usePlanStore((s) => s.uploadExcel);
  const fileRef = useRef<HTMLInputElement>(null);

  return (
    <header className="toolbar">
      <div className="brand">📊 AI Gantt Planner</div>
      <div className="toolbar-actions">
        <button onClick={() => fileRef.current?.click()}>Импорт Excel</button>
        <input
          ref={fileRef}
          type="file"
          accept=".xlsx"
          hidden
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void uploadExcel(f);
            e.target.value = "";
          }}
        />
        <a className="btn" href={exportExcelUrl()}>
          Экспорт Excel
        </a>
        <button onClick={() => void undo()}>Отменить</button>
        <button onClick={() => void resetDemo()}>Сброс demo</button>
        <span className="version">v{plan?.version ?? "—"}</span>
        <span className={"ws " + (wsConnected ? "on" : "off")} title="WebSocket">
          {wsConnected ? "● online" : "○ offline"}
        </span>
      </div>
    </header>
  );
}
