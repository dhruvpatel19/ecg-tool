# Mode 4 / Clinical Decisions — advanced learner and curriculum audit

> **Historical audit snapshot.** This report records the build and date named below; it is retained as defect-discovery evidence, not current product status. See [the remediation ledger](../PRODUCT_REMEDIATION_LEDGER.md) for reconciled fixes, verification, and remaining gates.

Date: 2026-07-12  
Perspective: senior medical student, near-intern, and curriculum/assessment reviewer  
Live target: `http://127.0.0.1:3110/practice`  
Scope: clinical-case coverage, safety boundaries, interaction design, AI roles, adaptive selection, debrief, competency receipts, authentication/isolation, storage, and learner workload.

## Executive verdict

Mode 4 has a credible visual shell and a better evidence-honesty instinct than most ECG question banks. The calibrated 12-lead viewer is excellent on desktop; real versus synthetic tracing provenance is explicit; the initial ECG-only phase is directionally correct; unsupported guided handoffs fail closed; and the product correctly refuses to manufacture resuscitation or ACLS mastery from resting PTB-XL ECGs.

It is not ready to store or report student competency, and it is not yet the comprehensive clinical mode requested. Five release-blocking findings dominate:

1. A request with **no authentication token** can read an authenticated learner's profile and clinical session and can submit an answer into that learner's session.
2. The same clinical item can be submitted repeatedly; each replay advances the session and writes another attempt even though only one unique item was served.
3. Completing three Learn cases through the live UI produces a report claiming **0% accuracy, 0/5 answered**.
4. Automatically generated cases are promoted from harness pass to `vetted` without the clinician sign-off that the repository itself says is pending; currently served cases include clinically unsafe or internally inconsistent framing.
5. The first-look button records no first-look interpretation. A subsequent management-choice answer can still update broad ECG-objective mastery, while the exact `apply_in_context` subskill is ordinarily not updated. The platform therefore maintains two conflicting learner records.

The current implementation is best described as a polished, safety-conscious **prototype of ECG-informed decision drills**, not a complete clinical-case learning system. It should not make competency or adaptive-mastery claims until the P0 findings and the acceptance gates at the end of this report are closed.

## Method and evidence boundary

I followed the in-app browser-control setup and recovery procedure first. Browser discovery returned no available browser sessions (`agent.browsers.list() == []`) after the documented recovery check, so direct in-app-browser control was unavailable. Per the task instruction, I then used the repository's Playwright installation against the same live production URL.

Evidence gathered:

- direct desktop and 390×844 mobile learner flows on the live site;
- completed an Emergency-department Learn set through the UI;
- exercised guided handoffs, an RBBB localization task, timed context reveal, three lanes, and the report page;
- live API probes using two newly registered audit accounts;
- live clinical-bank coverage and corpus status endpoints;
- direct inspection of the persisted `clinical_case_items` bank;
- frontend, API, grading, storage, authentication, generation, and schema source review;
- `4/4` current auth/clinical Playwright tests passed;
- `53` targeted backend auth/clinical/harness tests passed, `1` skipped.

Those passing tests are useful regression evidence, but they do not cover full-set completion, anonymous access to registered-user identifiers, answer replay, impossible requested lengths, or whether generated clinical content has human approval.

Representative screenshots:

- [Desktop picker](screenshots/MODE4_picker_desktop.png)
- [Incorrect Learn report after three completed ED cases](screenshots/MODE4_learn_report_incorrect.png)
- [Mobile `zoom_lead=V1` task rendered as an off-screen full 12-lead](screenshots/MODE4_zoom_task_mobile.png)
- [Mobile viewport immediately after “reveal clinical context”](screenshots/MODE4_context_reveal_mobile.png)

## What is already working well

### Evidence honesty and safety boundaries

