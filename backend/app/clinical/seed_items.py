"""Hand-authored seed Clinical Decisions items + their grounding packets.

These encode the review's worked cases (W complete heart block, T wide-complex
tachycardia, C click-the-long-PR, O old-or-new, M SVT, S spot-the-error) — including
the CORRECTED Case W (insufficient-data + a *parallel* safety action is ideal/acceptable,
not low credit). They double as the harness test fixtures, with minimal-but-faithful
grounding packets so the suite runs corpus-free. ``ADVERSARIAL`` holds the three
overclaims from the review that the harness must REJECT.

NOTE: the grounding packets here are synthetic stand-ins for real curated PTB-XL packets;
the production bank wires items to real ``cases`` rows. Concept ids match the ontology.
"""

from __future__ import annotations

from typing import Any

from ..schemas import LEADS
from ..fixtures import _make_waveform
from .schemas import (
    ClinicalCaseItem,
    DisplaySpec,
    EvidenceClaim,
    EvidenceManifest,
    MachineLine,
    Option,
    RoiTarget,
    StemChips,
    StepOption,
    StepwiseStep,
)


# --- minimal grounding-packet helpers ---------------------------------------------
def _roi(lead: str, concept: str) -> dict[str, Any]:
    return {
        "lead": lead,
        "concept": concept,
        "timeStartSec": 2.40,
        "timeEndSec": 2.62,
        "ampMinMv": -0.40,
        "ampMaxMv": 0.70,
        "label": concept.replace("_", " "),
        "source": "seed_synthetic",
        "confidence": "high",
    }


def _packet(ecg_id: str, supported: list[str], features: dict[str, Any], rois: list[dict]) -> dict[str, Any]:
    return {
        "case_id": ecg_id,
        "display_id": ecg_id,
        "source": "seed",
        "supported_objectives": supported,
        "ptbxl": {"report": "", "metadata": {}, "scp_codes": {}},
        "ptbxl_plus": {"features": features, "fiducials": {"rois": rois}},
        "waveform": {"leads": list(LEADS), "duration_sec": 10},
        "signal_quality": {"status": "acceptable", "reasons": []},
    }


SEED_PACKETS: dict[str, dict[str, Any]] = {
    "seed-chb-001": _packet(
        "seed-chb-001",
        ["av_block_third_degree", "bradycardia", "rate"],
        {"heart_rate": 38, "pr_ms": None, "qrs_ms": 112, "qt_ms": 460, "qtc_ms": 410, "axis_deg": 30},
        [_roi("II", "qrs_complex"), _roi("II", "p_wave")],
    ),
    "seed-wct-001": _packet(
        "seed-wct-001",
        ["wide_complex_tachycardia", "rate"],
        {"heart_rate": 170, "qrs_ms": 150, "qt_ms": 300, "qtc_ms": 470, "axis_deg": -80},
        [_roi("V1", "qrs_complex"), _roi("II", "qrs_complex")],
    ),
    "seed-1avb-001": _packet(
        "seed-1avb-001",
        ["av_block_first_degree", "sinus_rhythm", "rate"],
        {"heart_rate": 70, "pr_ms": 240, "qrs_ms": 90, "qt_ms": 400, "qtc_ms": 420, "axis_deg": 40},
        [_roi("II", "pr_interval"), _roi("II", "p_wave")],
    ),
    "seed-oldnew-today-001": _packet(
        "seed-oldnew-today-001",
        ["left_bundle_branch_block", "qrs_duration", "left_axis_deviation"],
        {"heart_rate": 74, "pr_ms": 168, "qrs_ms": 140, "qt_ms": 430, "qtc_ms": 470, "axis_deg": -35},
        [_roi("V1", "qrs_complex"), _roi("V6", "qrs_complex")],
    ),
    "seed-oldnew-prior-001": _packet(
        "seed-oldnew-prior-001",
        ["left_bundle_branch_block", "qrs_duration", "left_axis_deviation"],
        {"heart_rate": 71, "pr_ms": 166, "qrs_ms": 142, "qt_ms": 432, "qtc_ms": 468, "axis_deg": -33},
        [_roi("V1", "qrs_complex"), _roi("V6", "qrs_complex")],
    ),
    "seed-svt-001": _packet(
        "seed-svt-001",
        ["supraventricular_tachycardia", "rate"],
        {"heart_rate": 180, "qrs_ms": 88, "qt_ms": 280, "qtc_ms": 460, "axis_deg": 60},
        [_roi("II", "qrs_complex")],
    ),
    "seed-stdep-001": _packet(
        "seed-stdep-001",
        ["st_depression", "sinus_rhythm", "rate"],
        {"heart_rate": 80, "pr_ms": 160, "qrs_ms": 92, "qt_ms": 380, "qtc_ms": 438, "axis_deg": 20},
        [_roi("V5", "st_segment"), _roi("V4", "st_segment")],
    ),
    "seed-nonspecific-001": _packet(
        "seed-nonspecific-001",
        ["nonspecific_st_t_change", "sinus_rhythm", "rate"],
        {"heart_rate": 78, "pr_ms": 158, "qrs_ms": 94, "qt_ms": 384, "qtc_ms": 437, "axis_deg": 25},
        [_roi("V4", "st_segment")],
    ),
}


