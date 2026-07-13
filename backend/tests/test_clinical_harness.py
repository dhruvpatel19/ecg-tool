"""Phase-1 exit gate for the Clinical Decisions validation harness.

Every hand-authored seed item must PASS, and each of the review's three overclaims must
be REJECTED with the expected failing check. If this suite is red, nothing downstream
(grader, sessions, generator) should proceed.
"""

from __future__ import annotations

import pytest

from app.clinical.harness import run_harness
from app.clinical.seed_items import ADVERSARIAL, SEED_ITEMS, packet_for, prior_packet_for


@pytest.mark.parametrize("item", SEED_ITEMS, ids=lambda it: it.item_id)
def test_seed_items_pass_harness(item):
    report = run_harness(item, packet_for(item), prior_packet_for(item))
    assert report.passed, (
        f"{item.item_id} should pass but failed: "
        + "; ".join(f"{c.check}: {c.messages}" for c in report.hard_stop_failures)
    )


@pytest.mark.parametrize(
    "item, packet, prior, expected_check",
    ADVERSARIAL,
    ids=[a[0].item_id for a in ADVERSARIAL],
)
def test_adversarial_overclaims_rejected(item, packet, prior, expected_check):
    report = run_harness(item, packet, prior)
    assert not report.passed, f"{item.item_id} should have been rejected but passed."
    assert expected_check in report.failing_checks(), (
        f"{item.item_id} was rejected but not by {expected_check}; "
        f"failing checks were {report.failing_checks()}."
    )


def test_corrected_case_w_insufficient_data_bundle_is_high_credit():
    """The Case W 'get vitals + 12-lead WHILE readying pads' option must be tagged ideal,
    not insufficient_data — the round-2 correction (§16A1)."""
    case_w = next(it for it in SEED_ITEMS if it.item_id == "seed-W-chb")
    bundle = next(o for o in case_w.options if o.id == "w2")
    assert bundle.answer_class == "ideal"
    report = run_harness(case_w, packet_for(case_w), None)
    assert report.passed
    # And the parser recognizes it as a get-more-data + parallel-safety-action bundle.
    assert bundle.parsed is not None
    assert bundle.parsed.get_more_data and bundle.parsed.safety_action_present


def test_content_tables_import_and_cover_ontology():
    """Phase 0: the danger/acuity tables import cleanly and cover the ontology."""
    from app.clinical import content_tables  # import runs _validate_tables()
    from app.ontology import CONCEPT_BY_ID

    assert set(content_tables.ACUITY_BASE) == set(CONCEPT_BY_ID)
