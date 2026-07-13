# Learner persona review — round 2

Status: post-implementation adversarial review, July 2026. This report is a product-learning audit, not clinical validation.

## Method and evidence boundary

Three independent reviewer personas were used:

- **Maya — early pre-clerkship novice:** visually oriented, anxious about ECG math, variable attention, needs plain-language causal explanations and recoverable mistakes.
- **Jordan — clinical clerk:** case-first, time-poor, needs a usable bedside workflow, defensible handoff language, and a fast path that does not weaken the comprehensive course.
- **Priya — advanced learner:** challenges source agreement, measurement validity, mimics, timing, grounding, and whether the assessment actually measures its stated construct.

The root implementation agent directly exercised the production build in the in-app browser at laptop width. The persona workers attempted to obtain browser control, but that capability was unavailable in their worker contexts. They therefore reviewed production screenshots, DOM/browser findings supplied by the root agent, the storyboard, implementation code, API responses, and regression evidence. They did **not** claim direct clicking. This limitation means the next iteration still requires sessions with real representative learners.

Direct browser/API evidence included:

- all nine module routes and all 17 case-selector endpoints;
- wrong, correct, skip, resume, and exact tangent-return state;
- Foundations and native tutor tangents;
- guided → Train, Rapid, and Clinical return links;
- 20-second quick-look input and grading;
- live RBBB grounding and source-conflict behavior;
- laptop responsive layout and overlap recovery;
- scene-specific complete-block and PAC selection;
- rate, click, disclosed-answer, and Clinical-focus adversarial probes.

## Consensus verdict

**Go:** continued internal development and a small, moderated formative usability alpha with competency claims disabled.

**No-go:** unmoderated curriculum release, learner-efficacy study, clinical-content pilot, or any claim that a completed native scene demonstrates independent ECG competence.

The rebuild is a meaningful product and architecture improvement. The curriculum order, visual system, exact tutor waypoint, data boundaries, and mode distinctions are credible. The blocking construct-validity gap is equally clear: most of the 65 native post-Foundations scenes still render a revealable why-chain, a real but sometimes contrast-only ECG, and one three-option checkpoint. The learner can often pass without doing the waveform action specified in the storyboard.

## Findings fixed during round 2

| Finding | Revision made | Evidence |
|---|---|---|
| Wrong answer or skip could masquerade as progress | Wrong remains `needs review`; skip is stored and displayed separately; one-item placement checks never mark a part mastered | Browser replay + state tests |
| General tangent was refused as an unsupported current-case diagnosis | General concept teaching is classified before case-claim validation, labeled as non-case teaching, and returns to an exact waypoint | WCT and RBBB paraphrase regressions |
| “terminal” was parsed as “MI” and `where` as `here` | Concept matching uses word boundaries; current-case classification uses deictic phrase patterns rather than raw substrings | Unit tests + live RBBB response |
| Return button required another model call and could be intercepted by an overlapping rail | Return is an immediate focus/scroll restoration; responsive grid keeps the rail outside the tutor hit area | Laptop browser replay |
| Clinical handoff only displayed its focus | Shift session persists `focusObjective`; first eligible item is filtered to it, then adaptive interleaving resumes | QT-focused shift regression |
| 20-second one-finding UI used a four-objective full-read grader | `dominant_finding` assessment scope grades exactly the declared primary objective and updates only that mastery | RBBB quick-look regression |
| Complete-block and PAC scenes received generic first-degree/PVC cases | Guided scene focus is sent to the tutorial selector; selection is scene-specific when evidence exists | Live AV3 and PAC selector checks |
| Conflicted RBBB case anchored teaching | German/English opposite-bundle reports are quarantined; curation detects cross-source conflict; canonical exemplars require acceptable signal and non-limited morphology. If none qualifies, a visibly labeled normal contrast trace is shown | Case 11046 exclusion + exemplar tests |
| Numeric rate could be rescued by an unrelated matching number | Structured rate field has precedence; free-text numbers require rate context; contradictory values fail | “299 bpm + QRS 64 ms” regression |
| Average-RR projection was used on irregular rhythms and off-wave clicks could pass | Periodic projection is disabled for AF/ectopy/variable block; ungroundable clicks are not scored; amplitude envelope and component-specific time tolerances are applied | Click regressions |
| Vignette wording leaked AF/rate mastery | Items may author `disclosedObjectives`; automatic detection checks stem, prompt, and chips plus HR/pulse/tachycardic/BPM variants | Disclosure regressions |
| Small copy, smooth-scroll focus, chat announcements, and nested laptop rails diverged from the design spec | Major instructional copy increased, laptop rail/tutor use the page scroll, reduced motion controls navigation, headings receive focus, and full tutor replies have a polite live announcement | Typecheck + browser inspection |

