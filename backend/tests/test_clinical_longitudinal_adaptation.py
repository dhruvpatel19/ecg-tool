from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.adaptive import formative_application_index, independent_subskill_index
from app.clinical import shift
from app.clinical.real_items import (
    REAL_AF_WARD_STEPWISE,
    REAL_CHB_STEPWISE,
    REAL_SLOW_AF_WARD_MCQ,
)
from app.clinical.schemas import ClinicalCaseItem


class _ProfileStore:
    def __init__(self, profile: dict[str, Any]) -> None:
        self.profile = profile

    def ensure_profile(self, learner_id: str) -> dict[str, Any]:
        return self.profile

    def recent_case_ids(self, learner_id: str) -> list[str]:
        return []


class _ItemStore:
    def __init__(self, items: list[ClinicalCaseItem]) -> None:
        self.items = items

    def list_for_serving(self, **_: Any) -> list[ClinicalCaseItem]:
        return list(self.items)


def _application_items() -> tuple[ClinicalCaseItem, ClinicalCaseItem]:
    af = REAL_AF_WARD_STEPWISE.model_copy(
        deep=True,
        update={"application_objectives": ["atrial_fibrillation"]},
    )
    chb = REAL_CHB_STEPWISE.model_copy(
        deep=True,
        update={"application_objectives": ["av_block_third_degree"]},
    )
    return af, chb


def _independent_recognition_row(concept: str, practiced_at: str) -> dict[str, Any]:
    return {
        "concept": concept,
        "subskill": "recognize",
        "formativeScore": 0.7,
        "attempts": 6,
        "independentAttempts": 6,
        "independentMastery": 0.7,
        "correct": 4,
        "highConfidenceWrong": 0,
        "lastPracticedAt": practiced_at,
        "nextDueAt": (datetime.now(UTC) + timedelta(days=7)).isoformat(),
        "isDue": False,
        "overdueDays": 0.0,
        "lapses": 0,
    }


def _application_row(
    concept: str,
    *,
    score: float,
    high_confidence_wrong: int,
    practiced_at: str,
) -> dict[str, Any]:
    return {
        "concept": concept,
        "subskill": "apply_in_context",
        "formativeScore": score,
        "attempts": 12,
        "independentAttempts": 0,
        # This sentinel must never enter the formative application projection.
        "independentMastery": 0.99,
        "correct": 11 if score >= 0.8 else 1,
        "highConfidenceWrong": high_confidence_wrong,
        "lastPracticedAt": practiced_at,
    }


def _recognition_rows(items: list[ClinicalCaseItem]) -> list[dict[str, Any]]:
    practiced_at = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    concepts = {
        objective
        for item in items
        for objective in shift._item_targets(item)
    }
    return [
        _independent_recognition_row(concept, practiced_at)
        for concept in sorted(concepts)
    ]


def _allow_test_candidates(monkeypatch) -> None:
    monkeypatch.setattr(
        shift.integrity,
        "live_owner_exposures",
        lambda store, learner_id: set(),
    )
    monkeypatch.setattr(
        shift,
        "_runtime_provenance_ok",
        lambda item, packet_provider: True,
    )


def test_formative_application_index_is_exact_and_cannot_change_independent_mastery() -> None:
    now = datetime.now(UTC).isoformat()
    application = _application_row(
        "atrial_fibrillation",
        score=0.72,
        high_confidence_wrong=2,
        practiced_at=now,
    )
    profile = {
        "subskillMastery": [
            application,
            _independent_recognition_row("atrial_fibrillation", now),
            {
                "concept": "bradycardia",
                "subskill": "apply_in_context",
                "attempts": 0,
                "formativeScore": 0.0,
            },
        ]
    }

    application_index = formative_application_index(profile)

    assert set(application_index) == {"atrial_fibrillation"}
    assert application_index["atrial_fibrillation"] == {
        "concept": "atrial_fibrillation",
        "subskill": "apply_in_context",
        "formativeScore": 0.72,
        "attempts": 12,
        "correct": 1,
        "highConfidenceWrong": 2,
        "lastPracticedAt": now,
    }
    assert "independentMastery" not in application_index["atrial_fibrillation"]
    independent = independent_subskill_index(profile)
    assert [row["subskill"] for row in independent["atrial_fibrillation"]] == [
        "recognize"
    ]


