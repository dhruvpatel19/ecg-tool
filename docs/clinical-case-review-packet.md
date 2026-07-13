# Clinical Case mode — GPT review packet (v0.3, pre-build)

*For an external expert review. Companion doc: `docs/storyboard-clinical-case.md` (full design + iteration history). This packet is self-contained enough to review alone, but send both for the complete picture.*

---

## A. What you're reviewing & how

This is the **design + a working interactive prototype** of the "Clinical Case" practice mode for an AI-native ECG learning platform for med students — **before** the production v0 build. We've already run two persona passes (design read, then live on the prototype) and iterated. We want a sharp external critique of the *design and plan* now, to catch problems before building the React+backend v0.

**What it is:** rapid-fire, **situation-framed** ECG cases (clinic / ward / ED; an "active code" track is pluggable). The *answer is the clinical decision/action*, not the diagnosis label. Multiple question types, a soft clock, on-trace reason-me-back. Goal: beat ECG Wave-Maven (static ECG→dx) on situational realism, decision-focus, adaptivity, and grounded AI.

**Hard data constraint:** the corpus (PTB-XL + PTB-XL+) is **chronic/resting** — acute STEMI, 12-lead VT/VF, hyperkalemia are genuinely absent. The chronic ward/clinic/ED-non-arrest space is richly supported (AFib, AV blocks incl. complete heart block, BBB, LVH, old MI, long-QT/drug, ectopy, paced, WPW). Real acute data (STAFF-III: open, WFDB, acute ST-change during balloon-occlusion PCI — 104 patients, *excludes VT/emergency*, so acute-ischemia practice only, NOT VT/code) is a planned fast-follow ingest. MIMIC-IV-ECG v1.0 *waveforms* are open (ODC-ODbL), but its **Ext-ICD label linkage** (what makes acute cohorts pullable) is credentialed/DUA → the acute *labeling* is gated until cleared.

---

## B. Design in brief

- **Situations & clocks (reasonable):** Clinic ~90s → Ward ~60–90s → ED-non-arrest ~45–75s → Active code ~10–15s (pluggable). The situation sets the timer, stakes, and question framing.
- **Difficulty ramp (one dial):** a **Learn tier** (untimed, single-type, full scaffold, **calibration ungraded**) graduating into timed mixed **Shift** sets. Beginners get the ramp; the fluent crank it up.
- **Split clock:** untimed READ phase (read the stem/ECG) → the decision clock starts only when ready. Fixes the reading-time penalty for ESL/slow/mobile learners.
- **AI case generation (chosen approach):** a **pre-generated, vetted bank** — the LLM authors each case's clinical wrapper (situation, stem, question(s), distractors, disposition, reason-me-back, teaching) **offline** from a grounded packet (constrained by curation's allowed/forbidden claims), passed through claim-check guards + a validation pass, cached in a `clinical_case_items` table. The live LLM is used only for post-answer reason-me-back / "ask why". **Honesty principle:** the *tracing is real & curation-grounded; the vignette is authored* (like board questions) and labeled as such; a guardrail enforces **stem-acuity ≤ tracing-acuity** so chronic findings never masquerade as acute.
- **Tutor (less front-facing than the guided modules):** silent during answering; post-answer grounded reason-me-back that **highlights the missed finding on the trace**; opt-in "ask why"; end-of-shift synthesis linking to the relevant module.
- **Scoring:** accuracy, streak, avg decide-time, **calibration** (over/under-triage, high-confidence-wrong); no-repeat; mastery deltas reuse the existing backend (`review.py`/`grade_attempt`). Speed is secondary to correctness; kind timeout (reveals + teaches, never "failed").
- **Acuity/danger dimension** (currently absent in the backend; built as part of this): a concept→danger base map + per-case adjustment, driving situation/timer/triage scoring.

---

## C. The working prototype (as built) — verbatim

Historical prototype note: the six-case synthetic HTML mock was removed from the deployed frontend. The production Clinical mode now serves the governed real-ECG case bank; this review packet remains only as design history.

**The 6 cases (verbatim):**
1. **ED · triage (sick/not-sick).** Stem: "58, palpitations + lightheaded. BP 88/54." Trace: wide-complex tachy ~170. Answer: **Act now**. Reason: "Broad QRS at ~170 with hypotension — treat as VT until proven otherwise. Act now." Why: "Regular, wide, fast, unwell = VT until proven otherwise; don't reach for AV-nodal blockers."
2. **Ward · stepwise→disposition (decision-first).** Stem: "71, inpatient, new dizziness. Telemetry called you." Trace: rate ~38, AV dissociation. Commit disposition first; wrong → branch to steps (Rate? → P–QRS relationship?). Disposition: **Pads on + call cards (likely complete heart block)** [NOTE: answer-leak — flagged for fix]. Reason: "Slow, AV dissociation, symptomatic → high-grade/complete block. Pads + cardiology." Why: "Atropine often fails in infranodal block; pacing readiness is the safe move."
3. **Clinic · click-the-finding.** Stem: "48, routine pre-op, asymptomatic. Something looks prolonged." Trace: long PR (single beat). Prompt: "Click the interval that's prolonged (start of P → start of QRS)." Finding: first-degree AV block. Why: "Isolated long PR is usually benign; matters as part of higher-grade block."
4. **Clinic · old-or-new.** Stem: "62, pre-op clearance, asymptomatic. Today + a prior from 2 years ago." Two stacked lead-II strips (wide QRS + left axis, unchanged). Answer: **Old / unchanged**. Why: "The single most useful question: is it new? Unchanged conduction disease pre-op rarely needs work-up."
5. **Ward · spot-the-error (audit the machine read).** Stem: "80, intermittent chest discomfort. The machine printed a read — audit it." Machine: "Sinus rhythm. No acute ST-T changes." Trace: ST depression. Prompt: "One line of the machine read is wrong. Click the part of the trace that proves it." Why: "Trust the machine's numbers, re-derive its interpretation. ST depression → ischemia work-up in context."
6. **ED · MCQ.** Stem: "55, palpitations, regular and fast. Stable, BP 118/70." Trace: regular narrow-complex ~180. Q: "Most appropriate first step?" → **Vagal manoeuvres / adenosine (SVT)** (distractors: cardiovert now / IV metoprolol push / activate cath lab). Why: "Stable + narrow + regular = vagal/adenosine before electricity."