# Renderable synthetic teaching traces for the hand-authored simulations. These
# never masquerade as PTB-XL: the serving contract labels them synthetic and
# formative, and the waveform endpoint only uses this map as an explicit fallback
# for ``seed-*`` ids. Complete block has independent atrial/ventricular clocks so
# its stepwise P-QRS question is visually represented rather than inferred from a
# normal bradycardic template.
SEED_WAVEFORMS: dict[str, dict[str, Any]] = {
    "seed-chb-001": _make_waveform(
        "seed-chb-001", 38, morphology="complete_block", atrial_rate_bpm=78, noise=0.008
    ),
    "seed-wct-001": _make_waveform("seed-wct-001", 170, morphology="lbbb", noise=0.01),
    "seed-1avb-001": _make_waveform("seed-1avb-001", 70, noise=0.008),
    "seed-oldnew-today-001": _make_waveform("seed-oldnew-today-001", 74, morphology="lbbb"),
    "seed-oldnew-prior-001": _make_waveform("seed-oldnew-prior-001", 71, morphology="lbbb"),
    "seed-svt-001": _make_waveform("seed-svt-001", 180, noise=0.008),
    "seed-stdep-001": _make_waveform(
        "seed-stdep-001", 80, st_by_lead={"V4": -0.16, "V5": -0.18}, noise=0.008
    ),
    "seed-nonspecific-001": _make_waveform(
        "seed-nonspecific-001", 78, st_by_lead={"V4": -0.06}, noise=0.01
    ),
}


