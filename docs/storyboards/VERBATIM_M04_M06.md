# Verbatim production storyboard — M4 to M6

**Locked architecture:** 10-module curriculum, Modules 4–6  
**Modules covered here:** M4 AV Conduction and Bradyarrhythmias; M5 Ventricular Activation, Conduction Delay, Pre-excitation, and Pacing; M6 Tachyarrhythmias  
**Artifact status:** production copy and behavior contract; every quoted learner-facing string is literal  
**Safety boundary:** educational use only; deterministic case packets and interaction engines are the source of truth, never the language model

---

## 0. How to read this document

- Text in quotation marks is exact learner-facing copy.
- Bracketed tokens such as `[rate]`, `[PR]`, `[lead]`, and `[scene name]` are deterministic case-packet substitutions. They are never generated from free text.
- An em dash in a scripted sentence is literal. A slash in a control label is literal only when inside quotation marks.
- “Luna” is the tutor surface. A remote model may explain an approved concept, but it may not choose a diagnosis, score an action, create an ROI, invent a measurement, or advance a scene.
- Every scene uses the shared frame below plus its listed layout delta. No scene may be replaced by a generic multiple-choice card. A waveform, ladder, vector, caliper, march-out, or clinical-state action gates completion.

## 1. Source-reference registry

| Ref | Repository or authoritative source |
|---|---|
| `SPEC-11.5` | `ECG_PLATFORM_SPEC.md` §11: PR interval |
| `SPEC-11.6` | §11: axis |
| `SPEC-11.7` | §11: QRS duration and conduction delay |
| `SPEC-11.8` | §11: bundle branch blocks |
| `SPEC-11.11` | §11: ST elevation/depression and T-wave changes |
| `SPEC-11.13` | §11: bradyarrhythmias and AV block |
| `SPEC-11.14` | §11: AF/flutter, SVT, and wide-complex tachycardia |
| `SPEC-7.*` | §7 concept ontology, using the concept id after the dot |
| `SPEC-8.4` | §8.4 case eligibility for PR/AV block |
| `SPEC-8.5` | §8.5 case eligibility for QRS/BBB |
| `SPEC-8.9` | §8.9 case eligibility for AF/flutter |
| `SPEC-12.1` | §12.1 standard clerkship framework |
| `SPEC-16.*` | §16 misconception target named after the dot |
| `ARCH-M4`–`ARCH-M6` | `docs/storyboards/CURRICULUM_ARCHITECTURE_RECOMMENDATION.md` module contract |
| `FOUND-S6` | Foundations PR/QRS boundary and measurement skill |
| `M2-AXIS` | M2 vector, lead, and axis prerequisite |
| `M3-RHYTHM` | M3 atrial/ventricular clocks, PAC/PVC, pauses, and artifact prerequisite |
| `CURATE` | `docs/AUTONOMOUS_CURATION.md` Tier A/B and allowed-claim rules |
| `CLIN-TABLE.*` | `docs/clinical-content-tables-review.md`, concept row after the dot; concept vocabulary only because action/acuity rows await clinician sign-off |
| `AHA25-BRADY` | 2025 AHA Adult Bradycardia With a Pulse Algorithm |
| `AHA25-TACHY` | 2025 AHA Adult Tachyarrhythmia With a Pulse Algorithm |
| `ACC18-CONDUCTION` | 2018 ACC/AHA/HRS Bradycardia and Conduction Delay guideline definitions |
| `ACC23-AF` | 2023 ACC/AHA/ACCP/HRS atrial fibrillation guideline |

## 2. Shared production frame

### 2.1 Exact global chrome

- Product breadcrumb: “Learn / Guided modules”
- Tutor header: “Luna · guided tutor”
- Tutor status when case-grounded: “Grounded to this teaching case”
- Tutor input placeholder: “Ask why, ask for another explanation, or follow a tangent…”
- Tutor controls: “Ask Luna” · “Hint” · “Return to lesson”
- Reference control: “Open reference”
- Scene navigation: “Back” · “Continue”
- Locked footer: “Complete the waveform task to continue.”
- Complete footer: “Checkpoint complete. Continue when you’re ready.”
- Persistence toast: “Progress saved.”
- Real-case badge: “Real teaching ECG”
- Model badge: “Teaching model — not a patient tracing”
- Uncertain-case badge: “Classification intentionally limited”
- Case evidence drawer: “Why this case is eligible”
- Viewer reset: “Reset view”
- Full tracing control: “Show full 12-lead”
- Magnifier dismissal: “Return to full tracing”

### 2.2 Responsive layout inherited by every scene

**Desktop, 1280 px and wider.** A 72 px header sits above a 12-column work area. The 216 px module rail occupies columns 1–2, the learning stage columns 3–9, and the 340–380 px Luna panel columns 10–12. The ECG stage is never narrower than 680 px. The primary interaction sits directly beneath or over the tracing; explanatory copy never covers waveform ink. The footer remains sticky inside the stage, not across the tutor.

**Laptop, 900–1279 px.** The module rail becomes a one-line scene strip below the 60 px header. The stage occupies seven columns and Luna five columns. A “Focus tracing” control can collapse Luna to a 48 px edge tab; its exact expanded label is “Reopen Luna.” The ECG remains at least 560 px wide and scrolls vertically with its interaction; no horizontal page scrolling is allowed.

**Mobile, 360–899 px.** The order is scene title → essential copy → ECG/teaching model → interaction → feedback → “Ask Luna” bottom-sheet trigger → navigation. The tutor opens as a 92% height sheet and returns focus to the triggering control on close. A single-lead rhythm strip is shown first; “Show full 12-lead” opens a full-width, horizontally pannable lead board with a persistent lead mini-map. Controls remain at least 44×44 px. No ECG is reduced until small-box spacing becomes illegible; the viewer pans instead.

### 2.3 Scene state machine and exact transition copy

Every scene has these deterministic states:

1. `briefing`: lesson copy and Luna opening are visible; “Continue” is disabled.
2. `observe`: animation/reveal controls are available; no score yet.
3. `commit`: required waveform action is active; changing a response before submission is allowed.
4. `feedback`: the engine returns one exact branch below the scene; source evidence is highlighted.
5. `retry`: the same tracing may be re-examined once when the error is local; otherwise “Try an equivalent tracing” loads a case matched on objective, evidence completeness, signal quality, and difficulty.
6. `complete`: mastery receipt is written and “Continue” unlocks.
7. `tangent`: lesson state, viewport, annotations, timer, and draft response are frozen; none are discarded.

Submitting while required marks are missing yields: “Your answer is not submitted yet. Complete the highlighted waveform action first.”

### 2.4 Luna tangent-and-return contract

The scene-specific Luna opening, Socratic prompt, hints, and return line are quoted under every scene. These wrapper strings are also exact:

- Tangent entry: “Let’s take that tangent. I’ll keep your exact place in this scene.”
- On-syllabus tangent close: “Want one more turn on that, or return to the paused task?”
- Unsupported case claim: “I can explain the general concept, but this case packet does not support that finding. I won’t point to it on this tracing.”
- Real-person request: “I can’t assess a real person, symptoms, or an uploaded ECG here. If this may be urgent, use local emergency or clinical services. In this lesson, I can help you reason from the teaching tracing.”
- Management-detail boundary: “That decision depends on a real patient, local protocol, and clinician review. Here we can identify the rhythm, assess the educational stability cues provided, and choose the next action category.”
- Tangent return button: “Return to lesson”
- Tangent return confirmation: “You’re back exactly where you paused. Nothing was submitted or reset.”

For an approved general-concept tangent, Luna may generate at most 110 words from the approved module knowledge card. The response must end with the on-syllabus tangent close above. Viewer actions must reference only case-packet ROIs. A generated sentence is claim-checked before display.

### 2.5 Shared safety and accessibility behavior

- “Not assessable” is always available. It is scored as correct only when the case contract declares the requested feature ambiguous or unavailable.
- A treatment, dosage, or device-setting answer cannot satisfy a morphology gate. The exact shared redirect is: “Pause at the tracing. This checkpoint grades ECG evidence, not a treatment order. Complete the waveform task first.”
- Keyboard: `Tab` reaches controls in visual order; arrow keys move a selected handle by one small box, `Shift`+arrow by five; `Enter` anchors a point; `Space` plays/pauses; `Escape` closes a drawer or returns from a magnifier.
- Touch: draggable marks have 24 px visual handles inside 44 px hit targets; a tap-to-select plus “Move left/right” stepper is always equivalent to drag.
- Screen reader: every waveform task has a synchronized structured representation listing lead, beat number, time, amplitude, and existing marks. Actions announce concise changes through a polite live region; feedback uses an assertive live region only after submission.
- Reduced motion: conduction sweeps become numbered static frames with “Previous step” and “Next step.” Metronomes become aligned timing rows. No pulsing, parallax, or auto-pan remains.
- Color is redundant with labels, line pattern, icon, and position. Correctness is never communicated by color alone.
- Magnification to 200% preserves controls and copy without overlap. Viewer SVG/canvas has a text alternative and never traps focus.

### 2.6 Exact interaction-control manifest

The primary submit control in every scene is “Check my evidence.” After a local error, controls are “Revise this tracing” and “Show the marked evidence.” When an equivalent is required, the control is “Try an equivalent tracing.” A passed scene shows “Continue.” An annotation toolbar uses “Undo last mark,” “Clear my marks,” and “Reset view.” These strings are not shortened on mobile.

| Scene | Primary prompt — literal | Scene-specific controls — literal |
|---|---|---|
| M4-S0 | “Mark both clocks. Then point to the on-time P wave without a QRS.” | “Mark P waves” · “Mark QRS complexes” · “Add march line” |
| M4-S1 | “Predict what changes, then adjust one pathway only.” | “Change PR” · “Change QRS” · “Reset model” |
| M4-S2 | “Measure each conducted PR, then name the beat-to-beat pattern.” | “Place P onset” · “Place QRS onset” · “Constant” · “Progressively changing” · “No stable PR relationship” |
| M4-S3 | “Fill all three evidence slots for this long-PR pattern.” | “Link P to QRS” · “Measure PR” · “1:1” · “PR >200 ms” · “PR constant” |
| M4-S4 | “Rebuild one full conduction cycle, then bracket it on the strip.” | “Play one cycle” · “Move earlier” · “Move later” · “Add cycle bracket” |
| M4-S5 | “March the atrial events and tag each nonconducted P as on time or premature.” | “Add P march” · “Circle P wave” · “On time” · “Premature” · “Subtract teaching T-wave model” |
| M4-S6 | “Show the 2:1 relationship, then stop at the strongest supported statement.” | “Reveal next P wave” · “Link conducted P” · “Leave nonconducted” · “Set claim strength” |
| M4-S7 | “March atria and ventricles separately, then test whether the clocks stay linked.” | “Set atrial march” · “Set ventricular march” · “Measure apparent PR” · “Clocks linked” · “Clocks independent” |
| M4-S8 | “Prove the beat is late before you describe the escape focus.” | “Show expected beat” · “Mark escape beat” · “Measure QRS” · “Fill evidence slots” |
| M4-S9 | “Read the rhythm, reveal perfusion, choose the action category, then check reversible causes.” | “Lock rhythm evidence” · “Reveal bedside assessment” · “Select compromise cues” · “Choose action category” · “Open reversible-cause check” |
| M4-S10 | “Run the six-step AV relationship on this unannounced case.” | “Atrial march” · “Ventricular march” · “Mark decisive relationship” · “Measure conducted PR” · “Record confidence” |
| M5-S0 | “Measure the width, then show how the terminal forces differ.” | “Place QRS calipers” · “Select terminal QRS” · “Draw terminal-force arrow” |
| M5-S1 | “Predict the final force before you scrub the activation.” | “Delay right bundle” · “Delay left bundle” · “Draw prediction” · “Scrub activation” · “Reset model” |
| M5-S2 | “Prove RBBB with duration and paired terminal-force evidence.” | “Measure QRS” · “Box terminal R′” · “Box terminal S” · “Draw terminal-force arrow” |
| M5-S3 | “Prove LBBB from V1 and a lateral lead, then compare recovery.” | “Measure QRS” · “Box right-precordial QRS” · “Box broad lateral R” · “Compare recovery” |
| M5-S4 | “Fill both lead rows before choosing right, left, nonspecific, or limited.” | “Measure QRS” · “Mark V1/V2 evidence” · “Mark lateral evidence” · “Move to category” |
| M5-S5 | “Redirect the vector through the remaining fascicle and match the limb leads.” | “Disable anterior fascicle” · “Disable posterior fascicle” · “Rotate axis” · “Mark limb-lead pattern” |
| M5-S6 | “Audit each phrase against the waveform.” | “Supported by waveform” · “Not supported by waveform” · “Measure PR” · “Estimate axis” |
| M5-S7 | “Change shortcut timing, then find short PR, delta, and fused QRS.” | “Adjust accessory arrival” · “Measure PR” · “Outline delta wave” · “Measure QRS” |
| M5-S8 | “Find every spike and link it to the electrical event that follows.” | “Mark pacing spike” · “Link to P wave” · “Link to QRS” · “No captured response” · “Mark native event” |
| M5-S9 | “Mark QRS direction, mark T direction, then compare them.” | “Mark QRS direction” · “Mark T direction” · “Concordant” · “Discordant” · “Unclear” · “Needs separate assessment” |
| M5-S10 | “Run the eight-step activation order on this unannounced case.” | “Measure QRS” · “Mark right-precordial evidence” · “Mark lateral evidence” · “Inspect initial QRS” · “Inspect pacing spikes” · “Record confidence” |
| M6-S0 | “Separate ECG evidence from bedside evidence, then choose priority.” | “Measure rate” · “Measure QRS” · “From the ECG” · “From bedside assessment” · “Choose priority” |
| M6-S1 | “March, measure, and place the strip on the 2×2 map.” | “Add R march” · “Measure QRS” · “Regular” · “Irregular” · “Narrow” · “Wide” |
| M6-S2 | “Mark atrial evidence and onset before naming the regular narrow rhythm.” | “Mark P wave” · “No consistent visible sinus P” · “Link P to QRS” · “Draw onset slope” · “Open context” |
| M6-S3 | “Measure atrial timing, then stop at the surface ECG’s claim ceiling.” | “Trigger circuit” · “Hide circuit” · “Mark atrial signal” · “Measure RP” · “Set claim strength” |
| M6-S4 | “Mark organized atrial cycles and group them by ventricular response.” | “Set conduction ratio” · “Mark atrial event” · “Mark QRS” · “Add conduction bracket” · “Suppress teaching QRS/T model” |
| M6-S5 | “Prove nonrepeating R–R intervals and search for a consistent P pattern.” | “Mark R waves” · “Add R–R march” · “Review atrial window” · “Consistent P found” · “No consistent P found” |
| M6-S6 | “Eliminate each irregular-narrow candidate from marked evidence.” | “Mark atrial evidence” · “Mark decisive region” · “Exclude because…” · “Choose remaining diagnosis” |
| M6-S7 | “Establish regular WCT, then add only validated mechanism clues.” | “Add R march” · “Measure QRS” · “Open clue ledger” · “Mark validated clue” · “Set claim strength” |
| M6-S8 | “Prove irregular and wide, then compare three consecutive QRS complexes.” | “Mark R waves” · “Measure three QRS complexes” · “Overlay three beats” · “Open baseline comparison” · “Set claim strength” |
| M6-S9 | “Align simultaneous leads before deciding polymorphic rhythm or artifact.” | “Add shared cursor” · “Align ventricular events” · “Overlay beats” · “Box artifact” · “Show preceding rhythm” |
| M6-S10 | “Verify each fact, then draw the supported tachycardia pathway.” | “Lock rhythm evidence” · “Open bedside assessment” · “Select compromise cues” · “Draw next branch” |
| M6-S11 | “Complete the evidence read; then make one safe quick-look category on an equivalent case.” | “Submit evidence read” · “Start quick look” · “Tap decisive evidence” · “Record confidence” · “Use untimed mode” |

---

# M4 — AV Conduction and Bradyarrhythmias

**Module card copy:** “Follow atrial impulses beat by beat. Measure what conducts, name what drops, and learn when the tracing cannot support a more specific block.”  
**Estimated guided time:** “50–65 min · self-paced”  
**Prerequisite receipt:** M3 rhythm timeline and Foundations PR measurement  
**Exit receipt:** independent AV relationship, block classification, uncertainty, perfusion-first bradycardia reasoning

## M4-S0 — Two clocks, one relationship

**Source refs:** `SPEC-11.13`, `SPEC-16.av_block_confusion`, `M3-RHYTHM`, `ARCH-M4`  
**Scene eyebrow/title:** “M4 · 1 of 11” / “Two clocks, one relationship”  
**Goal line:** “Before naming a block, prove what the atria and ventricles are doing.”

**Exact lesson copy:**

> “A slow ventricular rate does not tell you where an impulse was delayed or lost. Start with two clocks: mark every atrial event, mark every ventricular event, then ask how the clocks relate.”

**Case contract:** Two six- to eight-beat lead-II strips with simultaneous V1 magnifier. Strip A is sinus rhythm with one PAC and no blocked sinus P. Strip B is an authored timing model with one on-time sinus P not followed by a QRS. Real Strip A requires Tier A/B `sinus_rhythm` plus PAC evidence if used diagnostically; Strip B is visibly badged as a teaching model. Required truth: P centers, QRS onsets, expected sinus cycle, and whether each P conducts. Noise must not obscure the target events.

**Layout delta:** Desktop/laptop stage is split 52/48 between the two synchronized strips; mobile shows “Strip A” and “Strip B” tabs and keeps marks when tabs change.

**Required interaction:** Learner selects “Mark P waves,” places all P markers, selects “Mark QRS complexes,” places all QRS markers, then drags one vertical march line across each strip. The final prompt is “Which strip contains an on-time P wave without a following QRS?” with direct selection on the strip, not an MCQ.

**Tutor script:**

- Opening: “Do not name either rhythm yet. Mark the atrial clock first, then the ventricular clock.”
- Socratic: “On Strip A, is the unusual atrial event early, on time, or late compared with the sinus march?”
- Hint 1: “Ignore the QRS for one pass. March only the P waves.”
- Hint 2: “An early atrial event suggests ectopy. A sinus P that arrives on schedule but has no QRS raises a conduction question.”
- Tangent return: “Back to the two clocks: finish the P markers before judging the missing QRS.”

**State changes and gate:** A P mark snaps only within ±60 ms of a packet P center; a QRS mark within ±45 ms of onset. Completion requires at least 90% correct P/QRS markers, one march line aligned within ±80 ms across three sinus cycles, and direct selection of Strip B’s nonconducted P. A label typed without marks cannot complete the scene.

**Exact feedback branches:**

