# Clerkship learner live report

> **Historical audit snapshot.** This report records the build and date named below; it is retained as defect-discovery evidence, not current product status. See [the remediation ledger](../PRODUCT_REMEDIATION_LEDGER.md) for reconciled fixes, verification, and remaining gates.

## Persona and test conditions

I tested as a time-pressured third-year medical student on clerkship with average ECG knowledge and a preference for learning through cases. The viewport was 1280 × 800, approximating a 13-inch laptop. I interacted with the running frontend at `http://localhost:3100` and the live backend at `http://localhost:8000` on July 10, 2026.

The in-app browser surface was not available to this task, so I used an isolated local Chrome session against the same live site. This means the findings cover the rendered application and networked behavior, but not the user's exact open tab or its pre-existing browser state. I made no implementation changes.

## Executive judgment

The curriculum copy is clinically thoughtful and substantially safer than a fact-recall product. M03.S14, in particular, teaches the distinction between ECG evidence, supplied context, and unknowns very well. The realistic waveform viewer, visible provenance, and refusal to turn resting ECGs into ACLS certification are also strong.

The present cross-mode implementation is not yet safe to use for competency tracking. A guided handoff can silently substitute a case from an unrelated concept and still record the attempt under the requested concept/subskill. This happened in Clinical, Training, and Rapid. Until a receipt is gated on exact agreement between the requested handoff, the selected case, the actual interaction, and the grounded objective, adaptive selection will learn from invalid evidence.

The second major problem is workflow density. Guided pages put too much curriculum chrome before the waveform, while a 45-second Rapid ward read asks for more typing than a clerk could reasonably complete. The strongest experience is the Clinical/Rapid waveform-first layout; the weakest is the long guided module header plus narrow scene rail plus raw source identifiers.

## Coverage completed

| Area | Live path exercised | Outcome |
|---|---|---|
| M3 clinical bridge | `/learn/rhythm-ectopy?scene=M03.S14` | Completed all three stages correctly; followed Clinical handoff |
| Clinical ward, untimed | `/practice?focus=ectopy&subskill=apply_in_context&support=guided&origin=rhythm-ectopy%3AM03.S14&returnTo=%2Flearn%2Frhythm-ectopy%3Fscene%3DM03.S14` | Started five-case Ward/Learn session and submitted the first ECG audit |
| M4 mechanism | `/learn/av-brady?scene=m04-s1` | Completed model exploration; acknowledged two unavailable evidence actions; followed Training handoff |
| Training measurement | `/train?focus=pr_qrs_boundaries&subskill=measure&support=guided&origin=av-brady%3Am04-s1&returnTo=%2Flearn%2Fav-brady%3Fscene%3Dm04-s1` | Performed caliper task; target fidelity failed before a valid receipt could be earned |
| M6 independent exit | `/learn/tachyarrhythmias?scene=m06-s11` | Inspected independent workflow and unavailable-case behavior |
| Rapid ward read | `/rapid?focus=tachyarrhythmia_mixed&subskill=recognize&support=independent&origin=tachyarrhythmias%3Am06-s11&returnTo=%2Flearn%2Ftachyarrhythmias%3Fscene%3Dm06-s11` | Started 45-second Ward read; verified silent tutor and first-case mismatch |
| M10 capstone | `/learn/integration-transfer?scene=m10-s11` | Inspected locked-case behavior and silent-tutor contract |
| Clinical ED, timed | `/practice?focus=integrated_chest_pain&subskill=apply_in_context&support=faded&origin=integration-transfer%3Am10-s8&returnTo=%2Flearn%2Fintegration-transfer%3Fscene%3Dm10-s8` | Started Emergency department/Shift case and checked disclosure, timer, and task realism |

## Severity-ranked findings

### P0 — Handoff target and competency receipt can describe a concept the learner never practiced

Three direct examples show a systemic target-fidelity failure.

1. M03.S14 generated the correct-looking URL for `ectopy × apply_in_context`, but the Ward session served “Chest discomfort on the ward” with an anterior ST machine-audit task. After a 50% attempt, the UI said: “Formative apply in context receipt recorded for ectopy · 15% independent mastery.” The backend profile then contained an `ectopy × apply_in_context` attempt and updated practice timestamp even though no ectopy evidence was present in that case.
2. M04.S1 generated `pr_qrs_boundaries × measure`, but Training opened a “Normal axis”/Normal ECG family drill and required an RR-interval caliper measurement. It did not measure PR or QRS boundaries.
3. M06.S11 generated `tachyarrhythmia_mixed × recognize`, but the first Rapid case was PTB-XL 11046. Its grounded packet was rate 60 bpm with sinus rhythm and RBBB, not tachyarrhythmia.

This is worse than imperfect recommendation quality. It contaminates spacing, attempts, remediation, and future adaptive case selection.