def seed_waveform_window(
    ecg_id: str,
    *,
    leads: list[str] | None = None,
    start: float = 0,
    end: float | None = None,
    max_points: int = 1200,
) -> dict[str, Any] | None:
    """Return a downsampled window for an explicitly synthetic seed tracing."""
    waveform = SEED_WAVEFORMS.get(ecg_id)
    if waveform is None:
        return None
    fs = int(waveform["sampling_frequency"])
    duration = float(waveform["duration_sec"])
    end = duration if end is None else min(float(end), duration)
    start = max(0.0, min(float(start), end))
    selected = [lead for lead in (leads or list(LEADS)) if lead in LEADS]
    start_idx, end_idx = int(start * fs), int(end * fs)
    step = max(1, max(1, end_idx - start_idx) // max_points)
    indices = list(range(start_idx, end_idx, step))
    times = [round(idx / fs, 3) for idx in indices]
    signal = waveform["signal"]
    return {
        "caseId": ecg_id,
        "samplingFrequency": fs,
        "durationSec": duration,
        "startSec": start,
        "endSec": end,
        "leads": [
            {
                "lead": lead,
                "points": [
                    {"timeSec": time, "amplitudeMv": signal[lead][idx]}
                    for time, idx in zip(times, indices)
                ],
            }
            for lead in selected
        ],
        "syntheticTeachingWaveform": True,
    }


# --- the seed items ---------------------------------------------------------------
CASE_W = ClinicalCaseItem(
    item_id="seed-W-chb",
    ecg_id="seed-chb-001",
    situation="ward",
    question_type="stepwise",
    acuity_tier="high",
    stem="Inpatient on telemetry with new dizziness; telemetry called you to the bedside.",
    chips=StemChips(age=71, setting="inpatient", symptom="dizziness"),
    prompt="Commit to the most appropriate next step.",
    options=[
        Option(
            id="w1",
            text="Apply transcutaneous pacing pads, check pulse/BP at the bedside, and call cardiology.",
            answer_class="ideal",
            required_safety_tokens=["pacing_pads", "bedside_now", "call_help"],
        ),
        Option(
            id="w2",
            text="Get vitals and a 12-lead while readying the pacing pads.",
            answer_class="ideal",
            required_safety_tokens=["tcp_ready", "twelve_lead"],
        ),
        Option(
            id="w3",
            text="Give atropine while placing pacing pads and calling cardiology.",
            answer_class="acceptable",
            required_safety_tokens=["atropine", "pacing_pads", "call_help"],
        ),
        Option(id="w4", text="Continuous monitoring and routine a.m. labs.", answer_class="under_triage"),
        Option(id="w5", text="Reassure and discharge.", answer_class="unsafe"),
    ],
    steps=[
        StepwiseStep(
            prompt="Ventricular rate?",
            options=[StepOption(text="~38 (bradycardic)", correct=True), StepOption(text="~75", correct=False)],
        ),
        StepwiseStep(
            prompt="P–QRS relationship?",
            options=[StepOption(text="Dissociated", correct=True), StepOption(text="1:1 conduction", correct=False)],
        ),
    ],
    evidence_manifest=EvidenceManifest(
        ecg_supports=[
            EvidenceClaim(objective_id="av_block_third_degree", source_type="curated_label"),
            EvidenceClaim(objective_id="bradycardia", threshold="heart_rate<=50", source_type="measured"),
        ],
        stem_adds=["age 71", "inpatient", "telemetry alert", "new dizziness"],
        action_rationale="Symptomatic high-grade/complete block needs bedside assessment + pacing readiness; atropine often fails in infranodal block.",
        forbidden_claims=["STEMI", "acute ischemia as cause", "hemodynamic collapse"],
        acceptable_range=["pacing readiness", "bedside assessment", "cardiology"],
        epistemic_status="determined",
    ),
    tested_scope="full_12_lead",
    display_spec=DisplaySpec(mode="twelve_lead_pinned_strip", pinned_strip_lead="II", tested_scope="full_12_lead"),
    provenance="hand_authored",
)

CASE_T = ClinicalCaseItem(
    item_id="seed-T-wct",
    ecg_id="seed-wct-001",
    situation="ed",
    question_type="triage",
    acuity_tier="high",
    stem="Palpitations and lightheadedness; the patient looks unwell.",
    chips=StemChips(age=58, setting="ed", symptom="palpitations", bp="88/54"),
    prompt="Sick or not sick — what now?",
    options=[
        Option(
            id="t_act",
            text="Treat as unstable: place pads, prepare synchronized cardioversion, call for help.",
            answer_class="ideal",
            value="act",
            required_safety_tokens=["synchronized_cardioversion", "defib_pads", "act_now"],
        ),
        Option(id="t_work", text="Work it up: labs and a formal rhythm read before treating.", answer_class="under_triage", value="workup"),
        Option(id="t_routine", text="Routine handling; recheck later.", answer_class="unsafe", value="routine"),
    ],
    evidence_manifest=EvidenceManifest(
        ecg_supports=[
            EvidenceClaim(objective_id="wide_complex_tachycardia", source_type="curated_label"),
            EvidenceClaim(objective_id="rate", threshold="heart_rate>=100", source_type="measured"),
        ],
        stem_adds=["age 58", "BP 88/54"],
        action_rationale="Wide + fast + hypotensive → treat as unstable; prepare synchronized cardioversion; avoid AV-nodal blockers.",
        forbidden_claims=["definitive VT label without caveat", "STEMI"],
        acceptable_range=["act now", "treat as VT until proven otherwise"],
        epistemic_status="determined",
    ),
    tested_scope="full_12_lead",
    display_spec=DisplaySpec(mode="twelve_lead_pinned_strip", pinned_strip_lead="II", tested_scope="full_12_lead"),
    provenance="hand_authored",
)

CASE_C = ClinicalCaseItem(
    item_id="seed-C-1avb",
    ecg_id="seed-1avb-001",
    situation="clinic",
    question_type="click",
    acuity_tier="low",
    stem="Routine pre-op, asymptomatic. Something looks prolonged.",
    chips=StemChips(age=48, setting="clinic", symptom="asymptomatic"),
    prompt="Click the interval that is prolonged (P onset → QRS onset).",
    roi_target=RoiTarget(concept="av_block_first_degree", leads=["II"], target_type="interval"),
    evidence_manifest=EvidenceManifest(
        ecg_supports=[
            EvidenceClaim(objective_id="av_block_first_degree", threshold="pr_ms>=200", leads=["II"], source_type="measured"),
        ],
        stem_adds=["age 48", "pre-op", "asymptomatic"],
        action_rationale="Isolated long PR is usually benign; it matters as part of higher-grade block.",
        forbidden_claims=["complete heart block", "need for pacing"],
        acceptable_range=["measure PR", "first-degree AV block"],
        epistemic_status="determined",
    ),
    tested_scope="zoom_lead",
    display_spec=DisplaySpec(mode="zoom_lead", zoom_lead="II", tested_scope="zoom_lead"),
    provenance="hand_authored",
)

CASE_O = ClinicalCaseItem(
    item_id="seed-O-oldnew",
    ecg_id="seed-oldnew-today-001",
    prior_ecg_id="seed-oldnew-prior-001",
    situation="clinic",
    question_type="oldnew",
    acuity_tier="low",
    stem="Pre-op clearance, asymptomatic. Today's ECG with a prior from two years ago.",
    chips=StemChips(age=62, setting="clinic", symptom="asymptomatic"),
    prompt="New, old/unchanged, or cannot determine?",
    options=[
        Option(id="o_old", text="Old / unchanged.", answer_class="ideal", value="old"),
        Option(id="o_new", text="New / acute conduction change.", answer_class="over_triage_safe", value="new"),
        Option(id="o_cant", text="Cannot determine from what is shown.", answer_class="under_triage", value="cannot_determine"),
    ],
    evidence_manifest=EvidenceManifest(
        ecg_supports=[
            EvidenceClaim(objective_id="left_bundle_branch_block", source_type="curated_label"),
            EvidenceClaim(objective_id="left_axis_deviation", threshold="axis_deg<=-30", source_type="measured"),
        ],
        stem_adds=["age 62", "pre-op", "prior available"],
        action_rationale="Unchanged conduction disease pre-op rarely needs work-up; the useful question is whether it is new.",
        forbidden_claims=["new bundle branch block", "acute MI"],
        acceptable_range=["old/unchanged"],
        epistemic_status="determined",
    ),
    tested_scope="full_12_lead",
    display_spec=DisplaySpec(mode="stacked_twelve_lead", tested_scope="full_12_lead"),
    provenance="hand_authored",
)

CASE_M = ClinicalCaseItem(
    item_id="seed-M-svt",
    ecg_id="seed-svt-001",
    situation="ed",
    question_type="mcq",
    acuity_tier="moderate",
    stem="Palpitations, regular and fast. Stable, BP 118/70.",
    chips=StemChips(age=55, setting="ed", symptom="palpitations", bp="118/70"),
    prompt="Most appropriate first step?",
    options=[
        Option(
            id="m_ideal",
            text="Vagal manoeuvres; if no conversion, adenosine with continuous monitoring.",
            answer_class="ideal",
            required_safety_tokens=["vagal_maneuver", "adenosine", "continuous_monitoring"],
        ),
        Option(id="m_over", text="Synchronized cardioversion now with sedation.", answer_class="over_triage_safe"),
        Option(id="m_af", text="Treat as atrial fibrillation with IV diltiazem rate control.", answer_class="under_triage"),
        Option(id="m_under", text="Order troponin, TSH, electrolytes and observe on telemetry first.", answer_class="under_triage"),
    ],
    evidence_manifest=EvidenceManifest(
        ecg_supports=[
            EvidenceClaim(objective_id="supraventricular_tachycardia", source_type="curated_label"),
            EvidenceClaim(objective_id="rate", threshold="heart_rate>=150", source_type="measured"),
        ],
        stem_adds=["age 55", "BP 118/70", "stable"],
        action_rationale="Stable + regular + narrow → vagal/adenosine before electricity.",
        forbidden_claims=["unstable", "irregularly irregular AF", "wide-complex tachycardia"],
        acceptable_range=["vagal manoeuvres", "adenosine"],
        epistemic_status="determined",
    ),
    tested_scope="full_12_lead",
    display_spec=DisplaySpec(mode="twelve_lead_pinned_strip", pinned_strip_lead="II", tested_scope="full_12_lead"),
    provenance="hand_authored",
)

CASE_S = ClinicalCaseItem(
    item_id="seed-S-spoterror",
    ecg_id="seed-stdep-001",
    situation="ward",
    question_type="spoterror",
    acuity_tier="moderate",
    stem="Intermittent chest discomfort. The machine printed a read — audit it.",
    chips=StemChips(age=80, setting="ward", symptom="chest_pain"),
    prompt="One line of the machine read is wrong. Click the part of the trace that proves it.",
    machine_read=[
        MachineLine(id="ml1", text="Sinus rhythm.", bad=False),
        MachineLine(id="ml2", text="No ST-T changes.", bad=True),
    ],
    roi_target=RoiTarget(concept="st_depression", leads=["V5", "V4"], target_type="segment"),
    evidence_manifest=EvidenceManifest(
        ecg_supports=[
            EvidenceClaim(objective_id="st_depression", leads=["V5"], roi_concept="st_segment", source_type="curated_label"),
        ],
        stem_adds=["age 80", "intermittent chest discomfort"],
        action_rationale="Trust the machine's numbers; re-derive its interpretation. ST depression warrants ischemia work-up in context.",
        forbidden_claims=["acute STEMI", "evolving ischemia"],
        acceptable_range=["ST depression", "ischemia work-up in context"],
        epistemic_status="determined",
    ),
    tested_scope="full_12_lead",
    display_spec=DisplaySpec(mode="twelve_lead_machine_panel", tested_scope="full_12_lead"),
    provenance="hand_authored",
)

SEED_ITEMS: list[ClinicalCaseItem] = [CASE_W, CASE_T, CASE_C, CASE_O, CASE_M, CASE_S]


# --- adversarial negatives the harness MUST reject --------------------------------
# (item, packet, prior_packet, expected_failing_check)
_ADV1 = ClinicalCaseItem(
    item_id="adv-1-chronic-as-acute",
    ecg_id="seed-stdep-001",
    situation="ed",
    question_type="mcq",
    acuity_tier="high",
    stem="66M with crushing chest pain that started 20 minutes ago, diaphoretic, pain escalating in the ED.",
    chips=StemChips(age=66, setting="ed", symptom="chest_pain"),
    prompt="Next step?",
    options=[
        Option(id="a1", text="Activate the cath lab and treat as an acute STEMI pathway.", answer_class="ideal"),
        Option(id="a2", text="Reassure and discharge.", answer_class="unsafe"),
    ],
    evidence_manifest=EvidenceManifest(
        ecg_supports=[EvidenceClaim(objective_id="st_depression", leads=["V5"], roi_concept="st_segment", source_type="curated_label")],
        stem_adds=["66M"],
        action_rationale="(adversarial) treats chronic ST depression as an evolving acute event.",
        epistemic_status="determined",
    ),
    tested_scope="full_12_lead",
    display_spec=DisplaySpec(mode="twelve_lead", tested_scope="full_12_lead"),
)

_ADV2 = ClinicalCaseItem(
    item_id="adv-2-1avb-syncope",
    ecg_id="seed-1avb-001",
    situation="clinic",
    question_type="mcq",
    acuity_tier="high",
    stem="48F with recurrent syncope. The ECG explains the episodes.",
    chips=StemChips(age=48, setting="clinic", symptom="syncope"),
    prompt="Next step?",
    options=[
        Option(id="b1", text="Admit for high-grade conduction disease evaluation and cardiology consult.", answer_class="ideal"),
        Option(id="b2", text="Reassure; routine follow-up.", answer_class="under_triage"),
    ],
    evidence_manifest=EvidenceManifest(
        ecg_supports=[EvidenceClaim(objective_id="av_block_first_degree", threshold="pr_ms>=200", leads=["II"], source_type="measured")],
        stem_adds=["48F"],
        action_rationale="(adversarial) keys isolated first-degree AV block as the cause of syncope.",
        epistemic_status="determined",
    ),
    tested_scope="full_12_lead",
    display_spec=DisplaySpec(mode="twelve_lead", tested_scope="full_12_lead"),
)

_ADV3 = ClinicalCaseItem(
    item_id="adv-3-nonspecific-as-nstemi",
    ecg_id="seed-nonspecific-001",
    situation="ed",
    question_type="mcq",
    acuity_tier="moderate",
    stem="The ECG shows inferolateral ST changes; treat as NSTEMI.",
    chips=StemChips(age=60, setting="ed", symptom="chest_pain"),
    prompt="Next step?",
    options=[
        Option(id="c1", text="Admit to the NSTEMI pathway.", answer_class="ideal"),
        Option(id="c2", text="Discharge home.", answer_class="unsafe"),
    ],
    evidence_manifest=EvidenceManifest(
        ecg_supports=[EvidenceClaim(objective_id="inferior_mi", leads=["II", "III", "aVF"], source_type="curated_label")],
        stem_adds=["60yo"],
        action_rationale="(adversarial) inflates a nonspecific ST-T finding into a localized infarct.",
        epistemic_status="determined",
    ),
    tested_scope="full_12_lead",
    display_spec=DisplaySpec(mode="twelve_lead", tested_scope="full_12_lead"),
)

ADVERSARIAL: list[tuple[ClinicalCaseItem, dict[str, Any], dict[str, Any] | None, str]] = [
    (_ADV1, SEED_PACKETS["seed-stdep-001"], None, "acute_temporal_causality"),
    (_ADV2, SEED_PACKETS["seed-1avb-001"], None, "symptom_causality"),
    (_ADV3, SEED_PACKETS["seed-nonspecific-001"], None, "evidence_binding"),
]


def vetted_seed_items() -> list[ClinicalCaseItem]:
    """Compatibility name: seed items that pass automated harness checks."""
    from .harness import run_harness

    out: list[ClinicalCaseItem] = []
    for item in SEED_ITEMS:
        report = run_harness(item, packet_for(item), prior_packet_for(item))
        if report.passed:
            item.validation_status = "harness_pass"
            out.append(item)
    return out


def packet_for(item: ClinicalCaseItem) -> dict[str, Any]:
    return SEED_PACKETS[item.ecg_id]


def prior_packet_for(item: ClinicalCaseItem) -> dict[str, Any] | None:
    return SEED_PACKETS.get(item.prior_ecg_id) if item.prior_ecg_id else None
