"""Single-plan SQLite storage with an undo snapshot stack.

"Simpler is better" (per spec): the whole plan is stored as one JSON document
in a singleton row, and every mutation pushes the *previous* plan onto a
snapshots stack so `undo_last` can pop it. No ORM — plain sqlite3.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from ..domain.models import Plan
from .seed import seed_plan

_SINGLETON_ID = 1


class Storage:
    def __init__(self, path: str | Path = "gantt.db") -> None:
        # ":memory:" is supported for tests.
        self._path = str(path)
        self._conn = sqlite3.connect(self._path)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS plan (
                id      INTEGER PRIMARY KEY CHECK (id = 1),
                version INTEGER NOT NULL,
                data    TEXT    NOT NULL
            );
            CREATE TABLE IF NOT EXISTS snapshots (
                seq     INTEGER PRIMARY KEY AUTOINCREMENT,
                version INTEGER NOT NULL,
                data    TEXT    NOT NULL
            );
            """
        )
        self._conn.commit()

    # --- plan ------------------------------------------------------------

    def has_plan(self) -> bool:
        cur = self._conn.execute("SELECT 1 FROM plan WHERE id = ?", (_SINGLETON_ID,))
        return cur.fetchone() is not None

    def get_plan(self) -> Plan:
        cur = self._conn.execute(
            "SELECT data FROM plan WHERE id = ?", (_SINGLETON_ID,)
        )
        row = cur.fetchone()
        if row is None:
            raise LookupError("No plan stored. Call reset_to_seed() first.")
        return Plan.model_validate_json(row[0])

    def save_plan(self, plan: Plan) -> None:
        """Overwrite the current plan WITHOUT pushing a snapshot."""
        self._conn.execute(
            "INSERT INTO plan (id, version, data) VALUES (?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET version = excluded.version, "
            "data = excluded.data",
            (_SINGLETON_ID, plan.version, plan.model_dump_json()),
        )
        self._conn.commit()

    def commit_plan(self, new_plan: Plan) -> None:
        """Push the current plan onto the undo stack, then store `new_plan`."""
        if self.has_plan():
            current = self.get_plan()
            self._push_snapshot(current)
        self.save_plan(new_plan)

    # --- undo stack ------------------------------------------------------

    def _push_snapshot(self, plan: Plan) -> None:
        self._conn.execute(
            "INSERT INTO snapshots (version, data) VALUES (?, ?)",
            (plan.version, plan.model_dump_json()),
        )
        self._conn.commit()

    def can_undo(self) -> bool:
        cur = self._conn.execute("SELECT 1 FROM snapshots ORDER BY seq DESC LIMIT 1")
        return cur.fetchone() is not None

    def undo_last(self) -> Plan:
        """Pop the most recent snapshot and make it the current plan."""
        cur = self._conn.execute(
            "SELECT seq, data FROM snapshots ORDER BY seq DESC LIMIT 1"
        )
        row = cur.fetchone()
        if row is None:
            raise LookupError("Nothing to undo.")
        seq, data = row
        self._conn.execute("DELETE FROM snapshots WHERE seq = ?", (seq,))
        restored = Plan.model_validate_json(data)
        self.save_plan(restored)
        return restored

    # --- lifecycle -------------------------------------------------------

    def reset_to_seed(self) -> Plan:
        """Clear snapshots and restore the demo seed plan."""
        self._conn.execute("DELETE FROM snapshots")
        plan = seed_plan()
        self.save_plan(plan)
        return plan

    def ensure_seeded(self) -> Plan:
        """Seed on first run; return the current plan otherwise."""
        if not self.has_plan():
            return self.reset_to_seed()
        return self.get_plan()

    def close(self) -> None:
        self._conn.close()
