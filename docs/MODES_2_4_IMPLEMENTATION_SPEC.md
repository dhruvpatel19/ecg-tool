# Modes 2–4 production implementation specification

**Status:** superseded implementation plan (archived 2026-07-12)  
**Scope:** Training, Rapid Reads, Clinical Cases, authentication, learner evidence, adaptive orchestration, corpus connectivity, and shared student UI  
**Source authority:** `ECG_PLATFORM_SPEC.md`, `docs/PRODUCT_REBUILD_2026.md`, the active PTB-XL/PTB-XL+ manifest, the production guided-storyboard handoffs, and the live persona audits

> This document records the pre-implementation target and is no longer the executable product contract. In particular, its 12-item Training recipe, guest-import rule, and conditional synthetic-simulation allowance were superseded by server-owned campaigns up to 5,000 ECGs, explicit transactional guest→account claiming, and a stronger no-learner-synthetic boundary. Use `docs/MODES_2_4_RELEASE_READINESS.md`, `docs/DATA_SCHEMA.md`, and the active corpus manifest for current behavior.

## 1. Product contract

The four modes are not four unrelated case banks. They are four evidence contexts over one objective graph:

| Mode | Learner job | Help before commitment | What may update independent competency |
| --- | --- | --- | --- |
| Guided | Build a mechanism and a repeatable method | Socratic tutor, animations, hints, tangent-and-return | Only an eligible independent transfer action |
| Training | Make one exact skill reliable across varied morphology | At most one bounded hint; tutor opens after commitment | Task-specific, trace-bound evidence on a Tier A/B case without a hint |
| Rapid | Execute a complete or priority read efficiently | Silent by default; optional coached untimed variant is formative | Grounded structured read, required trace task, confidence, and timing context |
| Clinical | Use an ECG finding within an authored clinical decision | Context is progressively revealed; attending debrief follows commitment | ECG recognition only when not disclosed; clinical application only for reviewed context/action content |

The deterministic platform owns diagnoses, measurements, fiducials, eligibility, answer keys, mastery, timers, and case selection. GPT-5.6 Luna explains, asks questions, chooses an approved teaching strategy, narrates authored branches, and integrates errors across cases. It cannot create clinical truth or assign mastery.

## 2. Shared learning-item contract

Every scored activity must resolve to a versioned item with:

```text
item_id and content_version
mode and session_id
educational_objective_id
case_concept_id
subskill_id
task_type
case_id / comparison_case_id
recording source and per-concept tier
morphology/difficulty cluster
prompt and display contract
allowed response schema
server-side answer/rubric
required leads/measurements/ROIs
scaffold ceiling
clinical-context provenance
review/governance status
```

Pre-answer payloads contain the prompt and response schema but never the answer, diagnosis-bearing report, supported-objective list, concept-confidence truth, or target geometry. Submissions are graded server-side against the pending item. A pending item can be submitted once; replay does not create another competency observation.

## 3. Shared learner-evidence event

Every mode writes the same event shape:

```text
learner_id, session_id, item_id, objective_id, case_concept_id
subskill_id, task_type, mode, context/pace
case_id, comparison_case_id, source, reliability tier, morphology cluster
response JSON, score, correct/partial, measurement or localization error
confidence, hints, scaffold level, response time, timed-out state
requested/effective evidence level, provenance, content/model version
misconceptions, timestamp
```

Competency summaries are derived from observations, not from time spent or a client-provided label. The same case/task replay cannot inflate mastery. Independent evidence requires eligible real data, the correct task predicate, and no disqualifying scaffold. The learner-facing summary separates:

- acquisition/formative understanding;
- independent accuracy;
- morphology/case diversity;
- retention due/overdue;
- timed transfer;
- clinical application;
- confidence calibration;
- evidence uncertainty.

## 4. Mode 2 — Training

### 4.1 Session setup

The learner may choose a concept and subskill or accept the adaptive recommendation. A focused session defaults to 12 items and has a visible recipe:

- 6 target cases;
- 2 close mimics;
- 2 normal/negative controls;
- 1 borderline or noisy case when the objective permits it;
- 1 independent transfer case.

The scheduler adjusts this recipe rather than blindly repeating one label. Below 60% independent evidence, target exposure rises. After three consecutive independent successes across distinct morphology clusters, mimic/normal interleaving rises. A high-confidence miss immediately schedules one discriminator task followed by a new target exemplar. The exact same recording is excluded within the session.

### 4.2 Task-template matrix

