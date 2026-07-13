# TRACE verbatim production storyboard — Modules 07–10

**Locked architecture:** ten guided modules; this artifact owns M7–M10 only.  
**Modules covered:** M7 Chambers, Voltage, and R-Wave Progression; M8 Repolarization, QT, Drugs, Electrolytes, and Nonischemic ST–T; M9 Ischemia, Infarction, Localization, and Mimics; M10 Integrated Interpretation and Clinical Transfer.  
**Artifact status:** implementation-ready copy, interaction, grading, responsive-layout, accessibility, grounding, and cross-mode contract. Text in quotation marks is literal learner-facing copy. Bracketed tokens such as `[lead]`, `[value]`, `[case]`, and `[finding]` are deterministic case-packet substitutions, never model-authored text.  
**Clinical boundary:** educational use only. The ECG/case packet and versioned deterministic rubric are the source of truth. Luna may explain approved content and preserve a tangent, but it may not invent findings, measurements, diagnoses, clinical facts, regions of interest, or action keys.  
**Data boundary:** PTB-XL/PTB-XL+ supports resting/chronic teaching. Acute/evolving/serial, telemetry, torsades, VT/VF arrest, and resuscitation mastery stay visibly locked until a suitable licensed corpus, validation, and named clinical review exist.

---

## 0. How to use this production packet

Every scene below is a Storyline-inspired stateful lesson implemented in the app shell, not a slide deck and not a generic multiple-choice substitute. Each scene contains one primary ECG/model manipulation that gates completion. Explanatory layers, triggers, visited/completed states, retry layers, and preserved variables may resemble Storyline 360 authoring, while the actual viewer remains data-native, responsive, keyboard operable, and screen-reader compatible.

The production team must treat the following words precisely:

- **Real teaching ECG** means a source waveform whose case contract supports every scored claim.
- **Teaching model — not a patient tracing** means a deterministic causal simulation. It may build understanding but cannot create real-clinical-pattern mastery.
- **Authored clinical context** means vignette data written separately from the ECG and explicitly disclosed.
- **Independent** means no hint, no answer-revealing tangent, and no equivalent retry before the successful attempt.
- **Assisted** means the scene can complete for learning progression, but the evidence is not recorded as independent mastery.
- **Not assessable** is a substantive answer, not an escape hatch. It scores only when the manifest intentionally withholds, obscures, or makes incomparable the required evidence.

### 0.1 Exact source-reference registry

| Ref | Exact source |
|---|---|
| `SPEC-ONTOLOGY` | `ECG_PLATFORM_SPEC.md:305-347` |
| `SPEC-ISCHEMIA-ELIGIBILITY` | `ECG_PLATFORM_SPEC.md:397-405` |
| `SPEC-CHAMBER-ELIGIBILITY` | `ECG_PLATFORM_SPEC.md:407-413` |
| `SPEC-QT-ELIGIBILITY` | `ECG_PLATFORM_SPEC.md:415-423` |
| `SPEC-VIEWER` | `ECG_PLATFORM_SPEC.md:491-600` |
| `SPEC-GUIDED-MINIMUM` | `ECG_PLATFORM_SPEC.md:618-665` |
| `SPEC-FRAMEWORKS` | `ECG_PLATFORM_SPEC.md:669-695` |
| `SPEC-RAPID` | `ECG_PLATFORM_SPEC.md:699-719` |
| `SPEC-TRAIN` | `ECG_PLATFORM_SPEC.md:722-741` |
| `SPEC-MASTERY` | `ECG_PLATFORM_SPEC.md:760-785` |
| `SPEC-MISCONCEPTIONS` | `ECG_PLATFORM_SPEC.md:789-806` |
| `ARCH-M7` | `docs/storyboards/CURRICULUM_ARCHITECTURE_RECOMMENDATION.md:153-167` |
| `ARCH-M8` | `docs/storyboards/CURRICULUM_ARCHITECTURE_RECOMMENDATION.md:169-184` |
| `ARCH-M9` | `docs/storyboards/CURRICULUM_ARCHITECTURE_RECOMMENDATION.md:186-202` |
| `ARCH-M10` | `docs/storyboards/CURRICULUM_ARCHITECTURE_RECOMMENDATION.md:206-221` |
| `ARCH-M6` | `docs/storyboards/CURRICULUM_ARCHITECTURE_RECOMMENDATION.md:134-149` |
| `ARCH-MODE-HANDOFF` | `docs/storyboards/CURRICULUM_ARCHITECTURE_RECOMMENDATION.md:265-294` |
| `INV-R-ISCH` | `docs/storyboards/SOURCE_CONTENT_INVENTORY.md:43` |
| `INV-R-CHAMBER` | `docs/storyboards/SOURCE_CONTENT_INVENTORY.md:44` |
| `INV-R-QT` | `docs/storyboards/SOURCE_CONTENT_INVENTORY.md:45` |
| `INV-R-VIEW` | `docs/storyboards/SOURCE_CONTENT_INVENTORY.md:46` and `:193-209` |
| `INV-R-NORMAL` | `docs/storyboards/SOURCE_CONTENT_INVENTORY.md:38` |
| `INV-R-PRECISION` | `docs/storyboards/SOURCE_CONTENT_INVENTORY.md:55` |
| `INV-R-SYNTH` | `docs/storyboards/SOURCE_CONTENT_INVENTORY.md:48` |
| `INV-R-CHRONIC` | `docs/storyboards/SOURCE_CONTENT_INVENTORY.md:50` |
| `INV-R-STAFF` | `docs/storyboards/SOURCE_CONTENT_INVENTORY.md:51` |
| `INV-R-AUTHCTX` | `docs/storyboards/SOURCE_CONTENT_INVENTORY.md:52` |
| `INV-R-TRANSIENT` | `docs/storyboards/SOURCE_CONTENT_INVENTORY.md:53` |
| `INV-R-CLINREV` | `docs/storyboards/SOURCE_CONTENT_INVENTORY.md:54` |
| `FOUND-ST-QT` | `foundations/MODULE_TEXT.md:80-87`, `:161-165`, `:189-192`; `docs/storyboard-foundations.md:159-168` |
| `FOUND-SWEEP` | `foundations/MODULE_GUIDE.md:28-31`, `:93-96`; `foundations/MODULE_TEXT.md:105-116` |
| `V2-CHAMBERS` | `docs/CURRICULUM_STORYBOARD_SYSTEM_V2.md:235-238` |
| `V2-REPOLARIZATION` | `docs/CURRICULUM_STORYBOARD_SYSTEM_V2.md:260-278` |
| `V2-ISCHEMIA` | `docs/CURRICULUM_STORYBOARD_SYSTEM_V2.md:280-299` |
| `V2-INTEGRATION` | `docs/CURRICULUM_STORYBOARD_SYSTEM_V2.md:301-318` |
| `CLIN-MODES` | `docs/storyboard-clinical-case.md:22-40`, `:148-159`, `:208-214`, `:244-258` |
| `CLIN-GROUNDING` | `docs/storyboard-clinical-case.md:78-100`, `:197-204`, `:231-239` |
| `CLIN-DISPLAY` | `docs/storyboard-clinical-case.md:208-214`, `:260-261` |
| `CLIN-GRADING` | `docs/storyboard-clinical-case.md:197-204`, `:220-243`, `:260-269` |

Any numerical chamber criterion, QT-risk threshold, ischemia threshold, drug-risk category, action category, or safety action also requires a criterion-level reference, named clinical owner, reviewer, version, and review date in the item manifest. This storyboard deliberately does not convert the unsigned values in `docs/clinical-content-tables-review.md` into authoritative copy.

## 1. Shared production frame

### 1.1 Exact global chrome and persistent controls

- Breadcrumb: “Learn / Guided modules”
- Tutor header: “Luna · guided tutor”
- Grounding status: “Grounded to this scene and teaching case”
- Tutor input placeholder: “Ask why, ask for another explanation, or follow a tangent…”
- Tutor controls: “Ask Luna” · “Hint” · “Return to lesson”
- Reference control: “Sources and limits”
- Case-evidence drawer: “Why this case is eligible”
- Provenance badges: “Real teaching ECG” · “Teaching model — not a patient tracing” · “Authored clinical context” · “Classification intentionally limited”
- Viewer controls: “Zoom” · “Pan” · “Calipers” · “Mark region” · “Compare leads” · “Reset view” · “Show full 12-lead”
- Scene navigation: “Back” · “Continue”
- Locked footer: “Complete the waveform task to continue.”
- Incomplete-submit message: “Your answer is not submitted yet. Complete the highlighted waveform action first.”
- Complete footer: “Checkpoint complete. Continue when you’re ready.”
- Persistence toast: “Progress saved.”
- Retry control: “Try an equivalent tracing”
- Uncertainty control: “Not assessable from the provided data”

The module rail shows four statuses with literal accessible labels: “Not started,” “In progress,” “Completed with help,” and “Completed independently.” A skipped scene displays “Skipped — not mastered.”

### 1.2 Desktop, laptop, and mobile layout

**Desktop, 1280 px and wider.** A 72 px header sits above a 12-column workspace. A 216 px module rail occupies columns 1–2; the learning stage occupies columns 3–9; Luna occupies columns 10–12 at 340–380 px. A full tracing is never narrower than 680 px. Explanatory copy is above or beside the waveform and never overlays waveform ink. The primary manipulation sits directly beneath or on the relevant lead panels. The scene footer is sticky inside the stage, not across Luna.

**Laptop, 900–1279 px.** The module rail becomes a one-line scene strip beneath a 60 px header. The stage uses seven columns and Luna five. “Focus tracing” collapses Luna to a 48 px edge tab labeled “Reopen Luna.” The tracing stays at least 560 px wide. There is no horizontal page scroll; only the ECG board itself may pan.

**Mobile, 360–899 px.** Order is title → essential copy → ECG/model → manipulation → feedback → “Ask Luna” bottom-sheet trigger → navigation. Luna opens as a 92% height sheet and returns focus to its trigger when closed. Full 12-leads use a horizontally pannable board with a persistent lead mini-map; a construct-valid target lead may open first, but “Show full 12-lead” remains available unless the case contract declares `testedScope: rhythm_only`. The waveform is never scaled below legible small-box spacing; the learner pans instead. All targets are at least 44×44 px. Compare scenes stack matched lead panels at identical scale rather than shrinking them side by side.

### 1.3 Storyline-style layers, state machine, and transition copy

Every scene implements these deterministic states:

1. `briefing`: title, goal, exact lesson copy, source/limit badge, and Luna opening appear. “Continue” is disabled.
2. `predict`: the learner commits a direction, boundary, evidence target, or hypothesis before any causal reveal.
3. `manipulate`: the model/viewer changes only from learner input. No animation autoplays and no answer is revealed.
4. `commit`: waveform marks, structured evidence, conclusion, and confidence are editable until “Submit evidence.”
5. `feedback`: the grading engine selects one exact authored branch and highlights only manifest-backed evidence.
6. `retry`: a local boundary error may be corrected once on the same case. A conceptual or critical error loads a contract-matched equivalent case.
7. `complete`: a mastery receipt is written; “Continue” unlocks; cross-mode cards appear.
8. `tangent`: viewport, annotations, draft, timer, and state are frozen. Nothing is submitted, cleared, or advanced.

Exact transition strings:

- `briefing → predict`: “Make a prediction before you reveal the mechanism.”
- `predict → manipulate`: “Prediction saved. Test it on the waveform.”
- `manipulate → commit`: “Now prove your conclusion on the ECG.”
- `commit → feedback`: “Evidence submitted.”
- `feedback → retry`: “The answer stays hidden while you try an equivalent example.”
- `feedback → complete`: “Checkpoint complete. Your evidence receipt is saved.”
- Data-contract failure: “This case cannot support the promised task. It has been removed from your session and will not affect mastery.”

Animations use 250–450 ms state transitions, learner-controlled scrubbers, and a visible “Pause animation” control. No mandatory waiting, pulsing target, parallax, confetti, or auto-pan is permitted. Reduced motion replaces animation with numbered static states and “Previous step” / “Next step.”

### 1.4 Luna exact tangent-and-return contract

The configured communication model may be presented as Luna. A GPT 5.6-class provider may serve the surface when available and approved, but the provider name is not hard-coded into scoring or case truth.

Exact wrapper copy:

- Tangent entry: “Let’s take that tangent. I’ll keep your exact place in this scene.”
- Concept answer close: “Want one more turn on that, or return to the paused task?”
- Later-module redirect: “That question matters, and it has its own evidence rules in [module]. I can give you a short preview now, then return you to [paused task].”
- Prior-module repair: “The missing step is [prerequisite]. I can reopen the two-minute repair without losing this scene.”
- Unsupported case claim: “I can explain the general concept, but this case packet does not support that finding. I won’t point to it on this tracing.”
- Real-person request: “I can’t assess a real person, symptoms, or an uploaded ECG here. If this may be urgent, use local emergency or clinical services. In this lesson, I can help you reason from the teaching tracing.”
- Management boundary: “That decision depends on a real patient, local protocol, and clinician review. Here we can identify supported ECG evidence and choose only a reviewed educational action category.”
- Return button: “Return to lesson”
- Return confirmation: “You’re back exactly where you paused. Nothing was submitted or reset.”

For an approved tangent, Luna may generate at most 120 words from the scene knowledge card and cited prerequisite cards. It must label case-specific versus general statements, end with the concept-answer close, and emit viewer actions only from approved case-packet ROIs. A schema validator and claim allowlist run before display. A hint reveals a reasoning step, never a label; using it changes the attempt to `assisted`.

### 1.5 Common case-packet and ECG evidence contract

Every scored scene packet must include:

```text
caseId; sourceRecordId; sourceType; provenance; licenseStatus;
samplingHz; paperSpeed; gain; leadOrder; leadAvailability; signalQuality;
testedScope; acceptedLeads; requiredMeasurements; measurementSources;
fiducials; acceptedROIs; ambiguityFlags; allowedClaims; forbiddenClaims;
criteriaPolicyId; criteriaPolicyVersion; clinicalReviewStatus;
authoredContextFields; contextProvenance; answerRubricVersion;
equivalentCaseFamily; difficultyVector; accessibilityTranscript.
```

Hard gates:

- A chamber-pattern case requires voltage and/or axis plus a compatible statement; one weak criterion cannot support a confident diagnosis.
- A QT case requires QT and QTc sources, rate, formula/source confidence, and no missing required measure. Fine boundary scoring requires a high-rate signal or validated median/fiducial path; a 100 Hz trace may be used for broad morphology, not false millisecond precision.
- An ischemia/localization case requires compatible diagnostic evidence and lead-level/territory evidence. Without it, only descriptive ST–T practice is allowed.
- A serial/new/dynamic claim requires genuinely comparable ECGs and either a validated serial source or a prior that proves change. PTB-XL records may not be presented as acute evolution.
- A transient rhythm/resuscitation claim requires a real rhythm stream or validated telemetry/simulation source and separate mastery axis. A resting 12-lead never supplies code mastery.
- Any scored clinical action requires `clinicalReviewStatus: approved`, a named owner/reviewer, a current policy version, and action/safety tokens. If any are absent, the action layer is disabled and the scene ends at interpretation plus “what information is needed.”

### 1.6 Shared deterministic grading and exact branch semantics

The language model never grades. The engine uses fiducial tolerance, ROI geometry, accepted lead sets, structured reasoning tokens, allowed/forbidden claims, confidence, and the versioned rubric.

- `correct_independent`: all required evidence and conclusion pass without help. Records full independent evidence.
- `correct_assisted`: final work passes after a hint or answer-revealing tangent. Completes the lesson but records assisted evidence only.
- `partial`: at least one required axis passes and no critical/unsafe claim is committed. Missing evidence remains visible; label stays locked.
- `wrong`: evidence or conclusion conflicts with the packet. A local boundary error gets one same-case correction; conceptual errors require an equivalent case.
- `unsafe_or_unsupported`: a treatment order, false urgency, unsupported acute/causal claim, or confident specificity beyond the evidence. It records a safety/calibration error and requires an equivalent case.
- `not_assessable_correct`: the packet intentionally makes the requested claim unavailable/ambiguous, and the learner states the supported remainder plus needed datum.
- `not_assessable_incorrect`: required evidence is readable and valid, so the learner must perform the waveform task.
- `data_contract_fail`: the platform—not the learner—failed. No score is written.

Shared confidence labels are “Low,” “Moderate,” and “High.” Confidence locks at submission. High-confidence wrong/unsafe work receives the larger calibration decrement specified by `SPEC-MASTERY`; low-confidence correct work opens a brief evidence recap but remains correct.

Every equivalent retry must use a different source record or deterministic model seed, preserve the same objective and evidence completeness, vary at least two nuisance dimensions, and never repeat the decisive ROI location. The original answer remains hidden until the retry is committed.

### 1.7 Shared accessibility behavior

- Keyboard: `Tab` follows visual order; arrow keys move a selected caliper/marker by one small box and `Shift`+arrow by five; `Enter` anchors; `Space` plays/pauses; `Escape` closes a layer or returns from magnification. Every drag has tap/select plus stepper alternatives.
- Touch: visual handles are 24 px within 44 px targets. First tap selects/zooms; second tap places; “Confirm mark” prevents accidental submission. Pinch is optional, never required.
- Screen reader: every waveform has a synchronized structured lead/beat/time/amplitude representation. Marks announce through a polite live region; submitted feedback uses an assertive live region. Evidence is announced before interpretation.
- Reduced motion: vector sweeps, morphology morphs, overlays, and lead pulses become static numbered frames. No information depends on motion.
- Color is always redundant with label, line style, icon, and position. Contrast meets WCAG AA. At 200% zoom, no control or copy overlaps the waveform.
- Timed experiences are never introduced in these guided scenes. Cross-mode timer accommodations change time, not the tested skill.

### 1.8 Realistic ECG rendering contract

- Real cases render from source waveform samples, never a redrawn approximation or decorative image. Source paper speed, gain, calibration, sampling rate, filters when known, lead order, and simultaneous/sequential acquisition structure remain in the manifest.
- The viewer maps time and amplitude physically. At standard display, 1 mm corresponds to the configured 40 ms at 25 mm/s and 0.1 mV at 10 mm/mV; other speed/gain settings must change both grid and measurement engine together and be labeled.
- Minor and major grid lines remain legible but subordinate to waveform ink. The trace uses subpixel antialiasing without smoothing away notches, pacing spikes, QRS onset, J point, terminal T, or artifact. Downsampling uses a peak-preserving renderer, not simple point dropping.
- A full 12-lead uses clinically recognizable lead labels and grouping, a visible calibration pulse when present, and a pinned long rhythm lead where the task needs time. Median beats are labeled “Representative median beat”; they are never shown as authentic beat-to-beat rhythm.
- At high zoom, the renderer exposes source samples and interpolation status. A 100 Hz derivative cannot display invented millisecond detail; fine-boundary scenes require the validated high-rate/fiducial path.
- Teaching models use the same calibrated renderer and plausible continuous morphology, but retain the permanent badge “Teaching model — not a patient tracing.” A model control may alter only the declared causal parameter; it cannot silently morph unrelated features.
- Rendering QA includes pixel-to-coordinate tests, calibration tests, lead-order tests, high-DPI and 200% zoom snapshots, touch-pan tests, and a clinician visual review of representative normal, narrow/wide QRS, low/high voltage, ST–T, QT/U-wave, pacing, and artifact examples before release.

### 1.9 Adaptive cross-mode publication contract

Every completed scene emits a deterministic learning receipt: `objectiveId`, `evidenceAxes`, `independence`, `attemptCount`, `hintLevel`, `misconceptionId`, `confidenceCalibration`, `caseId`, `lastSeenAt`, `nextEligibleAt`, `remediationSceneId`, and eligible `trainPool`, `rapidPool`, and `clinicalFamily` identifiers.

- Train prioritizes the weakest evidence axis and samples target, close mimic, and normal/variant examples. It may focus on the weak concept, but after two same-objective cases it interleaves one previously stable objective to test discrimination rather than cue-driven repetition.
- Rapid samples whole ECGs with no announced target. A weak objective increases its probability but does not make every case the same label. Luna remains silent until submission.
- Clinical receives a case only when ECG truth, authored context, action rubric, clinical review, and tested scope all pass. A locked clinical family remains visible with its reason and does not fall back to a fabricated vignette.
- Repeated correct independent work raises spacing and variation. Assisted or retry success schedules an earlier independent equivalent. High-confidence wrong work schedules a close mimic plus the exact remedial scene.
- Exact adaptive card copy: “Next because: [weak/stale/underexposed objective].” Secondary line: “You will see a different ECG and a close alternative; the target will not be announced.”
- Learner override control: “Choose a different focus.” It changes the next eligible objective, never its grading standard or case-validity gate.

---

# M7 — Chambers, Voltage, and R-Wave Progression

**Module card copy:** “Follow how atrial shape, ventricular mass, direction, distance, and lead placement change the signal. Use chamber criteria as evidence—not as anatomy proven by one number.”  
**Estimated guided time:** “50–65 min · self-paced”  
**Prerequisite receipt:** M2 lead vectors/axis/R-wave progression and M5 conduction/secondary ST–T.  
**Exit receipt:** atrial and ventricular chamber evidence, R-wave progression description, primary-versus-secondary recovery distinction, and calibrated uncertainty.  
**Persistent connection chip:** “M2 explains where the force points. M5 explains how activation changes recovery. M7 asks how much chamber evidence the tracing truly supports.”

## M7-S0 — Voltage is a projection, not a heart-size ruler

**Source refs:** `SPEC-CHAMBER-ELIGIBILITY`; `SPEC-VIEWER`; `ARCH-M7`; `V2-CHAMBERS`; `INV-R-SYNTH`.  
**Eyebrow/title:** “M7 · 1 of 8” / “Voltage is a projection”  
**Goal line:** “Predict how mass, direction, distance, and lead position alter the recorded signal.”

**Exact lesson copy:**

> “A lead records the projection of electrical activity toward or away from it. More activated muscle can increase voltage, but so can a better-aligned vector or a closer electrode. Distance, tissue, lead position, activation sequence, and cancellation can reduce it. Voltage is evidence about electrical forces—not a direct measurement of wall thickness.”

**On-screen model labels:** “Muscle contributing to the vector” · “Vector direction” · “Electrode distance” · “Lead position” · “Recorded amplitude” · “Hold other variables constant.”

**Case contract:** Deterministic torso/vector model, always badged “Teaching model — not a patient tracing.” It exports wall-mass parameter, net vector, lead coordinates, distance/attenuation parameter, and expected amplitude in I, aVL, V1, V3, V5, and V6. It cannot emit a hypertrophy diagnosis.

**Layout delta:** Desktop/laptop shows the torso model on the left, synchronized lead panels on the right, and a one-variable-at-a-time tray below. Mobile presents three numbered cards—“Change mass,” “Change direction,” “Change distance”—with the current lead fixed above the controls.

**Required interaction:** The learner predicts “larger,” “smaller,” or “may change direction” for each manipulation; then changes only the requested variable and places an amplitude caliper on the resulting lead. Final action: drag the four causal chips into “can change voltage” while leaving “proves wall thickness” outside the evidence frame.

**Tutor script:**

- Opening: “Change one cause at a time. Predict the lead’s response before moving the control.”
- Socratic: “If wall mass stays constant but the vector turns away from a lead, what should that lead record?”
- Hint 1: “A lead sees only the component of the vector aligned with that lead.”
- Hint 2: “Distance and intervening tissue alter the recorded amplitude without changing the myocardium.”
- Tangent return: “Back to [variable]: keep the other three controls fixed, then measure [lead].”

**State changes and deterministic gate:** `predict` locks all sliders until a direction is committed. `manipulate` enables one requested slider only. The amplitude caliper must land within ±0.05 mV of model truth. Completion requires four correct cause→signal predictions and rejection of “proves wall thickness.”

**Exact feedback branches:**

- Correct independent: “Exactly. Mass, vector alignment, distance, and lead position can all alter voltage. The tracing supplies electrical evidence; anatomy still needs corroboration.”
- Correct assisted: “That is now correct. Because you used a hint, this scene is complete with help and will return once in Train.”
- Partial: “You isolated [credited variable], but [uncontrolled variable] also moved. Reset and test one cause at a time.”
- Wrong: “The vector now points [toward/away from] [lead]. Predict the projection before using amplitude as a size claim.”
- Unsafe/unsupported: “That conclusion outruns the model. No simulated voltage alone proves hypertrophy or dictates treatment. Return to the cause→signal relationship.”
- Not assessable—correct: “Not assessable would be correct for wall thickness. The model does expose voltage and each causal control, so the signal change is assessable.”
- Not assessable—incorrect: “The requested variable and amplitude are available in the model. Measure the change.”

