# Advanced live-use report — senior resident / skeptical ECG educator

Date: 2026-07-10  
Build tested: `http://localhost:3100`  
Perspective: senior internal-medicine resident who teaches ECG interpretation and treats mastery claims as assessment claims, not engagement metrics.

## Test scope and method

I used the live application, not just the storyboards or source. The in-app browser exposed no attachable session, so the live interaction was completed in Chromium through the repository's Playwright runner against the same localhost build. This is a tooling limitation, not a product finding.

Viewports exercised:

- Desktop: 1440 × 1000
- Laptop: 1280 × 800
- Compact laptop: 1024 × 768

There was no page-level horizontal overflow at any tested width. Typical scene heights were 2,786–3,145 px, so the ECG, active task, and tutor occupy several vertical screens.

Live scenes exercised:

- M5: `m05-s0`, `m05-s2`, `m05-s8`
- M8: `m08-s3` through `m08-s7`
- M9: `m09-s0`, `m09-s1`, `m09-s8`, `m09-s9`
- M10: `m10-s10`, `m10-s11`
- Guided → Train handoff from `m05-s0`

I completed a wrong-then-correct caliper branch, a wrong-then-correct vector branch, a three-step locked-case path, the M10 source categorization task, an AI tangent and return, and the guided-to-Train transition. Screenshots are stored beside this report, including `ADV_m05_s0_desktop_workspace.png`, `ADV_m08_s4_laptop_workspace.png`, `ADV_m09_s8_laptop_workspace.png`, `ADV_m10_s10_desktop_workspace.png`, `ADV_ai_tangent_return.png`, and `ADV_m05_locked_complete.png`.

## Executive verdict

The scientific narrative and evidence-boundary language are substantially stronger than typical ECG courseware. The platform repeatedly distinguishes waveform findings from timing, causation, bedside status, and treatment authority. The real ECG renderer is credible. The tutor was cautious, case-grounded, and preserved work during a tangent.

It is not yet safe to present the current guided results as competency evidence. Two release-blocking problems dominate:

1. M5 permits independent visual competency to be earned without identifying the displayed QRS or terminal force.
2. M8's core QTc arithmetic scene is impossible to complete through the rendered UI.

My overall scores for this build:

| Dimension | Score | Judgment |
|---|---:|---|
| Scientific teaching narrative | 8.5/10 | Mechanistic, clinically connected, and appropriately cautious |
| Case-contract honesty | 8/10 | Excellent gates, with contradictory completion language |
| ECG rendering realism | 7.5/10 | Convincing real tracings and paper geometry; source resolution and task linkage need work |
| Assessment/task validity | 4/10 | Multiple interactions do not prove what their prompts claim |
| AI tutor | 8/10 | Strong safety and grounding; exact waypoint control is unreliable |
| Laptop usability | 6/10 | Legible and no overflow, but excessive vertical separation and persistent rail cost |

## Severity-ranked findings

### P0 — Independent conduction mastery can be earned without marking the displayed waveform

Exact scene: M5 `m05-s0`, **Width is not morphology**.

Live evidence:

1. I opened the keyboard/precise-entry alternative, selected V1, and entered 1.00–1.14 seconds. In a standard sequential 3×4 display, the visible V1 panel corresponds to the third 2.5-second acquisition column, not 1.00 seconds. The off-panel interval was nevertheless accepted as a 140-ms V1 QRS measurement.
2. The grader used duration alone. It did not verify that the chosen interval intersected a QRS, much less QRS onset and offset.
3. The second action says, “Select the final QRS segment in V1/V6, then rotate the arrow.” The rendered action contains only an angle slider. I moved it to 90° without selecting either lead or a waveform segment.
4. The platform then displayed: “SCENE COMPLETE · INDEPENDENT EVIDENCE RECORDED” and credited `localize` plus `explain mechanism`.

This is a mastery-integrity failure, not a cosmetic issue. A learner can complete the whole scene from two numeric guesses while ignoring the ECG.

Required fix:

- Restrict structured time choices to the visible acquisition interval for the selected lead.
- Quantize boundaries to actual samples.
- Require the submitted interval to overlap the reviewed QRS ROI and require onset/offset proximity.
- Require actual paired terminal-QRS regions in V1/V2 and I/V6 before the vector response unlocks.
- Derive or constrain the vector task from those selected regions; do not award `localize` from an ungrounded slider.
- Add an adversarial test that submits the correct duration over a T wave, baseline, and off-panel time and asserts zero independent credit.

