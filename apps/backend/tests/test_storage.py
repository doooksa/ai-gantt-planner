import pytest

from app.domain.models import Op, Patch, Selector
from app.storage.db import Storage
from app.storage.snapshots import apply_and_commit, undo, validate_patch
from conftest import FIXED_START


@pytest.fixture
def storage():
    s = Storage(":memory:")
    s.ensure_seeded()
    yield s
    s.close()


def test_seed_loaded(storage):
    plan = storage.get_plan()
    assert len(plan.tasks) == 8
    assert plan.version == 0


def test_validate_patch_does_not_persist(storage):
    op = Op(type="update_task", selector=Selector(by_name="Design"), payload={"duration_days": 9})
    diff = validate_patch(storage, op_patch := Patch(ops=[op]), FIXED_START)
    assert diff.version_after == 1
    # But nothing was written.
    assert storage.get_plan().version == 0
    assert storage.get_plan().by_id("design").duration_days == 3


def test_apply_and_commit_then_undo(storage):
    op = Op(type="update_task", selector=Selector(by_name="Design"), payload={"duration_days": 9})
    apply_and_commit(storage, Patch(ops=[op]), FIXED_START)

    assert storage.get_plan().version == 1
    assert storage.get_plan().by_id("design").duration_days == 9

    # Undo restores previous plan.
    assert storage.can_undo()
    restored = undo(storage)
    assert restored.by_id("design").duration_days == 3
    assert storage.get_plan().version == 0


def test_undo_with_nothing_raises(storage):
    assert not storage.can_undo()
    with pytest.raises(LookupError):
        undo(storage)


def test_reset_to_seed_clears_snapshots(storage):
    op = Op(type="update_task", selector=Selector(by_name="Design"), payload={"duration_days": 9})
    apply_and_commit(storage, Patch(ops=[op]), FIXED_START)
    assert storage.can_undo()

    storage.reset_to_seed()
    assert not storage.can_undo()
    assert storage.get_plan().version == 0