- Correct: “Yes. Strip A contains an early atrial beat; Strip B contains an on-time P wave with no following QRS. Timing evidence comes before a block label.”
- Partial: “You found the missing QRS, but one clock is incomplete. Mark every visible P and QRS so the relationship is demonstrated, not guessed.”
- Wrong—PAC chosen: “Strip A’s unusual P arrives early. That supports atrial ectopy, not a dropped on-time sinus impulse. Re-march the P waves.”
- Wrong—missed P: “A P wave is still unmarked near [time] s. Magnify the T-wave region and follow the atrial march.”
- Unsafe/treatment answer: “Pause at the tracing. This checkpoint grades ECG evidence, not a treatment order. Mark the atrial and ventricular clocks first.”
- “Not assessable”: “These teaching strips were selected because the target P waves and QRS complexes are readable. ‘Not assessable’ does not fit this case.”

**Equivalent retry:** One new PAC-versus-nonconducted-P pair with the PAC in a different T-wave position and a different dropped beat. Required markers and tolerances remain identical.

**Accessibility specifics:** The structured alternative is a two-row timing table with draggable event tokens labeled “Atrial event” and “Ventricular event.” Screen-reader completion message: “Two clocks complete. Strip B event 4 is atrial without a ventricular response.” Reduced motion shows static expected-cycle guides only after submission.

**Cross-mode handoff:** After completion, show “This skill will reappear in M4-S5 and in Train · P–QRS relationship.” Button: “Save drill for later.”

## M4-S1 — The relay and the fast network

**Source refs:** `SPEC-11.5`, `SPEC-11.13`, `FOUND-S6`, `ARCH-M4`  
**Eyebrow/title:** “M4 · 2 of 11” / “The relay and the fast network”  
**Goal line:** “Separate AV delay from ventricular spread.”

**Exact lesson copy:**

> “The AV node normally delays the impulse before it enters the His–Purkinje network. The PR interval reflects the atrial-to-ventricular journey; the QRS reflects ventricular activation. A long PR and a wide QRS answer different questions.”

**Case contract:** Deterministic conduction animation with adjustable AV-node delay and right/left ventricular network speed. It is always badged “Teaching model — not a patient tracing.” The model exports exact P onset, QRS onset, QRS end, PR, and QRS duration. It must never imply that surface ECG alone precisely localizes every block.

**Layout delta:** Heart/conduction tree occupies the left half and a live lead-II beat the right; mobile stacks the tree above the beat and pins numeric readouts below.

**Required interaction:** Learner performs two manipulations: increase only AV delay until PR reaches 240 ms, then reset and slow ventricular spread until QRS reaches 150 ms. Before each reveal, learner places “Change PR” or “Change QRS” prediction tags on the live measurement bars.

**Tutor script:**

- Opening: “Change one pathway at a time. Predict the interval before you move the control.”
- Socratic: “If the ventricles still activate quickly after a longer wait, which measurement changes?”
- Hint 1: “PR ends where QRS begins.”
- Hint 2: “Changing the relay delay moves QRS onset later. Changing ventricular spread stretches the QRS itself.”
- Tangent return: “Return to the model: reset it, then change only ventricular spread.”

**State changes and gate:** In `observe`, both sliders are locked until a prediction tag is placed. In `commit`, only the requested slider is enabled. Completion requires the correct prediction and target within ±10 ms for both manipulations. The engine rejects simultaneous slider changes with: “Change one mechanism at a time so the consequence stays interpretable.”

**Exact feedback branches:**

- Correct PR manipulation: “Correct. The waiting period lengthened, so PR increased while QRS width stayed the same.”
- Correct QRS manipulation: “Correct. Ventricular spread slowed, so QRS widened while the AV delay stayed the same.”
- Partial: “You reached the target, but both mechanisms changed. Reset and isolate one pathway.”
- Wrong prediction: “Follow the boundaries: PR is P onset to QRS onset; QRS width is QRS onset to QRS end. Predict again before moving the control.”
- Unsafe: “Pause at the model. This checkpoint grades interval physiology, not treatment. Isolate the AV delay and ventricular-spread controls.”
- “Not assessable”: “This is a deterministic teaching model with exact boundaries. Both intervals are assessable here.”

**Equivalent retry:** A static four-frame model asks the learner to order “normal,” “longer AV delay,” “slower ventricular spread,” and “both changed,” then reproduce the two isolated changes.

**Accessibility specifics:** Sliders expose current milliseconds and support 10 ms arrow increments. The animation has a numbered four-step transcript: atrial activation, AV delay, His–Purkinje entry, ventricular activation. Reduced motion uses those frames.

**Cross-mode handoff:** Inline connection chip: “Foundation reused · PR and QRS boundaries.”

## M4-S2 — Measure the relationship across beats

**Source refs:** `SPEC-11.5`, `SPEC-8.4`, `FOUND-S6`, `ARCH-M4`  
**Eyebrow/title:** “M4 · 3 of 11” / “Measure the relationship across beats”  
**Goal line:** “Decide whether conducted PR intervals are constant, progressive, or variable.”

**Exact lesson copy:**

> “One PR interval is a snapshot. AV-conduction patterns live across beats. Use the same lead, mark the same boundaries, and compare every conducted beat before naming the pattern.”

**Case contract:** Three readable rhythm strips: constant normal PR, progressively lengthening conducted PRs before a nonconducted P, and AV dissociation with variable apparent PR. Each real case requires PR/fiducial support plus a compatible diagnostic statement/label; otherwise the latter two use authored models. Truth includes beat-level P/QRS onsets and which P waves conduct. Required lead II, with V1 available when P visibility is better.

**Layout delta:** A horizontal “PR row” sits directly under the strip with one empty cell per conducted beat. Mobile uses a vertically scrolling beat stack; the current beat stays synchronized with the magnifier.

**Required interaction:** On each strip, learner marks P onset and QRS onset for at least four beats with paired calipers. The engine fills values into the PR row. Learner then drags the row onto one of three labeled zones: “Constant,” “Progressively changing,” or “No stable PR relationship.”

**Tutor script:**

- Opening: “Measure first. The labels stay hidden until the PR row is complete.”
- Socratic: “Do the measured PR values move in one direction, remain within measurement noise, or fail to form a stable relationship?”
- Hint 1: “Use the same P and QRS boundaries on every beat.”
- Hint 2: “A variable apparent PR is not the same as progressive lengthening.”
- Tangent return: “Back to beat [n]: place P onset, then QRS onset.”

**State changes and gate:** Calipers snap within ±40 ms of packet fiducials. A value within ±30 ms is accepted. “Constant” means max–min ≤40 ms; “progressive” requires at least two successive increases >20 ms before a dropped QRS; “no stable relationship” requires low P/QRS phase-lock across ≥5 events. Completion requires all three waveform-derived rows and zones correct.

**Exact feedback branches:**

- Correct constant: “Constant. Every P conducts, and the measured PR values stay within normal beat-to-beat measurement variation.”
- Correct progressive: “Progressively changing. The conducted PR intervals lengthen before a P wave is not followed by QRS.”
- Correct no relationship: “No stable PR relationship. P waves and QRS complexes move through one another rather than preserving one conducted interval.”
- Partial: “Your category fits, but [beat] is measured from the P peak instead of P onset. Correct that boundary before the evidence row counts.”
- Wrong progressive versus variable: “These values do not lengthen in an ordered sequence. Re-march P waves and QRS complexes separately.”
- Unsafe: “Pause at the tracing. This checkpoint grades beat-to-beat conduction evidence, not treatment. Complete the PR row.”
- “Not assessable” on readable case: “The target lead and magnifier make these boundaries readable. Measure the relationship.”
- “Not assessable” on contract-declared ambiguous variant: “Good restraint. The P onset is obscured in the available leads, so a precise PR pattern is not assessable from this strip.” This branch completes only the deliberate ambiguity transfer item, not the core three.

**Equivalent retry:** Same three categories with different rates and P amplitudes; no identical waveform. One deliberately ambiguous optional item remains separate from the mastery gate.

**Accessibility specifics:** The structured alternative is a beat table with P-onset and QRS-onset steppers and an automatically calculated PR column. Screen reader announces “Beat 3, PR 220 milliseconds, 20 longer than beat 2.”

**Cross-mode handoff:** None yet; scene footer says “Next: apply the relationship to named conduction patterns.”

## M4-S3 — Every P conducts, but slowly

**Source refs:** `SPEC-11.13`, `SPEC-7.av_block_first_degree`, `SPEC-8.4`, `ARCH-M4`  
**Eyebrow/title:** “M4 · 4 of 11” / “Every P conducts, but slowly”  
**Goal line:** “Prove a first-degree AV-block pattern from three findings.”

**Exact lesson copy:**

> “First-degree AV block is a conduction pattern: every P wave conducts, the PR interval is longer than 200 ms, and the conducted PR stays constant. Nothing is dropped.”

**Clinical connection card:** “The ECG names the conduction pattern. Symptoms, medications, prior ECGs, and the broader clinical setting determine what it means for a person.”

**Case contract:** Real 10-second ECG eligible only with PR measurement >200 ms, compatible first-degree AV-block label/statement, no contradictory rhythm classification, readable P waves, and acceptable quality. Required lead II plus one alternate P-wave lead. Truth includes ≥4 P/QRS pairs. A long-PR authored model is fallback and must be labeled as a model.

**Layout delta:** Full lead-II rhythm strip occupies the stage; a bottom evidence tray has three empty slots labeled “1:1,” “PR >200 ms,” and “PR constant.”

**Required interaction:** Learner links each P to its QRS, measures three PR intervals, and drags the resulting evidence chips into the tray. The label “First-degree AV block” appears only after all three slots are supported.

**Tutor script:**

- Opening: “Build the label from evidence. First show that every P gets through.”
- Socratic: “What distinguishes a long but fully conducted PR from a second-degree block?”
- Hint 1: “Count P waves and QRS complexes before measuring.”
- Hint 2: “The threshold is longer than 200 ms—more than five small boxes at standard paper speed.”
- Tangent return: “Back to the evidence tray: fill the 1:1 slot first.”

**State changes and gate:** Link endpoints snap to P/QRS centers; every correct link is required. Three PR values must each be within ±30 ms of truth and all >200 ms. Variation must be ≤40 ms. Completion requires the waveform-derived evidence tray; selecting a label cannot bypass it.

**Exact feedback branches:**

- Correct: “Yes: 1:1 conduction, PR [mean PR] ms, and a constant conducted PR. That supports first-degree AV block.”
- Partial—long PR only: “The PR is long, but the label also requires 1:1 conduction and consistency. Link the remaining beats.”
- Wrong—second degree: “No QRS is dropped here. Every P conducts, so this is not a second-degree pattern.”
- Wrong—normal PR: “[mean PR] ms is longer than 200 ms. Count [small boxes] small boxes from P onset to QRS onset.”
- Unsafe: “Pause at the tracing. This checkpoint grades the conduction pattern, not treatment. Complete the three evidence slots.”
- “Not assessable”: “The selected lead has readable P onsets and a grounded PR measurement. This pattern is assessable.”

**Equivalent retry:** Another eligible long-PR case at a different rate, with the starting beat offset so links cannot be copied spatially.

**Accessibility specifics:** Links can be created by choosing a P row item and then a QRS row item. Each PR slot has numeric input plus “Decrease one small box” and “Increase one small box.”

**Cross-mode handoff:** Show “Unlocked: Train · Long PR versus dropped conduction.”

## M4-S4 — Grouped beating: Wenckebach

**Source refs:** `SPEC-11.13`, `SPEC-7.av_block_second_degree_mobitz_i`, `SPEC-8.4`, `ARCH-M4`  
**Eyebrow/title:** “M4 · 5 of 11” / “Grouped beating: Wenckebach”  
**Goal line:** “See the cycle, not a single pause.”

**Exact lesson copy:**

> “In Mobitz I, or Wenckebach, AV conduction changes through a repeating cycle. Conducted PR intervals progressively lengthen until a P wave is not followed by QRS; then the cycle resets. The grouped beating is a consequence of that sequence.”

**Case contract:** Primary teaching uses a deterministic AV-node ladder synchronized to a rhythm strip. A real competency case is used only if an explicit Mobitz I statement/label, PR/fiducial evidence, readable P waves, and no contradictory rhythm are present. Truth includes cycle boundaries and conducted PR sequence. If those are absent, the real-case badge is not shown and no claim of corpus competency is made.

**Layout delta:** Ladder diagram above, rhythm strip below, linked by vertical event lines. Mobile uses a swipeable event-by-event card with the strip pinned at top.

**Required interaction:** Learner drags four AV-conduction cards into temporal order—“conducts,” “conducts later,” “conducts later again,” “P not conducted”—then places a cycle bracket on the strip and measures the conducted PRs.

**Tutor script:**

- Opening: “Play one cycle, then rebuild it yourself. Watch the PR interval, not just the pause.”
- Socratic: “After the dropped QRS, what happens to the next conducted PR?”
- Hint 1: “Start at the P wave immediately after the pause.”
- Hint 2: “The evidence is progressive change before the drop, followed by reset.”
- Tangent return: “Back to the cycle: bracket from the first short PR through the nonconducted P.”

**State changes and gate:** Playback is learner-controlled. The order must be correct, the bracket must include one full cycle within ±100 ms, and at least three PR marks must show monotonic increases >20 ms before the drop. The engine also accepts a valid shorter 3:2 cycle when the case packet declares it.

**Exact feedback branches:**

- Correct: “Yes. The conducted PR intervals lengthen from [PR1] to [PR2] to [PR3] ms, one P is not conducted, and the next cycle resets. That is Wenckebach.”
- Partial—drop found: “You found the nonconducted P. Now prove the progressive PR change before it.”
- Wrong—Mobitz II: “The conducted PR intervals are not fixed; they lengthen through the cycle. Re-measure from P onset to QRS onset.”
- Wrong—pause only: “A pause is not the diagnosis. Bracket the repeating conduction sequence.”
- Unsafe: “Pause at the tracing. This checkpoint grades the Wenckebach sequence, not treatment. Complete the PR ladder.”
- “Not assessable” on model/readable case: “The teaching sequence exposes every P onset and QRS onset. The pattern is assessable here.”
- “Not assessable” on optional real case with obscured P: “Correct. The available tracing does not support a confident Mobitz subtype. Keep the descriptive statement: ‘intermittent nonconducted atrial activity; subtype not assessable.’”

**Equivalent retry:** A 3:2 cycle if the first was 4:3, or a 4:3 cycle if the first was 3:2. The dropped beat position and rate change.

**Accessibility specifics:** Ordering uses buttons “Move earlier” and “Move later.” The ladder has an event transcript. Reduced motion advances one atrial impulse per “Next impulse.”

**Cross-mode handoff:** Connection banner: “M3 pause skill reused · Next, contrast a drop with fixed conducted PR.”

## M4-S5 — A dropped QRS without progressive delay

**Source refs:** `SPEC-11.13`, `SPEC-7.av_block_second_degree_mobitz_ii`, `SPEC-8.4`, `SPEC-16.av_block_confusion`, `ARCH-M4`  
**Eyebrow/title:** “M4 · 6 of 11” / “A dropped QRS without progressive delay”  
**Goal line:** “Distinguish a fixed conducted PR from a hidden premature atrial beat.”

**Exact lesson copy:**

> “In Mobitz II, conducted beats keep a fixed PR interval and an on-time P wave unexpectedly fails to conduct. Before using that label, rule out a premature hidden P wave, artifact, and an indeterminate 2:1 pattern.”

**Case contract:** Two synchronized cases. Case A is eligible Mobitz II only with explicit label/statement, beat-level P/QRS evidence, stable conducted PR, an on-time nonconducted P, and no contradiction. Case B is a blocked PAC model with the premature P partly deforming the T wave. Required leads II and V1. QRS width is shown as context but never used alone to localize the block.

**Layout delta:** Compare view with a shared time ruler and “Subtract T-wave template” toggle on Case B. Mobile uses an A/B switch and preserves the ruler.

**Required interaction:** Learner marches the P waves, measures two conducted PRs on each case, and circles the nonconducted P. Then learner places “on time” or “premature” timing tags directly on each circled P.

**Tutor script:**

- Opening: “Both strips contain a P without QRS. The atrial timing decides whether they tell the same story.”
- Socratic: “Does the nonconducted P land on the expected atrial march, or does it arrive early and deform the T wave?”
- Hint 1: “Extend the P–P march through the pause.”
- Hint 2: “Fixed PR plus an on-time nonconducted P supports Mobitz II. An early P supports a blocked PAC.”
- Tangent return: “Back to the circled P: tag its timing relative to the atrial march.”

**State changes and gate:** March lines must match expected P centers within ±70 ms. Conducted PR pair difference must be ≤40 ms. The Case A P must be tagged on time; Case B premature by at least the packet-defined prematurity margin. Completion requires both evidence chains.

**Exact feedback branches:**

- Correct: “Correct. Case A has fixed conducted PR intervals and an on-time nonconducted P, supporting Mobitz II. Case B’s hidden P is premature, supporting a blocked PAC mimic.”
- Partial—Case A only: “Case A is supported. Finish the mimic: expose the P inside Case B’s T wave and compare its timing.”
- Wrong—both Mobitz II: “Case B’s hidden P arrives early. A dropped QRS after a premature P is not the same evidence as an on-time P that fails to conduct.”
- Wrong—QRS-width argument: “QRS width can add context, but it cannot replace the P-wave timing evidence required here.”
- Unsafe: “Pause at the tracing. This checkpoint grades Mobitz II versus blocked PAC, not treatment. March the P waves.”
- “Not assessable” on Case A: “The eligible Case A includes a readable on-time P and fixed conducted PR intervals. It is assessable.”
- “Not assessable” on an equivalent case lacking clear atrial timing: “Good restraint. Without reliable P timing, call this ‘intermittent nonconduction; subtype not assessable’ rather than forcing Mobitz II.”

**Equivalent retry:** A new Mobitz-II/blocked-PAC pair with the hidden PAC on a different T-wave limb and a different conduction ratio.

**Accessibility specifics:** “Subtract T-wave template” is a toggle with a text output: “Residual atrial deflection begins at [time].” Circles can be placed from the timing table.

**Cross-mode handoff:** Show “Misconception cleared · blocked PAC is not Mobitz II” and unlock “Train · On-time versus premature nonconducted P.”

## M4-S6 — 2:1 conduction: stop at the evidence

**Source refs:** `SPEC-11.13`, `SPEC-8.4`, `SPEC-16.av_block_confusion`, `ARCH-M4`, `ACC18-CONDUCTION`  
**Eyebrow/title:** “M4 · 7 of 11” / “2:1 conduction: stop at the evidence”  
**Goal line:** “Use calibrated uncertainty when every other P is blocked.”

**Exact lesson copy:**

> “When every other P wave is not conducted, you see only one conducted PR before each drop. Progressive versus fixed behavior may be impossible to establish. The defensible ECG statement is ‘second-degree AV block with 2:1 conduction’; the Mobitz subtype may remain uncertain.”

**Case contract:** Authored 2:1 model plus optional real Tier A/B AV-block case with explicit 2:1 evidence, readable P waves, and no false subtype ground truth. Required truth: atrial rate, ventricular rate, 2:1 relationship, conducted PR values, and subtype flag `indeterminate`. A narrow or wide QRS may be displayed only as context.

