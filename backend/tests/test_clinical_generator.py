"""Phase 4 — the nano generation pipeline is correctly GATED by the harness.

Uses a fake provider returning canned drafts (no live model), so it tests the wiring:
a conforming, grounded draft is accepted; an overclaiming draft is rejected by the
harness; an unparseable draft is rejected at parse time.
"""

from __future__ import annotations

import json

from app.clinical.fixture_items import FIXTURE_PACKETS
from app.clinical.generator import build_generation_context, generate_and_vet, measure_convergence


class FakeProvider:
    def __init__(self, payload):
        self.payload = payload

    def generate(self, messages, context):
        return self.payload if isinstance(self.payload, str) else json.dumps(self.payload)


AF_PACKET = FIXTURE_PACKETS["fixture-af-001"]

GOOD_DRAFT = {
    "acuity_tier": "moderate",
    "stem": "Irregularly irregular pulse, rate ~118. Stable, BP 122/76.",
    "chips": {"age": 70, "setting": "ed", "symptom": "palpitations", "bp": "122/76"},
    "prompt": "First step?",
    "options": [
        {"text": "Rate control and assess anticoagulation.", "answer_class": "ideal",
         "required_safety_tokens": ["rate_control", "anticoagulation_assessment"]},
        {"text": "Immediate cardioversion.", "answer_class": "over_triage_safe"},
        {"text": "Reassure and discharge untreated.", "answer_class": "under_triage"},
    ],
    "evidence_manifest": {
        "ecg_supports": [
            {"objective_id": "atrial_fibrillation", "source_type": "curated_label"},
            {"objective_id": "rate", "threshold": "heart_rate>=100", "source_type": "measured"},
        ],
        "stem_adds": ["age 70"], "action_rationale": "Stable AF RVR → rate control + anticoagulation assessment.",
        "forbidden_claims": ["unstable"], "acceptable_range": ["rate control"], "epistemic_status": "determined",
    },
    "tested_scope": "full_12_lead",
    "display_spec": {"mode": "twelve_lead", "tested_scope": "full_12_lead"},
}

# Overclaims an acute STEMI the AF packet does not support — IN THE PROSE (the manifest is now
# grounded deterministically, so the overclaim has to be in learner-visible text to matter).
BAD_DRAFT = {
    **GOOD_DRAFT,
    "stem": "Irregularly irregular pulse, rate ~118. The ECG shows an acute anterior STEMI.",
}


def test_generation_context_carries_constraints():
    ctx = build_generation_context(AF_PACKET, "ed", "mcq")
    assert "atrial_fibrillation" in ctx["supported_objectives"]
    assert ctx["acuity_ceiling"] in {"routine", "workup", "admit", "urgent", "act_now"}


def test_conforming_grounded_draft_is_accepted():
    result = generate_and_vet(AF_PACKET, "ed", "mcq", FakeProvider(GOOD_DRAFT))
    assert result["accepted"], result["reason"]
    assert result["item"].validation_status == "harness_pass"  # NOT auto-vetted


def test_overclaiming_draft_is_rejected_by_harness():
    result = generate_and_vet(AF_PACKET, "ed", "mcq", FakeProvider(BAD_DRAFT))
    assert not result["accepted"]
    assert result["reason"].startswith("harness:")
    assert "evidence_binding" in result["reason"]


def test_unparseable_draft_is_rejected():
    result = generate_and_vet(AF_PACKET, "ed", "mcq", FakeProvider("not json at all"))
    assert not result["accepted"]
    assert result["reason"] == "unparseable"


def test_measure_convergence_reports_rate():
    # Two good packets' worth of attempts (same provider) → 100% accept on this canned draft.
    summary = measure_convergence([AF_PACKET, AF_PACKET], "ed", "mcq", FakeProvider(GOOD_DRAFT))
    assert summary["attempts"] == 2
    assert summary["accept_rate"] == 1.0