**Equivalent retry:** New torso rotation, different target lead, and different baseline distance; the requested causal sequence is shuffled.

**Accessibility specifics:** Each slider has named presets and numeric steppers. The vector has text alternatives “toward,” “away,” and “perpendicular.” Reduced motion replaces the moving vector with before/after frames. Screen reader announces, for example, “Lead aVL amplitude increased from 0.6 to 1.0 millivolts; mass unchanged.”

**Cross-mode handoff:** Connection cards: “Back to M2 · projection” / “Ahead to M7-S2 · voltage criteria need corroboration.”

## M7-S1 — Atrial enlargement: read the P wave as distributed evidence

**Source refs:** `SPEC-ONTOLOGY`; `SPEC-CHAMBER-ELIGIBILITY`; `SPEC-VIEWER`; `ARCH-M7`; `V2-CHAMBERS`; `INV-R-CHAMBER`.  
**Eyebrow/title:** “M7 · 2 of 8” / “Atrial evidence lives in P-wave shape”  
**Goal line:** “Use lead II and V1 morphology without turning one P-wave feature into an anatomical certainty.”

**Exact lesson copy:**

> “The P wave combines right- and left-atrial activation. Lead II helps show its overall duration and contour; V1 often separates an initial anterior/rightward component from a terminal posterior/leftward component. Broad, notched, tall, or prominent terminal components are clues. They support an atrial-abnormality pattern only when the signal, calibration, lead identity, and corroborating evidence are trustworthy.”

**Clinical connection card:** “Atrial-pattern evidence can fit chronic pressure or volume loading, but the ECG does not establish the cause. Echo, history, rhythm, and prior ECGs can change the interpretation.”

**Case contract:** Three paired P-wave examples: normal reference, left-atrial-abnormality-compatible, and right-atrial-abnormality-compatible. A real case is scoreable only when a compatible statement/label plus readable P morphology or validated P fiducials exist; high-rate waveform or validated median beat is required for duration/terminal-component precision. Required leads II and V1; calibration and noise status mandatory. If the corpus cannot meet the contract, use a labeled model and record causal-learning evidence only.

**Layout delta:** Linked lead-II and V1 magnifiers sit above a two-row atrial timeline. Mobile uses a synchronized “II / V1” toggle; both marks remain visible in the evidence tray.

**Required interaction:** For each example, the learner marks P onset/end in II, divides the biphasic V1 P wave into initial and terminal portions, and assigns evidence chips to “right-atrial clue,” “left-atrial clue,” “normal/within reference,” or “not reliably measurable.” A label cannot be submitted until the lead-specific marks exist.

**Tutor script:**

- Opening: “Start with the whole P wave in II, then inspect the terminal component in V1.”
- Socratic: “Which part of the V1 P wave points posteriorly and therefore can carry left-atrial evidence?”
- Hint 1: “Use onset and final return to baseline—not the peak—to measure duration.”
- Hint 2: “In V1, separate the initial positive portion from the terminal negative portion before naming a clue.”
- Tangent return: “Back to [case], [lead]: finish the P-wave boundary before assigning the chamber clue.”

**State changes and deterministic gate:** P boundaries snap within the policy card’s signal-appropriate tolerance; at least 60% overlap with each accepted component ROI is required. The criterion card displays only clinician-reviewed, versioned numerical thresholds. Completion requires both leads on all three examples and a confidence ceiling no higher than the packet’s allowed claim.

**Exact feedback branches:**

- Correct independent: “Supported. In [case], [lead-II evidence] and [V1 evidence] together support [normalized atrial-pattern description] at [confidence]. You used morphology across leads rather than a nickname.”
- Correct assisted: “The lead evidence is now complete. This counts as assisted because a hint exposed the component to inspect.”
- Partial: “Your lead-II boundary is supported. The atrial-pattern claim remains locked until you mark the initial and terminal components in V1.”
- Wrong: “You marked the QRS onset as the end of P. Return to the P wave’s final baseline crossing, then re-evaluate its duration and contour.”
- Unsafe/unsupported: “A P-wave clue does not prove a cause, chamber pressure, or treatment need. State the supported atrial pattern and its limitation.”
- Not assessable—correct: “Good restraint. In [case], noise obscures [component], so [specific atrial claim] is not assessable. The supported remainder is [description].”
- Not assessable—incorrect: “Lead [lead] contains a validated readable P-wave component. Mark it before choosing ‘not assessable.’”

**Equivalent retry:** Different rate, P amplitude, starting beat, and clearest V1 morphology; one new intentionally limited example tests restraint.

**Accessibility specifics:** A structured P-wave table exposes onset, end, positive component, and terminal negative component with steppers. Screen reader announces the evidence in temporal order. Touch users tap “Start P,” “End P,” “Split component,” then “Confirm.”

**Cross-mode handoff:** After completion: “Train · P-wave chamber contrasts” and connection chip “M3 reminder · atrial rhythm changes can make chamber morphology harder to assess.”

## M7-S2 — LVH: apply a voltage criterion, then audit its limits

**Source refs:** `SPEC-CHAMBER-ELIGIBILITY`; `SPEC-VIEWER`; `ARCH-M7`; `V2-CHAMBERS`; `INV-R-CHAMBER`; `INV-R-CLINREV`.  
**Eyebrow/title:** “M7 · 3 of 8” / “LVH is an evidence bundle”  
**Goal line:** “Measure voltage correctly, apply a reviewed criterion, and seek corroboration.”

**Exact lesson copy:**

> “LVH voltage criteria compress a three-dimensional signal into a screening rule. Sokolow–Lyon adds S in V1 to the larger R in V5 or V6. Cornell voltage combines R in aVL with S in V3 and interprets the sum using its reviewed context threshold. A positive criterion raises support; it does not measure wall thickness or establish a cause.”

**On-screen criterion card:** “[criterion display name]” / “[formula]” / “Reviewed threshold: [threshold and population context]” / “Policy version [version] · reviewed [date]” / “Use only with standard gain and eligible leads.”

**Corroboration tray labels:** “Voltage criterion” · “Axis/force pattern” · “Lateral repolarization pattern” · “Compatible statement/prior” · “Age/body habitus/athletic context” · “Lead placement and gain.”

**Case contract:** One eligible LVH-compatible real ECG, one high-voltage normal/variant comparison, and one nonstandard-gain or lead-placement trap. Real scoring requires voltage measurements or raw calibrated amplitude, compatible LVH statement/label, no contradictory normal statement, and at least one corroborating field. Required leads V1, V3, V5, V6, aVL plus calibration pulse. Criterion threshold is injected only from an approved policy card; without approval the threshold decision is demonstration-only, while amplitude measurement remains scoreable.

**Layout delta:** Full 12-lead remains visible with a pinned five-lead measurement tray. Desktop/laptop positions the criterion equation beside live numeric calipers. Mobile opens each required lead at identical scale and keeps the running sum pinned above the waveform.

**Required interaction:** The learner verifies gain, measures the required R and S amplitudes from baseline, chooses V5 or V6 according to the larger R, populates one reviewed criterion equation, then selects at least two corroborating/limiting factors from visible case data. Final claim must be one of “supports an LVH pattern,” “voltage positive but insufficient alone,” or “criterion not valid on this recording.”

**Tutor script:**

- Opening: “Check the calibration pulse before adding any millivolts.”
- Socratic: “If the voltage sum crosses a threshold, what second piece of evidence would make the pattern more persuasive?”
- Hint 1: “Measure each deflection from the local baseline, not peak to trough.”
- Hint 2: “The formula tells you which leads to combine; the case contract tells you whether the criterion may be used.”
- Tangent return: “Back to [criterion]: verify gain, then finish [lead] before interpreting the sum.”

**State changes and deterministic gate:** Calibration must be identified correctly before amplitude tools unlock. Amplitude accepted within ±0.1 mV for eligible waveforms. Equation arithmetic is deterministic. A criterion-positive case cannot complete without one corroborating factor and one limitation; the gain trap completes only with “criterion not valid.”

**Exact feedback branches:**

- Correct independent: “Supported. You measured [components], calculated [sum], and interpreted it with [corroboration] plus [limitation]. The strongest defensible wording is: ‘[normalized claim].’”
- Correct assisted: “Your measurement and evidence bundle are now correct. Because a hint identified the formula step, this is assisted completion.”
- Partial: “The voltage sum is correct. Add one corroborating feature and one reason voltage may mislead before the claim can complete.”
- Wrong: “The S wave was measured peak-to-trough. Return to the baseline, measure its depth, and recalculate.”
- Unsafe/unsupported: “Voltage alone does not prove anatomical LVH, hypertension, or a treatment decision. Replace certainty with the supported ECG-pattern wording.”
- Not assessable—correct: “Correct. This recording uses [gain/lead limitation], so the criterion is not valid as displayed. State what must be corrected before measurement.”
- Not assessable—incorrect: “Standard gain and all criterion leads are present. The voltage calculation is assessable; anatomical wall thickness is not.”

**Equivalent retry:** Different eligible criterion, different larger lateral R lead, different body-habitus context, and a new calibration trap.

**Accessibility specifics:** The equation is an accessible form with baseline-to-peak numeric steppers and automatic arithmetic. A lead selector announces amplitude and polarity. No required information is conveyed by tall-versus-short graphics alone.

**Cross-mode handoff:** Buttons: “Train · LVH voltage with mimics” / “Save for M8 · secondary ST–T” / “Clinical preview · pre-op abnormal voltage,” with the Clinical preview disabled until its action rubric is reviewed.

## M7-S3 — RVH: a rightward pattern needs more than a tall R in V1

**Source refs:** `SPEC-CHAMBER-ELIGIBILITY`; `SPEC-VIEWER`; `ARCH-M7`; `V2-CHAMBERS`; `INV-R-CHAMBER`; `SPEC-MISCONCEPTIONS`.  
**Eyebrow/title:** “M7 · 4 of 8” / “Assemble right-ventricular evidence”  
**Goal line:** “Combine frontal direction, precordial balance, and mimic checks.”

**Exact lesson copy:**

> “A dominant R in V1 can reflect rightward ventricular forces, but it can also appear with right-bundle delay, posterior forces, pre-excitation, lead placement, or normal variation. An RVH-compatible ECG pattern becomes stronger when right-axis evidence, the V1 R/S balance, persistent rightward precordial force, and a compatible clinical or diagnostic statement agree.”

**Evidence-board labels:** “Frontal QRS direction” · “V1 R/S balance” · “Progression across V1–V6” · “QRS duration and terminal morphology” · “Lead placement” · “Compatible statement/context” · “Mimic still plausible.”

**Case contract:** Target RVH-compatible case, RBBB mimic, and posterior-force/normal-variant or lead-placement mimic. Target requires compatible RVH statement plus voltage/axis support; all cases require readable I, aVF, V1, V2, V5, V6 and QRS duration. No posterior-infarction label may be keyed here without M9 evidence.

**Layout delta:** Full tracing plus a left-to-right evidence board. Selecting a board cell synchronously magnifies the required lead pair. Mobile uses an ordered checklist with the lead mini-map pinned.

**Required interaction:** Learner estimates axis from I/aVF, measures V1 R and S from baseline, traces R/S balance across the precordial leads, and boxes any terminal RBBB morphology. Learner then assembles “RVH-compatible,” “conduction mimic,” or “evidence limited” from the marked evidence.

**Tutor script:**

- Opening: “Do not stop at V1. Check axis, QRS width, terminal morphology, and the rest of the chest leads.”
- Socratic: “Does the rightward appearance begin with the dominant ventricular force, or is it a late terminal force from delayed conduction?”
- Hint 1: “RBBB is a terminal-force pattern; compare V1 with I or V6.”
- Hint 2: “RVH support should persist across independent evidence domains, not repeat the same V1 clue.”
- Tangent return: “Back to [case]: complete the QRS-duration and terminal-force check before naming the chamber pattern.”

**State changes and deterministic gate:** Axis quadrant, V1 R/S ratio, precordial trend, and QRS terminal pattern are separately scored. Target completion requires at least three compatible domains; mimic completion requires the decisive alternative feature. A one-feature RVH conclusion is rejected.

**Exact feedback branches:**

- Correct independent: “Supported. [Axis evidence], [V1/precordial evidence], and [corroboration] form an RVH-compatible pattern. You also excluded [mimic] from its decisive feature.”
- Correct assisted: “The evidence bundle is correct after help. The module will revisit this contrast without the target announced.”
- Partial: “You found the dominant R in V1. Now determine whether it is the main force or a late conduction force by checking QRS width and lateral terminal morphology.”
- Wrong: “The boxed deflection is terminal and paired with [lateral feature], which favors a conduction pattern over an RVH claim.”
- Unsafe/unsupported: “A tall R in V1 cannot by itself prove RVH, pulmonary disease, or posterior infarction. State the supported pattern and unresolved alternative.”
- Not assessable—correct: “Correctly limited. [Missing/obscured evidence] prevents a specific chamber claim; [supported description] remains assessable.”
- Not assessable—incorrect: “Axis, QRS duration, and paired precordial/lateral morphology are available. Complete those checks before limiting the call.”

**Equivalent retry:** Different axis, different V1 morphology, clearest lateral lead, and mimic family; no repeated target lead panel.

**Accessibility specifics:** Axis has text choices plus degree band; R/S amplitude uses numeric fields; the progression trace is mirrored in a V1–V6 table. Screen reader states whether each lead is R-dominant, S-dominant, or balanced.

**Cross-mode handoff:** Connection chips: “M5 · RBBB terminal force” / “M9 · posterior pattern is a separate evidence problem.”

## M7-S4 — R-wave progression: describe the precordial transition

**Source refs:** `SPEC-ONTOLOGY`; `SPEC-GUIDED-MINIMUM`; `SPEC-VIEWER`; `ARCH-M7`; `FOUND-ST-QT`; `V2-CHAMBERS`.  
**Eyebrow/title:** “M7 · 5 of 8” / “The precordial sweep, revisited”  
**Goal line:** “Measure R/S balance across V1–V6 and describe transition without forcing disease.”

**Exact lesson copy:**

> “Across the chest leads, the balance of ventricular forces usually shifts: R tends to grow, S tends to shrink, and transition is the lead where R first becomes larger than S. The exact transition varies with rotation, anatomy, and placement. Your first job is a reproducible description: where the balance changes and whether the sequence is smooth, early, late, or not assessable.”

**On-screen labels:** “R amplitude” · “S amplitude” · “R/S ratio” · “First R > S” · “Early transition” · “Expected-range transition” · “Late/poor progression” · “Nonmonotonic” · “Lead sequence suspect.”

**Case contract:** Four full precordial sets: common transition, early transition, late/poor progression, and a lead-order/placement trap. Required calibrated V1–V6 with matched gain and a validated lead order. Real cases may be used for broad morphology at 100 Hz; amplitude measurement tolerances reflect sampling and noise.

**Layout delta:** V1–V6 appear as a horizontal scrub rail with a synchronized R/S bar chart. Mobile shows one lead at a time with six persistent bar slots and “Previous lead” / “Next lead.”

**Required interaction:** For each case the learner measures R and S in all six leads, marks the first R>S lead when present, draws a line through the six ratios, and selects a descriptive progression category. The learner must flag the placement/order trap rather than classify its transition.

**Tutor script:**

- Opening: “Measure the same beat component from the same baseline in every chest lead.”
- Socratic: “Where does R first become larger than S, and does the path to that point make anatomical sense?”
- Hint 1: “Transition is defined by the R/S balance, not by the tallest R in the tracing.”
- Hint 2: “A sudden impossible jump should trigger a lead identity or placement check before a disease label.”
- Tangent return: “Back to [case], [lead]: enter R and S before moving to the next chest lead.”

**State changes and deterministic gate:** All six amplitude pairs are required unless a lead is contract-declared unreadable. The transition mark must match the first ratio >1 within measurement tolerance. The trap requires the placement/order flag. Completion records description, not etiology.

**Exact feedback branches:**

- Correct independent: “Correct. Transition occurs at [lead], with [smooth/early/late/nonmonotonic] progression across V1–V6. That is the supported descriptive claim.”
- Correct assisted: “The transition and sequence are now correct after help. This scene is complete with assistance.”
- Partial: “You identified [lead] as transition, but [missing lead] has no R/S measurement. Complete the sequence so the pattern is reproducible.”
- Wrong: “R becomes larger than S first in [lead], not the lead with the tallest absolute R. Recheck the ratios.”
- Unsafe/unsupported: “Poor progression is a description, not an infarction diagnosis. Save etiology for the differential and lead-evidence checks.”
- Not assessable—correct: “Correct. [Lead] is unreadable/misidentified, so a trustworthy transition cannot be assigned. State the lead problem.”
- Not assessable—incorrect: “All six leads are calibrated and readable. Measure the R/S sequence before using ‘not assessable.’”

**Equivalent retry:** Different transition lead, rotation pattern, amplitude scale, and one alternate placement discontinuity.

**Accessibility specifics:** The R/S chart has a six-row table equivalent. Scrubbing is optional; buttons navigate leads. The transition line is announced as text, and color is redundant with R/S labels.

**Cross-mode handoff:** “Train · transition and rotation” and visible connection “M2 taught the lead map; M7 turns it into an evidence sequence.”

## M7-S5 — Poor R-wave progression: open the differential before closing the case

**Source refs:** `SPEC-ISCHEMIA-ELIGIBILITY`; `SPEC-CHAMBER-ELIGIBILITY`; `ARCH-M7`; `V2-CHAMBERS`; `INV-R-ISCH`; `CLIN-GROUNDING`.  
**Eyebrow/title:** “M7 · 6 of 8” / “Poor progression is a finding, not a final diagnosis”  
**Goal line:** “Use placement, prior, conduction, chamber, and infarction evidence in the right order.”

**Exact lesson copy:**

> “Reduced or delayed R-wave growth has a broad differential: chest-lead placement, normal rotation or body habitus, altered conduction, chamber-force patterns, and prior infarction can all contribute. Begin with calibration and lead sequence, describe the progression, compare QRS morphology and any prior, then decide what remains plausible. Do not award infarction from progression alone.”

**Differential board labels:** “Acquisition/placement” · “Normal variation/rotation” · “Conduction” · “Chamber-force pattern” · “Prior infarction possible” · “Insufficient evidence.”

**Case contract:** Four target–mimic packets: lead misplacement with corrected reacquisition, normal late transition, LBBB/RBBB or IVCD, and an established anterior-infarction-compatible case only if lead/territory/Q-wave or statement evidence satisfies `SPEC-ISCHEMIA-ELIGIBILITY`. Prior/current pairs must be comparable in gain, lead order, and source. If not comparable, “change” cannot be scored.

**Layout delta:** Current ECG and prior/reacquisition stack vertically at identical scale with “Ghost overlay” and “Lead placement map.” On mobile the matched lead pair stacks and a pinned banner reads “Same scale” or “Comparison invalid.”

**Required interaction:** Learner completes the V1–V6 R/S trace, checks calibration/placement, boxes any conduction or Q-wave evidence, and drags each case into the strongest differential bin plus a “next check” slot. For the infarction-compatible case, a territory claim requires lead-level proof.

**Tutor script:**

- Opening: “Describe first. Then test the cheapest reversible explanation: calibration, identity, and placement.”
- Socratic: “Which alternative would change immediately after correct lead placement, and which requires independent infarction evidence?”
- Hint 1: “Compare the whole QRS shape, not only R height.”
- Hint 2: “A valid prior needs the same lead identity, order, gain, and interpretable signal.”
- Tangent return: “Back to [case]: finish the acquisition check before moving to disease hypotheses.”

**State changes and deterministic gate:** Differential bins remain locked until the progression trace and acquisition check pass. A prior-change claim requires the comparison-validity flag. “Prior infarction possible” requires an accepted territorial feature; otherwise only “poor progression, nonspecific” can complete.

**Exact feedback branches:**

- Correct independent: “Well calibrated. This ECG shows [progression description]. [Decisive evidence] makes [best explanation] the strongest supported category, while [alternative] remains [plausible/unsupported].”
- Correct assisted: “Your sequence is now evidence-limited and correct. Assistance was used, so the same differential will recur in Train.”
- Partial: “The progression description is correct. The cause remains unlocked because [placement/prior/conduction] has not been checked.”
- Wrong: “Poor R-wave progression alone does not establish prior anterior infarction. Mark territorial Q-wave/statement evidence or keep the conclusion descriptive.”
- Unsafe/unsupported: “Do not create an acute or causal claim from this resting pattern. The supported output is a descriptive finding plus the next verification step.”
- Not assessable—correct: “Correctly limited. The comparison is invalid because [reason]. Current progression is describable; old-versus-new is not.”
- Not assessable—incorrect: “The current V1–V6 sequence is readable and calibrated. Describe it even if etiology remains uncertain.”

**Equivalent retry:** New progression morphology, different placement error, different prior validity issue, and a different decisive lead.

**Accessibility specifics:** Current/prior comparison has a synchronized six-row table and a non-overlay difference summary. The placement map is described anatomically in text. Ghost overlay is optional.

**Cross-mode handoff:** Cards: “Train · poor-progression differential” / “M9 · Q waves and infarction require territory evidence” / “Clinical · old-or-new” only when a validated comparable pair exists.

## M7-S6 — Strain: when altered activation shapes recovery

**Source refs:** `ARCH-M7`; `SPEC-CHAMBER-ELIGIBILITY`; `SPEC-ISCHEMIA-ELIGIBILITY`; `V2-CHAMBERS`; `INV-R-CHAMBER`; `INV-R-ISCH`; M5-S9 in `docs/storyboards/VERBATIM_M04_M06.md:397-436`.  
**Eyebrow/title:** “M7 · 7 of 8” / “Chamber forces can alter ST–T”  
**Goal line:** “Link the dominant QRS to secondary recovery, then preserve room for a primary process.”

**Exact lesson copy:**

> “When ventricular forces are enlarged or activation is altered, recovery can shift in the opposite direction. An LVH ‘strain’ pattern describes secondary, usually discordant ST depression and T-wave inversion in leads with large dominant leftward QRS forces. It strengthens an LVH pattern; it does not make every ST–T change expected, and it does not exclude a superimposed primary process.”

**Case contract:** Three lead-pair sets: LVH-compatible voltage with secondary lateral ST–T pattern, LBBB/ventricular-paced secondary discordance, and a case with an authored superimposed primary shift for discrimination. Real cases require QRS polarity, chamber/conduction statement, and lead-level ST/T features. The superimposed example is a labeled model unless a reviewed eligible real case exists; no ischemia diagnosis is keyed here.

**Layout delta:** Each lead panel has an upper “QRS direction” lane and lower “ST/T direction” lane. A causal model offers “Remove chamber-force component” and “Remove conduction component.” Mobile shows the two directions as a paired card under each lead.

**Required interaction:** Learner marks dominant QRS direction, J point/ST direction, and T direction in at least three leads; links each as “expected secondary discordance,” “not explained by the activation pattern,” or “unclear”; and boxes the superimposed region that needs separate M8/M9 assessment.

**Tutor script:**

- Opening: “Read depolarization first, recovery second, then compare their directions.”
- Socratic: “Does the ST–T vector oppose the lead’s large dominant QRS, and is the distribution explained by the same activation pattern?”
- Hint 1: “Use the dominant QRS, not a small notch, as the depolarization direction.”
- Hint 2: “Secondary discordance is an expectation with limits, not permission to ignore an outlier.”
- Tangent return: “Back to [lead]: mark QRS direction before deciding whether recovery is secondary.”

**State changes and deterministic gate:** At least three QRS/ST/T direction triplets must match lead truth. The outlier ROI must overlap the manifest region by IoU ≥0.45. No ischemia label is offered. Completion requires the statement “needs separate assessment” for unexplained change.

**Exact feedback branches:**

- Correct independent: “Correct. [Leads] show recovery discordant to their dominant QRS and compatible with a secondary pattern. [Outlier] is not safely dismissed and needs separate assessment.”
- Correct assisted: “The direction comparison is now correct after help. The outlier remains appropriately unlabelled.”
- Partial: “Your T direction is correct, but the dominant QRS direction is missing. Establish activation before classifying recovery.”
- Wrong: “In [lead], QRS points [direction] while ST/T points [opposite]. That relationship is discordant, not concordant.”
- Unsafe/unsupported: “Neither ‘all expected’ nor an acute diagnosis is supported here. Mark what the activation pattern explains and what still needs separate assessment.”
- Not assessable—correct: “Correctly limited. [Lead] does not provide a stable baseline, so its ST relation is unclear; [other leads] remain assessable.”
- Not assessable—incorrect: “QRS and T polarity are readable in [lead]. Their relationship is assessable even though etiology beyond secondary change is not.”