## Persona-specific conclusions

### Maya — novice

What helps:

- `Recall from → Now → Reuse next` answers where the learner is in the conceptual sequence.
- “Why this changes practice” provides motivation without forcing a diagnosis-first approach.
- Mistakes no longer silently advance, and tangents return to a named task.
- Foundations now answers an inverted-T/heart-attack question with a safe explanatory bridge rather than a refusal.

What still blocks independent use:

- the why-chain is mostly clickable prose rather than a manipulable causal model;
- one correct choice still creates a strong completion signal;
- unfamiliar tangent terms need staged definitions based on learner level;
- every required ECG action needs a keyboard/non-pointer equivalent;
- a novice should not see internal product language such as “case selector,” “Tier,” or “versioned concept graph.”

### Jordan — clerkship learner

What helps:

- the dependency sequence supports a usable systematic read;
- clinical bridges and communication language are strong;
- Rapid’s quick-look is now a fair priority construct rather than a typing contest;
- RBBB tutoring distinguishes supported measurement from an unannotated morphology claim;
- acute, serial, telemetry, and ACLS lanes are not fabricated from resting PTB-XL data.

What still blocks clerkship utility:

- Train remains classification-heavy and its evidence statement is optional;
- a 45-second ward task can still measure typing speed;
- Guided handoffs need subskill/misconception/scaffold receipts, not only concept and URL;
- busy clerks need a 60–90 second diagnostic and a 5–8 minute patient-problem fast path that reconnects to the full curriculum;
- M9 describes prioritization and communication more often than it makes the learner perform them.

### Priya — advanced learner

What helps:

- earlier numeric-rate and arbitrary-beat click failures are fixed;
- source-conflicted exemplars are now rejected rather than rationalized by the tutor;
- case-specific responses cite grounded values and decline absent morphology claims;
- the quick-look grader now matches the quick-look UI;
- clinical recognition is separated from information already disclosed in the vignette.

What still blocks validity:

- scene contracts do not yet declare required morphology, leads, task, quality, provenance, and geometry;
- irregular per-beat clicks require real per-beat landmarks, not one representative fiducial;
- backend-safe viewer actions still lack a client-render acknowledgement and screenshot/geometry verification;
- the current scalar concept mastery does not implement recognition/localization/measurement/discrimination/explanation/synthesis/application axes;
- high-stakes criteria and every pilot exemplar require versioned clinician review.

## Required next implementation slice

Do not expand the number of prose scenes next. Build three distinct scene renderers end to end:

1. **Measurement:** learner places boundaries/calipers; grading uses valid sampling resolution and task-specific tolerance; an equivalent unseen retry is required.
2. **Proof-on-trace discrimination:** learner selects lead(s), points/bounds the discriminator, and distinguishes target, close mimic, and normal; the scene preflights its case/geometry contract.
3. **Explanation and transfer:** learner gives a prioritized evidence-linked synthesis on a new tracing; deterministic evidence scoring is separated from AI coaching/style feedback.

Use one representative scene from each major module to validate those renderers before filling the rest of the storyboard. Completion must come from the specified action. A three-option question may retrieve or check a misconception, but cannot substitute for the skill.

## Pilot acceptance gates

1. Every scene has a machine-checked case contract and zero unresolved source contradictions.
2. Genuine target actions pass at least 95%; off-wave/off-component false acceptance is at most 2% on a clinician-labeled test set.
3. General/current-case/clinical/real-patient tangent classification reaches at least 0.95 F1 across 100 adjudicated paraphrases; exact return succeeds 100%.
4. Rapid, Clinical, Train, and Guided update only the construct the learner was asked to demonstrate.
5. Promotion requires more than one morphology/task form, a close mimic, mixed transfer, and delayed retention.
6. Five novices and five clerks complete moderated laptop sessions; keyboard, reduced-motion, 200% zoom, touch, screen-reader, and timer-accommodation paths pass.
7. All clinical rules, exemplar morphology, answers, rationales, and urgency claims have a named reviewer, source/version, and review date.

Until those gates pass, the platform should describe its scores as provisional learning signals—not mastery or clinical competence.
