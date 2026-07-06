// Mirrors the backend ScheduledPlan / Diff JSON (app/domain/models.py).

export interface Task {
  id: string;
  name: string;
  description: string | null;
  assignee: string | null;
  duration_days: number;
  predecessor_ids: string[];
  offset_days: number;
  start: string; // ISO date "YYYY-MM-DD" (derived)
  end: string; // ISO date "YYYY-MM-DD" (derived, inclusive)
}

export interface Plan {
  version: number;
  project_start: string;
  tasks: Task[];
}

export type ChangeKind = "added" | "updated" | "removed";

export interface TaskDiff {
  id: string;
  change: ChangeKind;
  before: Task | null;
  after: Task | null;
}

export interface Diff {
  version_before: number;
  version_after: number;
  tasks: TaskDiff[];
  warnings: string[];
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

// SSE event shapes streamed by POST /api/chat.
export type ChatEvent =
  | { type: "tool"; name: string }
  | { type: "applied"; diff: Diff }
  | { type: "message"; text: string }
  | { type: "done"; text: string; applied: Diff[] }
  | { type: "error"; error: string };
