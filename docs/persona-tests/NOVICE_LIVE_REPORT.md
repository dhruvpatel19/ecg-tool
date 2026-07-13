# Novice live-use report

**Persona:** first-year medical student, low ECG confidence, visual/stepwise learner, keyboard-reliant  
**Build tested:** `http://localhost:3100` on 2026-07-10  
**Viewports:** 1366×768 and 390×844  
**State:** local storage cleared before the desktop run; the mobile pass used a new browser context and cleared storage again  
**Direct-use coverage:** Foundations scenes 1–4; M02.S0, M02.S1, and M02.S9; the M02.S9 → Competency Lab handoff

Severity: **P0** breaks a promised learning loop; **P1** materially blocks or misgrades learning/access; **P2** creates substantial friction or confusion; **P3** is polish.

## Executive finding

Foundations is the strongest part of the product: it is calm, visual, causal, and the tutor tangent/return loop genuinely works. Module 2 has an excellent underlying instructional model and realistic ECG workspace, but several current runtime details undermine trust: its cross-mode handoff launches the wrong competency, its free-response grader rejects correct reasoning unless the learner uses narrow phrases, and its mobile/keyboard presentation makes the highest-value visual work difficult.

## Severity-ranked findings

### P0 — M02.S9's targeted handoff launches an unrelated drill

After completing both M02.S9 actions independently, the completion card correctly offered **“Train contiguous and approximate opposing lead groups”** with `localize · faded`. Its URL also correctly encoded:

`/train?focus=lead_territories&subskill=localize&support=faded&origin=leads-vectors%3AM02.S9…`

The resulting Competency Lab instead loaded:

- **Focused on Rate · localize**
- target concept **Rate**
- a gate to click a decisive **QRS complex**
- answer choices Rate, Normal axis, Normal ECG, and Sinus rhythm

`lead_territories` was not available in the target-concept selector. This breaks the central promise that a guided weakness transfers into focused practice; a novice is told the handoff is personalized while receiving an unrelated task. The return URL itself correctly points back to `?scene=M02.S9`.

Evidence: [completed handoff](screenshots/novice-m02-s9-handoff.png), [wrong Competency Lab target](screenshots/novice-train-handoff-mismatch.png).

### P1 — M02.S1 misgrades correct explanations and contradicts its own hint

The prompt asks why the same beat differs across leads and says to include one event and different directed views. The deterministic checker rejected both of these semantically correct answers:

1. “the same electrical event is viewed from different lead directions, so toward the positive end is upright and away is downward.”
2. “One evolving electrical event looks different because each lead is one of multiple directed views: toward its positive pole is upright and away is downward.”

The second answer follows the displayed smaller-step hint almost verbatim: **“Use both phrases: one evolving event and multiple directed views.”** It was still marked “Not yet.” Only “The same electrical event … different directed views” passed. Because the false negatives exposed the hint ladder, the scene then required an equivalent retry despite demonstrated understanding.

This teaches keyword compliance rather than vector reasoning and will feel punitive to a learner who gave a more complete causal answer than the accepted phrase. Normalize synonyms/stems or grade the explicit rubric semantically; the hint must use wording the checker accepts.

### P1 — Critical keyboard/screen-reader controls are ambiguous or effectively invisible

Observed issues:

- **Foundations scene 4:** four `Readable` and four `Too noisy` buttons have identical accessible names and no strip number/context. A keyboard or screen-reader user cannot know which strip a control belongs to.
- **Foundations scene 2:** the one-beat range has a useful accessible name, but its focused computed style had no visible outline.
- **M02.S1:** the vector-angle range had no accessible name. Its focus indication was only the browser's subtle 1 px outline.
- **M02.S1:** moving from −90° to the intended +60° required 150 ArrowRight steps under the visible instruction. Larger-step keys are not disclosed in the live task.
- **M02.S9:** the completion handoff link had `outline: none` and no focus shadow when keyboard-focused.
- The main learning shell has no skip link; eight persistent navigation stops precede the primary learning CTA.

Add contextual names (`Strip 1: Readable`), strong `:focus-visible` treatment, a named vector slider with current value/direction, visible larger-step instructions, and a skip-to-scene link.

Evidence: [Foundations readability task](screenshots/novice-foundations-readable.png), [M02.S1 vector control](screenshots/novice-m02-s1-vector.png).