### P0 — M8 QTc arithmetic is unanswerable

Exact scene: M8 `m08-s4`, **Rate correction is a model**.

The prompt says to enter QT and RR in seconds and return Bazett QTc in milliseconds. The UI renders only one numeric field labeled “Bazett QTc” and supplies neither QT nor RR. It also has no QT and RR input fields. I tested every 10-ms value from 200 through 900 ms. Every value remained on action 1 and produced the same response: “The formula received milliseconds where seconds were required.”

This blocks a central M8 objective and makes the feedback scientifically incoherent: the only rendered field explicitly requests milliseconds.

Required fix:

- Choose one coherent interaction:
  - provide authored QT and RR values with provenance, unit-aware QT/RR inputs, a visible calculation transcript, and a QTc output; or
  - carry forward the learner's accepted QT and RR from the prior scene and visibly show them as the inputs.
- Give the authored simulation explicit expected Bazett and Fridericia values.
- Grade input units separately from output units.
- Test both formulas at slow, mid-range, and fast rates, including rounding tolerance.

### P1 — The M9 mimic comparison is a text-table proxy, not a trace comparison

Exact scene: M9 `m09-s8`, **Target, mimic, normal**.

The scene promises target, close mimic, and normal tracings at matched calibration. The live workspace shows one locked PTB-XL ECG. The interaction then labels two text columns “ischemia compatible pattern” and “ischemia mimic,” but no second or third tracing is present.

I entered the generic expected phrases in the ten text cells, without extracting evidence from a pair of ECGs. The response was accepted. The “correct” feedback contained unresolved authoring placeholders:

> Discriminator found. [Trace feature] in [lead/region] makes [category] more compatible than [mimic], while [remaining uncertainty] is preserved.

The next region action was correctly locked and explicitly formative, which prevented final independent visual credit. That safeguard is good, but the first action still teaches the wrong interaction model and can record a semantically thin formative success.

Required fix:

- Render three distinct, contract-valid case packets at identical calibration and lead order.
- Bind each answer row to visible case IDs and selected lead regions.
- Require one trace-level discriminator mark before accepting the comparison.
- Replace generic expected prose with case-specific evidence objects.
- Resolve all feedback tokens before rendering; unresolved tokens should fail curriculum validation and CI.

### P1 — Guided → Train loses the selected competency

Exact handoff: M5 `m05-s0` → **Train · Width versus morphology**.

The guided handoff URL uses `focus=qrs_width_morphology&subskill=discriminate`. The Train page reads `concept`, not `focus`, and `qrs_width_morphology` is not a selectable corpus concept. The landing page therefore changed the focus to **Rate** while still telling me that I had launched a `discriminate` contrast set from the guided scene.

This breaks the adaptive loop at precisely the point where the platform claims a competency-specific handoff. The concept chooser also showed duplicate RBBB, LBBB, QRS-duration, fascicular, WPW, AF, flutter, and AV-block entries.

Required fix:

- Use one typed handoff contract across all modes: `concept`, `subskill`, support level, origin, and return target.
- Maintain an explicit mapping from teaching objectives such as `qrs_width_morphology` to one or more eligible corpus concepts.
- If no mapped deck is eligible, show an honest unavailable state; never silently substitute Rate.
- Deduplicate the concept catalogue before rendering.
- Add route-contract tests for every production handoff.

### P1 — Feedback can be confident, specific, and wrong

Exact evidence:

- M5 `m05-s0`: a clearly excessive 300-ms “QRS” received “Equal duration does not make equal morphology,” rather than being told that the selected boundaries were not plausible QRS onset/offset.
- M5 `m05-s0`: the accepted response says “All three QRS complexes occupy the same duration band,” although the live workspace showed one ECG and no three-case comparison.
- M10 `m10-s10`: I intentionally categorized all seven questions as “Resting 12-lead.” The partial feedback claimed, “You assigned the rhythm-stream questions correctly,” which was false.
- M5 `m05-s2`: after acknowledging all three unavailable evidence actions, the honest formative receipt appeared, but the completion body still asserted that duration and both terminal anchors supported RBBB even though none had been demonstrated.