Recommended fix: resolve every handoff through one server-side contract before navigation. Require an eligible case whose grounded objectives contain the requested concept and whose interaction genuinely elicits the requested subskill. Return a signed/opaque selector receipt containing requested concept, actual case concept, subskill, eligibility tier, and interaction type. Record competency only when all fields agree. If no exact case exists, show “No eligible case currently available,” preserve the lesson, and create no attempt or spacing event.

### P1 — Clinical context can disclose the ECG interpretation before the learner commits

The timed ED handoff requested `integrated_chest_pain`, but it silently substituted a palpitations/AF case. The prompt said the ECG was shown “without a rhythm label,” while the first answer option read: “Irregular narrow-complex tachycardia consistent with AF…” That option supplies the diagnosis before an ECG-only commitment.

The backend may suppress a recognition score when a stem or option discloses the objective, but the learning experience is still compromised. The student can choose management without demonstrating that they saw AF.

Recommended fix: make relevant Clinical items explicitly two-stage. Stage 1 is a blinded ECG commitment (broad rhythm/category plus decisive trace evidence). Stage 2 reveals authored context and asks for the clinical decision. Grade recognition and management separately. Do not put the target diagnosis inside a pre-commit option.

### P1 — “Return to lesson” does not preserve exact activity state and disappears after a session begins

The generated `returnTo` parameters were accurate, and the M03.S14 scene completion flag survived reload. However, the completed scene reopened with its interaction reset to “Not submitted” at Stage 1; the three committed decisions were gone. This preserves completion status, not exact learner state.

Training kept a visible Return to lesson control during the active drill. Rapid and Clinical showed it on their setup screens but removed it once a round/shift began. A learner who realizes the handoff is inappropriate cannot return without abandoning the visible workflow through global navigation.

Recommended fix: persist the active action response, viewer marks, selected stage, tutor thread pointer, and completion receipt as a versioned scene-state object. Keep a persistent Return to lesson control in every active mode. On return, restore the precise scene/action state and show whether the destination attempt is incomplete, assisted, or completed.

### P1 — Independent scenes promise a collapsed/silent tutor but render an active tutor panel

M06.S11 says, “I’ll stay silent for the independent set.” M10.S11 says, “I’ll remain collapsed” and “Luna stays silent until submission.” Both rendered the full “Conversational Tutor · Tutorial mode” waypoint, an unsolicited opening message, and an enabled message textarea before submission.

This did not disclose the answer, but it violates the intended testing posture and adds distraction. Rapid handled this correctly: it showed “Tutor silent until commitment” and rendered no tutor input or coaching copy during the timed ECG.

Recommended fix: reuse the Rapid behavior. In independent guided scenes, render only a collapsed “Ask for help (marks attempt assisted)” control. Expanding it should freeze any timer, snapshot the exact viewer/draft state, and visibly convert the attempt to assisted before Luna responds.

### P1 — Unavailable/locked case behavior is internally contradictory

- M04.S1 had three actions. The model exploration worked, but the PR and QRS measurement actions were replaced by “Acknowledge evidence limit & continue.” Two thirds of a nominal five-minute mechanism scene therefore required no measurement.
- M06.S11’s independent exit opened on an unavailable case and could not perform the promised rhythm-march transfer.
- M10.S11 labeled the case “locked” and told the learner it “has been removed from your session,” yet still rendered an active sequence task and Check my evidence button on that same case.

The governance language is honest, but the interaction state is not. A locked task should not look actionable.

Recommended fix: perform case-contract resolution before the scene enters its task state. Choose an eligible equivalent, use an explicitly authored mechanism model where allowed, or lock the scene with one clear route to Training. Never render active scoring controls for a case described as removed.

### P1 — Rapid ward timing is incompatible with the amount of required input

The 45-second Ward read displayed the full 12-lead well and kept the tutor silent. The response then required:

- recognition tags;
- six text fields (rate, rhythm, axis, QRS/conduction, ST–T, and one-line synthesis); and
- confidence.

That is too much typing for a clerk using a laptop, especially after visually sweeping twelve leads. It rewards keyboard speed and terse field completion more than ECG interpretation. The 45-second Clinical ED MCQ was much more feasible, although it had the answer-disclosure problem above.

Recommended fix: separate timing objectives. A 20-second quick look should ask only for one broad category and one marked region. A 45-second ward read should use keyboard-friendly structured chips/shortcuts for rate/rhythm/axis/QRS/ST–T plus one optional spoken/typed line. The complete six-field narrative belongs in untimed mode. Timer performance must remain separate from mastery accuracy.

### P1 — The 13-inch guided hierarchy delays the actual learning task

At 1280 × 800, the module title, outcome, duration, raw source identifiers, completion card, recall/now/reuse band, and scene map consume the first viewport. The ECG workspace starts well below the fold. On M3, scene ID badges visually collided with or crowded the narrow scene titles. Long raw identifiers such as `SPEC-16...` read as internal metadata rather than learner guidance.