- Every served tracing carries a learner-facing provenance label: either “Real de-identified ECG · authored vignette” or “Synthetic teaching waveform · authored vignette.” The label is data-driven in `backend/app/clinical/shift.py`, not marketing copy.
- The answer key, evidence manifest, acuity, difficulty, review status, option classes, and ROI target are stripped from the blinded item.
- Unsupported guided targets fail closed. The ectopy handoff displays a clear unavailable state, disables Start, preserves the lesson return link, and creates no substitute receipt.
- The product explicitly locks critical-care/resuscitation/ACLS cases until an acute rhythm/telemetry corpus exists. This is the correct choice. A resting 10-second PTB-XL ECG cannot prove onset/offset, pulselessness, instability, response to therapy, or an ACLS action sequence.
- Stem-disclosed ECG objectives are identified and excluded from visual-recognition credit. The post-answer note communicates that distinction to the learner.
- The grading layer includes answer-class, safety caps, confidence penalties, click ROI geometry, machine-audit axes, and grounded viewer highlights.

### Student-facing design

- The picker is calm, legible, and appropriately low-density.
- Lane, Learn versus Shift, and set length are easy to understand.
- The ECG rendering is realistic and well calibrated on desktop: standard sequential 3×4, continuous lead-II rhythm strip, 25 mm/s, 10 mm/mV, zoom/pan/annotation controls, and honest acquisition information.
- Feedback is visually separated from the attempt and can highlight grounded evidence on the trace.
- A second authenticated user's bearer token correctly receives `404` when attempting to read another user's clinical session.

These are strong foundations worth preserving.

## P0 — release blockers

### P0.1 — Missing authentication is treated as authorization

Live result using a newly registered audit learner:

| Probe | Live status |
|---|---:|
| Owner creates authenticated clinical session | `200` |
| No token reads that authenticated session | `200` |
| Different authenticated user reads it | `404` |
| No token submits an answer into it | `200` |
| No token reads the registered learner's mastery by user id | `200` |

The owner id was an opaque `u_...` identifier, which reduces accidental discovery but is not an authorization control. A leaked session id or learner id is sufficient for anonymous read or mutation.

The cause is explicit:

- `backend/app/clinical_routes.py:50` checks ownership only **if** an Authorization header exists.
- `backend/app/main.py:35` falls back to any client-supplied learner id when the token is absent.
- learner profile/mastery endpoints and guided-event writes use that resolver.
- tutor-thread ownership has the same “only if authorization is present” pattern at `backend/app/main.py:477`.

Impact:

- student record confidentiality is not guaranteed;
- a clinical attempt, competency event, profile display name, or tutor thread can be read or altered outside the owning login;
- “proper student authentication” is not satisfied even though registration, password hashing, sessions, login, and logout exist.

Required fix:

- Registered-user resources must require a valid authenticated actor and an exact ownership match.
- Guest mode must use a server-issued guest identity scoped to its own session/cookie; it must not accept arbitrary `learnerId` values.
- Missing, invalid, and cross-user credentials must all fail before resource lookup or mutation.
- Add adversarial tests for anonymous profile read/write, anonymous attempt/guided-event write, anonymous clinical-session read/answer/report, tutor-thread read, expired sessions, and ownership changes.

### P0.2 — Clinical answers are replayable and are not bound to the current served item

Live result:

```text
first submit:          200
same item replay:      200
session position:      2
unique served items:   1
```

`grade_and_record()` accepts a session id and any existing item id, but does not prove that the item is the session's current issued item, belongs to the selected lane, has not already been answered, or matches the handoff focus. `record_shift_served()` increments `position` even when the item id is already present in `served`.

Impact:

- attempts and mastery can be inflated or poisoned;
- a session can be completed by replaying one answer;
- an unrelated case can be injected into a focused or lane-specific session;
- report denominators and adaptive history become untrustworthy.

Required fix:

- Persist a server-issued `current_item_id`, item version, and one-time attempt nonce on the session.
- Accept an answer only once for that exact issued item and actor.
- Make duplicate submission idempotent: return the original grade without a new attempt, mastery delta, position increment, or calibration event.
- Reject out-of-order, other-lane, other-focus, and never-issued item ids.
- Store each session answer in a normalized table with a unique `(session_id, position)` and/or nonce constraint.