Static branch copy is being presented as if it reflected the learner's actual response. That erodes trust and can reinforce misconceptions.

Required fix:

- Generate deterministic feedback from the actual wrong fields and evidence objects.
- Do not reference comparison cases that are not mounted.
- Separate “content path covered” from “finding demonstrated.”
- Add branch tests that deliberately choose each wrong option and verify every factual clause in the feedback.

### P2 — AI tangent handling is strong, but exact return control drifted

Exact scene: M5 `m05-s0`, with a saved incorrect 300-ms caliper response.

I asked how to interpret QTc in ventricular pacing and whether to stop a QT-prolonging medication. The tutor did several things well:

- explained that wide/paced QRS contributes to QT;
- suggested JT or a validated paced/wide-QRS method rather than inventing a correction;
- refused a patient-specific medication instruction;
- explicitly noted that the current packet showed sinus rhythm/RBBB rather than pacing;
- cited missing pacing mode, electrolytes, symptoms, medication list, and reviewed method;
- preserved the active scene and the 300-ms learner response after “Return to lesson.”

The redirect was not exact: it told me to complete the QRS-width assessment in **V2**, while the active scene's task required **V1**. The tutor was safer than most ECG chatbots, but the return waypoint should be controlled by application state, not inferred by the language model.

Required fix:

- Have the model answer only the tangent and return a structured bridge.
- Render the exact lead, action, and pending evidence from deterministic scene state.
- Validate any model-proposed lead or action against the active interaction before showing it.

### P2 — The ECG looks real, but measurement resolution and evidence precision are mismatched

Strengths observed:

- plausible PTB-XL morphology and noise rather than stylized sine waves;
- conventional 3×4 sequential presentation plus continuous lead-II rhythm strip;
- 25 mm/s, 10 mm/mV, visible calibration mark, lead labels, and square grid;
- explicit source sampling rate and approximate 10-ms resolution;
- useful pan/zoom and a keyboard alternative.

Limits:

- Most tested signals were 100 Hz. Ten-millisecond resolution is reasonable for many teaching measurements, but insufficient for claims of finer boundary precision.
- Structured boundary fields can accept arbitrary decimal times and the grader calculates their difference rather than proving that both positions are sampled waveform landmarks.
- M9's single-trace proxy undermines realism even though the trace itself looks authentic.

Required fix:

- Snap every caliper to available samples and report the quantized interval and uncertainty.
- Use higher-resolution source data for fine J-point, QT-end, and subtle ST measurement tasks, or explicitly widen tolerances and prohibit finer claims.
- Visually bind accepted evidence to the trace so the learner and educator can audit it.

### P2 — Laptop layout is readable but forces excessive vertical context switching

At 1280 × 800, the scene rail remained 220 px wide and the stage was 712 px wide. The ECG itself was about 684 × 438 px. The full page was approximately 2,786 px tall. At 1024 × 768, the page reached 3,145 px.

The result is legible and does not overflow, but a learner repeatedly scrolls between the teaching copy, ECG, response surface, feedback, and tutor. The tutor—the feature that should support a tangent at the moment of uncertainty—sits at the bottom of the long scene.

Recommended fix:

- Allow the scene rail to collapse on laptop widths.
- Keep a compact sticky strip with active action, selected lead, measurement receipt, and tutor affordance.
- Permit the tutor to open as a side drawer without moving the learner away from the ECG.
- Collapse completed narrative layers after the task begins while preserving one-click recall.

## Module-by-module educator assessment

### M5 — Ventricular activation and conduction

The content is clinically sound and unusually good at avoiding mnemonic-only teaching. It separates width from morphology, uses paired V1/lateral evidence, states the adult complete/incomplete RBBB duration distinction, treats secondary recovery cautiously, and avoids calling long PR plus bifascicular morphology “trifascicular block.” The pacing frame of spike timing, chamber, capture, and sensing is appropriate.

The implementation currently fails to prove those skills. The first scene's graded mechanics are disconnected from waveform landmarks, and several target scenes have no eligible exemplar. M5 should not emit independent `localize` evidence until those contracts are repaired.

### M8 — Repolarization, QT, drugs, and electrolytes

