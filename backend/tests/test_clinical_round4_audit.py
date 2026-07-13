"""Round-4 (clinical/pedagogical) audit regression tests — the harness blind spots the
cardiology audit found, now closed: false QTc threshold, distractor self-refutation, action-class
inversion, ECG-pattern-as-history, click stem leakage; + the triage-class and click-specificity fixes.
"""

from __future__ import annotations

from app.clinical.generator import _derive_triage_classes, _template_click
from app.clinical.harness import run_harness
from app.clinical.schemas import (
    ClinicalCaseItem,
    DisplaySpec,
    EvidenceClaim,
    EvidenceManifest,
    Option,
    RoiTarget,
    StemChips,
)


def _packet(supported, features, rois=None, sex=None):
    return {
        "case_id": "x",
        "supported_objectives": supported,
        "ptbxl": {"report": "", "metadata": {"sex": sex}, "scp_codes": {}},
        "ptbxl_plus": {"features": features, "fiducials": {"rois": rois or []}},
        "waveform": {"leads": ["II"], "duration_sec": 10},
        "signal_quality": {"status": "acceptable"},
    }


def _mcq(options, *, qtype="mcq", stem="Resting ECG in a stable patient.", manifest_targets=None, rationale="(test)"):
    return ClinicalCaseItem(
        item_id="t", ecg_id="x", situation="ward", question_type=qtype, acuity_tier="moderate",
        stem=stem, chips=StemChips(age=65, setting="ward"), prompt="Next step?",
        options=options,
        evidence_manifest=EvidenceManifest(
            ecg_supports=[EvidenceClaim(objective_id=c, source_type="curated_label") for c in (manifest_targets or [])],
            action_rationale=rationale, epistemic_status="determined",
        ),
        tested_scope="full_12_lead", display_spec=DisplaySpec(mode="twelve_lead", tested_scope="full_12_lead"),
    )


def test_false_qtc_prolongation_in_af_rejected():
    pkt = _packet(["atrial_fibrillation", "qtc_prolongation", "rate"], {"qtc_ms": 437}, sex=1)
    item = _mcq([Option(id="a", text="Review meds and electrolytes for QT.", answer_class="ideal"),
                 Option(id="b", text="Ignore it.", answer_class="unsafe")],
                manifest_targets=["qtc_prolongation"], stem="AF with a prolonged QTc of ~437 ms.")
    rep = run_harness(item, pkt, None)
    assert not rep.passed and "clinical_numeric_semantics" in rep.failing_checks()


def test_false_qtc_below_threshold_rejected():
    pkt = _packet(["qtc_prolongation", "sinus_rhythm", "rate"], {"qtc_ms": 437}, sex=1)
    item = _mcq([Option(id="a", text="Treat the prolonged QT.", answer_class="ideal"),
                 Option(id="b", text="Nothing.", answer_class="unsafe")],
                manifest_targets=["qtc_prolongation"], stem="Sinus rhythm with a prolonged QTc of 437 ms in a woman.")
    rep = run_harness(item, pkt, None)
    assert not rep.passed and "clinical_numeric_semantics" in rep.failing_checks()


def test_genuinely_prolonged_qtc_passes():
    pkt = _packet(["qtc_prolongation", "sinus_rhythm", "rate"], {"qtc_ms": 510}, sex=1)
    item = _mcq([Option(id="a", text="Review QT-prolonging meds and check electrolytes.", answer_class="ideal"),
                 Option(id="b", text="Discharge with no plan.", answer_class="unsafe")],
                manifest_targets=["qtc_prolongation"], stem="Sinus rhythm with a prolonged QTc of 510 ms.")
    assert "clinical_numeric_semantics" not in run_harness(item, pkt, None).failing_checks()


def test_distractor_self_refutation_rejected():
    pkt = _packet(["atrial_fibrillation", "rate"], {"heart_rate": 80})
    item = _mcq([Option(id="a", text="Assess stroke risk and anticoagulate if indicated.", answer_class="ideal"),
                 Option(id="b", text="Treat as ACS despite the chronic findings and no acute symptoms.", answer_class="unsafe")],
                manifest_targets=["atrial_fibrillation"])
    rep = run_harness(item, pkt, None)
    assert not rep.passed and "distractor_leak" in rep.failing_checks()


