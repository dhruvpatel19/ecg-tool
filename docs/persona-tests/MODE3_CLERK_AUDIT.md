# Mode 3 clerkship audit — Rapid ECG rounds

> **Historical audit snapshot.** This report records the build and date named below; it is retained as defect-discovery evidence, not current product status. See [the remediation ledger](../PRODUCT_REMEDIATION_LEDGER.md) for reconciled fixes, verification, and remaining gates.

**Persona:** core-clerkship student using ECGs on ward rounds and during ED shifts  
**Audit target:** live production app at `http://127.0.0.1:3110/rapid`  
**Audit date:** 2026-07-12/13 (America/New_York)  
**Verdict:** **not release-ready as the requested Mode 3 competency product**. The current surface is a visually strong prototype of a blinded rapid-read loop, but several explicit Mode 3 requirements are absent and three live correctness failures can either make an item unanswerable or corrupt the experience.

## Testing method and scope

I first followed the installed in-app browser-control skill and its prescribed recovery path. Browser runtime setup succeeded, URL-based selection returned `No browser is available`, and the required one-time browser list check returned `[]`. I therefore used the repository's installed Playwright Chromium directly against the same live production URL. This is a direct rendered-site audit, not a source-only review.

The existing Rapid Playwright suite also passed against production:

- `2/2` tests passed: blinded untimed submission/feedback and tachyarrhythmia handoff fidelity.
- No console errors occurred in those tests.

I then exercised these additional live flows:

1. 1280×800 setup, ward runner, committed full read, deterministic feedback.
2. 75-second ward timer and 20-second quick-look timer.
3. An unattended quick-look timeout through automatic grading.
4. A five-ECG untimed round through the final debrief.
5. Reload during ECG 2 with a partially completed read.
6. 390×844 mobile setup and runner.
7. A targeted PVC `recognize` handoff switched to emergency quick-look.
8. A targeted AF `recognize` handoff under a newly registered isolated learner, including the stored mastery receipt.
9. API/corpus, adaptive-selector, grading, receipt, and responsive-layout inspection.

Generated evidence:

- [1280 setup](MODE3_1280_SETUP.png)
- [1280×800 viewport](MODE3_1280x800_VIEWPORT.png)
- [ward runner](MODE3_1280_WARD_RUNNER.png)
- [ward feedback](MODE3_1280_WARD_FEEDBACK.png)
- [emergency quick-look](MODE3_1280_EMERGENCY.png)
- [five-case debrief](MODE3_1280_ROUND_DEBRIEF.png)
- [390px runner](MODE3_MOBILE_RUNNER.png)
- [targeted PVC quick-look](MODE3_PVC_EMERGENCY_UNANSWERABLE.png)

## What is working

The current implementation has a credible foundation worth preserving:

- The setup screen is calm, legible, and clinically framed. Ward (75 s), quick-look (20 s), and untimed modes are distinguished in plain language without claiming ACLS certification.
- The 12-lead tracing is realistic and calibrated: sequential 3×4 layout, lead-II rhythm strip, 25 mm/s, and 10 mm/mV.
- Pre-answer payloads are genuinely blinded. The live `packet?blinded=true` response had `blinded: true` and did not expose `supported_objectives`; reports, concept labels, and grounded ROIs were absent until commitment.
- The tutor is absent during commitment, which is appropriate for an assessment mode.
- The timer starts when the viewer reports ready, not while the waveform is still loading. The displayed emergency clock moved from 20 s to 19 s after approximately 1.3 s. An untouched quick-look auto-submitted and reached feedback after the 20-second decision window plus grading latency.
- Deterministic feedback separates recognized, missed, and overcalled concepts and reveals waveform-grounded ROIs afterward.
- Real corpus integration is substantial. `/dataset/status` reported 21,799 PTB-XL records built, zero skipped, 21,157 Tier A/B student-facing cases, and all 12 fiducial leads. Rapid case selection uses the actual corpus rather than fixtures.
- Case avoidance worked in a five-case round: five distinct PTB-XL IDs were served.
- Adaptive selection is real at the coarse concept level. In the audited five-case round the backend repeatedly targeted the learner's weak `axis_normal` concept while varying the tracing, with the reason `low mastery, spacing, case clarity, and recent-case avoidance`.
- A targeted, authenticated AF-recognition flow produced an isolated `independent_transfer` receipt for `atrial_fibrillation × recognize`; the learner's independent mastery moved from its default 0.15 to 0.25 after one correct attempt.
- A deep-linked guided handoff preserves a visible Return to lesson action during the runner.
- At 1280px, the setup and full document did not overflow horizontally.

