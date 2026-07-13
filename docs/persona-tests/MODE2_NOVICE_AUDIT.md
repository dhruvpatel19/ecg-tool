# Mode 2 novice learner audit

**Audit date:** 2026-07-12  
**Persona:** First-year medical student; low ECG confidence; keyboard-first; expects the app to explain why, provide a clear practice goal, and avoid assuming prior pattern fluency.  
**Scope:** Current live application at `http://127.0.0.1:3110`, especially `/train`, registration/sign-in/sign-out, first-use experience, target selection, question variety, tutor behavior, feedback, mastery visibility, account isolation, and 390 × 844 mobile behavior.

## Verdict

The implementation has a credible technical foundation but is not yet a comprehensive novice Training mode.

What is real and working:

- Registration, sign-in, sign-out, session restoration, and authenticated learner isolation worked in the live UI.
- A committed attempt for Learner A remained attached to Learner A after logout/login; a separately registered Learner B began with zero attempts.
- The selector served a different RBBB case after submission (`PTB-XL 5392` then `PTB-XL 5704`), so recent-case avoidance is not merely marketing copy.
- The tracing is real, blinded before commitment, calibrated, interactive, and paired with a grounded reveal.
- Localize and measure add waveform point/caliper gates. The keyboard caliper alternative and all principal Training controls were reachable by Tab once loading completed.
- The profile distinguishes concept-level mastery from concept × subskill evidence, and the wrong independent RBBB recognition attempt visibly lowered recognition evidence.

What prevents this from meeting the proposed product standard:

- “Training” is still predominantly one classification-button task plus one generic evidence textarea. Eight selector labels do not equal eight meaningfully different learning interactions.
- There is no first-use diagnostic/onboarding path. A new learner is assigned 25% mastery and told to make Normal ECG “unmistakable” without reporting confidence, stage, goals, accessibility needs, or a baseline performance sample.
- The advertised `5 focused · 2 contrast · 1 transfer` plan is not an implemented, visible Training session. The page presents one case and a generic “Next adaptive case” button without a set counter, mastery criterion, transition rule, or session debrief.
- Mobile Training has document-level horizontal overflow and puts target selection after a long ECG in reading order.
- Post-answer AI was safe but educationally unhelpful for a novice’s straightforward conceptual question.
- The current authentication layer isolates profiles, but its learner-facing validation and production security/recovery surface are still prototype-level.

I found **no P0 cross-account data leak** in the tested flow. The P1 findings below should block declaring Mode 2 and “proper student authentication” complete.

## Method and evidence

The prescribed in-app browser runtime was initialized first. Browser selection returned `No browser is available`; the required troubleshooting documentation was read, and the single allowed browser inventory check returned an empty list. I therefore used the repository’s existing Playwright installation as the instructed last resort, driving the live production server on port 3110.

Baseline live regression:

```text
E2E_BASE_URL=http://127.0.0.1:3110
npx playwright test e2e/auth.spec.ts e2e/train.spec.ts --project=chromium
5 passed
```

Adversarial persona exercise:

```text
E2E_BASE_URL=http://127.0.0.1:3110
npx playwright test e2e/mode2-novice-audit.spec.ts --project=chromium --reporter=list
3 passed
```

The audit exercise is preserved at [`frontend/e2e/mode2-novice-audit.spec.ts`](../../frontend/e2e/mode2-novice-audit.spec.ts). Its assertions cover account separation/restoration, a two-case adaptive transition, tutor availability, mobile geometry logging, keyboard access, and registration validation.

Key screenshots:

- [Sign-in page](./mode2-novice-login-desktop.png)
- [First authenticated dashboard](./mode2-novice-first-dashboard.png)
- [Training before commitment](./mode2-novice-train-desktop-before.png)
- [Wrong-answer feedback and grounded reveal](./mode2-novice-feedback-tutor.png)
- [Tutor answer to the novice question](./mode2-novice-tutor-answer.png)
- [Localize subskill state](./mode2-novice-localize-desktop.png)
- [Authenticated profile after the attempt](./mode2-novice-profile-after-attempt.png)
- [Mobile full page](./mode2-novice-train-mobile-full.png)
- [Mobile clipped viewport](./mode2-novice-train-mobile-top.png)
- [Weak-password validation](./mode2-novice-register-validation.png)

