import pytest

from app.domain.models import Op, Patch, Selector
from app.domain.patches import apply_patch
from app.domain.scheduler import schedule
from app.domain.validators import PlanValidationError
from app.storage.seed import seed_plan


def _apply(plan, ops, start):
    return apply_patch(plan, Patch(ops=ops), start)


def test_add_task_with_predecessor_by_name(start):
    plan = seed_plan()
    op = Op(
        type="add_task",
        payload={
            "name": "Security review",
            "assignee": "Anna",
            "duration_days": 2,
            "predecessors": ["Backend API"],
        },
    )
    new_plan, diff = _apply(plan, [op], start)

    added = new_plan.by_id("security-review")
    assert added is not None
    assert added.predecessor_ids == ["backend-api"]
    assert new_plan.version == plan.version + 1
    assert any(d.change == "added" and d.id == "security-review" for d in diff.tasks)


def test_mass_reassign_by_assignee_single_op(start):
    plan = seed_plan()
    op = Op(
        type="reassign",
        selector=Selector(by_assignee="Ivan"),
        payload={"assignee": "Maria"},
    )
    new_plan, diff = _apply(plan, [op], start)

    ivan_tasks = [t for t in new_plan.tasks if t.assignee == "Ivan"]
    assert ivan_tasks == []
    # Backend API + AI Agent were Ivan's.
    assert new_plan.by_id("backend-api").assignee == "Maria"
    assert new_plan.by_id("ai-agent").assignee == "Maria"


def test_delete_task_warns_and_strips_references(start):
    plan = seed_plan()
    op = Op(type="delete_task", selector=Selector(by_name="Testing"))
    new_plan, diff = _apply(plan, [op], start)

    assert new_plan.by_id("testing") is None
    # Demo depended on Testing -> reference stripped, plan still valid.
    assert "testing" not in new_plan.by_id("demo").predecessor_ids
    assert diff.warnings  # warned about the dependent
    assert any("Demo" in w for w in diff.warnings)


def test_shift_task_pushes_start_later(start):
    plan = seed_plan()
    before = {t.id: t for t in schedule(plan.tasks, start)}
    op = Op(type="shift_task", selector=Selector(by_name="Frontend"), payload={"days": 3})
    new_plan, diff = _apply(plan, [op], start)

    after = {t.id: t for t in schedule(new_plan.tasks, start)}
    delta = (after["frontend"].start - before["frontend"].start).days
    assert delta == 3


def test_shift_earlier_unwinds_previous_forward_shift(start):
    plan = seed_plan()
    # Push Frontend +5, then pull it -3 -> net offset 2.
    plan, _ = _apply(plan, [Op(type="shift_task", selector=Selector(by_name="Frontend"), payload={"days": 5})], start)
    assert plan.by_id("frontend").offset_days == 5

    before = {t.id: t for t in schedule(plan.tasks, start)}
    plan, _ = _apply(plan, [Op(type="shift_task", selector=Selector(by_name="Frontend"), payload={"days": -3})], start)
    assert plan.by_id("frontend").offset_days == 2

    after = {t.id: t for t in schedule(plan.tasks, start)}
    assert (after["frontend"].start - before["frontend"].start).days == -3


def test_shift_earlier_below_zero_is_refused(start):
    plan = seed_plan()
    op = Op(type="shift_task", selector=Selector(by_name="Frontend"), payload={"days": -3})
    with pytest.raises(PlanValidationError) as exc:
        _apply(plan, [op], start)
    assert exc.value.code == "shift_before_earliest"
    assert "Frontend" in exc.value.message
    # Atomic: original plan untouched.
    assert plan.by_id("frontend").offset_days == 0


def test_shift_earlier_partially_out_of_range_is_refused(start):
    plan = seed_plan()
    plan, _ = _apply(plan, [Op(type="shift_task", selector=Selector(by_name="Frontend"), payload={"days": 2})], start)
    # offset is 2; asking for -3 would go to -1 -> refuse (no silent clamp).
    op = Op(type="shift_task", selector=Selector(by_name="Frontend"), payload={"days": -3})
    with pytest.raises(PlanValidationError) as exc:
        _apply(plan, [op], start)
    assert exc.value.code == "shift_before_earliest"
    assert plan.by_id("frontend").offset_days == 2  # unchanged


def test_set_dependencies_replaces(start):
    plan = seed_plan()
    op = Op(
        type="set_dependencies",
        selector=Selector(by_name="Demo"),
        payload={"predecessors": ["Testing", "Excel Export"]},
    )
    new_plan, _ = _apply(plan, [op], start)
    demo = new_plan.by_id("demo")
    assert set(demo.predecessor_ids) == {"testing", "excel-export"}


def test_remove_dependency_via_set_dependencies(start):
    plan = seed_plan()
    op = Op(
        type="set_dependencies",
        selector=Selector(by_name="Frontend"),
        payload={"predecessors": []},
    )
    new_plan, _ = _apply(plan, [op], start)
    assert new_plan.by_id("frontend").predecessor_ids == []


def test_update_duration(start):
    plan = seed_plan()
    op = Op(
        type="update_task",
        selector=Selector(by_name="Design"),
        payload={"duration_days": 5},
    )
    new_plan, _ = _apply(plan, [op], start)
    assert new_plan.by_id("design").duration_days == 5


def test_atomic_rollback_on_invalid_op(start):
    plan = seed_plan()
    original_ids = [t.id for t in plan.tasks]
    # Creating a cycle: make Design depend on Demo (Demo already depends on Design chain).
    ops = [
        Op(type="update_task", selector=Selector(by_name="Backend API"), payload={"assignee": "Zoe"}),
        Op(type="set_dependencies", selector=Selector(by_name="Design"), payload={"predecessors": ["Demo"]}),
    ]
    with pytest.raises(PlanValidationError) as exc:
        _apply(plan, ops, start)
    assert exc.value.code == "cycle"
    # Input plan untouched (atomicity): version + first op's change not persisted.
    assert plan.version == 0
    assert [t.id for t in plan.tasks] == original_ids
    assert plan.by_id("backend-api").assignee == "Ivan"


def test_selector_no_match_errors(start):
    plan = seed_plan()
    op = Op(type="update_task", selector=Selector(by_name="Ghost"), payload={"duration_days": 2})
    with pytest.raises(PlanValidationError) as exc:
        _apply(plan, [op], start)
    assert exc.value.code == "selector_no_match"
