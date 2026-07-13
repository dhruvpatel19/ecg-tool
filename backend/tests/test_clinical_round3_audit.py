"""Round-3 implementation-audit regression tests.

Each case is an exploit the GPT audit constructed; the harness must now REJECT it via the
named check. Guards against regressions in the round-3 P0 fixes (option action-urgency cap,
anti-laundering measurement-claim binding, temporal paraphrases, territory aliases,
transient claims in keyed options, and symptom-null laundering).
"""

from __future__ import annotations

import pytest

from app.clinical.fixture_items import FIXTURE_PACKETS
from app.clinical.harness import run_harness
from app.clinical.schemas import (
    ClinicalCaseItem,
    DisplaySpec,
    EvidenceClaim,
    EvidenceManifest,
    Option,
    StemChips,
)
from app.clinical.seed_items import SEED_PACKETS

AVB = SEED_PACKETS["seed-1avb-001"]      # supported: av_block_first_degree, sinus_rhythm, rate
STDEP = SEED_PACKETS["seed-stdep-001"]   # supported: st_depression, sinus_rhythm, rate
QTC = FIXTURE_PACKETS["fixture-long-qtc-001"]  # supported: qtc_prolongation, sinus_rhythm, rate, …


def _mcq(item_id, stem, options, *, ecg_supports, situation="clinic", acuity="low", symptom=None):
    return ClinicalCaseItem(
        item_id=item_id,
        ecg_id="x",
        situation=situation,
        question_type="mcq",
        acuity_tier=acuity,
        stem=stem,
        chips=StemChips(age=60, setting=situation, symptom=symptom),
        prompt="Next step?",
        options=options,
        evidence_manifest=EvidenceManifest(ecg_supports=ecg_supports, action_rationale="(test)", epistemic_status="determined"),
        tested_scope="full_12_lead",
        display_spec=DisplaySpec(mode="twelve_lead", tested_scope="full_12_lead"),
    )


CASES = [
    # 1. grounded fact → ungrounded high-acuity ACTION
    (
        _mcq(
            "adv-action-overreach",
            "Asymptomatic pre-op baseline ECG.",
            [
                Option(id="a", text="Admit to ICU now and call cardiology for urgent transvenous pacemaker placement.", answer_class="ideal"),
                Option(id="b", text="Document first-degree AV block and proceed with routine assessment.", answer_class="unsafe"),
            ],
            ecg_supports=[EvidenceClaim(objective_id="av_block_first_degree", leads=["II"], source_type="curated_label")],
            symptom="asymptomatic",
        ),
        AVB,
        "option_action_urgency_cap",
    ),
    # 2. laundered numeric claim: prose says PR > 300 but nothing validates it
    (
        _mcq(
            "adv-launder-measured",
            "Asymptomatic pre-op. ECG shows a markedly prolonged PR interval over 300 ms.",
            [
                Option(id="a", text="Document the finding and review medications routinely.", answer_class="ideal"),
                Option(id="b", text="Ignore it.", answer_class="unsafe"),
            ],
            ecg_supports=[EvidenceClaim(objective_id="av_block_first_degree", leads=["II"], source_type="curated_label")],
            symptom="asymptomatic",
        ),
        AVB,
        "measurement_claim_binding",
    ),
    # 3. acute temporal paraphrase that dodges the literal cue list
    (
        _mcq(
            "adv-temporal-paraphrase",
            "66-year-old with chest pressure that came on during breakfast and is now spreading to the left arm.",
            [
                Option(id="a", text="Treat as NSTEMI and admit to a monitored bed.", answer_class="ideal"),
                Option(id="b", text="Routine outpatient follow-up.", answer_class="unsafe"),
            ],
            ecg_supports=[EvidenceClaim(objective_id="st_depression", leads=["V5"], roi_concept="st_segment", source_type="curated_label")],
            situation="ed",
            acuity="moderate",
            symptom="chest_pain",
        ),
        STDEP,
        "acute_temporal_causality",
    ),
    # 4. territory/occlusion alias not in the original banned list
    (
        _mcq(
            "adv-territory-alias",
            "70-year-old with chest discomfort. ECG suggests a high-lateral OMI pattern.",
            [
                Option(id="a", text="Call cardiology for suspected high-lateral occlusion MI.", answer_class="ideal"),
                Option(id="b", text="Treat as benign nonspecific change.", answer_class="unsafe"),
            ],
            ecg_supports=[EvidenceClaim(objective_id="st_depression", leads=["V5"], roi_concept="st_segment", source_type="curated_label")],
            situation="ed",
            acuity="moderate",
            symptom="chest_pain",
        ),
        STDEP,
        "evidence_binding",
    ),
    # 5. transient-event claim in the KEYED (ideal) option, not the stem
    (
        _mcq(
            "adv-transient-in-option",
            "70-year-old inpatient on haloperidol. ECG shown.",
            [
                Option(id="a", text="Give IV magnesium now for torsades and transfer to ICU.", answer_class="ideal"),
                Option(id="b", text="Hold QT-prolonging meds and check K/Mg/Ca.", answer_class="unsafe"),
            ],
            ecg_supports=[EvidenceClaim(objective_id="qtc_prolongation", threshold="qtc_ms>=500", source_type="measured")],
            situation="ward",
            acuity="moderate",
            symptom="dizziness",
        ),
        QTC,
        "transient_event_evidence",
    ),
    # 6. symptom-null laundering: stem says "blackouts" but the chip is null
    (
        _mcq(
            "adv-symptom-null",
            "48-year-old with recurrent blackouts while walking. Baseline ECG shows first-degree AV block.",
            [
                Option(id="a", text="Admit urgently for pacing evaluation.", answer_class="ideal"),
                Option(id="b", text="Review medications routinely.", answer_class="unsafe"),
            ],
            ecg_supports=[EvidenceClaim(objective_id="av_block_first_degree", threshold="pr_ms>=200", leads=["II"], source_type="measured")],
            symptom=None,
        ),
        AVB,
        "symptom_causality",
    ),
]


@pytest.mark.parametrize("item, packet, expected_check", CASES, ids=[c[0].item_id for c in CASES])
def test_round3_exploits_rejected(item, packet, expected_check):
    report = run_harness(item, packet, None)
    assert not report.passed, f"{item.item_id} should be rejected"
    assert expected_check in report.failing_checks(), (
        f"{item.item_id} not caught by {expected_check}; failing: {report.failing_checks()}"
    )
