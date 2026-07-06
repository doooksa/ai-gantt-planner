import { useEffect } from "react";

import { ChatPanel } from "./components/ChatPanel";
import { GanttBoard } from "./components/GanttBoard";
import { TaskModal } from "./components/TaskModal";
import { Toolbar } from "./components/Toolbar";
import { usePlanStore } from "./store/plan";

export default function App() {
  const bootstrap = usePlanStore((s) => s.bootstrap);
  const connectWs = usePlanStore((s) => s.connectWs);
  const error = usePlanStore((s) => s.error);
  const setError = usePlanStore((s) => s.setError);
  const plan = usePlanStore((s) => s.plan);
  const waking = usePlanStore((s) => s.waking);

  useEffect(() => {
    void bootstrap();
    connectWs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Cold-start overlay: the backend (Render free tier) may be waking from idle.
  if (!plan && !error) {
    return (
      <div className="boot-screen">
        <div className="boot-spinner" />
        <p className="boot-title">
          {waking ? "Сервер просыпается…" : "Загрузка плана…"}
        </p>
        {waking && (
          <p className="boot-hint">
            Бесплатный инстанс засыпает при простое. Первый запуск занимает
            ~30&nbsp;секунд — подождите, страница откроется сама.
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="app">
      <Toolbar />
      {error && (
        <div className="error-bar" onClick={() => setError(null)}>
          {error} ✕
        </div>
      )}
      <div className="main">
        <section className="gantt-pane">
          <GanttBoard />
        </section>
        <aside className="chat-pane">
          <ChatPanel />
        </aside>
      </div>
      <TaskModal />
    </div>
  );
}
