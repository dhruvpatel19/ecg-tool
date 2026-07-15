from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.adaptive import next_case
from app.retention import (
    competency_state,
    due_snapshot,
    durable_retention,
    parse_instant,
    update_retention,
)
from app.storage import LearningStore


FROZEN = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)


def _event(case_id: str, *, correct: bool = True, assistance: str = "independent") -> dict:
    return {
        "eventKey": f"retention-{uuid4().hex}",
        "moduleId": "rapid",
        "sceneId": "untimed:full",
        "interactionId": f"recognize-{uuid4().hex}",
        "concept": "axis_normal",
        "subskills": ["recognize"],
        "score": 1.0 if correct else 0.0,
        "correct": correct,
        "attempts": 1,
        "assistance": assistance,
        "hintsUsed": 0 if assistance == "independent" else 1,
        "confidence": 3,
        "evidenceLevel": "independent_transfer",
        "caseId": case_id,
        "caseProvenance": "real_eligible",
        "caseEligible": True,
        "misconceptions": [],
        "_retentionVerified": True,
        "_retentionMorphologyKey": "NORM",
        "_serverVerifiedScoring": True,
    }


def _row(store: LearningStore, learner: str) -> dict:
    return next(
        row
        for row in store.get_profile(learner)["subskillMastery"]
        if row["concept"] == "axis_normal" and row["subskill"] == "recognize"
    )


def test_three_same_day_successes_are_not_durable_even_on_distinct_ecgs() -> None:
    store = LearningStore(":memory:")
    learner = "same-day"
    for case_id in ("101", "102", "103"):
        store.save_guided_learning_event(
            learner,
            _event(case_id),
            occurred_at=FROZEN,
        )

    row = _row(store, learner)
    assert row["distinctSuccessfulEcgs"] == 3
    assert row["spacedRetrievals"] == 0
    assert row["stabilityDays"] == 1.0
    # Even if an accuracy estimator were already high, spacing remains a hard gate.
    assert competency_state({**row, "independentMastery": 0.95}) == "consolidating"


def test_due_priority_orders_overdue_then_due_then_unseen_then_scheduled() -> None:
    rows = {
        "scheduled": {"independentAttempts": 1, "nextDueAt": (FROZEN + timedelta(days=2)).isoformat()},
        "unseen": {"independentAttempts": 0, "nextDueAt": None},
        "due": {"independentAttempts": 1, "nextDueAt": FROZEN.isoformat()},
        "overdue": {"independentAttempts": 1, "nextDueAt": (FROZEN - timedelta(days=3)).isoformat()},
    }
    ordered = sorted(
        rows,
        key=lambda key: due_snapshot(rows[key], as_of=FROZEN)["duePriority"],
    )
    assert ordered == ["overdue", "due", "unseen", "scheduled"]


def test_due_success_expands_interval_but_early_repetition_does_not() -> None:
    first = update_retention({}, correct=True, occurred_at=FROZEN)
    early = update_retention(
        {
            "stabilityDays": first.stability_days,
            "nextDueAt": first.next_due_at,
            "lapses": first.lapses,
            "spacedRetrievals": first.spaced_retrievals,
        },
        correct=True,
        occurred_at=FROZEN + timedelta(hours=2),
    )
    assert early.stability_days == first.stability_days == 1.0
    assert early.next_due_at == first.next_due_at
    assert early.interval_expanded is False

    due = parse_instant(first.next_due_at)
    assert due is not None
    retrieval = update_retention(
        {
            "stabilityDays": first.stability_days,
            "nextDueAt": first.next_due_at,
            "lapses": first.lapses,
            "spacedRetrievals": first.spaced_retrievals,
        },
        correct=True,
        occurred_at=due,
    )
    assert retrieval.interval_expanded is True
    assert retrieval.stability_days > first.stability_days
    assert retrieval.spaced_retrievals == 1


def test_independent_lapse_shrinks_stability_and_increments_lapses() -> None:
    result = update_retention(
        {
            "stabilityDays": 8.0,
            "nextDueAt": (FROZEN + timedelta(days=8)).isoformat(),
            "lapses": 1,
            "spacedRetrievals": 3,
        },
        correct=False,
        occurred_at=FROZEN,
    )
    assert result.stability_days == 2.8
    assert result.lapses == 2
    assert result.last_independent_correct is False


def test_formative_or_tutor_assisted_event_does_not_change_retention() -> None:
    store = LearningStore(":memory:")
    learner = "formative-excluded"
    store.save_guided_learning_event(learner, _event("201"), occurred_at=FROZEN)
    before = _row(store, learner)
    store.save_guided_learning_event(
        learner,
        _event("202", assistance="scaffolded"),
        occurred_at=FROZEN + timedelta(days=3),
    )
    after = _row(store, learner)

    for field in (
        "nextDueAt",
        "stabilityDays",
        "lapses",
        "spacedRetrievals",
        "distinctEligibleEcgs",
        "distinctSuccessfulEcgs",
        "lastIndependentAt",
        "lastIndependentCorrect",
    ):
        assert after[field] == before[field]
    assert after["attempts"] == before["attempts"] + 1