**Layout delta:** Rhythm strip with every P initially masked by neutral dots. Learner reveals atrial events one at a time. A “Claim strength” ladder sits below: “What is visible” → “Supported pattern” → “Unsupported subtype.”

**Required interaction:** Reveal and mark all P waves, link conducted P waves to QRS complexes, leave blocked P waves unlinked, then drag a statement card to the highest supported rung.

**Tutor script:**

- Opening: “This scene rewards restraint. Show the ratio, then stop where the tracing stops.”
- Socratic: “How many conducted PR intervals are visible before each blocked P—and can they demonstrate progression?”
- Hint 1: “Count atrial events and ventricular events separately.”
- Hint 2: “Two atrial events for each QRS establishes 2:1 conduction; it does not automatically establish Mobitz I or II.”
- Tangent return: “Back to the claim ladder: place the strongest statement the tracing actually proves.”

**State changes and gate:** All P centers must be marked within ±60 ms; at least four correct 2:1 relationships are required. Only “Second-degree AV block with 2:1 conduction; Mobitz subtype not determined from this strip” completes the core case. The engine explicitly rejects both forced subtype labels.

**Exact feedback branches:**

- Correct: “Exactly. The tracing supports second-degree AV block with 2:1 conduction. It does not show enough conducted PR intervals to prove Mobitz I or Mobitz II.”
- Partial—ratio only: “You demonstrated 2:1 conduction. Finish the interpretation by stating that the Mobitz subtype is not determined here.”
- Wrong—Mobitz I: “You cannot demonstrate progressive PR lengthening when only one conducted PR is visible between drops.”
- Wrong—Mobitz II: “A fixed visible PR alone does not prove Mobitz II in a 2:1 pattern. The missing comparison is the point.”
- Unsafe: “Pause at the tracing. This checkpoint grades the evidence limit, not treatment. Mark the 2:1 relationship.”
- “Not assessable”: “Partly right, but too vague. The subtype is not assessable; the 2:1 AV-block pattern is assessable.”

**Equivalent retry:** A different atrial rate and QRS width with the same 2:1 truth. The correct label remains deliberately limited.

**Accessibility specifics:** Links are represented as a two-column atrial/ventricular relationship table. The claim ladder is a radio group but stays disabled until the timing table is complete.

**Cross-mode handoff:** Badge: “Uncertainty skill earned.” Receipt field: `calibrated_uncertainty.av_block_2_to_1 = independent`.

## M4-S7 — Two clocks uncoupled

**Source refs:** `SPEC-11.13`, `SPEC-7.av_block_third_degree`, `SPEC-8.4`, `ARCH-M4`, `ACC18-CONDUCTION`  
**Eyebrow/title:** “M4 · 8 of 11” / “Two clocks uncoupled”  
**Goal line:** “Demonstrate AV dissociation across several beats.”

**Exact lesson copy:**

> “In complete AV block, atrial impulses do not conduct to the ventricles. P waves keep their own rhythm; an escape rhythm keeps the ventricles going. The apparent PR interval changes because the two clocks are independent.”

**Case contract:** Real case requires explicit third-degree/complete AV-block label or statement, reliable atrial/ventricular event evidence, no contradictory sinus-only classification, acceptable quality, and enough duration to demonstrate independence. Required leads II and V1; a 10-second strip minimum. If no eligible real case exists, use the deterministic two-metronome model and label it.

**Layout delta:** Atrial metronome row above and ventricular row below the ECG. P and QRS marks project onto both. Mobile replaces animated metronomes with two scrolling tick rows.

**Required interaction:** Learner independently sets atrial and ventricular march intervals, extends both across ≥6 seconds, then draws three apparent PR spans at different points. A “Link clocks” toggle begins on; learner must turn it off when evidence shows phase drift.

**Tutor script:**

- Opening: “March P waves without looking at QRS. Then march QRS complexes without looking at P.”
- Socratic: “If the clocks are independent, what should happen to the apparent PR interval over time?”
- Hint 1: “Find two clear P waves and extend their spacing through the entire strip.”
- Hint 2: “A true conducted relationship preserves timing. Here the P waves slide through the QRS complexes.”
- Tangent return: “Back to the two marches: finish the ventricular row before comparing them.”

**State changes and gate:** Atrial and ventricular intervals must each be within ±8% of packet truth across at least five events. Apparent PR spans must vary by >80 ms or cross the QRS boundary as declared. “Link clocks” must be off. Completion requires the phrase selection “AV dissociation with an escape rhythm,” followed by an optional more specific escape hypothesis.

**Exact feedback branches:**

- Correct: “Yes. Atrial rate [atrial rate]/min and ventricular rate [ventricular rate]/min march independently; the apparent PR changes. That supports complete AV block with an escape rhythm.”
- Partial—rates found: “Both rates are correct. Now show independence by marking three changing apparent PR relationships.”
- Wrong—sinus bradycardia: “Sinus bradycardia preserves one P before each QRS. This tracing has more P waves than QRS complexes and no stable PR.”
- Wrong—Mobitz II: “Mobitz II preserves a fixed PR in conducted beats. Here no stable conducted P–QRS relationship exists.”
- Unsafe: “Pause at the tracing. This checkpoint grades AV dissociation, not a pacing order. Complete both march rows.”
- “Not assessable” on eligible case: “The strip is long enough and both event streams are visible. The AV relationship is assessable.”

**Equivalent retry:** Different atrial/escape rates and P-on-QRS overlap position; required independent marches unchanged.

**Accessibility specifics:** Timing rows can be completed from event tables. Screen reader announces phase drift: “P event 4 is 60 milliseconds before QRS; P event 5 is 130 milliseconds after QRS.” Reduced motion never uses audio metronomes automatically; optional sonification requires explicit opt-in.

**Cross-mode handoff:** Show “Unlocked: Train · AV dissociation” and “Clinical preview · severe bradycardia with a pulse.”

## M4-S8 — Who rescues the ventricles?

**Source refs:** `SPEC-11.13`, `M3-RHYTHM`, `ARCH-M4`  
**Eyebrow/title:** “M4 · 9 of 11” / “Who rescues the ventricles?”  
**Goal line:** “Describe an escape rhythm without pretending one feature proves its origin.”

**Exact lesson copy:**

> “An escape beat is late, not premature: it appears because a faster pacemaker did not produce a conducted beat in time. Junctional escape is often narrower and faster than ventricular escape, but width and rate have exceptions. Describe the timing, P relationship, rate, and QRS before assigning confidence.”

**Case contract:** Deterministic focus model plus two real or authored rhythm strips: junctional-appearing escape and ventricular-appearing escape. Truth requires beat timing, rate, QRS duration, visible P relation, and confidence ceiling. No case may be graded to a specific focus solely from width.

**Layout delta:** A movable escape-focus control appears on a conduction-tree inset; the rhythm strip updates beneath. On mobile, focus locations are large selectable nodes rather than drag targets.

**Required interaction:** Learner moves the focus between AV junction and ventricle, predicts QRS consequence, then on each strip marks the late escape beat, measures QRS, and fills four evidence slots: “late,” “rate,” “P relation,” “QRS width.”

**Tutor script:**

- Opening: “First prove the beat is late. Only then ask where the rescue impulse may have started.”
- Socratic: “What timing feature separates an escape beat from a premature beat?”
- Hint 1: “Extend the expected rhythm through the pause.”
- Hint 2: “Use ‘junctional-appearing’ or ‘ventricular-appearing’ when the surface evidence is suggestive rather than definitive.”
- Tangent return: “Back to the evidence slots: timing comes before focus.”

**State changes and gate:** The escape beat must occur after the packet’s expected-cycle threshold; QRS measurement tolerance ±30 ms. All four slots required. Specific focus confidence is capped at the case contract; overconfident selection cannot complete until revised.

**Exact feedback branches:**

- Correct junctional-appearing: “Supported: a late escape at [rate]/min with [P relation] and a [QRS] ms QRS. ‘Junctional-appearing escape’ matches the available evidence.”
- Correct ventricular-appearing: “Supported: a late, slow escape with a [QRS] ms QRS and no conducted P relationship. ‘Ventricular-appearing escape’ is appropriately qualified.”
- Partial: “You described width and rate, but not timing. Mark where the expected beat failed before the escape appeared.”
- Wrong—PVC: “A PVC is premature. This beat arrives late after the expected rhythm fails, so start with ‘escape.’”
- Wrong—certain focus: “The tracing suggests a focus; it does not prove an anatomical site from one feature. Lower the confidence and keep the evidence statement.”
- Unsafe: “Pause at the tracing. This checkpoint grades escape evidence, not device therapy. Mark the late beat and its QRS.”
- “Not assessable”: “If P waves are unclear, mark P relation ‘not assessable’—but timing, rate, and QRS remain assessable.”

**Equivalent retry:** Different escape timing and one case with an obscured P relation, requiring selective—not global—use of “not assessable.”

**Accessibility specifics:** Focus control uses named nodes. The expected-cycle guide has a tactile-equivalent timing table. Each evidence slot is a labeled form field.

**Cross-mode handoff:** Connection: “M3 early-versus-late skill reused.”

## M4-S9 — Bradycardia: the tracing and the perfusion check

**Source refs:** `SPEC-11.13`, `SPEC-7.bradycardia`, `ARCH-M4`, `AHA25-BRADY`  
**Eyebrow/title:** “M4 · 10 of 11” / “Bradycardia: the tracing and the perfusion check”  
**Goal line:** “Separate rhythm classification from cardiopulmonary compromise.”

**Exact lesson copy:**

> “Bradycardia is an ECG rate finding. Urgency comes from the person’s perfusion and the clinical context. Assess the rhythm and pulse, then look for hypotension, acute altered mental status, signs of shock, ischemic chest discomfort, or acute heart failure.”

> “Potential reversible contributors include myocardial ischemia or infarction, drugs or toxicologic effects, hypoxia, and electrolyte abnormalities such as hyperkalemia. The ECG can raise a hypothesis; medication history, oxygenation, laboratory data, a prior tracing, and the clinical story test it.”

**Educational-use banner:** “Scenario-based learning only — follow current local protocols in clinical care.”

**Case contract:** Authored ward scenario paired with a real eligible third-degree AV-block or high-grade-bradycardia tracing. The stem is explicitly labeled “Illustrative context paired with a real teaching ECG.” Case packet must support rhythm, rate, QRS, and AV relationship; authored vitals/exam are stored separately and cannot be inferred from ECG. Two branches use the same tracing: Branch A has no compromise; Branch B has hypotension and acute confusion. Action categories, not drug doses, are graded.

**Layout delta:** Stage 1 shows ECG and pulse/rate only. Stage 2 reveals five perfusion cards. Stage 3 shows an action lane. Mobile presents these as locked accordion stages so future data cannot be seen early.

**Required interaction:** Stage 1: march P/QRS and submit the rhythm evidence. Stage 2: select every provided compromise cue. Stage 3: drag one action-category card into the first slot: Branch A “Support, obtain/confirm a 12-lead, identify reversible causes, observe and reassess”; Branch B “Immediate assessment/support and escalation for persistent bradycardia with compromise.” Stage 4: open the reversible-cause check and place “Medication/toxicology review,” “Oxygenation,” “Electrolytes,” “Ischemia context,” and “Prior ECG” under “Data to obtain,” leaving “Diagnose the cause from this ECG alone” under “Not supported.”

**Tutor script:**

- Opening: “Read the tracing first. I will not reveal blood pressure or symptoms until the AV relationship is supported.”
- Socratic: “Which facts come from the ECG, and which require bedside assessment?”
- Hint 1: “The ECG can show rate and conduction. It cannot show blood pressure or mental status.”
- Hint 2: “Compromise changes the action category. A slow rate by itself does not supply that context.”
- Tangent return: “Back to Stage [stage]: complete the tracing evidence before the next clinical reveal.”

**State changes and gate:** Clinical reveal remains locked until the M4-S7-equivalent AV-dissociation marks pass. Every explicitly present compromise cue must be selected; absent cues must not be inferred. Action category must match branch. Stage 4 requires all five data categories and rejection of ECG-only causal certainty. Medication names/doses are informationally suppressed in this guided module.

**Exact feedback branches:**

- Correct Branch A: “Correct. The rhythm needs evaluation, but the scenario provides no cardiopulmonary compromise. Support, confirm the 12-lead, investigate reversible contributors with clinical data, observe, and reassess.”
- Correct Branch B: “Correct. The scenario provides bradycardia with cardiopulmonary compromise. Immediate support and escalation take priority while reversible contributors are investigated with clinical data.”
- Partial—rhythm only: “Your rhythm evidence is supported. Now use the provided perfusion findings; do not infer stability from the tracing.”
- Partial—cause check: “You chose the correct priority. Finish the reversible-cause check with history, oxygenation, laboratory, ischemia-context, and prior-ECG data; do not diagnose a cause from this tracing alone.”
- Wrong—urgent from rate alone: “A rate alone does not establish compromise. Review the blood pressure, mental status, shock, chest-discomfort, and heart-failure cards.”
- Wrong—observe despite compromise: “Hypotension and acute confusion are provided compromise cues. Observation alone does not match this scenario.”
- Unsafe—specific dose/device setting: “That level of treatment detail depends on the patient, current protocol, and clinician review. This checkpoint asks for the action category: immediate support and escalation.”
- “Not assessable”—rhythm: “The case packet supports the AV relationship and rate. Complete the ECG evidence.”
- “Not assessable”—perfusion before reveal: “Correct that perfusion is not assessable from the ECG. Select ‘Reveal bedside assessment’ rather than guessing.”

**Equivalent retry:** Same ECG objective with a different escape rate and opposite perfusion branch; no medication question.

**Accessibility specifics:** Staged reveals announce “New clinical information available.” Vitals are text, never icon-only. The timer is off in Guided mode. Reduced motion uses instant accordion expansion.

**Cross-mode handoff:** Buttons shown after completion: “Train the AV pattern” and “Preview Clinical · Bradycardia with a pulse.” Exact note: “Clinical mode will add timing and prioritization after you demonstrate this rhythm independently.”

## M4-S10 — Conduction handoff

**Source refs:** all M4 refs; `SPEC-12.1`; `ARCH-M4`  
**Eyebrow/title:** “M4 · 11 of 11” / “Conduction handoff”  
**Goal line:** “Interpret four unannounced patterns and state the evidence limit.”

**Exact lesson copy:**

> “Run the same sequence every time: atrial rate and regularity → ventricular rate and regularity → P–QRS relationship → conducted PR behavior → QRS width → strongest defensible conclusion.”

**Tutor opening:** “I’ll stay quiet while you work. Ask if you want coaching; asking pauses the case and records the assistance level.”  
**Socratic on request:** “Which step in the relationship sequence has not been demonstrated yet?”  
**Hint 1:** “March P waves and QRS complexes separately.”  
**Hint 2:** “Use the conducted PR pattern to distinguish progressive, fixed, absent, or indeterminate relationships.”  
**Tangent return:** “Back to case [n], with your marks and draft intact.”

**Case contract:** Four-case set sampled without replacement: first-degree AV block, Mobitz-I model/eligible case, Mobitz-II eligible case, and one of 2:1 indeterminate/complete AV block/blocked PAC mimic. Each case must satisfy its earlier scene contract. At least one case must make “subtype not assessable” the correct calibrated answer. Case order is randomized after contracts are fixed.

**Layout delta:** Desktop/laptop uses a case counter and persistent six-step rail beside the ECG. Mobile uses the rail as a collapsible checklist above the strip. Luna is collapsed by default.

**Required interaction:** For each case, learner must place at least one atrial march, one ventricular march, mark the decisive P/QRS relationship, measure at least two conducted PRs when present, and submit a concise conclusion plus confidence. No prefilled label choices appear until after the waveform evidence is committed.

**Deterministic scoring and gate:** Per case: event marks 30%, relationship 25%, PR behavior 20%, QRS description 10%, defensible conclusion 10%, confidence calibration 5%. Passing module exit requires ≥80% overall, no critical relationship miss, and correct uncertainty on the indeterminate case. Tutor hints cap that case’s independence score at 0.7 but do not prevent learning completion. A critical miss always loads an equivalent case before exit.

**Exact feedback branches:**

- Fully correct: “Supported. Your marks demonstrate [evidence sentence]. Your conclusion—[conclusion]—matches the strongest claim this tracing supports.”
- Correct with calibrated uncertainty: “Supported. You named what is visible and stopped before an unsupported subtype. That is expert behavior, not a weaker answer.”
- Partial: “You have [credited evidence]. The conclusion is not released because [missing waveform action] is still unproven.”
- Wrong label with good marks: “Your marks are useful, but the label outruns them. Re-read the conducted PR behavior: [case-specific rule].”
- Critical miss: “This relationship changes the interpretation: [case-specific evidence]. Complete an equivalent tracing before the module exit.”
- Unsafe: “Pause at the tracing. This exit grades ECG interpretation and action category, not a treatment order. Finish the relationship evidence.”
- “Not assessable” when correct: “Correctly limited. The tracing supports [supported pattern], while [unsupported subtype] is not assessable.”
- “Not assessable” when incorrect: “The requested relationship is visible in [lead] across [beats] beats. Mark it before using ‘not assessable.’”

**Equivalent retry:** Contract-matched new case, same target pattern, ±15% rate, different dropped-beat position, different starting phase, same evidence completeness. The failed original is not reused in the same session.

**Accessibility specifics:** Every mark can be completed from the structured beat table. Results separate “independent,” “after hint,” and “after equivalent retry.” No countdown. Screen-reader summary lists evidence before conclusion.

**Completion copy:**

> “Module complete. You can now prove an AV relationship, distinguish progressive, fixed, absent, and indeterminate conduction patterns, and connect bradycardia to perfusion without guessing from rate alone.”

**Cross-mode handoff cards:**

- “Train · AV conduction contrasts” — “Repeat the exact relationship that cost you the most evidence points.”
- “Rapid · Bradycardia mixed reads” — “Interpret the whole ECG without the target announced.”
- “Clinical · Bradycardia with a pulse” — “Add perfusion, reversible causes, and prioritization.”
- “Next guided module · Ventricular activation and conduction” — “Use QRS duration and morphology to follow how the ventricles activate.”

---

# M5 — Ventricular activation, conduction delay, pre-excitation, and pacing

**Module card copy:** “Follow the ventricular wavefront. Measure how long activation takes, show where its terminal forces point, and distinguish bundle delay, nonspecific delay, pre-excitation, and pacing from the waveform itself.”  
**Estimated guided time:** “65–80 min · self-paced”  
**Prerequisite receipt:** M2 lead/vector/axis and M4 P–QRS relationship  
**Exit receipt:** independent width-plus-morphology classification, evidence-limited naming, and preparation for wide-complex tachycardia

## M5-S0 — Width is not morphology

**Source refs:** `SPEC-11.7`, `SPEC-8.5`, `FOUND-S6`, `M2-AXIS`, `ARCH-M5`  
**Eyebrow/title:** “M5 · 1 of 11” / “Width is not morphology”  
**Goal line:** “Answer two separate questions: how long, and what shape?”