**Equivalent retry:** Different dominant-QRS directions, different affected leads, and a different superimposed region.

**Accessibility specifics:** Every direction arrow has a text selector. The causal removal layer has static before/after descriptions. Screen reader announces “Lead V6: QRS positive; ST depressed; T negative; discordant.”

**Cross-mode handoff:** Locked banners: “Saved for M8 · primary versus secondary repolarization” and “Saved for M9 · LVH/strain as an ischemia mimic.”

## M7-S7 — Chamber-pattern transfer: strongest claim, weakest link

**Source refs:** `SPEC-CHAMBER-ELIGIBILITY`; `SPEC-VIEWER`; `ARCH-M7`; `V2-CHAMBERS`; `INV-R-CHAMBER`; `INV-R-ISCH`; `SPEC-MASTERY`; `SPEC-MISCONCEPTIONS`; `ARCH-MODE-HANDOFF`.  
**Eyebrow/title:** “M7 · 8 of 8” / “Chamber-pattern transfer”  
**Goal line:** “Interpret unannounced chamber and progression patterns with calibrated confidence.”

**Exact lesson copy:**

> “Use an evidence bundle in the same order every time: calibration and quality → atrial morphology → frontal axis → ventricular voltage → QRS duration and morphology → R-wave progression → ST–T relationship → corroboration and limits → strongest defensible synthesis.”

**Tutor opening:** “I’ll remain collapsed for the independent set. Ask if you want help; the case will pause and assistance will be recorded.”  
**Socratic on request:** “Which evidence domain is still missing from your chamber claim?”  
**Hint 1:** “A chamber label needs more than one version of the same voltage clue.”  
**Hint 2:** “Before using poor progression, audit placement and conduction.”  
**Tangent return:** “Back to case [n], with your lead, zoom, marks, and draft intact.”

**Case contract:** Five cases without replacement: atrial-abnormality pattern, LVH-compatible pattern, RVH-compatible pattern, high-voltage/rotation or placement mimic, and one intentionally evidence-limited case. Every real target satisfies `SPEC-CHAMBER-ELIGIBILITY`; required lead-level truth, criterion policy, confidence ceiling, and forbidden diagnoses are explicit. No case makes an acute claim.

**Layout delta:** Full 12-lead with a nine-step evidence rail and case counter. Luna is collapsed. Mobile rail is a collapsible “Evidence [n] of 9” block above the tracing.

**Required interaction:** Per case the learner verifies calibration; marks the two most diagnostic lead regions; measures the relevant P/voltage/R-S feature; checks axis/QRS context; submits a one-sentence evidence-limited interpretation and confidence. Labels stay hidden until waveform proof is committed.

**Deterministic scoring and gate:** Per case: calibration/quality 10%, direct measurement 20%, lead localization 20%, corroboration/mimic check 20%, synthesis 20%, confidence 10%. Pass requires ≥82% overall, no LVH/RVH claim from one weak feature, correct uncertainty on the limited case, and no infarction overcall from poor progression. Any critical miss loads an equivalent case.

**Exact feedback branches:**

- Fully correct independent: “Supported. Your marks demonstrate [evidence sentence]. ‘[normalized synthesis]’ is the strongest claim this packet allows.”
- Correct limited: “Expertly limited. You named [supported evidence] and stopped before [unsupported chamber/etiology claim].”
- Correct assisted: “Your final evidence is supported. Because help was used, this case counts toward learning completion but not independent chamber mastery.”
- Partial: “You have [credited evidence]. The synthesis remains locked until [missing independent domain] is demonstrated.”
- Wrong: “Your conclusion depends on [weak feature], while [decisive mimic/limitation] argues against that specificity. Rebuild the bundle.”
- Unsafe/unsupported: “This resting ECG does not support an acute diagnosis, causal disease statement, or treatment order. Return to the chamber/progression evidence.”
- Not assessable—correct: “Correctly limited. [Supported description] is assessable; [specific claim] is not because [manifest reason].”
- Not assessable—incorrect: “The packet includes readable [required leads/measurement]. Complete those before limiting the conclusion.”

**Equivalent retry:** Same target family and difficulty, different record, different clearest leads, different voltage/axis combination, and different nuisance context. Failed records do not repeat in the session.

**Accessibility specifics:** The nine-step rail has a structured form equivalent; all measurements can use numeric steppers; screen-reader results list evidence before synthesis. No countdown.

**Completion copy:**

> “Module complete. You can now describe atrial and ventricular chamber evidence, measure voltage and R-wave progression, recognize common mimics, connect chamber forces to secondary ST–T change, and stop when the evidence stops.”

**Cross-mode handoff cards:**

- “Train · Your weakest chamber contrast” — “Repeat [objective] across varied ECGs until the evidence is independent.”
- “Rapid · Mixed whole-ECG reads” — “Find the chamber clue when it is not announced.”
- “Clinical · Pre-op or chronic-disease review” — “Use context and priors only in reviewed case families.”
- “Next guided module · Repolarization and QT” — “Use the activation context you just proved to interpret ST, T, and QT.”

---

# M8 — Repolarization, QT, Drugs, Electrolytes, and Nonischemic ST–T

**Module card copy:** “Read ventricular recovery in context. Establish the baseline and J point, describe ST and T shape, measure QT honestly, and connect drugs or electrolytes without diagnosing a laboratory value from a waveform.”  
**Estimated guided time:** “60–75 min · self-paced”  
**Prerequisite receipt:** M2 lead projection, M5 altered activation/secondary discordance, and M7 chamber-force/strain context.  
**Exit receipt:** defensible ST–T description, primary-versus-secondary recovery reasoning, reproducible QT/QTc, wide-QRS caveat, and safe medication/electrolyte information workflow.  
**Persistent connection chip:** “Recovery cannot be interpreted without knowing how activation arrived.”

## M8-S0 — Find the reference before judging recovery

**Source refs:** `FOUND-ST-QT`; `SPEC-VIEWER`; `ARCH-M8`; `V2-REPOLARIZATION`; `INV-R-QT`.  
**Eyebrow/title:** “M8 · 1 of 10” / “Baseline, J point, T end”  
**Goal line:** “Anchor every recovery claim to defensible boundaries.”

**Exact lesson copy:**

> “The J point is the end of QRS and the beginning of the ST segment. ST displacement needs a reference baseline, usually a stable TP segment when one is visible. QT begins at QRS onset and ends where the T wave returns to baseline. Noise, tachycardia, atrial activity, U waves, and altered QRS morphology can make each boundary uncertain. Uncertainty belongs in the measurement—not outside it.”

**Retrieval strip labels:** “QRS onset” · “J point” · “TP reference” · “T-wave end” · “Boundary uncertain.”

**Case contract:** Four synchronized beats: normal narrow QRS, RBBB, LBBB or paced model, and tachy/noisy ambiguous T end. Real QT scoring requires `SPEC-QT-ELIGIBILITY`; otherwise boundary identification is model-based. Each packet provides accepted boundary intervals, baseline segments, lead identity, QRS duration, and ambiguity flags.

**Layout delta:** A four-column boundary board on desktop/laptop; mobile shows one beat at a time with a persistent four-boundary receipt. Full tracing remains one tap away.

**Required interaction:** On each beat, learner places QRS-onset, J-point, baseline, and T-end markers; then chooses “precise,” “bounded range,” or “not reliably measurable” and shades the uncertainty interval when needed.

**Tutor script:**

- Opening: “Name the boundary before you measure the interval.”
- Socratic: “Where does ventricular activation end, and how certain is that transition in this QRS morphology?”
- Hint 1: “Trace the final QRS deflection until it joins the ST segment; do not use the tallest peak.”
- Hint 2: “For T end, follow the terminal downslope toward baseline and keep a visible U wave separate.”
- Tangent return: “Back to [beat]: place [missing boundary], then record its uncertainty.”

**State changes and deterministic gate:** Boundary markers pass when they fall within signal-specific accepted intervals. A point estimate on the deliberate ambiguity case fails; the learner must place a range or choose not reliably measurable. Completion requires all readable boundaries and correct uncertainty behavior.

**Exact feedback branches:**

- Correct independent: “Anchored. You identified [boundaries] and represented uncertainty where the waveform does not support a single point.”
- Correct assisted: “The boundaries are now correct after help. This scene is complete with assistance.”
- Partial: “Your baseline is defensible. The J point remains unmarked, so ST displacement cannot yet be interpreted.”
- Wrong: “That marker is at the T-wave peak, not T end. Follow the terminal limb back to baseline.”
- Unsafe/unsupported: “A boundary exercise cannot support an ischemia, electrolyte, or drug diagnosis. Complete the measurement anchors first.”
- Not assessable—correct: “Correct. [Boundary] is not reliably measurable in [lead] because [reason]. The supported range is [range]/another lead is required.”
- Not assessable—incorrect: “The packet provides a readable [boundary] in [lead]. Mark it and reserve uncertainty for the ambiguous beat.”

**Equivalent retry:** Different lead, heart rate, QRS morphology, T/U relationship, and noise phase.

**Accessibility specifics:** Structured alternatives provide waveform landmarks in a time-ordered list with millisecond steppers and an uncertainty-range control. Reduced motion removes the tracing sweep. Screen reader announces boundary order and interval.

**Cross-mode handoff:** “Foundation retrieved · J point, baseline, QT boundary” and “Next · connect activation to recovery direction.”

## M8-S1 — Primary or secondary? Start with the QRS

**Source refs:** `ARCH-M8`; `V2-REPOLARIZATION`; M5-S9 in `docs/storyboards/VERBATIM_M04_M06.md:397-436`; M7-S6 in this artifact; `SPEC-ISCHEMIA-ELIGIBILITY`.  
**Eyebrow/title:** “M8 · 2 of 10” / “Recovery follows its activation context”  
**Goal line:** “Distinguish expected secondary recovery from a primary or unexplained change.”

**Exact lesson copy:**

> “Primary repolarization change begins in recovery itself. Secondary repolarization change follows abnormal depolarization, as with bundle delay, ventricular pacing, pre-excitation, or marked chamber-force patterns. Read QRS duration, morphology, and dominant direction first. If ST–T direction and distribution fit that activation, call the relationship secondary-compatible. If they do not, preserve a primary or superimposed process for separate assessment.”

**Case contract:** Normal narrow-QRS model, eligible BBB case, paced simulation/eligible case, LVH/strain-compatible case, and an authored superimposed-change model. Every case has QRS/ST/T polarity truth in accepted leads and a maximum etiologic claim. No acute diagnosis is keyed.

**Layout delta:** A two-layer “Activation / Recovery” board sits beside paired lead magnifiers. “Hide QRS” and “Hide ST–T” may isolate components only after the learner’s initial prediction.

**Required interaction:** Learner measures QRS width, marks dominant QRS and T directions in three leads, links each pair, then assigns “secondary-compatible,” “primary/unexplained,” or “not assessable.” The learner must box the superimposed outlier.

**Tutor script:**

- Opening: “QRS first. Recovery cannot be classified in isolation.”
- Socratic: “Would this T-wave direction be surprising if the ventricular activation sequence were normal?”
- Hint 1: “Compare the dominant—not terminally tiny—QRS force with ST and T.”
- Hint 2: “A secondary pattern can coexist with an outlier that needs separate assessment.”
- Tangent return: “Back to [lead]: finish QRS width and direction before classifying ST–T.”

**State changes and deterministic gate:** Component isolation unlocks after a direction prediction. Completion requires three direction triplets, correct activation context, and outlier ROI IoU ≥0.45. Etiologic labels remain unavailable.

**Exact feedback branches:**

- Correct independent: “Correct. [Activation pattern] explains [secondary-compatible leads], while [outlier] is not explained and remains a separate recovery finding.”
- Correct assisted: “The activation→recovery link is now correct after a hint. It records as assisted.”
- Partial: “Your T direction is right. QRS width and dominant direction are still missing, so primary versus secondary remains unproven.”
- Wrong: “This ST–T direction is opposite a clearly abnormal dominant QRS and follows its lead distribution. Reconsider a secondary-compatible relationship.”
- Unsafe/unsupported: “Do not turn ‘not secondary’ into an acute diagnosis. This packet supports a recovery relationship, not etiology or treatment.”
- Not assessable—correct: “Correctly limited. [Lead/baseline] prevents a reliable relationship call; [other supported leads] remain assessable.”
- Not assessable—incorrect: “QRS and T directions are readable in the accepted lead set. Compare them before choosing ‘not assessable.’”

**Equivalent retry:** Different conduction/chamber context, different dominant directions, and a different outlier lead.

**Accessibility specifics:** Direction pairs have text controls; the component-isolation layer has a full written description; screen reader announces activation before recovery.

**Cross-mode handoff:** Chips: “M5/M7 connection restored” / “Saved for M9 · ischemia mimics.”

## M8-S2 — Describe ST and T before naming a cause

**Source refs:** `SPEC-ONTOLOGY`; `SPEC-GUIDED-MINIMUM`; `SPEC-ISCHEMIA-ELIGIBILITY`; `SPEC-VIEWER`; `ARCH-M8`; `V2-REPOLARIZATION`; `FOUND-ST-QT`.  
**Eyebrow/title:** “M8 · 3 of 10” / “Build a lead-level recovery sentence”  
**Goal line:** “Describe displacement, shape, polarity, distribution, and context.”

**Exact lesson copy:**

> “ST elevation, ST depression, T-wave inversion, and nonspecific ST–T change are findings before they are diagnoses. A useful description names the reference, lead set, direction, magnitude when valid, morphology, distribution, QRS context, and uncertainty. Words such as horizontal, downsloping, upsloping, symmetric, asymmetric, deep, or biphasic must point to visible waveform evidence.”

**Sentence-builder labels:** “Reference” · “Lead set” · “Direction” · “Magnitude” · “ST shape” · “T polarity/shape” · “QRS context” · “Uncertainty.”

**Case contract:** Six morphology tiles embedded in full ECGs: near-baseline, horizontal depression, downsloping depression, upsloping depression, T inversion, and biphasic/nonspecific T change. These may be real only with accepted lead-level evidence; deterministic models are allowed for pure morphology training. No tile carries an ischemia diagnosis.

**Layout delta:** Full tracing above a morphology workbench. A tangent line and baseline ruler sit on the selected lead. Mobile shows full-board mini-map plus a large selected lead and a collapsible sentence builder.

**Required interaction:** Learner taps the baseline and J point, places a tangent/segment line, boxes the T wave, paints affected leads on the lead map, and assembles one descriptive sentence. A free-text elaboration is optional and cannot replace structured evidence.

**Tutor script:**

- Opening: “Describe what the ink does. Cause comes later.”
- Socratic: “Could another reader reconstruct your finding from the lead set, direction, and morphology you named?”
- Hint 1: “Anchor ST to the baseline before choosing elevation or depression.”
- Hint 2: “T-wave polarity and shape are separate fields; mark both when visible.”
- Tangent return: “Back to [lead]: complete the reference and morphology marks before assembling the sentence.”

**State changes and deterministic gate:** ROI overlap ≥0.50, accepted lead-set F1 ≥0.80, and morphology token match are required. Magnitude scores only when calibration and approved measurement policy are present. Unsupported etiologic adjectives fail the conclusion axis.

**Exact feedback branches:**

- Correct independent: “Reproducible description: ‘[direction/morphology] in [lead set], [distribution], with [QRS context] and [uncertainty].’ You named the finding without inventing a cause.”
- Correct assisted: “The description is now reproducible after a hint. It counts as assisted.”
- Partial: “You marked the correct leads. Add the baseline-relative direction and T-wave shape so another reader can reconstruct the finding.”
- Wrong: “The selected segment is [relative direction] to the marked baseline. Recheck the reference before naming the displacement.”
- Unsafe/unsupported: “The word ‘[acute/ischemic/electrolyte]’ is not supported in this scene. Replace it with a lead-level ST–T description.”
- Not assessable—correct: “Correct. [Magnitude/morphology] is not reliable because [quality/calibration reason]; direction and distribution remain assessable.”
- Not assessable—incorrect: “The baseline, target leads, and morphology are readable. Complete the descriptive fields.”

**Equivalent retry:** Same morphology objective with a different lead set, QRS polarity, baseline noise, and amplitude.

**Accessibility specifics:** The lead-paint action has checkboxes in anatomical order. Tangent direction has numeric slope plus text. The sentence builder announces a live preview.

**Cross-mode handoff:** “Train · ST/T morphology deck” and “M9 will add ischemia, infarction, and mimic reasoning only after this description is stable.”

## M8-S3 — Measure QT: choose the lead, then choose the end

**Source refs:** `SPEC-QT-ELIGIBILITY`; `SPEC-VIEWER`; `ARCH-M8`; `V2-REPOLARIZATION`; `FOUND-ST-QT`; `INV-R-QT`; `INV-R-PRECISION`.  
**Eyebrow/title:** “M8 · 4 of 10” / “QT is a measured interval, not a machine label”  
**Goal line:** “Select a clear lead, separate T from U, and reproduce QT across beats.”

**Exact lesson copy:**

> “QT runs from the earliest QRS onset to the end of ventricular repolarization represented by the T wave. Choose a lead with a clear T ending, inspect more than one beat, and document the lead. The tangent method extends the steepest terminal T-wave slope to the baseline; the threshold method follows the waveform’s return to baseline. U waves are not automatically included. When the end is genuinely fused or indistinct, report a range or another lead rather than false precision.”

**Method controls:** “Tangent method” · “Threshold method” · “Use another lead” · “Bounded range” · “T/U separation uncertain.”

**Case contract:** Three eligible QT packets: clear T end, visible separate U wave, and fused/ambiguous T–U morphology. Required high-rate signal or validated median/fiducials, QT and QTc source, heart rate/RR, source confidence, QRS onset, accepted T-end interval, and at least two eligible beats/leads.

**Layout delta:** Lead carousel with synchronized median and rhythm beats; caliper values appear in a measurement notebook. Mobile shows one magnified lead with a persistent “Beat 1 / Beat 2 / Median” selector.

**Required interaction:** Learner chooses a lead with a written reason, marks QRS onset and T end on two beats using one named method, marks the U wave separately when present, and records mean QT plus uncertainty. The machine value stays hidden until commitment.

**Tutor script:**

- Opening: “Choose the clearest ending before placing a caliper.”
- Socratic: “What makes this deflection part of T rather than a separate U wave?”
- Hint 1: “Use the earliest QRS onset and the terminal return of T—not the T peak.”
- Hint 2: “If T and U merge, show the uncertainty instead of forcing a point.”
- Tangent return: “Back to [lead], beat [n]: finish the T-end method you selected.”

**State changes and deterministic gate:** Each boundary must lie in its accepted interval; calculated QT must be within the packet’s signal-appropriate tolerance. Two-beat reproducibility and a lead/method record are mandatory. The ambiguous case completes only with a valid range or alternate lead.

**Exact feedback branches:**

- Correct independent: “Reproducible. QT is [value/range] ms in [lead] by the [method], measured across [beats], with [uncertainty].”
- Correct assisted: “The measurement is now correct after help. It records as assisted QT evidence.”
- Partial: “Beat 1 is within tolerance. Measure a second eligible beat and document the lead before the QT can complete.”
- Wrong: “Your right caliper includes a separate U wave. Mark T end at [accepted region] and label U separately.”
- Unsafe/unsupported: “A QT measurement alone does not establish drug causation, torsades, or a treatment plan. Complete the interval and context first.”
- Not assessable—correct: “Correct. T end is fused/obscured in [lead]. Use [alternate lead/range] and state the limitation.”
- Not assessable—incorrect: “[Lead] has a validated readable T end on two beats. Measure it before limiting the interval.”

**Equivalent retry:** Different rate, lead, T polarity, U-wave timing, and noise; same method objective.

**Accessibility specifics:** Calipers have millisecond fields and steppers. A waveform-landmark list identifies QRS onset, T terminal slope, baseline intersection, and U onset without revealing the answer before submission. Touch uses select/move/confirm.

**Cross-mode handoff:** “Train · QT boundary calibration” / “Next · correct the measurement for rate.”

## M8-S4 — Correct QT for rate without worshipping one formula

**Source refs:** `SPEC-QT-ELIGIBILITY`; `ARCH-M8`; `V2-REPOLARIZATION`; `INV-R-QT`; `INV-R-CLINREV`.  
**Eyebrow/title:** “M8 · 5 of 10” / “Rate correction is a model”  
**Goal line:** “Calculate Bazett and Fridericia, inspect rate behavior, and state the caveat.”

**Exact lesson copy:**

> “Raw QT changes with cycle length. QTc estimates what QT might be at a standardized rate, but the estimate depends on the correction model. With QT and RR expressed in seconds, Bazett uses QT ÷ √RR and Fridericia uses QT ÷ ∛RR. Their behavior diverges at rate extremes. Always report the measured QT, heart rate or RR, correction method, and uncertainty; do not treat a corrected value as rate-free truth.”

**Formula card:** “Bazett: QTcB = QT / √RR” · “Fridericia: QTcF = QT / ∛RR” · “Enter QT and RR in seconds.”

**Case contract:** Deterministic rate/QT model plus three eligible real packets at slower, mid-range, and faster rates. Each includes manual QT, RR/rate, machine formula/source when available, confidence, QRS width, and no required missingness. No risk threshold is keyed without approved policy.

**Layout delta:** A rate slider drives raw QT and two correction curves; real-case values pin as points. Mobile replaces the broad plot with three rate cards and an expandable accessible data table.

**Required interaction:** Learner predicts which correction will diverge more at the model’s extremes, calculates both QTc values for two real packets, plots them, and writes a four-part report: QT, rate/RR, formula, caveat. Machine values reveal only afterward.

**Tutor script:**

- Opening: “Keep units visible. Calculate both formulas before deciding what the difference means.”
- Socratic: “If RR becomes shorter, how does each denominator change, and what happens to the corrected estimate?”
- Hint 1: “Convert milliseconds to seconds before applying the formula, then convert the result back if needed.”
- Hint 2: “A disagreement at an extreme rate is a model warning, not permission to choose the preferred answer.”
- Tangent return: “Back to [case]: finish QT, RR, and both formula fields before comparing them.”

**State changes and deterministic gate:** Formula values must be within ±5 ms of deterministic arithmetic after rounding. Unit errors are detected separately. Completion requires both formulas and the caveat “rate extreme/formula dependent” where applicable. No threshold classification appears unless the policy card is approved.

**Exact feedback branches:**

- Correct independent: “Correct. QT [value] ms at [rate]/RR [value] gives QTcB [value] and QTcF [value]. Their [agreement/divergence] should be reported with the method and rate context.”
- Correct assisted: “The arithmetic and caveat are correct after help. This is assisted formula evidence.”
- Partial: “Your Bazett value is correct. Add Fridericia and the rate-context caveat before interpreting the result.”
- Wrong: “The formula received milliseconds where seconds were required. Convert QT and RR to seconds, then recalculate.”
- Unsafe/unsupported: “Do not choose a treatment or torsades-risk category from an unreviewed threshold. Report the measurement, method, rate, and uncertainty.”
- Not assessable—correct: “Correct. QTc cannot be reproduced because [QT/RR/formula source] is missing. State the missing input.”
- Not assessable—incorrect: “QT, RR, and both formula definitions are present. Calculate the estimates; the clinical risk category may still be unavailable.”

**Equivalent retry:** Different QT, rate band, formula divergence, and unit presentation; arithmetic remains exact.

**Accessibility specifics:** The plot has a full table and spoken trend summaries. Formula inputs expose units. Slider steps are available as “Slower,” “Mid-range,” and “Faster” buttons.

**Cross-mode handoff:** “Train · QTc arithmetic and formula caveats” / “Next · ask how a wide QRS changes the meaning of QT.”

## M8-S5 — Wide QRS and pacing: separate depolarization from recovery

**Source refs:** `SPEC-QT-ELIGIBILITY`; `ARCH-M8`; `V2-REPOLARIZATION`; `INV-R-QT`; M5-S9 in `docs/storyboards/VERBATIM_M04_M06.md:397-436`; `INV-R-CLINREV`.  
**Eyebrow/title:** “M8 · 6 of 10” / “QT includes QRS, so width matters”  
**Goal line:** “Recognize when a simple QTc overstates recovery time.”

**Exact lesson copy:**