## Tested learner journey

1. Opened sign-in and registration on desktop.
2. Registered Learner A and inspected the first authenticated dashboard.
3. Opened an RBBB recognition drill and enumerated all visible target/subskill choices.
4. Submitted an incorrect independent answer, inspected mastery feedback and source evidence, and opened the post-answer tutor.
5. Asked: “I am a first-year student: why does V1 matter here, and how is this different from LBBB?”
6. Requested the next case and confirmed the case changed from 5392 to 5704.
7. Attempted to change subskills inside the selected RBBB deck.
8. Released the locked handoff using “Let AI choose the weakest competency,” then tested Localize.
9. Returned to the dashboard, confirmed Learner A had one attempt, signed out, registered Learner B, and confirmed Learner B had zero attempts.
10. Signed back in as Learner A and confirmed the attempt was restored.
11. Inspected the authenticated progress page and concept × subskill receipt.
12. Repeated Training at 390 × 844, selected Measure, inspected document geometry, and followed keyboard focus through the ECG, precise-entry alternative, selectors, options, confidence, and hint controls.
13. Submitted a one-character registration password and inspected the resulting error.

## Findings

### P1 · Ordinary target links are treated as locked lesson handoffs

The dashboard uses `/train?concept=...`, but `/train` interprets any `concept` query as a formal handoff. Both Target concept and Target subskill become disabled, while the page says “This lesson target is locked.” The learner did not come from a lesson.

The only visible release is “Let AI choose the weakest competency.” In the live exercise, releasing the RBBB deck changed the target to Rate. A learner who deliberately chose RBBB therefore cannot switch from Recognize to Localize/Measure while preserving RBBB.

This conflicts directly with the Mode 2 promise of repeatedly training different competencies within one specific finding.

**Acceptance criteria**

- Treat `concept` as a normal preselection with editable concept and subskill controls.
- Reserve locked receipt semantics for an explicit handoff contract, such as `focus + returnTo + support`, or a signed handoff identifier.
- Provide an “Unlock controls” action that preserves the current concept when a true handoff is released.
- Add a live test: dashboard → Train RBBB → change Recognize to Localize → target remains RBBB and the receipt is RBBB × Localize.

### P1 · Question variety is mostly nominal

The page exposes eight subskills, which is a good competency taxonomy. The actual runtime uses only two waveform task variants:

- `localize` → point on the tracing;
- `measure` → calipers, but only when that concept maps to QT, PR, RR, or QRS.

Recognize, discriminate, explain mechanism, synthesize, apply in context, and calibrate confidence all return to the same classification choices plus the same “Evidence or mechanism statement” textarea. Classification remains mandatory in every drill. There is no Mode 2 matching, ordering, lead-to-territory mapping, cloze/FITB, normal-versus-abnormal sorting, multi-select feature bundle, progressive feature construction, or error-correction task.

**Acceptance criteria**

- Define an authored interaction contract per concept × subskill rather than changing only the heading and text requirement.
- Include at least: waveform point/region, caliper, matching, ordering, FITB/numeric entry, compare-two-tracings, feature multi-select, mechanism chain, and short clinical implication.
- Classification should be optional when it would contaminate the targeted skill; e.g. measurement training can grade the interval without requiring a diagnostic label.
- An automated coverage test must fail when a targetable subskill has only the generic classification-plus-text template.
- A five-case session should contain at least three materially different response mechanics when the concept supports them.

### P1 · “Repetitive/adaptive session” is only a next-case loop

The dashboard promises `5 focused tracings · 2 contrast cases · 1 transfer case`. Live Training did change case IDs and displayed “low mastery, spacing, case clarity, and recent-case avoidance,” which supports a real selector. However, the learner sees no session counter, current phase, mastery threshold, streak/stability measure, reason the next case changed, planned mimic, or transfer checkpoint.

There is also no end-of-set debrief showing what stabilized, what remains weak, or why the next mode is appropriate. This feels like repeated single items rather than competency acquisition.

**Acceptance criteria**