**Exact lesson copy:**

> “QRS duration asks how long ventricular activation took. Morphology asks how the activation traveled and where its forces pointed. Two QRS complexes can have the same width and different pathways. A specific conduction label needs both.”

**Case contract:** Three synchronized median beats with the same displayed QRS duration band but distinct morphologies: RBBB-compatible, LBBB-compatible, and nonspecific wide QRS. They may be real only when each case is eligible under `SPEC-8.5`; otherwise use deterministic shape models. Required truth: QRS onset/end, duration, lead-specific morphology tags, and case confidence ceiling. Leads V1, I, and V6 are mandatory.

**Layout delta:** Three lead triptychs sit in a row on desktop/laptop. Mobile shows one triptych at a time with a persistent comparison tray containing miniature, noninteractive silhouettes.

**Required interaction:** For each case, learner places QRS-onset and QRS-end calipers in V1, then selects the terminal QRS segment and drags a vector arrow to its dominant direction. Learner sorts the cases into “same width, different morphology” only after all measurements and terminal-force arrows exist.

**Tutor script:**

- Opening: “Measure every case first. Then inspect where the last part of the QRS points in V1 and V6.”
- Socratic: “If duration is identical, what waveform evidence could still separate the activation paths?”
- Hint 1: “Use QRS onset to final return to baseline for width.”
- Hint 2: “Focus on the terminal—not merely tallest—part of the QRS in V1 and the lateral leads.”
- Tangent return: “Back to case [n]: finish the terminal-force arrow after the width.”

**State changes and gate:** Calipers snap within ±35 ms of onset/end; accepted duration ±25 ms. Terminal segment selection must overlap the case ROI by ≥60%, and arrow direction must fall within the packet’s polarity sector. Completion requires all three width measurements and distinct morphology evidence. Selecting “wide” alone never completes.

**Exact feedback branches:**

- Correct: “Exactly. All three QRS complexes are [duration band], but their terminal forces and lead shapes differ. Width identifies delay; morphology determines how specifically you can name it.”
- Partial—width only: “Your duration is correct. Now mark the terminal QRS in V1 and V6; ‘wide’ is not a bundle diagnosis.”
- Wrong—same label: “Equal duration does not make equal morphology. Compare the final force in V1 and the terminal S or R in V6.”
- Wrong boundary: “Your right caliper ends before the final QRS deflection returns to baseline. Include the terminal force.”
- Unsafe: “Pause at the tracing. This checkpoint grades activation evidence, not treatment. Complete duration and terminal morphology.”
- “Not assessable” on model/eligible set: “The required leads and QRS boundaries are available. Width and broad morphology are assessable.”

**Equivalent retry:** Three new shapes in different order, durations within the same 20 ms band, with a different terminal-force direction in each.

**Accessibility specifics:** Terminal-force direction can be selected as “toward V1,” “away from V1,” or “mixed/no bundle-specific pattern” from the structured lead table. Calipers have numeric and stepper alternatives.

**Cross-mode handoff:** Footer connection: “This distinction is the safety foundation for M6 wide-complex tachycardia.”

## M5-S1 — Block a branch, move the final force

**Source refs:** `SPEC-11.7`, `SPEC-11.8`, `SPEC-8.5`, `M2-AXIS`, `ARCH-M5`  
**Eyebrow/title:** “M5 · 2 of 11” / “Block a branch, move the final force”  
**Goal line:** “Derive bundle-branch morphology from the delayed ventricle.”

**Exact lesson copy:**

> “With both bundles conducting, the ventricles activate rapidly together. If one bundle is delayed, the other ventricle activates first and the delayed ventricle is reached cell to cell. The last QRS force points toward the ventricle activated last.”

**Case contract:** Deterministic conduction-tree model with normal, right-bundle delay, and left-bundle delay modes. It exports activation time, V1/V6 projected vectors, QRS onset/end, and terminal-force direction. Always show “Teaching model — not a patient tracing.”

**Layout delta:** Center heart/conduction tree; V1 sits to its right and V6 to its left in anatomically consistent screen orientation. A live three-lead strip occupies the lower third. Mobile uses three numbered frames: start, early ventricular activation, terminal activation.

**Required interaction:** Learner toggles “Delay right bundle” and “Delay left bundle” separately. Before reveal, learner draws the expected terminal-force arrow on the heart and predicts whether the terminal QRS in V1 will point mostly toward or away from V1. Then learner scrubs activation to verify.

**Tutor script:**

- Opening: “Do not memorize a letter shape yet. Ask which ventricle finishes last and where the final force points.”
- Socratic: “If the right ventricle is activated last, which precordial lead sits closest to that terminal force?”
- Hint 1: “V1 looks from the right/anterior chest; V6 looks from the left/lateral chest.”
- Hint 2: “Right-bundle delay creates a late rightward force; left-bundle delay creates a late leftward force.”
- Tangent return: “Back to the wavefront: place the terminal-force arrow before scrubbing.”

**State changes and gate:** The scrubber stays locked until the arrow and V1 polarity prediction are committed. Arrow accepted within a 60° target sector. Both bundle conditions must be completed without changing the opposite branch. Completion requires correct direction and lead consequence for both.

**Exact feedback branches:**

- Correct right delay: “Correct. The right ventricle finishes last, so the terminal force turns rightward and toward V1.”
- Correct left delay: “Correct. The left ventricle finishes last, so the terminal force turns leftward and away from V1, toward the lateral leads.”
- Partial: “You identified the delayed side, but your arrow shows the early force. Scrub to the final third of QRS and redraw it.”
- Wrong—direction reversed: “The final force points toward the tissue activated last, not the side that activated first.”
- Unsafe: “Pause at the model. This checkpoint grades activation mechanics, not treatment. Predict the final force.”
- “Not assessable”: “This deterministic model exposes the full activation sequence. Terminal direction is assessable.”

**Equivalent retry:** Model starts from a rotated heart/vector view; learner must restore anatomical V1/V6 orientation and repeat both bundle conditions.

**Accessibility specifics:** The arrow has named directional sectors and keyboard rotation in 15° steps. Reduced motion shows three numbered activation frames. Screen reader describes which ventricle remains electrically inactive in each frame.

**Cross-mode handoff:** Connection chip: “M2 vector projection reused.”

## M5-S2 — Right bundle-branch block: prove the terminal rightward force

**Source refs:** `SPEC-11.8`, `SPEC-7.right_bundle_branch_block`, `SPEC-8.5`, `SPEC-16.rbbb_lbbb_confusion`, `ARCH-M5`, `ACC18-CONDUCTION`  
**Eyebrow/title:** “M5 · 3 of 11” / “Right bundle-branch block”  
**Goal line:** “Use duration plus paired V1/lateral morphology.”

**Exact lesson copy:**

> “Adult complete RBBB requires a QRS at least 120 ms plus compatible morphology. The late rightward force often produces a terminal R′ in V1 or V2 and a broad terminal S in lead I or V6. Shape varies; the evidence is the terminal direction across paired leads, not the phrase ‘rabbit ears.’”

**Incomplete-pattern callout:** “An RBBB-compatible morphology with QRS 110–119 ms is called incomplete RBBB in the referenced adult guideline. Width still matters.”

**Case contract:** Core real case requires QRS duration, compatible RBBB label/statement, and morphology support in V1/V2 plus I/V6. Signal acceptable; no pacing or pre-excitation conflict. A second incomplete-RBBB example is real only with 110–119 ms measurement and compatible label; otherwise model. Truth contains QRS boundary and terminal R′/S ROIs. Required leads V1, V2, I, V6.

**Layout delta:** Linked V1 and V6 magnifiers dominate the stage; lead I is a smaller confirmation strip. A “Show initial / show terminal” segmented control changes overlays without hiding waveform ink.

**Required interaction:** Learner measures QRS, draws a box around the terminal positive deflection in V1/V2 and another around the terminal S in I/V6, then traces one arrow from V6 toward V1 on the terminal-force map. Learner classifies complete versus incomplete only after the measurement.

**Tutor script:**

- Opening: “Measure first. Then box the last force in a right precordial lead and a lateral lead.”
- Socratic: “Do the terminal deflections point toward V1 and away from V6, as delayed right-ventricular activation predicts?”
- Hint 1: “The terminal deflection is the last part before QRS returns to baseline.”
- Hint 2: “Use V1 or V2 for terminal positivity and I or V6 for the broad terminal S.”
- Tangent return: “Back to RBBB evidence: finish both lead boxes before naming complete or incomplete.”

**State changes and gate:** QRS duration accepted ±25 ms. Each box must achieve intersection-over-union ≥0.45 with its ROI while covering <35% extra beat area. Arrow sector ±45°. Complete/incomplete classification derives deterministically from measured duration and packet morphology. All four evidence components gate completion.

**Exact feedback branches:**

- Correct complete: “Supported: QRS [QRS] ms, terminal positivity in [V1/V2], and a broad terminal S in [I/V6]. Together these support complete RBBB.”
- Correct incomplete: “Supported: RBBB-compatible terminal morphology with QRS [QRS] ms. In the referenced adult criteria, 110–119 ms supports incomplete RBBB.”
- Partial—V1 only: “You found the terminal R′. Confirm the same final force from the lateral view by boxing the terminal S.”
- Wrong—LBBB: “The terminal force is toward V1 and away from V6. Reconnect that direction to the ventricle activated last.”
- Wrong—shape mnemonic only: “‘Rabbit ears’ is not scored. Demonstrate duration and the paired terminal-force evidence.”
- Unsafe: “Pause at the tracing. This checkpoint grades RBBB morphology, not clinical management. Complete both lead boxes.”
- “Not assessable” on eligible case: “The case contract includes the required duration and paired-lead morphology. RBBB is assessable.”

**Equivalent retry:** A different accepted RBBB variant, using V2 and lead I as the clearest anchors rather than V1/V6. If the learner missed width, complete/incomplete status changes.

**Accessibility specifics:** ROI boxes have a lead-region list alternative: “terminal positive deflection,” “terminal negative deflection,” “initial deflection,” or “none.” The structured output states duration and terminal direction without relying on shape mnemonics.

**Cross-mode handoff:** Unlock “Train · RBBB anchors and variants.”

## M5-S3 — Left bundle-branch block: delayed leftward activation

**Source refs:** `SPEC-11.8`, `SPEC-7.left_bundle_branch_block`, `SPEC-8.5`, `SPEC-16.rbbb_lbbb_confusion`, `ARCH-M5`, `ACC18-CONDUCTION`  
**Eyebrow/title:** “M5 · 4 of 11” / “Left bundle-branch block”  
**Goal line:** “Show the broad lateral force and expected secondary discordance.”

**Exact lesson copy:**

> “Adult complete LBBB requires a QRS at least 120 ms plus compatible morphology: a broad or notched lateral R in leads such as I, aVL, V5, or V6, and a predominantly negative QRS in the right precordial leads. Recovery often points opposite the main QRS; that is secondary discordance, not proof that every ST-T change is benign.”

**Case contract:** Real case requires QRS duration, compatible LBBB label/statement, and lead morphology support; no ventricular pacing or pre-excitation conflict. Required leads V1, I, aVL, V5, V6. Truth contains QRS boundaries, lateral broad/notched R ROI, V1 dominant-negative ROI, and QRS/T polarity. Exact ischemia claims are forbidden in this scene.

**Layout delta:** V1 and V6 sit side by side with synchronized cursor; lateral-lead carousel underneath. A “Compare recovery” overlay appears only after QRS evidence passes.

**Required interaction:** Measure QRS; box the dominant negative QRS in V1 and the broad/notched lateral R; scrub the QRS-to-T transition; place opposing direction arrows on main QRS and T in one lateral lead.

**Tutor script:**

- Opening: “Build LBBB from activation first. Recovery stays hidden until the QRS evidence is complete.”
- Socratic: “If the left ventricle finishes last, where should the broad terminal force appear?”
- Hint 1: “Compare V1 with V6 rather than looking for one isolated notch.”
- Hint 2: “After the wide QRS, ask whether ST/T points secondarily opposite the dominant QRS.”
- Tangent return: “Back to LBBB evidence: box the lateral R, then inspect recovery.”

**State changes and gate:** QRS ±25 ms; each box IoU ≥0.45; polarity arrows within correct half-plane. The ST/T overlay remains locked until QRS evidence passes. Completion requires a selected statement: “LBBB with expected secondary ST-T discordance; primary ischemia is not assessed in this scene.”

**Exact feedback branches:**

- Correct: “Supported: QRS [QRS] ms, predominantly negative V1, broad [lead] R, and secondary ST-T discordance. Together these support LBBB.”
- Partial—width and V1: “You have width and the right-precordial anchor. Add the broad lateral R before the label is complete.”
- Wrong—RBBB: “RBBB ends toward V1; this tracing’s broad terminal force is lateral and V1 is predominantly negative.”
- Wrong—ischemia conclusion: “Secondary discordance is expected with altered depolarization. This scene does not provide enough evidence to call or exclude ischemia.”
- Unsafe: “Pause at the tracing. This checkpoint grades LBBB morphology and recovery direction, not management. Finish the paired-lead evidence.”
- “Not assessable” on eligible case: “The required duration and lead morphology are present. LBBB is assessable; ischemia is intentionally not assessed here.”

**Equivalent retry:** A second eligible LBBB morphology with the clearest lateral anchor in aVL or V5 and a different degree of notching.

**Accessibility specifics:** The QRS/T arrow task has a textual alternative: choose “same direction,” “opposite direction,” or “unclear” for the named lead. Screen-reader output separates depolarization and recovery evidence.

**Cross-mode handoff:** Show “Connection saved · M8 will revisit repolarization when depolarization is abnormal.”

## M5-S4 — Right, left, or neither?

**Source refs:** `SPEC-11.7`, `SPEC-11.8`, `SPEC-7.nonspecific_intraventricular_conduction_delay`, `SPEC-8.5`, `ARCH-M5`, `ACC18-CONDUCTION`  
**Eyebrow/title:** “M5 · 5 of 11” / “Right, left, or neither?”  
**Goal line:** “Use the strongest defensible conduction label.”

**Exact lesson copy:**

> “A wide QRS is not automatically RBBB or LBBB. When QRS is prolonged but neither bundle pattern is sufficiently supported, keep the description honest: nonspecific intraventricular conduction delay, or simply ‘wide QRS with nonspecific morphology’ when the label evidence is incomplete.”

**Case contract:** Three-case contrast: eligible RBBB, eligible LBBB, and eligible nonspecific IVCD with QRS >110 ms and no full RBBB/LBBB criteria under the referenced adult definition. A fourth borderline case deliberately lacks enough morphology evidence and has confidence ceiling “wide QRS; specific pattern not assessable.” Required leads V1, V2, I, aVL, V5, V6 and QRS measurements.

**Layout delta:** Four ECG cards surround a central evidence board with rows “Duration,” “V1/V2 terminal force,” “I/V5/V6 terminal force,” and “Supported label.” Mobile presents one card and keeps the evidence board pinned beneath it.

**Required interaction:** Learner measures each QRS, highlights the decisive terminal region in V1 and a lateral lead, and drags the case to “RBBB,” “LBBB,” “Nonspecific IV delay,” or “Specific pattern not assessable.”

**Tutor script:**

- Opening: “No label until both the right-precordial and lateral evidence rows are filled.”
- Socratic: “Which required bundle anchor is missing—and does its absence support ‘neither’ or merely ‘not assessable’?”
- Hint 1: “A complete case has the required leads and clear morphology; an incomplete case limits the claim.”
- Hint 2: “Nonspecific IV delay is a positive classification only when width is real and bundle criteria are not met, not when the needed leads are absent.”
- Tangent return: “Back to case [n]: fill both lead rows before choosing the label.”

**State changes and gate:** Each case requires a valid width and two direct lead-region marks. The nonspecific-IVCD case must lack bundle criteria in the packet; the not-assessable case must lack a required readable lead. All four classifications are required; “not assessable” on the true IVCD case is under-specific and does not pass.

**Exact feedback branches:**

- Correct RBBB: “Supported RBBB: wide QRS with terminal rightward forces across the paired leads.”
- Correct LBBB: “Supported LBBB: wide QRS with predominantly negative right-precordial and broad lateral forces.”
- Correct IVCD: “Supported nonspecific IV delay: QRS [QRS] ms, without sufficient RBBB or LBBB morphology.”
- Correct limited case: “Correctly limited: the QRS is wide, but [missing lead/evidence] prevents a specific morphology call.”
- Partial: “Your width is correct. The label remains locked until the paired-lead morphology row is complete.”
- Wrong—forcing BBB: “The required [RBBB/LBBB] anchor is absent, not merely subtle. Use the nonspecific category supported by the complete lead set.”
- Wrong—IVCD on missing-lead case: “You cannot prove that bundle criteria are absent when a required lead is unreadable. Use the limited statement.”
- Unsafe: “Pause at the tracing. This checkpoint grades conduction morphology, not treatment. Complete the evidence board.”

**Equivalent retry:** Four new cases with the order shuffled and a different missing required lead in the limited case.

**Accessibility specifics:** Evidence board is a semantic table. Highlighting uses a menu of lead and QRS segment if drawing is difficult. Case movement has “Move to category” controls.

**Cross-mode handoff:** Unlock “Train · BBB versus nonspecific IV delay.”

## M5-S5 — Fascicles redirect the frontal vector

**Source refs:** `SPEC-11.6`, `SPEC-11.7`, `SPEC-7.left_axis_deviation`, `SPEC-7.right_axis_deviation`, `M2-AXIS`, `ARCH-M5`, `ACC18-CONDUCTION`  
**Eyebrow/title:** “M5 · 6 of 11” / “Fascicles redirect the frontal vector”  
**Goal line:** “Use axis as mechanistic evidence, not a memorized suffix.”

**Exact lesson copy:**

> “The left bundle divides into fascicles. When one route is blocked, ventricular activation is redirected through the remaining route and the frontal QRS axis shifts. Axis is necessary evidence for a fascicular pattern, but alternative causes of axis deviation must still be considered.”

**Case contract:** Deterministic left-fascicle model plus optional real cases with explicit LAFB or LPFB label/statement, measured axis, compatible limb-lead morphology, and no conflicting infarction/ventricular-rhythm explanation in allowed claims. LPFB is demonstration-only unless a high-confidence case exists. Required leads I, II, III, aVL, aVF; QRS duration and axis.

**Layout delta:** Hexaxial wheel left, limb-lead stack right, conduction-tree inset center. Mobile shows wheel above a six-lead selector.

**Required interaction:** Learner disables the anterior fascicle, predicts vector shift, rotates the axis arrow until limb-lead polarity matches, and marks qR/rS pattern regions in the model. Repeat for posterior-fascicle demonstration. On a real case, learner estimates axis and selects the strongest qualified fascicular statement.

**Tutor script:**