Clinical and Rapid were much better: the waveform occupied the central viewport immediately, with mode/status in a compact header.

Recommended fix: collapse module-level metadata after the first visit. Keep a compact sticky bar with module, scene, progress, and exit. Move sources to a disclosure panel. On laptop widths, make the scene map a drawer or horizontal chapter selector and give the ECG/task the primary column.

### P2 — One interaction can over-credit multiple subskills it did not explicitly elicit

M03.S14 used a three-stage option-selection interaction. Completing it recorded formative rows for `apply_in_context`, `synthesize`, and `calibrate_confidence` under premature atrial complex. The activity did not require a free synthesis or confidence estimate.

The clinical reasoning content was good, but the evidence does not justify all three receipts.

Recommended fix: each subskill receipt needs an explicit evidence predicate. For example, option selection can support apply-in-context; a learner-authored evidence/context/unknown statement can support synthesize; an elicited confidence with calibration outcome can support calibrate-confidence.

### P2 — Stated duration is inconsistent and too large for clerkship use without stronger chunking

M3 simultaneously stated “Usually 70–90 minutes” and “16 scenes · 153 min core path.” M10 stated about 113 minutes. A clerk is more likely to have 5–15 minutes between tasks than a continuous 90–150-minute block. M4’s 65-minute estimate also overstates productive time when some actions are unavailable acknowledgments.

Recommended fix: report chapter duration and “next useful stopping point,” not only module totals. Offer 8–12-minute resumable rounds with a visible clinical payoff. Recalculate duration from actual interaction medians and exclude locked acknowledgments.

### P2 — Training target selection is cognitively noisy

The Training screen exposed a very long concept selector with repeated concepts (for example RBBB, LBBB, QRS duration, AF, flutter, and AV block appeared in more than one grouping). It also displayed “Focused on Normal axis” while the target select value and classification family indicated other concepts. This compounds the handoff mismatch and makes the learner unsure what is being trained.

Recommended fix: when launched from a lesson, lock the target concept/subskill and show only the target plus 2–3 intentional mimics. Put “change target” behind an explicit escape hatch. Deduplicate the general catalog.

## What worked well

- M03.S14’s three decisions were clinically useful. They consistently rejected invented causation, waveform-derived instability, and patient-specific treatment. This clinical connection strengthened the lesson rather than distracting from it.
- ECG provenance was unusually clear. Real PTB-XL and synthetic authored waveforms were visibly distinguished, and blinded labels stayed hidden in Rapid before commitment.
- The rendered ECGs looked clinically credible at laptop size: standard 3 × 4 layout, lead-II rhythm strip, square grid, calibration, lead labels, and readable waveforms.
- The M04 mechanism model clearly separated AV delay (PR) from ventricular spread (QRS). The first model action was fast and conceptually effective.
- Rapid’s independent posture was correct: no tutor input or answer coaching appeared before submission.
- Rapid and Clinical both displayed a full 45 seconds after the task interface and waveform were rendered in my observations, which is the right timer boundary.
- The platform is appropriately explicit that resting PTB-XL data cannot certify resuscitation/ACLS skills. That boundary should remain.

## Recommended implementation order

1. Block all competency writes unless requested concept, grounded case objective, interaction type, and subskill predicate match exactly.
2. Make handoff selection fail closed: no silent cross-concept fallback.
3. Split Clinical recognition from management so context/options cannot disclose the ECG answer.
4. Persist exact scene/action/viewer state and keep Return to lesson visible inside active sessions.
5. Make independent tutor behavior truly collapsed; use Rapid as the reference implementation.
6. Resolve or lock case contracts before rendering task controls.
7. Redesign Rapid timing around low-typing structured inputs.
8. Compress guided laptop hierarchy and move source metadata behind disclosure.

## Overall clerkship verdict

The educational reasoning is promising enough that I would return to the product. I would not trust its current mastery map or adaptive recommendations because the cross-mode receipt can describe a different concept than the case I actually completed. Fixing that contract first would unlock the value of the otherwise strong case boundaries, realistic ECG viewer, and clinically literate explanations.

## Retest — cross-mode integrity after remediation

Retested against the live localhost build at 1280 × 800 after the cross-mode fixes. The in-app browser surface remained unavailable, so this used the same isolated local Chrome method as the original review. No product files were edited.

### Result summary

