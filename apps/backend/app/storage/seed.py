"""Demo seed plan (matches examples/sample_plan.xlsx).

Ids are slugs of the task names so predecessors resolve cleanly.
"""

from __future__ import annotations

from ..domain.models import Plan, Task

# (id, name, description, assignee, duration, predecessor_ids)
_SEED_ROWS = [
    ("research", "Research", "Сбор требований", "Anna", 2, []),
    ("design", "Design", "Макеты и UX", "Anna", 3, ["research"]),
    ("backend-api", "Backend API", "FastAPI endpoints", "Ivan", 4, ["design"]),
    ("frontend", "Frontend", "React Gantt UI", "Maria", 4, ["design"]),
    ("ai-agent", "AI Agent", "MCP + LLM chat", "Ivan", 3, ["backend-api"]),
    ("excel-export", "Excel Export", "Экспорт плана", "Maria", 2, ["backend-api"]),
    ("testing", "Testing", "E2E сценарий", "Oleg", 2, ["frontend", "ai-agent", "excel-export"]),
    ("demo", "Demo", "Запись gif", "Oleg", 1, ["testing"]),
]


def seed_plan() -> Plan:
    tasks = [
        Task(
            id=tid,
            name=name,
            description=desc,
            assignee=assignee,
            duration_days=duration,
            predecessor_ids=list(preds),
        )
        for tid, name, desc, assignee, duration, preds in _SEED_ROWS
    ]
    return Plan(version=0, tasks=tasks)