> “QT contains both ventricular depolarization and repolarization. When QRS widens from bundle delay or pacing, QT can lengthen even if recovery has not increased by the same amount. Inspect QRS duration, report the confound, and use only a reviewed method—such as a specified JT/JTc approach—when the curriculum policy provides one. Do not silently apply a narrow-QRS threshold to a wide-QRS tracing.”

**Component labels:** “QRS: depolarization” · “JT: J point to T end” · “QT: QRS onset to T end” · “Reviewed wide-QRS method required.”

**Case contract:** Paired narrow-QRS and wide-QRS/paced deterministic beats with matched T-end recovery plus eligible real BBB/pacing examples. Real cases require QRS/QT/QTc/rate and source confidence. JT/JTc scoring is disabled unless a named, reviewed policy specifies formula and population.

**Layout delta:** QT bar splits visibly into QRS and JT components beneath the waveform. A “Match recovery, widen QRS” model control demonstrates the confound. Mobile uses stacked component bars with exact numeric labels.

**Required interaction:** Learner measures QRS and QT, derives JT by subtraction, manipulates QRS width while holding the recovery component fixed, and selects “simple QTc interpretable,” “wide-QRS confound—reviewed method needed,” or “not measurable.”

**Tutor script:**

- Opening: “Split the interval before interpreting the total.”
- Socratic: “If QT grows by the same amount as QRS while JT stays fixed, what actually changed?”
- Hint 1: “JT begins at the J point and ends with the T wave.”
- Hint 2: “Do not invent a correction. Name the confound and use only the configured reviewed method.”
- Tangent return: “Back to [case]: finish QRS, QT, and derived JT before choosing the interpretation.”

**State changes and deterministic gate:** QRS/QT boundaries pass within case tolerance; JT arithmetic within ±5 ms. Completion requires recognition of wide-QRS confounding and blocks any unreviewed numeric risk conclusion.

**Exact feedback branches:**

- Correct independent: “Correct. QT is [value], but QRS contributes [value]. The wide-QRS/pacing confound must be reported; a reviewed method is needed before a recovery-risk conclusion.”
- Correct assisted: “The interval split is now correct after help and records as assisted.”
- Partial: “QT is measured. Add QRS duration and the remaining JT component before interpreting the total.”
- Wrong: “The longer QT here is explained largely by wider depolarization while the model’s recovery component is unchanged.”
- Unsafe/unsupported: “A narrow-QRS QTc threshold cannot be applied silently here, and this scene does not support a drug stop/start decision.”
- Not assessable—correct: “Correct. A reviewed wide-QRS interpretation method is not configured. The raw intervals and confound are assessable; the adjusted risk category is not.”
- Not assessable—incorrect: “QRS and QT boundaries are readable. Measure them even if adjusted interpretation remains unavailable.”

**Equivalent retry:** Different QRS morphology, pacing status, QT, rate, and component proportions.

**Accessibility specifics:** Component bars have a text equation “QT minus QRS equals JT.” Animation becomes three static frames. All measures have numeric alternatives.

**Cross-mode handoff:** “M5 · conduction context reused” / “Clinical medication cases will score measurement separately from action rationale.”

## M8-S6 — Medication-QT workflow: verify before you act

**Source refs:** `SPEC-QT-ELIGIBILITY`; `ARCH-M8`; `V2-REPOLARIZATION`; `INV-R-AUTHCTX`; `INV-R-CLINREV`; `CLIN-GROUNDING`; `CLIN-GRADING`.  
**Eyebrow/title:** “M8 · 7 of 10” / “Medication safety is an evidence chain”  
**Goal line:** “Build a reproducible QT review without embedding a stale drug list or issuing an order.”

**Exact lesson copy:**

> “A medication-QT review begins with a trustworthy ECG measurement, then asks what was taken, when, at what dose, with which interacting medicines, renal/hepatic context, electrolytes, symptoms, prior ECG, and follow-up plan. Drug-risk categories change and may be licensed. The platform must query a current approved source rather than teach a copied static list. In this guided scene, verify, reconcile, compare, and escalate through reviewed categories—do not create a patient-specific medication order.”

**Workflow labels:** “1 Verify ECG” · “2 Manual QT/QTc” · “3 QRS confound” · “4 Reconcile medicines” · “5 Check interactions/clearance” · “6 Check electrolytes/symptoms” · “7 Compare prior” · “8 Reviewed follow-up category.”

**Case contract:** Authored ward context explicitly separated from one eligible real QT ECG. The packet includes medication names only from an approved/licensed lookup connector or inert classes such as “QT-active medicine A” for demo; timing/dose/renal/electrolyte fields carry authored provenance. Any scored action category requires approved clinical policy. Without it, the case ends after measurement and data-request ordering.

**Layout delta:** Full 12-lead and an eight-step reconciliation timeline. Context cards remain face-down until manual measurement commits. Mobile uses a staged accordion and keeps the ECG summary pinned.

**Required interaction:** Learner measures QT/QTc before machine reveal, checks QRS width, drags available data into the eight steps, identifies two missing high-value data items, and orders “verify/repeat,” “obtain missing data,” “review with supervising clinician/local pathway,” and any approved action token only when enabled.

**Tutor script:**

- Opening: “Measure before reading the machine or medication card.”
- Socratic: “Which missing datum could change whether the corrected interval is trustworthy or actionable?”
- Hint 1: “Rate, formula, and QRS width belong beside the QTc value.”
- Hint 2: “Medication name alone is incomplete; timing, dose, interactions, clearance, electrolytes, and prior matter.”
- Tangent return: “Back to step [n]: complete the ECG evidence before revealing the next context card.”

**State changes and deterministic gate:** Context stays locked until manual QT/QTc passes. Data-request ranking is rule-based. If clinical review is absent, action controls display “Action scoring unavailable — policy review required” and cannot create mastery. If present, compound actions are component-scored under `CLIN-GRADING`.

**Exact feedback branches:**

- Correct independent: “Complete chain. You verified [QT/QTc/method/rate/QRS], reconciled [available factors], requested [missing data], and stayed within the reviewed follow-up category.”
- Correct assisted: “The evidence chain is now complete after help. Measurement and workflow record as assisted; no independent action credit is written.”
- Partial: “Your QTc is supported. The workflow remains incomplete until you check [QRS/prior/electrolytes/interactions].”
- Wrong: “The machine value cannot replace your manual boundary and formula check. Return to the ECG before using the medication context.”
- Unsafe/unsupported: “A stop/start/dose order is not authorized by this storyboard. Use the reviewed educational category or request supervision/local-pathway review.”
- Not assessable—correct: “Correct. [Required datum/policy] is absent. State what is measurable now and what must be obtained before an action category.”
- Not assessable—incorrect: “The ECG supports manual QT/QTc and QRS assessment. Complete those even though medication action may remain unavailable.”

**Equivalent retry:** Different rate, QRS width, missing-data pattern, medication class token, and prior availability; no repeated action key.

**Accessibility specifics:** Reveal layers announce “New authored clinical information.” Medicine data is text, not pill color/icon. Ordering can be done with numbered selects instead of drag. No timer.

**Cross-mode handoff:** Cards: “Train · QT measurement” / “Clinical · Medication-QT review” only if reviewed / “M10 · full medication case.”

## M8-S7 — Electrolytes: waveform hypothesis, laboratory confirmation

**Source refs:** `SPEC-ONTOLOGY`; `SPEC-QT-ELIGIBILITY`; `ARCH-M8`; `V2-REPOLARIZATION`; `INV-R-SYNTH`; `INV-R-CLINREV`; `INV-R-CHRONIC`.  
**Eyebrow/title:** “M8 · 8 of 10” / “Ion changes are patterns, not lab results”  
**Goal line:** “Connect broad K/Ca/Mg effects to waveform components and request confirming data.”

**Exact lesson copy:**

> “Electrolytes influence membrane currents and therefore P waves, PR, QRS, ST, T, and QT. Potassium disturbance can alter T-wave shape and, when substantial, atrial and ventricular conduction; calcium changes can shift ST duration and QT; magnesium matters to repolarization risk but may not produce a specific surface pattern. These findings overlap with drugs, ischemia, conduction disease, and normal variation. The ECG can raise a hypothesis and urgency concern; the laboratory value establishes the electrolyte measurement.”

**Model labels:** “Extracellular K — teaching continuum” · “Extracellular Ca — teaching continuum” · “Mg context — no unique waveform slider” · “Pattern overlap” · “Request laboratory confirmation.”

**Case contract:** Deterministic cellular-to-waveform models for isolated causal exploration plus three comparison packets (real only when a compatible electrolyte/drug statement and feature evidence exist; otherwise clearly labeled simulations). No model value is shown as a patient laboratory result. No torsades or acute-treatment mastery is awarded.

**Layout delta:** Ion controls sit beside a waveform component map. A hidden “overlap” layer superimposes drug/conduction mimics after the learner’s prediction. Mobile presents K and Ca as separate numbered experiments; Mg is a context card, not a morphology generator.

**Required interaction:** Learner predicts affected waveform components, moves one ion control while others stay fixed, marks changed P/QRS/ST/T/QT regions, then compares a mimic and selects the laboratory/medication/prior datum that would discriminate. The learner must state “pattern compatible with” rather than a numeric diagnosis.

**Tutor script:**

- Opening: “Use the model to connect mechanism to components, then let the mimic show why a real ECG is not specific.”
- Socratic: “Which observed change is shared by more than one cause, and what datum resolves that overlap?”
- Hint 1: “Track P, PR, QRS, ST/T, and QT separately rather than searching for one signature shape.”
- Hint 2: “The ECG suggests; a measured electrolyte and clinical context confirm.”
- Tangent return: “Back to the [ion] experiment: change only that control, then mark each waveform component that moved.”

**State changes and deterministic gate:** Prediction precedes model reveal. Required ROIs match changed components. Completion requires one overlap/mimic and correct next datum. Any exact lab-value inference or treatment order triggers unsafe/unsupported.

**Exact feedback branches:**

- Correct independent: “Correct. The model links [ion change] to [components], while the comparison shows overlap with [mimic]. The defensible next step is to obtain [datum], not infer a laboratory value.”
- Correct assisted: “The component map is correct after help. This is assisted causal-model evidence only.”
- Partial: “You identified the T-wave change. Inspect [P/QRS/ST/QT] before deciding how broad the pattern is.”
- Wrong: “That component did not change when only [ion] moved. Reset, compare before/after, and mark the actual regions.”
- Unsafe/unsupported: “The waveform does not supply a numeric electrolyte level or a patient-specific replacement/treatment order. State the compatible pattern and confirming datum.”
- Not assessable—correct: “Correct. A specific electrolyte cause is not assessable from this overlapping pattern. The waveform features and need for labs are assessable.”
- Not assessable—incorrect: “The model exposes which waveform components changed. Mark those even though real-case etiology remains uncertain.”

**Equivalent retry:** Different baseline rate, isolated ion control, overlapping mimic, and required confirming datum.

**Accessibility specifics:** Ion sliders have low/reference/high teaching states with explicit “not a patient value” labels. Before/after differences are available in a component table. No motion or color is required.

**Cross-mode handoff:** “Train · electrolyte-pattern contrasts” stays disabled if reliable cases are insufficient; available card copy is “Needs more reliable cases.” M10 medication case reuses the “request labs, do not guess” behavior.

## M8-S8 — Nonischemic ST–T and normal-variant comparison

**Source refs:** `SPEC-ISCHEMIA-ELIGIBILITY`; `ARCH-M8`; `V2-REPOLARIZATION`; `INV-R-ISCH`; `INV-R-CHRONIC`; `CLIN-GROUNDING`; M7-S6 in this artifact.  
**Eyebrow/title:** “M8 · 9 of 10” / “Compare distributions, not slogans”  
**Goal line:** “Distinguish variant, pericarditis-compatible, secondary, and nonspecific patterns while preserving uncertainty.”

**Exact lesson copy:**

> “Early-repolarization and age-related variants, pericarditis-compatible patterns, LVH/strain, bundle delay or pacing, lead error, and nonspecific change can overlap with ischemic-appearing ST–T findings. Use lead distribution, QRS context, J-point/ST morphology, PR/baseline findings when reliable, reciprocal relationships, prior ECG, symptoms, and serial data. No single mnemonic or ratio safely settles every case.”

**Comparison-matrix labels:** “Distribution” · “QRS context” · “J/ST morphology” · “T morphology” · “PR/baseline evidence” · “Reciprocal/opposing evidence” · “Prior/serial” · “Clinical context” · “What remains uncertain.”

**Case contract:** Four target–mimic–normal triads: normal/early-repolarization-compatible variation, pericarditis-compatible pattern, LVH/BBB secondary change, and nonspecific ST–T. Real labels require compatible statements plus lead-level evidence. Any ischemia comparison is descriptive preview only; M9 owns localization/acute claims. Authored context is disclosed.

**Layout delta:** Three full ECGs share identical calibration and lead order. Selecting a matrix row magnifies the same leads across all three. Mobile stacks the corresponding lead panels and pins the matrix row label.

**Required interaction:** Learner marks baseline/J point, paints distribution, links QRS and recovery direction, boxes PR/baseline evidence when present, and fills the comparison matrix before ranking “more compatible,” “overlap—needs context,” or “not assessable.”

**Tutor script:**

- Opening: “Compare one discriminator at a time across all three tracings.”
- Socratic: “Which feature is independent of the same ST shape and therefore adds real discriminating evidence?”
- Hint 1: “Start with distribution and QRS context before relying on a named morphology.”
- Hint 2: “Absence of a feature is useful only when the lead and baseline can actually show it.”
- Tangent return: “Back to matrix row [row]: complete that discriminator across all three ECGs.”

**State changes and deterministic gate:** At least five matrix rows require direct marks. Ranking is scored from a versioned triad rubric; a single-feature shortcut cannot complete. Acute, culprit-vessel, or treatment claims are forbidden.

**Exact feedback branches:**

- Correct independent: “Well compared. [Pattern] is more compatible with [category] because [two independent discriminators]. [Overlap/uncertainty] remains, so context or serial evidence is still needed.”
- Correct assisted: “Your comparison is supported after help. It records as assisted discrimination evidence.”
- Partial: “The distribution is correct. Add one independent discriminator—QRS context, reciprocal evidence, PR/baseline finding, or valid prior—before ranking.”
- Wrong: “That ranking relies on one morphology while [contradictory discriminator] is visible. Reopen the matching lead row.”
- Unsafe/unsupported: “This scene does not authorize an acute ischemia diagnosis, culprit vessel, or treatment action. Keep the output at pattern compatibility and needed evidence.”
- Not assessable—correct: “Correct. [Category distinction] remains unresolved because [missing/ambiguous datum]. You still correctly described [supported features].”
- Not assessable—incorrect: “The triad provides [discriminator] in readable matched leads. Complete the comparison before limiting it.”

**Equivalent retry:** New triad, different lead distribution, different secondary-QRS context, and different missing contextual datum.

**Accessibility specifics:** The matrix is a real table with row/column headers. Matched lead panels have text morphology summaries after the learner marks them. Mobile never requires side-by-side miniaturization.

**Cross-mode handoff:** Banner: “Next guided module · Ischemia, infarction, localization, and mimics” / “Your first M9 task will begin from these same descriptive fields.”

## M8-S9 — Repolarization and QT transfer

**Source refs:** `SPEC-QT-ELIGIBILITY`; `SPEC-ISCHEMIA-ELIGIBILITY`; `SPEC-VIEWER`; `ARCH-M8`; `V2-REPOLARIZATION`; `INV-R-QT`; `INV-R-CLINREV`; `SPEC-MASTERY`; `SPEC-MISCONCEPTIONS`; `SPEC-TRAIN`; `SPEC-RAPID`; `ARCH-MODE-HANDOFF`.  
**Eyebrow/title:** “M8 · 10 of 10” / “Recovery evidence under mixed conditions”  
**Goal line:** “Complete unannounced ST–T and QT tasks without causal overreach.”

**Exact lesson copy:**

> “Use the same recovery sequence every time: calibration and quality → QRS context → baseline and J point → ST direction, magnitude, morphology, and distribution → T direction and shape → QT lead and boundaries → rate correction and formula → wide-QRS caveat → drug/electrolyte/context evidence → strongest defensible conclusion.”

**Tutor opening:** “I’ll remain collapsed for the independent set. If you ask for help, the case pauses and the assistance level is saved.”  
**Socratic on request:** “Which recovery field is still unsupported by a mark or measurement?”  
**Hint 1:** “Activation context comes before ST–T classification.”  
**Hint 2:** “A QTc value needs QT, rate/RR, formula, QRS context, and uncertainty.”  
**Tangent return:** “Back to case [n], with your exact lead, zoom, calipers, and draft preserved.”

**Case contract:** Five-case set: primary/secondary ST–T contrast, descriptive ST-depression/T morphology, clear QT/QTc, wide-QRS QT confound, and medication/electrolyte context with intentional missing data. Each retains its source scene’s contract; at least one requires calibrated “not assessable.” No acute ischemia or treatment order is keyed.

**Layout delta:** Full tracing with a ten-step recovery rail; Luna collapsed. Context reveals only after waveform commitment. Mobile uses a collapsible rail with the current evidence step pinned.

**Required interaction:** Per case learner marks QRS context, baseline/J point, decisive ST/T ROI, and—when relevant—QT/QRS/RR calipers; submits a structured description, method, context limitation, conclusion, and confidence. The context case requires ordering missing information.

**Deterministic scoring and gate:** Per case: boundaries 15%, waveform morphology/distribution 25%, QRS context 15%, QT arithmetic/method when applicable 20%, conclusion/limits 15%, confidence 10%. Pass ≥82%, no U-wave inclusion critical error, no narrow-QRS threshold applied silently to wide QRS, and no electrolyte/drug causal overclaim. Critical error triggers an equivalent case.

**Exact feedback branches:**

- Fully correct independent: “Supported. Your waveform evidence shows [evidence sentence], and your conclusion—‘[normalized conclusion]’—matches the packet’s allowed claim.”
- Correct limited: “Correctly limited. You measured/described [supported fields] and identified [missing datum/method] before interpretation.”
- Correct assisted: “The final work is supported after assistance. Learning completion is saved; independent recovery mastery is not yet awarded.”
- Partial: “You have [credited evidence]. [Missing boundary/context/formula] must be completed before the conclusion unlocks.”
- Wrong: “Your conclusion conflicts with [case-specific discriminator]. Reopen [lead/measurement] and rebuild from the QRS context.”
- Unsafe/unsupported: “This case does not support an acute diagnosis, numeric laboratory inference, drug order, or torsades claim. Return to supported recovery evidence and needed data.”
- Not assessable—correct: “Correctly limited. [Supported finding] is assessable; [specific inference] is not because [manifest reason].”
- Not assessable—incorrect: “The packet includes readable [required evidence]. Complete it before using ‘not assessable.’”

**Equivalent retry:** Same objective and evidence completeness, different record/model seed, different lead, different rate/QRS context, and at least two nuisance changes.

**Accessibility specifics:** The ten-step rail mirrors a structured form; all calipers and lead-paint actions have numeric/checkbox alternatives; results announce evidence, limitation, conclusion, then confidence. No timer.

**Completion copy:**

> “Module complete. You can now anchor ST–T findings to the baseline and QRS context, measure and correct QT reproducibly, recognize wide-QRS limitations, and connect medications or electrolytes without inventing a cause or action.”

**Cross-mode handoff cards:**

- “Train · QT and ST–T calibration” — “Repeat the exact boundary, morphology, or formula that cost the most evidence points.”
- “Rapid · Whole-ECG recovery reads” — “Tutor stays silent until you submit.”
- “Clinical · Medication-QT review” — “Available only for clinician-reviewed case/action packets.”
- “Next guided module · Ischemia and infarction” — “Add territory, reciprocal evidence, serial comparison, and mimic discrimination.”

---

# M9 — Ischemia, Infarction, Localization, and Mimics

**Module card copy:** “Turn ST–T and Q-wave findings into an evidence-weighted geographic pattern. Require contiguous leads, seek reciprocal or serial support, compare mimics, and never manufacture acute timing from a resting chronic ECG.”  
**Estimated guided time:** “75–95 min · self-paced, resumable in two parts”  
**Prerequisite receipt:** M2 territories/vectors, M5 altered activation, M7 chamber/strain, and M8 baseline/ST–T/QT reasoning.  
**Exit receipt:** lead-supported localization, reciprocal and serial reasoning, Q-wave/prior interpretation, mimic discrimination, and proportionate uncertainty/urgency language.  
**Persistent data banner:** “Established/chronic patterns: available when eligible. Acute/evolving patterns: locked unless validated acute or true serial evidence is present.”

## M9-S0 — The ECG records electrical consequences, not a pathology clock

**Source refs:** `SPEC-ISCHEMIA-ELIGIBILITY`; `ARCH-M9`; `V2-ISCHEMIA`; `INV-R-ISCH`; `INV-R-CHRONIC`; `CLIN-GROUNDING`.  
**Eyebrow/title:** “M9 · 1 of 10” / “Start with what the ECG can know”  
**Goal line:** “Separate physiology, waveform finding, timing, and clinical diagnosis.”

**Exact lesson copy:**

> “Reduced myocardial oxygen supply can alter membrane behavior and regional electrical gradients; irreversible injury can later alter depolarization as well. The surface ECG records the summed electrical consequences from particular viewpoints. A single tracing may support an ST–T pattern, Q-wave pattern, or territorial distribution, but it does not by itself timestamp tissue, prove coronary anatomy, or exclude an acute coronary syndrome when nondiagnostic.”

**Epistemic-layer labels:** “Visible waveform” · “Spatial pattern” · “Mechanism hypothesis” · “Clinical diagnosis” · “Timing/newness” · “Action category.”

**Case contract:** Deterministic region/vector model plus one eligible established MI/ST–T real case and one normal/nondiagnostic case. The model is not scored as clinical recognition. Real cases expose allowed and forbidden claim layers; no acute wording unless provenance permits it.

**Layout delta:** A six-rung claim ladder sits beside the heart/lead model and real tracing. Mobile shows the ladder under the selected trace with one rung expanded at a time.

**Required interaction:** Learner marks the visible finding, paints its lead distribution, and drags six statements to the highest rung justified by each source. Statements include “ST elevation in [leads],” “territorial pattern,” “acute occlusion now,” “culprit artery,” “new compared with prior,” and “needs clinical correlation.”

**Tutor script:**

- Opening: “For each sentence, ask what source would be required to say it honestly.”
- Socratic: “Which claim needs a prior or acute-source timestamp rather than morphology alone?”
- Hint 1: “Lead distribution can support geography without proving a culprit vessel.”
- Hint 2: “Newness requires comparison or acute provenance; it cannot be inferred from dramatic appearance.”
- Tangent return: “Back to claim [claim]: place it on the highest rung the packet supports.”

**State changes and deterministic gate:** Claim placement uses the manifest allowlist. Completion requires the visible finding and territory at their supported rungs, and rejection of ungrounded acute/new/culprit claims.

**Exact feedback branches:**

- Correct independent: “Exactly. The tracing supports [finding and distribution]. [Timing/culprit/clinical diagnosis] requires additional evidence, so you stopped at the correct claim layer.”
- Correct assisted: “The claim ladder is now correct after help and records as assisted.”
- Partial: “Your waveform description is supported. The territory rung still needs lead-level proof.”
- Wrong: “The word ‘new’ requires a valid prior or acute temporal source. Morphology alone cannot supply that timestamp.”
- Unsafe/unsupported: “This packet does not support an acute occlusion, culprit-vessel, or treatment claim. Return to the visible waveform and lead distribution.”
- Not assessable—correct: “Correct. [Timing/culprit] is not assessable. [Finding/distribution] remains assessable and should still be stated.”
- Not assessable—incorrect: “The accepted leads support a descriptive pattern. Mark them before limiting higher claim layers.”

**Equivalent retry:** Different finding, distribution, chronic provenance, and unsupported high-level claim.

**Accessibility specifics:** The ladder is an ordered text list; drag has select-and-place alternatives. The vector model has static direction descriptions. Screen reader announces source needed for each rung after submission.

**Cross-mode handoff:** “M8 description retained” / “Next · geography from contiguous and opposing leads.”

## M9-S1 — Contiguous plus reciprocal: build the geographic pattern

**Source refs:** `SPEC-ISCHEMIA-ELIGIBILITY`; `SPEC-VIEWER`; `ARCH-M9`; `V2-ISCHEMIA`; `INV-R-ISCH`; M2 lead-map scenes in `docs/storyboards/VERBATIM_M01_M03.md:801-897`.  
**Eyebrow/title:** “M9 · 2 of 10” / “One regional vector, multiple viewpoints”  
**Goal line:** “Measure at the J point, group contiguous leads, and seek opposing evidence.”

