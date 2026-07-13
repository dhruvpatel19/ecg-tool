# Implementation coverage report

**Snapshot:** 2026-07-10  
**Product surface:** AI-first ECG learning platform at `/learn`, `/train`, `/rapid`, and `/practice`  
**Educational status:** comprehensive curriculum/runtime implementation with evidence-gated case use; not a clinical diagnostic product or a validated certification instrument

> **Archived snapshot.** Counts, mode limits, Clinical supply, authentication, retention, and verification totals below describe the July 10 checkpoint and are intentionally not current. The live source of truth is `docs/MODES_2_4_RELEASE_READINESS.md`, `docs/DATA_SCHEMA.md`, and `data/ecg_corpus/manifest.json`.

## Executive result

The repository now implements a coherent four-mode ECG learning system rather than a collection of disconnected tutorials. The guided curriculum uses **10 dependency-driven modules and 118 interactive scenes**. Ten modules were chosen because this is the smallest structure that preserves the validated beginner Foundations sequence, keeps rhythm and conduction reasoning in the correct order, and gives repolarization and ischemia enough separate conceptual space to avoid pattern-memorization shortcuts.

The implementation is backed by three production storyboard volumes totaling **84,325 words**, a typed interaction/runtime contract, a calibrated 12-lead ECG viewer, an AI tutor with tangent-and-return behavior, exact concept-by-subskill learner records, adaptive case selection, and explicit handoffs among Guided, Training, Rapid, and Clinical modes.

The full built corpus contains **21,799 real PTB-XL records**, of which **21,157 are student-facing Tier A/B cases**. That headline is not treated as uniform depth: eligibility is determined per case, per concept, and per task. Sparse concepts and source-incompatible activities fail closed instead of being padded with fabricated diagnoses or unrelated cases.

## 1. Curriculum source authority and architecture

The binding content spine is `ECG_PLATFORM_SPEC.md` §11, including all 16 minimum curriculum requirements. Section 7 supplies the concept ontology, §12 supplies systematic interpretation frameworks, and §16 supplies misconception targets. The original Foundations sequence remains the beginner dependency spine. Clinical-case documents inform transfer design but do not replace the §11 curriculum authority.

The rationale, dependency graph, exact §11 topic map, ontology deltas, misconception map, mode boundaries, and module-level coverage audits are documented in:

- `docs/storyboards/CURRICULUM_ARCHITECTURE_RECOMMENDATION.md`
- `docs/storyboards/SOURCE_CONTENT_INVENTORY.md`
- `frontend/src/lib/learning/sourceRequirements.ts`
- `frontend/src/lib/learning/modules/nativeRequirementCoverage.ts`
- `frontend/src/lib/learning/validateCurriculum.ts`

### Production module map

| Module | Production focus | Scenes |
| --- | --- | ---: |
| M1 | Foundations: signal, grid, calibration, waves, rate, rhythm, intervals, leads, basic axis, and complete descriptive read | 13 |
| M2 | Leads, vectors, axis, territories, contiguity, placement, and polarity prediction | 15 |
| M3 | Rhythm logic, atrial/ventricular timelines, pauses, ectopy, and artifact | 16 |
| M4 | AV conduction, bradyarrhythmias, ambiguity, escape rhythms, and perfusion context | 11 |
| M5 | Ventricular activation, bundle/fascicular delay, pre-excitation, pacing, and secondary ST-T change | 11 |
| M6 | Narrow/wide and regular/irregular tachyarrhythmias with a safety-first evidence sequence | 12 |
| M7 | Atrial/ventricular chamber evidence, voltage, R-wave progression, strain, and criteria limits | 8 |
| M8 | Repolarization, ST-T description, QT/QTc, wide-QRS confounding, drugs, and electrolytes | 10 |
| M9 | Ischemia/infarction geography, reciprocal evidence, established change, and mimics | 10 |
| M10 | Integrated interpretation, machine audit, communication, source limits, and clinical transfer | 12 |
| **Total** |  | **118** |