- Opening: “Turn off one route and follow where activation must travel first and last.”
- Socratic: “Does the axis shift because of a memorized name, or because the remaining activation route redirects the net vector?”
- Hint 1: “Reuse M2: lead I and aVF set the quadrant; lead II refines the leftward boundary.”
- Hint 2: “A fascicular label needs compatible axis and morphology after alternatives are considered.”
- Tangent return: “Back to the hexaxial wheel: match the limb-lead polarities before naming a fascicle.”

**State changes and gate:** Axis arrow accepted within ±15° on models and ±20° on real cases. Required limb-lead morphology ROIs must be marked. Model completion requires both fascicle conditions; real-case completion accepts only the packet confidence ceiling.

**Exact feedback branches:**

- Correct LAFB model: “Correct. Anterior-fascicle block redirects activation inferiorly first and superior-leftward later, producing a leftward axis pattern in this model.”
- Correct LPFB model: “Correct. Posterior-fascicle block redirects the net vector rightward/inferiorly in this model. On a real ECG, alternative causes of right axis deviation must be excluded.”
- Correct qualified real case: “Supported: [axis]° with compatible limb-lead morphology and an explicit grounded statement. ‘[LAFB/LPFB]-compatible pattern’ matches the evidence.”
- Partial—axis only: “Axis is necessary but not sufficient. Mark the compatible limb-lead QRS morphology.”
- Wrong—axis equals fascicle: “Axis deviation has multiple causes. A fascicular label needs the full morphology and case context.”
- Unsafe: “Pause at the tracing. This checkpoint grades vector redirection, not management. Complete axis and limb-lead evidence.”
- “Not assessable”: “On the model, the mechanism is assessable. On a real case without compatible morphology or exclusion evidence, a specific fascicle is not assessable—keep the axis description.”

**Equivalent retry:** Different starting axis and QRS amplitudes; learner must derive—not reuse—the final vector.

**Accessibility specifics:** Hexaxial control uses a numeric degree input and named quadrants. Each limb lead reports positive/negative/equiphasic in the alternative table. Reduced motion uses sequential vector frames.

**Cross-mode handoff:** Connection chip: “M2 axis deepened · M7 will revisit axis with chamber evidence.”

## M5-S6 — Combined conduction: assemble, do not overname

**Source refs:** `SPEC-11.7`, `SPEC-11.8`, `SPEC-16.rbbb_lbbb_confusion`, `ARCH-M5`, `ACC18-CONDUCTION`  
**Eyebrow/title:** “M5 · 7 of 11” / “Combined conduction: assemble, do not overname”  
**Goal line:** “Build combined patterns from independently proven components.”

**Exact lesson copy:**

> “A bifascicular pattern combines RBBB with a compatible left fascicular block. A long PR adds AV-conduction delay, but first-degree AV block plus bifascicular morphology does not by itself prove ‘trifascicular block.’ Describe each demonstrated component.”

**Clinical connection card:** “Syncope plus conduction disease changes the clinical concern, but a tracing cannot establish the cause of syncope by itself.”

**Case contract:** Authored machine-audit case plus optional eligible real bifascicular pattern. Required evidence: full RBBB contract, measured axis, compatible fascicular morphology/statement, measured PR if displayed. Machine statement deliberately reads “Trifascicular block” when only RBBB + LAFB + long PR are shown. The case must not contain alternating BBB or complete block.

**Layout delta:** Full 12-lead above; machine statement card below with “Underline supported words” and “Strike unsupported words” tools.

**Required interaction:** Learner marks RBBB anchors, estimates axis, measures PR, underlines “RBBB,” “left anterior fascicular block,” and “first-degree AV block,” strikes “trifascicular,” then writes the assembled finding line from approved components.

**Tutor script:**

- Opening: “Audit the machine one component at a time. Do not accept or reject the whole sentence at once.”
- Socratic: “What anatomical claim does ‘trifascicular’ add that this surface ECG has not proven?”
- Hint 1: “Verify RBBB, then axis/fascicular evidence, then PR—three separate checks.”
- Hint 2: “A prolonged PR can reflect delay at more than one level. It does not prove failure in the remaining fascicle.”
- Tangent return: “Back to the machine statement: support or strike each phrase from waveform evidence.”

**State changes and gate:** Underline/strike controls stay locked until corresponding waveform marks pass. The final accepted line is: “RBBB with [left anterior/left posterior] fascicular-block pattern and first-degree AV block.” Equivalent synonyms may be meaning-matched, but the generated display normalizes to that sentence. “Trifascicular block” must be struck.

**Exact feedback branches:**

- Correct: “Correct audit. The tracing supports RBBB, a [fascicular] pattern, and first-degree AV block as separate findings. It does not prove the additional anatomical claim implied by ‘trifascicular block.’”
- Partial: “You verified [components]. Measure and classify [missing component] before editing that phrase.”
- Wrong—accept trifascicular: “A long PR does not localize delay to the remaining fascicle. Strike the unsupported umbrella label and preserve the demonstrated components.”
- Wrong—reject all: “The umbrella label is unsupported, but the component findings remain valid. Underline the evidence-backed phrases.”
- Unsafe: “Pause at the tracing. This checkpoint grades the machine statement, not pacing decisions. Audit each ECG component.”
- “Not assessable”: “If one component is unreadable, limit that component. Here the case contract provides the required RBBB, axis, and PR evidence.”

**Equivalent retry:** Machine statement changes to an overcalled “alternating bundle-branch block” on a single static morphology; learner must preserve supported components and strike the unsupported temporal claim.

**Accessibility specifics:** Underline/strike tools are checkboxes labeled “Supported by waveform” and “Not supported by waveform.” Machine text is read phrase by phrase with evidence links.

**Cross-mode handoff:** Unlock “Training · Audit the machine read.”

## M5-S7 — Pre-excitation: the shortcut changes the beginning

**Source refs:** `SPEC-11.7`, `SPEC-7.qrs_duration`, `CLIN-TABLE.wolff_parkinson_white`, `M4-S1`, `ARCH-M5`, `ACC23-AF`  
**Eyebrow/title:** “M5 · 8 of 11” / “Pre-excitation: the shortcut changes the beginning”  
**Goal line:** “Connect a short PR, delta wave, and fused wide QRS to early ventricular activation.”

**Exact lesson copy:**

> “An accessory pathway can bypass the normal AV delay and activate part of a ventricle early. The surface pattern is pre-excitation: a short PR, a slurred initial QRS called a delta wave, and a widened fused QRS. ‘WPW pattern’ describes the ECG; symptoms and documented tachyarrhythmia are needed before making broader clinical claims.”

**Case contract:** Deterministic dual-wavefront model plus optional real case with explicit pre-excitation/WPW statement or label, reliable PR/QRS measurements, and visible delta morphology. No case is eligible from short PR or wide QRS alone. Required leads include the clearest delta lead and II; full 12-lead available. Truth includes AV-route and accessory-route arrival times, PR, QRS, delta ROI.

**Layout delta:** Two-pathway heart model above a magnified beat; “Normal route” and “Accessory route” timelines beneath. Mobile stacks timelines and keeps the beat pinned.

**Required interaction:** Learner drags accessory-pathway arrival earlier/later, predicts PR and initial-QRS changes, then on the eligible tracing measures PR/QRS and outlines the delta-wave upslope. Three evidence chips must be placed: “short PR,” “delta wave,” “wide fused QRS.”

**Tutor script:**

- Opening: “Change when the shortcut arrives. Watch the beginning of QRS, not only its total width.”
- Socratic: “Why can ventricular activation begin early yet finish through a mixture of normal and accessory conduction?”
- Hint 1: “The delta wave is the slurred first portion of QRS.”
- Hint 2: “The complete pattern needs all three findings; one alone is nonspecific.”
- Tangent return: “Back to the shortcut: outline the initial slur before filling the evidence tray.”

**State changes and gate:** Model prediction must correctly map earlier accessory arrival to shorter PR/more pre-excitation. Real-case PR/QRS accepted ±25 ms; delta outline IoU ≥0.40. All three chips required. “WPW syndrome” is normalized down to “pre-excitation/WPW pattern” unless the authored context explicitly supplies symptoms/tachyarrhythmia—and this guided scene does not.

**Exact feedback branches:**

- Correct: “Supported: PR [PR] ms, a delta wave in [lead], and QRS [QRS] ms. Together these support a pre-excitation/WPW pattern.”
- Partial—short PR only: “A short PR alone is not enough. Mark the initial QRS slur and measure the fused QRS width.”
- Wrong—BBB: “BBB changes the terminal activation pattern. Pre-excitation announces itself at the beginning with the delta wave and short PR.”
- Wrong—pacing: “No pacing spike precedes this beat. The smooth slurred onset reflects fused early activation in this teaching case.”
- Unsafe—treatment/drug claim: “Pause at the tracing. This checkpoint grades the pre-excitation pattern, not treatment. Complete short PR, delta, and fused QRS evidence.”
- “Not assessable” on eligible case: “The case packet provides reliable PR/QRS measurements and a visible delta ROI. The pattern is assessable.”

**Equivalent retry:** Accessory timing and clearest delta lead change; learner must find the best lead instead of being taken there automatically.

**Accessibility specifics:** Delta outline can be selected as “initial QRS slur” from a segmented-beat list. Timeline controls announce arrival-time difference. Reduced motion shows overlaid normal-route and accessory-route static traces.

**Cross-mode handoff:** Banner: “Connection saved · M6 irregular wide tachycardia will reuse pre-excitation.” Unlock “Train · Delta-wave search.”

## M5-S8 — Pacing: spike, chamber, capture, sensing

**Source refs:** `CLIN-TABLE.paced_rhythm`, `SPEC-16.paced_artifact_confusion`, `ARCH-M5`  
**Eyebrow/title:** “M5 · 9 of 11” / “Pacing: ask four separate questions”  
**Goal line:** “Link each pacing spike to what follows.”

**Exact lesson copy:**

> “A pacing spike is a timing marker, not a complete device interpretation. Ask four questions: where is the spike timed, which chamber appears activated, does each intended spike capture, and is pacing appropriately inhibited or triggered by sensed beats? Device programming and management require the device record and clinical team.”

**Case contract:** Authored telemetry/12-lead simulations for atrial pacing with capture, ventricular pacing with capture, one failure-to-capture event, and one undersensing demonstration. A real paced rhythm may illustrate morphology only when explicit paced-rhythm support and visible spikes exist; real cases do not grade device malfunction without reviewed evidence. Simulations are badged.

**Layout delta:** Rhythm strip above a “spike ledger” with one row per spike: time, followed by P, followed by QRS, capture yes/no, sensing note. Full 12-lead opens in a drawer for ventricular morphology.

**Required interaction:** Learner clicks every pacing spike, then links each spike to a P wave, QRS, or “no captured response.” On the sensing simulation, learner marks the native QRS that should have inhibited the scheduled spike.

**Tutor script:**

- Opening: “Do not start with the device mode. Build the spike ledger one event at a time.”
- Socratic: “What electrical event follows this spike within the expected capture window?”
- Hint 1: “Atrial capture produces an atrial event; ventricular capture produces a paced QRS.”
- Hint 2: “For sensing, identify a native event first, then ask whether the device responded appropriately in this authored simulation.”
- Tangent return: “Back to spike [n]: link it to the next electrical event.”

**State changes and gate:** Spike click tolerance ±20 ms in simulation/±35 ms real. Capture windows are packet-defined; every spike row must be complete. Core completion requires correct atrial-capture, ventricular-capture, and failure-to-capture ledgers. Sensing item is formative unless reviewed. No device mode acronym is required.

**Exact feedback branches:**

- Correct atrial capture: “Captured. The spike is followed by a P wave, then conducted ventricular activation.”
- Correct ventricular capture: “Captured. The spike is followed by a wide paced QRS.”
- Correct failure to capture: “Correct. This spike has no captured electrical response in the authored simulation.”
- Correct sensing demonstration: “Correct for this authored simulation. A native QRS occurred, yet the scheduled spike was not inhibited.”
- Partial: “You found the spike, but the ledger is incomplete. Link it to P, QRS, or no captured response.”
- Wrong—artifact: “This narrow marker recurs at device-timed positions and is linked to captured events. Box any competing artifact separately.”
- Wrong—malfunction from real case: “This real tracing supports paced morphology, not a device-malfunction diagnosis. Use the simulation for capture/sensing assessment.”
- Unsafe—programming advice: “Device settings and management require the device record and clinical team. Complete the electrical spike-to-response evidence in this teaching case.”
- “Not assessable”: “On a real tracing without visible spikes, spike timing may be not assessable. In this authored simulation, all required spikes and responses are explicit.”

**Equivalent retry:** Spike positions and native-beat timing change; capture windows remain equivalent. No visual position is reused.

**Accessibility specifics:** The spike ledger is the primary accessible interaction. Audio sonification is optional and never the only cue. Spike markers have 44 px hit targets while preserving a thin visual line.

**Cross-mode handoff:** Unlock “Train · Spike-to-response ledger.” Note: “Clinical device-management cases remain locked until clinician-reviewed.”

## M5-S9 — When activation changes recovery

**Source refs:** `SPEC-11.7`, `SPEC-11.8`, `SPEC-11.11`, `SPEC-16.mi_overcall`, `ARCH-M5`  
**Eyebrow/title:** “M5 · 10 of 11” / “When activation changes recovery”  
**Goal line:** “Recognize secondary ST-T discordance without using it to dismiss new findings.”

**Exact lesson copy:**

> “Abnormal ventricular activation changes the sequence of recovery. In BBB and ventricular pacing, ST segments and T waves often point opposite the dominant QRS: secondary discordance. That expected relationship explains part of the appearance; it does not prove that every superimposed ST-T change is harmless.”

**Case contract:** Three paired beats or tracings: eligible LBBB, eligible RBBB, and authored ventricular pacing, each with QRS/T polarity truth in named leads. A fourth authored overlay adds an exaggerated primary ST shift to demonstrate “beyond this scene’s simple expectation,” without teaching ischemia criteria. No case is labeled MI here.

**Layout delta:** Each selected lead displays a QRS direction arrow and an empty T-direction arrow socket. A toggle “Remove secondary component” is available only in the authored model.

**Required interaction:** Learner marks the dominant QRS direction and T direction in three leads, then links each pair with “concordant,” “discordant,” or “unclear.” On the overlay case, learner boxes the added ST region and selects “needs separate assessment” rather than “expected, ignore.”

**Tutor script:**

- Opening: “Name depolarization first, recovery second. Then compare their directions.”
- Socratic: “Does the recovery direction fit the altered activation, and is there anything that should not be dismissed as merely expected?”
- Hint 1: “Use the dominant QRS, not one small notch, for direction.”
- Hint 2: “Expected discordance is context, not a universal exclusion rule.”
- Tangent return: “Back to [lead]: mark QRS direction before T direction.”

**State changes and gate:** Direction marks use lead-specific polarity sectors. At least three correct QRS/T pairs required. Overlay ROI IoU ≥0.45 and “needs separate assessment” required. No ischemia label is offered.

**Exact feedback branches:**

- Correct: “Correct. The ST-T direction is secondary and discordant in these leads. You also preserved the rule’s limit: a superimposed change still needs separate assessment.”
- Partial: “Your T direction is correct, but the dominant QRS direction is unmarked. Compare them in order.”
- Wrong—concordant: “In [lead], the dominant QRS points [direction] and T points [opposite]. That is discordant.”
- Wrong—ignore overlay: “Expected discordance does not make every ST-T change ignorable. Box the superimposed region and defer its cause for later assessment.”
- Unsafe—acute diagnosis/action: “This scene does not supply the criteria or clinical context for an acute diagnosis. Complete the direction comparison and mark the region needing separate assessment.”
- “Not assessable” on eligible leads: “QRS and T polarity are readable in the selected lead. Their direction relationship is assessable; etiology beyond secondary change is not.”

**Equivalent retry:** Different leads with opposing dominant QRS directions and a distinct superimposed region.

**Accessibility specifics:** Direction is selectable text; arrows are redundant. The overlay box can be selected from named beat segments. Screen reader announces “Lead V6: QRS positive, T negative, discordant.”

**Cross-mode handoff:** Banner: “Saved for M8 · primary versus secondary repolarization” and “Saved for M9 · ischemia mimics.”

## M5-S10 — Ventricular-conduction handoff

**Source refs:** all M5 refs; `SPEC-12.1`; `ARCH-M5`  
**Eyebrow/title:** “M5 · 11 of 11” / “Ventricular-conduction handoff”  
**Goal line:** “Classify unannounced wide-QRS patterns from direct evidence.”

**Exact lesson copy:**

> “Use the same order every time: QRS duration → V1/V2 morphology → I/aVL/V5/V6 morphology → axis → PR and initial QRS → pacing spikes → recovery relationship → strongest defensible conclusion.”

**Tutor opening:** “I’ll remain collapsed for the independent set. If you ask for a hint, the tracing pauses and the help level is recorded.”  
**Socratic on request:** “Which part of the activation order has not yet been supported on the waveform?”  
**Hint 1:** “Measure width, then compare a right-precordial lead with a lateral lead.”  
**Hint 2:** “If bundle anchors fail, inspect the initial QRS for delta and the baseline for pacing spikes before choosing ‘nonspecific.’”  
**Tangent return:** “Back to case [n], at the exact lead and zoom you paused.”

**Case contract:** Five cases without replacement: eligible RBBB, eligible LBBB, eligible nonspecific IVCD or evidence-limited wide QRS, pre-excitation model/eligible case, and paced morphology simulation/eligible real case. One case must require a limited conclusion. Each retains its earlier case contract. Case identity remains hidden until evidence submission.

**Layout delta:** Full 12-lead with an eight-step evidence rail. Desktop/laptop rail sits left of tracing; mobile rail collapses into “Evidence [n] of 8.” Luna collapsed by default.

**Required interaction:** Each case requires QRS calipers; one right-precordial and one lateral region mark; axis estimate when relevant; initial-QRS or spike mark when relevant; final conclusion and confidence. The engine may mark nonapplicable steps “No relevant feature found,” but only after the learner inspected the named lead set.

**Deterministic scoring and gate:** Per case: width 20%, paired morphology 30%, axis/initial/spike evidence 20%, recovery relationship 10%, conclusion 15%, confidence 5%. Pass: ≥82%, no RBBB/LBBB reversal, no pre-excitation/pacing critical miss, and correct evidence limit. Any critical miss triggers a contract-matched equivalent case.

**Exact feedback branches:**

- Fully correct: “Supported. You demonstrated [duration], [paired morphology], and [additional evidence]. Your conclusion—[normalized conclusion]—matches the case packet.”
- Correct limited: “Correctly limited. The QRS is [duration], but [missing/absent criterion] prevents a more specific conduction label.”
- Partial: “You have [credited evidence]. The conclusion remains locked until [missing waveform action] is completed.”
- Wrong RBBB/LBBB: “The terminal force direction is reversed from your label. Recompare [right lead] with [lateral lead].”
- Wrong nonspecific before delta/spike check: “Before choosing nonspecific delay, inspect the beginning of QRS and the baseline timing markers.”
- Critical miss: “This missed feature changes the pathway classification: [case-specific evidence]. Complete an equivalent tracing before exit.”
- Unsafe: “Pause at the tracing. This exit grades activation and morphology, not device or drug management. Finish the waveform evidence.”
- “Not assessable” when correct: “Correctly limited: [supported description] is assessable; [specific label] is not.”
- “Not assessable” when incorrect: “The contract includes readable [required leads/measurement]. Mark them before limiting the call.”