**Exact lesson copy:**

> “A regional ST vector appears differently across leads because each lead views the same electrical field from a different direction. Anatomically related contiguous leads strengthen a geographic pattern. Opposing leads may show reciprocal displacement, which can add support when the relationship is real. An isolated change deserves more caution. Measurement uses the reviewed lead- and context-specific policy card; morphology and distribution still matter beyond millimeters.”

**Policy card copy:** “ST measurement policy [version]” / “Reference: [baseline rule]” / “Measure at: [J point or reviewed offset]” / “Threshold: [lead/context rule]” / “Reviewer: [name/date].” If absent: “Numeric threshold layer unavailable — mark method and distribution only.”

**Case contract:** Deterministic heart/lead vector model; an eligible territorial ST-pattern real case; an isolated-change mimic; and a case with reciprocal support. Required full 12-lead, calibration, baseline/J ROIs, lead-level ST values/features, compatible diagnostic statement, and policy version for numeric classification.

**Layout delta:** Heart map, 12-lead territory map, and paired lead magnifiers remain synchronized. A paint tool colors neither diagnosis nor correctness; patterned outlines identify selected/reciprocal groups. Mobile uses the lead map as navigation and stacks selected/opposing leads.

**Required interaction:** Learner places the affected region in the model and predicts positive/negative leads; on real cases, marks baseline/J, measures reviewed points when enabled, paints contiguous leads, links reciprocal leads, and labels any isolated change as limited.

**Tutor script:**

- Opening: “Predict the lead distribution from the vector, then prove it on the full 12-lead.”
- Socratic: “Which leads view the region together, and which view the vector from the opposite direction?”
- Hint 1: “Contiguous means anatomically neighboring viewpoints, not merely adjacent panels on the printout.”
- Hint 2: “Reciprocal evidence must be measured against its own baseline in the opposing leads.”
- Tangent return: “Back to [case]: finish the contiguous set before drawing the reciprocal link.”

**State changes and deterministic gate:** Prediction locks before model reveal. Real-case accepted-lead F1 ≥0.80; reciprocal link endpoints must land on accepted opposing sets. Numeric threshold scoring is impossible without an approved policy. Isolated-change case completes only with a cautious description.

**Exact feedback branches:**

- Correct independent: “Supported. [Contiguous leads] show [finding], and [opposing leads] provide [reciprocal/no reciprocal] evidence. The geographic description is [normalized territory pattern].”
- Correct assisted: “The lead geography is correct after help and records as assisted.”
- Partial: “You found [target leads]. Mark the baseline/J point and inspect the accepted opposing leads before completing the pattern.”
- Wrong: “[Selected leads] are not one anatomical group. Reopen the territory map and follow the shared viewpoint.”
- Unsafe/unsupported: “A reciprocal pattern does not by itself prove an acute culprit vessel or treatment. State the supported geography and evidence limit.”
- Not assessable—correct: “Correct. Numeric threshold status is unavailable because [policy/calibration reason]; direction, morphology, and distribution remain assessable.”
- Not assessable—incorrect: “The full calibrated lead set supports a geographic description. Paint the relevant leads before limiting the call.”

**Equivalent retry:** Different region, lead set, reciprocal relationship, isolated mimic, and measurement-policy availability.

**Accessibility specifics:** Lead painting has an anatomical checkbox tree and opposing-lead link menu. Vector directions are verbalized. The ST policy is readable text and not a hover-only tooltip.

**Cross-mode handoff:** “Train · territory and reciprocal pairs” / “Next · anterior, septal, and lateral descriptions.”

## M9-S2 — Anterior, septal, and lateral: localize without pretending borders are walls

**Source refs:** `SPEC-ONTOLOGY`; `SPEC-ISCHEMIA-ELIGIBILITY`; `ARCH-M9`; `V2-ISCHEMIA`; `INV-R-ISCH`.  
**Eyebrow/title:** “M9 · 3 of 10” / “Precordial and lateral geography”  
**Goal line:** “Use V1–V6 and I/aVL as overlapping viewpoints.”

**Exact lesson copy:**

> “V1–V2 provide septal/right-anterior viewpoints; V3–V4 are more anterior; I, aVL, V5, and V6 provide lateral viewpoints. Real patterns cross textbook borders, and activation or placement can imitate them. Use the contiguous lead set as a working geographic description, report overlap, and name missing or opposing evidence. Do not convert a lead territory directly into a single culprit artery.”

**Territory labels:** “Septal/right-anterior views” · “Anterior views” · “Lateral views” · “Anterolateral overlap” · “Evidence insufficient.”

**Case contract:** Eligible established anterior, lateral, and anterolateral pattern cases plus a V1–V3 placement/conduction mimic. Each real target requires compatible diagnosis/statement and lead-level feature evidence. No isolated “septal infarct” machine label is accepted without qualifying evidence and mimic exclusion.

**Layout delta:** 3D torso rotates between frontal and horizontal planes while the full lead map stays fixed. Matched target/mimic leads open in a comparison tray.

**Required interaction:** Learner paints the involved leads, draws the smallest defensible territory outline on the torso, boxes one supporting waveform region and one mimic check, then writes “pattern involving [territory]” plus confidence.

**Tutor script:**

- Opening: “Let the lead set define the geography; do not start from an artery name.”
- Socratic: “Does this pattern stay within one viewpoint group, or cross into a neighboring territory?”
- Hint 1: “Use V3–V4 for anterior evidence and I/aVL/V5–V6 for lateral evidence.”
- Hint 2: “Before accepting an isolated V1–V2 claim, check QRS morphology and chest-lead placement.”
- Tangent return: “Back to [case]: paint the full contiguous set, then outline the territory.”

**State changes and deterministic gate:** Territory outline must overlap the accepted region and lead-set F1 ≥0.80. The mimic case requires a placement/conduction feature. Culprit-vessel text is rejected.

**Exact feedback branches:**

- Correct independent: “Supported. [Leads] form a [territory/overlap] pattern, with [support] and [missing/opposing evidence].”
- Correct assisted: “The territory description is correct after help and records as assisted.”
- Partial: “Your precordial set is correct. Add the lateral limb/chest leads or explicitly state that lateral extension is not supported.”
- Wrong: “The outlined territory does not match the painted lead viewpoints. Reconnect each lead to its viewing direction.”
- Unsafe/unsupported: “The ECG geography does not prove one culprit artery, timing, or action. Remove the vessel claim.”
- Not assessable—correct: “Correctly limited. [Lead/placement/confound] prevents more specific localization; [broader pattern] remains supported.”
- Not assessable—incorrect: “The packet includes a validated contiguous lead set. Localize at the supported level.”

**Equivalent retry:** Different territory overlap, clearest leads, QRS context, and mimic.

**Accessibility specifics:** The torso outline has a named-region selector. Lead sets use checkboxes. Rotation is replaceable by two static labeled planes.

**Cross-mode handoff:** “M7 · R-wave progression is a modifier, not independent infarction proof.”

## M9-S3 — Inferior patterns and the right-sided question

**Source refs:** `SPEC-ISCHEMIA-ELIGIBILITY`; `ARCH-M9`; `V2-ISCHEMIA`; `INV-R-ISCH`; `CLIN-GROUNDING`.  
**Eyebrow/title:** “M9 · 4 of 10” / “Inferior first, extension second”  
**Goal line:** “Prove an inferior pattern, inspect reciprocal leads, and request right-sided views only when context supports the question.”

**Exact lesson copy:**

> “II, III, and aVF provide inferior viewpoints. I and aVL can offer opposing lateral evidence. When an eligible inferior pattern and clinical context raise a right-ventricular-extension question, correctly placed right-sided leads—commonly including V4R—can add information. The request is a next-data decision, not automatic proof of a vessel or hemodynamic state.”

**Placement card copy:** “Right-sided teaching placement” / “Mirror the relevant precordial position to the right chest according to the reviewed acquisition guide” / “Confirm lead label and calibration before interpretation.”

**Case contract:** Eligible inferior established-pattern real case, inferior mimic, and deterministic right-sided lead-placement/extension model. A real right-sided case requires validated acquisition metadata and lead-level evidence; otherwise it remains a teaching model. No hemodynamic or medication action is inferred.

**Layout delta:** Full 12-lead with inferior and high-lateral magnifiers; torso placement layer opens after inferior evidence is committed. Mobile uses a body-map placement task followed by the enlarged right-sided lead.

**Required interaction:** Learner paints II/III/aVF, links any I/aVL reciprocal evidence, reconstructs reviewed V4R placement, and decides “right-sided leads add relevant data,” “not indicated by this packet,” or “already supplied—interpret,” with a direct mark on the right-sided waveform when present.

**Tutor script:**

- Opening: “Prove the inferior lead pattern before asking for an extension lead.”
- Socratic: “What evidence makes a right-sided view a relevant next question rather than a routine reflex?”
- Hint 1: “Compare II, III, and aVF with I and aVL.”
- Hint 2: “A right-sided lead must be correctly placed and labeled before its polarity means anything.”
- Tangent return: “Back to [case]: complete the inferior/reciprocal pair, then open the placement layer.”

**State changes and deterministic gate:** Placement layer locks until inferior lead-set evidence passes. Body-map target must match the reviewed placement region; if no approved acquisition guide is configured, placement assessment is demonstration-only. Extension interpretation requires a real/validated right-sided lead.

**Exact feedback branches:**

- Correct independent: “Supported. [Inferior leads] show [finding], [lateral leads] show [reciprocal/no reciprocal evidence], and [right-sided request/result] is the proportionate next statement.”
- Correct assisted: “The inferior evidence and right-sided question are correct after help.”
- Partial: “You found the inferior leads. Inspect I/aVL and verify the context before requesting or interpreting a right-sided lead.”
- Wrong: “V4 is not V4R. Lead identity and right-chest placement must be explicit before interpretation.”
- Unsafe/unsupported: “This tracing does not establish a culprit vessel, preload state, or medication decision. Keep the claim at lead geography and next data.”
- Not assessable—correct: “Correct. Right-sided extension is not assessable because [lead/acquisition metadata] is absent. The inferior pattern remains assessable.”
- Not assessable—incorrect: “The inferior and reciprocal leads are readable. Complete that pattern even if extension remains unavailable.”

**Equivalent retry:** Different inferior morphology, reciprocal presence, context relevance, and body-map orientation.

**Accessibility specifics:** Body placement has anatomical text instructions and select lists. Lead links can be made from a paired table. No body-map precision is required beyond the reviewed region.

**Cross-mode handoff:** “Train · inferior/reciprocal geography” / “Clinical chest-pain cases will add context only after ECG commitment.”

## M9-S4 — Posterior pattern: use the mirror, then ask for direct views

**Source refs:** `SPEC-ONTOLOGY`; `SPEC-ISCHEMIA-ELIGIBILITY`; `ARCH-M9`; `V2-ISCHEMIA`; `INV-R-ISCH`; `INV-R-CHRONIC`.  
**Eyebrow/title:** “M9 · 5 of 10” / “The posterior wall may appear as a mirror”  
**Goal line:** “Recognize an anterior mirror pattern and know what posterior leads can clarify.”

**Exact lesson copy:**

> “Posterior electrical change may be viewed indirectly from V1–V3. An eligible pattern can include anterior ST depression with a relatively tall anterior R and upright T, interpreted as a possible mirror of posterior change. These features are not specific. Correctly placed V7–V9 can provide more direct posterior views. Request the leads when the evidence supports the question; do not award posterior infarction from one tall R.”

**Model controls:** “View from V2” · “Mirror waveform” · “View from V8” · “Show direct posterior lead.”

**Case contract:** Deterministic anterior/posterior mirror model, one eligible posterior-pattern case if available, and two mimics (RBBB/RVH and normal variation). Real scoring requires compatible posterior statement plus V1–V3 feature evidence and, for direct confirmation, actual V7–V9 data/metadata. Sparse pool status must be surfaced.

**Layout delta:** V1–V3 sit beside a mirror pane; V7–V9 appear only when present or in the labeled model. Full 12-lead remains available. Mobile uses “Anterior view / Mirrored concept / Direct posterior view” tabs.

**Required interaction:** Learner marks ST, R, and T features in V1–V3, flips the model, predicts the direct posterior appearance, checks QRS width/terminal morphology for mimics, and places a “request V7–V9” card on the tracing when warranted.

**Tutor script:**

- Opening: “Treat the mirror as a hypothesis generator, then test specificity.”
- Socratic: “Which anterior features would reverse into a direct posterior pattern, and which mimic can also make V1 look R-dominant?”
- Hint 1: “Mark ST, R, and T as a bundle; one tall R is not enough.”
- Hint 2: “Check QRS duration and terminal forces before calling the anterior R a mirror.”
- Tangent return: “Back to [case]: finish the V1–V3 feature bundle and mimic check before requesting posterior leads.”

**State changes and deterministic gate:** Three-feature bundle plus mimic check required. Posterior conclusion remains “posterior concern/pattern” unless direct eligible evidence and policy permit more. Request card is correct only on the intended packet.

**Exact feedback branches:**

- Correct independent: “Supported. V1–V3 show [feature bundle], [mimic check] is [result], and posterior leads are the appropriate clarifying data.”
- Correct assisted: “The mirror bundle is correct after help and records as assisted.”
- Partial: “You found ST depression. Add the anterior R/T pattern and exclude the conduction/chamber mimic before requesting posterior confirmation.”
- Wrong: “A tall R in V1 alone is nonspecific. Inspect QRS terminal morphology and the full V1–V3 ST/R/T bundle.”
- Unsafe/unsupported: “This evidence does not prove an acute posterior infarction, culprit vessel, or action. Use ‘posterior concern—obtain direct leads’ when supported.”
- Not assessable—correct: “Correct. Direct posterior confirmation is not assessable because V7–V9 are absent. The anterior mirror concern remains assessable.”
- Not assessable—incorrect: “The V1–V3 bundle is readable. Evaluate the mirror concern even if direct leads are unavailable.”

**Equivalent retry:** Different anterior bundle, rate, mimic, and presence/absence of posterior leads.

**Accessibility specifics:** Mirror transformation has static written before/after polarity. The “request leads” action is a button alternative. Posterior placement has a text-only reviewed guide.

**Cross-mode handoff:** “Train · posterior versus RBBB/RVH” appears only if enough contract-valid cases exist; otherwise “Needs more reliable cases.”

## M9-S5 — ST depression and T inversion: rank causes from distribution and dynamics

**Source refs:** `SPEC-ONTOLOGY`; `SPEC-ISCHEMIA-ELIGIBILITY`; `ARCH-M9`; `V2-ISCHEMIA`; `INV-R-ISCH`; M8-S1/M8-S2/M8-S8 in this artifact.  
**Eyebrow/title:** “M9 · 6 of 10” / “Nonspecific does not mean meaningless”  
**Goal line:** “Rank ischemia concern, secondary change, and other alternatives without binary overcall.”

**Exact lesson copy:**

> “ST depression and T-wave inversion are shared findings. Their distribution, depth, morphology, QRS relationship, symptoms, and genuine change over time alter concern. Dynamic contiguous primary change can carry different weight from stable discordant strain, bundle-related recovery, electrolyte/drug effects, or isolated nonspecific change. Describe first, then rank alternatives and state what would change the ranking.”

**Ranking-board labels:** “More compatible” · “Plausible alternative” · “Less supported” · “Cannot rank without [datum].” Evidence axes: “Distribution” · “Morphology” · “QRS relationship” · “Prior/serial” · “Context.”

**Case contract:** Four evidence matrices: LVH strain, BBB/pacing secondary change, eligible ischemic ST–T/chronic case, and nonspecific/ambiguous change. If a dynamic example lacks validated serial data, it is a teaching model and cannot award acute mastery. Context cards are separately authored.

**Layout delta:** Full ECG plus ranking board; matched leads across cases can be pinned. Context/serial columns remain masked until the learner commits waveform description.

**Required interaction:** Learner marks ST/T morphology and distribution, classifies QRS relationship, then reveals context/prior if available and reorders hypotheses with one trace-backed discriminator and one “what would change my mind” datum.

**Tutor script:**

- Opening: “Commit the tracing description before seeing the story.”
- Socratic: “Which finding is primary to recovery, and which could be explained by the QRS pattern?”
- Hint 1: “Use distribution and QRS discordance before symptom context.”
- Hint 2: “A valid prior can move a hypothesis; an incomparable prior cannot.”
- Tangent return: “Back to [case]: finish the ECG-only ranking before opening context.”

**State changes and deterministic gate:** Context cannot reveal before description passes. Ranking uses rule-backed evidence tokens, not model semantics. A cause can rank first only when its required discriminator exists. One needed datum is mandatory.

**Exact feedback branches:**

- Correct independent: “Well ranked. [Finding/distribution] plus [discriminator] makes [category] more compatible, while [alternative] remains plausible. [Datum] would most change the ranking.”
- Correct assisted: “The ranking is now supported after help and records as assisted.”
- Partial: “The waveform description is correct. Add its QRS relationship or valid comparison before ranking etiology.”
- Wrong: “Your top cause conflicts with [visible discriminator]. Reopen [lead/context field] and reorder the evidence.”
- Unsafe/unsupported: “Do not label a chronic/nonspecific tracing ‘acute ischemia’ or delay a reviewed escalation solely because change is nonspecific. Use the packet’s supported pattern and context limit.”
- Not assessable—correct: “Correct. Etiologic ranking is limited by [missing datum], but [ST/T description] is assessable.”
- Not assessable—incorrect: “The packet includes [distribution/QRS/prior] evidence sufficient for the intended ranking. Mark it first.”

**Equivalent retry:** Different morphology, distribution, QRS context, comparison validity, and missing datum.

**Accessibility specifics:** Ranking drag has numbered dropdowns. Masked context announces when available. Matched-lead comparison is mirrored in a table.

**Cross-mode handoff:** “Train · primary versus secondary ST–T” / “Clinical · what would change your mind?”

## M9-S6 — Q waves and established infarction: describe scar-pattern evidence, not timing

**Source refs:** `SPEC-ISCHEMIA-ELIGIBILITY`; `ARCH-M9`; `V2-ISCHEMIA`; `INV-R-ISCH`; `INV-R-PRECISION`; M7-S5 in this artifact.  
**Eyebrow/title:** “M9 · 7 of 10” / “Q-wave evidence needs criteria and territory”  
**Goal line:** “Measure initial negative deflections, group them anatomically, and compare a valid prior.”

**Exact lesson copy:**

> “A Q wave is the initial negative QRS deflection before any positive R wave. Q waves can support an established infarction pattern when reviewed width/depth or QS criteria, contiguous distribution, and the broader QRS context agree. Normal septal q waves, lead placement, conduction, and chamber patterns can mimic concern. Q waves may persist, disappear, or be absent despite infarction; they do not timestamp the event.”

**Criterion card copy:** “Q-wave policy [version]” / “Measure width from [onset rule]” / “Measure depth relative to [reference]” / “Required lead distribution: [rule]” / “Context exclusions: [rules].”

**Case contract:** Eligible established anterior/inferior/lateral Q-wave cases, normal septal q comparison, and placement/conduction mimic. Fine scoring requires high-rate or validated fiducials and an approved criterion card. Required full lead-level evidence and compatible diagnostic statement.

**Layout delta:** QRS onset magnifiers link to a territory map and a criterion notebook. Current/prior stack appears only when comparison-valid. Mobile selects one lead at a time and pins the cross-lead distribution.

**Required interaction:** Learner identifies whether the initial deflection is q/Q/QS or not Q, measures width/depth where valid, paints contiguous distribution, checks mimic context, and writes “established [territory] infarction-compatible Q-wave pattern” or a limited descriptive alternative.

**Tutor script:**

- Opening: “Confirm that the negative deflection is initial, then measure and map it.”
- Socratic: “Is this a normal small septal q, a pathologic-criteria candidate, or a later negative component that is not a Q wave?”
- Hint 1: “A negative deflection after an R is an S wave, not a Q wave.”
- Hint 2: “One Q wave is not a territory; use contiguous distribution and the reviewed criterion.”
- Tangent return: “Back to [lead]: classify the initial deflection before measuring it.”

**State changes and deterministic gate:** Initial-deflection classification precedes calipers. Criterion status scores only with approved policy. Lead-set F1 ≥0.80 and one mimic check required. “Acute/new” text is rejected absent valid comparison.

**Exact feedback branches:**

- Correct independent: “Supported. [Leads] contain [Q/QS evidence] meeting the reviewed pattern criteria, compatible with an established [territory] infarction pattern. Timing is not determined.”
- Correct assisted: “The Q-wave classification and territory are correct after help.”
- Partial: “You measured the deflection. Confirm it is initial and demonstrate a contiguous distribution before the pattern label unlocks.”
- Wrong: “This negative component follows an R wave, so it is an S wave—not a Q wave.”
- Unsafe/unsupported: “Q waves do not by themselves establish an acute event, symptom cause, culprit vessel, or action. Remove the timing/causal claim.”
- Not assessable—correct: “Correct. [Criterion/timing/newness] is not assessable because [reason]. [Visible QRS description] remains assessable.”
- Not assessable—incorrect: “The initial deflection and accepted lead set are readable. Classify and map them first.”

**Equivalent retry:** Different territory, Q/QS morphology, septal-q mimic, placement issue, and prior availability.

**Accessibility specifics:** Initial-deflection types have textual waveform definitions. Width/depth use numeric fields. Territory painting has an ordered lead checklist.

**Cross-mode handoff:** “Train · Q wave versus S wave and septal q” / “M7 · poor R progression alone remains insufficient.”

## M9-S7 — Prior and serial comparison: validate comparability before declaring change

**Source refs:** `ARCH-M9`; `V2-ISCHEMIA`; `INV-R-CHRONIC`; `INV-R-STAFF`; `CLIN-DISPLAY`; `CLIN-GRADING`; `CLIN-GROUNDING`.  
**Eyebrow/title:** “M9 · 8 of 10” / “Change is a measurement, not a vibe”  
**Goal line:** “Align ECGs, verify acquisition, and localize what truly changed.”

**Exact lesson copy:**

> “A prior or serial ECG can be more informative than a single tracing only when the comparison is valid. Confirm patient/case identity, lead set and order, gain, speed, acquisition context, and signal quality; align matched leads; then mark what changed, what did not, and what remains incomparable. ‘New,’ ‘dynamic,’ and ‘evolving’ are earned temporal claims.”

**Comparison-validity labels:** “Identity matched” · “Lead set/order matched” · “Gain matched” · “Speed matched” · “Signal interpretable” · “Acquisition context known” · “Comparison valid” · “Comparison limited/invalid.”

**Case contract:** One valid chronic prior/current pair, one deliberately invalid pair (gain/lead-placement/order mismatch), and a controlled serial teaching model. True acute serial scoring is enabled only for validated STAFF-III or another approved acute corpus with licensing/ingest/measurement review. PTB-XL pairings cannot masquerade as acute evolution.

**Layout delta:** Stacked full 12-leads at identical scale, synchronized pan/zoom, “Ghost overlay,” “Difference view,” and a validity checklist. Mobile stacks one matched lead pair at a time; overlay is optional.

**Required interaction:** Learner completes validity checks, aligns two anchor beats/leads, marks one changed and one unchanged region, and submits “new,” “old/unchanged,” or “cannot determine,” with the deciding constraint. On the invalid pair, the only passing temporal answer is “cannot determine.”

**Tutor script:**

- Opening: “Before looking for change, prove that the recordings can be compared.”
- Socratic: “Could this apparent amplitude or ST difference be created by gain, placement, or lead mismatch?”
- Hint 1: “Match lead identity and scale before using the overlay.”
- Hint 2: “A valid comparison needs one explicit unchanged anchor as well as the changed region.”
- Tangent return: “Back to the validity checklist: resolve [missing check] before declaring change.”

**State changes and deterministic gate:** Overlay/difference tools stay locked until identity, scale, and lead mapping pass. ROI change scoring uses matched lead/time geometry. Speed bonus is disabled for “cannot determine.” Temporal adjectives are forbidden on invalid comparisons.

**Exact feedback branches:**