## Release blockers (P0)

### P0-1 — Emergency questions can be impossible to answer

Rapid declares 36 reachable case concepts but offers only 16 recognition choices. Twenty reachable concepts have no recognition option:

`rate`, `axis_normal`, PVC, PAC, Mobitz II, complete heart block, SVT, LAFB, LPFB, WPW, RVH, atrial enlargement, QT interval, nonspecific ST-T change, ischemia, anterior/inferior/lateral/septal MI, and pathologic Q waves.

This is not theoretical. I launched:

`/rapid?focus=premature_ventricular_complex&subskill=recognize&returnTo=/learn/rhythms?scene=m03-s10`

The selector correctly served Tier-A PTB-XL 219 with `premature_ventricular_complex` as its first target. I switched to time-pressured quick-look. The only response control was a 16-choice select, and there was no PVC/premature ventricular option. Because emergency mode removes all free-text sweep fields, the requested exact answer could not be submitted. See [targeted PVC quick-look](MODE3_PVC_EMERGENCY_UNANSWERABLE.png).

This can create a false missed objective and an invalid competency consequence from an unanswerable item.

Relevant implementation: `RECOGNITION_OPTIONS` versus `RAPID_CASE_CONCEPTS` in `frontend/src/app/rapid/page.tsx:96-123`.

### P0-2 — Mobile Rapid mode is globally wider than the viewport

At a 390×844 viewport, live measurements were:

- `window.innerWidth = 390`
- `document.documentElement.scrollWidth = 898`
- `document.body.scrollWidth = 898`
- ECG SVG bounding width = 880 px
- Commit button width = 836 px

The entire page—not just an intentionally scrollable ECG-paper region—expands to 898px. The answer form and submit button therefore sit mostly off-screen. See [390px runner](MODE3_MOBILE_RUNNER.png).

The intention in `globals.css:4558-4569` is sound: preserve calibrated morphology and scroll the paper *inside* the viewer. In Rapid, however, the grid item/card is allowed to take the SVG's min-content width, so that width escapes into the page. A clerk using a phone cannot reliably enter or submit an interpretation.

### P0-3 — Ordinary Rapid rounds do not create exact concept × subskill receipts

An ordinary round calls `api.nextCase("demo")` without a subskill. The adaptive backend therefore ranks coarse objective mastery, not an assessed Rapid subskill. After grading, the exact guided-event receipt is written only when all of these are true: a deep-link supplied `focus`, a deep-link supplied `subskill`, a validated handoff exists, and this is the first result (`page.tsx:198, 260`).

Consequences:

- A student who enters Rapid from the main navigation can complete 5–10 independent ECGs without creating any independent `recognize`, `localize`, `measure`, `discriminate`, `synthesize`, or confidence-calibration receipts.
- Ordinary case selection cannot respond to a weakness such as `RBBB × discriminate` versus `RBBB × recognize`; it only sees coarse RBBB mastery.
- The platform cannot prove the requested testing competencies or adapt Rapid item formats to the student's precise gap.

The generic `/attempts` path does update objective mastery, and targeted handoffs can write a valid independent receipt, but that is not equivalent to Mode 3 participating in the full competency model.

### P0-4 — The promised post-round AI and cross-concept synthesis are absent

The backend already generates an AI tutor response on every `/attempts` submission (`backend/app/main.py:251-280`). The five audited attempt responses included useful `suggestedNextStep` values, such as restructuring the read into rate/rhythm/axis/intervals and anchoring observations to a lead. The frontend reads `response.grade` and drops `response.tutor` (`page.tsx:237-258`).

After each case there is no tutor question, no Ask why/Ask the tutor affordance, and no adaptive explanation. The five-case debrief contains only average score, completion, average response, timeout count, five IDs/scores, Repeat this round, and Change setup. It has no:

- AI synthesis of error patterns;
- cross-concept connection;
- confidence calibration;
- recommended next competency;
- rationale for the next case family;
- learner-controlled question entry;
- link to a relevant tutorial or competency lab.

