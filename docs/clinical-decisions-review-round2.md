# Clinical Decisions mode — GPT review ROUND 2 (sharp / targeted)

*Focused follow-up to the round-1 review. **Do NOT re-review the whole design** (that's in `storyboard-clinical-case.md`). Critique ONLY the **grading + honesty spine** — and do it by working our ACTUAL cases and red-teaming them. We want concrete failure cases, fixed tags, and specific guardrails — not general assessment-design principles or affirmation. Be adversarial.*

("Clinical Decisions" = the rebuilt Practice mode: situation-framed ECG cases where the answer is the clinical decision/action. ECG tracings are real + curation-grounded; the clinical vignette is authored, board-style. Corpus is chronic — acute is gated to a STAFF-III fast-follow.)

## The spine you're reviewing (from round 1, now locked)

- **Graded answer model:** every option is tagged one of `ideal · acceptable · over-triage-but-safe · under-triage · unsafe · appropriate-insufficient-data`, scored on 3 axes: **ECG-recognition · acuity-calibration · next-action-safety**. "Insufficient data → get prior/troponin/lytes/12-lead" is a first-class option.
- **Per-item evidence manifest (3 layers):** `ecg_supports` (what the real tracing shows) · `stem_adds` (authored age/setting/vitals/meds/prior) · `action_rationale`; + `forbidden_claims`, `acuity_tier`, `acceptable_range`.
- **Validator (4 axes):** pathology specificity · patient stability · action urgency · clinical-claim support.
- **Distractor rubric:** plausible-in-stem · wrong-for-a-visible-reason · same-specificity-as-key · defensible-elsewhere · safe-to-teach-against.
- **Generation:** a cheap **nano LLM drafts**; the rubric/validator is rule-backed + human-reviewed; items cached. The bank is auto-generated **at scale** (PTB-XL ~21,799 → per-concept Tier A/B pools → ~30–50 vetted to start, then scale).

## Exact mechanics (precise — pressure-test the realism, don't take these as endorsed)

*These are stated exactly so you can catch what's unrealistic or pedagogically wrong. We are NOT confident in all of them — say plainly where they teach the wrong habit.*

- **Clock (exact current behavior).** Two phases. (1) READ — **UNTIMED**; learner reads stem + ECG and clicks "I've read it." (2) DECIDE — **only now** a wall-clock timer starts and drains (clinic ~90s / ward ~75s / ED ~60s / triage ~12s); answering stops it; on timeout the answer is revealed ("kind timeout," never "failed"). **Net: the clock does not advance until the learner opts in.** Stated rationale was fairness for slow/ESL/mobile readers. We think this is **wrong for acute care** (the code/ED clock is already running; you don't get an untimed orient, and "read fast under pressure" is itself the skill) — see task 7.
- **Display (exact: prototype vs intended).** The prototype renders a **single lead (II)**. The intended v0 default is the **full 12-lead**, with single-lead/rhythm-strip reserved for rhythm/rate/triage gestalt, telemetry, the rhythm half of old-or-new, or a zoom-to-lead for click/measure. This default is **not yet decided per question type** — see task 8.
- **Tracings.** Prototype tracings are **synthetic** (clinicians flagged the synthetic "VT" as too clean). Production uses **real** PTB-XL tracings (acute via STAFF-III later). Critique the model assuming real tracings — not the synthetic prototype art.
- **Grading surface.** Per item the 4-axis validator runs; the learner gets class-appropriate feedback + an on-trace highlight of the discriminating finding; calibration (over/under-triage + high-confidence-wrong) accrues across a "shift" and is shown as triage-style labels at the end.

## Our worked standard — Case W (you critique + extend this format)

**Ward · complete heart block.** `ecg_supports`: ventricular rate ~38; AV dissociation (P-waves march independent of QRS); escape QRS. `stem_adds`: 71, inpatient, new dizziness, telemetry alert (no BP/other vitals given). `action_rationale`: symptomatic high-grade/complete AV block → pacing readiness + cardiology; atropine commonly fails in infranodal block. `forbidden_claims`: ischemia/STEMI/specific etiology; hemodynamic collapse (no vitals). `acuity_tier`: high.

Q "Most appropriate next step?" — options tagged (class → axes hit):
| Option | Class | ECG-recog | Acuity-calib | Action-safety |
|---|---|---|---|---|
| Apply transcutaneous pacing pads + call cardiology | **ideal** | ✓ | ✓ (escalate) | ✓ safe |
| IV atropine, reassess | **acceptable** | ✓ | ✓ | partial ("reasonable, but atropine often fails in infranodal — ready pacing") |
| Continuous monitor, routine a.m. labs | **under-triage** | partial | ✗ (under) | unsafe-ish |
| Reassure + discharge | **unsafe** | ✗ | ✗ | ✗ |
| "Insufficient data — get vitals/12-lead **while readying pads**" | **appropriate-insufficient-data → but LOW credit here** | ✓ | ✓ | the ECG+symptoms already mandate readiness; waiting is the error |

## Your tasks (be concrete; produce the actual artifacts)

1. **Critique Case W.** Where does our tagging over/under-credit, mislead, or leak? Re-tag what you'd change and say why (e.g., is atropine "acceptable" or "under-triage"? should insufficient-data ever be >low here?).
2. **Apply the model to 3 cases that AREN'T single-select MCQ** — and tell us how/whether the answer-class + 3-axis model even fits them:
   - **Triage (Case T):** ED, 58, palpitations+lightheaded, BP 88/54; wide-complex tachy ~170. Options: Act-now / Work-up / Routine.
   - **Click-the-abnormality (Case C):** clinic, asymptomatic, long PR; learner clicks the prolonged interval on the trace.
   - **Old-or-new (Case O):** clinic pre-op; today vs a 2-yr-prior, wide-QRS+left-axis unchanged; choices new / old-unchanged / cannot-determine.
   Produce the manifest + the graded outcomes for each. Where the model breaks for a non-MCQ type, say what replaces it.
3. **Red-team the provenance guardrail.** Give **3 concrete authored-vignette overclaims** on a *chronic* tracing that our 4-axis validator (as specified) would **MISS**, and the exact extra check each requires. (E.g., a chronic ST-depression strip wrapped as "active chest pain, escalating" — what catches the implied acuity the tracing can't support?)
4. **Distractor stress (Case M, MCQ):** ED, 55, stable, regular narrow-complex ~180 (SVT). Write the 3 best distractors per our rubric, AND one distractor a nano-LLM generator would *plausibly* emit that is **subtly unsafe to teach** (and the rule that should reject it).
5. **At-scale failure modes.** When a nano LLM auto-generates hundreds of these from per-concept corpus pools, where will the graded-answer model + manifest **silently degrade** (e.g., mis-tagged acceptable-vs-unsafe, manifest claims the tracing doesn't support, calibration mis-set)? Give the 3 most likely silent failures and the cheapest automated guardrail for each.
6. **Calibration integrity.** Our calibration score uses over/under-triage + high-confidence-wrong, surfaced as triage-style labels at end-of-shift. Name 2 ways a learner games it and the fix; and whether confidence should be required or optional per case.
7. **Clock realism (attack the exact mechanic above).** Is "untimed read → learner opts into a decision clock" defensible for ANY situation, or does it train the wrong reflex? Our proposed fix is **situation-scaled**: acute/triage → clock runs from the moment the ECG appears (optionally two-tier: short gestalt window + read window); ward/clinic → a brief untimed orient, then the decision clock; ESL/reading-speed accommodation → generous *scaled* timers + glossary + tap-to-define, NOT an unlimited read in acute lanes. Pressure-test it: where does it still mislead, what **exact** timer behavior would you set per situation, and how do you preserve fairness without faking the emergency clock?
8. **Display per question type (attack the default).** For EACH type — triage, stepwise→disposition, click-the-abnormality, old-or-new, spot-the-error, MCQ — specify exactly what should be on screen: full 12-lead / a named single lead / a rhythm strip / a zoomed lead; and how the click + on-trace highlight target works on a 12-lead (lead-panel selection vs zoom-to-lead). Call out every type where showing only a rhythm strip **silently narrows what's being tested** (e.g., hides axis, territory, BBB).

Output per task, with the actual tags / manifests / distractors / failure cases / exact timer + display specs. Skip anything that's just a restatement of good test-design principles — we have those; we want our specific items and exact mechanics pressure-tested.
