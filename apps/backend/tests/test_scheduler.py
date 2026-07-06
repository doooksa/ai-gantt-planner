from datetime import date, timedelta

import pytest

from app.domain.models import Task
from app.domain.scheduler import schedule
from app.domain.validators import PlanValidationError


def _by_id(scheduled):
    return {t.id: t for t in scheduled}


def test_linear_chain(start):
    tasks = [
        Task(id="a", name="A", duration_days=2),
        Task(id="b", name="B", duration_days=3, predecessor_ids=["a"]),
        Task(id="c", name="C", duration_days=1, predecessor_ids=["b"]),
    ]
    s = _by_id(schedule(tasks, start))

    assert (s["a"].start, s["a"].end) == (date(2026, 1, 1), date(2026, 1, 2))
    # B starts the day after A ends.
    assert (s["b"].start, s["b"].end) == (date(2026, 1, 3), date(2026, 1, 5))
    assert (s["c"].start, s["c"].end) == (date(2026, 1, 6), date(2026, 1, 6))


def test_diamond(start):
    # A -> B, A -> C, {B,C} -> D. D must wait for the LATER of B/C.
    tasks = [
        Task(id="a", name="A", duration_days=2),
        Task(id="b", name="B", duration_days=3, predecessor_ids=["a"]),
        Task(id="c", name="C", duration_days=1, predecessor_ids=["a"]),
        Task(id="d", name="D", duration_days=2, predecessor_ids=["b", "c"]),
    ]
    s = _by_id(schedule(tasks, start))

    assert s["b"].end == date(2026, 1, 5)   # longer branch
    assert s["c"].end == date(2026, 1, 3)   # shorter branch
    # D starts the day after the LATER predecessor (B).
    assert s["d"].start == date(2026, 1, 6)
    assert s["d"].end == date(2026, 1, 7)


def test_roots_share_project_start(start):
    tasks = [
        Task(id="a", name="A", duration_days=1),
        Task(id="b", name="B", duration_days=1),
    ]
    s = _by_id(schedule(tasks, start))
    assert s["a"].start == start
    assert s["b"].start == start


def test_default_project_start_is_today():
    tasks = [Task(id="a", name="A", duration_days=1)]
    s = schedule(tasks)  # no project_start -> today
    assert s[0].start == date.today()


def test_offset_days_shifts_start(start):
    tasks = [
        Task(id="a", name="A", duration_days=2),
        Task(id="b", name="B", duration_days=2, predecessor_ids=["a"], offset_days=3),
    ]
    s = _by_id(schedule(tasks, start))
    base_start = s["a"].end + timedelta(days=1)          # 2026-01-03
    assert s["b"].start == base_start + timedelta(days=3)  # 2026-01-06


def test_output_preserves_input_order(start):
    tasks = [
        Task(id="c", name="C", duration_days=1, predecessor_ids=["b"]),
        Task(id="a", name="A", duration_days=1),
        Task(id="b", name="B", duration_days=1, predecessor_ids=["a"]),
    ]
    result = schedule(tasks, start)
    assert [t.id for t in result] == ["c", "a", "b"]


def test_cycle_is_rejected_with_names(start):
    tasks = [
        Task(id="design", name="Design", duration_days=1, predecessor_ids=["frontend"]),
        Task(id="frontend", name="Frontend", duration_days=1, predecessor_ids=["design"]),
    ]
    with pytest.raises(PlanValidationError) as exc:
        schedule(tasks, start)
    assert exc.value.code == "cycle"
    # Message names the tasks in the cycle.
    assert "Design" in exc.value.message and "Frontend" in exc.value.message


def test_missing_predecessor(start):
    tasks = [Task(id="b", name="B", duration_days=1, predecessor_ids=["ghost"])]
    with pytest.raises(PlanValidationError) as exc:
        schedule(tasks, start)
    assert exc.value.code == "missing_predecessor"


def test_self_dependency(start):
    tasks = [Task(id="a", name="A", duration_days=1, predecessor_ids=["a"])]
    with pytest.raises(PlanValidationError) as exc:
        schedule(tasks, start)
    assert exc.value.code == "self_dependency"


def test_duplicate_id(start):
    tasks = [
        Task(id="a", name="A", duration_days=1),
        Task(id="a", name="A2", duration_days=1),
    ]
    with pytest.raises(PlanValidationError) as exc:
        schedule(tasks, start)
    assert exc.value.code == "duplicate_id"
