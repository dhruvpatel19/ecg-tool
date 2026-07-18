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

from ..ontology import concept_label
from .harness import run_harness
from .provenance import assert_learner_item_provenance
from .schemas import (
    ClinicalDataPoint,
    ClinicalCaseItem,
    DisplaySpec,
    EvidenceClaim,
    EvidenceManifest,
    FillInTask,
    MachineLine,
    MatchingChoice,
    MatchingRow,
    MatchingTask,
    Option,
    RoiTarget,
    StemChips,
    StepCompetency,
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
    stem="During a ward medication round, an inpatient reports dizziness and nearly fainting while walking. No pulse or blood-pressure assessment has yet been recorded.",
    chips=StemChips(age=71, setting="inpatient", symptom="dizziness"),
    prompt="Determine ventricular rate and atrioventricular relationship, then choose the most appropriate bedside response.",
    options=[
        Option(
            id="chb_bedside",
            text="Assess pulse, blood pressure, and perfusion now; apply pacing pads and obtain urgent senior or cardiology support.",
            answer_class="ideal",
            required_safety_tokens=["bedside_now", "pacing_pads", "call_help"],
        ),
        Option(
            id="chb_ready",
            text="Obtain bedside vital signs and a repeat 12-lead while preparing monitored transcutaneous pacing capability and urgent escalation.",
            answer_class="ideal",
            required_safety_tokens=["twelve_lead", "tcp_ready"],
        ),
        Option(
            id="chb_atropine",
            text="Give atropine as a monitored temporizing trial while applying pacing pads and arranging pacing-capable specialist support.",
            answer_class="acceptable",
            required_safety_tokens=["atropine", "pacing_pads", "call_help"],
        ),
        Option(
            id="chb_later",
            text="Continue telemetry, review rate-slowing medicines and electrolytes, and request a scheduled cardiology review later today.",
            answer_class="under_triage",
        ),
        Option(
            id="chb_home",
            text="Treat possible volume depletion with IV fluid, repeat the ECG after symptoms settle, and pursue conduction evaluation only if bradycardia persists.",
            answer_class="unsafe",
        ),
    ],
    steps=[
        StepwiseStep(
            stage_kind="ecg",
            stage_title="Estimate the ventricular rate",
            competencies=[
                StepCompetency(objective_id="rate", subskill="measure"),
            ],
            prompt="Ventricular rate?",
            options=[
                StepOption(text="About 38/min", correct=True),
                StepOption(text="About 55/min", correct=False),
                StepOption(text="About 75/min", correct=False),
            ],
        ),
        StepwiseStep(
            stage_kind="ecg",
            stage_title="Classify atrioventricular conduction",
            competencies=[
                StepCompetency(
                    objective_id="av_block_third_degree",
                    subskill="discriminate",
                ),
            ],
            prompt="P-wave to QRS relationship?",
            options=[
                StepOption(text="Independent atrial and ventricular activity (AV dissociation)", correct=True),
                StepOption(text="Progressive PR lengthening before a dropped QRS", correct=False),
                StepOption(text="Fixed PR intervals with intermittent nonconducted P waves", correct=False),
            ],
        ),
    ],
    evidence_manifest=EvidenceManifest(
        ecg_supports=[
            EvidenceClaim(objective_id="av_block_third_degree", source_type="curated_label"),
            EvidenceClaim(objective_id="bradycardia", threshold="heart_rate<=50", source_type="measured"),
            EvidenceClaim(objective_id="rate", threshold="heart_rate<=50", source_type="measured"),
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
    stem="A patient presents with persistent palpitations. They are alert, warm, and perfusing with BP 118/70 while the first 12-lead ECG is reviewed.",
    chips=StemChips(age=55, setting="ed", symptom="palpitations", bp="118/70"),
    prompt="Which interpretation-to-action sequence best integrates the ECG with the bedside assessment?",
    options=[
        Option(
            id="svt_vagal",
            text="Reassess perfusion and QRS width; for a tolerated regular narrow-complex tachycardia, attempt vagal manoeuvres, then monitored adenosine if needed.",
            answer_class="ideal",
            required_safety_tokens=["vagal_maneuver", "adenosine", "continuous_monitoring"],
        ),
        Option(
            id="svt_shock",
            text="Prepare procedural sedation and synchronized cardioversion now, followed by monitored observation and evaluation for a precipitating cause.",
            answer_class="over_triage_safe",
        ),
        Option(
            id="svt_af",
            text="Start a titrated oral beta-blocker for suspected sinus tachycardia, obtain targeted laboratory studies, and reassess after treating possible triggers.",
            answer_class="under_triage",
        ),
        Option(
            id="svt_wait",
            text="Observe briefly for spontaneous conversion, then arrange ambulatory monitoring and next-day cardiology review with symptom-based return precautions.",
            answer_class="unsafe",
        ),
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
    prompt="Which disposition is best supported by the tracing and the current clinical context?",
    options=[
        Option(
            id="normal_routine",
            text="Verify lead placement and the clinical history, then continue the planned visit without adding an ECG-driven acute work-up.",
            answer_class="ideal",
            value="routine",
        ),
        Option(
            id="normal_workup",
            text="Arrange same-day echocardiography and ambulatory monitoring, and postpone the planned activity until occult structural or intermittent rhythm disease is excluded.",
            answer_class="over_triage_safe",
            value="workup",
        ),
        Option(
            id="normal_emergency",
            text="Activate monitored emergency transfer and begin empiric antithrombotic treatment while repeat ECGs and cardiac biomarkers are obtained.",
            answer_class="unsafe",
            value="act",
        ),
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
    stem="A baseline ECG is obtained during medication reconciliation before adding a drug with repolarization liability. The patient has no current symptoms.",
    chips=StemChips(age=58, setting="clinic", symptom="none"),
    prompt="Which prescribing plan best uses the ECG finding and the available clinical information?",
    options=[
        Option(
            id="qtc_verify",
            text="Manually verify QT/QTc, hold the new QT-active prescription, reconcile interacting medicines, and check potassium, magnesium, and renal function.",
            answer_class="ideal",
            required_safety_tokens=["hold_qt_drugs", "check_electrolytes"],
        ),
        Option(
            id="qtc_mag",
            text="Place the patient in monitored observation, give IV magnesium, and obtain urgent cardiology input for prophylaxis against a malignant ventricular rhythm.",
            answer_class="over_triage_safe",
        ),
        Option(
            id="qtc_ignore",
            text="Proceed with the planned drug at a reduced dose, schedule an outpatient ECG after steady state, and advise prompt review for palpitations.",
            answer_class="unsafe",
        ),
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
    stem="A patient feels well at a routine visit. BP is 122/74, and the medication list has not yet been reconciled when the ECG becomes available.",
    chips=StemChips(age=42, setting="clinic", symptom="none", bp="122/74"),
    prompt="Which response is proportionate after interpreting the tracing in this clinical context?",
    options=[
        Option(
            id="brady_review",
            text="Confirm the rhythm and rate, review exertional symptoms and rate-slowing medicines, and arrange follow-up if the assessment remains reassuring.",
            answer_class="ideal",
            value="workup",
        ),
        Option(
            id="brady_ignore",
            text="Continue the visit, document the ECG for future comparison, and ask the patient to report exercise intolerance, presyncope, or syncope.",
            answer_class="under_triage",
            value="routine",
        ),
        Option(
            id="brady_emergency",
            text="Send the patient for monitored emergency evaluation and transcutaneous-pacing readiness while a reversible-cause and conduction assessment is completed.",
            answer_class="over_triage_safe",
            value="act",
        ),
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


REAL_QT_INTERVAL_FILLIN = ClinicalCaseItem(
    item_id="ptb-320-qt-interval-fillin",
    ecg_id="320",
    situation="clinic",
    question_type="fillin",
    acuity_tier="moderate",
    stem="A medication-safety review requires a manual QT estimate before the interval is interpreted clinically.",
    chips=StemChips(age=73, setting="clinic", symptom="none"),
    prompt=(
        "Using the ECG grid in lead II, estimate the raw QT interval from QRS onset "
        "through the end of the T wave. Enter the closest value."
    ),
    fill_in_task=FillInTask(
        response_label="Estimated QT interval",
        unit="ms",
        objective_id="qtc_prolongation",
        expected_feature="qt_ms",
        tolerance=40,
        min_value=200,
        max_value=800,
        step=10,
    ),
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
    stem="A telemetry alert prompts ECG review during morning rounds. The patient is comfortable, BP 126/76, and has no chest pain or dyspnea.",
    chips=StemChips(age=72, setting="ward", symptom="none", bp="126/76"),
    prompt="Determine ventricular rate and atrial organization, then choose the next ward assessment.",
    options=[
        Option(
            id="af_assess",
            text="Assess symptoms and perfusion, reconcile AV-nodal medicines and reversible contributors, then review thromboembolic risk and anticoagulation before selecting therapy.",
            answer_class="ideal",
            required_safety_tokens=["anticoagulation_assessment"],
        ),
        Option(
            id="af_more_blocker",
            text="Give a small additional dose of the current AV-nodal blocker, continue telemetry, and reassess the ventricular response before the next medication round.",
            answer_class="unsafe",
        ),
        Option(
            id="af_shock",
            text="Arrange sedation and synchronized cardioversion now, then review anticoagulation status and reversible contributors after sinus rhythm is restored.",
            answer_class="over_triage_safe",
        ),
    ],
    steps=[
        StepwiseStep(
            stage_kind="ecg",
            stage_title="Estimate the ventricular rate",
            competencies=[
                StepCompetency(objective_id="rate", subskill="measure"),
            ],
            prompt="Approximate ventricular rate?",
            options=[
                StepOption(text="About 63/min", correct=True),
                StepOption(text="About 45/min", correct=False),
                StepOption(text="About 90/min", correct=False),
            ],
        ),
        StepwiseStep(
            stage_kind="ecg",
            stage_title="Classify atrial organization",
            competencies=[
                StepCompetency(
                    objective_id="atrial_fibrillation",
                    subskill="discriminate",
                ),
            ],
            prompt="Atrial and ventricular organization?",
            options=[
                StepOption(text="Irregular ventricular rhythm without consistent conducted P waves", correct=True),
                StepOption(text="Sinus rhythm with frequent premature atrial complexes", correct=False),
                StepOption(text="Atrial flutter with fixed atrioventricular conduction", correct=False),
            ],
        ),
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
    stem="A hospitalized patient has an admission ECG reviewed during medication reconciliation. They are comfortable and perfusing; rate-slowing medicines and anticoagulation history are not yet available.",
    chips=StemChips(age=76, setting="ward", symptom="none"),
    prompt="Which assessment should occur before the team modifies rhythm or rate therapy?",
    options=[
        Option(
            id="slow_af_review",
            text="Assess symptoms and perfusion, reconcile rate-slowing medicines and reversible contributors, and evaluate thromboembolic risk and anticoagulation before changing therapy.",
            answer_class="ideal",
            required_safety_tokens=["anticoagulation_assessment"],
        ),
        Option(
            id="slow_af_block",
            text="Give a low-dose AV-nodal blocker to prevent later rapid conduction, continue telemetry, and reassess after the next scheduled medication round.",
            answer_class="unsafe",
        ),
        Option(
            id="slow_af_ignore",
            text="Continue telemetry with the current regimen, document the rhythm for comparison, and leave medication and thromboembolic review for the routine ward round.",
            answer_class="under_triage",
        ),
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
    stem="An inpatient ECG is obtained during evaluation of longstanding hypertension. The patient is comfortable and has no acute cardiopulmonary symptoms.",
    chips=StemChips(age=64, setting="ward", symptom="none"),
    prompt="Which interpretation and follow-up plan is best supported by the ECG and clinical context?",
    options=[
        Option(
            id="lvh_correlate",
            text="Interpret the voltage pattern as possible LVH, verify blood-pressure burden and prior evaluation, and consider echocardiography when structural clarification would change management.",
            answer_class="ideal",
        ),
        Option(
            id="lvh_emergency",
            text="Treat the tracing as hypertensive target-organ injury, begin IV blood-pressure reduction, and transfer the patient for continuous monitored assessment.",
            answer_class="unsafe",
        ),
        Option(
            id="lvh_normal",
            text="Document sinus rhythm with a nonspecific high-voltage variant, continue the current antihypertensive plan, and revisit structural assessment at routine follow-up.",
            answer_class="under_triage",
        ),
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
    stem="A patient reports persistent palpitations, remains alert and well perfused, and has BP 116/72 while the first ECG is reviewed.",
    chips=StemChips(age=49, setting="ed", symptom="palpitations", bp="116/72"),
    prompt="Classify rate, width, and regularity, then choose the initial management path.",
    options=[
        Option(
            id="svt_step_vagal",
            text="Complete the bedside stability check; if tolerated and regular narrow-complex, begin vagal manoeuvres, then monitored adenosine if the rhythm persists.",
            answer_class="ideal",
            required_safety_tokens=["vagal_maneuver", "adenosine", "continuous_monitoring"],
        ),
        Option(
            id="svt_step_shock",
            text="Establish IV access, provide procedural sedation, and perform synchronized cardioversion now, followed by monitored observation and evaluation for precipitating factors.",
            answer_class="over_triage_safe",
        ),
        Option(
            id="svt_step_home",
            text="Start a low-dose oral beta-blocker, observe briefly for symptom improvement, and discharge with ambulatory monitoring and expedited cardiology follow-up.",
            answer_class="unsafe",
        ),
    ],
    steps=[
        StepwiseStep(
            stage_kind="ecg",
            stage_title="Estimate the ventricular rate",
            competencies=[
                StepCompetency(objective_id="rate", subskill="measure"),
            ],
            prompt="Approximate ventricular rate?",
            options=[
                StepOption(text="About 165/min", correct=True),
                StepOption(text="About 130/min", correct=False),
                StepOption(text="About 195/min", correct=False),
            ],
        ),
        StepwiseStep(
            stage_kind="ecg",
            stage_title="Classify width and regularity",
            competencies=[
                StepCompetency(
                    objective_id="supraventricular_tachycardia",
                    subskill="discriminate",
                ),
            ],
            prompt="QRS width and regularity?",
            options=[
                StepOption(text="Regular narrow-complex tachycardia", correct=True),
                StepOption(text="Regular wide-complex tachycardia", correct=False),
                StepOption(text="Irregular narrow-complex tachycardia", correct=False),
            ],
        ),
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
    stem="A patient with persistent palpitations is alert, speaking normally, warm, and has BP 120/76 while an ECG is obtained.",
    chips=StemChips(age=38, setting="ed", symptom="palpitations", bp="120/76", mental_status="alert"),
    prompt="Which initial pathway best integrates the tracing with the bedside stability assessment?",
    options=[
        Option(
            id="svt_triage_treat",
            text="Complete the bedside stability check; if tolerated and regular narrow-complex, begin vagal manoeuvres, then monitored adenosine if the rhythm persists.",
            answer_class="ideal",
            value="workup",
            required_safety_tokens=["vagal_maneuver", "adenosine", "continuous_monitoring"],
        ),
        Option(
            id="svt_triage_shock",
            text="Establish IV access, provide procedural sedation, and perform synchronized cardioversion now, followed by monitored observation and precipitant evaluation.",
            answer_class="over_triage_safe",
            value="act",
        ),
        Option(
            id="svt_triage_routine",
            text="Start a low-dose oral beta-blocker, observe briefly for symptom improvement, and discharge with ambulatory monitoring and expedited cardiology follow-up.",
            answer_class="unsafe",
            value="routine",
        ),
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
    stem="A patient with palpitations is alert and perfusing with BP 124/78 while an ECG is reviewed. No ischemic symptoms or acute heart-failure findings are provided.",
    chips=StemChips(age=67, setting="ed", symptom="palpitations", bp="124/78", mental_status="alert"),
    prompt="Which initial pathway best integrates the tracing, bedside stability, and missing clinical history?",
    options=[
        Option(
            id="af_triage_assess",
            text="Confirm stability and onset context, evaluate contributors and contraindications, begin appropriate monitored rate control, and assess thromboembolic risk and anticoagulation needs.",
            answer_class="ideal",
            value="workup",
            required_safety_tokens=["rate_control", "anticoagulation_assessment"],
        ),
        Option(
            id="af_triage_shock",
            text="Provide procedural sedation and synchronized cardioversion now, then determine episode duration and anticoagulation strategy after conversion.",
            answer_class="over_triage_safe",
            value="act",
        ),
        Option(
            id="af_triage_home",
            text="Start an oral rate-control agent, arrange next-day rhythm follow-up and ambulatory monitoring, and provide return precautions for worsening symptoms.",
            answer_class="unsafe",
            value="routine",
        ),
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
    stem="A patient presents after dizziness and near-syncope. They are awake with BP 104/66 while the ECG and bedside perfusion assessment are reviewed.",
    chips=StemChips(age=74, setting="ed", symptom="syncope", bp="104/66", mental_status="alert"),
    prompt="Which immediate priority best integrates the ECG with the incomplete bedside assessment?",
    options=[
        Option(
            id="chb_triage_act",
            text="Continue bedside perfusion assessment, apply pacing pads, investigate reversible contributors in parallel, and obtain urgent pacing-capable senior or cardiology support.",
            answer_class="ideal",
            value="act",
            required_safety_tokens=["bedside_now", "pacing_pads", "call_help"],
        ),
        Option(
            id="chb_triage_labs",
            text="Maintain continuous telemetry, obtain electrolytes and medication levels, and request cardiology review after the reversible-cause results are available.",
            answer_class="under_triage",
            value="workup",
        ),
        Option(
            id="chb_triage_home",
            text="Treat possible volume depletion, repeat orthostatic vital signs and the ECG after fluids, and use ambulatory rhythm monitoring if symptoms resolve.",
            answer_class="unsafe",
            value="routine",
        ),
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
    stem="A patient reports lightheadedness. They are awake, warm, and have BP 108/70 while medication exposure and reversible contributors are reviewed.",
    chips=StemChips(age=52, setting="ed", symptom="dizziness", bp="108/70", mental_status="alert"),
    prompt="Determine rate and atrioventricular conduction, then choose the next bedside plan.",
    options=[
        Option(
            id="brady_step_assess",
            text="Continue bedside perfusion assessment and continuous monitoring, review medicines and reversible contributors, and prepare escalation if symptoms or perfusion worsen.",
            answer_class="ideal",
            required_safety_tokens=["bedside_now", "continuous_monitoring"],
        ),
        Option(
            id="brady_step_pace",
            text="Establish IV access, apply pacing pads, and begin transcutaneous pacing now while arranging monitored admission and specialist review.",
            answer_class="over_triage_safe",
        ),
        Option(
            id="brady_step_home",
            text="Give oral fluids, withhold the next dose of any rate-slowing medicine, and discharge with ambulatory monitoring and early clinic follow-up.",
            answer_class="unsafe",
        ),
    ],
    steps=[
        StepwiseStep(
            stage_kind="ecg",
            stage_title="Estimate the ventricular rate",
            competencies=[
                StepCompetency(objective_id="rate", subskill="measure"),
            ],
            prompt="Approximate ventricular rate?",
            options=[
                StepOption(text="About 47/min", correct=True),
                StepOption(text="About 65/min", correct=False),
                StepOption(text="About 90/min", correct=False),
            ],
        ),
        StepwiseStep(
            stage_kind="ecg",
            stage_title="Classify atrioventricular conduction",
            competencies=[
                StepCompetency(objective_id="sinus_rhythm", subskill="discriminate"),
            ],
            prompt="Atrial-to-ventricular relationship?",
            options=[
                StepOption(text="Sinus rhythm with one P wave before each QRS", correct=True),
                StepOption(text="Sinus rhythm with intermittent nonconducted P waves", correct=False),
                StepOption(text="Atrial fibrillation with a slow ventricular response", correct=False),
            ],
        ),
    ],
    evidence_manifest=EvidenceManifest(
        ecg_supports=[
            EvidenceClaim(objective_id="bradycardia", threshold="heart_rate<=50", source_type="measured"),
            EvidenceClaim(objective_id="rate", threshold="heart_rate<=50", source_type="measured"),
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
    REAL_QT_INTERVAL_FILLIN,
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
    "ptb-195-rbbb-click": ("195", "172", "269", "287", "5003"),
    "ptb-2-brady-clinic-triage": ("2", "78", "284", "289", "543"),
    "ptb-138-lvh-voltage-click": ("138", "191", "223", "273", "277"),
    "ptb-39-qt-interval-click": ("39", "316"),
    "ptb-320-qt-interval-fillin": ("320", "409", "520"),
    "ptb-330-af-ward-stepwise": ("330", "282", "318", "321", "17769"),
    "ptb-307-slow-af-medication": ("307", "581", "637", "722", "731"),
    "ptb-621-rbbb-spoterror": ("621", "424", "455", "600", "635"),
    "ptb-296-lvh-voltage-spoterror": ("296", "298", "313", "501", "534"),
    "ptb-299-lvh-context-mcq": ("299", "436", "452", "537", "542"),
    "ptb-1173-svt-ed-stepwise": ("1173", "7889", "9866", "10306", "10936"),
    "ptb-3267-svt-ed-triage": ("3267", "14286", "16229", "16753", "336"),
    "ptb-567-af-rvr-ed-triage": ("567", "428", "482", "948", "608"),
    "ptb-959-chb-ed-triage": ("959", "4838", "8620", "21533"),
    "ptb-7806-st-depression-ed-spoterror": ("7806", "1178", "1524", "6594", "11849"),
    "ptb-12-brady-ed-stepwise": ("12", "568", "611", "612", "658"),
}

# These comparisons are not two convenient look-alike tracings. Each pair is
# sourced from PTB-XL records with the same non-null patient identity, distinct
# record ids, acceptable human-validated signal, and a strictly increasing
# recording timestamp. Runtime provenance revalidates those facts before every
# serve and grade. The case narrative and all laboratory/bedside updates remain
# explicitly authored simulation rather than source-dataset claims.
AUTHENTIC_LONGITUDINAL_PRIOR_BY_CURRENT: dict[str, str] = {
    "948": "942",      # 23 h 43 min: rapid AF -> sinus rhythm
    "17769": "17763",  # 25 h: rapid AF -> sinus rhythm; ST-T changes persist
    "5003": "4942",    # 5 d 18 h: unchanged RBBB + LAFB pattern
}

# Governed downstream concepts for the three complete longitudinal episodes.
# These remain narrower than the ECG evidence manifest and are used only for
# formative Clinical application receipts.
LONGITUDINAL_APPLICATION_OBJECTIVES_BY_CURRENT: dict[str, tuple[str, ...]] = {
    "948": ("qt_interval",),
    "17769": ("myocardial_ischemia",),
    "5003": ("right_bundle_branch_block", "left_anterior_fascicular_block"),
}


# Twelve existing real-ECG encounters become source-matching tasks.  These are
# conversions, never additions, so the release bank remains 103 patient cases.
# Four tasks appear in each learner lane; the LVH exemplar is first so
# focused keyboard/browser tests can request it deterministically without
# depending on adaptive ordering or consuming unrelated cases.
MATCHING_ORDINALS_BY_SCENARIO: dict[str, tuple[int, ...]] = {
    # clinic
    "ptb-3-normal-triage": (4,),
    "ptb-28-qtc-medication": (4,),
    "ptb-2-brady-clinic-triage": (4,),
    "ptb-138-lvh-voltage-click": (0,),
    # ward
    "ptb-8911-chb-stepwise": (3,),
    "ptb-307-slow-af-medication": (4,),
    "ptb-299-lvh-context-mcq": (4,),
    "ptb-621-rbbb-spoterror": (4,),
    # emergency department
    "ptb-3267-svt-ed-triage": (4,),
    "ptb-567-af-rvr-ed-triage": (4,),
    "ptb-959-chb-ed-triage": (3,),
    "ptb-7806-st-depression-ed-spoterror": (4,),
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
    "ptb-320-qt-interval-fillin": "qt_drug_safety",
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
    "ptb-320-qt-interval-fillin": (),
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
        _v(71, "medical ward medication round", "dizziness", "During a ward medication round, an inpatient reports dizziness when standing and an ECG is obtained while pulse and perfusion are assessed.", "Determine ventricular rate and atrioventricular relationship, then select the bedside response that should occur in parallel with further evaluation."),
        _v(66, "inpatient mobility assessment", "presyncope", "An inpatient mobility assessment is interrupted by presyncope, and the ward team obtains an ECG while medication exposure and reversible contributors are gathered.", "Sequence the ventricular rate and atrial-to-ventricular activity before choosing the immediate ward priority."),
        _v(79, "evening medical ward review", "fatigue", "At an evening ward review, an inpatient describes unusual fatigue and routine observations prompt an ECG before medications and bedside perfusion have been reconciled.", "Use rate and conduction findings from the trace to decide which actions can proceed together and which response is too delayed."),
        _v(74, "monitored inpatient bed", "syncope", "A monitored inpatient is evaluated after a reported fainting episode; the ECG is available before the bedside cause assessment and medication review are complete.", "Interpret atrial and ventricular activity in sequence, then choose the safest preparation and escalation plan."),
    ),
    "ptb-556-first-degree-click": (
        _v(48, "pre-procedure clinic", "asymptomatic", "An asymptomatic adult has an ECG during elective pre-procedure review, and the automated interval summary needs manual verification.", "In lead II, mark the atrioventricular conduction interval from the start of the P wave to the start of the QRS."),
        _v(54, "medication follow-up clinic", "none", "A medication follow-up visit includes a baseline ECG with a mildly delayed atrioventricular conduction measurement.", "Locate the full PR interval in lead II rather than clicking only the P wave or QRS."),
        _v(36, "occupational health clinic", "asymptomatic", "An occupational health assessment includes a routine ECG whose conduction timing is longer than expected but causes no stated symptoms.", "Select one complete P-onset-to-QRS-onset interval in lead II."),
        _v(62, "primary care review", "none", "A primary-care clinician is checking ECG intervals before renewing medicines that can slow atrioventricular conduction.", "Show where the prolonged PR measurement should be made in lead II."),
        _v(45, "elective therapy baseline clinic", "asymptomatic", "An asymptomatic patient has a baseline tracing before an elective therapy plan, and one conduction interval requires confirmation.", "Place the marker within the PR interval bounded by P-wave onset and QRS onset in lead II."),
    ),
    "ptb-1919-svt-action": (
        _v(55, "emergency department rhythm assessment", "palpitations", "A patient presents with persistent palpitations, and the first emergency-department ECG is available while pulse, perfusion, and symptoms are reassessed.", "Which sequence correctly combines ECG classification, bedside stability, and conditional treatment?"),
        _v(43, "emergency department referral bay", "palpitations", "An urgent-care referral reaches the emergency department for unresolved palpitations, with no rhythm-specific treatment given before transfer.", "Interpret the tracing, then choose the plan that preserves the stability branch before rhythm-specific treatment."),
        _v(61, "emergency department monitored space", "lightheadedness", "A patient reporting lightheadedness is placed in a monitored emergency space while the ECG and bedside perfusion assessment are reviewed together.", "Select the interpretation-to-action order that uses rate, width, and regularity without over-subtyping the atrial mechanism."),
        _v(29, "emergency department triage review", "palpitations", "Emergency triage requests ECG review for persistent heart racing while the bedside assessment proceeds separately from waveform interpretation.", "Which option applies the correct treatment pathway after the tracing and stability findings are integrated?"),
        _v(70, "emergency department observation area", "dyspnea", "A patient in emergency observation reports breathlessness and persistent awareness of a rapid heartbeat; an ECG is obtained without assigning the symptom's cause.", "Choose the conditional pathway supported by the rhythm evidence and the bedside assessment."),
    ),
    "ptb-11034-st-depression-spoterror": (
        _v(80, "general medical ward", "chest_pain", "A ward patient describes intermittent chest discomfort, and the team asks whether the automated ST statement matches this ECG without assigning an acute cause.", "Identify the incorrect machine line and prove the disagreement on the lateral precordial trace."),
        _v(68, "inpatient pre-procedure ward", "chest_pain", "An inpatient awaiting a non-cardiac procedure mentions episodic chest discomfort, and an automated ECG statement requires human review.", "Select the machine claim that the tracing contradicts, then mark the supporting ST segment."),
        _v(73, "respiratory ward consultation", "dyspnea", "A respiratory-ward consultation includes an ECG with a disputed repolarization statement; breathlessness is context, not a diagnosis from the tracing.", "Audit the machine text and localize the lateral ST evidence that resolves the dispute."),
        _v(59, "medical ward symptom review", "chest_pain", "During a ward symptom review, a patient reports nonspecific chest discomfort and the computer interpretation says the ST segments are normal.", "Choose the false automated line and point to the segment that makes it false."),
        _v(76, "inpatient cardiology review", "none", "An inpatient cardiology review is requested because the ECG report and visible lateral repolarization do not agree; no symptoms are supplied.", "Find the report error first, then demonstrate the relevant ST-segment region on the ECG."),
    ),
    "ptb-3-normal-triage": (
        _v(24, "preventive care clinic", "asymptomatic", "An asymptomatic adult has an ECG during a preventive health visit with no cardiopulmonary concern on history or examination.", "Which disposition is proportionate after the tracing is interpreted?"),
        _v(39, "occupational clearance clinic", "none", "An occupational clearance assessment includes a routine resting ECG and an otherwise unremarkable encounter history.", "Choose the disposition supported by the ECG rather than screening for conditions the encounter does not suggest."),
        _v(31, "elective procedure clinic", "asymptomatic", "An elective procedure clinic obtains a screening ECG from a patient without reported symptoms or examination concerns.", "What should this ECG add to the immediate pre-procedure plan?"),
        _v(52, "primary care wellness visit", "none", "A primary-care wellness visit includes a baseline ECG before routine risk-factor counselling; no active symptoms are reported.", "Select the next step justified by the waveform and the stated clinical context."),
        _v(46, "medication baseline clinic", "asymptomatic", "An asymptomatic patient has a baseline ECG before a non-cardiac medication plan, with no concerning clinical finding provided.", "Which response uses the tracing appropriately without adding an unsupported diagnosis?"),
    ),
    "ptb-28-qtc-medication": (
        _v(58, "medication reconciliation clinic", "none", "A medication reconciliation visit is considering an additional drug with repolarization liability, and a baseline ECG is available for review.", "Measure and interpret the relevant interval, then choose the prescribing plan supported by the result."),
        _v(64, "polypharmacy review clinic", "asymptomatic", "An asymptomatic patient attends a polypharmacy review where several current and proposed medicines may affect ventricular repolarization.", "Which action appropriately integrates interval accuracy, interacting drugs, and modifiable contributors?"),
        _v(41, "behavioral health medication clinic", "none", "A behavioral-health medication clinic requests an ECG before adjusting a regimen with known repolarization effects.", "Which plan uses the ECG finding without treating it as proof of a ventricular arrhythmia?"),
        _v(72, "antiemetic planning clinic", "none", "An outpatient treatment plan may add a repolarization-active antiemetic, and this ECG is available for pre-prescribing safety review.", "Interpret the measured interval, then select the most appropriate medication-safety response."),
        _v(50, "specialty pharmacy clinic", "asymptomatic", "A specialty pharmacy flags a possible interaction between two repolarization-active medicines during an otherwise asymptomatic clinic review.", "What should happen after the ECG is measured but before the therapy is changed?"),
    ),
    "ptb-195-rbbb-click": (
        _v(60, "routine cardiology clinic", "asymptomatic", "A routine cardiology ECG has a wide ventricular complex with a right-sided conduction morphology that needs trace-level confirmation.", "In V1, mark a QRS complex that demonstrates the widened ventricular depolarization."),
        _v(47, "pre-procedure assessment clinic", "none", "A pre-procedure assessment includes a wide-QRS ECG, and the reviewer wants the visible ventricular waveform rather than the machine label.", "Select the QRS region in V1 that supports the conduction description."),
        _v(65, "primary care ECG review", "asymptomatic", "A primary-care ECG review notes delayed ventricular conduction on an otherwise routine visit.", "Point to one full widened QRS complex in V1."),
        _v(38, "occupational medicine clinic", "none", "An occupational-medicine tracing contains a right-precordial conduction pattern, and manual waveform localization is requested.", "Use V1 to identify the ventricular complex that carries the conduction pattern."),
        _v(71, "medication baseline clinic", "asymptomatic", "A medication baseline visit includes an ECG with a broad QRS, prompting verification of the ventricular depolarization window.", "Click inside a representative widened QRS complex in lead V1."),
    ),
    "ptb-2-brady-clinic-triage": (
        _v(42, "routine primary care visit", "none", "A routine primary-care visit records a lower pulse than expected, and the medicine list has not yet been reconciled when an ECG is obtained.", "Determine the rhythm and rate, then choose the proportionate assessment and follow-up plan."),
        _v(57, "pre-procedure clinic", "asymptomatic", "An asymptomatic patient has an elective pre-procedure ECG after the intake pulse triggers a manual recheck.", "Which response fits the waveform, current symptoms, and procedure setting?"),
        _v(33, "preventive medicine clinic", "fatigue", "A preventive-medicine patient mentions fatigue and has an ECG after an unexpected pulse reading; the symptom's cause remains undetermined.", "What should be reviewed before deciding whether routine follow-up is sufficient?"),
        _v(69, "medication monitoring clinic", "none", "A medication-monitoring visit obtains an ECG before the current rate-slowing regimen and recent symptoms have been confirmed.", "Interpret the tracing, then select the plan that addresses medication contributors and clinical stability."),
        _v(51, "general internal medicine clinic", "asymptomatic", "An asymptomatic adult has a routine ECG during general medicine follow-up, with no medication reconciliation completed yet.", "Which immediate review and safety-netting plan is supported after the ECG is interpreted?"),
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
    ),
    "ptb-320-qt-interval-fillin": (
        _v(73, "polypharmacy clinic", "none", "A polypharmacy assessment includes an ECG whose repolarization timing should be measured rather than accepted from the machine.", "Count the lead II grid from QRS onset through T-wave end, then enter your raw QT estimate."),
        _v(36, "antiemetic planning clinic", "asymptomatic", "An outpatient antiemetic plan prompts manual review of ventricular depolarization-plus-repolarization timing.", "Measure a representative lead II QT interval and report its duration in milliseconds."),
        _v(66, "specialty medication review", "none", "A specialty medication review flags a prolonged ECG interval and asks for trace-level confirmation.", "Estimate QRS-onset-to-T-end time on a representative lead II beat and enter the nearest QT value."),
    ),
    "ptb-330-af-ward-stepwise": (
        _v(72, "morning medical ward round", "none", "A morning ward round reviews an ECG obtained after a nursing pulse check prompts concern; medicines and stroke history remain unreconciled.", "Determine ventricular rate and atrial organization, then choose the next clinical assessment."),
        _v(78, "inpatient medication reconciliation", "asymptomatic", "During inpatient medication reconciliation, the admission ECG is flagged for clinician review and the current cardiac medication history is incomplete.", "Build the rhythm interpretation in sequence before selecting the medication and thromboembolic review."),
        _v(65, "ward discharge planning", "none", "A ward discharge-planning review includes an ECG that has not yet been reconciled with the outpatient medicine list or rhythm history.", "Use rate and atrial organization to decide what must be assessed before discharge planning continues."),
        _v(69, "general medicine ward consultation", "dyspnea", "A general-medicine inpatient reports breathlessness and has an ECG obtained during bedside review; the symptom's cause remains undetermined.", "Classify the rhythm stepwise, then choose an assessment that preserves uncertainty about the symptom."),
        _v(83, "overnight ward ECG review", "none", "An overnight ECG is obtained after staff request rhythm review, before the medicine list and prior rhythm history have been reconciled.", "Estimate rate, evaluate atrial organization, and select the most appropriate next information-gathering step."),
    ),
    "ptb-307-slow-af-medication": (
        _v(76, "medical ward medication review", "none", "A ward medication review includes an ECG before the patient's rate-slowing medicines and anticoagulation history have been reconciled.", "Interpret the rhythm and ventricular response, then choose what should be assessed before therapy changes."),
        _v(70, "inpatient transfer review", "asymptomatic", "An inpatient transfer note includes an ECG, but the receiving team has not yet confirmed symptoms, cardiac medicines, or thromboembolic history.", "Which next step best integrates the waveform with the missing medication and stroke-risk information?"),
        _v(81, "ward pharmacy consultation", "none", "A ward pharmacist asks whether the next scheduled AV-nodal medicine should be given while the patient's ECG and current regimen are reviewed.", "Use the ventricular response and atrial activity to choose the safest medication and risk assessment."),
        _v(67, "inpatient discharge medication check", "none", "A discharge medication check identifies an unreconciled ECG finding and an incomplete record of rate-control exposure.", "Select the action that integrates rate, symptoms, medicines, and thromboembolic risk before discharge planning continues."),
        _v(74, "general medicine ward round", "fatigue", "A general-medicine inpatient reports fatigue and has an ECG reviewed during the ward round, without evidence that the waveform explains the symptom.", "Which clinical review is proportionate before therapy is intensified or left unchanged?"),
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
        _v(64, "medical ward blood-pressure evaluation", "none", "An inpatient ECG is reviewed during evaluation of longstanding hypertension, and the patient has no acute cardiopulmonary symptoms.", "Which interpretation and follow-up statement is best supported by the trace and clinical context?"),
        _v(58, "ward chronic-risk review", "asymptomatic", "A ward chronic-risk review includes a resting ECG, blood-pressure records, and no available echocardiographic information.", "Choose the interpretation-to-action statement that uses the ECG without overstating structural anatomy."),
        _v(72, "inpatient medication planning", "none", "An inpatient antihypertensive medication plan includes ECG review before outpatient follow-up is arranged.", "What is the most defensible clinical use of the waveform finding?"),
        _v(49, "ward pre-procedure assessment", "none", "A ward pre-procedure assessment obtains an ECG in a patient with hypertension and no evidence of an acute pressure complication.", "Select the response that gives the finding appropriate weight in the broader assessment."),
        _v(67, "general medicine discharge review", "asymptomatic", "A general-medicine discharge review includes an ECG and an incomplete record of prior blood-pressure burden and structural assessment.", "How should the trace be interpreted and followed up without overstating anatomy?"),
    ),
    "ptb-1173-svt-ed-stepwise": (
        _v(49, "emergency department rhythm bay", "palpitations", "A patient with persistent palpitations is assessed in an emergency rhythm bay while the ECG and bedside stability review are completed together.", "Classify ventricular rate, QRS width, and regularity, then choose the conditional management branch."),
        _v(35, "emergency department monitored assessment", "lightheadedness", "A patient reporting lightheadedness is placed in a monitored emergency space while pulse, perfusion, and the first ECG are reviewed.", "Build the rhythm description before deciding which stability findings control treatment."),
        _v(62, "emergency department referral review", "palpitations", "An emergency referral arrives for unresolved palpitations, and the transfer record documents no rhythm-specific treatment before arrival.", "Estimate the rate, determine width and regularity, and select the assessment-first pathway."),
        _v(28, "emergency department triage room", "palpitations", "A patient reporting persistent heart racing has a triage ECG while bedside hemodynamic information is collected.", "Work through the rhythm matrix, then choose the most appropriate conditional first-line plan."),
        _v(73, "emergency observation unit", "dyspnea", "A patient in emergency observation reports breathlessness and a racing heartbeat, with the relationship between the symptoms and ECG still undetermined.", "Use ventricular rate and QRS organization to guide the next treatment branch."),
    ),
    "ptb-3267-svt-ed-triage": (
        _v(38, "emergency department triage", "palpitations", "Emergency triage obtains an ECG for persistent palpitations while pulse, perfusion, mental status, and symptoms are assessed.", "Choose the urgency pathway supported after the waveform and bedside stability data are integrated."),
        _v(46, "emergency department fast-track review", "lightheadedness", "A patient with lightheadedness and ongoing heart racing has an ECG during fast-track review; bedside perfusion assessment is proceeding in parallel.", "Which initial pathway appropriately separates ECG interpretation from the stability decision?"),
        _v(57, "emergency department rhythm station", "palpitations", "An emergency rhythm station receives a patient with persistent palpitations before any rhythm-specific treatment has been given.", "Interpret the trace, then select the initial pathway that preserves the correct stability branch."),
        _v(31, "emergency department assessment area", "palpitations", "A patient in the emergency assessment area has an ECG obtained for persistent heart racing before rhythm-specific treatment is given.", "How urgent is the monitored evaluation, and which conditional first-line route fits the tracing?"),
        _v(69, "emergency department observation", "dyspnea", "The emergency observation team evaluates breathlessness with a racing heartbeat, and obtains an ECG without assigning a cause to either symptom.", "Choose the response that combines bedside stability with the appropriate rhythm-specific pathway."),
    ),
    "ptb-567-af-rvr-ed-triage": (
        _v(67, "emergency department rhythm evaluation", "palpitations", "A patient with persistent palpitations has an ECG while contributors, medication contraindications, onset history, and bedside stability are assessed.", "Interpret the rhythm and rate, then choose the initial management path."),
        _v(74, "emergency department referral bay", "dyspnea", "An emergency referral includes breathlessness and an ECG obtained before medication exposure and episode duration have been reconciled.", "Which triage option integrates stability, contributors, rate strategy, and thromboembolic risk?"),
        _v(52, "emergency department monitored room", "lightheadedness", "A patient with lightheadedness is placed in a monitored emergency room while the ECG is reviewed; no ischemic or heart-failure conclusion is supplied.", "Use the tracing and bedside findings to select the proportionate initial pathway."),
        _v(63, "emergency department triage assessment", "palpitations", "Emergency triage obtains a resting ECG for ongoing palpitations before medication exposure, episode duration, and stroke-risk history are reconciled.", "What information and treatment considerations belong in the first clinical branch after rhythm interpretation?"),
        _v(79, "emergency observation area", "none", "An emergency observation ECG is flagged for rhythm review while the chart lacks a confirmed rate-control regimen or anticoagulation history.", "Choose the immediate assessment that the waveform supports without inferring instability from rate alone."),
    ),
    "ptb-959-chb-ed-triage": (
        _v(74, "emergency department triage", "presyncope", "A patient reports presyncope and has an emergency ECG while bedside perfusion, medication exposure, and reversible contributors are assessed.", "Interpret the trace, then choose the immediate safety priority that should not await a complete diagnostic work-up."),
        _v(68, "emergency department monitored bay", "dizziness", "A patient with dizziness is assessed in a monitored emergency bay while the ECG and bedside stability findings are reviewed together.", "Which response fits the atrial-to-ventricular relationship and the unresolved bedside risk?"),
        _v(81, "emergency department monitored assessment", "syncope", "A monitored emergency assessment follows a reported fainting episode, and the ECG is available before a cause or medication contribution has been assigned.", "Select the immediate plan while reversible contributors and perfusion are investigated in parallel."),
        _v(59, "emergency department rhythm review", "lightheadedness", "An emergency rhythm review is requested for lightheadedness while bedside perfusion and the first 12-lead ECG are assessed.", "Use the ventricular rate and conduction relationship to choose the safest immediate priority."),
    ),
    "ptb-7806-st-depression-ed-spoterror": (
        _v(69, "emergency department chest discomfort review", "chest_pain", "A patient reports chest pressure in the emergency department, and the computer states that no ST depression is present on this resting ECG.", "Identify the incorrect machine statement and localize the lateral ST evidence, without declaring acuity."),
        _v(56, "emergency department symptom assessment", "chest_pain", "An emergency symptom assessment includes chest discomfort and an ECG report that conflicts with the visible lateral ST segments.", "Select the report error, then prove it on the trace while keeping cause undetermined."),
        _v(72, "emergency department dyspnea evaluation", "dyspnea", "A patient evaluated for breathlessness has an ECG with a disputed ST-segment statement; the tracing alone cannot assign the symptom's cause.", "Audit the automated interpretation and point to the repolarization evidence that needs clinical correlation."),
        _v(63, "emergency department referral review", "chest_pain", "An emergency referral for nonspecific chest discomfort arrives with an automated normal-ST statement that requires over-reading.", "Choose the false line and mark the ST depression visible in contiguous lateral leads."),
        _v(78, "emergency observation ECG audit", "none", "An emergency observation ECG is sent for audit because the machine report and lateral ST morphology disagree, with no symptom history supplied.", "Resolve the machine disagreement on the trace and state only the finding the ECG supports."),
    ),
    "ptb-12-brady-ed-stepwise": (
        _v(52, "emergency department bedside review", "lightheadedness", "A patient reports lightheadedness and has an ECG while medicine exposure, reversible contributors, and bedside stability are assessed.", "Estimate ventricular rate, verify the atrial-to-ventricular relationship, then choose the next bedside plan."),
        _v(64, "emergency department assessment room", "dizziness", "An emergency assessment room requests ECG review for a patient with dizziness, with no evidence of collapse and no medication reconciliation completed yet.", "Work through rate and rhythm organization before deciding on monitoring and reversible-cause review."),
        _v(47, "emergency department medication review", "none", "An emergency medication review includes an ECG before the current rate-slowing regimen and recent symptoms have been confirmed.", "Classify the rhythm and rate, then select the action that gathers the missing clinical information."),
        _v(70, "emergency observation unit", "fatigue", "An emergency observation patient reports fatigue and has an ECG reviewed without evidence that the waveform explains the symptom.", "Use rate and atrioventricular conduction to choose a proportionate assessment and escalation plan."),
        _v(58, "emergency department triage review", "presyncope", "Emergency triage obtains an ECG after a report of presyncope while perfusion, medication exposure, and reversible causes are evaluated at the bedside.", "Determine the atrial-to-ventricular relationship, then choose the safest monitoring and escalation plan."),
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


_OPTION_BEARING_QUESTION_TYPES = frozenset({"mcq", "triage", "stepwise"})
_OBVIOUS_DISTRACTOR_CUES = (
    "ignore the",
    "do nothing",
    "without treatment",
    "without further assessment",
    "without checking",
    "without reviewing",
    "based solely on",
    "based on the ecg alone",
    "because the qrs is",
    "because the blood pressure is",
    "routine morning rounds",
    "leave the rhythm untreated",
    "reassure the patient that",
)
_STEM_ANSWER_GIVEAWAY_CUES = (
    "atrial fibrillation",
    "supraventricular tachycardia",
    "complete heart block",
    "third-degree av block",
    "atrioventricular dissociation pattern",
    "sinus bradycardia",
    "left ventricular hypertrophy",
    "normal ecg",
    "normal tracing",
    "prolonged qtc",
    "prolonged corrected interval",
    "regular narrow-complex tachycardia",
    "regular narrow tachycardia",
    "fast irregular rhythm",
    "rapid irregular ecg",
    "irregular tachycardia",
    "high-voltage ecg",
    "high precordial voltage",
    "slow irregular rhythm",
)
_OPTION_WORD = re.compile(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*")


def authored_content_quality_failures(
    items: tuple[ClinicalCaseItem, ...] | list[ClinicalCaseItem],
) -> list[str]:
    """Return deterministic authoring failures for selectable case content.

    These checks intentionally target observable item-writing defects rather
    than trying to infer clinical plausibility from prose.  A selectable option
    must be a complete peer-length action, distractors may not announce their
    own wrongness, and the vignette may not name the diagnosis the learner is
    expected to derive from the ECG.  Stepwise interpretation stages use three
    distinct peer alternatives rather than a binary obvious-extremes check.
    """

    failures: list[str] = []
    for item in items:
        if item.question_type not in _OPTION_BEARING_QUESTION_TYPES:
            continue
        if not 3 <= len(item.options) <= 5:
            failures.append(
                f"{item.item_id}: selectable item has {len(item.options)} options; expected 3-5."
            )
        normalized_options = [" ".join(option.text.casefold().split()) for option in item.options]
        if len(set(normalized_options)) != len(normalized_options):
            failures.append(f"{item.item_id}: selectable options are not textually distinct.")
        word_counts = [len(_OPTION_WORD.findall(option.text)) for option in item.options]
        if word_counts and min(word_counts) < 14:
            failures.append(
                f"{item.item_id}: option word counts {word_counts} include a fragment-like choice."
            )
        if word_counts and max(word_counts) - min(word_counts) > 7:
            failures.append(
                f"{item.item_id}: option word counts {word_counts} are not parallel in detail."
            )
        ideal_count = sum(option.answer_class == "ideal" for option in item.options)
        acceptable_count = sum(option.answer_class == "acceptable" for option in item.options)
        if ideal_count < 1 or (ideal_count != 1 and acceptable_count == 0):
            failures.append(
                f"{item.item_id}: expected one best answer or an explicitly tiered ideal/acceptable set."
            )
        for option in item.options:
            if option.answer_class == "ideal":
                continue
            cue = next(
                (marker for marker in _OBVIOUS_DISTRACTOR_CUES if marker in option.text.casefold()),
                None,
            )
            if cue:
                failures.append(
                    f"{item.item_id}/{option.id}: distractor gives away its weakness via {cue!r}."
                )
        vignette_task = f"{item.stem} {item.prompt}".casefold()
        cue = next(
            (marker for marker in _STEM_ANSWER_GIVEAWAY_CUES if marker in vignette_task),
            None,
        )
        if cue:
            failures.append(
                f"{item.item_id}: vignette/prompt names the ECG answer via {cue!r}."
            )
        if item.question_type == "stepwise":
            if item.prior_ecg_id and not item.application_objectives:
                failures.append(
                    f"{item.item_id}: longitudinal episode requires a governed application objective."
                )
            for index, step in enumerate(item.steps, start=1):
                step_texts = [" ".join(option.text.casefold().split()) for option in step.options]
                if len(step.options) < 3 or len(set(step_texts)) != len(step_texts):
                    failures.append(
                        f"{item.item_id}/step-{index}: expected at least three distinct choices."
                    )
                if sum(option.correct for option in step.options) != 1:
                    failures.append(
                        f"{item.item_id}/step-{index}: expected exactly one keyed interpretation."
                    )
                if not step.competencies:
                    failures.append(
                        f"{item.item_id}/step-{index}: every served stepwise stage requires exact competency mappings."
                    )
                if not step.stage_kind or not step.stage_title:
                    failures.append(
                        f"{item.item_id}/step-{index}: every served stepwise stage requires explicit stage kind and title."
                    )
                if item.prior_ecg_id and any(
                    not option.rationale for option in step.options
                ):
                    failures.append(
                        f"{item.item_id}/step-{index}: every longitudinal choice requires a correction rationale."
                    )
                if "rate" in step.prompt.casefold():
                    displayed_rates = [
                        match.group(0).casefold()
                        for option in step.options
                        if (match := _RATE_TEXT.search(option.text))
                    ]
                    if len(displayed_rates) != len(step.options) or len(set(displayed_rates)) != len(
                        displayed_rates
                    ):
                        failures.append(
                            f"{item.item_id}/step-{index}: rate estimates must be present and distinct."
                        )
    return failures


_RATE_TEXT = re.compile(r"\bAbout\s+\d+\s*/min\b", re.IGNORECASE)


def _rate_distractor_values(heart_rate: int, count: int) -> list[int]:
    """Return distinct, clinically adjacent rate estimates for stepwise choices.

    The old two-choice steps paired the packet-derived answer with a single
    physiologically remote value (for example 47 versus 110/min).  These
    distractors stay on both sides of the measured rate where possible, are
    rounded like a manual grid estimate, and never duplicate the keyed value.
    """

    if heart_rate < 60:
        candidates = (heart_rate + 15, heart_rate + 35, heart_rate - 12, heart_rate + 55)
    elif heart_rate >= 120:
        candidates = (heart_rate - 30, heart_rate + 25, heart_rate - 50, heart_rate + 45)
    else:
        candidates = (heart_rate - 20, heart_rate + 25, heart_rate - 35, heart_rate + 45)
    values: list[int] = []
    for candidate in candidates:
        rounded = min(240, max(20, int(round(candidate / 5.0) * 5)))
        if rounded == heart_rate or rounded in values:
            continue
        values.append(rounded)
        if len(values) == count:
            break
    if len(values) != count:
        raise RuntimeError(
            f"Could not derive {count} distinct rate distractors for {heart_rate}/min."
        )
    return values


def _longitudinal_episode_item(item: ClinicalCaseItem) -> ClinicalCaseItem:
    """Upgrade three reviewed records into source-authenticated patient episodes.

    Only the ECG pair and elapsed interval come from PTB-XL metadata. Symptoms,
    laboratory values, treatment, and handoff facts are authored simulations and
    retain that label in every staged data point. Runtime provenance separately
    proves that the two records belong to the same de-identified patient and are
    chronologically ordered before the item can be served.
    """

    if item.ecg_id == "948":
        update = {
            "item_id": "ptb-948-serial-rhythm-medication-safety",
            "prior_ecg_id": "942",
            "situation": "ed",
            "question_type": "stepwise",
            "acuity_tier": "moderate",
            "stem": (
                "During emergency observation, a repeat ECG is obtained almost 24 hours after an "
                "earlier tracing for sustained palpitations. The patient is now comfortable and "
                "the disposition plan is being reviewed."
            ),
            "chips": StemChips(
                age=67,
                setting="emergency observation unit",
                symptom="palpitations",
                bp="118/72",
                mental_status="alert",
            ),
            "prompt": (
                "Integrate the authenticated ECG comparison, reversible risk factors, and the "
                "handoff before selecting the safest disposition plan."
            ),
            "options": [
                Option(
                    id="episode-plan-a",
                    text=(
                        "Admit to a monitored inpatient unit for extended observation and expedited electrophysiology "
                        "review before disposition to extend rhythm surveillance and medication assessment."
                    ),
                    answer_class="over_triage_safe",
                ),
                Option(
                    id="episode-plan-b",
                    text=(
                        "Continue monitored observation while correcting electrolytes, review QT-active and "
                        "rate-control medicines, complete thromboembolic assessment, and arrange rhythm follow-up before disposition."
                    ),
                    answer_class="ideal",
                    required_safety_tokens=["continuous_monitoring", "check_electrolytes"],
                ),
                Option(
                    id="episode-plan-c",
                    text=(
                        "Treat conversion as resolution, restart the outpatient regimen, and use routine primary-care "
                        "follow-up for any recurrent palpitations or medication questions."
                    ),
                    answer_class="unsafe",
                ),
            ],
            "steps": [
                StepwiseStep(
                    stage_kind="ecg",
                    stage_title="Compare the two ECGs",
                    elapsed_label="Repeat ECG 23 hours 43 minutes later",
                    clinical_update=(
                        "The comparison study and current study are authenticated records from the same "
                        "de-identified patient. No treatment response is implied by the source data."
                    ),
                    data_points=[
                        ClinicalDataPoint(
                            label="Pair relationship",
                            value="Same patient · time ordered",
                            detail="PTB-XL record identity and timestamps",
                            source="source_metadata",
                        )
                    ],
                    competencies=[
                        StepCompetency(objective_id="sinus_rhythm", subskill="synthesize"),
                    ],
                    prompt="Which statement best describes the serial rhythm change?",
                    options=[
                        StepOption(
                            text="The ventricular response is slower, but atrial fibrillation persists on the current ECG.",
                            correct=False,
                            rationale="The current tracing has organized sinus activity; a slower rate alone does not describe the rhythm transition.",
                        ),
                        StepOption(
                            text="The rapid irregular rhythm on the comparison ECG has changed to sinus rhythm on the current ECG.",
                            correct=True,
                            rationale="This is the narrowest comparison supported by the authenticated pair: the earlier irregular rhythm is no longer present and the current tracing is sinus.",
                        ),
                        StepOption(
                            text="The current tracing shows organized atrial activity, but the ventricular rhythm remains a regular tachycardia.",
                            correct=False,
                            rationale="Organized atrial activity is present, but the current ventricular rate does not support persistent regular tachycardia.",
                        ),
                    ],
                ),
                StepwiseStep(
                    stage_kind="reassessment",
                    stage_title="Reassess modifiable risk",
                    elapsed_label="20 minutes after medication reconciliation",
                    clinical_update=(
                        "The episode onset remains uncertain. Medication review identifies two QT-active agents, "
                        "and the first electrolyte panel shows correctable abnormalities."
                    ),
                    data_points=[
                        ClinicalDataPoint(label="Potassium", value="3.3 mmol/L", trend="new"),
                        ClinicalDataPoint(label="Magnesium", value="1.6 mg/dL", trend="new"),
                        ClinicalDataPoint(label="Episode onset", value="Uncertain"),
                    ],
                    competencies=[
                        StepCompetency(objective_id="qt_interval", subskill="apply_in_context"),
                    ],
                    prompt="Which interpretation should drive the next branch?",
                    options=[
                        StepOption(
                            text="Conversion does not resolve stroke-risk, trigger, or medication-safety questions; correct contributors and complete those assessments.",
                            correct=True,
                            rationale="Rhythm conversion is one observation, not closure of episode timing, thromboembolic risk, electrolyte, or QT-active medication questions.",
                        ),
                        StepOption(
                            text="Correct the electrolytes and review QT-active medicines, but defer episode-duration and thromboembolic assessment because sinus rhythm is restored.",
                            correct=False,
                            rationale="Electrolyte and medication review is appropriate, but restored sinus rhythm does not erase episode-duration or thromboembolic assessment needs.",
                            competency_scores={"qt_interval": 1.0},
                        ),
                        StepOption(
                            text="Complete thromboembolic assessment and rhythm follow-up, but leave the QT-active regimen unchanged because no ventricular ectopy was observed.",
                            correct=False,
                            rationale="Absence of observed ectopy does not make correctable electrolyte abnormalities or a QT-active medication combination irrelevant.",
                        ),
                    ],
                ),
                StepwiseStep(
                    stage_kind="handoff",
                    stage_title="Build the disposition handoff",
                    elapsed_label="After initial correction and observation",
                    clinical_update=(
                        "Electrolyte replacement has started, no ventricular ectopy has been observed, and there "
                        "has been no recurrent sustained tachyarrhythmia during the authored observation period."
                    ),
                    data_points=[
                        ClinicalDataPoint(label="Potassium", value="4.1 mmol/L", trend="up"),
                        ClinicalDataPoint(label="Magnesium", value="2.1 mg/dL", trend="up"),
                        ClinicalDataPoint(label="Rhythm monitoring", value="No sustained recurrence"),
                    ],
                    competencies=[
                        StepCompetency(objective_id="qt_interval", subskill="apply_in_context"),
                    ],
                    prompt="Which handoff detail most reduces the chance of an unsafe transition?",
                    options=[
                        StepOption(
                            text="Document current sinus rhythm, corrected electrolytes, and return precautions; defer uncertain episode timing and medication reconciliation to routine follow-up.",
                            correct=False,
                            rationale="This omits unresolved episode timing and the medication-safety work that should travel with the patient at transition.",
                        ),
                        StepOption(
                            text="Document conversion and the reconciled medication list, but omit stroke-risk assessment because there was no sustained recurrence during observation.",
                            correct=False,
                            rationale="A recurrence-free observation interval does not remove the need to communicate the completed or pending stroke-risk assessment.",
                        ),
                        StepOption(
                            text="Document episode timing uncertainty, conversion, electrolyte correction, medication-review findings, stroke-risk assessment, and explicit recurrence follow-up.",
                            correct=True,
                            rationale="This handoff preserves what is known, what remains uncertain, the modifiable risks addressed, and the follow-up needed after disposition.",
                        ),
                    ],
                ),
            ],
            "machine_read": [],
            "roi_target": None,
            "fill_in_task": None,
            "matching_task": None,
            "application_objectives": list(
                LONGITUDINAL_APPLICATION_OBJECTIVES_BY_CURRENT["948"]
            ),
            "disclosed_objectives": [],
            "evidence_manifest": EvidenceManifest(
                ecg_supports=[
                    EvidenceClaim(objective_id="sinus_rhythm", source_type="curated_label"),
                    EvidenceClaim(objective_id="qt_interval", source_type="curated_label"),
                ],
                stem_adds=[
                    "authored emergency-observation presentation",
                    "authored BP 118/72 and alert mental status",
                    "authored medication reconciliation and electrolyte values",
                    "authored monitoring course and disposition handoff",
                    "source-metadata interval: 23 hours 43 minutes",
                ],
                action_rationale=(
                    "Documented rhythm conversion does not close the episode: medication and electrolyte risk, "
                    "episode timing, thromboembolic assessment, and a safe follow-up plan still require attention."
                ),
                forbidden_claims=[
                    "treatment caused rhythm conversion",
                    "torsades occurred",
                    "sinus rhythm eliminates thromboembolic risk",
                ],
                acceptable_range=[
                    "recognize rhythm conversion",
                    "correct modifiable QT risk",
                    "complete stroke-risk and follow-up assessment",
                ],
                epistemic_status="intentionally_underdetermined",
            ),
            "display_spec": DisplaySpec(mode="stacked_twelve_lead", tested_scope="full_12_lead"),
            "tested_scope": "full_12_lead",
        }
    elif item.ecg_id == "17769":
        update = {
            "item_id": "ptb-17769-serial-heart-failure-myocardial-injury",
            "prior_ecg_id": "17763",
            "situation": "ward",
            "question_type": "stepwise",
            "acuity_tier": "moderate",
            "stem": (
                "An older inpatient is reassessed after treatment for acute breathlessness and a fast rhythm. "
                "A repeat ECG is available beside the admission tracing while the team reviews myocardial-injury data."
            ),
            "chips": StemChips(
                age=81,
                setting="monitored heart-failure ward",
                symptom="dyspnea",
                bp="146/84",
                mental_status="alert",
            ),
            "prompt": (
                "Use the serial ECGs, biomarker trajectory, and clinical response without forcing a mechanism "
                "that the available evidence does not establish."
            ),
            "options": [
                Option(
                    id="episode-plan-a",
                    text=(
                        "Prioritize decongestion and rate management, defer further ischemia assessment unless chest "
                        "pressure recurs, and arrange outpatient coronary evaluation after discharge."
                    ),
                    answer_class="under_triage",
                ),
                Option(
                    id="episode-plan-b",
                    text=(
                        "Transfer to a higher-acuity monitored unit for expedited cardiology review and consideration "
                        "of early angiography while the myocardial-injury mechanism remains unresolved."
                    ),
                    answer_class="over_triage_safe",
                ),
                Option(
                    id="episode-plan-c",
                    text=(
                        "Continue heart-failure treatment and monitored serial ACS assessment, compare symptoms, ECGs, "
                        "and troponin trajectory, and escalate cardiology evaluation if ischemic concern persists or worsens."
                    ),
                    answer_class="ideal",
                ),
            ],
            "steps": [
                StepwiseStep(
                    stage_kind="ecg",
                    stage_title="Compare rhythm and repolarization",
                    elapsed_label="Repeat ECG 25 hours later",
                    clinical_update=(
                        "These are authenticated same-patient recordings. The source comparison supports a rhythm "
                        "change and persistent ST-T abnormality, but does not provide symptoms, treatment, or biomarkers."
                    ),
                    data_points=[
                        ClinicalDataPoint(
                            label="Pair relationship",
                            value="Same patient · time ordered",
                            detail="PTB-XL record identity and timestamps",
                            source="source_metadata",
                        )
                    ],
                    competencies=[
                        StepCompetency(objective_id="sinus_rhythm", subskill="synthesize"),
                        StepCompetency(objective_id="nonspecific_st_t_change", subskill="discriminate"),
                    ],
                    prompt="Which comparison is most defensible from the two tracings?",
                    options=[
                        StepOption(
                            text="The rate has slowed, but atrial fibrillation persists and the ST-T abnormalities remain on the current ECG.",
                            correct=False,
                            rationale="The persistent ST-T abnormality is relevant, but the current tracing no longer supports persistent atrial fibrillation.",
                            competency_scores={
                                "sinus_rhythm": 0.0,
                                "nonspecific_st_t_change": 1.0,
                            },
                        ),
                        StepOption(
                            text="The rhythm has changed to sinus, and the remaining ST-T changes can be treated as rate-related because they are less prominent.",
                            correct=False,
                            rationale="A rate change does not establish the mechanism of persistent repolarization abnormalities or make them clinically negligible.",
                            competency_scores={
                                "sinus_rhythm": 1.0,
                                "nonspecific_st_t_change": 0.0,
                            },
                        ),
                        StepOption(
                            text="The rhythm has changed to sinus and slowed, while clinically important ST-T abnormalities remain on the current ECG.",
                            correct=True,
                            rationale="This states the observable rhythm change and preserves the residual repolarization finding without assigning an unsupported cause.",
                        ),
                    ],
                ),
                StepwiseStep(
                    stage_kind="reassessment",
                    stage_title="Interpret the biomarker trajectory",
                    elapsed_label="Two hours into authored reassessment",
                    clinical_update=(
                        "Breathlessness is improving after diuresis and there is no ongoing chest pressure. High-sensitivity "
                        "troponin is mildly elevated with a small rise; renal function is reduced."
                    ),
                    data_points=[
                        ClinicalDataPoint(
                            label="hs-troponin I",
                            value="42 → 49 ng/L",
                            detail="Reference limit <14 ng/L",
                            trend="up",
                        ),
                        ClinicalDataPoint(label="Creatinine", value="1.6 mg/dL", trend="new"),
                        ClinicalDataPoint(label="Respiratory status", value="Improving after diuresis"),
                    ],
                    competencies=[
                        StepCompetency(objective_id="myocardial_ischemia", subskill="apply_in_context"),
                    ],
                    prompt="What conclusion is justified at this point?",
                    options=[
                        StepOption(
                            text="Plaque rupture is the leading explanation for the elevated troponin and persistent ST-T changes, so a type 1 infarction pathway should begin before further correlation.",
                            correct=False,
                            rationale="The available trajectory establishes myocardial injury, but neither plaque rupture nor type 1 infarction is proven by these data alone.",
                        ),
                        StepOption(
                            text="Myocardial injury is present, but whether it has a clinically significant acute component and what mechanism is responsible remain unresolved.",
                            correct=True,
                            rationale="An elevated troponin with a small change supports injury while the ECG, symptoms, renal function, and trajectory still require integration to determine acuity and mechanism.",
                        ),
                        StepOption(
                            text="Chronic renal-associated injury is the leading explanation; improving symptoms make additional ECG or biomarker correlation unnecessary.",
                            correct=False,
                            rationale="Reduced renal function can affect troponin interpretation, but it does not by itself explain away a change or remove the need for serial clinical correlation.",
                        ),
                    ],
                ),
                StepwiseStep(
                    stage_kind="handoff",
                    stage_title="Hand off uncertainty safely",
                    elapsed_label="At evening handoff",
                    clinical_update=(
                        "The third authored troponin is 47 ng/L, oxygenation remains improved, and no recurrent chest "
                        "pressure has occurred. No additional ECG has been obtained."
                    ),
                    data_points=[
                        ClinicalDataPoint(
                            label="hs-troponin I",
                            value="49 → 47 ng/L",
                            detail="Mild plateau after the initial rise",
                            trend="down",
                        ),
                        ClinicalDataPoint(label="Chest pressure", value="None during reassessment"),
                        ClinicalDataPoint(label="Additional ECG", value="Not yet obtained"),
                    ],
                    competencies=[
                        StepCompetency(objective_id="myocardial_ischemia", subskill="apply_in_context"),
                    ],
                    prompt="Which handoff statement best preserves the evidence boundary?",
                    options=[
                        StepOption(
                            text="State the observed injury and persistent ECG abnormality, the unresolved mechanism, and explicit symptom, ECG, and troponin escalation triggers.",
                            correct=True,
                            rationale="This communicates the observed risk signal, preserves diagnostic uncertainty, and gives the next team concrete triggers for reassessment.",
                        ),
                        StepOption(
                            text="Describe likely demand ischemia that is improving, and repeat testing only if chest pressure or breathlessness returns.",
                            correct=False,
                            rationale="Demand ischemia is not established, and waiting only for recurrent symptoms under-communicates the unresolved ECG and biomarker trajectory.",
                        ),
                        StepOption(
                            text="Describe likely type 1 non-ST-elevation infarction and plan early angiography because the ST-T abnormality persists despite symptom improvement.",
                            correct=False,
                            rationale="Persistent ST-T abnormality and injury warrant continued assessment, but they do not establish a type 1 mechanism or a specific invasive plan in this vignette.",
                        ),
                    ],
                ),
            ],
            "machine_read": [],
            "roi_target": None,
            "fill_in_task": None,
            "matching_task": None,
            "application_objectives": list(
                LONGITUDINAL_APPLICATION_OBJECTIVES_BY_CURRENT["17769"]
            ),
            "disclosed_objectives": [],
            "evidence_manifest": EvidenceManifest(
                ecg_supports=[
                    EvidenceClaim(objective_id="sinus_rhythm", source_type="curated_label"),
                    EvidenceClaim(objective_id="nonspecific_st_t_change", source_type="curated_label"),
                    EvidenceClaim(objective_id="myocardial_ischemia", source_type="curated_label"),
                ],
                stem_adds=[
                    "authored acute-breathlessness and heart-failure treatment context",
                    "authored BP 146/84 and alert mental status",
                    "authored serial high-sensitivity troponin and creatinine values",
                    "authored symptom response and evening handoff",
                    "source-metadata interval: 25 hours",
                ],
                action_rationale=(
                    "Persistent repolarization abnormality plus elevated serial troponin supports myocardial injury and "
                    "continued risk assessment, but its acute component and mechanism require the full clinical trajectory."
                ),
                forbidden_claims=[
                    "type 1 myocardial infarction proven",
                    "type 2 myocardial infarction proven",
                    "heart-failure treatment caused the ECG change",
                    "acute coronary syndrome excluded",
                ],
                acceptable_range=[
                    "serial ACS assessment",
                    "treat the precipitating heart-failure physiology",
                    "preserve uncertainty about myocardial-injury mechanism",
                ],
                epistemic_status="intentionally_underdetermined",
            ),
            "display_spec": DisplaySpec(mode="stacked_twelve_lead", tested_scope="full_12_lead"),
            "tested_scope": "full_12_lead",
        }
    elif item.ecg_id == "5003":
        update = {
            "item_id": "ptb-5003-serial-bifascicular-syncope",
            "prior_ecg_id": "4942",
            "situation": "clinic",
            "question_type": "stepwise",
            "acuity_tier": "moderate",
            "stem": (
                "An older adult is seen urgently after an unexplained transient loss of consciousness. A current ECG "
                "and a comparison tracing from six days earlier are available before the disposition decision."
            ),
            "chips": StemChips(
                age=81,
                setting="urgent ambulatory assessment",
                symptom="syncope",
                bp="132/76",
                mental_status="alert",
            ),
            "prompt": (
                "Separate ECG chronicity from symptom risk, incorporate the reassessment, and build a safe transfer handoff."
            ),
            "options": [
                Option(
                    id="episode-plan-a",
                    text=(
                        "Arrange monitored evaluation for unexplained syncope, communicate the unchanged bifascicular "
                        "pattern and medication review, and involve cardiology for intermittent conduction-risk assessment."
                    ),
                    answer_class="ideal",
                ),
                Option(
                    id="episode-plan-b",
                    text=(
                        "Transfer to a higher-acuity monitored inpatient unit for continuous monitoring and expedited "
                        "electrophysiology review while the cause of syncope remains unresolved."
                    ),
                    answer_class="over_triage_safe",
                ),
                Option(
                    id="episode-plan-c",
                    text=(
                        "Use the unchanged comparison to classify the ECG as chronic, arrange outpatient ambulatory monitoring, "
                        "and discharge with precautions after a reassuring examination."
                    ),
                    answer_class="under_triage",
                ),
            ],
            "steps": [
                StepwiseStep(
                    stage_kind="ecg",
                    stage_title="Establish what changed",
                    elapsed_label="Comparison ECG 5 days 19 hours earlier",
                    clinical_update=(
                        "The source records belong to the same de-identified patient. The cardiologist-reviewed comparison "
                        "describes the conduction pattern as not significantly changed."
                    ),
                    data_points=[
                        ClinicalDataPoint(
                            label="Pair relationship",
                            value="Same patient · time ordered",
                            detail="PTB-XL record identity and timestamps",
                            source="source_metadata",
                        )
                    ],
                    competencies=[
                        StepCompetency(objective_id="right_bundle_branch_block", subskill="synthesize"),
                        StepCompetency(objective_id="left_anterior_fascicular_block", subskill="synthesize"),
                        StepCompetency(objective_id="qrs_duration", subskill="discriminate"),
                    ],
                    prompt="Which ECG comparison is best supported?",
                    options=[
                        StepOption(
                            text="A wide-QRS right bundle and left anterior fascicular pattern is present on both ECGs without significant interval change.",
                            correct=True,
                            rationale="The authenticated pair supports the same bifascicular morphology and wide QRS on both recordings without significant interval progression.",
                        ),
                        StepOption(
                            text="Right bundle delay is present on both ECGs, but left anterior fascicular block appears only on the current tracing.",
                            correct=False,
                            rationale="The left anterior fascicular pattern is not newly confined to the current tracing; it is part of the unchanged comparison.",
                            competency_scores={
                                "right_bundle_branch_block": 1.0,
                                "left_anterior_fascicular_block": 0.0,
                                "qrs_duration": 0.5,
                            },
                        ),
                        StepOption(
                            text="The bifascicular pattern is present on both ECGs, but the wider current QRS represents significant interval progression.",
                            correct=False,
                            rationale="The pair is reviewed as not significantly changed, so describing meaningful QRS progression overstates the available comparison.",
                            competency_scores={
                                "right_bundle_branch_block": 1.0,
                                "left_anterior_fascicular_block": 1.0,
                                "qrs_duration": 0.0,
                            },
                        ),
                    ],
                ),
                StepwiseStep(
                    stage_kind="reassessment",
                    stage_title="Reassess the collapse",
                    elapsed_label="After focused history and examination",
                    clinical_update=(
                        "A witness describes abrupt loss of posture with rapid recovery and no clear prodrome. Orthostatic "
                        "vital signs are unrevealing, and no atrioventricular nodal blocker is identified."
                    ),
                    data_points=[
                        ClinicalDataPoint(label="Witness account", value="Abrupt collapse · rapid recovery"),
                        ClinicalDataPoint(label="Orthostatic BP", value="No significant drop"),
                        ClinicalDataPoint(label="Medication review", value="No AV nodal blocker identified"),
                    ],
                    competencies=[
                        StepCompetency(objective_id="right_bundle_branch_block", subskill="apply_in_context"),
                        StepCompetency(objective_id="left_anterior_fascicular_block", subskill="apply_in_context"),
                    ],
                    prompt="How should the unchanged ECG affect risk assessment?",
                    options=[
                        StepOption(
                            text="Stable chronicity lowers but does not eliminate arrhythmic risk; outpatient monitoring is proportionate because the examination and orthostatics are reassuring.",
                            correct=False,
                            rationale="Unchanged morphology answers chronicity, but abrupt unexplained syncope plus unavailable on-site monitoring makes routine outpatient disposition insufficient here.",
                            competency_scores={
                                "right_bundle_branch_block": 0.5,
                                "left_anterior_fascicular_block": 0.5,
                            },
                        ),
                        StepOption(
                            text="Abrupt collapse with bifascicular disease makes intermittent high-grade block the working diagnosis, so a device pathway can begin before rhythm documentation.",
                            correct=False,
                            rationale="Intermittent block is a serious possibility, not a captured diagnosis; the case supports monitored evaluation without claiming a device indication is already established.",
                            competency_scores={
                                "right_bundle_branch_block": 0.5,
                                "left_anterior_fascicular_block": 0.5,
                            },
                        ),
                        StepOption(
                            text="It argues against new conduction morphology but does not exclude intermittent high-grade block or another serious cause of syncope.",
                            correct=True,
                            rationale="Serial stability narrows the morphology question while leaving transient conduction disease and other serious causes of abrupt syncope unresolved.",
                        ),
                    ],
                ),
                StepwiseStep(
                    stage_kind="handoff",
                    stage_title="Prepare monitored transfer",
                    elapsed_label="At disposition",
                    clinical_update=(
                        "The patient remains alert and perfusing, but continuous rhythm monitoring is not available in the "
                        "ambulatory unit. No cause of the collapse has been established."
                    ),
                    data_points=[
                        ClinicalDataPoint(label="Current status", value="Alert · warm · perfusing"),
                        ClinicalDataPoint(label="On-site telemetry", value="Unavailable"),
                        ClinicalDataPoint(label="Cause of syncope", value="Unresolved"),
                    ],
                    competencies=[
                        StepCompetency(objective_id="right_bundle_branch_block", subskill="apply_in_context"),
                        StepCompetency(objective_id="left_anterior_fascicular_block", subskill="apply_in_context"),
                    ],
                    prompt="Which information belongs in the receiving-team handoff?",
                    options=[
                        StepOption(
                            text="Report probable intermittent high-grade block and request pacing evaluation, while noting that the diagnosis has not been captured on ECG.",
                            correct=False,
                            rationale="Labeling the mechanism probable overstates the evidence even if monitored evaluation and possible pacing assessment may follow.",
                            competency_scores={
                                "right_bundle_branch_block": 0.5,
                                "left_anterior_fascicular_block": 0.5,
                            },
                        ),
                        StepOption(
                            text="Describe the abrupt event, unchanged bifascicular pattern, negative focused review, unresolved cause, and need for monitored rhythm assessment.",
                            correct=True,
                            rationale="This separates observed facts from the unresolved mechanism and tells the receiving team why monitored assessment is still needed.",
                        ),
                        StepOption(
                            text="Report stable chronic conduction disease and recommend expedited outpatient monitoring because current vital signs and orthostatics are reassuring.",
                            correct=False,
                            rationale="Current stability and negative orthostatics do not resolve an abrupt loss of consciousness, and telemetry is unavailable in the current setting.",
                            competency_scores={
                                "right_bundle_branch_block": 0.5,
                                "left_anterior_fascicular_block": 0.5,
                            },
                        ),
                    ],
                ),
            ],
            "machine_read": [],
            "roi_target": None,
            "fill_in_task": None,
            "matching_task": None,
            "application_objectives": list(
                LONGITUDINAL_APPLICATION_OBJECTIVES_BY_CURRENT["5003"]
            ),
            "disclosed_objectives": [],
            "evidence_manifest": EvidenceManifest(
                ecg_supports=[
                    EvidenceClaim(
                        objective_id="right_bundle_branch_block",
                        threshold="qrs_ms>=120",
                        source_type="curated_label",
                    ),
                    EvidenceClaim(objective_id="left_anterior_fascicular_block", source_type="curated_label"),
                    EvidenceClaim(objective_id="qrs_duration", threshold="qrs_ms>=120", source_type="measured"),
                ],
                stem_adds=[
                    "authored unexplained syncope presentation",
                    "authored BP 132/76 and alert mental status",
                    "authored witness, orthostatic, and medication reassessment",
                    "authored monitoring availability and transfer handoff",
                    "source-metadata interval: 5 days 19 hours",
                ],
                action_rationale=(
                    "An unchanged conduction pattern answers the newness question, not the syncope-risk question; "
                    "unexplained abrupt collapse still warrants monitored evaluation without claiming documented complete block."
                ),
                forbidden_claims=[
                    "complete heart block captured",
                    "the ECG proves the cause of syncope",
                    "permanent pacing indication established",
                    "unchanged means benign",
                ],
                acceptable_range=[
                    "unchanged bifascicular conduction pattern",
                    "monitored syncope evaluation",
                    "preserve causal uncertainty",
                ],
                epistemic_status="intentionally_underdetermined",
            ),
            "display_spec": DisplaySpec(mode="stacked_twelve_lead", tested_scope="full_12_lead"),
            "tested_scope": "full_12_lead",
        }
    else:
        return item

    upgraded = item.model_copy(deep=True, update=update)
    # model_copy deliberately skips validation; re-enter the strict bank schema
    # after replacing the source family interaction with the episode contract.
    return ClinicalCaseItem.model_validate(upgraded.model_dump())


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
        for step in item.steps:
            if "rate" not in step.prompt.casefold():
                continue
            distractors = iter(
                _rate_distractor_values(
                    rounded_rate,
                    sum(not option.correct for option in step.options),
                )
            )
            for option in step.options:
                replacement = rounded_rate if option.correct else next(distractors)
                option.text = _RATE_TEXT.sub(f"About {replacement}/min", option.text)
    quality_failures = authored_content_quality_failures([item])
    if quality_failures:
        raise RuntimeError("Clinical authored content quality failed: " + "; ".join(quality_failures))
    if ordinal in MATCHING_ORDINALS_BY_SCENARIO.get(template.item_id, ()):
        claims = item.evidence_manifest.ecg_supports
        forbidden = item.evidence_manifest.forbidden_claims
        if not claims or not forbidden or not item.chips.setting:
            raise RuntimeError(
                f"{item.item_id}: matching materialization requires ECG evidence, "
                "an authored setting, and a forbidden claim."
            )
        objective = claims[0].objective_id
        setting_reference = f"authored setting: {item.chips.setting}"
        forbidden_reference = forbidden[0]
        matching_choices = [
            MatchingChoice(id="ecg", label="Supported by this ECG packet"),
            MatchingChoice(id="context", label="Provided only by the authored vignette"),
            MatchingChoice(id="unsupported", label="Not established by this ECG or vignette"),
        ]
        matching_rows = [
            MatchingRow(
                id="ecg-evidence",
                clause=concept_label(objective),
                source_type="ecg_support",
                correct_choice_id="ecg",
                objective_id=objective,
                source_reference=objective,
            ),
            MatchingRow(
                id="authored-context",
                clause=f"Encounter setting: {item.chips.setting}",
                source_type="authored_context",
                correct_choice_id="context",
                source_reference=setting_reference,
            ),
            MatchingRow(
                id="unsupported-claim",
                clause=f"Claim: {forbidden_reference}",
                source_type="unsupported_claim",
                correct_choice_id="unsupported",
                source_reference=forbidden_reference,
            ),
        ]
        # Vary both visual orders deterministically.  The mapping remains stable
        # across refresh/replay, but position cannot become an accidental key.
        seed = sum(ord(character) for character in template.item_id) + ordinal * 17
        choice_shift = seed % len(matching_choices)
        row_shift = (seed // len(matching_choices)) % len(matching_rows)
        matching_choices = matching_choices[choice_shift:] + matching_choices[:choice_shift]
        matching_rows = matching_rows[row_shift:] + matching_rows[:row_shift]
        for index, row in enumerate(matching_rows):
            # Public row ids are transport handles, not semantic hints.  Assign
            # them only after shuffling so an id cannot reveal the hidden key.
            row.id = f"clause-{chr(ord('a') + index)}"
        item = item.model_copy(
            deep=True,
            update={
                "item_id": f"{item.item_id}-matching",
                "question_type": "matching",
                "prompt": "Match each clause to the strongest evidence boundary for this case.",
                "options": [],
                "steps": [],
                "roi_target": None,
                "fill_in_task": None,
                "machine_read": [],
                "application_objectives": [],
                "matching_task": MatchingTask(
                    choices=matching_choices,
                    rows=matching_rows,
                ),
            },
        )
        # ``model_copy(update=...)`` intentionally avoids coercion; re-validate
        # the final converted interaction so a future template edit fails closed.
        item = ClinicalCaseItem.model_validate(item.model_dump())
    if item.ecg_id in AUTHENTIC_LONGITUDINAL_PRIOR_BY_CURRENT:
        item = _longitudinal_episode_item(item)
        quality_failures = authored_content_quality_failures([item])
        if quality_failures:
            raise RuntimeError(
                "Clinical longitudinal content quality failed: " + "; ".join(quality_failures)
            )
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
                "stageKind": step.stage_kind,
                "stageTitle": norm(step.stage_title),
                "elapsedLabel": norm(step.elapsed_label),
                "clinicalUpdate": norm(step.clinical_update),
                "prompt": norm(step.prompt),
                "options": [norm(option.text) for option in step.options],
                "dataPoints": [
                    {
                        "label": norm(point.label),
                        "value": norm(point.value),
                        "detail": norm(point.detail),
                        "trend": point.trend,
                        "source": point.source,
                    }
                    for point in step.data_points
                ],
            }
            for step in item.steps
        ],
        "machineRead": [norm(line.text) for line in item.machine_read],
        "matching": {
            "choices": [norm(choice.label) for choice in item.matching_task.choices],
            "rows": [norm(row.clause) for row in item.matching_task.rows],
        } if item.matching_task else None,
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
    template_quality_failures = authored_content_quality_failures(list(REAL_AUTHORED_ITEMS))
    if template_quality_failures:
        raise RuntimeError(
            "Clinical authored template quality failed: "
            + "; ".join(template_quality_failures)
        )
    for scenario_id, ecg_ids in REAL_ECGS_BY_SCENARIO.items():
        variants = AUTHORED_VARIANTS_BY_SCENARIO[scenario_id]
        if len(variants) != len(ecg_ids):
            raise RuntimeError(
                f"{scenario_id}: {len(ecg_ids)} ECGs require exactly {len(ecg_ids)} "
                f"authored variants, found {len(variants)}."
            )

    unknown_matching = set(MATCHING_ORDINALS_BY_SCENARIO) - family_ids
    matching_count = sum(len(ordinals) for ordinals in MATCHING_ORDINALS_BY_SCENARIO.values())
    if unknown_matching or matching_count != 12:
        raise RuntimeError(
            "Clinical matching conversion contract is invalid "
            f"(unknown={sorted(unknown_matching)}, count={matching_count}; expected 12)."
        )
    templates_by_id = {template.item_id: template for template in REAL_AUTHORED_ITEMS}
    matching_by_lane = {"clinic": 0, "ward": 0, "ed": 0}
    for scenario_id, ordinals in MATCHING_ORDINALS_BY_SCENARIO.items():
        if len(ordinals) != len(set(ordinals)) or any(
            ordinal < 0 or ordinal >= len(REAL_ECGS_BY_SCENARIO[scenario_id])
            for ordinal in ordinals
        ):
            raise RuntimeError(f"{scenario_id}: matching ordinals are duplicated or out of range.")
        lane = templates_by_id[scenario_id].situation
        if lane not in matching_by_lane:
            raise RuntimeError(f"{scenario_id}: matching tasks may only be served in clinic, ward, or ed.")
        matching_by_lane[lane] += len(ordinals)
    if matching_by_lane != {"clinic": 4, "ward": 4, "ed": 4}:
        raise RuntimeError(f"Clinical matching lane mix must be 4/4/4, got {matching_by_lane}.")

    all_ecg_ids = [
        ecg_id
        for template in REAL_AUTHORED_ITEMS
        for ecg_id in REAL_ECGS_BY_SCENARIO[template.item_id]
    ]
    current_ids = set(all_ecg_ids)
    pair_currents = set(AUTHENTIC_LONGITUDINAL_PRIOR_BY_CURRENT)
    pair_priors = set(AUTHENTIC_LONGITUDINAL_PRIOR_BY_CURRENT.values())
    if not pair_currents <= current_ids:
        raise RuntimeError(
            "Clinical longitudinal current ECGs are absent from the serving bank: "
            f"{sorted(pair_currents - current_ids)}."
        )
    if pair_priors & current_ids or len(pair_priors) != len(AUTHENTIC_LONGITUDINAL_PRIOR_BY_CURRENT):
        raise RuntimeError(
            "Clinical longitudinal comparison ECGs must be unique and reserved from standalone serving."
        )
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
