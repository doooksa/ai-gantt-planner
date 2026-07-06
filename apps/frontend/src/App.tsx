import { useEffect } from "react";

import { ChatPanel } from "./components/ChatPanel";
import { GanttBoard } from "./components/GanttBoard";
import { TaskModal } from "./components/TaskModal";
import { Toolbar } from "./components/Toolbar";
import { usePlanStore } from "./store/plan";

export default function App() {
  const refresh = usePlanStore((s) => s.refresh);
  const connectWs = usePlanStore((s) => s.connectWs);
  const error = usePlanStore((s) => s.error);
  const setError = usePlanStore((s) => s.setError);

  useEffect(() => {
    void refresh();
    connectWs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
