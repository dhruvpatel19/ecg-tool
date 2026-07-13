"""Playable v0 Clinical Decisions bank, authored on the renderable fixture cases.

Unlike the synthetic ``seed_items`` (harness fixtures with no waveform), these reference
real fixture ``ecg_id``s, so the React viewer renders an actual 12-lead and grading runs
against the real curated packet. Each is automatically screened through the harness at seed time
(``main`` calls ``vetted_fixture_items``). Covers mcq / click / oldnew / spoterror / triage
across the clinic / ward / ED lanes. Concept ids + grounding match the fixtures (see
``app.fixtures.build_fixture_cases``).
"""

from __future__ import annotations

from ..fixtures import build_fixture_cases
from .schemas import (
    ClinicalCaseItem,
    DisplaySpec,
    EvidenceClaim,
    EvidenceManifest,
    MachineLine,
    Option,
    RoiTarget,
    StemChips,
)

AF_MCQ = ClinicalCaseItem(
    item_id="fx-af-rvr-mcq",
    ecg_id="fixture-af-001",
    situation="ed",
    question_type="mcq",
    acuity_tier="moderate",
    stem="Palpitations for a few hours. Currently alert, warm, and perfusing; BP 124/78. The ECG is shown without a rhythm label.",
    chips=StemChips(age=64, setting="ed", symptom="palpitations", bp="124/78"),
    prompt="Which ECG interpretation-to-action chain is best?",
    options=[
        Option(id="af_rate", text="Irregular narrow-complex tachycardia consistent with AF: assess stability, evaluate rate-control options and contraindications, and assess thromboembolic risk.",
               answer_class="ideal", required_safety_tokens=["rate_control", "anticoagulation_assessment"]),
        Option(id="af_dccv", text="Immediate synchronized cardioversion.", answer_class="over_triage_safe"),
        Option(id="af_reassure", text="Reassure and discharge without treatment.", answer_class="under_triage"),
    ],
    evidence_manifest=EvidenceManifest(
        ecg_supports=[
            EvidenceClaim(objective_id="atrial_fibrillation", source_type="curated_label"),
            EvidenceClaim(objective_id="rate", threshold="heart_rate>=100", source_type="measured"),
        ],
        stem_adds=["age 64", "BP 124/78", "stable"],
        action_rationale="For stable AF with a rapid response, assess contributors and contraindications, choose an appropriate rate-control strategy, and evaluate thromboembolic risk; instability changes the pathway.",
        forbidden_claims=["unstable", "wide-complex tachycardia"],
        acceptable_range=["rate control", "anticoagulation assessment"],
    ),
    display_spec=DisplaySpec(mode="twelve_lead_pinned_strip", pinned_strip_lead="II", tested_scope="full_12_lead"),
)

QTC_MCQ = ClinicalCaseItem(
    item_id="fx-longqtc-mcq",
    ecg_id="fixture-long-qtc-001",
    situation="clinic",
    question_type="mcq",
    acuity_tier="moderate",
    stem="Medication review before starting a new agent. A baseline ECG is shown; the patient has no current symptoms.",
    chips=StemChips(age=58, setting="clinic", symptom="none"),
    prompt="Best next step?",
    options=[
        Option(id="qt_hold", text="Verify the QT/QTc, review or withhold implicated drugs as appropriate, and check/correct electrolytes.",
               answer_class="ideal", required_safety_tokens=["hold_qt_drugs", "check_electrolytes"]),
        Option(id="qt_mag", text="Give IV magnesium for presumed torsades now.", answer_class="over_triage_safe"),
        Option(id="qt_ignore", text="No action; recheck in a year.", answer_class="under_triage"),
    ],
    evidence_manifest=EvidenceManifest(
        ecg_supports=[
            EvidenceClaim(objective_id="qtc_prolongation", threshold="qtc_ms>=480", source_type="measured"),
        ],
        stem_adds=["age 58", "medication review"],
        action_rationale="Verify a prolonged QTc, review implicated drugs and interactions, check relevant electrolytes, and use the full clinical context rather than treating a printed number alone.",
        forbidden_claims=["torsades captured", "give magnesium for torsades"],
        acceptable_range=["hold QT-prolonging drugs", "check electrolytes"],
    ),
    display_spec=DisplaySpec(mode="twelve_lead_pinned_strip", pinned_strip_lead="II", tested_scope="full_12_lead"),
)

RBBB_CLICK = ClinicalCaseItem(
    item_id="fx-rbbb-click",
    ecg_id="fixture-rbbb-001",
    situation="clinic",
    question_type="click",
    acuity_tier="low",
    stem="Routine ECG, asymptomatic. The QRS looks wide.",
    chips=StemChips(age=60, setting="clinic", symptom="asymptomatic"),
    prompt="Click the wide QRS complex (look at V1).",
    roi_target=RoiTarget(concept="right_bundle_branch_block", leads=["V1", "V6"], target_type="segment"),
    evidence_manifest=EvidenceManifest(
        ecg_supports=[
            EvidenceClaim(objective_id="right_bundle_branch_block", leads=["V1"], source_type="curated_label"),
            EvidenceClaim(objective_id="qrs_duration", threshold="qrs_ms>=120", source_type="measured"),
        ],
        stem_adds=["age 60", "asymptomatic"],
        action_rationale="Wide QRS with an RBBB pattern; measure the QRS and recognize the terminal R' in V1.",
        forbidden_claims=["acute ischemia", "need for pacing"],
        acceptable_range=["wide QRS", "RBBB morphology"],
    ),
    tested_scope="zoom_lead",
    display_spec=DisplaySpec(mode="zoom_lead", zoom_lead="V1", tested_scope="zoom_lead"),
)

