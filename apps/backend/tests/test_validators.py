import pytest
from pydantic import ValidationError

from app.domain.models import Task
from app.domain.validators import (
    PlanValidationError,
    dependents_of,
    validate_structure,
)


def test_duration_below_one_rejected_by_model():
    # duration_days >= 1 is enforced at the model boundary (pydantic).
    with pytest.raises(ValidationError):
        Task(id="a", name="A", duration_days=0)


def test_negative_offset_rejected_by_model():
    with pytest.raises(ValidationError):
        Task(id="a", name="A", duration_days=1, offset_days=-1)


def test_validate_structure_passes_for_valid_plan():
    tasks = [
        Task(id="a", name="A", duration_days=1),
        Task(id="b", name="B", duration_days=1, predecessor_ids=["a"]),
    ]
    validate_structure(tasks)  # should not raise


def test_dependents_of():
    tasks = [
        Task(id="a", name="A", duration_days=1),
        Task(id="b", name="B", duration_days=1, predecessor_ids=["a"]),
        Task(id="c", name="C", duration_days=1, predecessor_ids=["a"]),
    ]
    deps = {t.id for t in dependents_of(tasks, "a")}
    assert deps == {"b", "c"}


def test_validate_structure_missing_predecessor():
    tasks = [Task(id="a", name="A", duration_days=1, predecessor_ids=["nope"])]
    with pytest.raises(PlanValidationError) as exc:
        validate_structure(tasks)
    assert exc.value.code == "missing_predecessor"