### P0.3 — Learn completion produces a false report

I completed every available ED case through the live Learn UI. The set ended after three cases, then reported:

```text
0% accuracy
0 best streak
0/5 answered
— avg decide
Calibration Off (Learn)
```

The screenshot is [here](screenshots/MODE4_learn_report_incorrect.png).

Cause:

- Learn intentionally omits calibration events at `backend/app/clinical/shift.py:183-184`.
- The report uses `len(session["calibration"])` as `answered` at lines 225-226 and derives accuracy/streak/time from that same list.
- Attempts are saved, but the report never reads them or a separate session-answer ledger.

This is a data-integrity failure, not a cosmetic bug. It tells a student who just completed cases that they did nothing and scored zero.

Required fix:

- Track answer outcomes for both Learn and Shift independently from calibration.
- Turn only the calibration label off in Learn; keep answered, correctness, concepts, time if desired, and feedback summaries accurate.
- A three-case early-completed ED set must report `3/3` or clearly `3 answered · set ended because pool exhausted`, never `0/5`.
- Add a browser test that finishes an entire Learn set and verifies the report against recorded attempts.

### P0.4 — `vetted` does not currently mean clinician reviewed

The repository says the danger/acuity tables are a “first-draft pending clinician sign-off,” and the sign-off block is blank in `docs/clinical-content-tables-review.md`. Nevertheless, `backend/scripts/build_generated_bank.py:54` automatically changes each harness-passing generated item to `validation_status = "vetted"`, making it eligible for live serving.

The live bank contains 15 `nano_generated` items. The automated harness is valuable, but it did not prevent clinically important failures, including:

- `gen-191-left_ventricular_hypertrophy-2`: ward patient, heart rate 31 bpm and PR 352 ms; the keyed response centers outpatient LVH evaluation and risk-factor management rather than addressing marked bradycardia/conduction risk.
- `gen-45-right_bundle_branch_block-1`: calls the tracing RBBB while stating QRS 102 ms; that is inconsistent with complete RBBB and should trigger a morphology/duration reconciliation.
- `gen-78-bradycardia-2`: item lane and chips say clinic, while the stem says the patient is “on the ward” and “noted on telemetry.”
- `gen-28-qtc_prolongation-0`: ED lane but the stem describes routine pre-operative clearance in a stable asymptomatic patient.
- `gen-162-left_ventricular_hypertrophy-1`: an 85-year-old ward patient with stated QTc 493 ms and an anterior-MI pattern is reduced to a single LVH outpatient follow-up decision.

These are exactly the kinds of whole-patient and setting errors a concept-by-concept keyword harness will miss.

Required fix:

- `harness_pass` and `clinician_reviewed` must remain distinct states.
- No generated management case may become learner-facing `vetted` without reviewer identity, review timestamp, content/grader version, and explicit sign-off.
- Complete the danger/acuity/action-table sign-off before using those tables for student-facing decisions.
- Add whole-patient conflict checks: severe co-finding dominance, lane/stem/chip consistency, complete-versus-incomplete conduction thresholds, and “keyed plan ignores the most urgent supplied fact.”
- Quarantine the five examples above until reviewed and corrected.

### P0.5 — The learner model can credit the wrong competency

The “Commit first look” control records only `phase = decide`. It does not collect a rhythm, finding, localization, measurement, or confidence judgment. After context reveal, an option-based management answer can update broad `objective_mastery` for ECG concepts that the stem did not disclose, even though the learner never demonstrated visual recognition.

At the same time:

