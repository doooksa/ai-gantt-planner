import { useMemo, useRef } from "react";
import { Gantt, WillowDark } from "@svar-ui/react-gantt";
import type { IApi, ILink, ITask } from "@svar-ui/react-gantt";
import "@svar-ui/react-gantt/style.css";
import { format } from "date-fns";

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
// format with date-fns. Week header shows the week's start date as a short
// numeric `dd.MM` ("26.07") — fixed width so a narrow last-week cell at the right
// edge can't wrap to two lines and clip. Day header is the day-of-month number.
const SCALES = [
  { unit: "week", step: 1, format: (d: Date) => format(d, "dd.MM") },
  { unit: "day", step: 1, format: (d: Date) => format(d, "d") },
];

const CELL_HEIGHT = 38; // px per task row (matches the `cellHeight` prop)
const SCALE_HEIGHT = 73; // px for the two-row scale header (Willow theme)
const HSCROLL_SLACK = 18; // room for the horizontal scrollbar

// Bar label: the task NAME always (the name matters more than the dates — dates
// are readable off the scale, the name is not), plus a small dd.MM–dd.MM range
// appended only when the task is long enough (>= 3 days). If "name + dates" don't
// fit, the bar clips the trailing dates first, so the name is preserved.
function BarLabel({ data }: { data: ITask }) {
  const duration = (data.duration as number) ?? 0;
  const start = data.start as Date | undefined;
  const end = data.end as Date | undefined;
  let dates: string | null = null;
  if (duration >= 3 && start && end) {
    const e = new Date(end);
    e.setDate(e.getDate() - 1); // SVAR end is exclusive
    dates = `${format(start, "dd.MM")}–${format(e, "dd.MM")}`;
  }
  return (
    <span className="bar-label">
      <span className="bar-name">{data.text as string}</span>
      {dates && <span className="bar-dates">{dates}</span>}
    </span>
  );
}

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

    // Tight project window so a ~3-week plan fills the view without large empty
    // margins. Extra room on the right (SVAR draws each task's label to the
    // right of its bar) so the last task's name isn't clipped at the edge.
    let start: Date | undefined;
    let end: Date | undefined;
    if (tasks.length) {
      const minStart = Math.min(...tasks.map((t) => (t.start as Date).getTime()));
      const maxEnd = Math.max(...tasks.map((t) => (t.end as Date).getTime()));
      start = shiftDays(new Date(minStart), -1);
      end = shiftDays(new Date(maxEnd), 5);
    }
    return { tasks, links, start, end };
  }, [plan]);

  if (!plan) return <div className="gantt-empty">Загрузка плана…</div>;
  if (!plan.tasks.length) return <div className="gantt-empty">План пуст.</div>;

  // Size the board to its content so SVAR doesn't paint empty rows below the
  // tasks; `max-height: 100%` (in CSS) lets a large plan scroll instead.
  const contentHeight = SCALE_HEIGHT + tasks.length * CELL_HEIGHT + HSCROLL_SLACK;

  return (
    <div className="gantt-wrap" style={{ height: contentHeight }}>
      {/* readonly: edits go through the chat agent / Excel, not drag-and-drop. */}
      <WillowDark>
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
          taskTemplate={BarLabel as never}
          init={(api: IApi) => {
            apiRef.current = api;
            api.on("select-task", (ev: { id?: string | number }) => {
              if (ev?.id != null) selectTask(String(ev.id));
            });
          }}
        />
      </WillowDark>
    </div>
  );
}