The visible runner text says `Tutor silent until commitment`, which reasonably implies availability after commitment, while no tutor becomes available. The sidebar simultaneously says `AI coach ready`.

This is a central requested capability, not optional polish.

### P0-5 — Dynamic and varied assessment interactions are not implemented

Every non-emergency case uses the same recognition pills plus six text inputs; every emergency case uses the same select plus confidence. The ECG viewer receives `toolbar="none"` before commitment and no `task` at all (`page.tsx:509`). After commitment the generic toolbar appears, but no waveform action is requested, graded, or attached to mastery.

There are no live Rapid items for:

- pointing to an abnormality;
- drawing a region or localizing across contiguous leads;
- caliper measurement;
- marching rhythm markers;
- matching morphology to diagnosis;
- fill-in-the-blank numeric intervals;
- ordered/sequential reveal;
- normal-versus-abnormal discrimination pairs.

The text fields are arranged in a systematic order, but all appear at once. This is a static form, not sequential interpretation. Mode 3 therefore does not yet satisfy the explicit requirement to go beyond repetitive MCQ/static forms or reuse the tutorial's dynamic ECG interactions.

## Major findings (P1)

### P1-1 — A 1280×800 timed user must scroll before seeing any answer control

In the exact 1280×800 viewport, the answer panel began at `y = 794.16` and ended at `y = 1251.16`. In other words, the entire first screen is the tracing; the quick-look answer control begins below the fold. This is workable untimed, but it wastes part of a 20-second emergency round on scrolling and breaks the visual connection between tracing and commitment. A sticky compact answer rail or responsive two-column composition is needed for timed desktop/laptop use.

### P1-2 — Reload or interruption destroys the active round

During ECG 2 I entered `88 bpm` and reloaded. The app returned to the initial Rapid setup; pace, case index, completed results, current case, and draft were lost. All active state is component `useState`; there is no session/local storage or server round object (`page.tsx:133-153`). Return-to-lesson navigation similarly does not preserve a resumable Rapid round.

For clerkship use, an accidental refresh, device sleep, network transition, or brief tutorial tangent must not erase an assessment session. Timed resume policy should be explicit and fair.

### P1-3 — Grading is opaque and can feel contradictory

In one live ward read I selected Sinus rhythm and entered a systematic sentence. Feedback was 25%: AF-style recognition was not involved, but normal axis, QT interval, and rate were graded as missed. In the five-case run I deliberately chose the visible `Normal ECG` pill and wrote `Normal ECG on structured rapid review` on five backend-selected normal/axis cases. Every score was 0%, even where the revealed teaching points said `normal ECG`, because the four graded objectives were higher-tier component labels such as axis/rate/sinus/QT and `normal_ecg` fell outside the four-objective grading slice.

The app does not show which dimensions are scored, how a broad normal interpretation maps to component findings, or why a correct supported label receives no score. A broad normal call should either earn bounded credit while components remain required, or the prompt must explicitly say that every field is independently scored.

Targeted handoffs add another ambiguity: the AF-recognition transfer correctly recorded `AF × recognize`, but the same full-read attempt also lowered axis, rate, and QT objective mastery. If this is deliberate mixed assessment, disclose it before commitment; otherwise set a focused grading scope.

### P1-4 — Adaptive selection works, but its plan is invisible

The backend returned a clear reason and target objectives on every selection. The five-case run repeatedly focused Normal axis and varied case IDs, which is a reasonable mastery response. None of that reason, target, or progression is shown after submission or on the debrief. From the learner perspective the round appears random and five 0% cases look punitive rather than intentionally repetitive.

The next-item policy also receives no current-session item-format plan. It can vary cases based on persisted concept mastery, but it cannot deliberately choose `point → discriminate → synthesize` or interleave concepts after a criterion is met because ordinary Rapid items have no declared assessed subskill.

### P1-5 — Debrief cannot support deliberate improvement

Case rows are inert. A learner cannot reopen the tracing, compare their read to the reference, inspect recognized/missed/overcalled findings, see confidence versus correctness, or ask a question about a specific case. Timing is shown only as an average and per-row value; trends and outliers are absent. A 0%/5 case debrief provides no actionable route other than rerunning another opaque round.

### P1-6 — Raw PTB reports reduce feedback clarity