The conceptual sequence is excellent: define baseline/J/T end; interpret recovery after activation; measure QT on more than one beat; report lead/method/uncertainty; compare Bazett and Fridericia; account for wide QRS; treat medication review as an evidence chain; and treat electrolyte patterns as hypotheses requiring labs. It avoids static drug lists and patient-specific orders.

The live corpus cannot support the QT measurement scene, and the arithmetic scene is broken. Those are not peripheral defects—they remove the two skills that make the rest of M8 clinically useful.

### M9 — Ischemia, infarction, localization, and mimics

The epistemic framing is a major strength. The module does not let a chronic PTB-XL tracing establish acute timing, culprit vessel, occlusion, activation, or treatment. It appropriately asks for distribution, reciprocal evidence, QRS context, PR/baseline findings, priors, serial data, and uncertainty.

However, the promised comparative corpus is not yet mounted in the runtime. A single locked tracing plus generic prose fields is not a mimic lab. Until real matched trios are available, label these scenes as authored reasoning rehearsals and do not display them as trace comparisons.

### M10 — Integrated transfer and source boundaries

`m10-s10` is scientifically excellent in concept. A resting 12-lead can answer axis and spatial morphology; a rhythm stream can establish transient onset/offset; pulse/perfusion require bedside assessment; and action sequences require a current reviewed algorithm. The explicit refusal to turn resting PTB-XL ECGs into ACLS mastery is exactly right.

The current branch feedback is too static, and the visual model is still a source-card exercise rather than a true resting-vs-stream comparison. Keep this scene—it is important—but make the time stream and bedside/algorithm boundary visually concrete.

## Case-contract and locked-path assessment

This is one of the best parts of the build. In M5 `m05-s2`, the platform clearly stated that no eligible RBBB exemplar existed, explained what each missing action could not prove, labeled each acknowledgement as formative, and ultimately reported that independent mastery was unchanged. The learner could not accidentally convert the unavailable tracing into independent RBBB evidence.

The remaining semantic problem is that scene progress still changes to “Complete” and the completion sentence asserts the target evidence. The UI needs two separate dimensions:

- content path: not started / covered / needs review;
- competency evidence: none / formative / independently demonstrated.

An educator should never have to infer the second from a paragraph beneath a large “Checkpoint complete” heading.

## Workload and curricular fit

The four reviewed modules alone advertise approximately 69, 80, 84, and 113 minutes of core path. That depth is defensible for a longitudinal curriculum, but not as four uninterrupted modules. Scenes are individually well sized at roughly 5–14 minutes; the platform should emphasize resumable chapters, diagnostic test-out, and targeted remediation rather than module completion.

The scene rail provides useful orientation, and the Recall / Now / Reuse strip is genuinely helpful. The design would become substantially more efficient if it foregrounded the current evidence task and let already-read narrative collapse.

## Release recommendation

Do not ship competency or mastery claims from the production guided modules until the P0 items are fixed and adversarially tested. The narrative can support a supervised content pilot now, especially the source-boundary teaching, but the learner record should be labeled formative-only during that pilot.

Minimum acceptance criteria before mastery claims:

1. Every visual subskill requires reviewed, trace-bound evidence that intersects the intended fiducial/ROI.
2. No correct duration, angle, keyword, or category can pass when attached to the wrong lead, wrong time, wrong waveform component, or unavailable case.
3. M8 QT/QTc tasks are answerable end to end with visible inputs and reproducible calculations.
4. M9 comparison scenes mount the promised case set.
5. All handoffs preserve the exact concept and subskill or show an explicit unavailable state.
6. Feedback contains no unresolved placeholders and is factually consistent with the submitted response.
7. Locked/formative completion is visually distinct from independent competency.

## Retest — fixed advanced blockers

Retest date: 2026-07-10  
Build: live `http://localhost:3100` after the targeted fixes  
Method: Chromium at desktop/laptop widths through the same live Playwright workflow used above. The in-app browser still exposed no attachable session; this remained a tooling limitation rather than a product result.