- ordinary Clinical sessions do not write an `apply_in_context` subskill receipt;
- exact subskill receipts are attempted only for a guided deep link carrying `focus` and `subskill`;
- Clinical sends real PTB cases as `real_eligible`, but storage requires `real_reviewed` for independent `apply_in_context`, so current guided Clinical transfers are necessarily downgraded to formative;
- most generated stems explicitly state the ECG diagnosis, correctly suppressing visual credit but leaving no objective mastery delta at all;
- the adaptive Clinical selector reads broad `objective_mastery`, not concept × subskill mastery.

This creates contradictory records: broad “RBBB/QTc/AF mastery” can change from a management option, while the more defensible `apply_in_context` record remains absent or formative.

There is an additional API integrity hole: `GuidedLearningEventRequest.concept` is any non-empty string, not a validated ontology id, and the endpoint can presently be called anonymously. Arbitrary concept × subskill rows can therefore be inserted.

Required fix:

- Capture and grade first look separately: at minimum rhythm/rate, principal finding, localization or measurement when relevant, and first-look confidence.
- Update visual subskills only from trace-bound responses.
- Update `apply_in_context` only from the clinical decision axis.
- Never infer visual recognition from choosing the best management option.
- Use one versioned concept × subskill learner model for adaptive selection, reports, and dashboard claims; treat broad objective rollups as derived summaries only.
- Validate every concept id, subskill, case id, evidence level, case provenance, and assessment contract server-side.
- Define a real clinical-review provenance route before any independent Clinical receipt can be earned.

## P1 — major completeness, validity, and usability gaps

### P1.1 — The clinical bank is tiny relative to the connected PTB corpus

Live corpus status:

- 21,799 PTB records loaded;
- 21,157 Tier A/B student-facing ECGs;
- 46 ontology concepts.

Live Clinical bank:

- 21 items total;
- 19 distinct ECGs total;
- only 14 distinct real PTB ECGs (`0.066%` of the eligible corpus);
- 10 of 46 ontology concepts represented;
- Clinic: 10 items; Ward: 8; ED: 3.

The full corpus is connected to the generic case repository/viewer, but it is not connected to Mode 4 selection. Mode 4 is a static 21-item bank, not near-infinite practice.

The picker offers 5- and 10-case sets for every lane even when the lane cannot supply them. Live runs showed:

| Lane | Requested | Served | Distinct ECGs | Result |
|---|---:|---:|---:|---|
| ED | 5 | 3 | 3 | ended early |
| Ward | 10 | 8 | 7 | ended early; ECG `162` appeared twice |

The UI does not disclose pool depth or disable impossible lengths.

### P1.2 — Question-style variation is mostly nominal

Current distribution:

| Question type | Items | Share |
|---|---:|---:|
| Single-option-set MCQ | 17 | 81% |
| Click | 1 | 5% |
| Old/new | 1 | 5% |
| Spot machine error + click | 1 | 5% |
| Triage option set | 1 | 5% |
| Stepwise | 0 | 0% |
| Fill-in-the-blank / numeric | 0 | 0% |
| Matching / ordering | 0 | 0% |
| Caliper measurement | 0 | 0% |
| Branching management sequence | 0 | 0% |

The schema contains `steps`, but `ClinicalDecisions.tsx` has no step renderer, and the grader dispatches only click, spot-error, or generic option-based grading. There is no branching clinical state.

### P1.3 — Scenario coverage does not yet resemble clinical practice

See the coverage matrix below. In brief: chest pain is one synthetic machine-audit item; QT/drug safety is four near-duplicate option sets; stable AF is repetitive anticoagulation/rate-control wording; there are no high-grade block, wide-complex tachycardia, electrolyte-value, serial-change, or resuscitation scenarios. The locked ACLS boundary is correct but remains an explicit missing deliverable.

### P1.4 — No AI is present inside Mode 4

The global navigation says “AI coach ready,” but `ClinicalDecisions.tsx` imports neither the tutor UI nor the tutor API. There is:

- no Ask AI entry point;
- no case-bound tutor thread;
- no Learn-mode questioning before or after commitment;
- no AI reason-me-back or Socratic probe;
- no cross-concept synthesis after a case or set;
- no AI-generated debrief plan;
- no AI scenario state driver.