### P1 — The mobile Module 2 flow buries the lesson and compresses the ECG below useful inspection size

At 390×844, M02.S9 had no horizontal overflow, but the page was **5,153 px tall** before any completion state. The learner encounters the module overview and all 15 scene-map entries before the active scene. The full 12-lead ECG is then compressed into the narrow column; the rhythm is recognizable, but fine morphology and grid-based comparison are not credible at that default size for a novice.

On mobile, collapse the module overview and scene map behind a persistent chapter/scene picker, jump focus/scroll directly to the requested scene, and default the ECG to a legible single-lead or relevant-lead stack with an obvious “show full 12-lead” control.

Evidence: [M02.S9 mobile full page](screenshots/novice-m02-s9-mobile-full.png).

### P2 — Module 2 announces conflicting workload and exposes authoring metadata

At 1366×768 the header simultaneously said **“Usually 60–80 minutes”** and **“15 scenes · 128 min core path.”** The same header exposed raw source identifiers such as `SPEC-11.1` and long misconception IDs. For a low-confidence learner, the contradiction makes the course feel unfinishable, and the source map competes with the actual objective.

Show one honest learner-facing duration (preferably chapter-level), move source provenance behind an optional educator/info drawer, and reserve the first viewport for “what I will learn / what I do next.”

Evidence: [M02.S0 desktop full page](screenshots/novice-m02-s0-desktop.png).

### P2 — Normal asynchronous loading briefly presents a failure state

On first entry to M02.S0, the workspace showed “Selecting an eligible tracing…,” immediately followed by **“Scene locked for this case,” “No case packet is loaded,”** and tutor copy saying the learning case failed its content check. A normal PTB-XL packet loaded shortly afterward without intervention.

Keep loading, empty, and validation-failure states distinct. Do not tell a novice the scene is locked or invalid while selection is still in flight.

### P2 — M02.S1's requested evidence and actual control do not fully align

The action says to point the vector and **predict the dominant sign in lead II and aVR**, but it only collects the angle. At +60° the feedback correctly explains II-positive/aVR-negative, yet the learner never commits either sign. Add explicit polarity choices or ask only for vector placement.

### P2 — Foundations mobile uses nested scrolling

Foundations itself reflows cleanly at 390 px with no horizontal overflow, but it is hosted in a 358×673 iframe whose document was 1,610 px tall. Reaching the tutor and navigation requires scrolling inside the lesson while the outer shell remains a separate scroll context. This is awkward on touch and can trap keyboard focus/scroll.

Evidence: [Foundations mobile](screenshots/novice-foundations-mobile.png).

### P2 — Fresh-state messaging is internally inconsistent

After local storage was cleared, Foundations correctly began at the opening scene, but the shared demo profile still showed non-zero mastery across later modules while the shell said **“Progress saves locally.”** For onboarding and persona testing, distinguish seeded demo data from the learner's own progress or provide a true reset/new-learner control.

## What worked particularly well

- **Foundations progression:** “one beat, one wave” → calibrated grid → readability is a sensible first-principles sequence. The animation narrates atrial activation, ventricular activation, and reset before asking for labels.
- **Keyboard calipers:** both markers had useful accessible names; Arrow and Shift+Arrow worked. Moving from 16.0 to 5.0 boxes produced 200 ms, and feedback tied the box count to time.
- **Tutor tangent and return:** asking “Why does atrial repolarization not appear as a separate wave?” produced a concise, accurate answer by the 8-second observation point. The explicit **Return to One beat, one wave** control restored the exact scene and reported that the unfinished interaction was unchanged. This is the clearest implementation of the product's AI-first promise. Evidence: [tangent and return](screenshots/novice-foundations-tangent.png).
- **M02.S0 remediation:** the plausible wrong ordering triggered a small-step cue—ruler, signal, view, finding. The corrected feedback explained why calibration/quality precede lead orientation and waveform claims. This feedback teaches a dependency, not just an answer.
- **Equivalent retry:** the replacement ECG changed from PTB-XL 3 to PTB-XL 10 in about 1.3 seconds and preserved the learning objective.
- **M02.S1 vector feedback:** at +60°, the explanation clearly connected toward lead II and away from aVR to opposite waveform directions.
- **M02.S9 language:** “localize before diagnosing” and the prohibition against jumping from territory to cause/culprit vessel are appropriate, memorable clinical guardrails.
- **ECG realism:** desktop tracings look like genuine PTB-XL recordings rather than idealized cartoons, with standard 3×4 sequential layout, continuous lead-II rhythm strip, square grid, calibration annotation, noise, and natural beat-to-beat variation. The desktop visualization is convincing; the limitation is responsive legibility, not source realism.