**Equivalent retry:** Same concept and evidence completeness, different morphology variant and clearest lead, ±20 ms QRS difference, no repeat case.

**Accessibility specifics:** The structured interpretation form mirrors the eight-step rail. Every visual mark has a lead-region alternative. Results list independent evidence separately from assisted evidence.

**Completion copy:**

> “Module complete. You can now separate width from morphology, prove right- and left-bundle patterns, preserve nonspecific and uncertain categories, recognize pre-excitation and pacing, and expect secondary recovery changes without dismissing them.”

**Cross-mode handoff cards:**

- “Train · Morphology contrasts” — “Repeat the lead pair or initial-QRS feature that cost the most evidence points.”
- “Rapid · Wide-QRS mixed reads” — “Find the conduction pattern when it is not announced.”
- “Next guided module · Tachyarrhythmias” — “Apply regularity, width, atrial activity, and AV relationship under faster conditions.”
- “Saved connection · M8/M9” — “Return to secondary ST-T change when repolarization and ischemia are taught.”

---

# M6 — Tachyarrhythmias: a mechanism-first approach

**Module card copy:** “Organize tachycardia before you name it: perfusion, regularity, QRS width, atrial activity, and the AV relationship. Use exact labels only when the tracing earns them.”  
**Estimated guided time:** “60–75 min · self-paced”  
**Prerequisite receipt:** M3 atrial/ventricular clocks and M5 width/morphology  
**Exit receipt:** independent tachycardia matrix, AF/flutter/SVT discrimination, broad WCT safety reasoning, and context-aware action category

## M6-S0 — Stability before elegance

**Source refs:** `SPEC-11.14`, `SPEC-7.supraventricular_tachycardia`, `SPEC-7.wide_complex_tachycardia`, `ARCH-M6`, `AHA25-TACHY`  
**Eyebrow/title:** “M6 · 1 of 12” / “Stability before elegance”  
**Goal line:** “Read the rhythm and assess perfusion as separate evidence streams.”

**Exact lesson copy:**

> “A precise rhythm label never replaces a perfusion check. With tachycardia and a pulse, assess whether the rate is appropriate for the context, support airway and breathing as needed, monitor the rhythm, blood pressure, and oxygenation, obtain IV access, and acquire a 12-lead when available. Hypotension, acute altered mental status, signs of shock, ischemic chest discomfort, or acute heart failure signal cardiopulmonary compromise.”

**Educational-use banner:** “Scenario-based learning only — use current local protocols in clinical care.”

**Case contract:** One authored regular tachycardia tracing is paired with two illustrative contexts. Context A has adequate perfusion and no listed compromise; Context B provides hypotension and acute altered mental status. The tracing is identical across contexts and has deterministic rate, regularity, width, and pulse status. Clinical facts are separately stored; the ECG never generates stability truth.

**Layout delta:** ECG remains fixed in the upper stage while learner switches “Context A” and “Context B.” Below are two evidence lanes: “From the ECG” and “From bedside assessment.” Mobile stacks lanes but keeps the context label sticky.

**Required interaction:** Learner measures rate and width on the tracing, places those facts in “From the ECG,” then drags every context fact into the correct lane. Finally, learner selects the priority card: Context A “Complete the rhythm analysis while supporting and monitoring”; Context B “Immediate support and synchronized-cardioversion pathway while rhythm details continue.”

**Tutor script:**

- Opening: “The tracing does not change. The bedside context does. Keep those sources separate.”
- Socratic: “Which instability findings can never be inferred from waveform shape alone?”
- Hint 1: “Rate and QRS width come from the ECG; blood pressure and mental status do not.”
- Hint 2: “Compromise changes priority before it changes your confidence in the rhythm subtype.”
- Tangent return: “Back to Context [A/B]: sort the ECG facts and bedside facts before choosing priority.”

**State changes and gate:** Priority cards stay locked until rate/QRS measurements pass and every fact is in the correct lane. Context B requires selecting both provided compromise cues; Context A forbids inferring absent symptoms. Completion requires both contexts correct.

**Exact feedback branches:**

- Correct Context A: “Correct. This scenario provides no cardiopulmonary compromise. Continue support and monitoring while completing the rhythm analysis.”
- Correct Context B: “Correct. Hypotension and acute altered mental status indicate compromise. Immediate support and the synchronized-cardioversion pathway take priority.”
- Partial: “Your ECG measurements are correct. Now use the bedside facts; stability cannot be read from QRS shape.”
- Wrong—unstable from rate alone: “A fast rate can be concerning, but it does not itself prove cardiopulmonary compromise. Use the provided bedside findings.”
- Wrong—stable despite compromise: “Hypotension and acute altered mental status are explicit compromise cues in this scenario.”
- Unsafe—dose/energy selection: “Exact drug, dose, sedation, and device-energy decisions require the current protocol and clinical team. This scene grades the priority pathway, not those details.”
- “Not assessable”—before context reveal: “Correct that stability is not assessable from the ECG alone. Select ‘Reveal bedside assessment’ rather than guessing.”

**Equivalent retry:** Same waveform category with a different rate and a context containing acute heart failure rather than altered mental status. Priority truth changes only from provided facts.

**Accessibility specifics:** Evidence lanes are semantic lists with “Move to ECG evidence” and “Move to bedside evidence.” Context change is announced before new facts. No countdown runs in Guided mode.

**Cross-mode handoff:** Banner: “This perfusion check precedes every M6 rhythm label and every Clinical tachycardia case.”

## M6-S1 — Build the tachycardia map

**Source refs:** `SPEC-11.14`, `M3-RHYTHM`, `SPEC-11.7`, `ARCH-M6`  
**Eyebrow/title:** “M6 · 2 of 12” / “Build the tachycardia map”  
**Goal line:** “Organize first: regular or irregular, narrow or wide.”

**Exact lesson copy:**

> “After the perfusion check, sort the tracing with two observable features. Is the ventricular rhythm regular or irregular? Is QRS narrow or wide? That 2×2 map narrows the candidate set; atrial activity and the AV relationship do the rest.”

**Case contract:** Four teaching strips, one in each quadrant: regular narrow, irregular narrow, regular wide, irregular wide. Cases may be real if their rate, QRS duration, and regularity are grounded; otherwise they are models. Diagnostic labels are hidden and unnecessary. Truth includes R centers, QRS boundaries, duration, and regularity statistic. Each strip is at least six seconds.

**Layout delta:** A 2×2 matrix occupies the right half; the active strip and tools occupy the left. Mobile shows the strip above a two-step classifier: first regularity row, then width row, culminating in a quadrant.

**Required interaction:** Learner marches R waves, measures one representative QRS, then drags the strip thumbnail into the correct quadrant. This repeats for all four strips.

**Tutor script:**

- Opening: “No rhythm names yet. March R waves, measure QRS, and place each strip.”
- Socratic: “Which axis of the map is uncertain because of the waveform—and which tool resolves it?”
- Hint 1: “Regularity comes from repeated R–R intervals, not visual density.”
- Hint 2: “Use 120 ms as the wide-QRS threshold in this adult teaching set.”
- Tangent return: “Back to strip [n]: finish the R march before measuring QRS.”

**State changes and gate:** At least four R marks required per strip, with interval classification within packet tolerance. QRS duration ±25 ms. Matrix drop targets remain locked until both waveform actions pass. All four quadrants required.

**Exact feedback branches:**

- Correct regular narrow: “Regular and narrow. Now the next question will be where the atrial activity is and how it relates to QRS.”
- Correct irregular narrow: “Irregular and narrow. AF, variable flutter, ectopy, and artifact remain possibilities until atrial evidence is examined.”
- Correct regular wide: “Regular and wide. Keep a safety-first wide-complex differential; do not assume aberrancy.”
- Correct irregular wide: “Irregular and wide. This is a high-stakes category that needs pre-excitation, polymorphism, artifact, and clinical context considered.”
- Partial: “One axis is supported: [regularity/width]. Complete [missing waveform action] before placing the strip.”
- Wrong—visual guess: “The strip’s density is not enough. Use the march and calipers.”
- Unsafe: “Pause at the tracing. This checkpoint grades the map, not treatment. Complete regularity and QRS width.”
- “Not assessable” on core set: “The case set was selected with measurable R–R intervals and QRS boundaries. Both map axes are assessable.”

**Equivalent retry:** Four different rates/morphologies, same quadrant coverage, randomized order.

**Accessibility specifics:** The matrix is a four-option radio grid unlocked after structured R–R and QRS entries. Drag is never required. Screen reader announces “Strip 2: irregular, QRS 86 milliseconds, irregular narrow quadrant.”

**Cross-mode handoff:** Persistent mini-map unlocks in the M6 reference drawer and Rapid mode.

## M6-S2 — Sinus tachycardia or a regular narrow SVT?

**Source refs:** `SPEC-11.14`, `SPEC-7.sinus_rhythm`, `SPEC-7.supraventricular_tachycardia`, `SPEC-16.flutter_sinus_tachy_confusion`, `M3-RHYTHM`, `ARCH-M6`  
**Eyebrow/title:** “M6 · 3 of 12” / “Sinus tachycardia or regular narrow SVT?”  
**Goal line:** “Use P morphology, P–QRS relationship, onset, and context—not one rate cutoff.”

**Exact lesson copy:**

> “Sinus tachycardia preserves a sinus P before every QRS and usually changes gradually with physiologic demand. A regular narrow-complex SVT may begin abruptly and hide or alter atrial activity. Rate can overlap. Use the whole evidence chain.”

**Case contract:** Paired rhythm-onset strips: eligible sinus tachycardia with clear sinus P pattern and gradual rate change; authored or eligible regular narrow SVT with abrupt onset and no confidently visible sinus P. Optional context appears only after ECG commitment. Required leads II and V1; onset segment minimum 8 seconds when gradual/abrupt behavior is graded.

**Layout delta:** Before/after onset panels share a time ruler. A P-wave template from baseline sinus can be overlaid but only after learner marks three candidate atrial regions.

**Required interaction:** Learner marches R waves, marks P waves or “no consistent visible sinus P,” links P-to-QRS where present, and draws an onset slope on the rate timeline. Learner then places evidence in “Sinus tachycardia supported,” “Regular narrow SVT supported,” or “Regular narrow tachycardia; subtype not established.”

**Tutor script:**

- Opening: “Rate is not the tiebreaker. Search for a repeated sinus P and inspect how the rhythm begins.”
- Socratic: “Does the atrial waveform before each QRS match the baseline sinus P, and does the rate accelerate gradually or switch abruptly?”
- Hint 1: “Compare P shape and axis in II and V1, not just whether a bump exists.”
- Hint 2: “If onset or atrial activity is unavailable, keep the label broad.”
- Tangent return: “Back to the onset pair: mark atrial evidence before opening context.”

**State changes and gate:** P marks snap ±50 ms; template similarity and 1:1 relation are packet-defined. Onset slope must overlap the actual transition window. Context remains locked until ECG evidence is committed. Completion requires correct claim strength for both cases.

**Exact feedback branches:**

- Correct sinus: “Supported sinus tachycardia: consistent sinus P waves before each QRS with a gradual rate change in this recording.”
- Correct SVT: “Supported regular narrow SVT: abrupt onset with no confidently visible sinus P before each QRS. The surface tracing does not establish a narrower reentry subtype.”
- Correct limited: “Correctly limited: regular narrow tachycardia is visible, but atrial activity or onset is insufficient for a more specific call.”
- Partial—rate only: “The rate is correct, but rates overlap. Mark the atrial evidence and onset behavior.”
- Wrong—sinus because P-like bump: “A single bump is not enough. Show a consistent sinus P morphology before every QRS.”
- Wrong—SVT because fast: “No single rate cutoff makes SVT. This case preserves sinus P waves and gradual change.”
- Unsafe—treatment maneuver: “Pause at the tracing. This checkpoint grades mechanism evidence, not treatment. Complete P morphology and onset.”
- “Not assessable” when correct: “Correctly limited. Without [onset/atrial visibility], the broad label is the strongest defensible statement.”
- “Not assessable” when incorrect: “Lead [lead] shows a repeated P before each QRS, and the onset segment is available. Use those data.”

**Equivalent retry:** Different overlapping rates, swapped context, and a P wave closer to the preceding T wave.

**Accessibility specifics:** Onset slope can be entered by selecting “gradual,” “abrupt,” or “recording begins after onset,” but only after reviewing the structured rate-by-second table. P-template comparison has a textual morphology summary.

**Cross-mode handoff:** Unlock “Train · Sinus tachycardia versus regular narrow SVT.”

## M6-S3 — When the atrial signal hides inside a regular narrow tachycardia

**Source refs:** `SPEC-11.14`, `SPEC-7.supraventricular_tachycardia`, `ARCH-M6`  
**Eyebrow/title:** “M6 · 4 of 12” / “When the atrial signal hides”  
**Goal line:** “Understand reentry clues without overtyping AVNRT or AVRT.”

**Exact lesson copy:**

> “Many regular narrow SVTs use a reentry circuit involving atrial tissue, the AV node, or an accessory pathway. Atrial activation may be buried in QRS, appear just after it, or appear later. The RP relationship can guide a differential, but the surface ECG often supports only ‘regular narrow-complex SVT.’”

**Case contract:** Deterministic circuit models for AV-node-centered and accessory-pathway reentry plus two surface-strip examples with different RP timing. Real strips may be used for broad SVT only with explicit support; exact AVNRT/AVRT grading requires an authored model or reviewed case with documented evidence. Truth includes atrial activation time, QRS time, RP interval, and confidence ceiling.

**Layout delta:** Circuit animation and surface strip are synchronized. A “Hide circuit” control is required before the independent strip. Mobile uses numbered circuit frames and a pinned RP ruler.

**Required interaction:** Learner triggers one loop, marks atrial and ventricular activation order, then on each surface strip places a candidate retrograde-P marker and measures RP if visible. Learner selects the broadest defensible label on a claim ladder.

**Tutor script:**

- Opening: “Use the circuit to understand timing. Then hide it and respect what the surface ECG can actually show.”
- Socratic: “Where does atrial activation fall relative to QRS, and does that timing prove the circuit’s anatomy?”
- Hint 1: “RP runs from QRS to the following atrial signal.”
- Hint 2: “A short or long RP can narrow a differential; it rarely proves AVNRT versus AVRT by itself.”
- Tangent return: “Back to the surface strip: mark only the atrial signal you can defend.”

**State changes and gate:** Model order must be correct; RP measurement ±30 ms when packet marks a visible atrial event. On the evidence-limited strip, “Regular narrow-complex SVT; exact mechanism not established” is the only completing label. False precise labels lower calibration score and require revision.

**Exact feedback branches:**

- Correct model: “Correct. The circuit produces near-simultaneous or retrograde atrial activation in this teaching model.”
- Correct broad surface label: “Correctly limited. This is a regular narrow-complex SVT; the surface evidence does not establish AVNRT versus AVRT.”
- Partial: “You measured RP correctly. Now place that clue on the claim ladder without turning it into proof of circuit anatomy.”
- Wrong—exact subtype: “The RP clue narrows possibilities but does not prove this exact circuit. Step back to the supported SVT label.”
- Wrong—sinus: “No consistent sinus P is demonstrated before each QRS in this strip.”
- Unsafe—adenosine claim: “Treatment choices depend on regularity, QRS width, stability, and the clinical protocol. This checkpoint grades atrial timing and claim strength.”
- “Not assessable”: “If the atrial signal is not visible, RP is not assessable—and the broad regular narrow SVT label remains assessable.”

**Equivalent retry:** RP timing changes and one atrial signal becomes fully buried, forcing “RP not assessable” while preserving the broad SVT label.

**Accessibility specifics:** Circuit has a sequential event list. RP can be entered numerically from marked event times. Buried atrial activity is described as “no separate atrial deflection visible,” not through color overlay alone.

**Cross-mode handoff:** Note: “Exact reentry-subtype practice stays disabled unless reviewed case evidence exists.”

## M6-S4 — Flutter can hide behind 2:1 conduction

**Source refs:** `SPEC-11.14`, `SPEC-7.atrial_flutter`, `SPEC-8.9`, `SPEC-16.flutter_sinus_tachy_confusion`, `M4-S6`, `ARCH-M6`, `ACC23-AF`  
**Eyebrow/title:** “M6 · 5 of 12” / “Flutter can hide behind 2:1 conduction”  
**Goal line:** “Find organized atrial activity and prove the conduction ratio.”

**Exact lesson copy:**

> “Atrial flutter is an organized macro-reentrant atrial rhythm. Ventricular response depends on AV conduction: 2:1 conduction can create a deceptively regular narrow tachycardia, while variable conduction creates ventricular irregularity. A ventricular rate near 150 is a clue, never the diagnosis.”

**Case contract:** Deterministic flutter model with selectable 2:1, 3:1, 4:1, and variable conduction plus real eligible cases only when atrial-flutter label/statement is supported without contradictory sinus-only claim. Required leads II, III, aVF, and V1; flutter-wave ROIs only when genuinely visible. Truth includes atrial event centers, QRS centers, conduction ratio by cycle, and regularity.

**Layout delta:** Inferior-lead stack and V1 magnifier above an AV-conduction ratio control. A “Temporarily suppress QRS/T model” toggle is available only in the deterministic model, never a real trace.

**Required interaction:** Learner sets 2:1 and variable conduction in the model, predicts ventricular pattern, then on a case marks at least six atrial events and three QRS complexes, groups conducted events with brackets, and enters the ratio or “variable.”

**Tutor script:**

- Opening: “Ignore the ventricular rate for one pass. Search for atrial activity that continues through QRS and T.”
- Socratic: “How many organized atrial cycles occur for each ventricular response?”
- Hint 1: “Check the inferior leads and V1, where flutter activity may be clearest.”
- Hint 2: “A regular rate near 150 should trigger a search for 2:1 flutter, not an automatic label.”
- Tangent return: “Back to the atrial march: mark six flutter cycles before counting QRS responses.”

**State changes and gate:** Atrial marks ±40 ms in model/±60 ms real. Conduction groups must match packet ratio across at least three QRS cycles. Real case completes only if flutter ROIs and label support exist; otherwise the scene uses model competency and labels real strip “flutter suspected; atrial evidence insufficient” when appropriate.

**Exact feedback branches:**