The executable registry is `frontend/src/lib/learning/modules/index.ts`; the learner-facing hub projection and scene totals are in `frontend/src/lib/modules.ts`. Prerequisites form a dependency graph rather than a rigid lockstep sequence: after the common literacy/rhythm/conduction spine, learners can branch and later reconverge for ischemia and integrated transfer.

### Storyboard depth

| Storyboard volume | Word count |
| --- | ---: |
| `docs/storyboards/VERBATIM_M01_M03.md` | 32,320 |
| `docs/storyboards/VERBATIM_M04_M06.md` | 23,264 |
| `docs/storyboards/VERBATIM_M07_M10.md` | 28,741 |
| **Total** | **84,325** |

These are implementation storyboards, not module-title outlines. Scenes specify instructional objective, exact learner-facing copy, first-principles mechanism, clinical connection, prerequisite recall, future reuse, layout at desktop/laptop/mobile sizes, tutor opening and Socratic prompts, hint ladder, tangent bridge, exact return waypoint, interaction sequence, feedback branches, completion rule, case contract, evidence ceiling, and cross-mode handoff.

## 2. Guided learning runtime and interaction coverage

Modules 2–10 run through the typed production scene system in:

- `frontend/src/lib/learning/interactionTypes.ts`
- `frontend/src/components/learning/ProductionModuleExperience.tsx`
- `frontend/src/components/learning/LearningInteractionRenderer.tsx`
- `frontend/src/lib/learning/gradeInteraction.ts`

The runtime supports 17 interaction kinds: single-select, multi-select, sequencing, lead selection, vector prediction, waveform point, waveform region, caliper measurement, marching markers, comparison, free response, staged clinical decisions, hotspot maps, animated/model exploration, numeric entry, pairing, and categorization. Each interaction requires keyboard/screen-reader instructions and appropriate feedback branches. Scene completion, pathway progress, formative evidence, and independent competency evidence are represented separately.

Foundations remains a validated 13-scene hosted experience, synchronized with the shared progress contract through `frontend/src/app/learn/foundations/page.tsx` and described by `frontend/src/lib/learning/modules/foundationsExternal.ts`. It now includes keyboard alternatives, stronger focus visibility, and learner-state synchronization. Its remaining architectural difference is explicit: it is still hosted rather than fully migrated into the native React scene state.

### Realistic ECG interaction

`frontend/src/components/ECGViewer.tsx` renders real corpus waveforms as a conventional sequential 3 × 4 diagnostic print with a continuous lead-II rhythm strip. The viewer uses square **25 mm/s · 10 mm/mV** paper, a calibration pulse, lead labels, zoom/pan/reset, lead/time/amplitude coordinates, point and region drawing, calipers, reviewed ROI overlays, and keyboard-operable task entry.

Measurement grading no longer accepts the right duration at an unrelated time or in the wrong sequential lead panel. PR/QRS/QT tasks can require overlap with a reviewed waveform boundary, and missing reviewed evidence makes the task not assessable rather than guessable. The mobile presentation preserves a calibrated minimum trace width inside an internal horizontal scroller so morphology is not crushed to fit the viewport.

## 3. Four learning modes and their distinct jobs

| Mode | Route | Primary educational job | AI posture and valid evidence |
| --- | --- | --- | --- |
| **Guided** | `/learn` | Construct first-principles mental models, teach a repeatable method, connect prior and future concepts, and rehearse with fading support | Visible Socratic tutor; tangent-and-return; guided evidence is not silently promoted to independent mastery |
| **Training** | `/train` | Repeat one exact subskill across target, normal, and nearby mimic cases until the learner becomes fluent | AI selects weakness-relevant cases and offers one tracked hint; independent trace-bound attempts update the selected concept × subskill |
| **Rapid** | `/rapid` | Test complete ECG performance at untimed, ward, or quick-look pace | Tutor is silent before commitment; deterministic post-submit feedback records full-read accuracy, timing, confidence, and grounded target evidence |
| **Clinical Decisions** | `/practice` | Transfer ECG interpretation into clinical context, prioritization, calibration, and action categories | Context is withheld until a first-look commitment; reason-me-back feedback follows the decision; only reviewed, compatible case families can earn clinical-application evidence |

