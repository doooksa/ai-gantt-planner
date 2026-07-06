import { useMemo, useRef } from "react";
import { Gantt, Willow } from "@svar-ui/react-gantt";
import type { IApi, ILink, ITask } from "@svar-ui/react-gantt";
import "@svar-ui/react-gantt/style.css";

import { usePlanStore } from "../store/plan";

function isoToDate(iso: string, addDays = 0): Date {
  const d = new Date(iso + "T00:00:00");
  if (addDays) d.setDate(d.getDate() + addDays);
  return d;
}

const SCALES = [
  { unit: "month", step: 1, format: "MMMM yyyy" },
  { unit: "day", step: 1, format: "d" },
];

export function GanttBoard() {
  const plan = usePlanStore((s) => s.plan);
  const selectTask = usePlanStore((s) => s.selectTask);
  const apiRef = useRef<IApi | null>(null);

  const { tasks, links } = useMemo(() => {
    const tasks: ITask[] = (plan?.tasks ?? []).map((t) => ({
      id: t.id,
      text: t.name,
      start: isoToDate(t.start),
      // Our end is the inclusive last day; SVAR's end is exclusive -> +1 day.
      end: isoToDate(t.end, 1),
      type: "task",
      progress: 0,
    }));

    const links: ILink[] = [];
    for (const t of plan?.tasks ?? []) {
      for (const p of t.predecessor_ids) {
        links.push({ id: `${p}->${t.id}`, source: p, target: t.id, type: "e2s" });
      }
    }
    return { tasks, links };
  }, [plan]);

  if (!plan) return <div className="gantt-empty">Загрузка плана…</div>;
  if (!plan.tasks.length) return <div className="gantt-empty">План пуст.</div>;

  return (
    <div className="gantt-wrap">
      {/* readonly: edits go through the chat agent / Excel, not drag-and-drop. */}
      <Willow>
        <Gantt
          readonly
          tasks={tasks}
          links={links}
          scales={SCALES as never}
          columns={false}
          cellWidth={40}
          cellHeight={40}
          init={(api: IApi) => {
            apiRef.current = api;
            api.on("select-task", (ev: { id?: string | number }) => {
              if (ev?.id != null) selectTask(String(ev.id));
            });
          }}
        />
      </Willow>
    </div>
  );
}