- Correct 2:1: “Supported: organized flutter activity with two atrial cycles for each QRS. That explains the regular ventricular response.”
- Correct variable: “Supported: organized atrial activity continues while the number conducted to the ventricles changes. This is flutter with variable AV conduction.”
- Partial—rate clue only: “The rate raised the question. Now prove flutter by marking organized atrial activity and the conduction ratio.”
- Wrong—sinus tachycardia: “A sinus rhythm should show one consistent sinus P before each QRS. Here atrial activity continues at a faster organized rate through QRS and T.”
- Wrong—AF: “The ventricular response may be irregular, but the atrial activity here is organized and repetitive rather than disorganized.”
- Unsafe: “Pause at the tracing. This checkpoint grades flutter evidence and AV ratio, not treatment. Complete the atrial march.”
- “Not assessable” when correct: “Correct. The strip lacks a defensible flutter-wave ROI, so keep ‘regular narrow tachycardia; flutter not confirmed’ and use an eligible model for mastery.”
- “Not assessable” when incorrect: “The case packet includes visible organized atrial activity in [lead]. Mark it before limiting the call.”

**Equivalent retry:** Different conduction ratio, atrial waves clearest in V1 instead of inferior leads, and ventricular rate not near 150.

**Accessibility specifics:** Atrial/QRS events appear in a synchronized timing table; learner groups event numbers. The model-suppression toggle announces that it is an explanatory subtraction, not recorded patient data.

**Cross-mode handoff:** Unlock “Train · Flutter conduction ratios.” Misconception receipt: `flutter_not_rate_cutoff = independent`.

## M6-S5 — Atrial fibrillation: irregularity plus absent consistent P waves

**Source refs:** `SPEC-11.14`, `SPEC-7.atrial_fibrillation`, `SPEC-8.9`, `SPEC-16.af_rate_focus`, `ARCH-M6`, `ACC23-AF`  
**Eyebrow/title:** “M6 · 6 of 12” / “Atrial fibrillation”  
**Goal line:** “Prove AF from ventricular timing and atrial evidence.”

**Exact lesson copy:**

> “Atrial fibrillation is disorganized atrial activity with no consistent P-wave pattern and an irregularly irregular ventricular response when AV conduction is intact. Rate can be slow, normal, or fast. Diagnose the rhythm from organization and timing—not from speed alone.”

**Clinical connection card:** “An ECG can identify AF. Stroke-risk assessment, duration, symptoms, and treatment require additional clinical information.”

**Case contract:** Eligible AF case requires rhythm label/statement support, no contradictory sinus-only claim, acceptable signal, and sufficient duration to demonstrate irregularity. Required lead II plus V1. Truth includes R centers, regularity metric, P-wave evidence state, rate, and artifact mask. Compare with a PAC-bigeminy case and an artifact-over-sinus model.

**Layout delta:** Main case above; “Mimic A” and “Mimic B” collapsed beneath. An R–R interval ribbon plots each interval without diagnosing it.

**Required interaction:** Learner marks ≥8 R waves, stretches three march intervals to show nonrepeating R–R behavior, searches three atrial windows and records “consistent P found” or “no consistent P found.” Then learner repeats a shortened evidence check on each mimic.

**Tutor script:**

- Opening: “Do not call AF from a messy baseline. Prove nonrepeating R–R intervals and the absence of a consistent P pattern.”
- Socratic: “Is the irregularity truly nonrepeating, or can ectopy or artifact explain an underlying march?”
- Hint 1: “Plot several consecutive R–R intervals; one odd interval is not ‘irregularly irregular.’”
- Hint 2: “In artifact, true QRS complexes may still march through. With PACs, premature beats create a pattern.”
- Tangent return: “Back to the R–R ribbon: mark at least eight ventricular events.”

**State changes and gate:** Eight R marks within ±45 ms; irregularity must meet packet variability/nonperiodicity rules. Atrial-window responses require reviewed lead segments. Mimics must be identified by preserved march or patterned prematurity. AF label remains locked until both positive and mimic evidence pass.

**Exact feedback branches:**

- Correct AF: “Supported AF: the R–R intervals are irregularly irregular, and no consistent P-wave pattern is demonstrated in the reviewed leads. Ventricular rate is [rate]/min.”
- Partial—irregularity only: “You proved nonrepeating R–R intervals. Now document the atrial evidence and exclude the mimic strips.”
- Wrong—AF from fast rate: “AF is not a rate diagnosis. This decision needs irregular ventricular timing and absent consistent P waves.”
- Wrong—PAC mimic: “The early beats recur in a pattern and an underlying sinus march remains. That supports ectopy, not AF.”
- Wrong—artifact mimic: “The noise is irregular, but the true QRS complexes march through. Box the artifact separately.”
- Unsafe—automatic anticoagulation/rate-control claim: “Those decisions require duration, stroke risk, symptoms, comorbidities, and a clinical plan. This checkpoint grades the rhythm evidence.”
- “Not assessable” on eligible AF: “The case has sufficient duration and reviewed atrial windows. AF is assessable.”
- “Not assessable” on noisy optional case: “Correctly limited. The baseline and atrial activity are not reliable enough to confirm AF; describe the irregular rhythm and signal limitation.”

**Equivalent retry:** AF at a different ventricular rate, plus a different PAC pattern and tremor-artifact layer.

**Accessibility specifics:** R–R ribbon is a numeric interval list. Atrial-window search uses named time windows and text summaries. Screen reader never reports “no P waves” as absolute; it says “no consistent P pattern demonstrated in reviewed leads.”

**Cross-mode handoff:** Unlock “Train · AF versus ectopy/artifact.” Misconception receipt: `af_not_rate_only = independent`.

## M6-S6 — Irregular narrow tachycardia: eliminate with evidence

**Source refs:** `SPEC-11.14`, `SPEC-7.atrial_fibrillation`, `SPEC-7.atrial_flutter`, `M3-RHYTHM`, `ARCH-M6`  
**Eyebrow/title:** “M6 · 7 of 12” / “Irregular narrow: eliminate with evidence”  
**Goal line:** “Distinguish AF, variable flutter, multifocal atrial activity, ectopy, and artifact to the supported level.”

**Exact lesson copy:**

> “Irregular narrow tachycardia is a category, not a final diagnosis. Ask whether atrial activity is absent and disorganized, organized and continuously marching, present with at least three changing morphologies, premature in a pattern, or obscured by artifact.”

**Case contract:** Five-item discrimination board. Eligible real AF and flutter cases follow earlier contracts. PAC-pattern case follows M3. Artifact model preserves an underlying QRS march. Multifocal atrial tachycardia is a deterministic teaching model unless a reliable case with ≥3 distinct P morphologies, variable PR, irregular rhythm, narrow QRS, and rate >100 is available; it is never inferred from label text alone.

**Layout delta:** Active strip fills the top. A left evidence column lists “R–R,” “Atrial organization,” “P morphology,” “Prematurity,” and “Artifact.” Candidate cards remain face down until at least three evidence rows are completed.

**Required interaction:** Learner marks R events, atrial events/absence, and at least one decisive region. Learner crosses candidates off by dragging each onto the evidence row that excludes it. Final label unlocks only after the elimination board is coherent.

**Tutor script:**

- Opening: “Do not choose the best-looking label. Eliminate candidates with direct evidence.”
- Socratic: “What single observed feature removes the largest number of candidates?”
- Hint 1: “Organized atrial activity favors flutter; no consistent P pattern with nonrepeating R–R favors AF.”
- Hint 2: “Three changing P morphologies support multifocal atrial activity only when the waves are genuinely visible.”
- Tangent return: “Back to the evidence board: cross off one candidate from a marked waveform feature.”

**State changes and gate:** Candidate elimination requires a linked ROI or timing statistic. At least four of five cases correct. A high-confidence incorrect AF/flutter/MAT label triggers an equivalent case even if total score passes. Model-only MAT cannot count as real-corpus case mastery.

**Exact feedback branches:**

- Correct AF: “AF remains: nonrepeating R–R intervals and no consistent P-wave pattern.”
- Correct variable flutter: “Variable flutter remains: organized atrial activity continues while ventricular conduction varies.”
- Correct multifocal model: “Multifocal atrial tachycardia fits this teaching model: irregular narrow tachycardia with at least three visible P morphologies and variable PR intervals.”
- Correct ectopy: “Patterned premature atrial beats explain the irregularity while the sinus march persists.”
- Correct artifact: “Artifact distorts the baseline, but the true QRS complexes continue their underlying march.”
- Partial: “Your final candidate may fit, but one elimination lacks waveform evidence. Link it to a marked feature.”
- Wrong—MAT without visible P: “Do not count noise as P-wave morphology. If three distinct P waves are not defensible, MAT is not assessable.”
- Unsafe: “Pause at the tracing. This checkpoint grades the differential, not treatment. Complete the elimination board.”
- “Not assessable” when correct: “Correctly limited. The broad irregular narrow category is visible, but atrial evidence does not support a specific subtype.”
- “Not assessable” when incorrect: “The case includes a reviewed atrial ROI in [lead]. Mark its organization before limiting the call.”

**Equivalent retry:** Five new strips with different artifact and ectopy patterns; MAT remains clearly badged as model if no eligible real case exists.

**Accessibility specifics:** Elimination board is a semantic matrix. Each candidate has “Exclude because…” controls tied to evidence row IDs. No drag required.

**Cross-mode handoff:** Unlock “Train · Irregular narrow differential.”

## M6-S7 — Regular wide-complex tachycardia: safety before certainty

**Source refs:** `SPEC-11.14`, `SPEC-7.wide_complex_tachycardia`, `SPEC-8.5`, `SPEC-16.wide_qrs_miss`, `M5-S10`, `ARCH-M6`, `AHA25-TACHY`  
**Eyebrow/title:** “M6 · 8 of 12” / “Regular wide tachycardia”  
**Goal line:** “Use a high-safety broad label unless direct evidence earns more specificity.”

**Exact lesson copy:**

> “A regular wide-complex tachycardia may be ventricular tachycardia, SVT with aberrant conduction, or pre-excited tachycardia. In an appropriate adult clinical context, uncertainty should not be converted into reassurance. Start with ‘regular wide-complex tachycardia; ventricular tachycardia is a major concern,’ then add only supported clues.”

**Case contract:** Authored WCT models plus real cases only when rate, QRS width, rhythm, and WCT concept support are grounded. Clues such as AV dissociation, capture beats, fusion beats, or concordance may be shown only with explicit deterministic event/ROI truth. A prior baseline BBB comparison may be paired but cannot independently prove aberrancy. Required full 12-lead and ≥6-second rhythm strip.

**Layout delta:** Full 12-lead with a “Clue ledger” below: “AV relation,” “Capture/fusion,” “Baseline comparison,” “Morphology,” “What remains uncertain.” Clues reveal progressively only after core map actions.

**Required interaction:** Learner marches R waves, measures QRS, places the case in regular-wide quadrant, then separately searches/marks each available clue. Learner selects a conclusion on a claim ladder from “regular WCT” through “VT strongly supported” only to the packet ceiling.

**Tutor script:**

- Opening: “Earn the broad category first. Specificity comes only from direct clues.”
- Socratic: “Which marked clue changes probability, and which absent clue merely remains unknown?”
- Hint 1: “Do not treat a familiar BBB-like shape as proof of SVT with aberrancy.”
- Hint 2: “AV dissociation or a validated capture/fusion beat can support VT; never invent those clues.”
- Tangent return: “Back to the clue ledger: mark only what this packet supports.”

**State changes and gate:** Regularity and QRS width must pass before clues unlock. Each clue requires ROI overlap/timing evidence. Claim ladder cannot exceed `confidenceCeiling`. Core scene completes with the broad safety statement even when no subtype clue exists; exact VT completion requires an authored/reviewed case ceiling permitting it.

**Exact feedback branches:**

- Correct broad: “Supported: regular wide-complex tachycardia, QRS [QRS] ms. The tracing does not settle the mechanism; ventricular tachycardia remains a major concern.”
- Correct VT-supported: “Supported: regular WCT plus [validated clue]. That strengthens ventricular tachycardia as the mechanism in this teaching case.”
- Partial: “You proved regular and wide. Complete the clue ledger before choosing how specific to be.”
- Wrong—SVT with aberrancy from baseline BBB: “A prior BBB can support aberrancy as a possibility, but it does not exclude VT. Keep the conclusion broad unless direct evidence resolves it.”
- Wrong—VT from width alone: “Wide and regular establishes WCT, not a ventricular origin by itself. Add direct clues or lower the claim.”
- Unsafe—reassuring label/action: “Do not convert uncertain regular WCT into a benign label. Keep the safety-first category and use the clinical pathway.”
- Unsafe—adenosine without qualifiers: “The 2025 AHA pathway limits adenosine consideration in wide-QRS tachycardia to regular, monomorphic cases within the full clinical context. This scene grades the rhythm category, not a medication order.”
- “Not assessable”: “The mechanism may be not assessable; the regular wide-complex category is assessable from the measured tracing.”

**Equivalent retry:** WCT with different baseline comparison and one case without any advanced clue, requiring the broad label.

**Accessibility specifics:** Clue ledger uses lead/time references and text descriptions. ROI searches have list alternatives. Claim ladder announces its evidence ceiling.

**Cross-mode handoff:** Unlock “Train · Regular WCT evidence ladder.” Clinical quick-look remains locked until M6-S10.

## M6-S8 — Irregular wide tachycardia: recognize the stop pattern

**Source refs:** `SPEC-11.14`, `SPEC-7.wide_complex_tachycardia`, M5 pre-excitation, `ARCH-M6`, `ACC23-AF`, `AHA25-TACHY`  
**Eyebrow/title:** “M6 · 9 of 12” / “Irregular wide tachycardia”  
**Goal line:** “Distinguish variable conduction from beat-to-beat polymorphism and avoid harmful shortcuts.”

**Exact lesson copy:**

> “Irregular wide tachycardia is a high-stakes category. Possibilities include AF with bundle-branch aberrancy, pre-excited AF, polymorphic ventricular tachycardia, and artifact. In pre-excited AF, ventricular intervals and QRS morphology can vary markedly because impulses reach the ventricles through changing routes.”

**Safety card copy:** “Suspected pre-excited AF is a stop-and-escalate pattern. Standard AV-node-blocking shortcuts can accelerate accessory-pathway conduction and be harmful. Management depends on stability and expert/current-protocol guidance.”

**Case contract:** Authored pre-excited-AF model paired with an eligible baseline pre-excitation ECG when available. The model has disorganized atrial events, irregular ventricular intervals, and beat-to-beat QRS variation from changing fusion. Comparison cases: AF with fixed BBB morphology and artifact. Exact pre-excited AF claims on real ECG require both AF and pre-excitation evidence; otherwise the broad irregular-wide label is scored.

**Layout delta:** Three-beat overlay and R–R ribbon sit beneath the rhythm strip. Baseline sinus/pre-excitation tracing opens in a comparison drawer. Safety card appears only after the waveform category is completed.

**Required interaction:** Learner marks ≥8 R waves, measures three QRS complexes, overlays three shapes, and selects whether width/morphology is “fixed,” “varying,” or “artifact-limited.” Learner then compares the baseline for delta/short PR evidence and chooses the claim ceiling.

**Tutor script:**

- Opening: “First prove irregular and wide. Then decide whether QRS morphology is fixed, varying, or too distorted to trust.”
- Socratic: “Does a baseline pre-excitation pattern plus irregular, variably wide tachycardia change the safety concern?”
- Hint 1: “Use consecutive R–R intervals and multiple QRS measurements; one broad complex is not enough.”
- Hint 2: “Pre-excited AF requires both atrial-fibrillation evidence and pre-excitation evidence. If either is missing, keep the label broad.”
- Tangent return: “Back to the overlay: compare three consecutive QRS complexes before opening the safety card.”

**State changes and gate:** Eight R marks, three widths, and three overlays required. Real-case claim limited by packet support. Safety card cannot be opened before category completion and cannot itself satisfy the waveform gate.

**Exact feedback branches:**

- Correct pre-excited model: “Supported in this teaching model: irregularly irregular ventricular timing, beat-to-beat QRS variation, and baseline pre-excitation. That pattern raises concern for pre-excited AF.”
- Correct AF with fixed BBB: “Supported: irregular AF timing with a relatively fixed wide-QRS morphology matching the baseline BBB. Pre-excitation is not demonstrated.”
- Correct broad: “Correctly limited: irregular wide-complex tachycardia is established; the mechanism is not.”
- Partial: “You proved irregularity. Measure and overlay multiple QRS complexes before judging the pathway.”
- Wrong—AF alone: “AF describes atrial rhythm; the wide, changing ventricular activation still needs explanation.”
- Wrong—pre-excited AF without baseline evidence: “Variable width raises concern but does not prove pre-excitation. Lower the claim unless delta/short-PR or packet evidence is present.”
- Unsafe—AV-node-blocking shortcut: “Stop. In suspected pre-excited AF, routine AV-node-blocking shortcuts can be harmful. Use the stability-based urgent/expert pathway in this educational scenario.”
- “Not assessable”: “If artifact prevents reliable QRS boundaries, the mechanism may be not assessable. In the core model, irregularity, width variation, and baseline pre-excitation are explicit.”

**Equivalent retry:** Different fusion sequence and a baseline with subtler delta morphology; a second case lacks baseline evidence and requires the broad label.

**Accessibility specifics:** Overlay is accompanied by a beat table listing width, polarity summary, and interval. Safety warning is text and icon, not color-only. Screen reader announces it once, not repeatedly.

**Cross-mode handoff:** Connection receipt: “M5 pre-excitation reused.” Unlock “Clinical preview · irregular wide tachycardia” only after M6-S10.

## M6-S9 — Polymorphic ventricular tachycardia and artifact

**Source refs:** `SPEC-11.14`, `SPEC-7.wide_complex_tachycardia`, `SPEC-16.paced_artifact_confusion`, `ARCH-M6`  
**Eyebrow/title:** “M6 · 10 of 12” / “When morphology changes beat to beat”  
**Goal line:** “Confirm true polymorphism across leads before naming the pattern.”

**Exact lesson copy:**

> “Polymorphic ventricular tachycardia changes QRS axis and morphology beat to beat. Artifact can look chaotic in one channel while true QRS complexes continue in another. Confirm that the changing ventricular complexes are present across simultaneous leads before naming a ventricular rhythm.”

**Torsades preview copy:** “Torsades de pointes is polymorphic VT associated with prolonged repolarization. The rhythm alone is not enough; M8 will connect it to the preceding QT/QTc, medications, and electrolytes.”

**Case contract:** Authored simultaneous three-lead telemetry models for true polymorphic VT and artifact-over-sinus rhythm. Optional torsades model includes a separate preceding sinus ECG with grounded prolonged QTc; without that, label remains “polymorphic VT.” No real competency claim unless appropriate high-confidence data exist.

**Layout delta:** Three simultaneous channels share a vertical cursor. A beat-overlay wheel appears below. “Show preceding rhythm” is locked until polymorphism is established.

**Required interaction:** Learner aligns five QRS complexes across leads, overlays their axes/morphologies, and boxes either the changing ventricular complex across all leads or the artifact region while marching underlying QRS. On the torsades preview, learner must open the preceding rhythm and mark the QT boundary rather than label from appearance alone.

**Tutor script:**