| Task type | Learner action | Valid evidence |
| --- | --- | --- |
| Classification | Choose target, mimic, normal, or not-assessable | Case concept and claim ceiling |
| Lead selection | Select all decisive/contiguous leads and no unrelated leads | Objective-specific lead rubric |
| Point | Mark one named fiducial or decisive waveform point | Lead + time/voltage tolerance |
| Region/bounding box | Enclose the relevant wave/segment in a decisive lead | Intersection-over-union/overlap with reviewed ROI |
| Caliper | Place both interval boundaries | Boundary overlap plus millisecond tolerance |
| Normal comparison | Compare a target with a matched normal case | Feature-level differences, not labels alone |
| Look-alike discrimination | Target versus nearest mimic | Required positive and negative discriminators |
| Matching | Match leads↔territories, findings↔mechanisms, or finding↔implication | Exact pair set |
| Fill-in frame | Complete a short evidence sentence from structured tokens | Required evidence slots; semantic text is supplementary |
| Sequence | Order interpretation or mechanism steps | Exact/partially ordered rubric |
| Clinical connection | Choose implication, information need, or claim ceiling | Only after recognition is stable; reviewed content only |
| Confidence calibration | Commit confidence before reveal | Accuracy-confidence relationship over repeated cases |

Every task remains keyboard/touch operable. Classification is never required when the intended skill is pure measurement or localization; task evidence and concept evidence are recorded separately.

### 4.3 AI roles

Before commitment, the coach may provide one learner-requested nudge chosen from an approved ladder: orient to a lead family, name a comparison question, or highlight a neutral region. It may not say the diagnosis. After commitment it may:

- compare the learner’s reasoning with the grounded rubric;
- explain why the nearest mimic fails;
- answer tangents while preserving the current case;
- request allow-listed viewer highlights;
- offer a one-question retrieval check;
- explain the deterministic next-case recommendation.

## 5. Mode 3 — Rapid Reads

### 5.1 Pace contracts

- **Untimed method:** full eight-domain sweep; optional coached variant is formative.
- **Ward read:** validated pilot duration, structured chips/short entries, full synthesis, one trace task.
- **Emergency first look:** priority finding, confidence, and one high-yield localization/measurement action; it is not ACLS certification.

The timer starts only after the waveform and required controls are interactive. Timeout submits the current draft and is recorded; it does not erase learner work.

### 5.2 Case workflow

1. Blinded calibrated 12-lead appears.
2. Learner completes the pace-appropriate first-look task.
3. Ward/untimed modes complete Rate → Rhythm → Axis → Intervals → QRS/conduction → ST–T → Chambers → Synthesis.
4. A case-specific trace task is required when the packet supports it: point, region, lead set, or caliper.
5. Learner commits confidence.
6. Server grades component accuracy, critical misses, overcalls, synthesis, trace evidence, and calibration.
7. Grounded feedback and viewer overlays appear.
8. The next case is selected from the evolving competency graph.

Question forms rotate across full sweep, dominant-finding localization, manual interval verification, territory selection, machine-read audit, finding prioritization, and evidence-limited synthesis. The learner is never asked to type a paragraph under a short emergency clock.

### 5.3 Round debrief and AI integration

The debrief groups errors by mechanism rather than listing percentages. It shows:

- stable domains and brittle domains;
- high-confidence misses and overcalls;
- time versus accuracy trade-off;
- case/morphology diversity;
- one cross-concept connection;
- one recommended Training drill and one optional Clinical transfer;
- why the scheduler chose those activities.

Luna receives only the grounded round summary, misconception tags, and approved destinations. It produces a concise teaching synthesis and can answer questions after the round. The deterministic scheduler supplies the actual recommended objective/case family.

## 6. Mode 4 — Clinical Cases

### 6.1 Evidence layers

Every item visibly separates:

1. **ECG supports** — real recording evidence and its claim ceiling.
2. **Context adds** — authored age, setting, symptoms, vitals, medication list, laboratory value, or prior information.
3. **Action rationale** — reviewed educational decision category and alternatives.

The authored context is never represented as having occurred with the PTB-XL subject. Recognition is committed before any stem that discloses it.

### 6.2 Case families

- chest pain and established ischemia/infarction pattern reasoning;
- bradycardia with pulse/perfusion context;
- tachycardia with pulse and stability context;
- QT/QTc medication-safety review;
- electrolyte/drug-pattern information needs when source evidence permits;
- syncope/palpitations with conduction or rhythm evidence;
- pre-procedure/machine-read audit;
- paced/device observation with explicit management limits;
- resuscitation/ACLS source selection and clearly labeled simulated rhythm streams.

