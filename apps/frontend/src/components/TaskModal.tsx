import { usePlanStore } from "../store/plan";

// Read-only detail view (drag/field editing is out of scope by spec). Shows all
// fields + predecessors + dependent tasks.
export function TaskModal() {
  const plan = usePlanStore((s) => s.plan);
  const id = usePlanStore((s) => s.selectedTaskId);
  const select = usePlanStore((s) => s.selectTask);

  if (!plan || !id) return null;
  const task = plan.tasks.find((t) => t.id === id);
  if (!task) return null;

  const nameOf = (tid: string) => plan.tasks.find((t) => t.id === tid)?.name ?? tid;
  const predecessors = task.predecessor_ids.map(nameOf);
  const dependents = plan.tasks
    .filter((t) => t.predecessor_ids.includes(task.id))
    .map((t) => t.name);

  return (
    <div className="modal-backdrop" onClick={() => select(null)}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>{task.name}</h2>
          <button className="icon-btn" onClick={() => select(null)} aria-label="Закрыть">
            ×
          </button>
        </div>
        <dl className="modal-fields">
          <dt>Исполнитель</dt>
          <dd>{task.assignee ?? "—"}</dd>
          <dt>Длительность</dt>
          <dd>{task.duration_days} дн.</dd>
          <dt>Начало</dt>
          <dd>{task.start}</dd>
          <dt>Конец</dt>
          <dd>{task.end}</dd>
          {task.offset_days > 0 && (
            <>
              <dt>Сдвиг</dt>
              <dd>+{task.offset_days} дн.</dd>
            </>
          )}
          <dt>Описание</dt>
          <dd>{task.description ?? "—"}</dd>
          <dt>Предшественники</dt>
          <dd>{predecessors.length ? predecessors.join(", ") : "—"}</dd>
          <dt>Зависимые задачи</dt>
          <dd>{dependents.length ? dependents.join(", ") : "—"}</dd>
        </dl>
      </div>
    </div>
  );
}
