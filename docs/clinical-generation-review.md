# Clinical Decisions — GENERATION review packet (for external clinical/pedagogical audit)

*You are auditing an **automated case-generation pipeline** for an AI-native ECG learning tool for medical students. A cheap LLM drafts board-style decision cases from real PTB-XL tracings; a rule-based **validation harness** gates them; only passing items ("harness_pass") are eligible to be served. The harness already enforces grounding + safety (see §3). YOUR JOB is the layer the harness CANNOT check: **clinical correctness and pedagogical quality of the actual generated items** — is the "ideal" truly ideal? are the distractors and their answer-class tags right? are stems realistic and free of subtle errors? plus critique the pipeline + the proposed future question types. Be specific and adversarial; cite the item by its ECG id.*

---

## 1. Product context (why this exists)
The mode is **objective-driven adaptive mastery**: keep serving a student cases on the pathology they're weak at — varied, not repeats — until mastery, then anything. That requires a **deep, diverse pool of cases per concept** across the ontology, which is why cases are auto-generated (a human can't author thousands). The corpus is the **full PTB-XL** (chronic/resting 12-lead ECGs; ~1.5k AFib, ~4.6k MI, ~1.9k QTc, etc.). Acute STEMI / VT / hyperK are NOT in PTB-XL — findings are chronic/established.

## 2. The generation pipeline (exact)
For one item:
1. **Pick a real case** for a target concept (`repo.candidates(concept)` → Tier A/B PTB-XL cases). Each case packet exposes `supported_objectives` (curation's Tier-A/B concept set), `features` (HR, PR, QRS, QTc, axis, per-lead ST), neutral **ROIs** (p_wave, pr_interval, qrs_complex, st_segment, qt_segment, t_wave per lead), and de-identified age/sex.
2. **Build a grounding context** the model must obey: `supported_objectives`, per-concept `acuity_base`, an `acuity_ceiling` (max action urgency allowed), `required_safety_actions`, the real `measurements`, sanitized `demographics` (age/sex), and `type_guidance` for the question type.
3. **Draft** with a cheap model (gpt-5.4-nano, temperature 0.3, JSON-only) using the system prompt in §2a + the grounding context.
4. **Repair/normalize** the draft (deterministic, lossless-where-safe): lowercase/snap enums; coerce age→int; map sex code; prune keys not in the schema; reconstruct a structured threshold instead of dropping it; etc.
5. **Ground the evidence manifest deterministically**: keep only the model's claimed concepts that are in `supported_objectives`, as `curated_label`, prefer pathology concepts, cap at 4. (The model is bad at writing machine thresholds — "79 bpm" — so we don't trust it to author the safety-critical manifest; it only writes prose. Prose overclaims are still caught by the harness.)
6. **Click items are TEMPLATED**: we set `roi_target` from a supported concept whose neutral ROI is grounded on this tracing, clear options, and set the prompt ("Click the PR interval…"); the model writes only the clinical stem.
7. **Gate through the harness** (§3). Pass → status `harness_pass` (NOT auto-served; a human promotes to `vetted`). Reject reason recorded (parse / schema / harness:<checks>).