## Timing and cognitive-load notes

- Equivalent retry: about **1.3 s**.
- Tutor tangent: response present by the **8 s** observation point.
- Competency handoff: the full drill was visible after roughly **5–6 s**; its initial loading screen lasted long enough to notice.
- Foundations copy is short enough to scan and each task asks for one main decision.
- Module 2's first viewport asks a novice to process a long objective, two inconsistent durations, raw source identifiers, three connection cards, 15 scene entries, a real ECG, and a task before reaching the tutor. The pedagogy inside each scene is substantially clearer than the surrounding information architecture.

## Recommended fix order

1. Honor `focus=lead_territories` end to end and add a regression test for the exact M02.S9 → Train URL, selected concept, evidence gate, and return route.
2. Repair free-response normalization/rubric logic and test the two rejected novice answers above; never show a hint phrase the checker rejects.
3. Fix contextual accessible names and strong focus states; make the vector control efficient by keyboard.
4. Collapse mobile overview/scene navigation and provide a legible relevant-lead ECG view.
5. Unify duration copy, hide authoring metadata, and separate loading from case-validation failure.

## RETEST — fixed novice paths (2026-07-10)

Retested only M02.S1, the M02.S9 → Train handoff/return, and M02.S9 at 390×844 in a fresh browser session.

- **PASS — M02.S1 vector evidence now matches the prompt.** The slider has the descriptive accessible name `Net vector angle toward down-left vector toward lead II`; keyboard-accessible ±15° controls reduced the −90° → +60° move from 150 one-degree presses to 10 presses; and labeled II/aVR polarity selectors now require the learner to commit **positive/upright** and **negative/downward** before submission. The combined answer produced the intended causal feedback. Evidence: [retested vector task](screenshots/retest-m02-s1-vector.png).
- **PASS — both previously rejected explanations are accepted.** The checker marked each of these `Evidence aligned`: (1) “the same electrical event is viewed from different lead directions, so toward the positive end is upright and away is downward”; and (2) “One evolving electrical event looks different because each lead is one of multiple directed views: toward its positive pole is upright and away is downward.” No scaffold was exposed for either submission.
- **PASS — M02.S9 preserves the requested training objective.** The handoff still encodes `focus=lead_territories&subskill=localize&support=faded`. Train now explicitly says it was launched for **lead territories · localize**, explains why it uses the validated Normal ECG case family, and changes the evidence gate to: **mark one QRS in the inferior territory and name all contiguous inferior leads**. It no longer presents a generic Rate/QRS task as though it were territory training. Evidence: [retested targeted drill](screenshots/retest-m02-s9-train.png).
- **PASS — return route.** The visible return link targeted `/learn/leads-vectors?scene=M02.S9`; activating it returned to that exact URL and restored the “Contiguous and opposing views” scene. This retest verified target selection and navigation, not completion of an entire Train classification.
- **PASS with residual friction — mobile scene map and ECG.** At 390×844, the 15-entry map is collapsed behind **Choose scene**, the page has no horizontal overflow, and the ECG now uses a readable two-column vertical lead stack rather than compressing twelve leads into a tiny four-column print. Waveforms, grid, and labels were legible at the default scale. Document height fell from 5,153 px to 4,368 px. The remaining issue is that a deep link to `?scene=M02.S9` still opens at the module overview; the learner must scroll past the overview/progress/connection cards to reach the already-selected scene. Evidence: [mobile overview](screenshots/retest-mobile-top.png), [collapsed scene map](screenshots/retest-mobile-scene.png), [legible mobile ECG](screenshots/retest-mobile-ecg.png).

### Post-retest implementation closeout

The remaining deep-link friction was subsequently fixed: a valid `?scene=` restoration now focuses and scrolls directly to the selected scene with mobile navigation clearance. The responsive regression asserts both focus and a nonzero restored scroll position; the final full Playwright run passed 24/24 tests.