| Assertion | Result | Live evidence |
|---|---|---|
| M3 ectopy → Clinical fails closed | **Pass** | The handoff explicitly says no vetted clinical case can prove ectopy, disables Start shift, retains Return to lesson, and creates no substitute case or receipt. |
| M4 PR/QRS → Training preserves the measurement target | **Pass** | The route resolves `pr_qrs_boundaries × measure` to the vetted first-degree AV-block family and requires calipers across one PR interval. |
| M6 tachyarrhythmia → Rapid constrains the first case or fails explicitly | **Pass** | Setup explicitly maps the mixed handoff to the vetted AF family; first case PTB-XL 7215 is Tier A and its grounded objectives include `atrial_fibrillation`. |
| Return to lesson remains available after Rapid/Clinical start | **Pass** | Both active sessions displayed the control, and clicking it restored the exact originating scene. |

### 1. Ectopy → Clinical now fails closed correctly

Route retested:

`/practice?focus=ectopy&subskill=apply_in_context&support=guided&origin=rhythm-ectopy%3AM03.S14&returnTo=%2Flearn%2Frhythm-ectopy%3Fscene%3DM03.S14`

The setup screen now states: “No vetted clinical case family can currently prove ectopy. The handoff is locked; no substitute case or competency receipt will be created.” Start shift is disabled. The prior unrelated anterior-ST case is no longer served.

The learner profile still showed exactly the single historical `ectopy × apply_in_context` attempt from the original failing test, with its original timestamp. Opening and interacting with the locked setup did not add an attempt, change mastery, or update the practice timestamp. Return to lesson remained visible on the locked screen.

This is the correct behavior: transparent unavailability is much safer than a plausible-looking substitute.

### 2. PR/QRS boundary handoff now opens an appropriate measurement drill

Route retested:

`/train?focus=pr_qrs_boundaries&subskill=measure&support=guided&origin=av-brady%3Am04-s1&returnTo=%2Flearn%2Fav-brady%3Fscene%3Dm04-s1`

The handoff banner now explicitly explains that `pr qrs boundaries · measure` is being served through the validated First-degree AV block family because it supplies measurable PR and QRS boundaries. The initial target select value is `av_block_first_degree`, the subskill remains `measure`, the case is PTB-XL 98 (Tier A), and the waveform gate says: “Drag calipers across one PR interval before classifying.”

This fixes the prior drift to Normal axis/Rate and the unrelated RR-interval task. Minor caveat: the target and subskill selectors remain editable during a lesson-launched drill. The initial contract is correct, but changing either selector should visibly end or replace the handoff receipt contract so a learner cannot believe the modified task still satisfies the original remediation.

### 3. Tachyarrhythmia → Rapid now constrains and discloses the mapped family

Route retested:

`/rapid?focus=tachyarrhythmia_mixed&subskill=recognize&support=independent&origin=tachyarrhythmias%3Am06-s11&returnTo=%2Flearn%2Ftachyarrhythmias%3Fscene%3Dm06-s11`

The setup now says: “The first case is constrained to Atrial Fibrillation because the vetted tachyarrhythmia family supports rhythm discrimination; later cases interleave the corpus.” Starting the Ward read served PTB-XL 7215. Its live grounded packet was Tier A and included `atrial_fibrillation` among supported objectives. This replaces the prior unrelated sinus/RBBB case.

The mapping is explicit rather than pretending the corpus has a single `tachyarrhythmia_mixed` label. The Ward timer was also increased from 45 to 75 seconds and the copy now acknowledges avoiding a typing test, addressing part of the original timing concern.

### 4. Active Rapid and Clinical sessions now keep a functional return route

Rapid showed Return to lesson in the active ECG header after the timer began. Its href was `/learn/tachyarrhythmias?scene=m06-s11`; clicking it returned to that exact scene and the Tachyarrhythmia handoff content was present.

For Clinical, I used a valid tachycardia-with-pulse handoff because ectopy is intentionally unable to start:

`/practice?focus=tachycardia_with_pulse&subskill=apply_in_context&support=faded&origin=tachyarrhythmias%3Am06-s10&returnTo=%2Flearn%2Ftachyarrhythmias%3Fscene%3Dm06-s10`

After starting the timed Emergency-department case, Return to lesson remained in the active case header. Its href was `/learn/tachyarrhythmias?scene=m06-s10`; clicking it restored the exact “Tachycardia with a pulse: use the pathway” scene.

The active Clinical case also opened with an ECG-only first-look stage and kept symptoms, bedside context, and the decision prompt masked until commitment. That directly addresses the earlier diagnosis-disclosure problem for this case family.

### Retest verdict

The requested cross-mode integrity regressions are fixed in the live build. Handoffs now either map transparently to a grounded eligible family or fail closed, and active-mode return navigation works. The remaining small design decision is whether lesson-launched Training should lock its target selectors or explicitly invalidate the originating receipt when the learner changes them.

### Post-retest implementation closeout

Lesson-launched Training now locks both target and subskill selectors for the originating receipt. The learner can explicitly release that contract through **Let AI choose the weakest competency**, which starts a separate adaptive drill. The final full Playwright run passed 24/24 tests, including the targeted handoff cases.