Cases were authored offline, some by a model, but that is content generation—not AI-integrated learning.

The correct architecture should keep three roles separate:

1. **Scenario engine:** reviewed deterministic state graph; the model may phrase bounded dialogue but may not invent vitals, ECG facts, outcomes, or actions beyond the evidence manifest.
2. **Tutor:** available in Learn and after commitment; grounded to the current ECG, manifest, response, and branch; silent during independent Shift until submission.
3. **Adaptive planner:** reads the authenticated concept × subskill profile, selects the next validated case contract, logs why it selected it, and never grades its own selection.

### P1.5 — Adaptive selection is a narrow deterministic heuristic and has a trace-repeat bug

The selector does prioritize low broad mastery and high-confidence errors among the small lane pool. That is a useful beginning, but it is not the requested adaptive system:

- it does not use concept × subskill mastery;
- after the first focused handoff item, it does not continue target-specific mastery practice;
- there is no learner-facing target picker, recommendation, rationale, or mastery criterion;
- ties are deterministic rather than intentionally randomized/interleaved;
- weak concepts outside the ten-item-bank concepts cannot be selected;
- generated disclosed-answer cases often produce no objective delta, so the loop receives little signal.

There is also an identifier mismatch: `save_attempt()` stores `case_id=item_id` for Clinical at `shift.py:188`, while `_score_item()` checks whether `item.ecg_id` is in recent case ids at line 88. The recent-tracing penalty therefore never matches Clinical attempts. Ward served ECG `162` twice in one eight-item run.

### P1.6 — Mobile and timed workload interferes with the clinical task

The page has no document-level horizontal overflow, which is good. However:

- an authored `zoom_lead=V1` click task is rendered as the full sequential 12-lead; `viewer-stage` measured 880 px wide inside a 356 px mobile viewport;
- V1 is off-screen and there is no “scroll to V1” cue or automatic lead framing;
- the mobile screenshot initially shows only limb leads even though the task's target is V1;
- the full 12-lead already contains a continuous lead-II rhythm strip, yet 18/21 items add another pinned II strip below it;
- the question sits below the ECG and duplicate strip. In a timed mobile ED case, the question began around document y=1398;
- immediately after pressing “Commit first look & reveal clinical context,” the viewport was y=822–1666 while the newly inserted clinical stem was y=200–343—fully off-screen. The action says it reveals context, but the learner does not see the context unless they scroll back up, then down again to answer;
- the ED clock continues to charge this navigation overhead.

This produces construct-irrelevant time pressure: the learner is partly being tested on page navigation.

### P1.7 — Sessions are durable but not resumable in the UI

Clinical session rows and attempts persist in SQLite, but the active session id lives only in React state. Refreshing or closing the page returns to the picker and orphans the active session. There is no “resume current shift,” completed-shift history, case-by-case transcript, or cross-device continuation.

Guided pathway position remains browser-local, while authenticated competency is server-side. Authentication therefore does not yet provide one coherent student record.

## P2 — important refinement gaps

- The report has no concept/subskill breakdown, missed-evidence review, safety pattern, recommended module, or next adaptive set.
- Learn/Shift confidence is only Low/Medium/High mapped to 2/3/5. `confidenceTimeMs` exists in the schema but is never captured by the UI.
- Backgrounding/visibility, accommodations, and timer fairness are not implemented despite constants for an accommodation scale.
- The raw question-type chip displays labels such as `Mcq`, which feels like an implementation label rather than a learner task label.
- Generated cases are labeled “authored vignette” but do not disclose whether the vignette is clinician-reviewed, model-generated/harness-passed, or hand-authored.
- The picker does not show pool depth, concept availability, expected case mix, or why the adaptive planner selected a lane/set.
- Feedback gives a headline, axes, rationale, and highlight, but not an explicit “what I saw → what it means → what I do” causal chain or a patient outcome.
- No item/grader/objective-version identifiers are stored with attempts, limiting future auditability after content changes.