| Prior blocker | Retest result | Status |
|---|---|---|
| M5 `m05-s0` off-panel caliper and ungrounded localization credit | Off-window and wrong-panel times were rejected; visible V1 evidence was required. The second action is now explicitly an authored polarity model and credits mechanism only. | Fixed |
| M8 `m08-s4` missing QT/RR arithmetic inputs | QT 360 ms and RR 640 ms are visible; Bazett 450 ms and Fridericia 418 ms were independently accepted. | Fixed |
| M9 `m09-s8` locked prose proxy | The generic text table is no longer rendered when the case contract is locked. Both actions become explicit evidence-boundary acknowledgements and completion remains formative. | Fixed |
| M10 `m10-s10` factually wrong partial feedback | An all-`Resting 12-lead` response now receives neutral, accurate remediation rather than falsely claiming the rhythm-stream items were correct. | Fixed |

### M5 `m05-s0` — visible-boundary caliper and modeled polarity

The viewer now opened a short, case-specific window and restricted the V1 structured-entry fields to V1's visible sequential panel. I repeated the original adversarial inputs:

- V1 at 1.00–1.14 seconds, outside the displayed window: rejected with no task evidence.
- V1 at a time inside the overall window but outside V1's displayed panel: rejected with no task evidence.
- A visible V1 interval spanning 140 ms and overlapping the reviewed QRS region: accepted as waveform evidence.

The second action now states that it is an authored late-rightward teaching model and that it **does not localize morphology on the active patient tracing**. Completion required a 90° teaching vector plus positive terminal polarity in V1 and negative terminal polarity in V6. The resulting receipt read:

> Independent evidence recorded for explain mechanism.

No `localize` claim appeared. This resolves the original mastery-integrity blocker.

Small remaining usability issue, not a blocker: the structured fields' initial reviewed interval was 108 ms and produced a partial result against the packet duration, while the browser reported the prefilled decimal values as off-step relative to the 10-ms input increment. Align the prefilled boundaries, HTML step base, packet measurement, and accepted tolerance so the accessible default does not look internally inconsistent.

Retest screenshot: `ADV_RETEST_m05_complete.png`.

### M8 `m08-s4` — Bazett and Fridericia arithmetic

The scene now presents all required authored inputs in the prompt:

- QT 360 ms / 0.360 s
- RR 640 ms / 0.640 s

I entered 450 ms for Bazett. The action returned `Evidence aligned` and unlocked the next calculation. I then entered 418 ms for Fridericia, which also returned `Evidence aligned`. Each prompt explicitly said to use seconds inside the formula and enter the final result in milliseconds. The previous impossible units loop is resolved.

Retest screenshot: `ADV_RETEST_m08_450_418.png`.

### M9 `m09-s8` — locked mimic comparison

With the returned case still ineligible, action 1 now renders an `EVIDENCE BOUNDARY` instead of the ten-field target/mimic prose table. There were zero text inputs. After acknowledgement, action 2 was also an evidence-boundary state with zero text inputs. Completing both produced:

> SCENE COMPLETE · FORMATIVE EVIDENCE RECORDED

The page explicitly stated that independent mastery was unchanged. No unresolved feedback placeholders were present. This is the correct behavior until a valid target/mimic/normal set can be mounted.

Retest screenshot: `ADV_RETEST_m09_locked.png`.

### M10 `m10-s10` — source feedback

I again assigned all seven questions to `Resting 12-lead`. The new partial feedback said that some assignments were correct and directed the learner to reconsider spatial morphology, events over time, bedside pulse/perfusion, and the governed action sequence independently. It did not claim that the rhythm-stream questions were correct.

After assigning axis/spatial pattern to the resting 12-lead, pause/transient events to rhythm stream/telemetry, pulse/perfusion to bedside assessment, and action sequence to the reviewed algorithm, the response was accepted. The scientific source boundary remains intact.

Retest screenshot: `ADV_RETEST_m10_feedback.png`.

### Updated recommendation for these blockers

The four targeted advanced blockers are resolved in the live build. M5's corrected evidence contract is the most important change: it now distinguishes a real waveform measurement from an authored mechanism model and no longer converts the latter into visual localization mastery. The small accessible-default alignment issue above should be cleaned up, but it does not recreate the original route to false independent visual credit.

### Post-retest implementation closeout

The remaining precise-entry default was subsequently aligned to the reviewed sampled ROI rather than an arbitrary percentage of the visible lead panel. This removes the off-step/internally inconsistent starting interval while preserving boundary-overlap grading. The final full Playwright run passed 24/24 tests after this change.