- Correct independent—changed: “Valid comparison. [Finding] is new/changed in [leads], while [anchor] is unchanged. The temporal claim is supported by this pair.”
- Correct independent—unchanged: “Valid comparison. [Finding] is present and unchanged across comparable ECGs.”
- Correct limited: “Correct. The recordings are not comparable because [constraint], so old-versus-new cannot be determined.”
- Correct assisted: “The comparison conclusion is correct after help and records as assisted.”
- Partial: “You marked a difference. Complete the scale/lead validity checks and one unchanged anchor before calling it change.”
- Wrong: “This apparent difference follows [gain/lead mismatch], not a validated temporal change.”
- Unsafe/unsupported: “Do not use ‘acute,’ ‘evolving,’ or ‘new’ when comparison validity or temporal provenance fails.”
- Not assessable—correct: “Correct. Old-versus-new is not assessable because [comparison flaw]. The current ECG finding remains assessable and should still be stated.”
- Not assessable—incorrect: “This pair is fully comparable and contains a manifest-backed change. Align and mark it before limiting the conclusion.”

**Equivalent retry:** Different mismatch type, changed lead set, unchanged anchor, and acquisition interval. No pseudo-serial chronic pairing.

**Accessibility specifics:** Overlay is never required; a matched-lead difference table is equivalent. Validity checks are announced before waveform differences. Synchronized pan can be disabled.

**Cross-mode handoff:** “Clinical · old-or-new” only for comparable pairs / “Acute serial practice · Locked—validated acute corpus required” when unavailable.

## M9-S8 — Mimic laboratory: find the discriminator on the trace

**Source refs:** `SPEC-ISCHEMIA-ELIGIBILITY`; `SPEC-MISCONCEPTIONS`; `ARCH-M9`; `V2-ISCHEMIA`; `INV-R-ISCH`; `INV-R-CLINREV`; M7-S6/M8-S8 in this artifact.  
**Eyebrow/title:** “M9 · 9 of 10” / “Target, mimic, normal”  
**Goal line:** “Discriminate ischemia-compatible patterns from LVH, BBB/pacing, variants, pericarditis, electrolyte effects, prior patterns, and lead error.”

**Exact lesson copy:**

> “Expert discrimination is not a longer label list. It is the ability to find the feature that makes one explanation fit better than a close alternative. Compare distribution, reciprocal relationship, QRS context, ST/T proportionality and shape, PR/baseline findings, Q waves, lead placement, prior/serial behavior, and clinical context. Advanced occlusion criteria in BBB or pacing are allowed only as a separately reviewed, versioned layer.”

**Mimic-family labels:** “LVH/strain” · “BBB/pacing” · “Early-repolarization/age-related variant” · “Pericarditis-compatible” · “Electrolyte/drug pattern” · “Established infarction/aneurysmal pattern” · “Lead error” · “Nonspecific ST–T.”

**Case contract:** At least six target–mimic–normal triads, with two distinct mimics for each ischemia target across the bank. Real cases require lead-level evidence for every scored discriminator. Advanced BBB/pacing occlusion rules require approved criteria cards and human-reviewed items; otherwise those examples are labeled “Demonstration only — advanced criterion layer not scored.”

**Layout delta:** Three matched full ECGs; a discriminator rail opens identical lead panels across the triad. Luna is concise by default. Mobile stacks matched panels and uses a persistent triad label.

**Required interaction:** Learner commits an ECG-only rank, clicks the single most diagnostic lead/region for each pair, tags the discriminator, then reveals prior/context and revises if justified. At least one triad must end “overlap—insufficient data.”

**Tutor script:**

- Opening: “Do not ask which label feels familiar. Ask which visible feature separates this pair.”
- Socratic: “What finding would be expected under one explanation and surprising under the other?”
- Hint 1: “Use QRS context and distribution before a named ST shape.”
- Hint 2: “If the discriminator requires a prior or symptom, say that instead of inventing it.”
- Tangent return: “Back to triad [n]: click one trace region that changes the comparison.”

**State changes and deterministic gate:** ROI hit uses accepted lead/region geometry; tag must match the rule-backed discriminator. A correct label with no proof cannot complete. Revision is credited only when newly revealed evidence warrants it.

**Exact feedback branches:**

- Correct independent: “Discriminator found. [Trace feature] in [lead/region] makes [category] more compatible than [mimic], while [remaining uncertainty] is preserved.”
- Correct limited: “Correct. The visible features overlap, and [missing datum] is required to rank them safely.”
- Correct assisted: “The discriminator is now correct after help and records as assisted.”
- Partial: “Your category is plausible, but the decisive region is unmarked. Prove the comparison on the trace.”
- Wrong: “The selected feature is shared by both cases. Find a feature that differs: [eligible evidence family].”
- Unsafe/unsupported: “Do not apply an unreviewed advanced criterion, acute label, or treatment action. Use the available discriminator or state the missing evidence.”
- Not assessable—correct: “Correct. The visible patterns overlap and the required discriminator is [missing datum]. State the shared findings and request that datum.”
- Not assessable—incorrect: “This triad contains a manifest-backed discriminator in [accepted leads]. Locate it before limiting the comparison.”

**Equivalent retry:** New target/mimic/normal records, different discriminator family and lead, same difficulty vector, no repeated triad.

**Accessibility specifics:** Each ROI has a structured lead/segment alternative. Triad differences can be navigated by table. After submission, screen reader announces the discriminator before the labels.

**Cross-mode handoff:** “Train · your missed mimic family” / “Rapid · unannounced ischemia/mimic mix.”

## M9-S9 — Chest-pain transfer and the honest data gate

**Source refs:** `SPEC-ISCHEMIA-ELIGIBILITY`; `SPEC-VIEWER`; `ARCH-M9`; `V2-ISCHEMIA`; `INV-R-ISCH`; `CLIN-MODES`; `CLIN-GROUNDING`; `CLIN-GRADING`; `INV-R-CHRONIC`; `INV-R-STAFF`; `INV-R-AUTHCTX`; `INV-R-CLINREV`; `ARCH-MODE-HANDOFF`.  
**Eyebrow/title:** “M9 · 10 of 10” / “Finding → geography → differential → urgency”  
**Goal line:** “Perform an independent evidence chain and stop exactly where corpus or clinical governance stops.”

**Exact lesson copy:**

> “For chest pain, run two linked processes: interpret the ECG completely, and assess the clinical situation through a reviewed local pathway. Describe the tracing, localize supported patterns, compare mimics and priors, state confidence, and identify what additional data are needed. A nondiagnostic ECG does not by itself exclude an acute coronary syndrome. Urgency and action scoring require authored context plus clinician-reviewed policy; acute mastery requires acute or true serial evidence.”

**Lane cards:**

- “Established/chronic interpretation lane” — “Eligible resting ECGs; supports chronic Q-wave and stable ST–T pattern practice. Does not award acute recognition.”
- “Acute/serial interpretation lane” — “Requires validated acute/serial corpus, lead-level evidence, and clinical review.”
- Locked-state copy: “Not available yet: the current corpus cannot honestly award acute/evolving mastery.”

**Tutor opening:** “I’ll remain silent while you interpret. The authored context appears only after your ECG evidence is committed.”  
**Socratic on request:** “Which link is missing: waveform, geography, mimic, comparison, confidence, or reviewed urgency category?”  
**Hint 1:** “Describe and localize before opening the symptom timeline.”  
**Hint 2:** “If acute provenance or a valid serial comparison is absent, remove temporal language.”  
**Tangent return:** “Back to case [n], with your full tracing, marks, and draft preserved.”

**Case contract:** Four established/chronic real cases sampled without replacement: established infarction-compatible, ischemic/nonspecific ST–T, a mimic, and a nondiagnostic/normal ECG. A fifth acute/serial case appears only if corpus and review gates pass. Authored context fields are disclosed and cannot alter ECG truth. Action layer requires approved policy/safety tokens; otherwise learner selects needed information/escalation-to-local-pathway only.

**Layout delta:** Full 12-lead, evidence chain, provenance badge, and masked context panel. Acute lane tile remains visible even when locked so the limitation is taught rather than hidden. Mobile uses the same sequence with no side-by-side compression.

**Required interaction:** Per case learner verifies quality/calibration, marks decisive leads, submits full ECG description/localization/mimic/confidence, then reveals context and chooses a reviewed urgency/action category or, when locked, identifies required next data and local-pathway escalation. No generic MCQ; every clinical option is enabled only after trace proof.

**Deterministic scoring and gate:** ECG recognition 35%, localization/reciprocal 20%, mimic/comparison 20%, confidence 10%, clinical calibration/action 15% only when reviewed. If action is locked, its weight redistributes to information need/epistemic restraint and does not create action mastery. Pass ≥82%, no acute claim from chronic data, no culprit-vessel overclaim, and correct response to the nondiagnostic case.

**Exact feedback branches:**

- Fully correct independent: “Supported. You described [finding], localized [geography], addressed [mimic/prior], and matched the packet’s allowed urgency language without exceeding the evidence.”
- Correct chronic-lane limit: “Correct. This real resting ECG supports [established/chronic interpretation], not acute or evolving mastery.”
- Correct acute-lane lock: “Correct. The required acute/serial evidence is not available, so this lane cannot be scored.”
- Correct assisted: “The evidence chain is supported after help. It completes the lesson but not independent chest-pain transfer.”
- Partial: “You have [credited ECG evidence]. Complete [geography/mimic/prior/needed datum] before the context conclusion unlocks.”
- Wrong: “Your [localization/timing] conflicts with [lead or provenance evidence]. Reopen [accepted lead/data source].”
- Unsafe/unsupported: “This packet does not support the acute, culprit-vessel, discharge, activation, or treatment claim you selected. Use only the reviewed category—or state that the action layer is unavailable.”
- Not assessable—correct: “Correctly limited. [Supported interpretation] is assessable; [acute/new/action claim] is not because [manifest reason].”
- Not assessable—incorrect: “The tracing contains readable lead-level evidence for [finding/geography]. Complete that interpretation even if action remains unavailable.”

**Equivalent retry:** Contract-matched different record/context, different territory/mimic, different prior validity, and no reused decisive ROI.

**Accessibility specifics:** Evidence chain is an ordered form; context reveal announces source; provenance and locks are text. No timer in Guided. Results report ECG recognition separately from clinical calibration/action.

**Completion copy:**

> “Module complete. You can now build lead-supported ischemia and established-infarction patterns, use reciprocal and comparison evidence, distinguish close mimics, and protect the boundary between a resting ECG, acute timing, coronary anatomy, and clinical action.”

**Cross-mode handoff cards:**

- “Train · Territory, reciprocal, and mimic contrasts” — “Repeat the exact evidence family that failed.”
- “Rapid · Mixed ischemia/mimic reads” — “Tutor stays silent until submission.”
- “Clinical · Chest pain” — “Only reviewed case/action packets; acute lane remains provenance-gated.”
- “Next guided module · Integrated interpretation” — “Combine every domain into a prioritized read and concise handoff.”

---

# M10 — Integrated Interpretation and Clerkship-to-Clinical Transfer

**Module card copy:** “Interpret the whole ECG, decide what matters first, audit the machine, compare a prior, and communicate a concise evidence-linked synthesis across clinic, ward, and ED-style teaching cases.”  
**Estimated guided time:** “85–110 min · self-paced · resumable by case chapter”  
**Prerequisite receipt:** Rhythm transfer through M6 and morphology/repolarization/localization transfer through M9. Learners may enter by readiness override, but a failed prerequisite domain opens the smallest repair scene before the affected case.  
**Exit receipt:** independent complete sweep, prioritized synthesis, evidence-linked machine audit, valid comparison, context-calibrated next-data/escalation reasoning, and concise handoff.  
**Persistent banner:** “Interpretation mastery and clinical-action mastery are separate. An unavailable action layer never changes ECG truth.”

## M10-S0 — Choose your framework; keep every domain

**Source refs:** `SPEC-FRAMEWORKS`; `ARCH-M10`; `V2-INTEGRATION`; `FOUND-SWEEP`; `ARCH-MODE-HANDOFF`.  
**Eyebrow/title:** “M10 · 1 of 12” / “Two routes through the same ECG”  
**Goal line:** “Map Standard and HEARTS, then select the language Luna will use.”

**Exact lesson copy:**

> “A framework is a memory scaffold, not a substitute for seeing. Both routes begin with calibration and quality, cover the same objective domains, and end with synthesis. Standard follows rate → rhythm → axis → intervals → conduction/QRS → chambers/progression → ST–T → synthesis. HEARTS groups them as Heart rate/rhythm → Electrical axis → Atria/intervals → R-wave progression/QRS → T waves/ST → Synthesis. Priority comes after completeness.”

**Framework cards:**

- “Preflight” — “Identity, calibration, paper speed, gain, quality, lead set.”
- “Standard” — “Rate · Rhythm · Axis · Intervals · Conduction/QRS · Chambers/progression · ST–T · Synthesis.”
- “HEARTS” — “H Heart rate/rhythm · E Electrical axis · A Atria/intervals · R R-wave progression/QRS · T T waves/ST · S Synthesis.”
- Choice buttons: “Use Standard” · “Use HEARTS” · “Switch anytime.”

**Case contract:** Framework mapping model with one normal full 12-lead. No diagnosis is scored. The learner-profile receipt stores preferred label order but not a different objective set.

**Layout delta:** Two parallel tracks occupy the stage with draggable domain cards between them. The ECG highlights the relevant region when a mapped pair is selected. Mobile stacks tracks and shows one mapping pair at a time.

**Required interaction:** Learner orders both tracks, draws mappings between equivalent fields, identifies preflight as shared, then selects a default and completes one spoken/typed sweep using that vocabulary.

**Tutor script:**

- Opening: “Choose the language that lowers your working-memory load. I’ll adapt, but I won’t let a domain disappear.”
- Socratic: “Where does chamber evidence live in HEARTS, and where does QT live?”
- Hint 1: “Atria and intervals belong under A; QT is revisited with T/repolarization while still recorded as an interval.”
- Hint 2: “Calibration and quality come before either mnemonic.”
- Tangent return: “Back to the framework map: connect [domain] before choosing your default.”

**State changes and deterministic gate:** All eight Standard domains must map to HEARTS without omission. The selected preference changes subsequent labels and tutor wording only. Completion requires a full ordered sweep.

**Exact feedback branches:**

- Correct independent: “Mapped. You chose [framework], and every objective domain remains present. Luna will use that order from the next scene.”
- Correct assisted: “The map is complete after help. Your framework preference is saved.”
- Partial: “[Mapped domains] are correct. [Missing domain] has no home yet, so the framework is incomplete.”
- Wrong: “Synthesis cannot replace a missing observation domain. Return [domain] to the track before prioritizing.”
- Unsafe/unsupported: “A mnemonic cannot generate a diagnosis or action. Use it to organize the complete evidence sweep.”
- Not assessable—correct: “No clinical diagnosis is being assessed here. Framework completeness is assessable.”
- Not assessable—incorrect: “Both framework definitions and all domain cards are present. Complete the mapping.”

**Equivalent retry:** Shuffled domain cards, different normal ECG, and the opposite framework preselected.

**Accessibility specifics:** Mapping has paired dropdowns and an ordered list alternative. Screen reader announces both labels in each mapping. No drag is required.

**Cross-mode handoff:** Persistent control appears in every later scene: “Framework: [Standard/HEARTS] · Change.”

## M10-S1 — Preflight, then a complete sweep

**Source refs:** `SPEC-FRAMEWORKS`; `SPEC-VIEWER`; `SPEC-ONTOLOGY`; `ARCH-M10`; `FOUND-SWEEP`; `INV-R-NORMAL`.  
**Eyebrow/title:** “M10 · 2 of 12” / “Completeness before cleverness”  
**Goal line:** “Perform a full structured interpretation on a normal/near-normal ECG.”

**Exact lesson copy:**

> “A reliable interpretation starts by proving that the recording can answer the question. Confirm calibration, speed, gain, lead set, artifact, and comparability. Then complete every framework field—even when the answer is ‘within the supported reference’ or ‘not assessable.’ Normal is a conclusion earned by a negative sweep, not a first impression.”

**Sweep rail:** Uses the learner’s selected framework. Each field has buttons “Mark evidence,” “Within supported reference,” “Abnormal finding,” and “Not assessable from this recording.”

**Case contract:** One `normal_ecg`-eligible real case and one near-normal/normal-variant case. Requires concordant normal support, no major conflicting statements, acceptable signal, and near-normal rate/QRS/QTc/axis where available. Full 12-lead plus long II unless source format differs transparently.

**Layout delta:** Full 12-lead dominates the stage; the sweep rail sits left on desktop/laptop and collapses above on mobile. Luna uses the learner-selected terminology.

**Required interaction:** Learner marks calibration pulse/lead set, measures rate and key intervals, estimates axis, inspects conduction/R progression/chambers/ST–T, and fills every field. A final “No major abnormality supported” synthesis unlocks only after the rail is complete.

**Tutor script:**

- Opening: “I’ll ask only for the next missing domain. You decide what counts as evidence.”
- Socratic: “Which unchecked field could still overturn a ‘normal’ conclusion?”
- Hint 1: “Start with the calibration pulse and lead inventory.”
- Hint 2: “Use the normal-reference card, but prove each field on this ECG.”
- Tangent return: “Back to [framework field]: your earlier measurements and marks are intact.”

**State changes and deterministic gate:** Every field requires either a valid measurement/mark or a manifest-backed not-assessable reason. Normal synthesis requires no major abnormal allowed claim and all critical domains complete. Free text cannot bypass structured fields.

**Exact feedback branches:**

- Correct independent: “Complete. This ECG supports [normalized full read]. You earned the normal/near-normal synthesis by checking every domain.”
- Correct assisted: “The full sweep is correct after help. It completes the lesson but not independent integrated mastery.”
- Partial: “Your completed domains are supported. [Missing field] remains unchecked, so the final synthesis stays locked.”
- Wrong: “The ‘normal’ conclusion conflicts with [manifest-backed finding]. Reopen [domain] and mark the evidence.”
- Unsafe/unsupported: “A screening conclusion cannot become medical clearance or treatment advice in this scene. Keep the output to the ECG interpretation.”
- Not assessable—correct: “Correct. [Field] cannot be assessed because [recording reason], and you still completed the remaining sweep.”
- Not assessable—incorrect: “[Field] is readable in [lead/measurement]. Complete it before using ‘not assessable.’”

**Equivalent retry:** Different normal/variant record, rate, axis, transition, and minor artifact.

**Accessibility specifics:** The entire sweep is an ordered form; each measurement has numeric alternatives; a text waveform summary appears only after the learner’s marks. Focus returns to the next incomplete field.

**Cross-mode handoff:** “Train · normal versus subtle abnormal” / “Next · turn a complete list into a prioritized synthesis.”

## M10-S2 — Observations, interpretation, consequence

**Source refs:** `ARCH-M10`; `V2-INTEGRATION`; `SPEC-MASTERY`; `CLIN-GROUNDING`.  
**Eyebrow/title:** “M10 · 3 of 12” / “Prioritize without dropping evidence”  
**Goal line:** “Separate what you saw, what it supports, and why it matters.”

**Exact lesson copy:**

> “A complete read and a useful presentation are different products. First preserve the full evidence. Then sort each statement into observation, interpretation, confidence/limit, or clinical consequence. Lead with the supported finding most likely to change the current clinical question, not the order in which you noticed it. Never use urgency to strengthen an uncertain ECG label.”

**Column labels:** “Observation” · “Interpretation” · “Confidence/limit” · “Clinical consequence or next data.”  
**Compression prompt:** “In one sentence: rate/rhythm + highest-priority finding + comparison/uncertainty + context-relevant implication.”

**Case contract:** Three eligible multi-finding packets: one benign/incidental, one conduction/rhythm priority, and one ST–T/chamber ambiguity. Authored context is separated and appears only after the ECG-only sort. Consequence tokens require review; otherwise they are phrased as “next data/clinical correlation.”

**Layout delta:** Full ECG remains pinned above a four-column statement board. A “Full evidence / Handoff view” toggle changes organization, never hides the original marks. Mobile uses one column at a time with a persistent statement count.

**Required interaction:** Learner marks evidence, sorts case statements into the four columns, ranks findings for the provided context, and compresses them with structured sentence tokens plus optional free text.

**Tutor script:**

- Opening: “Do the ECG-only sort first. Context may reorder priority, but it cannot rewrite the waveform.”
- Socratic: “Which sentence is an observation, and which adds a mechanism or consequence that needs another source?”
- Hint 1: “Lead and measurement language usually belongs in observation.”
- Hint 2: “Put uncertainty next to the interpretation it limits—not in a vague final disclaimer.”
- Tangent return: “Back to [statement]: place its evidence layer before ranking it.”

**State changes and deterministic gate:** Each statement has a packet-defined epistemic type. Ranking unlocks after the ECG-only sort. Completion requires all critical findings in the full view and a concise synthesis containing the highest-priority supported item plus a limit.

**Exact feedback branches:**

- Correct independent: “Clear and calibrated. Your full record keeps [evidence], while the handoff leads with [priority finding] and states [limit/next data].”
- Correct assisted: “The evidence layers and priority are correct after help.”
- Partial: “The priority finding is right, but your sentence omits [comparison/uncertainty/rhythm]. Add it without re-expanding the whole sweep.”
- Wrong: “You ranked [incidental/unsupported finding] above [context-relevant supported finding]. Recheck what changes the current question.”
- Unsafe/unsupported: “Urgency cannot convert an uncertain observation into a certain diagnosis or treatment order. Restore the evidence limit.”
- Not assessable—correct: “Correct. The clinical consequence is unavailable without [context/policy], while the ECG interpretation remains assessable.”
- Not assessable—incorrect: “The packet provides the context needed for the intended priority rank. Use it after preserving the ECG-only interpretation.”

**Equivalent retry:** Different multi-finding combination, context, priority order, and missing evidence layer.

**Accessibility specifics:** Sorting has dropdown equivalents. The compressed sentence is assembled from accessible tokens and can be edited. No penalty for speech accent, grammar style, or typing speed.

**Cross-mode handoff:** “Rapid will ask for the handoff view; review always preserves the full evidence view.”

## M10-S3 — Audit the machine: trust measurements provisionally, re-derive claims

**Source refs:** `ARCH-M10`; `V2-INTEGRATION`; `SPEC-VIEWER`; `CLIN-GROUNDING`; `CLIN-DISPLAY`; `CLIN-GRADING`.  
**Eyebrow/title:** “M10 · 4 of 12” / “Spot the unsupported machine sentence”  
**Goal line:** “Verify numbers and prove or refute interpretation statements on the waveform.”

**Exact lesson copy:**

> “Automated measurements and interpretation statements are different claims. A rate or interval may be useful after boundary verification; a diagnostic sentence still needs waveform proof. Audit each line as ‘verified,’ ‘plausible—needs manual check,’ or ‘unsupported/incorrect.’ To challenge a sentence, select it and mark the lead region that disproves it.”

**Machine-panel labels:** “Machine measurement” · “Machine interpretation” · “Verify boundary” · “Flag sentence” · “Click waveform proof” · “Rewrite with supported wording.”

**Case contract:** Three full 12-lead cases with authentic or authored machine reports: one wrong chamber/MI overread, one rhythm/conduction error, and one mostly correct report with a measurement requiring boundary adjustment. Every wrong statement has a rule-backed trace discriminator and accepted ROI.

**Layout delta:** Machine panel occupies the right of the full ECG; selecting a sentence highlights no waveform until the learner marks proof. Mobile shows the report below the full-board mini-map and opens the selected lead at full width.

**Required interaction:** Learner verifies two machine measurements with calipers, tags every report line, selects one bad sentence, clicks/boxes disproving evidence, and rewrites it with packet-approved structured wording.

**Tutor script:**

- Opening: “Do not accept or reject the whole report. Audit one claim at a time.”
- Socratic: “Which waveform boundary supports the number, and which lead feature supports the interpretation?”
- Hint 1: “A correct number can coexist with a wrong label.”
- Hint 2: “Your challenge is incomplete until you click the trace evidence.”
- Tangent return: “Back to machine line [n]: verify or refute it with one waveform action.”

**State changes and deterministic gate:** Report tags are deterministic. Measurement tolerance follows source quality. The bad-sentence ROI must hit accepted geometry and rewrite tokens must stay inside allowed claims. No report-wide thumbs-up/down completes.

**Exact feedback branches:**

- Correct independent: “Audit complete. [Measurements] are verified/adjusted, and ‘[bad sentence]’ is unsupported because [trace evidence]. Your rewrite—‘[supported wording]’—matches the case.”
- Correct assisted: “The audit is correct after help and records as assisted.”
- Partial: “You flagged the correct sentence. Click the lead/region that disproves it and rewrite the claim.”
- Wrong: “The selected sentence is supported by [evidence]. Recheck the line whose claim conflicts with [discriminator].”
- Unsafe/unsupported: “Do not replace one overread with a stronger unsupported diagnosis or action. Rewrite only what the trace and packet support.”
- Not assessable—correct: “Correct. [Machine claim] cannot be verified because [boundary/lead] is unavailable; mark it ‘needs manual/other-data check.’”
- Not assessable—incorrect: “The decisive lead and boundary are present. Audit them before limiting the report.”