The feedback surface exposes untranslated and sometimes mojibake source reports, for example `supraventrikulÃ„ra extraslag` and `unbestÃ„tigter bericht`. The raw report is valuable provenance, but it should sit behind a Source details disclosure. The primary grounded reference should be normalized English concept language and reviewed measurements.

### P1-7 — Confidence is collected but not taught

Confidence is stored and high-confidence errors influence backend mastery, but Rapid never explains calibration, plots confidence against correctness, flags confident overcalls, or proposes an uncertainty exercise. The requested `calibrate_confidence` competency is only possible through a special handoff receipt, not through the normal round experience.

## Minor findings (P2)

- `Repeat this round` does not repeat the same cases; it launches fresh adaptive selections. Rename it `Start another round` or add a genuine replay option.
- The unattended quick-look reached feedback about 23.9 seconds after the heading appeared: a 20-second response window plus approximately four seconds of grading. During that latency, the interface should explicitly say `Time expired — grading your committed blank response` so the student understands what happened.
- The feedback case identity is primarily a PTB-XL number. A short learner-facing summary is needed after reveal; keep the source ID as provenance.
- The static 5/10 length choices are adequate for MVP, but a one-case shift interruption drill and a custom-length option would better fit clerkship time constraints after the core issues are fixed.

## Clerkship workflow assessment

| Requirement | Current evidence | Verdict |
|---|---|---|
| Ward versus emergency versus untimed pacing | 75 s, 20 s, and untimed are implemented; clocks start on viewer readiness | Partial pass |
| Systematic sequential interpretation | Ordered fields exist, but all reveal simultaneously and nothing enforces a sequence | Partial/fail |
| Blinded pre-answer state | Live packet and UI stayed blinded; tutor absent | Pass |
| Dynamic waveform localization/annotation | No pre-answer task or graded viewer evidence | Fail |
| Non-MCQ variety | Pills/select plus free text only; same template every case | Fail |
| Corpus breadth | Full PTB corpus ingested, 21,157 Tier A/B cases eligible | Pass |
| Answerability | 20/36 reachable concepts absent from the only emergency response control | Fail |
| Per-case deterministic feedback | Recognized/review/missed/overcalled and post-reveal ROIs | Pass with clarity issues |
| AI after commitment | Backend response generated but discarded; no learner-facing AI | Fail |
| Round-level AI/cross-concept synthesis | Not present | Fail |
| Adaptive next cases | Coarse concept adaptation and no-repeat selection work; rationale hidden | Partial |
| Exact concept × subskill mastery | Works for special first-case handoffs only; ordinary rounds omit it | Fail |
| Interrupt and resume | Reload resets the round and draft | Fail |
| 1280×800 usability | No horizontal overflow, but all response controls begin below fold | Partial |
| Mobile usability | Global width expands from 390 to 898 px | Fail |
| Authenticated isolation | Verified with a correctly initialized registered learner and exact AF receipt | Pass |

## Release acceptance criteria

Mode 3 should not be accepted until all P0 criteria and the interruption/mastery-integrity P1 criteria are covered by automated tests and a repeat persona pass.

### 1. Item contract and answerability

- Every Rapid item must declare `caseId`, grounded target concepts, assessed subskills, pace-compatible question blueprint, acceptable evidence types, grading scope, and competency-receipt policy before it is shown.
- A server/client invariant must prove that every reachable target has at least one valid response path in the selected pace. If not, the case fails closed before presentation.
- Add a coverage test across all 36 current Rapid concepts and every enabled blueprint. The targeted PVC emergency flow must contain a valid PVC answer/evidence path and must never penalize an unanswerable target.
- Do not use one hard-coded option list for all cases. Generate distractors and response controls from the item's validated target family.

### 2. Genuine interaction variety

- Implement and rotate at least these grounded blueprints: dominant-finding select, structured full read, numeric FITB, point-to-abnormality, lead/territory region selection, caliper measurement, rhythm marching, morphology/diagnosis matching, and paired normal-versus-abnormal discrimination.
- Select only blueprints supported by reviewed case evidence (ROIs, fiducials, measurements, or explicit labels). Missing evidence must be neutral/fail-closed, never incorrect.
- At least one waveform action must appear in a normal five-case round when eligible cases exist, and its evidence must be included in deterministic grading and mastery.
- Sequential-read items should stage rate → rhythm → axis → intervals/conduction → ST-T → synthesis, while allowing a deliberate `show full form` accommodation in untimed mode.