def test_aggressive_action_tagged_undertriage_rejected():
    pkt = _packet(["av_block_first_degree", "sinus_rhythm", "rate"], {"pr_ms": 216})
    item = _mcq([Option(id="a", text="Continue ward monitoring and outpatient follow-up.", answer_class="ideal"),
                 Option(id="b", text="Send to the ED immediately for emergent evaluation.", answer_class="under_triage"),
                 Option(id="c", text="Discharge with no follow-up.", answer_class="unsafe")],
                qtype="stepwise", manifest_targets=["av_block_first_degree"])
    rep = run_harness(item, pkt, None)
    assert not rep.passed and "option_class_action_consistency" in rep.failing_checks()


def test_ecg_pattern_as_documented_history_rejected():
    pkt = _packet(["myocardial_infarction", "anterior_mi", "rate"], {"heart_rate": 70})
    item = _mcq([Option(id="a", text="Outpatient cardiology follow-up for the old-MI pattern.", answer_class="ideal"),
                 Option(id="b", text="Do nothing.", answer_class="unsafe")],
                manifest_targets=["anterior_mi"],
                rationale="Ensure secondary prevention for known prior MI.")
    rep = run_harness(item, pkt, None)
    assert not rep.passed and "disease_history_provenance" in rep.failing_checks()


def test_click_stem_leak_rejected():
    pkt = _packet(["av_block_first_degree", "rate"], {"pr_ms": 220},
                  rois=[{"lead": "II", "concept": "pr_interval", "timeStartSec": 0.8, "timeEndSec": 1.0, "ampMinMv": -0.1, "ampMaxMv": 0.2}])
    item = ClinicalCaseItem(
        item_id="t", ecg_id="x", situation="clinic", question_type="click", acuity_tier="low",
        stem="A 30-year-old in clinic. The learner is asked to click the correct finding on the trace.",
        chips=StemChips(age=30, setting="clinic"), prompt="Click the PR interval.",
        roi_target=RoiTarget(concept="av_block_first_degree", leads=["II"], target_type="interval"),
        evidence_manifest=EvidenceManifest(ecg_supports=[EvidenceClaim(objective_id="av_block_first_degree", source_type="curated_label")]),
        tested_scope="zoom_lead", display_spec=DisplaySpec(mode="zoom_lead", zoom_lead="II", tested_scope="zoom_lead"),
    )
    rep = run_harness(item, pkt, None)
    assert not rep.passed and "click_stem_leak" in rep.failing_checks()


def test_template_click_prefers_specific_over_nonspecific():
    pkt = _packet(["nonspecific_st_t_change", "st_depression", "rate"], {"heart_rate": 80},
                  rois=[{"lead": "V5", "concept": "st_segment", "timeStartSec": 1.0, "timeEndSec": 1.1, "ampMinMv": -0.2, "ampMaxMv": 0.0}])
    item = _mcq([], manifest_targets=["st_depression"])
    item.question_type = "click"
    out = _template_click(item, pkt)
    assert out.roi_target.concept == "st_depression"  # NOT nonspecific_st_t_change
    assert "depress" in out.prompt.lower()


def test_derive_triage_classes_fixes_inversion():
    item = ClinicalCaseItem(
        item_id="t", ecg_id="x", situation="ed", question_type="triage", acuity_tier="low",
        stem="Stable symptomatic sinus bradycardia.", chips=StemChips(age=40, setting="ed"),
        prompt="Act now, work it up, or routine?",
        options=[
            Option(id="a", text="Act now: urgent ED resuscitation escalation.", answer_class="under_triage", value="act"),
            Option(id="b", text="Work it up: monitor + labs + med review.", answer_class="ideal", value="workup"),
            Option(id="c", text="Routine: discharge without evaluation.", answer_class="over_triage_safe", value="routine"),
        ],
        evidence_manifest=EvidenceManifest(ecg_supports=[EvidenceClaim(objective_id="bradycardia", source_type="curated_label")]),
        tested_scope="full_12_lead", display_spec=DisplaySpec(mode="twelve_lead", tested_scope="full_12_lead"),
    )
    _derive_triage_classes(item)
    by = {o.id: o.answer_class for o in item.options}
    assert by["a"] == "over_triage_safe"  # act > workup → over-triage (was wrongly under_triage)
    assert by["c"] == "under_triage"      # routine < workup → under-triage (was wrongly over_triage_safe)