Guided exits publish typed cross-mode destinations. `frontend/src/lib/learning/handoffTargets.ts` resolves narrow teaching competencies to explicit eligible corpus families. A destination validates the returned target before recording a receipt. If there is no compatible case, the platform shows an unavailable state and preserves the return route; it does not substitute an unrelated case.

## 4. AI-first tutoring and adaptive competency model

### Tutor behavior

The configured OpenAI-compatible tutor model is `gpt-5.6-luna`, with deployment configuration in the backend environment. The AI layer is deliberately separated from ECG truth:

- The tutor may explain, ask Socratic questions, quiz, summarize, and request validated viewer actions.
- It may not invent or override diagnoses, measurements, intervals, lead findings, fiducials, ROIs, or curation tiers.
- Structured responses are schema-validated; malformed output falls back to grounded guidance.
- Viewer actions are allow-listed and rejected when their lead or time window is absent from the active case packet.
- Unsupported claims trigger explicit uncertainty/refusal behavior rather than being presented as findings.

The implementation is documented in `docs/AI_GROUNDING_AND_SAFETY.md` and lives primarily in `backend/app/llm.py`, `frontend/src/components/TutorChat.tsx`, and the tutor contract attached to every production scene.

The tutor supports multi-turn threads and learner-driven tangents. When a question leaves the lesson, the active scene, viewer state, draft, evidence, and response are preserved. The model handles the tangent, while the application supplies the deterministic scene/action/lead return waypoint; “Return to lesson” restores the instructional thread instead of restarting it.

### Exact concept × subskill adaptation

The learner record separates the ECG concept from the skill being demonstrated. The eight tracked subskills are:

1. recognize;
2. localize;
3. measure;
4. discriminate;
5. explain mechanism;
6. synthesize;
7. apply in context;
8. calibrate confidence.

`backend/app/storage.py` persists formative and independent values for each exact pair. Assistance, hints, attempts, confidence, high-confidence errors, evidence level, case provenance, and case eligibility affect the receipt. A scaffolded success can improve formative evidence without falsely increasing independent mastery; an authored model may prove mechanism while remaining ineligible to prove visual recognition; clinical application requires reviewed clinical content.

`backend/app/adaptive.py` selects the next explicit competency using exact subskill mastery when supplied, high-confidence error history, attempt count, spacing, corpus availability, case clarity, and recent-case avoidance. This supports the requested behavior of feeding additional RBBB discrimination or localization cases when that exact competency is weak, then interleaving other material as evidence improves. It is a transparent scheduling heuristic, not a psychometrically validated declaration of clinical competence.

## 5. Corpus realism, provenance, and data governance

The complete manifest at `data/ecg_corpus/manifest.json` reports:

- 21,799 total PTB-XL records;
- 16,636 Tier A cases;
- 4,521 Tier B cases;
- 642 Tier C cases;
- **21,157 student-facing Tier A/B cases**;
- 100 Hz waveform sampling in the current build;
- PTB-XL+ fiducial metadata spanning all 12 standard leads.

The corpus combines PTB-XL waveforms/labels/reports with independent PTB-XL+ 12SL statements, measurements, and fiducials. `backend/app/curation.py` assigns reliability per concept rather than per ECG globally:

- **Tier A:** clean, high-confidence teaching case with concordant evidence;
- **Tier B:** usable practice case with cautious feedback;
- **Tier C:** uncertain or discordant and not student-facing;
- **Tier D:** unsupported and not surfaced.

Tiering, selected evidence rules, and the non-diagnostic use of neutral fiducial regions are documented in `docs/AUTONOMOUS_CURATION.md`. The LLM cannot alter eligibility. The runtime only serves a corpus whose manifest is complete, preventing an interrupted build from becoming the live teaching source.