## Scenario and case-family coverage matrix

| Family | Current live evidence | Current status | What is required |
|---|---|---|---|
| Acute chest pain / ACS | One synthetic anterior-pattern machine-audit item on the ward | Very thin; no real PTB case, serial ECG, troponin layer, triage/disposition branch, or mimic comparison | Stable-vs-unstable branch, serial/prior evidence, reciprocal/localization task, mimics, “ECG does not exclude ACS,” and reviewed action boundaries |
| QTc / medication safety | Four items/four ECGs; almost all “review/stop QT drugs, check K/Mg/Ca” MCQs | Present but repetitive; diagnosis/QTc often disclosed; no learner measurement | QT calipers, correction choice/limitations, wide-QRS caveat, medication/electrolyte data, repeat ECG, risk stratification, and distinct scenarios |
| Stable AF | Four items/four ECGs; one synthetic ED AF-RVR, three ward anticoagulation/rate-control MCQs | Basic coverage; repetitive, limited clinical data | Stability branch, rate versus rhythm reasoning, contraindications, stroke-risk inputs, flutter discrimination, post-answer integration |
| Bradycardia / AV block | Three bradycardia MCQs | Inadequate; no first/second/third-degree block cases; one lane/stem mismatch | Symptom/perfusion branch, PR/beat-relation task, reversible causes, high-grade-block escalation, telemetry requirement |
| Bundle/fascicular conduction | Five RBBB items across four ECGs; one click and one old/new | Best interaction variety, but complete/incomplete duration inconsistency and thin ECG diversity | RBBB/LBBB/fascicular/bifascicular comparisons, symptoms/prior integration, morphology-bound localization and reviewed action cases |
| Normal / reassurance | One synthetic normal triage item | Useful but too small | Normal variants, technical quality, normal-with-concerning-symptom cases, false reassurance safeguards |
| LVH / chamber patterns | Three real LVH MCQs | Present but management-only and unsafe co-finding prioritization in one item | BP/history/echo data, strain-vs-ischemia discrimination, voltage limitations, whole-patient priority checks |
| Ischemia / infarct / mimics | One synthetic anterior machine-error item | Essentially absent despite thousands of corpus ECGs | Chronic infarct patterns, ST/T changes, pericarditis/mimics, territory localization, prior comparison, explicit acute-evidence limits |
| Old versus new / serial change | One synthetic unchanged-RBBB item | Demonstration only | Authentic linked serial data or an explicitly authored data layer, change annotation, action consequence, no unsupported “new/acute” claims |
| Electrolyte-specific cases | Mentioned generically inside QT options | Absent | Supplied K/Mg/Ca values, ECG finding boundaries, medication list, correction/recheck branch; no diagnosis from ECG alone |
| Transient telemetry events | Some generated stems say “telemetry,” but only resting PTB ECGs are supplied | Unsupported | Validated rhythm-strip/telemetry corpus with onset/offset and event labels before competency claims |
| Resuscitation / ACLS | Picker visibly locked | Correctly blocked but unimplemented | Rhythm stream plus pulse/perfusion/clinical state, reviewed current algorithm, action timeline, response-to-intervention states, safety review |
| Wide-complex tachycardia / emergency rhythm | No eligible corpus case in Mode 4 | Absent | Validated acute rhythm source, instability and VT-first safety framing, synchronized/defibrillation branches as appropriate |

## Safety and data-integrity checklist