def test_distinct_successful_real_ecgs_are_a_hard_durable_gate() -> None:
    repeated_case = {
        "stabilityDays": 8.0,
        "spacedRetrievals": 3,
        "distinctEligibleEcgs": 1,
        "distinctSuccessfulEcgs": 1,
        "lastIndependentCorrect": True,
    }
    varied_cases = {
        **repeated_case,
        "distinctEligibleEcgs": 4,
        "distinctSuccessfulEcgs": 4,
    }
    assert durable_retention(repeated_case) is False
    assert durable_retention(varied_cases) is True


class _AdaptiveStore:
    def ensure_profile(self, learner_id: str) -> dict:
        return {
            "mastery": [
                {"objective": "normal_ecg", "mastery": 0.9, "attempts": 10, "highConfidenceWrong": 0},
                {"objective": "bradycardia", "mastery": 0.1, "attempts": 1, "highConfidenceWrong": 0},
            ],
            "subskillMastery": [
                {
                    "concept": "normal_ecg",
                    "subskill": "recognize",
                    "independentMastery": 0.9,
                    "independentAttempts": 5,
                    "nextDueAt": (FROZEN - timedelta(days=2)).isoformat(),
                    "lastPracticedAt": FROZEN.isoformat(),
                },
                {
                    "concept": "bradycardia",
                    "subskill": "recognize",
                    "independentMastery": 0.1,
                    "independentAttempts": 1,
                    "nextDueAt": (FROZEN + timedelta(days=2)).isoformat(),
                    "lastPracticedAt": FROZEN.isoformat(),
                },
            ],
        }

    def recent_case_ids(self, learner_id: str) -> list[str]:
        return []

    def protected_case_ids(self, learner_id: str, *, as_of=None) -> list[str]:
        return []

    def retention_case_ids(self, learner_id: str, concept: str, subskill: str) -> list[str]:
        return []


class _AdaptiveRepo:
    def __init__(self) -> None:
        self.packets = {
            "n": self._packet("n", "normal_ecg"),
            "b": self._packet("b", "bradycardia"),
        }

    @staticmethod
    def _packet(case_id: str, concept: str) -> dict:
        return {
            "case_id": case_id,
            "display_id": case_id,
            "source": "ptbxl",
            "teaching_tier": "A",
            "clinical_stem": "",
            "supported_objectives": [concept],
            "concept_confidence": {concept: {"tier": "A", "score": 1.0}},
            "ptbxl": {"report": ""},
            "signal_quality": {"status": "acceptable"},
            "waveform": {
                "sampling_frequency": 100,
                "duration_sec": 10.0,
                "leads": [
                    "I", "II", "III", "aVR", "aVL", "aVF",
                    "V1", "V2", "V3", "V4", "V5", "V6",
                ],
            },
        }

    def concept_ab_counts(self) -> dict[str, int]:
        return {"normal_ecg": 1, "bradycardia": 1}

    def candidates(self, concept_id: str | None = None) -> list[dict]:
        if concept_id == "normal_ecg":
            return [{"case_id": "n", "teaching_tier": "A", "source": "ptbxl", "supported_objectives": ["normal_ecg"], "concept_tier": "A"}]
        if concept_id == "bradycardia":
            return [{"case_id": "b", "teaching_tier": "A", "source": "ptbxl", "supported_objectives": ["bradycardia"], "concept_tier": "A"}]
        return []

    def get_case(self, case_id: str) -> dict | None:
        return self.packets.get(case_id)


def test_adaptive_scheduler_serves_due_retention_before_lower_not_due_mastery() -> None:
    selected = next_case(
        _AdaptiveRepo(),
        _AdaptiveStore(),  # type: ignore[arg-type]
        "learner",
        subskill_id="recognize",
        as_of=FROZEN,
    )
    assert selected["case"]["caseId"] == "n"
    assert selected["retention"]["dueState"] == "overdue"


def test_unscoped_adaptive_scheduler_prefers_exact_receipts_over_legacy_mastery() -> None:
    class ExactWinsStore(_AdaptiveStore):
        def ensure_profile(self, learner_id: str) -> dict:
            return {
                "mastery": [
                    {"objective": "normal_ecg", "mastery": 0.05, "attempts": 4, "highConfidenceWrong": 0},
                    {"objective": "bradycardia", "mastery": 0.95, "attempts": 4, "highConfidenceWrong": 0},
                ],
                "subskillMastery": [
                    {
                        "concept": "normal_ecg", "subskill": "recognize",
                        "independentMastery": 0.9, "independentAttempts": 4,
                        "nextDueAt": (FROZEN + timedelta(days=2)).isoformat(),
                        "lastPracticedAt": FROZEN.isoformat(),
                    },
                    {
                        "concept": "bradycardia", "subskill": "recognize",
                        "independentMastery": 0.2, "independentAttempts": 4,
                        "nextDueAt": (FROZEN + timedelta(days=2)).isoformat(),
                        "lastPracticedAt": FROZEN.isoformat(),
                    },
                ],
            }

    selected = next_case(
        _AdaptiveRepo(),
        ExactWinsStore(),  # type: ignore[arg-type]
        "learner",
        as_of=FROZEN,
    )
    assert selected["case"]["caseId"] == "b"