### 2a. The model system prompt (verbatim)
```
You author ONE board-style "Clinical Decisions" ECG item as STRICT JSON. The answer is a
clinical DECISION/management action — NOT an interpretation label. Output ONLY a JSON object, no prose.
Follow the `type_guidance` for the requested question_type exactly.

EXACT VALUES (using any other value will be REJECTED):
- situation: one of clinic/ward/ed/triage (lowercase).
- question_type: exactly the requested type.
- acuity_tier: one of none/low/moderate/moderate_high/high; must not exceed acuity_ceiling.
- each option answer_class: ideal/acceptable/over_triage_safe/under_triage/unsafe/insufficient_data. 3-4 options, EXACTLY ONE ideal.
- chips: {age:<int>, setting, symptom, bp}. USE THE PROVIDED demographics age/sex; if age null pick a plausible adult age.
- each ecg_supports source_type: measured/curated_label/authored_context; epistemic_status: determined/intentionally_underdetermined.

ANSWER-CLASS DEFINITIONS (classify each option by what is clinically TRUE of it):
- ideal: the single best management action.
- acceptable: reasonable and safe, slightly suboptimal.
- over_triage_safe: MORE than needed / too aggressive, not harmful (unnecessary admit/cardiology/ED for a benign finding).
- under_triage: does too LITTLE — misses/delays a needed action.
- unsafe: actively harmful/contraindicated/dangerous (wrong drug; discharging a dangerous finding; an irrelevant/absurd action).
- insufficient_data: ONLY for a genuine "gather a specific piece of data before acting" option.

HARD RULES (a validator enforces these):
- The tracing is a RESTING / CHRONIC 12-lead ECG. MI/ischemia/ST-T findings are ESTABLISHED/OLD, not an active event.
  Do NOT write acute/evolving/sudden-onset/"spreading/radiating" narratives or imply an acute coronary event.
- Only claim findings in supported_objectives. Never invent territory/acuity.
- For a high-acuity concept in required_safety_actions, every ideal/acceptable option MUST include a safety token.
- No acute/temporal language unless serial/acute evidence exists.
- Options must be plausible management choices, same specificity, safe to teach against.
- A finding must not be keyed as the CAUSE of a symptom it cannot explain.
```
`type_guidance`: mcq = "3-4 options, one ideal"; triage = "EXACTLY 3 options, values act/workup/routine, one ideal"; stepwise = "3-4 disposition options + a steps array of 2-3 reasoning steps, each step has options with exactly one correct, steps walk rate→rhythm→finding→disposition"; click = "write only the stem + a 'click the…' prompt, no options".