| Check | Verdict | Evidence |
|---|---|---|
| Real versus synthetic tracing labeled | Pass | Live UI and packet-derived provenance |
| Authored context distinguished from tracing | Pass | Picker and per-case label |
| Answer keys blinded | Pass | API source and tests |
| Unsupported handoff fails closed | Pass | Live ectopy flow and E2E |
| Resting ECG not used to fake ACLS | Pass / deliberately unavailable | Locked picker boundary |
| Stem-disclosed recognition suppressed | Pass for explicit diagnosis text | Grader and live feedback |
| Trace-bound click grading | Pass in backend | ROI geometry and viewer actions |
| Zoomed target actually visible | Fail | `zoom_lead=V1` served; full 880 px viewer rendered on 356 px viewport |
| Registered-user data requires owner auth | Fail | anonymous session/profile read and anonymous answer returned `200` |
| Answer exactly-once/current-item bound | Fail | duplicate answer returned `200`; position 2, unique served 1 |
| Learn report matches saved attempts | Fail | three completed cases reported 0/5 and 0% |
| Requested set length is achievable/disclosed | Fail | ED 3/5; Ward 8/10 |
| No repeated tracing in a set | Fail | ECG 162 twice in Ward run; identifier mismatch defeats recent penalty |
| `vetted` means clinician reviewed | Fail | automatic promotion; review sign-off blank |
| Visual mastery requires visual response | Fail | first look is an unrecorded button; option answer can update objective mastery |
| Clinical application mastery tracked routinely | Fail | exact receipt only on guided deep link and remains formative with current provenance |
| Objective ids validated server-side | Fail | guided-event concept accepts arbitrary string |
| Active session survives refresh | Fail | durable row, no UI resume path |
| AI claims match actual Mode 4 capability | Fail | global “AI coach ready”; no Mode 4 tutor/planner/debrief UI |

## Acceptance criteria before Mode 4 can be called implemented

### 1. Identity, ownership, and privacy

- Every persisted registered-user read/write returns `401/404` without a valid owner session.
- A different authenticated account cannot read or mutate another account's profile, attempts, tutor threads, clinical sessions, or reports.
- Guest use receives a server-owned guest identity and cannot choose another learner id.
- Session tokens are production-hardened: secure transport, revocation, expiry, rate limiting, password policy/recovery, and an explicit XSS/HttpOnly-cookie decision.
- Automated two-user and anonymous adversarial tests cover every learner-scoped route.

### 2. Exactly-once assessment events

- The server persists the issued current item, item/grader version, position, and one-time nonce.
- Only that item can be answered; duplicates are idempotent and cause no new attempt, mastery delta, position, or calibration event.
- Lane, focus, review status, evidence contract, actor, and session status are validated on every answer.
- A database uniqueness constraint enforces the contract even under concurrent requests.

### 3. Truthful reports and resumable sessions

- Learn and Shift reports derive from a session-answer ledger, not calibration-only events.
- A completed three-case set reports three answers and their actual scores.
- The picker disables impossible lengths or states the available depth and dynamically adjusts the denominator with an explicit reason.
- Refresh, reconnect, and cross-device login can resume an active set without replay or data loss.
- Completed sets expose case-level review and concept × subskill outcomes.

### 4. Clinician-governed content

- `harness_pass` cannot be served as `vetted` without a clinician-review record.
- Danger/acuity, action, causality, and required-safety tables have named sign-off and versioning.
- The five unsafe/inconsistent generated items identified above are quarantined, reviewed, and regression-tested.
- Whole-patient dominance, lane/stem/chip consistency, measurement/diagnosis thresholds, and co-finding conflicts are automated gates.
- Learner-facing provenance distinguishes hand-authored reviewed, model-authored reviewed, and synthetic simulation.

### 5. Complete, coherent competency evidence

- Every case declares which subskills it can assess and the exact response evidence required.
- ECG-only first look records a real response before context reveal.
- Recognition/localization/measurement/discrimination/synthesis can change only from trace-bound evidence.
- Management decisions update `apply_in_context`; confidence updates `calibrate_confidence`; neither silently updates visual mastery.
- Disclosed objectives, assisted AI use, hints, and authored simulations are reflected in evidence level.
- The same concept × subskill model drives the dashboard, adaptive planner, handoffs, and reports.
- All concept ids are ontology-validated; attempts store ontology, item, rubric, and grader versions.

### 6. Corpus-wide adaptive case supply