The corpus is wide but not uniform. For example, rate and QT have 21,157 eligible cases, while Mobitz I, third-degree AV block, ST elevation, and Mobitz II are much sparser. The platform therefore reports concept-specific availability and uses locks or authored mechanism models where appropriate; “21,157 cases” is never treated as 21,157 valid examples of every pathology.

## 6. Honest locks and evidence boundaries

Several high-value lanes remain intentionally locked or formative because a resting/chronic PTB-XL ECG cannot establish the required temporal, clinical, or action evidence:

- evolving acute STEMI or a new acute coronary event;
- serial change without a true paired prior/current source;
- transient onset/offset events that require telemetry or a rhythm stream;
- VT/VF/arrest and full ACLS/resuscitation performance;
- pulse, perfusion, hemodynamic stability, or symptom causation from the tracing alone;
- drug causality, electrolyte value, or patient-specific medication action without the required medication/laboratory/context evidence;
- culprit-vessel, treatment, or device-programming claims beyond the reviewed evidence ceiling.

These topics are still taught as source-boundary reasoning: learners identify what a resting 12-lead can establish, which additional source is required, and why. They do not receive false independent or clinical mastery for acknowledging unavailable evidence. Acute/serial, telemetry, resuscitation, and electrolyte-linked tracks require licensed supplemental data and versioned clinical review before they should unlock.

Automated clinical harness status is also not represented as human clinician approval. Generated stems, action policies, rationales, distractors, acuity caps, and pilot items require formal, versioned content review before a student-facing clinical pilot.

## 7. Learner-persona testing and remediation

Three independent personas used the live localhost product directly through Chromium/Playwright at desktop, 13-inch laptop, and mobile sizes. Reports and evidence screenshots are in:

- `docs/persona-tests/NOVICE_LIVE_REPORT.md`
- `docs/persona-tests/CLERK_LIVE_REPORT.md`
- `docs/persona-tests/ADVANCED_LIVE_REPORT.md`
- `docs/persona-tests/screenshots/`

The app-integrated browser did not expose an attachable tab during these runs, so the personas used an isolated direct local-browser workflow against the same live site. This is a test-tool limitation, not a product failure.

### Novice perspective

The first pass found an unrelated M2-to-Training handoff, overly literal semantic grading, ambiguous keyboard labels, a compressed mobile ECG, source metadata clutter, conflicting duration copy, and a transient loading failure state. Retest confirmed the high-impact paths were repaired: the exact lead-territory drill is preserved, natural first-principles explanations are accepted, vector polarity is explicitly elicited, the scene map collapses on mobile, the ECG remains legible without document-level overflow, and technical source mapping is moved behind disclosure. The final retest also found that a deep-linked mobile scene initially landed above the module overview; restoration now moves focus and scroll directly to the selected scene below the fixed navigation.

### Clerkship perspective

The first pass found cross-mode receipts that could describe a concept not actually practiced, clinical context that disclosed the answer before ECG commitment, disappearing return navigation, active tutors in scenes described as independent, contradictory unavailable states, and an unrealistic ward typing burden. Retest confirmed that handoffs now map transparently or fail closed, PR/QRS boundaries launch a real PR measurement drill, tachyarrhythmia handoff launches a grounded AF-family case, clinical context stays masked until first-look commitment, independent tutors start collapsed, ward time is more realistic, and return navigation persists during active Rapid and Clinical sessions.

### Advanced/educator perspective

The first pass deliberately attacked evidence integrity. It found that an off-panel caliper could receive credit, the QTc arithmetic scene lacked usable inputs, a locked ischemia-mimic comparison rendered as a prose proxy, and static feedback could claim actions the learner had not performed. Retest confirmed the blockers were fixed: visible lead-panel/ROI overlap is required for QRS evidence; the authored vector model no longer receives localization credit; Bazett 450 ms and Fridericia 418 ms are reproducibly accepted from the displayed QT 360 ms/RR 640 ms inputs; the locked mimic scene renders evidence-boundary acknowledgements rather than fake comparison fields; and M10 feedback is response-neutral when the answer pattern does not support a more specific claim.