## 3. The harness checks (what already gates the items — do NOT re-derive these)
11 hard-stop checks: compound-option parsing; **evidence_binding** (every claim ∈ supported_objectives; banned territory adjectives; OMI/STEMI/territory-infarct diagnosis claims must be supported); **measurement_claim_binding** (a numeric claim in prose is EVALUATED against the real features — "rate of 140" passes only if true); acute_temporal_causality (negation-aware); symptom_causality (a finding can't be keyed as the cause of a symptom it must-not-explain); transient_event_evidence; required_safety_action; acuity_cap_by_concept; **option_action_urgency_cap** (an ideal/acceptable option's action urgency ≤ the per-concept ceiling — can't key ICU/cath on a benign finding); per-type scoring-schema; display checks. Assume these all PASS for the items below — so any problem you find is a harness **blind spot**.

## 4. Measured yields (real PTB-XL, after ~5 iterations of prompt/pipeline tuning)
MCQ ~60% · triage ~37% · **stepwise ~75%** · **click ~87%** (templated). Rejections are now mostly legitimate (the model over-treating or overclaiming). 0% before tuning (the model wrote unbound thresholds / acute stories / over-aggressive actions). MCQ-only at first; all four types now generate. **Deferred**: old-or-new (PTB-XL has no paired prior ECG per patient) and spot-the-error (templatable, not built).

## 5. VERBATIM generated items — AUDIT THESE (each PASSED the harness)

### MCQ-1 · ECG 307 · ward · acuity=moderate
- grounded: anterior_mi, atrial_fibrillation, axis_normal, LVH, myocardial_infarction, myocardial_ischemia, qt_interval, rate, septal_mi, st_depression, t_wave_inversion · HR 56, QRS 100, QTc 414
- targets: [atrial_fibrillation, myocardial_infarction, anterior_mi, septal_mi] · chips: 63yo man, ward
- **STEM:** "A 63-year-old man is on the ward for chronic medical problems. A resting 12-lead ECG is obtained as part of routine evaluation. The ECG shows atrial fibrillation with a ventricular rate around 56 bpm and established ischemic changes consistent with old anterior/septal myocardial infarction, along with ST-segment depression and T-wave inversion. He is currently hemodynamically stable and has no new chest pain or acute symptoms. What is the best next management action?"
- **OPTIONS:**
  - [ideal] Assess stroke risk and bleeding risk, then initiate or optimize long-term anticoagulation for atrial fibrillation (and arrange follow-up for rate/rhythm strategy).
  - [unsafe] Order serial troponins and treat as an acute coronary syndrome despite the ECG representing established/chronic findings and no acute symptoms.
  - [under_triage] Discharge from the ward without addressing atrial fibrillation stroke prevention because the ECG abnormalities appear chronic.
  - [over_triage_safe] Request urgent ED transfer/cardiology admission solely because the ECG shows old infarct/ischemic changes and AF, even though the patient is stable and asymptomatic.
- grading: ideal 1.0, unsafe 0.0. *(Note: AF rate 56 — is rate control vs anticoagulation framing right here? AF at 56 is slow — relevant?)*

### MCQ-2 · ECG 321 · ward · acuity=moderate
- grounded: atrial_fibrillation, atrial_flutter, axis_normal, electrolyte_drug_pattern, LVH, nonspecific_st_t_change, qt_interval, qtc_prolongation, rate · HR 96, QTc 437
- **STEM:** "72-year-old woman on the ward has a resting 12-lead ECG showing atrial fibrillation with a ventricular rate around 96 bpm and a prolonged QTc (~437 ms). She is clinically stable and has no new chest pain. The team is deciding the next best management step focused on the ECG abnormalities."
- **OPTIONS:**
  - [ideal] Review current medications and correct potential QT-prolonging contributors (check and replete K+/Mg2+), then repeat ECG to confirm QTc improvement.
  - [acceptable] Start or adjust rate control for AF (beta-blocker or non-DHP CCB) while continuing routine monitoring, without specifically addressing QTc contributors at this step.
  - [over_triage_safe] Escalate to immediate ED transfer/cardiology activation solely based on this resting ECG finding.
  - [unsafe] Discharge/stop monitoring because the ECG shows only chronic/non-specific abnormalities and QTc is not actionable.
- grading: ideal 1.0, over_triage 0.0. *(Note: is QTc 437 ms even "prolonged"? Typical cutoffs ~470 men/480 women. The stem calls 437 "prolonged" — possible error; qtc_prolongation is in supported, but 437 is borderline-normal.)*

### MCQ-3 · ECG 162 · clinic · acuity=moderate
- grounded: anterior_mi, LAFB, left_axis_deviation, LVH, myocardial_infarction, myocardial_ischemia, qrs_duration, qt_interval, qtc_prolongation, rate, septal_mi, sinus_rhythm · HR 71, PR 170, QRS 118, QTc 493, axis -43
- **STEM:** "An 85-year-old woman is evaluated in clinic for chronic exertional dyspnea and reduced exercise tolerance. Resting 12-lead ECG shows sinus rhythm with left-axis deviation, left anterior fascicular block, left ventricular hypertrophy, and prolonged QTc. There are established (non-acute) Q-wave/MI pattern findings and possible non-specific ischemic ST-T changes on this resting ECG. What is the best next management action?"
- **OPTIONS:**
  - [ideal] Arrange prompt outpatient cardiology follow-up and medication review for QTc prolongation (avoid QT-prolonging drugs; check/correct K/Mg), and ensure guideline-based secondary prevention for established MI/LVH.
  - [acceptable] Order baseline labs (electrolytes incl K/Mg, renal function) and schedule routine follow-up within several weeks to reassess QTc and symptoms.
  - [over_triage_safe] Send to ED immediately for ACS rule-out based solely on this resting ECG.
  - [unsafe] Discharge without further evaluation because the ECG is chronic and the QTc prolongation does not require action.
- grading: ideal 1.0, over_triage 0.0. *(QTc 493 here genuinely prolonged — good.)*

### TRIAGE-1 · ECG 12 · ed · acuity=low
- grounded: axis_normal, bradycardia, qt_interval, rate, sinus_rhythm · HR 47, PR 102, QTc 387 · 43yo woman
- **STEM:** "43-year-old woman presents to the ED for evaluation of lightheadedness and fatigue. Vitals are otherwise stable. A resting 12-lead ECG is obtained. Heart rate is 47 bpm with sinus rhythm; axis within normal limits; QTc 387 ms."
- **PROMPT:** "act now, work it up, or routine?"
  - [under_triage] value=act: Act now (urgent ED resuscitation/monitoring escalation)
  - [ideal] value=workup: Work it up (ED evaluation with monitoring and targeted labs/med review for symptomatic bradycardia)
  - [over_triage_safe] value=routine: Routine (no urgent escalation; outpatient/low-acuity if symptoms mild and no red flags)
- grading: ideal 1.0, under_triage 0.0. *(Note: "Act now" is tagged UNDER_triage — but acting-now is OVER-triage. Tag may be inverted. And "Routine" tagged over_triage_safe — routine is the LESS aggressive option, i.e. under-triage. The triage value↔class mapping looks scrambled here.)*

### TRIAGE-2 · ECG 78 · ed · acuity=low
- grounded: axis_normal, bradycardia, qt_interval, rate, sinus_rhythm · HR 45, PR 192, QTc 389 · 27yo man
- **STEM:** "27-year-old man presents to the ED for evaluation of dizziness and fatigue. Vitals are stable. … Heart rate is 45 bpm with sinus rhythm; PR 192 ms; QRS 88 ms; QT 450 ms (QTc 389 ms); frontal axis 61°. No acute ischemic pattern; ECG otherwise consistent with sinus bradycardia."
  - [unsafe] Act now: initiate immediate resuscitation/temporary pacing pathway and continuous ACLS-level monitoring
  - [ideal] value=workup: Work it up: cardiac monitoring, basic labs, review meds/substances, evaluate reversible causes of sinus bradycardia
  - [under_triage] value=routine: Routine: discharge with outpatient follow-up without cardiac monitoring or immediate evaluation
- grading: ideal 1.0, unsafe 0.0. *(Here "Act now" is tagged unsafe and "Routine" under_triage — different tagging than TRIAGE-1 for a similar case. Is over-resuscitating an asymptomatic-ish 27yo with HR45 "unsafe" or "over-triage"? Inconsistent across the two triage items.)*

### STEPWISE-1 · ECG 167 · ward · acuity=moderate
- grounded: av_block_first_degree, axis_normal, bradycardia, myocardial_ischemia, qt_interval, rate, sinus_rhythm · HR 54, PR 216, QTc 430 · 54yo man
- **STEM:** "54-year-old man on the ward … sinus rhythm with bradycardia (~54 bpm) and first-degree AV block (PR ~216 ms). Established ST-T changes consistent with myocardial ischemia on this resting tracing (not an acute event). QTc ~430 ms, axis ~+74°."
- **DISPOSITION OPTIONS:**
  - [ideal] Continue inpatient monitoring (telemetry) + outpatient cardiology follow-up for ischemic ST-T; no ED transfer if stable.
  - [over_triage_safe] Obtain serial ECGs and troponins to rule out ACS despite a resting tracing with no acute evolution.
  - [unsafe] Discharge without monitoring/follow-up because QTc is normal and rhythm is sinus.
  - [under_triage] Send to ED immediately for emergent evaluation for unstable bradyarrhythmia/ACS based solely on this resting ECG. *(Note: tagged under_triage but it's clearly OVER-triage.)*
- **STEPS:**
  1. "first step based on the ECG rate?" → [correct] Assess hemodynamic stability + consider ward telemetry given bradycardia (~54). distractors: treat as VT/ACLS; no monitoring ever needed.
  2. "rhythm/AV conduction pattern?" → [correct] Sinus + first-degree AV block (PR ~216), continue monitoring not emergent pacing. distractors: AFib needing anticoagulation; complete heart block needing pacing.
  3. "key finding to drive disposition?" → [correct] Established ischemic ST-T → follow-up + ward monitoring, not automatic ED transfer. distractors: normal QTc alone → discharge; no monitoring needed.
- grading: ideal 1.0, over_triage 0.0. *(Steps are good. But the disposition distractor "Send to ED immediately" is mis-tagged under_triage.)*

### CLICK-1 · ECG 98 · clinic · acuity=low  (TEMPLATED roi_target)
- grounded: av_block_first_degree, axis_normal, qt_interval, rate, sinus_rhythm · HR 64, PR 214, QTc 381 · 20yo male
- **STEM:** "A 20-year-old male presents for a routine clinic visit. … sinus rhythm with a PR interval of 214 ms and a QTc of 381 ms. The learner is asked to click the correct finding on the trace."
- **PROMPT (ours):** "Click the PR interval on the trace." · ROI_TARGET concept=av_block_first_degree leads=[II] type=interval
- grading: correct click 1.0, wrong click 0.0. *(Clean. Minor: stem leaks "The learner is asked to click…".)*

### CLICK-2 · ECG 1178 · ed · acuity=moderate  (TEMPLATED)
- grounded: atrial_fibrillation, axis_normal, electrolyte_drug_pattern, nonspecific_st_t_change, PVC, qt_interval, rate, st_depression · HR 89 · 70yo man
- **STEM:** "A 70-year-old man presents to the ED for evaluation of palpitations. … atrial fibrillation with low-amplitude ST-T abnormalities and occasional PVCs. For this question, click the finding that best matches the following objective: ST segment depression."
- **PROMPT (ours):** "Click the ST segment on the trace." · ROI_TARGET concept=nonspecific_st_t_change leads=[II]
- grading: correct click 1.0, wrong click 0.0. *(Two issues I already see: target concept = nonspecific_st_t_change even though st_depression IS supported (our picker chose the first match); and the stem leaks "click the finding that best matches the following objective: ST segment depression".)*

## 6. Deferred / proposed future question types
- **old-or-new** (today vs prior ECG, ternary new/old/cannot-determine): blocked — PTB-XL has no paired prior ECG per patient. Options: synthetic same-ECG "unchanged" (weak), or source a paired dataset.
- **spot-the-error** (audit a machine read, click the proof): templatable like click (generate a machine-read panel with one wrong line about a supported finding + an ROI target). Not built.
- Other candidates we've considered: order-the-steps, what-would-change-your-mind, confidence-calibrated, telemetry-alarm-triage, prove-it-find-the-lead.

## 7. Your tasks (be concrete; cite items by ECG id)
1. **Clinical correctness of each item above** — is the keyed `ideal` truly the best action? Any clinically wrong stem, option, or rationale? (e.g., MCQ-2: is QTc 437 ms "prolonged"? MCQ-1: AF at rate 56 — does the framing hold?)
2. **Answer-class tagging** — verify every option's class. I flagged likely inversions in TRIAGE-1/2 and STEPWISE-1 (the "act now"/"ED transfer" options). Are those wrong, and is the triage value↔class mapping systematically broken? Since the class drives the SCORE, a wrong tag mis-grades the student.
3. **Distractor quality** — are the distractors plausible-but-wrong and well-discriminated, or too obvious / overlapping / unfair?
4. **The click templating** — is "click the ST segment / PR interval" a sound way to auto-make click items? The CLICK-2 concept-mismatch + stem leakage — how should we pick the target concept and instruct the stem?
5. **The deterministic-manifest tradeoff** — we let the model write prose but build the safety manifest ourselves. Does anything important get lost? Can a clinically-wrong item still pass because the manifest is forced-correct?
6. **Harness blind spots** — give 2-3 concrete clinical errors a generated item could contain that ALL 11 checks (§3) would miss. (This is the highest-value output.)
7. **Future types** — for old-or-new and spot-the-error, and any new type you'd add, sketch how to generate it safely on chronic PTB-XL, and which are worth building.
8. **Diversity & coverage** — across these items, is there enough variety, or do you see formulaic patterns (stem templates, repeated phrasing, same dispositions) that would make a student see "the same question" repeatedly?

Output per task, citing items. We most want: wrong answer-keys, wrong answer-class tags, and harness blind spots — the things that would teach a student something false.
