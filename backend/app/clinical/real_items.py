"""Hand-authored Clinical Decisions bank grounded in checked PTB packets.

The vignettes and answer choices are authored simulations.  The ECGs are real,
de-identified records selected from the checked corpus and resolved at startup
through the same packet provider used for serving and grading.  Synthetic seed
and fixture banks live in their test modules and are intentionally not imported
by the application startup path.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any, Callable

from .harness import run_harness
from .provenance import assert_learner_item_provenance
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

PacketProvider = Callable[[str], dict[str, Any] | None]


REAL_CHB_STEPWISE = ClinicalCaseItem(
    item_id="ptb-8911-chb-stepwise",
    ecg_id="8911",
    situation="ward",
    question_type="stepwise",
    acuity_tier="high",
    stem="An inpatient reports new dizziness after telemetry asks you to review a slow rhythm. No blood pressure or pulse assessment has yet been documented.",
    chips=StemChips(age=71, setting="inpatient", symptom="dizziness"),
    prompt="Build the ECG interpretation, then choose the safest immediate next step.",
    options=[
        Option(
            id="chb_bedside",
            text="Assess pulse and blood pressure now, place pacing pads, and call for senior/cardiology support.",
            answer_class="ideal",
            required_safety_tokens=["bedside_now", "pacing_pads", "call_help"],
        ),
        Option(
            id="chb_ready",
            text="Obtain bedside vitals and a 12-lead while preparing transcutaneous pacing capability.",
            answer_class="ideal",
            required_safety_tokens=["twelve_lead", "tcp_ready"],
        ),
        Option(
            id="chb_atropine",
            text="Give atropine while placing pacing pads and escalating for help.",
            answer_class="acceptable",
            required_safety_tokens=["atropine", "pacing_pads", "call_help"],
        ),
        Option(id="chb_later", text="Continue telemetry and review on routine morning rounds.", answer_class="under_triage"),
        Option(id="chb_home", text="Reassure the patient that the slow rate is benign.", answer_class="unsafe"),
    ],
    steps=[
        StepwiseStep(
            prompt="Ventricular rate?",
            options=[
                StepOption(text="About 38/min (bradycardic)", correct=True),
                StepOption(text="About 80/min", correct=False),
            ],
        ),
        StepwiseStep(
            prompt="P-wave to QRS relationship?",
            options=[
                StepOption(text="AV dissociation", correct=True),
                StepOption(text="Consistent 1:1 conduction", correct=False),
            ],
        ),
    ],
    evidence_manifest=EvidenceManifest(
        ecg_supports=[
            EvidenceClaim(objective_id="av_block_third_degree", source_type="curated_label"),
            EvidenceClaim(objective_id="bradycardia", threshold="heart_rate<=50", source_type="measured"),
        ],
        stem_adds=["age 71", "inpatient", "new dizziness", "hemodynamics not yet assessed"],
        action_rationale="Complete block with symptoms requires immediate bedside stability assessment, escalation, and pacing readiness; the tracing alone does not prove shock.",
        forbidden_claims=["hemodynamic collapse", "acute myocardial infarction", "atropine will reliably work"],
        acceptable_range=["bedside assessment", "pacing readiness", "urgent escalation"],
    ),
    display_spec=DisplaySpec(mode="twelve_lead_pinned_strip", pinned_strip_lead="II", tested_scope="full_12_lead"),
)


REAL_FIRST_DEGREE_CLICK = ClinicalCaseItem(
    item_id="ptb-556-first-degree-click",
    ecg_id="556",
    situation="clinic",
    question_type="click",
    acuity_tier="low",
    stem="An asymptomatic adult has a routine pre-procedure ECG. One conduction interval is mildly prolonged.",
    chips=StemChips(age=48, setting="clinic", symptom="asymptomatic"),
    prompt="In lead II, click the prolonged interval from P-wave onset to QRS onset.",
    roi_target=RoiTarget(concept="av_block_first_degree", leads=["II"], target_type="interval"),
    evidence_manifest=EvidenceManifest(
        ecg_supports=[
            EvidenceClaim(
                objective_id="av_block_first_degree",
                threshold="pr_ms>=200",
                leads=["II"],
                roi_concept="pr_interval",
                source_type="measured",
            )
        ],
        stem_adds=["age 48", "routine pre-procedure", "asymptomatic"],
        action_rationale="Measure the PR interval before naming first-degree AV block; an isolated mild prolongation does not itself establish a pacing indication.",
        forbidden_claims=["complete heart block", "symptomatic bradycardia", "pacing indication"],
        acceptable_range=["measure PR", "first-degree AV block"],
    ),
    tested_scope="zoom_lead",
    display_spec=DisplaySpec(mode="zoom_lead", zoom_lead="II", tested_scope="zoom_lead"),
)


REAL_SVT_MCQ = ClinicalCaseItem(
    item_id="ptb-1919-svt-action",
    ecg_id="1919",
    situation="ed",
    question_type="mcq",
    acuity_tier="moderate",
    stem="A patient presents with sudden palpitations. The rhythm is regular and fast; they are alert, warm, and perfusing with BP 118/70.",
    chips=StemChips(age=55, setting="ed", symptom="palpitations", bp="118/70"),
    prompt="Which interpretation-to-action sequence is most appropriate?",
    options=[
        Option(
            id="svt_vagal",
            text="Complete the bedside stability check; if the rhythm is tolerated, recognize a regular narrow-complex SVT and use vagal manoeuvres followed by adenosine with continuous monitoring if it persists.",
            answer_class="ideal",
            required_safety_tokens=["vagal_maneuver", "adenosine", "continuous_monitoring"],
        ),
        Option(id="svt_shock", text="Perform immediate synchronized cardioversion with procedural sedation.", answer_class="over_triage_safe"),
        Option(id="svt_af", text="Treat this as irregular atrial fibrillation with diltiazem without checking the rhythm pattern.", answer_class="under_triage"),
        Option(id="svt_wait", text="Defer treatment until outpatient cardiology review.", answer_class="unsafe"),
    ],
    evidence_manifest=EvidenceManifest(
        ecg_supports=[
            EvidenceClaim(objective_id="supraventricular_tachycardia", source_type="curated_label"),
            EvidenceClaim(objective_id="rate", threshold="heart_rate>=150", source_type="measured"),
        ],
        stem_adds=["age 55", "BP 118/70", "alert", "warm and perfusing"],
        action_rationale="Bedside stability is assessed separately from the ECG; a tolerated regular narrow-complex SVT supports vagal manoeuvres followed by monitored adenosine, while instability changes the pathway.",
        forbidden_claims=["hemodynamically unstable", "irregularly irregular", "wide-complex tachycardia"],
        acceptable_range=["vagal manoeuvres", "monitored adenosine"],
    ),
    display_spec=DisplaySpec(mode="twelve_lead_pinned_strip", pinned_strip_lead="II", tested_scope="full_12_lead"),
)


REAL_ST_DEPRESSION_SPOTERROR = ClinicalCaseItem(
    item_id="ptb-11034-st-depression-spoterror",
    ecg_id="11034",
    situation="ward",
    question_type="spoterror",
    acuity_tier="moderate",
    stem="A ward patient reports intermittent chest discomfort. Audit the machine statement against the tracing before deciding what the finding means clinically.",
    chips=StemChips(age=80, setting="ward", symptom="chest_pain"),
    prompt="Select the incorrect machine line, then click trace evidence that disproves it.",
    machine_read=[
        MachineLine(id="st_line_rhythm", text="Sinus rhythm.", bad=False),
        MachineLine(id="st_line_normal", text="No significant ST-segment abnormality.", bad=True),
    ],
    roi_target=RoiTarget(concept="st_depression", leads=["V4", "V5", "V6"], target_type="segment"),
    evidence_manifest=EvidenceManifest(
        ecg_supports=[
            EvidenceClaim(
                objective_id="st_depression",
                leads=["V4", "V5", "V6"],
                roi_concept="st_segment",
                source_type="curated_label",
            )
        ],
        stem_adds=["age 80", "ward", "intermittent chest discomfort"],
        action_rationale="The machine statement must be rejected because ST depression is visible; symptoms and serial clinical data determine whether this represents acute ischemia.",
        forbidden_claims=["acute STEMI", "evolving ischemia proven by this single ECG"],
        acceptable_range=["ST depression", "clinical and serial ischemia assessment"],
    ),
    display_spec=DisplaySpec(mode="twelve_lead_machine_panel", tested_scope="full_12_lead"),
)


REAL_NORMAL_TRIAGE = ClinicalCaseItem(
    item_id="ptb-3-normal-triage",
    ecg_id="3",
    situation="clinic",
    question_type="triage",
    acuity_tier="none",
    stem="An asymptomatic adult has a routine screening ECG and no concerning history or examination findings.",
    chips=StemChips(age=24, setting="clinic", symptom="asymptomatic"),
    prompt="How should this ECG change the immediate plan?",
    options=[
        Option(id="normal_routine", text="Treat this as a normal sinus ECG and continue routine care.", answer_class="ideal", value="routine"),
        Option(id="normal_workup", text="Arrange urgent echocardiography and ambulatory rhythm monitoring before clearance.", answer_class="over_triage_safe", value="workup"),
        Option(id="normal_emergency", text="Activate an emergency response for an unstable rhythm.", answer_class="unsafe", value="act"),
    ],
    evidence_manifest=EvidenceManifest(
        ecg_supports=[
            EvidenceClaim(objective_id="normal_ecg", source_type="curated_label"),
            EvidenceClaim(objective_id="sinus_rhythm", source_type="curated_label"),
        ],
        stem_adds=["age 24", "asymptomatic", "routine screening"],
        action_rationale="Recognizing a normal sinus ECG prevents unnecessary escalation when the clinical context is also reassuring.",
        forbidden_claims=["acute arrhythmia", "acute ischemia"],
        acceptable_range=["routine care", "no ECG-driven acute work-up"],
    ),
    display_spec=DisplaySpec(mode="twelve_lead_pinned_strip", pinned_strip_lead="II", tested_scope="full_12_lead"),
)


REAL_QTC_MCQ = ClinicalCaseItem(
    item_id="ptb-28-qtc-medication",
    ecg_id="28",
    situation="clinic",
    question_type="mcq",
    acuity_tier="moderate",
    stem="A baseline ECG is obtained during medication reconciliation before starting another potentially QT-prolonging drug. The patient has no current symptoms.",
    chips=StemChips(age=58, setting="clinic", symptom="none"),
    prompt="What is the safest next step?",
    options=[
        Option(
            id="qtc_verify",
            text="Verify the QT/QTc, review interacting or QT-prolonging medicines, and check/correct relevant electrolytes before prescribing.",
            answer_class="ideal",
            required_safety_tokens=["hold_qt_drugs", "check_electrolytes"],
        ),
        Option(id="qtc_mag", text="Give IV magnesium now for torsades captured on this tracing.", answer_class="over_triage_safe"),
        Option(id="qtc_ignore", text="Ignore the interval because the patient is asymptomatic.", answer_class="unsafe"),
    ],
    evidence_manifest=EvidenceManifest(
        ecg_supports=[
            EvidenceClaim(objective_id="qtc_prolongation", threshold="qtc_ms>=480", source_type="measured")
        ],
        stem_adds=["age 58", "medication reconciliation", "asymptomatic"],
        action_rationale="A markedly prolonged QTc should be verified and used to review medicines, interactions, and electrolytes; it does not prove torsades is occurring.",
        forbidden_claims=["torsades captured", "ventricular tachycardia"],
        acceptable_range=["verify QTc", "review QT-prolonging drugs", "check electrolytes"],
    ),
    display_spec=DisplaySpec(mode="twelve_lead_pinned_strip", pinned_strip_lead="II", tested_scope="full_12_lead"),
)


REAL_RBBB_CLICK = ClinicalCaseItem(
    item_id="ptb-195-rbbb-click",
    ecg_id="195",
    situation="clinic",
    question_type="click",
    acuity_tier="low",
    stem="An asymptomatic patient has a routine ECG with a wide QRS and a right bundle branch pattern.",
    chips=StemChips(age=60, setting="clinic", symptom="asymptomatic"),
    prompt="In V1, click a QRS complex that demonstrates the widened ventricular depolarization.",
    roi_target=RoiTarget(concept="right_bundle_branch_block", leads=["V1"], target_type="segment"),
    evidence_manifest=EvidenceManifest(
        ecg_supports=[
            EvidenceClaim(objective_id="right_bundle_branch_block", leads=["V1"], roi_concept="qrs_complex", source_type="curated_label"),
            EvidenceClaim(objective_id="qrs_duration", threshold="qrs_ms>=120", source_type="measured"),
        ],
        stem_adds=["age 60", "routine ECG", "asymptomatic"],
        action_rationale="Localize the wide QRS before naming the conduction pattern; the ECG alone does not establish acuity or a pacing need.",
        forbidden_claims=["new bundle branch block", "acute myocardial infarction", "pacing indication"],
        acceptable_range=["wide QRS", "right bundle branch pattern"],
    ),
    tested_scope="zoom_lead",
    display_spec=DisplaySpec(mode="zoom_lead", zoom_lead="V1", tested_scope="zoom_lead"),
)


REAL_BRADY_CLINIC_TRIAGE = ClinicalCaseItem(
    item_id="ptb-2-brady-clinic-triage",
    ecg_id="2",
    situation="clinic",
    question_type="triage",
    acuity_tier="low",
    stem="A patient feels well at a routine visit. Pulse is regular, BP 122/74, and the medication list has not yet been reviewed.",
    chips=StemChips(age=42, setting="clinic", symptom="none", bp="122/74"),
    prompt="How should the slow rhythm change the immediate plan?",
    options=[
        Option(id="brady_review", text="Confirm the rate, review symptoms and rate-slowing medicines, and arrange routine follow-up if the assessment remains reassuring.", answer_class="ideal", value="workup"),
        Option(id="brady_ignore", text="Document a normal-rate ECG and continue without reviewing the slow pulse.", answer_class="under_triage", value="routine"),
        Option(id="brady_emergency", text="Activate an emergency pacing response immediately.", answer_class="over_triage_safe", value="act"),
    ],
    evidence_manifest=EvidenceManifest(
        ecg_supports=[
            EvidenceClaim(objective_id="bradycardia", threshold="heart_rate<=50", source_type="measured"),
            EvidenceClaim(objective_id="sinus_rhythm", source_type="curated_label"),
        ],
        stem_adds=["routine visit", "asymptomatic", "BP 122/74", "medications not yet reviewed"],
        action_rationale="Stable asymptomatic sinus bradycardia calls for confirmation and contextual review rather than an emergency response or automatic dismissal.",
        forbidden_claims=["symptomatic bradycardia", "high-grade AV block", "pacing indication"],
        acceptable_range=["confirm rate", "review symptoms and medications", "routine follow-up"],
    ),
    display_spec=DisplaySpec(mode="twelve_lead_pinned_strip", pinned_strip_lead="II", tested_scope="full_12_lead"),
)


REAL_LVH_VOLTAGE_CLICK = ClinicalCaseItem(
    item_id="ptb-138-lvh-voltage-click",
    ecg_id="138",
    situation="clinic",
    question_type="click",
    acuity_tier="low",
    stem="A primary-care ECG is reviewed during a blood-pressure assessment. The precordial voltage is prominent.",
    chips=StemChips(age=57, setting="clinic", symptom="none"),
    prompt="In V5, click a QRS complex that contributes to the high-voltage pattern.",
    roi_target=RoiTarget(concept="left_ventricular_hypertrophy", leads=["V5"], target_type="segment"),
    evidence_manifest=EvidenceManifest(
        ecg_supports=[
            EvidenceClaim(objective_id="left_ventricular_hypertrophy", threshold="sokolow_lyon_mv>=3.5", leads=["V5"], roi_concept="qrs_complex", source_type="measured")
        ],
        stem_adds=["primary-care blood-pressure assessment"],
        action_rationale="Voltage criteria are identified on the QRS complexes and then interpreted with blood pressure, body habitus, and structural context.",
        forbidden_claims=["heart failure", "hypertensive emergency", "acute ischemia"],
        acceptable_range=["high QRS voltage", "LVH voltage pattern"],
    ),
    tested_scope="zoom_lead",
    display_spec=DisplaySpec(mode="zoom_lead", zoom_lead="V5", tested_scope="zoom_lead"),
)


REAL_QT_INTERVAL_CLICK = ClinicalCaseItem(
    item_id="ptb-39-qt-interval-click",
    ecg_id="39",
    situation="clinic",
    question_type="click",
    acuity_tier="moderate",
    stem="A medication-safety review identifies a markedly prolonged repolarization measurement on the ECG.",
    chips=StemChips(age=61, setting="clinic", symptom="none"),
    prompt="In lead II, click the QT interval from QRS onset through the end of the T wave.",
    roi_target=RoiTarget(concept="qtc_prolongation", leads=["II"], target_type="interval"),
    evidence_manifest=EvidenceManifest(
        ecg_supports=[
            EvidenceClaim(objective_id="qtc_prolongation", threshold="qtc_ms>=480", leads=["II"], roi_concept="qt_segment", source_type="measured")
        ],
        stem_adds=["medication-safety review"],
        action_rationale="The QT interval must be localized and verified before medication and electrolyte decisions are made.",
        forbidden_claims=["torsades captured", "ventricular tachycardia"],
        acceptable_range=["QT interval", "verify QTc"],
    ),
    tested_scope="zoom_lead",
    display_spec=DisplaySpec(mode="zoom_lead", zoom_lead="II", tested_scope="zoom_lead"),
)


REAL_AF_WARD_STEPWISE = ClinicalCaseItem(
    item_id="ptb-330-af-ward-stepwise",
    ecg_id="330",
    situation="ward",
    question_type="stepwise",
    acuity_tier="moderate",
    stem="A telemetry rhythm is reviewed during morning rounds. The patient is comfortable, BP 126/76, and has no chest pain or dyspnea.",
    chips=StemChips(age=72, setting="ward", symptom="none", bp="126/76"),
    prompt="Interpret the rhythm sequentially, then choose the next clinical assessment.",
    options=[
        Option(id="af_assess", text="Confirm stability, review rate and contributors, and assess thromboembolic risk before choosing rate or rhythm management.", answer_class="ideal", required_safety_tokens=["anticoagulation_assessment"]),
        Option(id="af_more_blocker", text="Give an additional AV-nodal blocker immediately without checking the ventricular rate.", answer_class="unsafe"),
        Option(id="af_shock", text="Perform immediate synchronized cardioversion in this comfortable, perfusing patient.", answer_class="over_triage_safe"),
    ],
    steps=[
        StepwiseStep(prompt="Ventricular rate?", options=[StepOption(text="About 63/min", correct=True), StepOption(text="About 160/min", correct=False)]),
        StepwiseStep(prompt="Rhythm organization?", options=[StepOption(text="Irregular rhythm without consistent conducted P waves", correct=True), StepOption(text="Regular sinus rhythm with fixed PR intervals", correct=False)]),
    ],
    evidence_manifest=EvidenceManifest(
        ecg_supports=[
            EvidenceClaim(objective_id="atrial_fibrillation", source_type="curated_label"),
            EvidenceClaim(objective_id="rate", threshold="heart_rate<100", source_type="measured"),
        ],
        stem_adds=["ward telemetry review", "comfortable", "BP 126/76", "no chest pain or dyspnea"],
        action_rationale="Stable AF with a controlled ventricular rate requires clinical assessment and stroke-risk review; the ECG does not justify reflex cardioversion or more rate slowing.",
        forbidden_claims=["rapid ventricular response", "hemodynamic instability", "acute ischemia"],
        acceptable_range=["assess stability", "review contributors", "thromboembolic risk assessment"],
    ),
    display_spec=DisplaySpec(mode="twelve_lead_pinned_strip", pinned_strip_lead="II", tested_scope="full_12_lead"),
)


REAL_SLOW_AF_WARD_MCQ = ClinicalCaseItem(
    item_id="ptb-307-slow-af-medication",
    ecg_id="307",
    situation="ward",
    question_type="mcq",
    acuity_tier="low",
    stem="A hospitalized patient with a newly reviewed irregular rhythm is comfortable and perfusing. Their rate-slowing medicines and anticoagulation history are not yet available.",
    chips=StemChips(age=76, setting="ward", symptom="none"),
    prompt="What is the most appropriate next step?",
    options=[
        Option(id="slow_af_review", text="Assess symptoms and perfusion, reconcile rate-slowing medicines, and evaluate thromboembolic risk before changing therapy.", answer_class="ideal", required_safety_tokens=["anticoagulation_assessment"]),
        Option(id="slow_af_block", text="Give another rate-slowing medicine immediately.", answer_class="unsafe"),
        Option(id="slow_af_ignore", text="Ignore the rhythm because the ventricular rate is below 100/min.", answer_class="under_triage"),
    ],
    evidence_manifest=EvidenceManifest(
        ecg_supports=[
            EvidenceClaim(objective_id="atrial_fibrillation", source_type="curated_label"),
            EvidenceClaim(objective_id="rate", threshold="heart_rate<=60", source_type="measured"),
        ],
        stem_adds=["hospitalized", "comfortable and perfusing", "medication and anticoagulation history unavailable"],
        action_rationale="Slow AF should prompt bedside and medication assessment plus stroke-risk review; the ECG does not establish drug toxicity or justify further rate slowing.",
        forbidden_claims=["drug toxicity", "hemodynamic instability", "acute infarction"],
        acceptable_range=["assess perfusion", "medication reconciliation", "thromboembolic risk assessment"],
    ),
    display_spec=DisplaySpec(mode="twelve_lead_pinned_strip", pinned_strip_lead="II", tested_scope="full_12_lead"),
)


REAL_RBBB_WARD_SPOTERROR = ClinicalCaseItem(
    item_id="ptb-621-rbbb-spoterror",
    ecg_id="621",
    situation="ward",
    question_type="spoterror",
    acuity_tier="low",
    stem="A stable inpatient ECG has an automated interval summary. Audit the machine statement against the tracing.",
    chips=StemChips(age=68, setting="ward", symptom="none"),
    prompt="Select the incorrect line, then click trace evidence that disproves it.",
    machine_read=[
        MachineLine(id="rbbb_line_sinus", text="Sinus rhythm.", bad=False),
        MachineLine(id="rbbb_line_narrow", text="QRS duration is narrow and conduction is normal.", bad=True),
    ],
    roi_target=RoiTarget(concept="right_bundle_branch_block", leads=["V1", "V6"], target_type="segment"),
    evidence_manifest=EvidenceManifest(
        ecg_supports=[
            EvidenceClaim(objective_id="right_bundle_branch_block", leads=["V1"], roi_concept="qrs_complex", source_type="curated_label"),
            EvidenceClaim(objective_id="qrs_duration", threshold="qrs_ms>=120", source_type="measured"),
        ],
        stem_adds=["stable inpatient", "automated interval summary"],
        action_rationale="The QRS is wide and carries an RBBB pattern; chronicity and clinical significance require context not supplied by this tracing.",
        forbidden_claims=["new conduction disease", "acute myocardial infarction", "pacing indication"],
        acceptable_range=["wide QRS", "RBBB pattern"],
    ),
    display_spec=DisplaySpec(mode="twelve_lead_machine_panel", tested_scope="full_12_lead"),
)


REAL_LVH_WARD_SPOTERROR = ClinicalCaseItem(
    item_id="ptb-296-lvh-voltage-spoterror",
    ecg_id="296",
    situation="ward",
    question_type="spoterror",
    acuity_tier="moderate",
    stem="A ward ECG is reviewed while evaluating persistently elevated blood pressure. Audit the automated voltage statement.",
    chips=StemChips(age=65, setting="ward", symptom="none"),
    prompt="Select the incorrect machine line, then click the QRS evidence that disproves it.",
    machine_read=[
        MachineLine(id="lvh_line_sinus", text="Sinus rhythm.", bad=False),
        MachineLine(id="lvh_line_voltage", text="No voltage evidence of left ventricular hypertrophy.", bad=True),
    ],
    roi_target=RoiTarget(concept="left_ventricular_hypertrophy", leads=["V5", "V6"], target_type="segment"),
    evidence_manifest=EvidenceManifest(
        ecg_supports=[
            EvidenceClaim(objective_id="left_ventricular_hypertrophy", threshold="sokolow_lyon_mv>=3.5", leads=["V5"], roi_concept="qrs_complex", source_type="measured")
        ],
        stem_adds=["ward", "persistently elevated blood pressure"],
        action_rationale="High QRS voltage supports an LVH pattern, which should be correlated with pressure history and structural assessment rather than treated as an acute diagnosis.",
        forbidden_claims=["hypertensive emergency", "acute heart failure", "acute ischemia proven"],
        acceptable_range=["high QRS voltage", "LVH pattern", "clinical correlation"],
    ),
    display_spec=DisplaySpec(mode="twelve_lead_machine_panel", tested_scope="full_12_lead"),
)


REAL_LVH_WARD_MCQ = ClinicalCaseItem(
    item_id="ptb-299-lvh-context-mcq",
    ecg_id="299",
    situation="ward",
    question_type="mcq",
    acuity_tier="low",
    stem="An inpatient ECG shows high voltage during evaluation of longstanding hypertension. The patient is comfortable without acute cardiopulmonary symptoms.",
    chips=StemChips(age=64, setting="ward", symptom="none"),
    prompt="What is the best interpretation-to-action statement?",
    options=[
        Option(id="lvh_correlate", text="Treat this as an LVH voltage pattern: correlate with blood pressure and prior evaluation, and consider structural assessment when clinically appropriate.", answer_class="ideal"),
        Option(id="lvh_emergency", text="Treat the voltage alone as a hypertensive emergency requiring immediate IV therapy.", answer_class="unsafe"),
        Option(id="lvh_normal", text="Call the tracing normal because the rhythm is sinus.", answer_class="under_triage"),
    ],
    evidence_manifest=EvidenceManifest(
        ecg_supports=[
            EvidenceClaim(objective_id="left_ventricular_hypertrophy", threshold="sokolow_lyon_mv>=3.5", source_type="measured")
        ],
        stem_adds=["longstanding hypertension", "comfortable", "no acute cardiopulmonary symptoms"],
        action_rationale="Voltage supports an LVH pattern, not an acute blood-pressure emergency; correlate it with longitudinal and structural context.",
        forbidden_claims=["hypertensive emergency", "acute heart failure"],
        acceptable_range=["LVH voltage pattern", "blood-pressure correlation", "structural assessment when appropriate"],
    ),
    display_spec=DisplaySpec(mode="twelve_lead", tested_scope="full_12_lead"),
)


REAL_SVT_ED_STEPWISE = ClinicalCaseItem(
    item_id="ptb-1173-svt-ed-stepwise",
    ecg_id="1173",
    situation="ed",
    question_type="stepwise",
    acuity_tier="moderate",
    stem="A patient has abrupt palpitations, remains alert and well perfused, and has BP 116/72.",
    chips=StemChips(age=49, setting="ed", symptom="palpitations", bp="116/72"),
    prompt="Classify the rhythm, then choose the initial management path.",
    options=[
        Option(id="svt_step_vagal", text="Complete the bedside stability check; if the regular narrow-complex tachycardia is tolerated, use vagal manoeuvres followed by monitored adenosine if it persists.", answer_class="ideal", required_safety_tokens=["vagal_maneuver", "adenosine", "continuous_monitoring"]),
        Option(id="svt_step_shock", text="Proceed directly to synchronized cardioversion.", answer_class="over_triage_safe"),
        Option(id="svt_step_home", text="Discharge without treatment while the tachycardia continues.", answer_class="unsafe"),
    ],
    steps=[
        StepwiseStep(prompt="Approximate ventricular rate?", options=[StepOption(text="About 165/min", correct=True), StepOption(text="About 70/min", correct=False)]),
        StepwiseStep(prompt="QRS width and regularity?", options=[StepOption(text="Regular, narrow-complex tachycardia", correct=True), StepOption(text="Irregular, wide-complex rhythm", correct=False)]),
    ],
    evidence_manifest=EvidenceManifest(
        ecg_supports=[
            EvidenceClaim(objective_id="supraventricular_tachycardia", source_type="curated_label"),
            EvidenceClaim(objective_id="rate", threshold="heart_rate>=150", source_type="measured"),
        ],
        stem_adds=["abrupt palpitations", "alert and well perfused", "BP 116/72"],
        action_rationale="After bedside stability is assessed, a tolerated regular narrow-complex tachycardia supports vagal manoeuvres followed by monitored adenosine; the exact atrial mechanism may require further rhythm analysis.",
        forbidden_claims=["hemodynamic instability", "definitive AVNRT mechanism", "wide-complex tachycardia"],
        acceptable_range=["vagal manoeuvres", "monitored adenosine"],
    ),
    display_spec=DisplaySpec(mode="twelve_lead_pinned_strip", pinned_strip_lead="II", tested_scope="full_12_lead"),
)


REAL_SVT_ED_TRIAGE = ClinicalCaseItem(
    item_id="ptb-3267-svt-ed-triage",
    ecg_id="3267",
    situation="ed",
    question_type="triage",
    acuity_tier="moderate",
    stem="A patient with a sustained fast regular rhythm is alert, speaking normally, warm, and has BP 120/76.",
    chips=StemChips(age=38, setting="ed", symptom="palpitations", bp="120/76", mental_status="alert"),
    prompt="Choose the appropriate urgency and immediate pathway.",
    options=[
        Option(id="svt_triage_treat", text="Complete the bedside stability check and, if the regular narrow rhythm is tolerated, treat promptly in a monitored setting with vagal manoeuvres and adenosine if needed.", answer_class="ideal", value="workup", required_safety_tokens=["vagal_maneuver", "adenosine", "continuous_monitoring"]),
        Option(id="svt_triage_shock", text="Prepare immediate synchronized cardioversion as the first intervention.", answer_class="over_triage_safe", value="act"),
        Option(id="svt_triage_routine", text="Leave the rhythm untreated for routine outpatient follow-up.", answer_class="unsafe", value="routine"),
    ],
    evidence_manifest=EvidenceManifest(
        ecg_supports=[
            EvidenceClaim(objective_id="supraventricular_tachycardia", source_type="curated_label"),
            EvidenceClaim(objective_id="rate", threshold="heart_rate>=150", source_type="measured"),
        ],
        stem_adds=["alert", "warm", "BP 120/76", "sustained palpitations"],
        action_rationale="Bedside stability determines the branch: a tolerated regular narrow-complex tachycardia needs prompt monitored treatment, while instability requires escalation to the appropriate emergency pathway.",
        forbidden_claims=["hemodynamic instability", "wide-complex tachycardia"],
        acceptable_range=["prompt monitored treatment", "vagal manoeuvres", "adenosine"],
    ),
    display_spec=DisplaySpec(mode="twelve_lead_pinned_strip", pinned_strip_lead="II", tested_scope="full_12_lead"),
)


REAL_AF_RVR_ED_TRIAGE = ClinicalCaseItem(
    item_id="ptb-567-af-rvr-ed-triage",
    ecg_id="567",
    situation="ed",
    question_type="triage",
    acuity_tier="moderate",
    stem="A patient with palpitations is alert and perfusing with BP 124/78. No ischemic symptoms or acute heart-failure findings are provided.",
    chips=StemChips(age=67, setting="ed", symptom="palpitations", bp="124/78", mental_status="alert"),
    prompt="Choose the appropriate urgency and initial assessment path.",
    options=[
        Option(id="af_triage_assess", text="Assess contributors and contraindications, consider rate control, and evaluate thromboembolic risk in a monitored setting.", answer_class="ideal", value="workup", required_safety_tokens=["rate_control", "anticoagulation_assessment"]),
        Option(id="af_triage_shock", text="Perform immediate synchronized cardioversion based on the ECG alone.", answer_class="over_triage_safe", value="act"),
        Option(id="af_triage_home", text="Discharge without further assessment because the QRS is narrow.", answer_class="unsafe", value="routine"),
    ],
    evidence_manifest=EvidenceManifest(
        ecg_supports=[
            EvidenceClaim(objective_id="atrial_fibrillation", source_type="curated_label"),
            EvidenceClaim(objective_id="rate", threshold="heart_rate>=100", source_type="measured"),
        ],
        stem_adds=["alert and perfusing", "BP 124/78", "no ischemic or acute heart-failure findings provided"],
        action_rationale="Stable AF with a rapid response calls for contributor and contraindication assessment, appropriate rate strategy, and stroke-risk evaluation; instability would change urgency.",
        forbidden_claims=["hemodynamic instability", "acute myocardial infarction", "acute heart failure"],
        acceptable_range=["monitored assessment", "rate-control evaluation", "thromboembolic risk assessment"],
    ),
    display_spec=DisplaySpec(mode="twelve_lead_pinned_strip", pinned_strip_lead="II", tested_scope="full_12_lead"),
)


REAL_CHB_ED_TRIAGE = ClinicalCaseItem(
    item_id="ptb-959-chb-ed-triage",
    ecg_id="959",
    situation="ed",
    question_type="triage",
    acuity_tier="high",
    stem="A patient presents after dizziness and near-syncope. They are currently awake with BP 104/66; a complete bedside stability assessment is still in progress.",
    chips=StemChips(age=74, setting="ed", symptom="syncope", bp="104/66", mental_status="alert"),
    prompt="Choose the safest immediate priority.",
    options=[
        Option(id="chb_triage_act", text="Continue immediate bedside assessment, place pacing pads, evaluate reversible contributors, and escalate for pacing-capable support.", answer_class="ideal", value="act", required_safety_tokens=["bedside_now", "pacing_pads", "call_help"]),
        Option(id="chb_triage_labs", text="Wait for routine laboratory results before preparing pacing support.", answer_class="under_triage", value="workup"),
        Option(id="chb_triage_home", text="Discharge because the blood pressure is currently measurable.", answer_class="unsafe", value="routine"),
    ],
    evidence_manifest=EvidenceManifest(
        ecg_supports=[
            EvidenceClaim(objective_id="av_block_third_degree", source_type="curated_label"),
            EvidenceClaim(objective_id="rate", threshold="heart_rate<=50", source_type="measured"),
        ],
        stem_adds=["dizziness and near-syncope", "awake", "BP 104/66", "stability assessment in progress"],
        action_rationale="Complete block with concerning symptoms warrants immediate assessment, reversible-cause review, escalation, and pacing readiness without claiming shock from the ECG alone.",
        forbidden_claims=["hemodynamic collapse", "acute myocardial infarction", "permanent pacing decision already made"],
        acceptable_range=["bedside assessment", "reversible-cause review", "pacing readiness", "urgent escalation"],
    ),
    display_spec=DisplaySpec(mode="twelve_lead_pinned_strip", pinned_strip_lead="II", tested_scope="full_12_lead"),
)


REAL_ST_DEPRESSION_ED_SPOTERROR = ClinicalCaseItem(
    item_id="ptb-7806-st-depression-ed-spoterror",
    ecg_id="7806",
    situation="ed",
    question_type="spoterror",
    acuity_tier="moderate",
    stem="A patient reports chest pressure. Audit the automated statement, then interpret the ECG finding alongside symptoms and serial data.",
    chips=StemChips(age=69, setting="ed", symptom="chest_pain"),
    prompt="Select the incorrect machine line, then click trace evidence that disproves it.",
    machine_read=[
        MachineLine(id="ed_st_line_af", text="Atrial fibrillation.", bad=False),
        MachineLine(id="ed_st_line_normal", text="No ST-segment depression.", bad=True),
    ],
    roi_target=RoiTarget(concept="st_depression", leads=["V4", "V5", "V6"], target_type="segment"),
    evidence_manifest=EvidenceManifest(
        ecg_supports=[
            EvidenceClaim(objective_id="st_depression", leads=["V4", "V5", "V6"], roi_concept="st_segment", source_type="curated_label")
        ],
        stem_adds=["chest pressure", "ED"],
        action_rationale="ST depression is present, but a single tracing does not establish acuity or cause; integrate symptoms, prior ECGs when authentically available, biomarkers, and serial change.",
        forbidden_claims=["acute coronary syndrome proven", "evolving ischemia proven", "digitalis effect known"],
        acceptable_range=["ST depression", "serial and clinical ischemia assessment"],
    ),
    display_spec=DisplaySpec(mode="twelve_lead_machine_panel", tested_scope="full_12_lead"),
)


REAL_BRADY_ED_STEPWISE = ClinicalCaseItem(
    item_id="ptb-12-brady-ed-stepwise",
    ecg_id="12",
    situation="ed",
    question_type="stepwise",
    acuity_tier="low",
    stem="A patient reports lightheadedness. They are awake, warm, and have BP 108/70; medication and reversible-cause review is pending.",
    chips=StemChips(age=52, setting="ed", symptom="dizziness", bp="108/70", mental_status="alert"),
    prompt="Interpret the rhythm, then choose the next bedside plan.",
    options=[
        Option(id="brady_step_assess", text="Continue bedside stability assessment, review medicines and reversible contributors, monitor closely, and prepare escalation if perfusion worsens.", answer_class="ideal", required_safety_tokens=["bedside_now", "continuous_monitoring"]),
        Option(id="brady_step_pace", text="Begin immediate transcutaneous pacing without completing the current stability assessment.", answer_class="over_triage_safe"),
        Option(id="brady_step_home", text="Discharge without evaluating the reported lightheadedness.", answer_class="unsafe"),
    ],
    steps=[
        StepwiseStep(prompt="Approximate rate?", options=[StepOption(text="About 47/min", correct=True), StepOption(text="About 110/min", correct=False)]),
        StepwiseStep(prompt="Rhythm relationship?", options=[StepOption(text="Sinus rhythm with a P wave before each QRS", correct=True), StepOption(text="Complete AV dissociation", correct=False)]),
    ],
    evidence_manifest=EvidenceManifest(
        ecg_supports=[
            EvidenceClaim(objective_id="bradycardia", threshold="heart_rate<=50", source_type="measured"),
            EvidenceClaim(objective_id="sinus_rhythm", source_type="curated_label"),
        ],
        stem_adds=["lightheadedness", "awake and warm", "BP 108/70", "medication and reversible-cause review pending"],
        action_rationale="Sinus bradycardia plus symptoms requires bedside assessment and reversible-cause review; current data do not prove unstable perfusion or a pacing indication.",
        forbidden_claims=["complete heart block", "hemodynamic collapse", "medication toxicity established"],
        acceptable_range=["bedside assessment", "reversible-cause review", "monitoring", "escalate if perfusion worsens"],
    ),
    display_spec=DisplaySpec(mode="twelve_lead_pinned_strip", pinned_strip_lead="II", tested_scope="full_12_lead"),
)


REAL_AUTHORED_ITEMS = (
    REAL_CHB_STEPWISE,
    REAL_FIRST_DEGREE_CLICK,
    REAL_SVT_MCQ,
    REAL_ST_DEPRESSION_SPOTERROR,
    REAL_NORMAL_TRIAGE,
    REAL_QTC_MCQ,
    REAL_RBBB_CLICK,
    REAL_BRADY_CLINIC_TRIAGE,
    REAL_LVH_VOLTAGE_CLICK,
    REAL_QT_INTERVAL_CLICK,
    REAL_AF_WARD_STEPWISE,
    REAL_SLOW_AF_WARD_MCQ,
    REAL_RBBB_WARD_SPOTERROR,
    REAL_LVH_WARD_SPOTERROR,
    REAL_LVH_WARD_MCQ,
    REAL_SVT_ED_STEPWISE,
    REAL_SVT_ED_TRIAGE,
    REAL_AF_RVR_ED_TRIAGE,
    REAL_CHB_ED_TRIAGE,
    REAL_ST_DEPRESSION_ED_SPOTERROR,
    REAL_BRADY_ED_STEPWISE,
)


# Each row is a deliberately selected, distinct PTB-XL record that passes the
# evidence contract of its authored scenario family.  The first record in every
# row is the original authoring exemplar; the remaining records were selected
# from the complete checked corpus with the same objective/measurement/ROI
# requirements.  Keeping the allow-list explicit makes content review and
# rollback possible, while ``vetted_real_items`` still resolves and re-validates
# every packet at startup (so an outdated corpus cannot silently serve it).
#
# The scenarios are simulations.  The waveform is never simulated: every ECG id
# below resolves through the production packet provider to a distinct PTB record.
MINIMUM_CLINICAL_BANK_SIZE = 100
REAL_ECGS_BY_SCENARIO: dict[str, tuple[str, ...]] = {
    "ptb-8911-chb-stepwise": ("8911", "7688", "16151", "16271"),
    "ptb-556-first-degree-click": ("556", "98", "102", "167", "182"),
    "ptb-1919-svt-action": ("1919", "2051", "3134", "3476", "7796"),
    "ptb-11034-st-depression-spoterror": ("11034", "1927", "2891", "3438", "4464"),
    "ptb-3-normal-triage": ("3", "10", "14", "21", "27"),
    "ptb-28-qtc-medication": ("28", "162", "266", "281", "306"),
    "ptb-195-rbbb-click": ("195", "172", "269", "287", "310"),
    "ptb-2-brady-clinic-triage": ("2", "78", "284", "289", "543"),
    "ptb-138-lvh-voltage-click": ("138", "191", "223", "273", "277"),
    "ptb-39-qt-interval-click": ("39", "316", "320", "409", "520"),
    "ptb-330-af-ward-stepwise": ("330", "282", "318", "321", "337"),
    "ptb-307-slow-af-medication": ("307", "581", "637", "722", "731"),
    "ptb-621-rbbb-spoterror": ("621", "424", "455", "600", "635"),
    "ptb-296-lvh-voltage-spoterror": ("296", "298", "313", "501", "534"),
    "ptb-299-lvh-context-mcq": ("299", "436", "452", "537", "542"),
    "ptb-1173-svt-ed-stepwise": ("1173", "7889", "9866", "10306", "10936"),
    "ptb-3267-svt-ed-triage": ("3267", "14286", "16229", "16753", "336"),
    "ptb-567-af-rvr-ed-triage": ("567", "428", "482", "569", "608"),
    "ptb-959-chb-ed-triage": ("959", "4838", "8620", "21533"),
    "ptb-7806-st-depression-ed-spoterror": ("7806", "1178", "1524", "6594", "11849"),
    "ptb-12-brady-ed-stepwise": ("12", "568", "611", "612", "658"),
}


@dataclass(frozen=True)
class AuthoredScenarioVariant:
    """One deliberately authored encounter bound to one real ECG.

    These are not demographic suffixes.  Each row supplies a complete clinical
    framing and a distinct learner decision prompt.  Context remains explicitly
    simulated; the ECG and every ECG-derived claim remain packet-grounded.
    """

    age: int
    setting: str
    symptom: str
    stem: str
    prompt: str


def _v(age: int, setting: str, symptom: str, stem: str, prompt: str) -> AuthoredScenarioVariant:
    return AuthoredScenarioVariant(age, setting, symptom, stem, prompt)


# The authored educational families are deliberately broader than the ECG label.
# They provide a release-auditable content mix without pretending a resting PTB
# tracing contains an arrest rhythm, a treatment response, an acute time course,
# or a serial comparison.
CLINICAL_FAMILY_BY_SCENARIO: dict[str, str] = {
    "ptb-8911-chb-stepwise": "syncope_brady",
    "ptb-556-first-degree-click": "conduction",
    "ptb-1919-svt-action": "palpitations_rhythm",
    "ptb-11034-st-depression-spoterror": "chest_discomfort_claim_boundary",
    "ptb-3-normal-triage": "normal_mimic",
    "ptb-28-qtc-medication": "qt_drug_safety",
    "ptb-195-rbbb-click": "conduction",
    "ptb-2-brady-clinic-triage": "syncope_brady",
    "ptb-138-lvh-voltage-click": "chamber_voltage",
    "ptb-39-qt-interval-click": "qt_drug_safety",
    "ptb-330-af-ward-stepwise": "palpitations_rhythm",
    "ptb-307-slow-af-medication": "palpitations_rhythm",
    "ptb-621-rbbb-spoterror": "machine_audit",
    "ptb-296-lvh-voltage-spoterror": "machine_audit",
    "ptb-299-lvh-context-mcq": "chamber_voltage",
    "ptb-1173-svt-ed-stepwise": "palpitations_rhythm",
    "ptb-3267-svt-ed-triage": "palpitations_rhythm",
    "ptb-567-af-rvr-ed-triage": "palpitations_rhythm",
    "ptb-959-chb-ed-triage": "syncope_brady",
    "ptb-7806-st-depression-ed-spoterror": "chest_discomfort_claim_boundary",
    "ptb-12-brady-ed-stepwise": "syncope_brady",
}


# Only these concepts are deliberately exercised as clinical applications.  A
# rate or secondary rhythm fact may ground an item without being the management
# competency being scored.  Trace-only click/audit families intentionally map to
# no application objective and can issue only exact formative localization.
APPLICATION_OBJECTIVES_BY_SCENARIO: dict[str, tuple[str, ...]] = {
    "ptb-8911-chb-stepwise": ("av_block_third_degree",),
    "ptb-556-first-degree-click": (),
    "ptb-1919-svt-action": ("supraventricular_tachycardia",),
    "ptb-11034-st-depression-spoterror": (),
    "ptb-3-normal-triage": ("normal_ecg",),
    "ptb-28-qtc-medication": ("qtc_prolongation",),
    "ptb-195-rbbb-click": (),
    "ptb-2-brady-clinic-triage": ("bradycardia",),
    "ptb-138-lvh-voltage-click": (),
    "ptb-39-qt-interval-click": (),
    "ptb-330-af-ward-stepwise": ("atrial_fibrillation",),
    "ptb-307-slow-af-medication": ("atrial_fibrillation",),
    "ptb-621-rbbb-spoterror": (),
    "ptb-296-lvh-voltage-spoterror": (),
    "ptb-299-lvh-context-mcq": ("left_ventricular_hypertrophy",),
    "ptb-1173-svt-ed-stepwise": ("supraventricular_tachycardia",),
    "ptb-3267-svt-ed-triage": ("supraventricular_tachycardia",),
    "ptb-567-af-rvr-ed-triage": ("atrial_fibrillation",),
    "ptb-959-chb-ed-triage": ("av_block_third_degree",),
    "ptb-7806-st-depression-ed-spoterror": (),
    "ptb-12-brady-ed-stepwise": ("bradycardia",),
}


# Five authored records are supplied for every five-ECG family; the two four-ECG
# families use their first four records.  Every stem and prompt is a complete
# authoring decision, not a neutral suffix attached to a shared vignette.
AUTHORED_VARIANTS_BY_SCENARIO: dict[str, tuple[AuthoredScenarioVariant, ...]] = {
    "ptb-8911-chb-stepwise": (
        _v(71, "medical ward medication round", "dizziness", "During a ward medication round, an inpatient reports dizziness and the bedside monitor prompts review of a slow rhythm; pulse and perfusion assessment is beginning.", "Work from ventricular rate to atrioventricular relationship, then choose the bedside safety priority."),
        _v(66, "inpatient mobility assessment", "presyncope", "An inpatient mobility assessment is interrupted because of presyncope, and the ward team asks for ECG analysis while reversible contributors are being gathered.", "Sequence the rate and atrial-versus-ventricular activity before selecting the immediate ward response."),
        _v(79, "evening medical ward review", "fatigue", "At an evening ward review, an inpatient describes fatigue and a slow pulse is noted; medication exposure and bedside perfusion have not yet been reconciled.", "Identify the bradycardic conduction pattern step by step, then choose what cannot safely wait."),
        _v(74, "monitored inpatient bed", "syncope", "A monitored inpatient is being evaluated after a reported fainting episode, and this slow-rhythm ECG is available before the bedside cause assessment is complete.", "Use the ECG sequence to distinguish atrioventricular dissociation, then choose the safest preparation and escalation."),
    ),
    "ptb-556-first-degree-click": (
        _v(48, "pre-procedure clinic", "asymptomatic", "An asymptomatic adult has an ECG during elective pre-procedure review, and the automated interval summary needs manual verification.", "In lead II, mark the atrioventricular conduction interval from the start of the P wave to the start of the QRS."),
        _v(54, "medication follow-up clinic", "none", "A medication follow-up visit includes a baseline ECG with a mildly delayed atrioventricular conduction measurement.", "Locate the full PR interval in lead II rather than clicking only the P wave or QRS."),
        _v(36, "occupational health clinic", "asymptomatic", "An occupational health assessment includes a routine ECG whose conduction timing is longer than expected but causes no stated symptoms.", "Select one complete P-onset-to-QRS-onset interval in lead II."),
        _v(62, "primary care review", "none", "A primary-care clinician is checking ECG intervals before renewing medicines that can slow atrioventricular conduction.", "Show where the prolonged PR measurement should be made in lead II."),
        _v(45, "elective therapy baseline clinic", "asymptomatic", "An asymptomatic patient has a baseline tracing before an elective therapy plan, and one conduction interval requires confirmation.", "Place the marker within the PR interval bounded by P-wave onset and QRS onset in lead II."),
    ),
    "ptb-1919-svt-action": (
        _v(55, "emergency department rhythm assessment", "palpitations", "A patient with palpitations has a fast regular rhythm in the emergency department; the ECG is available while the bedside stability branch is being completed.", "Which sequence correctly combines rhythm classification, stability assessment, and conditional treatment?"),
        _v(43, "emergency department referral bay", "palpitations", "An urgent-care referral reaches the emergency department with a regular narrow-complex tachycardia requiring a fresh bedside and ECG assessment.", "Choose the plan that checks stability first and then uses the regular narrow-complex pathway."),
        _v(61, "emergency department monitored space", "lightheadedness", "A monitored emergency-department ECG shows a rapid regular rhythm in a patient reporting lightheadedness; no cause or instability is inferred from the tracing.", "Select the safest interpretation-to-action order without over-subtyping the atrial mechanism."),
        _v(29, "emergency department triage review", "palpitations", "Emergency-department triage requests a rhythm review for persistent heart racing, with bedside assessment proceeding separately from ECG interpretation.", "Which option preserves the stability fork before vagal manoeuvres or monitored medication?"),
        _v(70, "emergency department observation area", "dyspnea", "A patient in the emergency observation area reports breathlessness and has a regular narrow tachycardia on a single resting ECG.", "Choose the conditional pathway that treats the rhythm evidence without claiming the symptom's cause."),
    ),
    "ptb-11034-st-depression-spoterror": (
        _v(80, "general medical ward", "chest_pain", "A ward patient describes intermittent chest discomfort, and the team asks whether the automated ST statement matches this ECG without assigning an acute cause.", "Identify the incorrect machine line and prove the disagreement on the lateral precordial trace."),
        _v(68, "inpatient pre-procedure ward", "chest_pain", "An inpatient awaiting a non-cardiac procedure mentions episodic chest discomfort, and an automated ECG statement requires human review.", "Select the machine claim that the tracing contradicts, then mark the supporting ST segment."),
        _v(73, "respiratory ward consultation", "dyspnea", "A respiratory-ward consultation includes an ECG with a disputed repolarization statement; breathlessness is context, not a diagnosis from the tracing.", "Audit the machine text and localize the lateral ST evidence that resolves the dispute."),
        _v(59, "medical ward symptom review", "chest_pain", "During a ward symptom review, a patient reports nonspecific chest discomfort and the computer interpretation says the ST segments are normal.", "Choose the false automated line and point to the segment that makes it false."),
        _v(76, "inpatient cardiology review", "none", "An inpatient cardiology review is requested because the ECG report and visible lateral repolarization do not agree; no symptoms are supplied.", "Find the report error first, then demonstrate the relevant ST-segment region on the ECG."),
    ),
    "ptb-3-normal-triage": (
        _v(24, "preventive care clinic", "asymptomatic", "An asymptomatic adult has an ECG as part of a preventive health visit with no stated cardiopulmonary concern.", "How much immediate clinical action is justified by this tracing?"),
        _v(39, "occupational clearance clinic", "none", "An occupational clearance assessment includes a routine resting ECG and an otherwise unremarkable encounter history.", "Choose the disposition that matches a reassuring ECG without inventing hidden disease."),
        _v(31, "elective procedure clinic", "asymptomatic", "An elective procedure clinic obtains a screening ECG from a patient without reported symptoms or examination concerns.", "What is the proportionate next step based on the ECG and stated context?"),
        _v(52, "primary care wellness visit", "none", "A primary-care wellness visit includes a baseline ECG before routine risk-factor counselling; no active symptoms are reported.", "Decide whether the tracing calls for routine care, additional work-up, or emergency action."),
        _v(46, "medication baseline clinic", "asymptomatic", "An asymptomatic patient has a baseline ECG before a non-cardiac medication plan, with no concerning clinical finding provided.", "Select the immediate plan that does not over-medicalize a normal tracing."),
    ),
    "ptb-28-qtc-medication": (
        _v(58, "medication reconciliation clinic", "none", "A medication reconciliation visit is considering an additional drug with QT liability, and the baseline ECG interval needs to guide the safety review.", "What should be verified or reviewed before the medication plan proceeds?"),
        _v(64, "polypharmacy review clinic", "asymptomatic", "An asymptomatic patient attends a polypharmacy review where several medicines may affect repolarization.", "Choose the action that addresses interval accuracy, interacting drugs, and modifiable contributors."),
        _v(41, "behavioral health medication clinic", "none", "A behavioral-health medication clinic requests ECG review before adjusting a regimen that can prolong repolarization.", "Which next step uses the QTc finding without claiming a ventricular arrhythmia is present?"),
        _v(72, "antiemetic planning clinic", "none", "An outpatient treatment plan may add a QT-active antiemetic, and this ECG is available for pre-prescribing safety review.", "Select the medication-safety response appropriate to a prolonged corrected interval."),
        _v(50, "specialty pharmacy clinic", "asymptomatic", "A specialty pharmacy flags a possible QT interaction during an otherwise asymptomatic clinic review.", "What is the safest evidence-based response to the ECG before changing therapy?"),
    ),
    "ptb-195-rbbb-click": (
        _v(60, "routine cardiology clinic", "asymptomatic", "A routine cardiology ECG has a wide ventricular complex with a right-sided conduction morphology that needs trace-level confirmation.", "In V1, mark a QRS complex that demonstrates the widened ventricular depolarization."),
        _v(47, "pre-procedure assessment clinic", "none", "A pre-procedure assessment includes a wide-QRS ECG, and the reviewer wants the visible ventricular waveform rather than the machine label.", "Select the QRS region in V1 that supports the conduction description."),
        _v(65, "primary care ECG review", "asymptomatic", "A primary-care ECG review notes delayed ventricular conduction on an otherwise routine visit.", "Point to one full widened QRS complex in V1."),
        _v(38, "occupational medicine clinic", "none", "An occupational-medicine tracing contains a right-precordial conduction pattern, and manual waveform localization is requested.", "Use V1 to identify the ventricular complex that carries the conduction pattern."),
        _v(71, "medication baseline clinic", "asymptomatic", "A medication baseline visit includes an ECG with a broad QRS, prompting verification of the ventricular depolarization window.", "Click inside a representative widened QRS complex in lead V1."),
    ),
    "ptb-2-brady-clinic-triage": (
        _v(42, "routine primary care visit", "none", "A routine primary-care visit finds a slow regular pulse, and the medicine list has not yet been reconciled.", "How should the slow rhythm change today's assessment and follow-up plan?"),
        _v(57, "pre-procedure clinic", "asymptomatic", "An asymptomatic patient has a slow sinus rhythm on an elective pre-procedure ECG.", "Choose the proportionate response before deciding that the rate is benign or dangerous."),
        _v(33, "preventive medicine clinic", "fatigue", "A preventive-medicine patient mentions fatigue and has a slow rhythm; the ECG alone cannot assign the symptom's cause.", "What review is appropriate before routine follow-up is considered sufficient?"),
        _v(69, "medication monitoring clinic", "none", "A medication-monitoring visit identifies bradycardia before rate-slowing medicines have been checked.", "Select the plan that verifies symptoms and medication contributors without triggering an unsupported emergency response."),
        _v(51, "general internal medicine clinic", "asymptomatic", "An asymptomatic adult has a slow but organized rhythm during a general medicine follow-up.", "Decide what immediate review and safety-netting the tracing warrants."),
    ),
    "ptb-138-lvh-voltage-click": (
        _v(57, "blood-pressure assessment clinic", "none", "A blood-pressure assessment includes an ECG with prominent left-precordial voltage requiring manual verification.", "In V5, identify a QRS complex that contributes to the voltage criterion."),
        _v(63, "primary care risk review", "asymptomatic", "A primary-care cardiovascular risk review notes high precordial voltage on the resting ECG.", "Mark the ventricular complex in V5 used for the voltage assessment."),
        _v(45, "preventive cardiology clinic", "none", "A preventive cardiology visit includes a high-voltage ECG but no structural imaging information.", "Select one V5 QRS complex that supplies the lateral voltage measurement."),
        _v(70, "hypertension follow-up clinic", "none", "A hypertension follow-up includes manual verification of the waveform evidence behind an automated voltage statement.", "Point to the relevant high-amplitude QRS in lead V5."),
        _v(52, "general medicine clinic", "asymptomatic", "A general-medicine ECG shows prominent lateral precordial voltage during an otherwise routine encounter.", "Click a representative V5 ventricular complex used in the voltage pattern."),
    ),
    "ptb-39-qt-interval-click": (
        _v(61, "medication safety clinic", "none", "A medication-safety review requires direct verification of a long ventricular repolarization interval on the ECG.", "In lead II, mark the QT interval from QRS onset through T-wave end."),
        _v(49, "behavioral health prescribing clinic", "asymptomatic", "A prescribing clinic requests an ECG interval check before changing a QT-active medicine.", "Select the complete QRS-onset-to-T-end interval in lead II."),
        _v(73, "polypharmacy clinic", "none", "A polypharmacy assessment includes an ECG whose repolarization timing should be measured rather than accepted from the machine.", "Locate one full QT interval in lead II."),
        _v(36, "antiemetic planning clinic", "asymptomatic", "An outpatient antiemetic plan prompts manual review of ventricular depolarization-plus-repolarization timing.", "Place the click within the QT measurement window in lead II, ending at T-wave completion."),
        _v(66, "specialty medication review", "none", "A specialty medication review flags a prolonged ECG interval and asks for trace-level confirmation.", "Demonstrate the QT interval boundaries on a representative beat in lead II."),
    ),
    "ptb-330-af-ward-stepwise": (
        _v(72, "morning medical ward round", "none", "A morning ward round notes an irregular pulse, and the team asks for a structured ECG review before medicines or stroke risk are discussed.", "Determine ventricular rate and atrial organization, then choose the next clinical assessment."),
        _v(78, "inpatient medication reconciliation", "asymptomatic", "During inpatient medication reconciliation, an irregular rhythm is found on the admission ECG and the current rate-control history is incomplete.", "Build the rhythm interpretation in sequence before selecting the medication and thromboembolic review."),
        _v(65, "ward discharge planning", "none", "A ward discharge-planning review includes an irregular ECG that has not yet been reconciled with the outpatient medicine list.", "Use rate and rhythm organization to decide what must be assessed before discharge planning continues."),
        _v(69, "general medicine ward consultation", "dyspnea", "A general-medicine inpatient reports breathlessness and has an irregular rhythm; the symptom remains context rather than an ECG-proven cause.", "Classify the rhythm stepwise, then choose a clinical assessment that preserves uncertainty about symptoms."),
        _v(83, "overnight ward ECG review", "none", "An overnight ward ECG is obtained after staff notice an irregular pulse, before the medicine list and rhythm history have been reconciled.", "Estimate rate, evaluate atrial organization, and select the safest next information-gathering step."),
    ),
    "ptb-307-slow-af-medication": (
        _v(76, "medical ward medication review", "none", "A ward medication review finds an irregular rhythm with a controlled ventricular response; rate-slowing medicines and anticoagulation history remain unreconciled.", "What should be assessed before changing rhythm or rate therapy?"),
        _v(70, "inpatient transfer review", "asymptomatic", "An inpatient transfer note includes an irregular ECG, but the receiving team has not yet confirmed symptoms, medicines, or thromboembolic history.", "Choose the next step that avoids both reflex rate slowing and dismissal of the rhythm."),
        _v(81, "ward pharmacy consultation", "none", "A ward pharmacist asks whether another rate-slowing dose is appropriate for a patient whose ECG is irregular but not fast.", "Which response best integrates the ventricular rate with medication and stroke-risk review?"),
        _v(67, "inpatient discharge medication check", "none", "A discharge medication check identifies an irregular rhythm and an incomplete record of rate-control exposure.", "Select the action that reconciles rate, symptoms, medicines, and thromboembolic risk."),
        _v(74, "general medicine ward round", "fatigue", "A general-medicine inpatient reports fatigue and has a slow irregular rhythm, without evidence that the ECG explains the symptom.", "What is the proportionate clinical review before therapy is intensified or the finding is ignored?"),
    ),
    "ptb-621-rbbb-spoterror": (
        _v(68, "inpatient admission ECG audit", "none", "An admission ECG has a broad QRS, but the automated interval panel reports normal ventricular conduction.", "Select the incorrect report line and mark the QRS evidence that contradicts it."),
        _v(59, "ward pre-procedure review", "asymptomatic", "A ward pre-procedure review finds disagreement between the visible right-precordial waveform and the machine summary.", "Audit the conduction statement, then localize proof in V1."),
        _v(75, "medical ward consultant review", "none", "A medical consultant reviews an inpatient ECG because the automated QRS summary appears inconsistent with the tracing.", "Choose the false machine statement and point to the representative ventricular complex."),
        _v(44, "inpatient medication baseline review", "none", "An inpatient medication baseline ECG carries a normal-QRS machine label despite a visibly broad conduction pattern.", "Identify the reporting error and demonstrate the trace region that resolves it."),
        _v(63, "general ward ECG quality check", "asymptomatic", "A general ward quality check compares an automated interval readout with the right-precordial leads.", "Find the incorrect interval claim, then click the QRS morphology supporting your correction."),
    ),
    "ptb-296-lvh-voltage-spoterror": (
        _v(65, "ward blood-pressure review", "none", "A ward blood-pressure review includes an ECG whose automated report says that voltage criteria are absent.", "Select the incorrect voltage statement and demonstrate the lateral QRS evidence."),
        _v(71, "general medicine admission audit", "asymptomatic", "A general-medicine admission ECG shows prominent precordial voltage that conflicts with the machine summary.", "Audit the machine line, then point to the QRS region supporting the correction."),
        _v(56, "inpatient risk-factor review", "none", "An inpatient cardiovascular risk review asks whether the automated low-voltage conclusion fits the tracing.", "Choose the report error and localize the high-voltage ventricular complex."),
        _v(62, "ward pre-procedure ECG check", "none", "A ward pre-procedure ECG check finds that the visible V5 voltage and the automated statement do not agree.", "Identify the false statement and mark the trace evidence in V5."),
        _v(77, "inpatient consultant ECG review", "asymptomatic", "An inpatient consultant reviews a high-amplitude precordial ECG after the computer fails to include the voltage pattern.", "Select the machine error, then show the ventricular waveform that disproves it."),
    ),
    "ptb-299-lvh-context-mcq": (
        _v(64, "medical ward blood-pressure evaluation", "none", "An inpatient ECG has high precordial voltage during evaluation of a longstanding blood-pressure problem, without acute cardiopulmonary symptoms.", "Which statement best separates an ECG voltage pattern from a definitive structural diagnosis?"),
        _v(58, "ward chronic-risk review", "asymptomatic", "A ward chronic-risk review notes prominent voltage on the resting ECG and no echocardiographic information.", "Choose the interpretation-to-action statement that calls for appropriate clinical correlation."),
        _v(72, "inpatient medication planning", "none", "An inpatient medication plan includes review of a high-voltage ECG before outpatient follow-up is arranged.", "What is the most defensible use of the voltage finding?"),
        _v(49, "ward pre-procedure assessment", "none", "A ward pre-procedure assessment identifies an ECG voltage criterion but supplies no evidence of an acute pressure complication.", "Select the response that neither ignores the criterion nor treats voltage alone as an emergency."),
        _v(67, "general medicine discharge review", "asymptomatic", "A general-medicine discharge review includes a high-voltage ECG and an incomplete record of prior structural assessment.", "How should the finding be communicated and followed up without overstating anatomy?"),
    ),
    "ptb-1173-svt-ed-stepwise": (
        _v(49, "emergency department rhythm bay", "palpitations", "A patient with palpitations has a regular fast rhythm in the emergency department while bedside stability assessment proceeds independently of the ECG read.", "Classify rate, width, and regularity, then choose the conditional management branch."),
        _v(35, "emergency department monitored assessment", "lightheadedness", "A monitored emergency-department ECG shows a rapid narrow rhythm in a patient reporting lightheadedness, without an ECG basis for declaring instability.", "Build the rhythm description before deciding what stability information controls treatment."),
        _v(62, "emergency department referral review", "palpitations", "An emergency referral arrives with a regular narrow tachycardia and no documented response to prior manoeuvres or medicines.", "Estimate the rate, confirm width and regularity, and select the assessment-first pathway."),
        _v(28, "emergency department triage room", "palpitations", "A patient reporting heart racing has a regular tachycardia on the triage ECG; no atrial mechanism beyond the tracing is assumed.", "Work through the rhythm matrix, then choose the safest conditional first-line plan."),
        _v(73, "emergency observation unit", "dyspnea", "An emergency observation ECG shows a rapid regular narrow-complex rhythm in a patient with breathlessness, whose cause remains undetermined.", "Use rate and QRS organization to guide the next branch without attributing the symptom to the ECG alone."),
    ),
    "ptb-3267-svt-ed-triage": (
        _v(38, "emergency department triage", "palpitations", "Emergency-department triage identifies a sustained regular tachycardia and requests an ECG-guided priority while bedside stability is assessed.", "Choose the urgency pathway that starts with stability and preserves monitored treatment options."),
        _v(46, "emergency department fast-track review", "lightheadedness", "A fast-track emergency review includes a regular narrow tachycardia in a patient with lightheadedness; the ECG does not establish perfusion status.", "Which triage choice is prompt but does not assume the unstable branch?"),
        _v(57, "emergency department rhythm station", "palpitations", "An emergency rhythm station receives a patient with persistent palpitations and a regular rapid tracing, before treatment has been given.", "Select the immediate pathway that separates rhythm evidence from the stability decision."),
        _v(31, "emergency department assessment area", "palpitations", "A patient in the emergency assessment area has a regular narrow-complex tachycardia on a single ECG.", "How urgent is the monitored evaluation, and what conditional first-line route is appropriate?"),
        _v(69, "emergency department observation", "dyspnea", "The emergency observation team asks for triage of a regular rapid rhythm in a patient reporting breathlessness, with no cause assigned.", "Choose the response that obtains stability information and treats a tolerated rhythm through the appropriate monitored pathway."),
    ),
    "ptb-567-af-rvr-ed-triage": (
        _v(67, "emergency department rhythm evaluation", "palpitations", "A patient with palpitations has a fast irregular rhythm on the emergency-department ECG; contributors, contraindications, and stability still require bedside assessment.", "Choose the initial assessment path before selecting rate or rhythm treatment."),
        _v(74, "emergency department referral bay", "dyspnea", "An emergency referral includes a rapid irregular ECG in a patient reporting breathlessness, without evidence that the rhythm is the sole cause.", "Which triage option addresses stability, contributors, rate strategy, and thromboembolic risk?"),
        _v(52, "emergency department monitored room", "lightheadedness", "A monitored emergency-department ECG shows an irregular tachycardia in a patient with lightheadedness; no ischemic or heart-failure conclusion is supplied.", "Select the proportionate monitored work-up rather than reflex shock or discharge."),
        _v(63, "emergency department triage assessment", "palpitations", "Emergency triage notes a fast irregular pulse and obtains a resting ECG before medication exposure and stroke-risk history are reconciled.", "What information and treatment considerations belong in the first clinical branch?"),
        _v(79, "emergency observation area", "none", "An emergency observation ECG is irregular and fast, while the chart lacks a confirmed rate-control regimen or anticoagulation history.", "Choose the immediate review that the ECG supports without inferring instability from rate alone."),
    ),
    "ptb-959-chb-ed-triage": (
        _v(74, "emergency department triage", "presyncope", "A patient reports presyncope and has a markedly slow conduction rhythm on the emergency ECG while bedside assessment and reversible-cause review begin.", "Choose the immediate safety priority without waiting for a complete diagnostic work-up."),
        _v(68, "emergency department monitored bay", "dizziness", "An emergency-department monitored bay evaluates dizziness with a slow atrioventricular dissociation pattern; the resting ECG does not establish collapse.", "Which response provides bedside assessment, pacing readiness, and escalation?"),
        _v(81, "emergency department monitored assessment", "syncope", "A monitored emergency assessment follows a reported fainting episode, and the ECG shows severe conduction disease before a cause has been assigned.", "Select what must happen now while medicines and reversible contributors are investigated."),
        _v(59, "emergency department rhythm review", "lightheadedness", "An emergency rhythm review is requested for lightheadedness and profound bradycardic conduction on a resting ECG.", "Choose the safest priority that does not mistake the ECG for proof of hemodynamic collapse."),
    ),
    "ptb-7806-st-depression-ed-spoterror": (
        _v(69, "emergency department chest discomfort review", "chest_pain", "A patient reports chest pressure in the emergency department, and the computer states that no ST depression is present on this resting ECG.", "Identify the incorrect machine statement and localize the lateral ST evidence, without declaring acuity."),
        _v(56, "emergency department symptom assessment", "chest_pain", "An emergency symptom assessment includes chest discomfort and an ECG report that conflicts with the visible lateral ST segments.", "Select the report error, then prove it on the trace while keeping cause undetermined."),
        _v(72, "emergency department dyspnea evaluation", "dyspnea", "A patient evaluated for breathlessness has an ECG with a disputed ST-segment statement; the tracing alone cannot assign the symptom's cause.", "Audit the automated interpretation and point to the repolarization evidence that needs clinical correlation."),
        _v(63, "emergency department referral review", "chest_pain", "An emergency referral for nonspecific chest discomfort arrives with an automated normal-ST statement that requires over-reading.", "Choose the false line and mark the ST depression visible in contiguous lateral leads."),
        _v(78, "emergency observation ECG audit", "none", "An emergency observation ECG is sent for audit because the machine report and lateral ST morphology disagree, with no symptom history supplied.", "Resolve the machine disagreement on the trace and state only the finding the ECG supports."),
    ),
    "ptb-12-brady-ed-stepwise": (
        _v(52, "emergency department bedside review", "lightheadedness", "A patient reports lightheadedness and has a slow organized rhythm; medicine exposure, reversible contributors, and bedside stability are still being assessed.", "Estimate rate, verify the atrial-to-ventricular relationship, then choose the next bedside plan."),
        _v(64, "emergency department assessment room", "dizziness", "An emergency assessment room requests review of a slow ECG in a patient with dizziness, without evidence of atrioventricular dissociation or collapse.", "Work through rate and rhythm organization before deciding on monitoring and reversible-cause review."),
        _v(47, "emergency department medication review", "none", "An emergency medication review finds sinus bradycardia before the current rate-slowing regimen has been confirmed.", "Classify the slow rhythm, then select the action that gathers the missing clinical information."),
        _v(70, "emergency observation unit", "fatigue", "An emergency observation patient reports fatigue and has a slow sinus rhythm, with no basis to assign the symptom's cause from the ECG.", "Use the rhythm sequence to choose a proportionate assessment rather than immediate pacing or dismissal."),
        _v(58, "emergency department triage review", "presyncope", "Emergency triage obtains a slow-rhythm ECG after a report of presyncope, while perfusion and reversible causes are evaluated at the bedside.", "Determine whether atrial activity conducts normally, then choose the safest monitoring and escalation plan."),
    ),
}


_OLD_NEUTRAL_CLONE_MARKERS = (
    "treat the tracing as a single time point",
    "only the history stated here",
    "only the bedside details stated here",
    "only the stability details stated here",
    "no additional hemodynamic or longitudinal data are supplied",
    "no treatment response or additional hemodynamic data are supplied",
)


_RATE_TEXT = re.compile(r"\bAbout\s+\d+\s*/min\b", re.IGNORECASE)


def _materialize_authored_case(
    template: ClinicalCaseItem,
    ecg_id: str,
    ordinal: int,
    packet: dict[str, Any],
) -> ClinicalCaseItem:
    """Bind one authored scenario family to one reviewed real ECG packet.

    Numeric rate choices are packet-derived so an authored stepwise case never
    carries another tracing's rate.  Stem, chips, and decision prompt come from
    the ECG's own authored scenario record rather than a shared neutral suffix.
    """

    prefix = f"ptb-{template.ecg_id}-"
    slug = template.item_id[len(prefix):] if template.item_id.startswith(prefix) else template.item_id
    item_id = template.item_id if ecg_id == template.ecg_id else f"ptb-{ecg_id}-{slug}"
    variants = AUTHORED_VARIANTS_BY_SCENARIO.get(template.item_id) or ()
    if ordinal >= len(variants):
        raise RuntimeError(
            f"{template.item_id}: ECG ordinal {ordinal} has no complete authored scenario variant."
        )
    variant = variants[ordinal]
    item = template.model_copy(
        deep=True,
        update={
            "item_id": item_id,
            "ecg_id": ecg_id,
            "stem": variant.stem,
            "prompt": variant.prompt,
            "chips": StemChips(
                age=variant.age,
                setting=variant.setting,
                symptom=variant.symptom,
            ),
            "application_objectives": list(
                APPLICATION_OBJECTIVES_BY_SCENARIO.get(template.item_id, ())
            ),
        },
    )
    # Replace exemplar-specific facts (including its age/vitals) with the exact
    # authored facts for this encounter.  The entire simulated context is stored
    # as one source-labelled fact so the evidence boundary remains inspectable.
    item.evidence_manifest.stem_adds = [
        f"authored age {variant.age}",
        f"authored setting: {variant.setting}",
        f"authored symptom: {variant.symptom}",
        f"authored vignette: {variant.stem}",
    ]

    rate = ((packet.get("ptbxl_plus") or {}).get("features") or {}).get("heart_rate")
    if rate is not None:
        rounded_rate = int(round(float(rate)))
        distractor_rate = 70 if rounded_rate >= 120 else (110 if rounded_rate < 60 else 150)
        for step in item.steps:
            if "rate" not in step.prompt.casefold():
                continue
            for option in step.options:
                replacement = rounded_rate if option.correct else distractor_rate
                option.text = _RATE_TEXT.sub(f"About {replacement}/min", option.text)
    return item


def normalized_scenario_signature(item: ClinicalCaseItem) -> str:
    """Return an ID- and number-insensitive signature for clone detection.

    ECG ids, item ids, and demographic numbers are intentionally excluded.  A
    bank reaches 100 signatures only when its clinical framing or learner task
    differs semantically, not because the bound record or patient age changed.
    """

    def norm(value: str | None) -> str:
        text = re.sub(r"\d+(?:\.\d+)?", "#", value or "")
        text = re.sub(r"[^a-z#]+", " ", text.casefold())
        return " ".join(text.split())

    payload = {
        "situation": item.situation,
        "questionType": item.question_type,
        "stem": norm(item.stem),
        "setting": norm(item.chips.setting),
        "symptom": item.chips.symptom,
        "prompt": norm(item.prompt),
        "options": [norm(option.text) for option in item.options],
        "steps": [
            {
                "prompt": norm(step.prompt),
                "options": [norm(option.text) for option in step.options],
            }
            for step in item.steps
        ],
        "machineRead": [norm(line.text) for line in item.machine_read],
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def vetted_real_items(packet_provider: PacketProvider) -> list[ClinicalCaseItem]:
    """Resolve, provenance-check, and harness-check the complete authored bank.

    Startup fails instead of silently degrading when an authored item loses its
    packet or no longer passes the deterministic checks.  That makes the bank a
    release assertion rather than a best-effort content import.
    """

    family_ids = {template.item_id for template in REAL_AUTHORED_ITEMS}
    configured_ids = set(REAL_ECGS_BY_SCENARIO)
    if family_ids != configured_ids:
        missing = sorted(family_ids - configured_ids)
        unknown = sorted(configured_ids - family_ids)
        raise RuntimeError(
            f"Clinical scenario/ECG allow-list mismatch (missing={missing}, unknown={unknown})."
        )
    for contract_name, mapping in (
        ("authored variants", AUTHORED_VARIANTS_BY_SCENARIO),
        ("clinical families", CLINICAL_FAMILY_BY_SCENARIO),
        ("application objectives", APPLICATION_OBJECTIVES_BY_SCENARIO),
    ):
        mapping_ids = set(mapping)
        if mapping_ids != family_ids:
            raise RuntimeError(
                f"Clinical {contract_name} mapping mismatch "
                f"(missing={sorted(family_ids - mapping_ids)}, "
                f"unknown={sorted(mapping_ids - family_ids)})."
            )
    for scenario_id, ecg_ids in REAL_ECGS_BY_SCENARIO.items():
        variants = AUTHORED_VARIANTS_BY_SCENARIO[scenario_id]
        if len(variants) != len(ecg_ids):
            raise RuntimeError(
                f"{scenario_id}: {len(ecg_ids)} ECGs require exactly {len(ecg_ids)} "
                f"authored variants, found {len(variants)}."
            )

    all_ecg_ids = [
        ecg_id
        for template in REAL_AUTHORED_ITEMS
        for ecg_id in REAL_ECGS_BY_SCENARIO[template.item_id]
    ]
    if len(all_ecg_ids) < MINIMUM_CLINICAL_BANK_SIZE:
        raise RuntimeError(
            f"Clinical authored bank has {len(all_ecg_ids)} ECGs; "
            f"at least {MINIMUM_CLINICAL_BANK_SIZE} distinct real ECGs are required."
        )
    duplicate_ecgs = sorted(
        {ecg_id for ecg_id in all_ecg_ids if all_ecg_ids.count(ecg_id) > 1},
        key=lambda value: int(value),
    )
    if duplicate_ecgs:
        raise RuntimeError(
            f"Clinical authored bank reuses PTB ECG id(s): {duplicate_ecgs}."
        )

    ready: list[ClinicalCaseItem] = []
    failures: list[str] = []
    for template in REAL_AUTHORED_ITEMS:
        for ordinal, ecg_id in enumerate(REAL_ECGS_BY_SCENARIO[template.item_id]):
            packet = packet_provider(ecg_id)
            if packet is None:
                failures.append(
                    f"{template.item_id}: no grounded packet for configured ECG {ecg_id!r}."
                )
                continue
            item = _materialize_authored_case(template, ecg_id, ordinal, packet)
            try:
                packet = assert_learner_item_provenance(item, packet_provider)
            except RuntimeError as exc:
                failures.append(str(exc))
                continue
            report = run_harness(item, packet, None)
            if not report.passed:
                failures.append(
                    f"{item.item_id}: failed checks {', '.join(report.failing_checks())}"
                )
                continue
            item.validation_status = "harness_pass"
            ready.append(item)
    if failures:
        raise RuntimeError("Clinical authored bank failed startup validation: " + "; ".join(failures))
    if len(ready) < MINIMUM_CLINICAL_BANK_SIZE or len({item.ecg_id for item in ready}) != len(ready):
        raise RuntimeError("Clinical authored bank did not preserve its minimum distinct-real-ECG contract.")
    clone_marker_hits = [
        item.item_id
        for item in ready
        if any(marker in f"{item.stem} {item.prompt}".casefold() for marker in _OLD_NEUTRAL_CLONE_MARKERS)
    ]
    if clone_marker_hits:
        raise RuntimeError(
            "Clinical authored bank still contains neutral clone framing: "
            + ", ".join(clone_marker_hits)
        )
    signatures = {normalized_scenario_signature(item) for item in ready}
    if len(signatures) < MINIMUM_CLINICAL_BANK_SIZE:
        raise RuntimeError(
            f"Clinical authored bank has only {len(signatures)} normalized scenario signatures; "
            f"at least {MINIMUM_CLINICAL_BANK_SIZE} are required."
        )
    return ready