- The Clinical selector can draw eligible ECGs from the full 21,157-case Tier A/B corpus through reviewed, parameterized case contracts—not only a static 14-real-ECG bank.
- All 46 ontology concepts have an explicit clinical-coverage status: supported with pool depth, not clinically applicable, or locked pending a named evidence source.
- Common clinical families have enough distinct ECGs to support repetition without memorization; a reasonable initial gate is at least 20 distinct reviewed ECGs per common family and at least 8 for rare families before adaptive drilling is advertised.
- The planner uses concept × subskill mastery, misconception history, confidence, assistance, staleness, and true ECG ids.
- No exact ECG repeats within a set, and recent-tracing penalties use ECG ids rather than item ids.
- The UI tells the learner the target, why it was selected, the mastery stop rule, and when the planner is interleaving transfer cases.

### 7. Meaningful interaction variety

- Stepwise, numeric/FITB, matching/ordering, caliper measurement, localization/annotation, old/new, spot-error, triage, and synthesis components are implemented and graded.
- No single interaction style exceeds 50% of a representative 20-case adaptive set unless the learner intentionally selects that drill.
- At least 30% of applicable cases require trace interaction rather than option recognition.
- Stepwise cases preserve earlier commitments and branch to different reviewed states; they are not several MCQs displayed sequentially.
- Every dynamic task has a keyboard/touch alternative and trace-grounded scoring.

### 8. AI-first roles with safety separation

- Learn mode has a case-bound tutor that can answer tangents, cite the ECG/manifest evidence, and return to the current decision point.
- Independent Shift keeps the tutor silent until commitment; after submission it can run a bounded reason-me-back and cross-concept probe.
- A separate adaptive planner proposes the next case/set from the authenticated profile and logs a human-readable selection rationale.
- A scenario model may phrase dialogue only inside a reviewed state graph and evidence manifest; it cannot invent ECG findings, vitals, clinical outcomes, or treatment facts.
- Post-set AI debrief identifies a small number of evidence-backed strengths/gaps, connects them to guided/training modes, and offers a specific next set.
- AI help, hints, and tutor exposure are persisted so evidence levels remain honest.

### 9. Clinical-family minimums

- Chest pain: stable/unstable framing, serial/prior boundaries, localization, mimics, troponin/clinical-data layer, and action consequences.
- QT/drugs: learner measurement, correction limits, medication/electrolyte data, wide-QRS caveat, recheck/outcome, and distinct risk contexts.
- Rhythm: stable/unstable AF/flutter/SVT/brady/high-grade block branches and reviewed action safety.
- Ischemia/conduction/normal: enough real variations and mimics to prevent memorization.
- ACLS/resuscitation remains locked until validated rhythm streams, pulse/perfusion state, response-to-action data, and a reviewed current algorithm are connected.

### 10. UI workload and accessibility

- `zoom_lead` renders and frames the requested lead; a V1 mobile target is visible without discovering a hidden horizontal canvas.
- Context reveal scrolls/focuses the newly revealed stem, then provides a persistent compact ECG or clear return-to-trace control.
- The question and decision controls remain reachable without repeated 1,000+ px travel during a running clock.
- Duplicate II strips are removed unless the second strip has a distinct clinical purpose.
- Timers begin only after all required displays and controls are ready and do not charge layout/navigation overhead; accommodation and backgrounding behavior are tested.
- Mobile, keyboard-only, screen-reader, reduced-motion, and large-text flows have end-to-end acceptance tests for each question type.

## Release recommendation

Keep Mode 4 available only as a clearly labeled internal/supervised prototype until P0.1–P0.5 are fixed. The provenance labels, fail-closed handoffs, calibrated ECG viewer, and ACLS data boundary should be retained. The next implementation pass should prioritize identity/ownership and exactly-once event integrity first, then truthful reporting and clinician governance, before scaling the corpus or adding AI. Scaling an invalid learner record or an unreviewed clinical bank would make the later adaptive system confidently wrong.