The educator retest retained one small accessibility/usability note about aligning a prefilled caliper boundary with its input step base. Final polish now initializes precise entry from the reviewed sampled ROI rather than an arbitrary percentage of the visible panel, eliminating the internally inconsistent default without weakening the waveform-bound evidence gate.

## 8. Automated QA evidence

Latest completed verification evidence for this implementation:

| Check | Result | Coverage emphasis |
| --- | --- | --- |
| Backend pytest suite | **135 passed** | ingestion, curation, packets, grading, exact/subskill mastery, replay-safe evidence, pathway persistence, adaptive selection, tutor safety, cookie auth/throttling/isolation, objective coverage, clinical first-look/context boundary/stepwise grading/shift behavior, synthetic-waveform provenance, and fail-closed handoffs |
| Frontend TypeScript and Next.js production build | **Clean** | typed curriculum/runtime, all production routes, server/client boundaries, and static generation |
| Full Playwright suite | **31 passed** in the final clean run | dashboard/auth, all four modes, production curriculum registry, guided interactions, tangent/return, cross-mode handoffs, the complete ten-case Training recipe, caliper/trace-proof integrity, keyboard alternatives, learner isolation, mobile/responsive layout, server-enforced Clinical first-look masking/stepwise flow, and grounded AI debriefs |

The final 31-test Playwright run completed against the full 21,799-record corpus after authenticated pathway sync, the ten-case no-repeat Training set, Rapid trace proof/refresh recovery, server-enforced Clinical context reveal, stepwise simulation, and Profile objective-matrix work. All 31 tests passed in 1.7 minutes. The browser suite lives in `frontend/e2e/`, including dedicated specs for Guided, Training, Rapid, Clinical, Foundations accessibility, production-registry coverage, persona isolation, and responsive visuals.

Curriculum correctness is also enforced at application load. `frontend/src/lib/learning/validateCurriculum.ts` checks module count/order, prerequisite references, source citations, §11 subtopic-to-scene coverage, interaction integrity, feedback and accessibility contracts, case fallback safety, completion references, tutor contracts, layout contracts, and handoff presence. The registry throws if validation produces an issue rather than silently shipping a partially mapped curriculum.

## 9. Current implementation boundary and release posture

### Implemented and demonstrable

- Ten source-audited guided modules with 118 routed scenes and ~84k words of detailed storyboard copy.
- Four distinct but connected learning modes.
- Realistic calibrated ECG rendering from a large real-record corpus.
- Trace-native interactions, including drawing, regions, calipers, lead selection, vectors, marching, calculations, comparisons, and clinical stages.
- Grounded multi-turn AI tutoring with Socratic guidance, validated viewer actions, tangent support, preserved work, and exact return.
- Exact concept × subskill formative/independent records and adaptive selection.
- Typed cross-mode handoffs that validate the destination or fail closed.
- Separate pathway completion and competency evidence.
- Automated source-coverage validation and broad backend/browser regression suites.

### Required before a formal student pilot or competence claim

- Versioned clinician review of all clinical policies and every production assessment item.
- Supplemental licensed acute/serial, telemetry, paired-ECG, arrest/resuscitation, and laboratory-linked datasets.
- Expansion of the real-record Clinical Decisions bank beyond the currently narrow reviewed families.
- Formal accessibility audit, learner timing studies, and usability validation across assistive technologies.
- Delayed-retention, item-difficulty, morphology-diversity, and prospective educational validation of the mastery model.

The appropriate release description is therefore: **a comprehensive AI-first ECG learning implementation with strong curriculum traceability, realistic waveform practice, and conservative evidence governance; suitable for supervised curriculum/content evaluation, but not yet a clinically reviewed or psychometrically validated certification product.**