**Equivalent retry:** Different machine error family, correct/incorrect line position, decisive lead, and measurement boundary.

**Accessibility specifics:** Report lines are a navigable list linked to structured lead segments. ROI proof has a lead/region selector. Screen reader announces the challenged sentence before its evidence.

**Cross-mode handoff:** “Train · machine-audit errors” / “Clinical cases will always show the complete report, never a cherry-picked sentence alone.”

## M10-S4 — Compare a prior, then update the synthesis

**Source refs:** `ARCH-M10`; `V2-INTEGRATION`; `CLIN-DISPLAY`; `CLIN-GRADING`; M9-S7 in this artifact; `INV-R-CHRONIC`.  
**Eyebrow/title:** “M10 · 5 of 12” / “Old, new, or cannot determine”  
**Goal line:** “Carry comparison validity into a complete updated read.”

**Exact lesson copy:**

> “A prior does not replace today’s full interpretation. Read the current ECG, validate comparability, align matched leads, and state what is new, unchanged, resolved, or indeterminate. Then update the synthesis: ‘current finding + comparison + significance/next data.’ If the pair is invalid, preserve the current finding and say that newness cannot be determined.”

**Case contract:** Three comparable full 12-lead pairs: unchanged chronic finding, genuine nonacute interval/morphology change, and invalid comparison. No acute temporal language unless source provenance supports it. Each includes comparison-validity truth and accepted change/anchor ROIs.

**Layout delta:** Uses the M9 synchronized comparison viewer plus the complete framework rail. Current ECG is interpreted before the prior tab unlocks.

**Required interaction:** Learner completes current sweep, validates pair, marks changed and unchanged anchors, chooses new/unchanged/cannot determine, then edits the one-line synthesis.

**Tutor script:**

- Opening: “Read today first. The prior should modify—not generate—the interpretation.”
- Socratic: “Which part of your current synthesis changes after this valid comparison?”
- Hint 1: “Check gain, lead mapping, and one unchanged anchor before declaring change.”
- Hint 2: “An invalid prior limits newness, not the current ECG description.”
- Tangent return: “Back to the comparison checklist; your current full read remains saved.”

**State changes and deterministic gate:** Prior locks until current critical fields pass. Comparison tools follow M9-S7. Updated synthesis must retain current finding and valid comparison status.

**Exact feedback branches:**

- Correct independent: “Updated accurately: ‘[current finding], [new/unchanged/indeterminate] compared with [prior], [limit/next data].’”
- Correct assisted: “The comparison and updated synthesis are correct after help.”
- Partial: “Your current read is complete. Add one unchanged anchor and the validity decision before updating newness.”
- Wrong: “The apparent change follows [comparison flaw]. Keep today’s finding and change newness to ‘cannot determine.’”
- Unsafe/unsupported: “Do not turn a chronic comparison into acute timing, symptom causation, or a treatment decision.”
- Not assessable—correct: “Correct. Newness is not assessable because [reason]; the current [finding] is still assessable.”
- Not assessable—incorrect: “The pair is comparable and the change ROI is available. Align and mark it.”

**Equivalent retry:** Different chronic finding, change domain, comparison flaw, and decisive leads.

**Accessibility specifics:** Matched-lead table is equivalent to overlays. Updated synthesis has a change-tracked text alternative showing exactly what the prior modified.

**Cross-mode handoff:** “Clinical · old-or-new” / “Rapid · prior appears only when comparison is construct-valid.”

## M10-S5 — Palpitations and tachycardia: tracing first, perfusion second, subtype third

**Source refs:** `ARCH-M10`; `ARCH-M6`; `V2-INTEGRATION`; `INV-R-TRANSIENT`; `INV-R-AUTHCTX`; `INV-R-CLINREV`; `CLIN-MODES`; `CLIN-GRADING`.  
**Eyebrow/title:** “M10 · 6 of 12” / “Palpitations: keep the clocks separate”  
**Goal line:** “Interpret rate/rhythm/width, then integrate the provided stability context.”

**Exact lesson copy:**

> “For palpitations or tachycardia, the ECG supplies rate, regularity, QRS width, atrial activity, and AV relationship. Bedside data supply perfusion and symptom context. First classify the tracing; then reveal the clinical state; then choose a reviewed priority/action category. Do not infer stability from the ECG or force an exact SVT mechanism when the surface evidence supports only a broader rhythm.”

**Case contract:** Three eligible rhythm cases: regular narrow tachycardia with intentionally limited mechanism, AF/flutter-family case, and wide-complex tachycardia only with reliable rhythm evidence or labeled simulation. Authored context contains vitals/perfusion. Any action tokens require approved policy; transient onset/termination claims require rhythm-stream evidence.

**Layout delta:** Full 12-lead plus pinned long rhythm strip; context drawer stays locked. A five-step rhythm rail shows “Rate → Regularity → Width → Atrial activity → AV relationship.” Mobile opens the strip first but retains “Show full 12-lead.”

**Required interaction:** Learner marches R–R, measures width, marks atrial activity/P–QRS relationship, submits rhythm at strongest specificity, then reveals perfusion context and selects reviewed priority/action or needed-data/escalation category.

**Tutor script:**

- Opening: “I’ll stay quiet until your ECG-only rhythm is committed.”
- Socratic on request: “Which rung—regularity, width, atrial activity, or AV relationship—still separates the candidates?”
- Hint 1: “Do not let the rate substitute for atrial activity.”
- Hint 2: “Stability comes from the provided bedside state, not QRS appearance.”
- Tangent return: “Back to [case], beat [n], with your rhythm marks and hidden context intact.”

**State changes and deterministic gate:** Context reveals only after rhythm rail passes. ECG recognition and clinical calibration/action score separately. If action policy is unavailable, the action selector is replaced by “Escalate through local reviewed pathway / obtain bedside assessment,” and no action mastery is written.

**Exact feedback branches:**

- Correct independent: “Supported. The tracing shows [rhythm evidence/conclusion]. The provided context shows [perfusion state], so [reviewed priority/needed-data category] is proportionate.”
- Correct limited: “Correct. The surface ECG supports [broad rhythm], while [exact mechanism] is not assessable.”
- Correct assisted: “The rhythm/context chain is correct after help; it records as assisted.”
- Partial: “Your rate and width are correct. Mark atrial activity and AV relationship before revealing stability.”
- Wrong: “The rhythm conclusion conflicts with [regularity/P–QRS/width evidence]. Reopen the rhythm rail.”
- Unsafe/unsupported: “Do not infer stability, administer a drug, or choose a device setting from this tracing. Use only the supplied context and reviewed category.”
- Not assessable—correct: “Correct. [Exact mechanism/stability before reveal/action] is not assessable; [supported rhythm evidence] is.”
- Not assessable—incorrect: “The packet includes [required rhythm/context evidence]. Complete it before limiting the intended claim.”

**Equivalent retry:** Different rate, rhythm family, QRS width, atrial visibility, and opposite perfusion branch.

**Accessibility specifics:** Rhythm marks have a beat-table equivalent; context is text; no countdown in Guided. A future timed handoff begins only after all pixels, controls, and stem fields render.

**Cross-mode handoff:** “Train · [weak rhythm rung]” / “Rapid · tachy quick look” / “Clinical · palpitations/tachycardia” only when reviewed.

## M10-S6 — Syncope and bradycardia: do not make a resting ECG reenact the event

**Source refs:** `ARCH-M10`; `V2-INTEGRATION`; M4 in `docs/storyboards/VERBATIM_M04_M06.md:595-1071`; `INV-R-TRANSIENT`; `INV-R-AUTHCTX`; `INV-R-CLINREV`; `CLIN-GROUNDING`; `CLIN-GRADING`.  
**Eyebrow/title:** “M10 · 7 of 12” / “Syncope: rhythm evidence, event evidence, perfusion”  
**Goal line:** “Interpret AV conduction and identify what the resting tracing cannot establish.”

**Exact lesson copy:**

> “A resting ECG can show today’s rate, rhythm, AV relationship, conduction pattern, and potential clues. It may not capture the rhythm during a syncopal event. Separate three questions: what does this ECG show, does the provided event evidence link a rhythm to symptoms, and what is the current perfusion state? Request monitoring or event data when the causal link is absent; do not make a low-acuity incidental finding ‘cause’ syncope without supporting evidence.”

**Evidence lanes:** “Resting 12-lead” · “Event/rhythm-stream evidence” · “Current perfusion/context” · “Medication/reversible-cause context” · “Reviewed priority/action.”

**Case contract:** Three cases: eligible AV-conduction/brady pattern with no event capture, complete/high-grade pattern only with strong evidence, and a benign/incidental conduction finding paired with authored syncope context. A rhythm-stream excerpt is real/validated or explicitly a teaching simulation; it never upgrades resting-ECG mastery. Action scoring requires reviewed content and safe complete-block handling.

**Layout delta:** Full 12-lead with long II plus four evidence lanes. Event/rhythm-stream lane displays “Not provided” until a valid source exists. Mobile orders ECG → event evidence → perfusion → medication/context.

**Required interaction:** Learner marches P and QRS, measures conducted PR/QRS, states the strongest rhythm/conduction conclusion, assigns each context fact to its source lane, chooses the most informative missing datum, then selects reviewed priority/action or supervision/local-pathway escalation when enabled.

**Tutor script:**

- Opening: “Interpret the resting ECG without claiming it captured the event.”
- Socratic: “What evidence would connect this conduction finding to the time of syncope?”
- Hint 1: “March atrial and ventricular events separately before naming the block.”
- Hint 2: “The ECG cannot supply blood pressure, mental status, or an unrecorded transient pause.”
- Tangent return: “Back to [case]: finish the P–QRS relationship before opening the event-evidence lane.”

**State changes and deterministic gate:** Event/context lanes lock until conduction evidence passes. Causality claim requires actual event linkage plus policy. Incidental finding cannot be keyed as cause. High-grade action item disabled unless safety tokens and review are present.

**Exact feedback branches:**

- Correct independent: “Supported. The resting ECG shows [conduction pattern]. It [does/does not] capture the event, current perfusion is [provided state], and [missing datum/reviewed category] is the proportionate next step.”
- Correct limited: “Correct. The ECG finding is real, but symptom causality is not established without event-linked evidence.”
- Correct assisted: “The conduction/context chain is correct after help and records as assisted.”
- Partial: “You identified bradycardia. Complete atrial rate, ventricular rate, P–QRS relationship, and conducted PR behavior before using the context.”
- Wrong: “The case does not contain an event rhythm. A resting [finding] cannot be assumed to explain the syncope.”
- Unsafe/unsupported: “Do not delay escalation for provided compromise, and do not enter a drug dose or pacing/device setting. Use the reviewed action category or local-pathway escalation.”
- Not assessable—correct: “Correct. Event rhythm/causality is not assessable because no valid rhythm stream is provided. The resting conduction pattern is assessable.”
- Not assessable—incorrect: “The resting ECG provides readable P–QRS evidence. Complete that interpretation even though event causality remains unavailable.”

**Equivalent retry:** Different AV relationship, escape rate, event-data availability, incidental mimic, and perfusion branch.

**Accessibility specifics:** P/QRS marching has a structured beat table. Source lanes are labeled text. Any staged vital change is announced; no timer.

**Cross-mode handoff:** “Train · AV relationship” / “Clinical · syncope/bradycardia” only for reviewed packets / “Request monitoring” as a next-data skill, not telemetry mastery.

## M10-S7 — QT-active medication: measurement and action rationale are separate

**Source refs:** `ARCH-M10`; `V2-INTEGRATION`; M8-S3–M8-S7 in this artifact; `SPEC-QT-ELIGIBILITY`; `INV-R-CLINREV`; `CLIN-GROUNDING`; `CLIN-GRADING`.  
**Eyebrow/title:** “M10 · 8 of 12” / “Medication review with a full ECG”  
**Goal line:** “Integrate manual QT/QTc, QRS context, medication reconciliation, labs, and prior.”

**Exact lesson copy:**

> “The medication question does not erase the rest of the ECG. Complete the sweep, manually verify QT and rate correction, identify wide-QRS confounding, then reconcile medicines, dose/timing, interactions, clearance, electrolytes, symptoms, and prior ECG. Measurement accuracy and action rationale receive separate scores. A correct action category cannot rescue a false QT measurement.”

**Case contract:** Two eligible real QT ECGs with separately authored medication contexts: one narrow QRS with missing laboratory/prior data and one BBB/paced confound. Drug-risk lookup requires current approved/licensed source. Exact medication action requires approved policy; otherwise only verification/data/supervision steps score.

**Layout delta:** Full 12-lead and framework rail above a medication timeline. Machine QTc and medicine cards remain masked until manual QT/QTc/QRS submission. Mobile keeps the manual measurement notebook pinned across reveals.

**Required interaction:** Learner completes full ECG sweep, manually measures QT on two beats, calculates configured QTc, measures QRS/JT context, reveals medication data, orders missing information, compares valid prior if present, and submits one measurement sentence plus one separately reviewed rationale sentence.

**Tutor script:**

- Opening: “The medicine card stays closed until your manual interval is committed.”
- Socratic: “Would your action rationale change if the QTc discrepancy came from rate formula or QRS widening?”
- Hint 1: “Report QT, rate/RR, formula, lead, and uncertainty together.”
- Hint 2: “Check renal/hepatic context, interacting drugs, electrolytes, symptoms, and prior before a follow-up category.”
- Tangent return: “Back to [measurement/workflow step]: the medication reveal remains paused.”

**State changes and deterministic gate:** Follows M8 measurement gates. Measurement axis locks before context. Action/rationale axis exists only with approved policy and component parsing; unsafe order cannot receive partial credit from a correct QT number.

**Exact feedback branches:**

- Correct independent: “Measurement supported: [QT/QTc/rate/formula/QRS context]. Rationale supported: [data reviewed, missing data, reviewed category]. The two axes are recorded separately.”
- Correct limited: “Correct. Measurement is supported, but action is not assessable until [missing datum/policy].”
- Correct assisted: “The measurement/workflow is correct after help and records as assisted.”
- Partial: “Your QTc is correct. Add [QRS confound/prior/electrolytes/interaction] before the rationale can complete.”
- Wrong: “The QT boundary/formula is incorrect. Re-measure before interpreting the medication context.”
- Unsafe/unsupported: “A medication stop/start/dose order is not authorized by this packet. Use the reviewed category or state the missing supervision/policy.”
- Not assessable—correct: “Correct. The action rationale is not assessable until [missing datum/policy] is available. Your supported QT/QTc and QRS measurements still count.”
- Not assessable—incorrect: “Manual QT/QTc and QRS context are available. Complete them even if the action layer is unavailable.”

**Equivalent retry:** Different rate, formula divergence, QRS morphology, missing context, and prior validity.

**Accessibility specifics:** Medication reconciliation is a text timeline; equations have unit-aware fields; comparison has table alternative. Results announce measurement axis before action-rationale axis.

**Cross-mode handoff:** “Train · [QT subskill]” / “Clinical · medication safety” only if reviewed / “Return to M8-S5” for wide-QRS error.

## M10-S8 — Chest pain: complete read, evidence-limited urgency, closed-loop communication

**Source refs:** `ARCH-M10`; `V2-INTEGRATION`; M9-S0–M9-S9 in this artifact; `INV-R-CHRONIC`; `INV-R-STAFF`; `INV-R-AUTHCTX`; `INV-R-CLINREV`; `CLIN-GRADING`.  
**Eyebrow/title:** “M10 · 9 of 12” / “Chest pain without invented acuity”  
**Goal line:** “Integrate trace, territory, mimic, comparison, context, and reviewed escalation.”

**Exact lesson copy:**

> “A chest-pain case requires a complete ECG read plus a focused high-priority statement. Commit the tracing before the symptom timeline or biomarkers appear. Then integrate timing, prior/serial validity, symptoms, and other data without allowing the story to manufacture an acute ECG. Communicate the supported finding, concern, uncertainty, and the reviewed escalation or information need in closed-loop language.”

**Closed-loop template:** “This ECG shows [finding/distribution]. Compared with [valid prior/none], [change statement]. In the provided context, I am concerned about [reviewed concern category] because [evidence]. I would [reviewed escalation/obtain data] and confirm receipt.”

**Case contract:** Established/chronic Q-wave or ST–T real case, mimic case, and nondiagnostic/normal case with authored chest-pain context. Acute/serial case appears only under M9-S9 data gate. Troponin and symptoms are authored context and do not alter ECG truth. Action content is review-gated.

**Layout delta:** Full 12-lead and evidence chain; symptom timeline and labs are masked. A “Communicate now” layer opens after integration. Mobile uses a persistent evidence receipt above each reveal.

**Required interaction:** Learner completes full sweep, marks territory/reciprocal/mimic evidence, validates prior, commits ECG-only synthesis, reveals context, orders one needed datum and reviewed escalation category, and assembles the closed-loop statement.

**Tutor script:**

- Opening: “The symptom story cannot rescue a weak tracing description. Commit the ECG first.”
- Socratic: “Which sentence is supported by the trace, and which depends on the authored clinical layer?”
- Hint 1: “Name the lead distribution and mimic before urgency.”
- Hint 2: “If the tracing is nondiagnostic, say so without treating that as clinical exclusion.”
- Tangent return: “Back to [case]: your ECG-only synthesis remains unchanged while the context layer is paused.”

**State changes and deterministic gate:** Context locks until ECG evidence passes. Acute wording requires provenance. Closed-loop statement must contain finding, comparison/limit, reviewed concern/action or needed data, and receiver confirmation token.

**Exact feedback branches:**

- Correct independent: “Supported and communicable. You separated [ECG evidence] from [authored context], used [valid comparison/limit], and selected [reviewed escalation/data need] without inventing acuity.”
- Correct chronic limit: “Correct. This ECG supports [established/chronic pattern]; the chest-pain context requires clinical evaluation but does not create acute-pattern mastery.”
- Correct assisted: “The interpretation and communication chain is correct after help.”
- Partial: “Your high-priority concern is clear. Add the lead-level finding and comparison/uncertainty so the receiver can verify it.”
- Wrong: “Your acute/new statement lacks [acute source/valid serial change]. Replace it with the supported finding and context-based concern.”
- Unsafe/unsupported: “Do not discharge, activate, medicate, or name a culprit vessel outside the reviewed packet. Use the enabled escalation category or state that policy is unavailable.”
- Not assessable—correct: “Correct. [Acute timing/action] is not assessable; [current ECG description and need for evaluation] are.”
- Not assessable—incorrect: “The trace supports [finding/distribution]. Complete that evidence before limiting clinical conclusions.”

**Equivalent retry:** Different chronic/mimic/nondiagnostic ECG, symptom timeline, prior validity, and policy availability.

**Accessibility specifics:** Timeline and labs are text; the handoff can be typed or spoken; speech is assessed for claim content, not accent, prosody, or filler words. No timer in Guided.

**Cross-mode handoff:** “Rapid · chest-pain whole read” / “Clinical · chest pain” only if reviewed / “Acute lane locked” when provenance fails.

## M10-S9 — Wide QRS and device context: identify before interpreting recovery

**Source refs:** `ARCH-M10`; `V2-INTEGRATION`; M5 in `docs/storyboards/VERBATIM_M04_M06.md:10-487`; M6 wide-tachy prerequisite; M8-S1/M8-S5; `INV-R-CLINREV`.  
**Eyebrow/title:** “M10 · 10 of 12” / “Device and conduction case”  
**Goal line:** “Distinguish BBB, pacing, pre-excitation, and tachycardia context before judging ST–T or device function.”

**Exact lesson copy:**

> “A wide QRS changes the rest of the read. Measure duration, compare V1 with lateral leads, inspect the initial QRS and baseline for pre-excitation or pacing spikes, determine rhythm and AV relation, then interpret ST–T as primary or secondary. Spike timing, capture, and sensing are separate questions. A surface ECG can support a device/conduction observation; device reprogramming and troubleshooting actions require specialist-reviewed cases.”

**Case contract:** Four packets: eligible RBBB/LBBB, paced simulation/eligible paced ECG, pre-excitation model/eligible case, and wide-complex tachy only with rhythm evidence. Device malfunction examples remain authored simulations unless validated data and review exist. Required V1/V2, I/V5/V6, long strip, QRS/QT context.

**Layout delta:** Full 12-lead with activation rail and machine-report panel. Spike-to-event timeline appears only for pacing cases. Mobile begins with paired V1/V6 magnifiers but retains full tracing.

**Required interaction:** Learner measures QRS, marks paired morphology/initial delta/spikes, links spikes to P/QRS and capture when applicable, assesses rhythm, classifies secondary ST–T relationship, critiques one machine statement, and states an evidence-limited synthesis.

**Tutor script:**

- Opening: “Width first, pathway second, recovery third.”
- Socratic: “Which feature distinguishes a terminal bundle delay from an initial pre-excitation change or a pacing event?”
- Hint 1: “Compare a right-precordial lead with a lateral lead.”
- Hint 2: “For pacing, ask spike timing, chamber, capture, and sensing separately.”
- Tangent return: “Back to [case]: complete the activation pathway before interpreting ST–T.”

**State changes and deterministic gate:** Follows M5 source contracts. Recovery cannot unlock until activation classification. Device action layer disabled without review. Wide-tachy event evidence required.

**Exact feedback branches:**

- Correct independent: “Supported. [Width/morphology/spike evidence] identifies [pattern], [rhythm evidence] is [result], and [ST–T relationship] is interpreted in the correct activation context.”
- Correct limited: “Correct. The tracing supports [device/conduction observation], while [capture/sensing subtype/device action] is not assessable.”
- Correct assisted: “The activation and recovery synthesis is correct after help.”
- Partial: “QRS width is correct. Add paired morphology and initial-QRS/spike evidence before naming the pathway.”
- Wrong: “Your label conflicts with [terminal/initial/spike evidence]. Recompare V1 with [lateral lead].”
- Unsafe/unsupported: “Do not recommend a device setting, reprogramming, or drug action from this packet. State the observed pattern and reviewed consultation need only.”
- Not assessable—correct: “Correct. [Device subtype/action] is not assessable because [missing timing/review data]. [Observed conduction/pacing evidence] remains assessable.”
- Not assessable—incorrect: “The required paired leads and timing markers are available. Complete the activation evidence first.”

**Equivalent retry:** Different wide-QRS family, QRS duration, clearest paired leads, spike visibility, rhythm, and machine error.

**Accessibility specifics:** Spike/event relations have a structured timing table; morphology has named lead-region choices; screen reader presents activation before recovery.

**Cross-mode handoff:** “Train · wide-QRS contrasts” / “Rapid · mixed wide-QRS” / “Clinical · device case” only with reviewed packet.

## M10-S10 — Resuscitation boundary: monitor rhythm and 12-lead ECG are related, not interchangeable

**Source refs:** `ARCH-M10`; `V2-INTEGRATION`; `INV-R-TRANSIENT`; `INV-R-CHRONIC`; `INV-R-STAFF`; `INV-R-CLINREV`; `CLIN-MODES`; `CLIN-GROUNDING`.  
**Eyebrow/title:** “M10 · 11 of 12” / “Know which instrument answers which question”  
**Goal line:** “Separate rhythm-stream recognition, pulse/perfusion assessment, and 12-lead interpretation.”

**Exact lesson copy:**

> “A monitor or defibrillator rhythm stream supports continuous rhythm recognition; a 12-lead supports spatial morphology, axis, intervals, and territory. Resuscitation decisions also require pulse, perfusion, timing, and a current reviewed algorithm. A resting PTB-XL ECG cannot be relabeled as a code rhythm. Until a validated rhythm-stream corpus and reviewed ACLS content are installed, this module teaches the boundary and source selection—not arrest-rhythm or treatment mastery.”

**Source cards:**

- “Resting 12-lead” — “Spatial morphology, intervals, axis, territories; brief time sample.”
- “Rhythm stream/telemetry” — “Evolution, onset/termination, pauses, runs, alarms; requires valid stream.”
- “Bedside assessment” — “Pulse, perfusion, mental status, symptoms, airway/breathing context.”
- “Reviewed algorithm” — “Time-sensitive action sequence; clinician owner and version required.”
- Locked lane: “ACLS/arrest scoring locked — verified rhythm stream and reviewed algorithm required.”