Acute/evolving, true serial comparison, telemetry-onset, arrest-rhythm, drug-causality, and electrolyte-value mastery stay locked until the required reviewed source exists. A complete locked lane still teaches which instrument/source is required and does not award false mastery.

### 6.3 Interaction types

- best-next-decision MCQ with answer-class scoring;
- triage/disposition ranking;
- click/prove-it waveform evidence;
- spot the machine-read error plus trace proof;
- stepwise branching case with optional scaffold bypass;
- select missing information / insufficient-data answer;
- medication-QT calculation and policy boundary;
- old-versus-new only with a valid paired source;
- resuscitation source/rhythm/action sequencing only with reviewed simulated or real stream content.

The scenario engine chooses only among vetted item branches. Luna may deliver the branch conversationally, challenge the learner’s rationale, and connect the result to prior competencies; it cannot generate a new vital sign, lab, answer key, treatment threshold, or branch at runtime.

## 7. Objective graph and corpus connectivity

The objective registry contains the 46 confidence-curated case concepts plus the narrower educational objectives emitted by the ten guided modules. Each educational objective maps explicitly to one or more case concepts and task predicates, or to an honest unavailable state. The backend, not individual pages, owns this mapping.

All 21,799 PTB-XL records remain indexed against all 46 case concepts with A/B/C/D evidence tiers. Student-facing activities use only task-eligible A/B evidence. “Connected” means every record is discoverable and tiered; it does not mean every record is safe for every task. Per-objective coverage reports show:

- total and distinct eligible recordings;
- available task types;
- morphology/difficulty clusters;
- required measurement/ROI/lead coverage;
- reasons a task or clinical lane is unavailable.

## 8. Authentication and progress ownership

Student accounts use revocable, expiring, opaque sessions in HttpOnly SameSite cookies. Passwords are salted and slow-hashed. Login and registration do not expose reusable tokens to browser JavaScript. Authenticated requests ignore client-supplied learner IDs. Ownership checks apply to profiles, attempts, pathway progress, tutor threads, Training sessions, Rapid rounds, review sessions, Clinical shifts, and reports.

Required behaviors:

- verified-email registration, username-or-email sign in, sign out, recovery,
  email change, optional email-code protection, and session hydration;
- length-first password quality plus normalized unique usernames and emails;
- generic invalid-credential responses and bounded failed-login throttling;
- session rotation on sign-in and revocation on sign-out;
- server-stored per-user pathway scene/action state;
- no deployed guest learning mode or anonymous learning writes;
- positive legacy browser records offered once for explicit attach or discard
  after a verified account signs in;
- no cross-user read or replay by changing an ID in a URL/body;
- password-confirmed profile export and transactional account deletion.

## 9. Student UI system

The ECG is the dominant visual surface. Controls are organized by the learner’s current decision, not by backend schema.

- Desktop/laptop: compact session header, dominant viewer, focused response rail, collapsible AI drawer.
- Tablet/mobile: selected lead/task first, horizontally calibrated viewer, response sheet below, persistent timer/commit controls.
- The AI drawer shows its current role: **Coach**, **Silent observer**, **Debrief**, or **Attending challenge**.
- Technical provenance is visible but secondary; answer-bearing evidence stays masked.
- Progress distinguishes path coverage, formative evidence, independent evidence, retention, and clinical transfer.
- Every interaction has visible focus, descriptive names, ≥44 px touch targets where feasible, reduced-motion behavior, and a non-drag alternative.

## 10. Acceptance gates

The implementation is not complete until:

1. All task types above have server-side grading and at least one eligible end-to-end case.
2. Training sessions enforce target/mimic/normal/transfer composition and no-repeat evidence.
3. Rapid cases require a case-appropriate trace action and produce a cross-case adaptive debrief.
4. Clinical scored production excludes synthetic fixtures unless the lane explicitly labels simulation and its competency ceiling.
5. Authentication uses HttpOnly sessions and automated tests prove cross-user isolation for every session/report/thread/progress route.
6. Guided, Training, Rapid, and Clinical write the shared evidence event.
7. The profile exposes all tracked objective×subskill states and deterministic recommendations.
8. The active manifest and objective-coverage API prove corpus/task availability without overstating sparse concepts.
9. Novice, clerkship, and advanced personas retest desktop/mobile flows directly.
10. Backend, typecheck, production build, browser, accessibility, timer, blinding, replay, and responsive tests all pass.