- Opening: “Check simultaneity. A true ventricular complex should have corresponding activity across leads.”
- Socratic: “Does the apparent chaos replace the QRS in every channel, or does an underlying QRS continue through it?”
- Hint 1: “Use the shared vertical cursor to match the same moment across leads.”
- Hint 2: “Reserve ‘torsades’ for polymorphic VT with supporting prolonged-repolarization context.”
- Tangent return: “Back to the synchronized channels: align five ventricular events.”

**State changes and gate:** Five synchronized event marks within ±40 ms; overlay variation must meet model truth. Artifact case requires an underlying march within ±8%. Torsades label requires preceding QT/QTc evidence; otherwise rejected.

**Exact feedback branches:**

- Correct polymorphic: “Supported: wide ventricular complexes change axis and morphology beat to beat across simultaneous leads. That is polymorphic VT in this teaching model.”
- Correct artifact: “Correct. The noisy channel is artifact; true QRS complexes continue through it on the other leads.”
- Correct torsades-limited: “Polymorphic VT is supported. ‘Torsades’ remains unconfirmed until the preceding QT/QTc context is demonstrated.”
- Correct torsades preview: “Supported in this paired teaching model: polymorphic VT with a preceding prolonged-QTc context. M8 will teach the QT measurement and causes.”
- Partial: “You showed changing shape in one channel. Confirm the same ventricular events across the simultaneous leads.”
- Wrong—artifact as VT: “The true QRS march persists in the cleaner channel. Box the artifact without replacing the underlying rhythm.”
- Unsafe—rhythm-only treatment claim: “This checkpoint grades true polymorphism versus artifact. Clinical action depends on pulse and stability, which are not supplied here.”
- “Not assessable”: “If only one noisy channel were available, the mechanism could be not assessable. This model provides simultaneous leads for confirmation.”

**Equivalent retry:** Artifact moves to a different channel; polymorphic axis sequence changes; torsades evidence is withheld in one variant.

**Accessibility specifics:** Simultaneous leads are represented as aligned event rows. Overlay variation is summarized numerically by polarity/axis sector. Reduced motion uses static consecutive-beat tiles.

**Cross-mode handoff:** Banner: “Saved for M8 · QT/QTc and torsades context.”

## M6-S10 — Tachycardia with a pulse: use the current pathway

**Source refs:** `SPEC-11.14`, `ARCH-M6`, `AHA25-TACHY`  
**Eyebrow/title:** “M6 · 11 of 12” / “Tachycardia with a pulse: use the pathway”  
**Goal line:** “Choose the next action category from stability, width, and regularity.”

**Exact lesson copy:**

> “For adult tachycardia with a pulse, first assess whether the rate fits the clinical condition and provide initial support and monitoring. If persistent tachyarrhythmia is causing cardiopulmonary compromise, use the synchronized-cardioversion pathway. Without compromise, QRS width and regularity organize the next branch.”

**Pathway card copy:**

- “Compromise present → synchronized-cardioversion pathway; sedate when feasible without delaying urgent care.”
- “No compromise + narrow regular rhythm → regular narrow-tachycardia pathway.”
- “No compromise + wide regular monomorphic rhythm → wide-QRS pathway with expert consultation; adenosine is considered only in the regular monomorphic context.”
- “Irregular wide rhythm or suspected pre-excitation → stop routine shortcuts and escalate to expert/current-protocol guidance.”

**Case contract:** Four authored clinical branches, each paired with a waveform satisfying its category: unstable regular narrow; stable regular narrow; stable regular monomorphic wide; irregular wide with suspected pre-excitation. Facts include pulse, blood pressure, mental status, shock, chest discomfort, heart-failure cues, oxygenation, regularity, QRS duration, and morphology. No dose, energy, or patient-specific treatment outcome is graded.

**Layout delta:** Three locked stages: “1 · Rhythm evidence,” “2 · Perfusion evidence,” “3 · Pathway.” A branching diagram grows only from verified facts. Mobile shows one stage at a time with a persistent breadcrumb.

**Required interaction:** Stage 1 requires R march and QRS measurement. Stage 2 requires selecting present compromise cues. Stage 3 requires drawing a path through the algorithm nodes. A learner must complete all four branches.

**Tutor script:**

- Opening: “Build the pathway from observed facts. I will not let a rhythm label skip the stability branch.”
- Socratic: “Which single verified fact determines the next branch: compromise, width, or regularity?”
- Hint 1: “Compromise is checked before width.”
- Hint 2: “In the no-compromise branch, wide QRS is 120 ms or more; regular monomorphic wide rhythm is different from irregular wide rhythm.”
- Tangent return: “Back to Stage [n]: verify the fact that feeds the next node.”

**State changes and gate:** Each node remains locked until its source fact is verified. The path is deterministic from the scenario. Medication/dose controls do not exist. A wrong high-stakes branch always requires an equivalent branch before completion.

**Exact feedback branches:**

- Correct unstable branch: “Correct. Persistent tachyarrhythmia with [compromise cues] enters the synchronized-cardioversion pathway.”
- Correct stable narrow: “Correct. No compromise is provided, QRS is [QRS] ms, and the rhythm is regular. Continue through the regular narrow-tachycardia pathway.”
- Correct stable regular wide: “Correct. No compromise is provided; the rhythm is regular, monomorphic, and wide. Use the wide-QRS pathway with expert consultation.”
- Correct irregular wide: “Correct. Irregular wide tachycardia with suspected pre-excitation is not a routine narrow-SVT branch. Stop shortcuts and escalate through expert/current-protocol guidance.”
- Partial: “Your rhythm category is supported. The pathway remains locked until the perfusion evidence is completed.”
- Wrong—width before compromise: “The algorithm checks cardiopulmonary compromise before using QRS width to organize the stable branch.”
- Wrong—adenosine on irregular wide: “The regular-monomorphic qualifier is missing. Do not apply that shortcut to irregular wide tachycardia.”
- Unsafe—specific dose/energy: “Exact medication, dose, sedation, and device-energy decisions require the current protocol and clinical team. This checkpoint grades the pathway branch only.”
- “Not assessable”—before bedside data: “Correct that compromise is not assessable from the ECG. Open the provided bedside assessment.”
- “Not assessable”—after full data: “The scenario provides the required perfusion, width, and regularity facts. Trace the supported branch.”

**Equivalent retry:** Same pathway target with different rhythm rate/morphology and a different compromise cue. No waveform or context is reused.

**Accessibility specifics:** Branch diagram is also an ordered decision form with one question per page. The final path is read as a sentence. No timed interaction in Guided mode.

**Cross-mode handoff:** Unlock “Clinical · Tachycardia with a pulse” and “Rapid · 20-second rhythm category.” Exact note: “Rapid mode will time the first high-yield category, not a full management plan.”

## M6-S11 — Tachyarrhythmia handoff

**Source refs:** all M6 refs; `SPEC-12.1`; `ARCH-M6`  
**Eyebrow/title:** “M6 · 12 of 12” / “Tachyarrhythmia handoff”  
**Goal line:** “Interpret unannounced tachycardias, then make one high-yield quick-look decision.”

**Exact lesson copy:**

> “Your fixed sequence is: pulse and perfusion context → ventricular rate and regularity → QRS width and morphology → atrial activity → AV relationship → strongest defensible rhythm → action category. Accuracy comes before speed; the quick look asks for only the first safe category.”

**Tutor opening:** “I’ll stay silent for the independent set. If you ask, the clock pauses, your work is preserved, and assistance is recorded.”  
**Socratic on request:** “Which step in the fixed sequence remains unsupported?”  
**Hint 1:** “Complete the regular/narrow-wide map before searching for a named rhythm.”  
**Hint 2:** “For atrial rhythms, prove organization and P evidence; for WCT, preserve a broad safety label unless direct clues support more.”  
**Tangent return:** “Back to case [n] at the exact timer, zoom, and draft you paused.”

**Case contract:** Six-case independent set, sampled without replacement: sinus tachycardia or limited regular narrow; SVT; flutter; AF; regular WCT with broad or VT-supported ceiling; irregular wide or polymorphic/artifact comparison. Every case retains its earlier eligibility contract. At least one case requires calibrated uncertainty. Context is absent in ECG-only cases and explicitly provided in the final two clinical cases.

**Layout delta:** Round 1 “Evidence read” shows the full tools and no timer. Round 2 “Quick look” uses a new equivalent case, 20-second visible but nonpunitive clock, and only three required actions: tap decisive rhythm region, choose broad category, record confidence. Mobile quick-look keeps the single decisive lead plus “Show full 12-lead”; opening the full tracing does not pause time.

**Required interaction:** Round 1: R march, QRS calipers, atrial-event or absence marks, AV relationship, normalized conclusion, confidence, and action category if context exists. Round 2: direct point/box on decisive evidence plus broad category; no full typed interpretation.

**Deterministic scoring and gate:** Six evidence reads: regularity 15%, width 15%, atrial evidence 20%, AV relationship 15%, conclusion/claim strength 20%, confidence 5%, context action 10% when present. Pass ≥82%, no high-confidence AF/flutter confusion, no falsely reassuring WCT label, and correct instability branch. Quick-look reports time but completion depends on category/evidence, not beating 20 seconds. Critical miss loads one equivalent case.

**Exact feedback branches:**

- Fully correct: “Supported. You demonstrated [evidence sentence], chose [normalized conclusion], and matched your confidence to the case evidence.”
- Correct broad WCT: “Correctly safe and limited: [broad category]. The packet does not justify a more specific mechanism.”
- Correct uncertainty: “Correctly limited. You preserved what is visible and named what remains unresolved.”
- Partial: “You have [credited evidence]. The conclusion remains locked until [missing waveform action] is completed.”
- Wrong AF/flutter: “The ventricular timing is [pattern], but the discriminator is atrial organization. Re-open [lead] and mark whether atrial activity is organized and repetitive.”
- Wrong sinus/SVT: “Rate alone does not decide this case. Recheck P morphology and onset evidence.”
- Wrong/reassuring WCT: “This tracing establishes [regular/irregular] wide-complex tachycardia. Do not down-classify it without direct mechanism evidence.”
- Wrong stability branch: “The provided [compromise cue] changes the priority pathway. Complete an equivalent clinical branch before exit.”
- Unsafe—specific treatment: “This exit grades the evidence chain and action category, not a patient-specific medication, dose, or device setting.”
- “Not assessable” when correct: “Correctly limited: [supported category] is assessable; [specific mechanism] is not.”
- “Not assessable” when incorrect: “The packet provides readable [atrial/QRS/onset] evidence in [lead]. Mark it before limiting the call.”
- Quick-look correct: “Safe first category in [seconds] s. Your evidence tap landed on [feature]. Speed is reported separately from accuracy.”
- Quick-look wrong: “The first category was not supported. Time is not the issue; re-run an untimed equivalent case and mark [decisive feature].”

**Equivalent retry:** Contract-matched new case with different rate, atrial-feature location, QRS morphology, and context; no repeated ECG in the same session. A quick-look miss first returns to an untimed evidence read, then offers a new quick look.

**Accessibility specifics:** Quick-look can be disabled with “Use untimed mode”; this does not reduce mastery credit. Screen readers default to untimed because waveform navigation latency is not a clinical skill. Voice-control labels are unique. Results show accuracy, evidence localization, confidence, and time as separate metrics.

**Completion copy:**

> “Module complete. You can now organize tachycardia before naming it, distinguish common atrial patterns from their mimics, keep wide-complex uncertainty safe, and connect the tracing to a perfusion-first action pathway.”

**Cross-mode handoff cards:**

- “Train · Your weakest discriminator” — “Repeat [objective] with blocked targets, mimics, and normal controls.”
- “Rapid · Tachycardia quick looks” — “Choose ward, emergency, or untimed pacing; AI stays silent until submission.”
- “Clinical · Palpitations and tachycardia with a pulse” — “Add symptoms, perfusion, prior ECG, and action category.”
- “Next guided module · Chambers, voltage, and R-wave progression” — “Shift from rhythm mechanisms to structural electrical patterns.”
- “Saved connection · M8” — “Return to QT/QTc before torsades is assessed independently.”

---

## 3. Shared mastery receipts and cross-mode routing

Each scene writes a receipt only after its waveform gate passes. Required fields are:

```text
moduleId, sceneId, objectiveId, caseIdOrModelId, sourceKind,
evidenceActions[], correctness, assistanceLevel, attempts,
equivalentRetryUsed, confidence, confidenceCalibration,
notAssessableAppropriate, elapsedActiveMs, accessibilityPath,
remediationSceneId, trainObjectiveId, rapidEligibility, clinicalEligibility
```

Assistance levels are exact enum labels shown in results: “Independent,” “After one hint,” “After two hints,” “After tutor tangent,” and “After equivalent retry.” A tutor answer never changes deterministic truth and never upgrades a receipt to independent.

### M4 objective routes

| Guided objective | Train destination | Rapid/Clinical unlock | Remediation |
|---|---|---|---|
| P/QRS independent march | `train.av_relationship` | Rapid brady rhythms | M4-S0 |
| PR behavior | `train.pr_sequence` | AV-block mixed read | M4-S2 |
| First-degree versus dropped conduction | `train.long_pr_vs_drop` | Ward brady case | M4-S3 |
| Wenckebach versus Mobitz II/blocked PAC | `train.av_block_contrast` | Brady Clinical after exit | M4-S4 or M4-S5 by error |
| 2:1 uncertainty | `train.av_2_to_1_claim_strength` | Rapid calibration item | M4-S6 |
| AV dissociation | `train.av_dissociation` | Severe-brady Clinical | M4-S7 |
| Perfusion-first brady branch | `train.brady_context` | Clinical bradycardia with a pulse | M4-S9 |

### M5 objective routes

| Guided objective | Train destination | Rapid/Clinical unlock | Remediation |
|---|---|---|---|
| QRS width plus terminal morphology | `train.qrs_width_morphology` | Rapid wide-QRS reads | M5-S0 |
| RBBB/LBBB anchors | `train.bbb_contrast` | Mixed Rapid | M5-S2 or M5-S3 |
| Nonspecific/limited label | `train.ivcd_claim_strength` | Confidence calibration | M5-S4 |
| Fascicular vector | `train.fascicular_axis` | Syncope/conduction cases after review | M5-S5 |
| Machine-statement audit | `train.machine_audit_conduction` | Clinical old-versus-new | M5-S6 |
| Pre-excitation | `train.delta_search` | M6 irregular-wide path | M5-S7 |
| Pacing spike/capture ledger | `train.pacing_ledger` | Device-management cases remain review-gated | M5-S8 |
| Secondary discordance | `train.secondary_repolarization` | M8/M9 only after prerequisites | M5-S9 |

### M6 objective routes

| Guided objective | Train destination | Rapid/Clinical unlock | Remediation |
|---|---|---|---|
| Regularity × width matrix | `train.tachy_matrix` | Rapid tachy quick looks | M6-S1 |
| Sinus versus SVT | `train.sinus_vs_svt` | Palpitations Clinical | M6-S2 |
| Flutter ratio | `train.flutter_ratios` | Rapid atrial rhythms | M6-S4 |
| AF evidence/mimics | `train.af_mimics` | AF Clinical after context lesson | M6-S5 |
| Irregular narrow differential | `train.irregular_narrow` | Mixed Rapid | M6-S6 |
| Regular WCT claim strength | `train.regular_wct` | Emergency quick-look | M6-S7 |
| Irregular wide/pre-excitation | `train.irregular_wide` | Clinical after pathway scene | M6-S8 |
| Polymorphic versus artifact | `train.polymorphic_artifact` | QT/torsades remains M8-gated | M6-S9 |
| Stability/pathway | `train.tachy_context` | Clinical tachycardia with a pulse | M6-S10 |

## 4. Curriculum and case validators

The implementation must fail its content build if any of these conditions occurs:

1. A scene lacks at least one required waveform/model action before completion.
2. A real case lacks the concept-specific evidence listed in its case contract.
3. A case is used to teach an ROI or lead claim absent from its packet.
4. A Mobitz subtype is scored from an intentionally 2:1-indeterminate tracing.
5. RBBB/LBBB is scored from QRS width without paired-lead morphology.
6. A real pacing malfunction is diagnosed without reviewed spike/response evidence.
7. AVNRT versus AVRT is graded beyond the case confidence ceiling.
8. AF is scored from rate alone, or flutter from a near-150 rate alone.
9. WCT is down-classified to benign SVT/aberrancy without direct supporting evidence.
10. Torsades is scored without polymorphic VT plus preceding prolonged-repolarization evidence.
11. A clinical stability/action branch is inferred from ECG morphology instead of provided scenario facts.
12. “Not assessable” is always wrong or always accepted rather than case-contract dependent.
13. A drag-only interaction has no keyboard/tap/structured alternative.
14. Reduced-motion mode removes information rather than changing its presentation.
15. A tutor response advances the state machine or mutates deterministic truth.

## 5. Clinical review locks

These items may be storyboarded and demonstrated but must not become scored patient-management recommendations until the content version is clinician-reviewed and tied to a dated source:

- medication selection, dose, route, or contraindication beyond the explicit high-level safety guard;
- cardioversion energy and sedation specifics;
- transcutaneous/transvenous pacing settings;
- device malfunction diagnosis or programming advice from a real case;
- a precise anatomical level of AV block from surface ECG alone;
- a precise AVNRT/AVRT mechanism without reviewed evidence;
- electrolyte, drug, or torsades causal attribution before M8 evidence;
- risk prediction or disposition from an ECG without authored clinical context.

The learner-facing source drawer for the two action-pathway scenes must display: “Guidance version: 2025 AHA adult bradycardia/tachyarrhythmia with a pulse pathway. Educational abstraction; verify current local protocol.”

## 6. Authoritative external references used to verify clinical-pathway copy

- [2025 AHA Adult Bradycardia With a Pulse Algorithm](https://www.heart.org/-/media/CPR-Files/CPR-Guidelines-Files/2025-Algorithms/Algorithm-ACLS-Bradycardia-250514.pdf)
- [2025 AHA Adult Tachyarrhythmia With a Pulse Algorithm](https://www.heart.org/-/media/CPR-Files/CPR-Guidelines-Files/2025-Algorithms/Algorithm-ACLS-Tachycardia-250514.pdf)
- [2018 ACC/AHA/HRS Bradycardia and Cardiac Conduction Delay — Guidelines Made Simple](https://www.acc.org/-/media/Non-Clinical/Files-PDFs-Excel-MS-Word-etc/Guidelines/2018/Guidelines_Made_Simple_2018_Bradycardia.pdf)
- [2023 ACC/AHA/ACCP/HRS Guideline for Atrial Fibrillation](https://www.heart.org/-/media/Files/Professional/Quality-Improvement/Get-With-the-Guidelines/Get-With-The-Guidelines-AFIB/AFib-Month/joglaretal20232023accahaaccphrsguidelineforthediagnosisandmanagementofatrialfibrillation.pdf)

These sources supplement the repository’s binding curriculum coverage; they do not authorize the LLM to provide patient-specific advice.