**Case contract:** Source-selection teaching model plus one resting 12-lead and one deterministic rhythm-stream demo clearly labeled. No VT/VF/torsades/arrest clinical mastery is recorded. If a future validated corpus exists, it must use a separate case family, mastery axis, algorithm version, and clinical review.

**Layout delta:** Four source lanes and a split view of resting ECG versus time stream. The locked ACLS tile remains visible. Mobile displays sources before the demonstration so a waveform cannot be mistaken for a patient case.

**Required interaction:** Learner assigns ten questions—such as “What is the axis?”, “Did a pause occur during symptoms?”, “Is there a pulse?”, and “Which action sequence applies?”—to the source that can answer them; then labels each demo claim “supported,” “requires another source,” or “lane locked.”

**Tutor script:**

- Opening: “This scene tests source selection, not memorized resuscitation actions.”
- Socratic: “What information exists over time, and what exists only at the bedside?”
- Hint 1: “A 12-lead is spatially rich but temporally brief.”
- Hint 2: “A waveform never supplies a pulse.”
- Tangent return: “Back to question [n]: assign the source before interpreting the demo.”

**State changes and deterministic gate:** All questions have fixed source keys. The locked lane cannot be bypassed by a model output or synthetic tracing. Completion records epistemic/source-selection evidence only.

**Exact feedback branches:**

- Correct independent: “Correct. You matched each question to the source that can answer it and kept arrest-rhythm/action mastery locked.”
- Correct assisted: “The source map is correct after help.”
- Partial: “You assigned the rhythm-stream questions correctly. Move pulse/perfusion and action-sequence questions to bedside assessment and reviewed algorithm.”
- Wrong: “A resting 12-lead cannot show whether a transient event occurred later or whether a pulse is present.”
- Unsafe/unsupported: “Do not choose a shock, medication, energy, or timing sequence here. The required corpus and reviewed algorithm are not installed.”
- Not assessable—correct: “Correct. Arrest rhythm/action mastery is not assessable in the current platform. Source selection remains assessable.”
- Not assessable—incorrect: “The scene does assess which source answers each question. Complete the source map.”

**Equivalent retry:** Different question set/order, different resting morphology, and different rhythm-stream demo seed. The ACLS lane remains locked until real gates pass.

**Accessibility specifics:** Source assignment has a table with question and source dropdown. The time stream has a static event list. Lock reason is persistent text, not disabled-control opacity alone.

**Cross-mode handoff:** Locked card: “Clinical · Resuscitation/ACLS — unavailable until validated.” Available card: “Train · choose the right ECG evidence source.”

## M10-S11 — Integrated capstone: complete, prioritize, prove, communicate

**Source refs:** `SPEC-CHAMBER-ELIGIBILITY`; `SPEC-QT-ELIGIBILITY`; `SPEC-ISCHEMIA-ELIGIBILITY`; `SPEC-FRAMEWORKS`; `SPEC-VIEWER`; `ARCH-M7`; `ARCH-M8`; `ARCH-M9`; `ARCH-M10`; `SPEC-RAPID`; `SPEC-TRAIN`; `SPEC-MASTERY`; `SPEC-MISCONCEPTIONS`; `ARCH-MODE-HANDOFF`; `CLIN-MODES`; `CLIN-GRADING`.  
**Eyebrow/title:** “M10 · 12 of 12” / “Mixed clerkship round”  
**Goal line:** “Interpret unannounced cases, communicate one evidence-linked line, and receive exact remediation.”

**Exact lesson copy:**

> “For each case: preflight → complete your chosen framework → mark decisive evidence → prioritize → state confidence and limits → communicate one concise line. Luna stays silent until submission. A hint pauses the case and converts that attempt to assisted. Guided mode is untimed; optional pacing rehearsal never changes mastery. Clinical timing begins only in the destination mode after the complete interface has rendered.”

**Tutor opening:** “I’ll remain collapsed. If you ask for help, your exact case state freezes and the assistance level is recorded.”  
**Socratic on request:** “Which framework domain or evidence source is still missing?”  
**Hint 1:** “Return to the first unsupported field, not the final label.”  
**Hint 2:** “Click the waveform evidence for the finding you plan to lead with.”  
**Tangent return:** “Back to case [n], at the same lead, zoom, comparison state, and draft.”

**Case contract:** Six-case adaptive-but-interleaved set without replacement:

1. normal/variant or subtle abnormal;
2. rhythm/AV-conduction case;
3. wide-QRS/chamber case;
4. ST–T/QT case;
5. established infarction/mimic or evidence-limited localization case;
6. one authored clinic/ward/ED-non-arrest context with action layer reviewed or explicitly unavailable.

Every case inherits its source-scene eligibility and requires target, mimic, and normal exposure across the session. No unsupported acute, telemetry, or resuscitation case may substitute for a missing family. Case selection prioritizes low mastery, repeated/high-confidence errors, staleness, and underexposure while preventing same-record repetition.

**Layout delta:** Full viewer, learner-selected framework rail, case counter, confidence control, and handoff recorder. Luna is collapsed. Desktop/laptop keeps the evidence receipt beside the trace; mobile places it beneath the full-board mini-map. Optional “Practice a 20-second handoff” appears only after untimed submission and is labeled “Pacing rehearsal — not scored.”

**Required interaction:** Per case learner completes critical framework fields, places at least two decisive trace marks, verifies machine/prior when present, submits full structured interpretation, confidence, one-line handoff, and context/action or needed-data response when available. No label list appears before trace commitment.

**Deterministic scoring and gate:** Separate axes:

- waveform recognition/localization 25%;
- measurement 15%;
- mechanism/mimic discrimination 15%;
- complete synthesis 20%;
- confidence calibration 10%;
- communication claim/evidence linkage 10%;
- clinical action safety 5% only when reviewed; otherwise that 5% becomes epistemic-source selection.

Module pass requires ≥82% overall, ≥75% on synthesis, no critical rhythm/conduction or ischemia-mimic reversal, correct not-assessable behavior on the limited case, no unsupported acute/transient claim, and completion of any critical-miss equivalent case. Assisted cases can complete the module but remain scheduled for independent recheck. Clinical action mastery is never inferred when the action layer is unavailable.

**Exact feedback branches:**

- Fully correct independent: “Supported. Your full read is [normalized interpretation]. You led with [priority finding], proved it in [lead/region], stated [comparison/limit], and calibrated confidence at [level].”
- Correct limited: “Expertly limited. You completed the readable domains, stated [supported finding], and named [missing source/data] instead of guessing.”
- Correct assisted: “Your final interpretation is supported after assistance. The case completes for learning, and an independent equivalent is scheduled.”
- Partial: “You have [credited domains]. The handoff/conclusion remains locked until [missing framework field or waveform proof] is complete.”
- Wrong with useful marks: “Your marks support [evidence], but the conclusion says [conflicting claim]. Rebuild from [specific domain].”
- Critical miss: “This missed evidence changes the interpretation: [case-specific discriminator]. Complete an equivalent case before exit.”
- Unsafe/unsupported: “Your response adds an unsupported acute, transient, causal, culprit-vessel, medication, device, discharge, or resuscitation claim. Return to the allowed evidence and reviewed action layer.”
- Not assessable—correct: “Correctly limited. [Supported fields] are assessable; [claim] is not because [manifest reason].”
- Not assessable—incorrect: “The packet provides [required lead/measurement/context]. Complete it before limiting the interpretation.”
- Data-contract failure: “This case cannot support the promised task. It has been removed from your session and will not affect mastery.”

**Equivalent retry:** Same failed objective and difficulty vector; different source record/context, different decisive leads/ROI, ±15% rate where relevant, different nuisance morphology, no repeat record. The original explanation remains hidden until retry submission.

**Adaptive remediation receipt:** After every case, show exactly one of:

- “Independent evidence saved.”
- “Assisted evidence saved · independent recheck scheduled.”
- “Repair assigned · [module-scene title].”
- “Equivalent case required before exit.”
- “Clinical action not scored · reviewed content unavailable.”

The repair button deep-links the smallest scene, not the whole module: M7-S1 atrial morphology; M7-S2 voltage criterion; M7-S3 RVH/RBBB; M7-S4 progression; M7-S6 secondary ST–T; M8-S0 boundaries; M8-S3 QT end; M8-S4 formula; M8-S5 wide-QRS confound; M8-S8 nonischemic comparison; M9-S1 geography/reciprocal; M9-S4 posterior; M9-S6 Q waves; M9-S7 comparison validity; M9-S8 mimic discriminator; or the appropriate M1–M6 source scene.

**Accessibility specifics:** Full structured form and mark alternatives remain available. Handoff may be typed or spoken; scoring ignores accent, dialect, grammar style, and typing speed and verifies only required claims against packet evidence. Optional pacing rehearsal respects the learner’s timing accommodation and carries no speed bonus for “not assessable.” Results list each mastery axis separately.

**Completion copy:**

> “Guided curriculum complete. You can now perform a complete ECG sweep, prove high-priority findings on the trace, audit machine output, compare valid priors, state uncertainty, and communicate a concise context-aware interpretation. Your next cases will be selected from what you have not yet shown independently—not from what you have merely seen.”

**Cross-mode handoff cards:**

- “Train · Build [weak objective]” — “Focused repetition with normal, target, and close mimics until the subskill is stable.”
- “Rapid · Mixed ECG interpretation” — “Tutor silent before submission; whole-read recognition, confidence, and concise feedback.”
- “Clinical · [eligible case family]” — “Situation-scaled timing and reviewed action scoring; unavailable families remain visibly locked.”
- “Review plan · [date/interval]” — “Independent equivalent cases are interleaved after spacing; assisted completion does not erase the need.”

---

# Cross-module connection and retrieval map

Connections must be visible in three places: the scene’s opening retrieval chip, the feedback evidence receipt, and the completion handoff. A connection is not merely a hyperlink; it reuses an earlier representation or action and names how the new module changes it.

| Earlier learning | Reused representation/action | New use in M7–M10 | Exact learner-facing connection copy |
|---|---|---|---|
| M1 calibration, baseline, waves, intervals, full sweep | Grid, calibration pulse, QRS/ST/T/QT boundaries | Valid chamber voltage, QT/ST measurement, integrated preflight | “Same ruler, higher-stakes claim: verify calibration before interpreting amplitude or interval.” |
| M2 vectors, lead map, axis, contiguous/opposing leads | Direction arrow, hexaxial map, V1–V6 scrub | Chamber forces, R progression, territory/reciprocal localization | “The lead still records a projection. Now use several projections to build a chamber or geographic pattern.” |
| M3 atrial/ventricular clocks | Beat markers, march lines, P search | Atrial morphology limits and integrated rhythm cases | “First identify the atrial event; only then ask whether its shape carries chamber evidence.” |
| M4 AV relationship | P–QRS links, serial PR row, escape evidence | Syncope/bradycardia transfer | “The conduction label comes from the clocks; urgency comes from the supplied perfusion and event context.” |
| M5 QRS width, terminal force, pacing/pre-excitation, secondary recovery | Paired V1/lateral magnifier, initial/terminal QRS marks | RVH mimics, strain, QT confounding, ischemia mimics, device case | “Activation is the context for voltage and recovery. Read the QRS before ST–T.” |
| M6 tachy matrix and stability boundary | Regularity×width matrix, atrial/AV evidence | Palpitations/tachycardia case and QT/torsades boundary | “Classify the tracing first; reveal perfusion second; do not infer stability from rate or width.” |
| M7 chamber/progression evidence bundle | Voltage/P-wave calipers, R/S trace, primary/secondary link | LVH/strain mimic, Q-wave/progression interpretation, integrated wide-QRS/chamber case | “Poor progression and strain modify the differential; neither closes an infarction diagnosis alone.” |
| M8 baseline/J/ST/T/QT workflow | Boundary marks, morphology sentence, QT notebook | Ischemia description, drug/electrolyte comparison, clinical medication case | “The ischemia module begins from your description; it does not replace it with a label.” |
| M9 geography, mimic, comparison validity | Lead painting, reciprocal links, target–mimic triads, current/prior alignment | Chest-pain and capstone synthesis | “Lead evidence and provenance determine how urgent language may become.” |

## Connection behavior

- Opening retrieval chip control: “Show the earlier model.” It opens a nonmodal 90-second recap layer; closing returns focus to the triggering chip and preserves the scene.
- Failed prerequisite control: “Repair [skill] now.” It deep-links the smallest prior scene, stores a return waypoint, and shows on completion: “Repair complete. Return to [current scene].”
- Prior topic already independent: “You’ve shown this independently. Use the compact reminder.”
- Prior topic only assisted: “You completed this with help. Try the retrieval item before continuing.”
- Learner chooses to skip repair: “Continue with support.” The current scene remains available, but independent mastery is capped and the missing prerequisite is scheduled.
- No connection may auto-navigate, erase current marks, or mark the earlier skill mastered from passive review.

# Scene traceability matrix

| Scene | Primary objective | Required independent evidence | Smallest remediation | Cross-mode publication |
|---|---|---|---|---|
| M7-S0 | voltage causality | four one-variable predictions + amplitude measures | M2 vector projection | Train: voltage causes |
| M7-S1 | atrial morphology | II duration/contour + V1 component evidence | M1 P boundary | Train: P-wave contrasts |
| M7-S2 | LVH evidence bundle | calibration + criterion measure + corroboration + limit | M7-S0 | Train: LVH/mimics |
| M7-S3 | RVH/mimic discrimination | axis + V1 R/S + precordial/QRS context | M5 RBBB terminal force | Train: RVH versus RBBB |
| M7-S4 | R progression | six-lead R/S trace + transition/placement status | M2 R-wave progression | Train: transition/rotation |
| M7-S5 | poor-progression differential | description + acquisition check + independent cause evidence | M7-S4 or M5 morphology | Train: progression differential |
| M7-S6 | secondary strain | QRS/ST/T direction triplets + unexplained outlier | M5-S9 | Train: primary/secondary recovery |
| M7-S7 | chamber transfer | five cases; ≥82%; correct limited case | exact failed M7 scene | Rapid whole read; eligible chronic Clinical |
| M8-S0 | recovery boundaries | QRS onset/J/baseline/T end + uncertainty | M1-S7 | Train: boundaries |
| M8-S1 | primary vs secondary | QRS context + three direction triplets + outlier | M5-S9 or M7-S6 | Train: recovery relationship |
| M8-S2 | ST/T description | reference + morphology ROI + lead distribution + sentence | M8-S0 | Train: ST/T morphology |
| M8-S3 | QT measurement | two beats + lead/method + T/U handling | M8-S0 | Train: QT boundary |
| M8-S4 | rate correction | QT/RR + Bazett/Fridericia + caveat | M8-S3 | Train: formula calibration |
| M8-S5 | wide-QRS QT | QRS/QT/JT components + confound statement | M5 width then M8-S3 | Train: wide-QRS QT |
| M8-S6 | medication workflow | manual measure + ordered evidence/data chain | M8-S3–S5 | Clinical only if reviewed |
| M8-S7 | electrolyte hypothesis | causal component marks + mimic + confirming datum | M8-S2 or S3 | Train only if reliable bank |
| M8-S8 | nonischemic comparison | ≥5 discriminator rows + evidence-limited rank | M8-S1/S2 or M7-S6 | Train: variants/mimics |
| M8-S9 | recovery transfer | five cases; ≥82%; no critical QT/causal error | exact failed M8 scene | Rapid; reviewed medication Clinical |
| M9-S0 | epistemic claim limits | finding/distribution + correct claim rung | M8-S2 | all modes retain claim ceiling |
| M9-S1 | contiguous/reciprocal | baseline/J + lead-set paint + reciprocal link | M2 lead map or M8-S0 | Train: geography |
| M9-S2 | anterior/lateral localization | lead set + region + mimic check | M9-S1 or M7-S4 | Train: territory |
| M9-S3 | inferior/right-sided question | inferior/reciprocal proof + placement/data decision | M9-S1 | reviewed chest-pain Clinical |
| M9-S4 | posterior pattern | V1–V3 ST/R/T bundle + mimic check + lead request | M5/M7-S3 | Train only if sufficient bank |
| M9-S5 | ST depression/T inversion rank | description + QRS relation + valid context/needed datum | M8-S1/S2/S8 | Train: primary/secondary |
| M9-S6 | Q waves/established infarction | initial-deflection measure + contiguous territory + mimic | M7-S5 or M2 | Train: Q versus S/septal q |
| M9-S7 | comparison validity | validity checks + change/unchanged ROIs + ternary conclusion | M9-S1 + comparison repair | Clinical old/new if valid |
| M9-S8 | mimic discrimination | trace ROI + rule-backed discriminator for triads | source scene for missed mimic | Train: missed mimic; Rapid mix |
| M9-S9 | chest-pain transfer/data gate | full ECG chain + provenance-limited context response | exact failed M9 scene | Clinical only if reviewed/provenanced |
| M10-S0 | framework mapping | all domains mapped + chosen complete sweep | M1 full sweep | preference changes language only |
| M10-S1 | complete normal read | preflight + every framework field | exact M1–M9 domain | Rapid: normal/subtle abnormal |
| M10-S2 | priority synthesis | evidence layers + context rank + concise line | M10-S1/domain scene | Rapid handoff view |
| M10-S3 | machine audit | two verified measures + bad line + trace proof + rewrite | exact source domain | Train: audit errors |
| M10-S4 | integrated prior | current sweep + valid comparison + updated synthesis | M9-S7 | Clinical old/new |
| M10-S5 | palpitations/tachy | rhythm ladder + supplied perfusion + reviewed/needed-data response | M3/M6 | Rapid/Clinical when eligible |
| M10-S6 | syncope/brady | AV evidence + event-source limit + perfusion/context | M4 | Clinical when reviewed |
| M10-S7 | medication/QT | full sweep + QT/QTc/QRS + separate rationale | M8-S3–S6 | Clinical when reviewed |
| M10-S8 | chest pain | full read + geography/mimic/prior + closed-loop line | M9 exact scene | Clinical when reviewed/provenanced |
| M10-S9 | wide QRS/device | activation evidence before recovery/device limit | M5/M8-S1/S5 | Rapid; Clinical when reviewed |
| M10-S10 | resuscitation source boundary | all questions assigned to valid source | source-selection retry | ACLS lane locked until gates pass |
| M10-S11 | capstone transfer | six cases; ≥82%; synthesis ≥75%; no critical miss | smallest exact scene | personalized Train/Rapid/Clinical plan |

# Build-blocking acceptance checklist

## Content and sequence

- [ ] The deployed scene order is M7 chambers/progression → M8 repolarization/QT → M9 ischemia/localization → M10 integration.
- [ ] No chamber diagnosis is graded from one weak criterion; every scoreable criterion card has owner, source, version, reviewer, and population/context.
- [ ] M8 teaches baseline, J point, morphology, and primary/secondary context before M9 asks for ischemia interpretation.
- [ ] M9 localization requires lead-level evidence; poor R progression, a single Q wave, isolated ST change, or a machine label cannot satisfy it.
- [ ] M10 requires a complete framework before priority compression and retains a full evidence view behind every handoff.
- [ ] Every module exit publishes exact Train objective, Rapid whole-read destination, eligible Clinical family, and smallest remedial scene.

## Viewer and interaction

- [ ] Every scene’s required waveform/model action exists in code; no reveal-chain or generic MCQ substitutes for it.
- [ ] Full 12-lead is default wherever axis, territory, chambers, BBB, ST–T, old/new, or machine audit is tested.
- [ ] Calibration, gain, time, lead labels, sampling provenance, zoom/pan/reset, annotations, calipers, coordinates, and evidence drawer are correct.
- [ ] Every ROI click stores lead, panel, time, amplitude, beat, and viewport; mobile requires confirm.
- [ ] Comparison views verify identity, lead mapping, scale, and signal before overlay or temporal grading.
- [ ] Model traces always display “Teaching model — not a patient tracing” and cannot silently write real-pattern mastery.

## Tutor and AI grounding

- [ ] Luna opening, Socratic prompt, two hints, tangent entry, exact return, unsupported-claim response, and management boundary are implemented for every scene.
- [ ] Tangent entry freezes viewport, marks, draft, state, and any destination-mode timer; return restores all values exactly.
- [ ] Generated tutor text is limited to approved knowledge cards, schema validated, claim checked, and capped at 120 words.
- [ ] Luna cannot select cases, create truth, draw an unregistered ROI, change a score, advance a state, or invent a clinical fact.
- [ ] Provider failure falls back to authored scene copy and deterministic hints without blocking completion.

## Grading and adaptivity

- [ ] Every scene implements independent, assisted, partial, wrong, unsafe/unsupported, correct not-assessable, incorrect not-assessable, and data-contract-failure states.
- [ ] A correct label without the required waveform proof cannot complete.
- [ ] Equivalent retries change record/model seed, decisive ROI, and at least two nuisance dimensions while preserving objective/evidence completeness.
- [ ] Recognition, measurement, localization, mechanism, synthesis, clinical action, and confidence remain separate mastery axes.
- [ ] Assistance completes learning but does not create independent mastery; skipping does not create mastery.
- [ ] High-confidence wrong/unsafe work receives the configured larger calibration decrement and exact remedial scene.
- [ ] Adaptive selection prioritizes weak/stale/repeatedly missed/high-confidence-wrong/underexposed objectives while avoiding duplicate records.

## Clinical/data governance

- [ ] PTB-XL/PTB-XL+ is never described as an acute evolving, telemetry, torsades, VT/VF arrest, or resuscitation source.
- [ ] STAFF-III or any acute corpus remains disabled until license, ingest, lead measurements, validation, and reviewer sign-off are recorded; it cannot supply code/VT/VF training without evidence.
- [ ] Authored context is visually and structurally separate from real ECG provenance.
- [ ] “Acute,” “new,” “dynamic,” “evolving,” and symptom-causality claims require their declared temporal/context source.
- [ ] Drug categories use a current approved/licensed lookup; no copied static list is embedded.
- [ ] Action caps, safety actions, numeric thresholds, compound-option parsing, and case policies are unavailable—not guessed—until clinician-reviewed.
- [ ] ACLS/resuscitation scoring stays locked until verified rhythm streams and a current reviewed algorithm are installed.

## Responsive design and accessibility

- [ ] Desktop, laptop, and 360 px mobile pass the shared layout plus every scene delta; ECG ink stays legible and unobscured.
- [ ] Every drag/paint/caliper/vector interaction has keyboard, stepper/select, touch-confirm, and structured screen-reader equivalents.
- [ ] Focus order follows the visual task; tangent/modal close returns focus to the triggering control.
- [ ] Reduced motion replaces—not merely stops—animation with complete numbered static states.
- [ ] Color is redundant, 200% zoom does not overlap content, targets are at least 44×44 px, and no canvas traps focus.
- [ ] Speech handoffs are scored on evidence-linked claims, never accent, dialect, prosody, filler words, or typing speed.
- [ ] Guided scenes are untimed. Destination-mode clocks start only after pixels, controls, and stem have rendered and apply accommodations without lowering skill thresholds.

## Automated validation failures

The scene build must fail when any of the following is true: missing source refs; assessed objective not taught; missing prerequisite/return waypoint; absent full-lead evidence for a full-lead construct; absent accepted ROI/lead set; criterion or action without approved policy; real/model/context provenance conflated; acute/transient language without source; missing independent gate; retry reuses a record/decisive ROI; one of the required feedback states is absent; tangent cannot restore state; or any visual-only interaction lacks an equivalent nonvisual path.

# Final production copy for locked/unavailable states

- Sparse concept: “Needs more reliable cases. This concept remains in the curriculum, but scored practice is unavailable.”
- Missing numeric policy: “Numeric criterion unavailable — the measurement method remains available.”
- Missing clinical review: “Action scoring unavailable — clinician-reviewed policy required.”
- Chronic corpus boundary: “This resting ECG supports established/chronic interpretation only. It cannot award acute or evolving mastery.”
- Missing serial validity: “Old-versus-new cannot be determined from these recordings.”
- Missing rhythm stream: “Transient rhythm recognition unavailable — a verified rhythm stream is required.”
- ACLS lock: “ACLS/arrest scoring locked — verified rhythm stream and reviewed algorithm required.”
- Model boundary: “Teaching model — not a patient tracing. This activity builds mechanism understanding, not clinical-pattern mastery.”
- Tutor outage: “Luna is temporarily unavailable. Your lesson, deterministic hints, and scoring still work.”
- Invalid case: “This case cannot support the promised task. It has been removed from your session and will not affect mastery.”