def test_application_priority_uses_errors_recency_and_unseen_case_capacity() -> None:
    now = datetime.now(UTC)
    recent = _application_row(
        "atrial_fibrillation",
        score=0.6,
        high_confidence_wrong=0,
        practiced_at=(now - timedelta(hours=1)).isoformat(),
    )
    stale = {**recent, "lastPracticedAt": (now - timedelta(days=60)).isoformat()}
    confident_error = {**recent, "highConfidenceWrong": 3}

    recent_priority = shift._formative_application_priority(
        recent, unseen_case_count=1
    )
    assert shift._formative_application_priority(
        stale, unseen_case_count=1
    ) > recent_priority
    assert shift._formative_application_priority(
        confident_error, unseen_case_count=1
    ) > recent_priority
    assert shift._formative_application_priority(recent, unseen_case_count=0) == 0.0
    assert shift._formative_application_priority(
        recent, unseen_case_count=4
    ) > recent_priority


def test_opposite_longitudinal_application_outcomes_change_next_clinical_case(
    monkeypatch,
) -> None:
    _allow_test_candidates(monkeypatch)
    af, chb = _application_items()
    items = [af, chb]
    independent_rows = _recognition_rows(items)
    now = datetime.now(UTC)
    old = (now - timedelta(days=45)).isoformat()
    recent = (now - timedelta(hours=2)).isoformat()

    af_struggle_profile = {
        "subskillMastery": independent_rows
        + [
            _application_row(
                "atrial_fibrillation",
                score=0.08,
                high_confidence_wrong=4,
                practiced_at=old,
            ),
            _application_row(
                "av_block_third_degree",
                score=0.96,
                high_confidence_wrong=0,
                practiced_at=recent,
            ),
        ]
    }
    chb_struggle_profile = {
        "subskillMastery": independent_rows
        + [
            _application_row(
                "atrial_fibrillation",
                score=0.96,
                high_confidence_wrong=0,
                practiced_at=recent,
            ),
            _application_row(
                "av_block_third_degree",
                score=0.08,
                high_confidence_wrong=4,
                practiced_at=old,
            ),
        ]
    }

    # Their defensible ECG-recognition evidence is byte-for-byte equivalent;
    # only their formative longitudinal application histories differ.
    assert independent_subskill_index(
        af_struggle_profile
    ) == independent_subskill_index(chb_struggle_profile)

    af_next = shift._select_next(
        _ProfileStore(af_struggle_profile),
        _ItemStore(items),
        lambda ecg_id: None,
        "ward",
        [],
        set(),
        "learner-af",
    )
    chb_next = shift._select_next(
        _ProfileStore(chb_struggle_profile),
        _ItemStore(items),
        lambda ecg_id: None,
        "ward",
        [],
        set(),
        "learner-chb",
    )

    assert af_next is not None
    assert af_next.application_objectives == ["atrial_fibrillation"]
    assert chb_next is not None
    assert chb_next.application_objectives == ["av_block_third_degree"]


def test_exhausted_application_cases_do_not_turn_trace_tasks_into_proxies(
    monkeypatch,
) -> None:
    _allow_test_candidates(monkeypatch)
    af_application, chb_application = _application_items()
    # This is a distinct real AF tracing, but its authored task is used here as
    # a trace-only control.  It must not inherit AF application priority.
    af_trace_only = REAL_SLOW_AF_WARD_MCQ.model_copy(
        deep=True,
        update={"application_objectives": []},
    )
    items = [af_application, af_trace_only, chb_application]
    profile = {
        "subskillMastery": _recognition_rows(items)
        + [
            _application_row(
                "atrial_fibrillation",
                score=0.04,
                high_confidence_wrong=5,
                practiced_at=(datetime.now(UTC) - timedelta(days=30)).isoformat(),
            )
        ]
    }
    store = _ProfileStore(profile)
    item_store = _ItemStore(items)

    first = shift._select_next(
        store,
        item_store,
        lambda ecg_id: None,
        "ward",
        [],
        set(),
        "learner",
    )
    assert first is not None
    assert first.item_id == af_application.item_id

    after_af_application_is_used = shift._select_next(
        store,
        item_store,
        lambda ecg_id: None,
        "ward",
        [af_application.item_id],
        {af_application.ecg_id},
        "learner",
    )
    assert after_af_application_is_used is not None
    assert after_af_application_is_used.item_id == chb_application.item_id
    assert af_trace_only.item_id != after_af_application_is_used.item_id
