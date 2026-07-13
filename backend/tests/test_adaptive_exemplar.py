from __future__ import annotations

from app.adaptive import _teaching_exemplar_rejection_reasons
from app.store.case_store import CaseStore


def test_rbbb_teaching_exemplar_rejects_conflicted_unconfirmed_borderline_case() -> None:
    case = {
        "signal_quality": {"status": "borderline"},
        "ptbxl": {"report": "Sinusrhythmus Linksschenkelblock unbestÃ„tigter Bericht"},
        "concept_confidence": {
            "right_bundle_branch_block": {
                "tier": "B",
                "warnings": ["Morphology support is limited; avoid over-specific lead claims."],
            }
        },
    }

    reasons = _teaching_exemplar_rejection_reasons(case, "right_bundle_branch_block")

    assert any("signal quality" in reason for reason in reasons)
    assert any("unconfirmed" in reason for reason in reasons)
    assert any("conflicts" in reason for reason in reasons)
    assert any("morphology" in reason for reason in reasons)


def test_acceptable_source_aligned_rbbb_case_can_anchor_teaching() -> None:
    case = {
        "signal_quality": {"status": "acceptable"},
        "ptbxl": {"report": "Sinusrhythmus Rechtsschenkelblock"},
        "concept_confidence": {
            "right_bundle_branch_block": {"tier": "A", "warnings": []}
        },
    }

    assert _teaching_exemplar_rejection_reasons(case, "right_bundle_branch_block") == []


def test_runtime_candidate_index_quarantines_opposite_bundle_report(tmp_path) -> None:
    store = CaseStore(tmp_path / "corpus.db")

    def packet(case_id: str, report: str) -> dict:
        return {
            "case_id": case_id,
            "source": "ptbxl",
            "teaching_tier": "B",
            "ptbxl": {"report": report},
            "signal_quality": {"status": "acceptable"},
            "supported_objectives": ["right_bundle_branch_block"],
            "concept_confidence": {
                "right_bundle_branch_block": {"tier": "B", "score": 0.76}
            },
        }

    store.upsert_case(packet("1", "Linksschenkelblock"))
    store.upsert_case(packet("2", "Rechtsschenkelblock"))

    assert [row["case_id"] for row in store.candidates("right_bundle_branch_block")] == ["2"]
    assert [row["caseId"] for row in store.summaries("right_bundle_branch_block")] == ["2"]