- Materialize the promised set as a session object with focused, contrast, interleaved, and transfer phases.
- Show `case n of m`, current subskill, independent/assisted status, and the next transition rule without exposing the answer.
- Continue concentration until a declared stability criterion is met; then interleave a close mimic and later a transfer item.
- Do not count duplicate or ungrounded cases toward the session.
- End with a concept × subskill receipt, misconception summary, delayed-recheck recommendation, and explicit handoff to Rapid or Clinical only when readiness criteria are met.

### P1 · Mobile width expands from 390 px to 545 px

At a 390 × 844 viewport:

```text
window.innerWidth = 390
document.documentElement.scrollWidth = 545
```

The page header, selection note, Training grid, viewer, and rail all measured about 529 px wide. The visible viewport clips right-side copy and controls; horizontal panning is required. The likely layout trigger is intrinsic grid/select width propagating through the single-column Training grid.

The target panel also occurs after the full ECG and provenance in mobile reading order. A novice who arrives without a preselected target must move through a large tracing before choosing the exercise.

**Acceptance criteria**

- At 320, 375, 390, and 430 px, document scroll width must be no greater than viewport width plus 1 px.
- Use `minmax(0, 1fr)`, `min-width: 0`, and constrained select/button copy at the Training container and grid-item boundaries.
- Keep only the ECG canvas internally scrollable when preserving calibrated scale; surrounding page content must not widen.
- Put a compact target/subskill/session bar before the viewer on mobile; keep the detailed mastery panel later.
- Add a 390 × 844 screenshot and geometry assertion to the permanent Training suite.

### P1 · Tutor grounding suppresses useful first-principles teaching

After reveal, the novice asked why V1 matters and how RBBB differs from LBBB. The tutor responded that it could not support “that statement” from curated evidence and asked the learner to name a visible feature. It cited the case’s RBBB report and QRS duration, then said no validated V1 ROI or explicit V1 morphology was supplied.

The safety boundary is appropriate for case-specific morphology. The educational response is not. The learner asked a general conceptual comparison, not for an unsupported assertion about this trace. A useful answer should have separated:

1. **General principle:** V1 is a right-precordial view; delayed right- versus left-ventricular activation produces different terminal directions in V1 and lateral leads.
2. **Typical contrast:** RBBB and LBBB morphology at a conceptual level.
3. **This case:** what is and is not independently supported by its reviewed geometry/report.

**Acceptance criteria**

- Classify tutor questions as general concept, case observation, or clinical action.
- Answer safe general concepts even when case ROI evidence is absent, while clearly labeling them “general teaching, not proof for this tracing.”
- Cite case evidence only for case claims.
- Include a novice-readable explanation and a single check-for-understanding question.
- Add regression prompts for “why does this lead matter?”, “how is A different from B?”, and tangents after both correct and incorrect attempts.

### P1 · No genuine onboarding or baseline diagnostic

Registration leads directly to a polished dashboard. The fresh profile begins with uniform 25% concept mastery and recommends Normal ECG. There is no explanation that 25% is a prior/default rather than measured ability.

No first-use flow captures training stage, ECG exposure, course goals, preferred pace, accessibility/keyboard needs, or confidence. No baseline normal/abnormal discrimination sample verifies the recommendation. The displayed personalized plan therefore looks more certain than its evidence.

**Acceptance criteria**

- Label unmeasured objectives as “not yet assessed,” not a learner-facing numeric mastery score.
- Offer a short, skippable onboarding flow: training level, goals, confidence, accessibility preferences, and desired session length.
- Use a small diagnostic set with at least normal, rate/rhythm, interval, and one high-yield morphology; record uncertainty rather than forcing mastery from one item.
- Explain why the initial target was chosen and distinguish profile priors from observed evidence.

### P1 · Auth is isolated but not production-ready student authentication

Positive evidence:

- Passwords are hashed with PBKDF2-HMAC-SHA256 and per-password salts.
- Sessions are opaque and revocable.
- The backend resolves the bearer token over client-supplied `learnerId`, preventing a logged-in client from selecting another learner profile.
- The direct UI isolation exercise passed: A = 1 attempt, B = 0, restored A = 1.

Remaining production gaps:

- Minimum password length is six characters with no learner-facing password requirements.
- A short password produces “That username is taken or invalid,” which is factually wrong and prevents correction.
- There is no recovery/reset flow, email or institutional identity linkage, verification, session/device management, or visible privacy/consent information.
- Bearer tokens are stored in `localStorage`; the current design therefore depends heavily on perfect XSS prevention.
- No rate limiting/lockout protection is evident at the authentication boundary.

**Acceptance criteria**

- Return structured field errors and display the actual password/username problem beside the field.
- Establish a production auth threat model and choose hardened cookie-based sessions or document/mitigate localStorage token risk.
- Add login throttling, session rotation/expiry UX, reset/recovery, and session revocation.
- Define institution/SSO and privacy requirements before real student deployment.
- Preserve the current effective-learner override and add cross-account negative tests for profiles, attempts, tutor threads, review sessions, and clinical sessions.

### P1 · Authenticated mastery UI contains trust-breaking contradictions

The authenticated page correctly titled itself “Novice A progress” and showed one isolated attempt, but the card beneath that count said **“Shown from the demo learner profile.”**

After one wrong RBBB attempt, the page simultaneously showed:

- RBBB Recognize independent competency: 9%;
- legacy RBBB concept signal: 19%;
- the same RBBB 19% row twice (recent movement and the priority list);
- no misconception, despite the submitted LAFB overcall;
- a “Recommended Next” RBBB case whose action links to `/practice` rather than `/train`.

These signals may have valid internal meanings, but the novice-facing hierarchy does not make them understandable.

**Acceptance criteria**

- Remove demo-specific copy for authenticated learners.
- Explain the difference between concept aggregate and concept × subskill evidence in situ, including priors and evidence counts.
- Do not duplicate the same row in adjacent lists.
- Persist the learner’s observed wrong contrast as an actionable misconception or explain why it did not qualify.
- Route a concept × subskill recommendation to the exact Training deck; use Clinical only when the recommendation is explicitly contextual transfer.

### P2 · Feedback contains irrelevant and raw source material

On an LAFB selection for an RBBB case, feedback also said “Overcalled or unsupported here: Anterior MI,” although the learner did not select Anterior MI. The grounded evidence included untranslated/raw report text with mojibake (`unbestÃ¤tigter`) and “teaching points” that read like label-confidence exports rather than authored instruction.

**Acceptance criteria**

- Feedback names only the learner’s submitted claim, required omitted claims, and directly relevant close mimics.
- Normalize encoding and translate or hide report strings that are not learner-ready.
- Convert confidence exports into authored explanations: feature → mechanism → discriminator → implication.

### P2 · The mobile keyboard path is functional but inefficient

Once the measurement case finished loading, Tab reached the ECG canvas, “Keyboard / precise-entry alternative,” concept and subskill selectors, classification options, evidence note, confidence, and hint. This is a meaningful success.

However, DOM order places the full viewer and its many toolbar buttons before target selection. Several icon-only controls had no readable text in the audit trail, and the selected point/caliper gate leaves Commit disabled without a concise focus move to the missing requirement.

**Acceptance criteria**

- Give every viewer button a unique accessible name.
- On disabled commit, expose a nearby status naming the missing evidence and provide a focusable jump to it.
- Place compact session controls before the detailed viewer controls in mobile keyboard order.
- Verify the entire measurement submission using only keyboard controls at 390 × 844.

## Proposed novice Mode 2 acceptance scenario

A clean completion test should be possible without internal knowledge:

1. A new student registers and sees an honest “not yet assessed” state.
2. They choose or accept RBBB × Recognize and begin a clearly bounded five-item focused phase.
3. Case mechanics vary: feature multi-select, point in V1, compare V1/V6, short discriminator cloze, and classification.
4. Wrong answers produce contrast-specific feedback, not unrelated overcalls.
5. The tutor answers general conceptual questions while keeping case claims grounded.
6. The selector repeats RBBB with nonduplicate morphology until a declared stability criterion is met.
7. It then serves LBBB/IVCD close mimics and finally an unannounced transfer case.
8. The session ends with a readable RBBB × subskill receipt and a scheduled independent recheck.
9. Logout/login restores the exact learner state; another account sees none of it.
10. The complete flow works at 390 × 844 with no document overflow and with keyboard-only pointing/caliper alternatives.

Until that scenario passes, the current implementation should be described as a strong Training prototype, not a finished adaptive competency-building mode.
