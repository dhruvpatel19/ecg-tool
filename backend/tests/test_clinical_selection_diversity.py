from __future__ import annotations

from typing import Any

from app.clinical import shift
from app.clinical.real_items import (
    REAL_AF_WARD_STEPWISE,
    REAL_FIRST_DEGREE_CLICK,
    REAL_LVH_WARD_MCQ,
    REAL_QTC_MCQ,
    REAL_RBBB_WARD_SPOTERROR,
    REAL_SLOW_AF_WARD_MCQ,
)
from app.clinical.schemas import ClinicalCaseItem


class _Store:
    def ensure_profile(self, learner_id: str) -> dict[str, Any]:
        return {"subskillMastery": []}

    def recent_case_ids(self, learner_id: str) -> list[str]:
        return []


class _ItemStore:
    def __init__(self, items: list[ClinicalCaseItem]) -> None:
        self.items = items

    def list_for_serving(
        self,
        *,
        situation: str | None = None,
        status: str = "harness_pass",
    ) -> list[ClinicalCaseItem]:
        return [
            item
            for item in self.items
            if situation is None or item.situation == situation
        ]


def _allow_candidates(monkeypatch, scores: dict[str, float]) -> None:
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
    monkeypatch.setattr(
        shift,
        "_score_item",
        lambda item, *args, **kwargs: scores[item.item_id],
    )


def test_close_alternative_avoids_consecutive_same_interaction_type(
    monkeypatch,
) -> None:
    previous = REAL_LVH_WARD_MCQ
    repeated_type = REAL_SLOW_AF_WARD_MCQ
    varied_type = REAL_RBBB_WARD_SPOTERROR
    _allow_candidates(
        monkeypatch,
        {
            repeated_type.item_id: 1.0,
            varied_type.item_id: 0.96,
        },
    )

    selected = shift._select_next(
        _Store(),
        _ItemStore([previous, repeated_type, varied_type]),
        lambda ecg_id: None,
        "ward",
        [previous.item_id],
        {previous.ecg_id},
        "learner",
    )

    assert selected is not None
    assert selected.item_id == varied_type.item_id
    assert selected.question_type != previous.question_type


def test_first_item_focus_and_subskill_fidelity_precede_diversity(
    monkeypatch,
) -> None:
    focused = REAL_FIRST_DEGREE_CLICK
    unrelated = REAL_QTC_MCQ
    _allow_candidates(
        monkeypatch,
        {
            focused.item_id: 0.0,
            unrelated.item_id: 50.0,
        },
    )

    selected = shift._select_next(
        _Store(),
        _ItemStore([unrelated, focused]),
        lambda ecg_id: None,
        "clinic",
        [],
        set(),
        "learner",
        focus_objective="av_block_first_degree",
        focus_subskill="localize",
    )

    assert selected is not None
    assert selected.item_id == focused.item_id
    assert selected.roi_target is not None
    assert selected.roi_target.concept == "av_block_first_degree"


def test_materially_higher_personalized_need_still_wins(monkeypatch) -> None:
    previous = REAL_LVH_WARD_MCQ
    stronger_same_type = REAL_SLOW_AF_WARD_MCQ
    varied_but_lower_need = REAL_RBBB_WARD_SPOTERROR
    _allow_candidates(
        monkeypatch,
        {
            stronger_same_type.item_id: 1.0,
            varied_but_lower_need.item_id: 0.7,
        },
    )

    selected = shift._select_next(
        _Store(),
        _ItemStore([previous, stronger_same_type, varied_but_lower_need]),
        lambda ecg_id: None,
        "ward",
        [previous.item_id],
        {previous.ecg_id},
        "learner",
    )

    assert selected is not None
    assert selected.item_id == stronger_same_type.item_id


def test_bloom_demand_is_structural_and_underrepresented_band_gets_small_bonus() -> None:
    assert shift._bloom_demand(REAL_FIRST_DEGREE_CLICK) == "apply"
    assert shift._bloom_demand(REAL_RBBB_WARD_SPOTERROR) == "analyze"
    assert shift._bloom_demand(REAL_AF_WARD_STEPWISE) == "evaluate"

    apply_history = [REAL_LVH_WARD_MCQ, REAL_FIRST_DEGREE_CLICK]
    apply_bonus = shift._selection_diversity_bonus(
        REAL_SLOW_AF_WARD_MCQ,
        apply_history,
    )
    analyze_bonus = shift._selection_diversity_bonus(
        REAL_RBBB_WARD_SPOTERROR,
        apply_history,
    )

    assert analyze_bonus > apply_bonus
    assert 0.0 <= analyze_bonus <= 0.11