**Question types demonstrated:** triage; stepwise→disposition w/ decision-first + branch-on-wrong; click-the-finding; old-or-new (with prior); spot-the-error (click the trace); MCQ (+ confidence slider in Shift). All verified grading correctly; zero console errors. Tracings are **synthetic** (prototype only).

---

## D. Iteration history (two persona passes, 10 profiles each)

Profiles span mastery/style: Maya (anxious M1), Sam (methodical M2), Devin (fast M3), Priya (strong M4), Leo (visual), Aisha (ESL), Marcus (gunner), Carlos (rusty non-trad), Jenna (mobile), Okafor (IMG resident).

- **Pass 1 (design read of the storyboard):** avg ~3.0/5. Core validated (situation + decision-as-answer + reason-me-back beats Wave-Maven), but assumed an intermediate desktop learner. Drove the **v0.2** changes: difficulty ramp, split-clock, decision-first, on-trace visual feedback, resumable mini-shifts, stem-acuity guardrail; (P1) ambiguity tier + insufficient-data + defensible distractors, tiered tutor, free-text out of timed sets + glossary, opt-in competitive layer.
- **Pass 2 (live, on the working prototype):** **avg ~3.85/5.** Mechanics landed (split-clock, Learn tier, decision-first+branch, on-trace highlight, stacked strips, **phone-tappable single-beat click targets**). New **v0.3** fixes — P0: kill timed-vibe in Learn ("Decide fast" + HUD), strip answer-leaking parentheticals from options, lock all options uniformly post-answer, ≥44px mobile toggle. P1: calipers/arrows + ghost landmarks on-trace (static box "says look here, not here's why"); **first-class scoreable "insufficient data / get more" answer + ambiguity tier + contestable "ask why"** (top depth ask from Priya/Okafor); sharper discriminator-named feedback for experts; persistent jargon glossary; during-case opt-in lifeline + framework-visible-in-Learn; competitive layer (composite score/blitz/rank, confidence→Brier); resumable mini-shifts + portrait viewer. P2/reinforced: **replace synthetic acute strips with real STAFF-III** (clinicians instantly clock the synthetic "VT" as too clean).

Full per-persona detail: storyboard §12 (design) and §13 (live).

---

## E. Open decisions & questions for the reviewer

Please opine specifically on:
1. **Authored-vignette honesty.** Is "real teaching ECG + authored clinical context, labeled as such, with a stem-acuity ≤ tracing-acuity guardrail" a sound, defensible approach for a med-student product — or does wrapping chronic ECGs in clinical vignettes risk teaching false illness scripts even with the guardrail? How would you harden it?
2. **Single-keyed decisions vs. defensible range.** Experts flagged single "correct" dispositions as gamey and old-or-new as too binary. Is a scoreable "insufficient data → get prior/troponin/12-lead" answer + a disposition *range* the right fix, and how do you grade a range without making it mushy?
3. **Distractor quality at scale.** The MCQ pipeline must generate distractors that are *defensible* (not wrong-on-sight) yet verifiably-false-for-this-case, from a chronic corpus, via a cheap nano LLM + claim-checker. Is this achievable with acceptable quality, and what validation would you require?
4. **Difficulty ramp as one dial.** Does the Learn→Shift ramp (untimed/calibration-off → timed/mixed; full-scaffold → decision-first) genuinely serve both Maya-types and Priya-types, or will it satisfy neither? 
5. **Calibration scoring.** Over/under-triage + high-confidence-wrong as the differentiating metric — is this pedagogically sound, and how should it be surfaced (rank? Brier? something else) without gaming or demoralizing?
6. **Clinical realism ceiling on chronic data.** Given no real acute data until STAFF-III, how far can a *clinical-case* mode credibly go on chronic ECGs? Which situations/decisions are honest now vs. should wait?
7. **Scope for v0** (§9): is "ED + ward, core question types + 2 trial types, ~30–50 vetted chronic items, ramp + split-clock + on-trace feedback + acuity dimension" the right first build, or would you cut/add?

We are NOT looking to expand into a pathology course; this mode should stay scoped to situation-framed decision practice on what the data honestly supports.
