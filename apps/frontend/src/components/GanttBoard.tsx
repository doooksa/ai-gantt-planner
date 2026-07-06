import { useMemo, useRef } from "react";
import { Gantt, Willow } from "@svar-ui/react-gantt";
import type { IApi, ILink, ITask } from "@svar-ui/react-gantt";
import "@svar-ui/react-gantt/style.css";
import { format } from "date-fns";
import { ru } from "date-fns/locale";

import { usePlanStore } from "../store/plan";

function isoToDate(iso: string, addDays = 0): Date {
  const d = new Date(iso + "T00:00:00");
  if (addDays) d.setDate(d.getDate() + addDays);
  return d;
}

function shiftDays(date: Date, days: number): Date {
  const d = new Date(date);
  d.setDate(d.getDate() + days);
  return d;
}

// Left grid columns: task / assignee / duration.
const COLUMNS = [
  { id: "text", header: "Задача", flexgrow: 2, width: 150 },
  { id: "assignee", header: "Исполнитель", width: 120, template: (_v: unknown, row: ITask) => row.assignee || "—" },
  { id: "duration", header: "Длительность", width: 120, align: "center" },
];

// SVAR scale `format` is a function (its string tokens are not date-fns), so we
// format with date-fns + Russian locale. Week header shows the week's start
// date, day header the day-of-month number.
const SCALES = [
  { unit: "week", step: 1, format: (d: Date) => format(d, "d MMM", { locale: ru }) },
  { unit: "day", step: 1, format: (d: Date) => format(d, "d") },
];

export function GanttBoard() {
  const plan = usePlanStore((s) => s.plan);
  const selectTask = usePlanStore((s) => s.selectTask);
  const apiRef = useRef<IApi | null>(null);

  const { tasks, links, start, end } = useMemo(() => {
    const src = plan?.tasks ?? [];
    const tasks: ITask[] = src.map((t) => ({
      id: t.id,
      text: t.name,
      assignee: t.assignee ?? "",
      start: isoToDate(t.start),
      // Our end is the inclusive last day; SVAR's end is exclusive -> +1 day.
      end: isoToDate(t.end, 1),
      duration: t.duration_days,
      type: "task",
      progress: 0,
    }));

    const links: ILink[] = [];
    for (const t of src) {
      for (const p of t.predecessor_ids) {
        links.push({ id: `${p}->${t.id}`, source: p, target: t.id, type: "e2s" });
      }
    }

    // Tight project window (a couple of days of padding) so a ~3-week plan fills
    // the view without large empty margins.
    let start: Date | undefined;
    let end: Date | undefined;
    if (tasks.length) {
      const minStart = Math.min(...tasks.map((t) => (t.start as Date).getTime()));
      const maxEnd = Math.max(...tasks.map((t) => (t.end as Date).getTime()));
      start = shiftDays(new Date(minStart), -2);
      end = shiftDays(new Date(maxEnd), 2);
    }
    return { tasks, links, start, end };
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
          columns={COLUMNS as never}
          scales={SCALES as never}
          start={start}
          end={end}
          cellWidth={44}
          cellHeight={38}
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