RBBB_OLDNEW = ClinicalCaseItem(
    item_id="fx-rbbb-oldnew",
    ecg_id="fixture-rbbb-001",
    prior_ecg_id="fixture-rbbb-001",
    situation="clinic",
    question_type="oldnew",
    acuity_tier="low",
    stem="Pre-op clearance, asymptomatic. Today's ECG with a prior on file.",
    chips=StemChips(age=66, setting="clinic", symptom="asymptomatic"),
    prompt="New, old/unchanged, or cannot determine?",
    options=[
        Option(id="on_old", text="Old / unchanged.", answer_class="ideal", value="old"),
        Option(id="on_new", text="New conduction change.", answer_class="over_triage_safe", value="new"),
        Option(id="on_cant", text="Cannot determine from what is shown.", answer_class="under_triage", value="cannot_determine"),
    ],
    evidence_manifest=EvidenceManifest(
        ecg_supports=[
            EvidenceClaim(objective_id="right_bundle_branch_block", source_type="curated_label"),
            EvidenceClaim(objective_id="qrs_duration", threshold="qrs_ms>=120", source_type="measured"),
        ],
        stem_adds=["age 66", "pre-op", "prior on file"],
        action_rationale="An unchanged RBBB pre-op rarely needs work-up; the useful question is whether it is new.",
        forbidden_claims=["new bundle branch block", "acute MI"],
        acceptable_range=["old/unchanged"],
    ),
    display_spec=DisplaySpec(mode="stacked_twelve_lead", tested_scope="full_12_lead"),
)

ANTERIOR_SPOTERROR = ClinicalCaseItem(
    item_id="fx-anterior-spoterror",
    ecg_id="fixture-anterior-mi-001",
    situation="ward",
    question_type="spoterror",
    acuity_tier="moderate",
    stem="Chest discomfort on the ward. The machine printed a read — audit it.",
    chips=StemChips(age=68, setting="ward", symptom="chest_pain"),
    prompt="One machine line is wrong. Click the part of the trace that proves it.",
    machine_read=[
        MachineLine(id="ml1", text="Sinus rhythm.", bad=False),
        MachineLine(id="ml2", text="No significant ST-segment abnormality.", bad=True),
    ],
    roi_target=RoiTarget(concept="anterior_mi", leads=["V2", "V3", "V4"], target_type="segment"),
    evidence_manifest=EvidenceManifest(
        ecg_supports=[
            EvidenceClaim(objective_id="anterior_mi", leads=["V2", "V3"], source_type="curated_label"),
        ],
        stem_adds=["age 68", "chest discomfort"],
        action_rationale="The machine missed anterior ST changes; re-derive its read and prove it on the precordial leads.",
        forbidden_claims=["evolving ischemia", "acute STEMI"],
        acceptable_range=["anterior ST changes", "ischemia work-up in context"],
    ),
    display_spec=DisplaySpec(mode="twelve_lead_machine_panel", tested_scope="full_12_lead"),
)

NORMAL_TRIAGE = ClinicalCaseItem(
    item_id="fx-normal-triage",
    ecg_id="fixture-normal-001",
    situation="clinic",
    question_type="triage",
    acuity_tier="none",
    stem="Asymptomatic adult, routine pre-participation ECG.",
    chips=StemChips(age=24, setting="clinic", symptom="asymptomatic"),
    prompt="Sick or not sick — what now?",
    options=[
        Option(id="nt_routine", text="Routine: reassure, no acute work-up.", answer_class="ideal", value="routine"),
        Option(id="nt_work", text="Work it up further before clearing.", answer_class="over_triage_safe", value="workup"),
        Option(id="nt_act", text="Treat as an emergency now.", answer_class="unsafe", value="act"),
    ],
    evidence_manifest=EvidenceManifest(
        ecg_supports=[
            EvidenceClaim(objective_id="normal_ecg", source_type="curated_label"),
            EvidenceClaim(objective_id="sinus_rhythm", source_type="curated_label"),
        ],
        stem_adds=["age 24", "asymptomatic"],
        action_rationale="Normal ECG in an asymptomatic adult → routine; recognizing normal is a skill.",
        forbidden_claims=["any acute finding"],
        acceptable_range=["routine", "not sick"],
    ),
    display_spec=DisplaySpec(mode="twelve_lead_pinned_strip", pinned_strip_lead="II", tested_scope="full_12_lead"),
)

FIXTURE_ITEMS: list[ClinicalCaseItem] = [
    AF_MCQ,
    QTC_MCQ,
    RBBB_CLICK,
    RBBB_OLDNEW,
    ANTERIOR_SPOTERROR,
    NORMAL_TRIAGE,
]

# Deterministic grounding for the fixture bank: the curated fixture case dicts already
# carry supported_objectives + ptbxl_plus (features/ROIs), which is all the harness and
# grader read. Used as a clinical_packet fallback so grounding does not depend on whether
# the corpus repo currently has fixtures loaded. (The viewer renders via /waveform, which
# serves fixtures regardless.)
FIXTURE_PACKETS: dict[str, dict] = {case["case_id"]: case for case in build_fixture_cases()}


def vetted_fixture_items(packet_provider) -> list[ClinicalCaseItem]:
    """Compatibility name: return fixture items that pass automated harness checks.

    Harness passage is not clinician review and must never be promoted to
    ``vetted`` without a separate, versioned reviewer record.
    """
    from .harness import run_harness

    out: list[ClinicalCaseItem] = []
    for item in FIXTURE_ITEMS:
        packet = packet_provider(item.ecg_id)
        if packet is None:
            continue
        prior = packet_provider(item.prior_ecg_id) if item.prior_ecg_id else None
        if run_harness(item, packet, prior).passed:
            item.validation_status = "harness_pass"
            out.append(item)
    return out