### 3. Exact mastery and adaptive policy

- Every ordinary Rapid item must write exactly the independent concept × subskill receipts it can prove, not just generic objective mastery and not only when launched from a tutorial.
- The adaptive selector must receive the intended subskill/blueprint and use independent mastery, high-confidence error, spacing, case clarity, and recent-case avoidance at that exact level.
- The response must expose an auditable `why this case / why this task` rationale after commitment.
- A test must demonstrate: miss `RBBB × discriminate` → receive eligible RBBB/LBBB discrimination cases → improve that exact receipt → interleave a different competency after the mastery criterion, without substituting unrelated cases.
- Targeted handoff grading must either scope penalties to the announced target or explicitly disclose that the remaining systematic read is also scored.

### 4. Learner-facing AI

- Keep AI silent and diagnosis fields blinded before commitment.
- After deterministic grading, expose a compact optional tutor that consumes the grade, learner evidence, confidence, viewer state, and allowed grounded case claims. It may explain and ask Socratic follow-ups but must not rewrite the deterministic grade.
- Use the already-returned tutor response rather than discarding it, and provide a visible `Ask about this ECG` affordance.
- At round end, generate a grounded synthesis of repeated misses, overcalls, confidence calibration, speed/accuracy trade-offs, and cross-concept relationships; cite the exact cases/objectives behind each statement.
- Offer 2–3 explainable next actions (targeted training, guided refresher, another Rapid round) and clearly distinguish AI recommendation from mastery policy.

### 5. Debrief and interruption recovery

- Each debrief row must reopen the case, learner answer, deterministic grade, ROIs/measurements, confidence, and response time.
- Persist the round server-side or in durable client state after case selection, every draft change, and every result. Reload and Return to lesson must restore pace, case index, results, and the current draft.
- Define a fair timed-resume rule: pause on a deliberate tutorial tangent; after crash/reload either resume with a clearly displayed remaining time or mark the item interrupted and serve a fresh case without mastery penalty.
- `Repeat this round` must replay the same cases, or the control must be renamed `Start another adaptive round`.

### 6. Responsive clinical workspace

- At 360, 390, 768, 1024, and 1280px, assert `document.documentElement.scrollWidth === window.innerWidth`.
- Preserve ECG calibration inside a dedicated horizontal paper scroller; the viewer card, answer panel, and submit button must remain viewport-bound.
- At 1280×800 quick-look, the dominant-finding control, confidence, timer, and commit button must be visible without page scrolling. A tracing plus sticky/side answer rail is acceptable.
- Repeat the mobile and 1280 screenshots and a touch/keyboard submit flow after the layout correction.

### 7. Feedback quality and safety

- Primary feedback must use normalized English concept labels and reviewed measurements. Put the raw multilingual PTB report behind Source details and fix text encoding.
- Timed-out feedback must explicitly say the item timed out and distinguish response-window time from grading latency.
- Preserve the current honest statement that emergency quick-look is not ACLS/acute-event certification.

## Recommended retest scenarios

1. New learner, five untimed cases: verify at least three question blueprints, exact receipts, and a useful round synthesis.
2. Repeated weak RBBB discrimination: verify adaptive repetition to criterion, then interleaving.
3. PVC targeted quick-look: verify answerability and an exact independent receipt.
4. 20-second quick-look at 1280×800: answer without scrolling; verify timer, auto-submit, and timeout copy.
5. Refresh at ECG 2/5 with a partial answer: restore without loss or unfair penalty.
6. Navigate to a tutorial tangent and return: restore the exact case/round state.
7. 390×844 mobile: paper scrolls internally; form and commit control remain 390px-bound.
8. Five-case debrief: reopen a case, ask the tutor a grounded question, follow a cross-concept recommendation, and verify the resulting route.
9. Authenticated two-user isolation: prove attempts, exact receipts, round state, and AI thread never cross accounts.

## Bottom line

The current Rapid mode successfully proves that realistic PTB-XL tracings, blinding, deterministic grading, clocks, and coarse adaptive selection can work together. It does **not** yet implement the requested testing mode as a complete learning system. The next iteration should retain the visual restraint and evidence boundaries while replacing the static universal answer form with a grounded item contract, exact subskill receipts, varied waveform interactions, durable rounds, and an actual post-commit/post-round AI learning loop.
