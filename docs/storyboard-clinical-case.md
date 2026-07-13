# Storyboard — Clinical Case mode (v0 design)

*The "Practice / Clinical-case" mode: rapid-fire, situation-framed ECG cases with real clinical decisions. Sibling to the Foundations guided module.*
**Mode name (adopted): "Clinical Decisions"** (the activity = "decision drills"). Status: design v0.4 (GPT-green-lit) → sharp round-2 review of the grading/honesty spine (`clinical-decisions-review-round2.md`) → v0 build.
**Note:** the "6 cases" in §13/the mock are a PROTOTYPE set (interaction test only). The production bank is AI-generated **at scale** from the corpus (PTB-XL ~21,799 → per-concept Tier A/B pools → ~30–50 vetted to start, then scale; STAFF-III acute later).

---

## 1. Positioning — beat ECG Wave-Maven

Wave-Maven (and LITFL/cases) = a static gallery: here's an ECG, here's the diagnosis + a discussion paragraph. We do four things it can't:

1. **Situation-framed & timed** — every case lives in a clinical *context* (who, where, how sick) with a reasonable clock, so the learner reasons under realistic pressure, not in a vacuum.
2. **Decision/action is the answer, not the label** — the payoff is *what you do* (activate? admit? hold the drug? pace? discharge?), with the ECG→cause→action chain made explicit. (Validated in the `c1-sweep` mock.)
3. **Reason-me-back on the trace** — wrong calls are met by highlighting the missed finding *on the waveform* and the discriminator, not a red ✗. (Design principle from the learning-environment work.)
4. **Adaptive + grounded AI** — serves what you keep missing; the tutor is constrained to curated case evidence (can't invent findings); cases are AI-authored from real grounded packets and vetted.

This mode IS the validated prior art: the `r1-triage`, `c1-sweep`, and `c2-serial` mocks already prototyped and persona-tested these interactions.

---

## 2. The data reality + situational reconciliation

Our corpus (PTB-XL + PTB-XL+) is **chronic/resting** — acute STEMI, 12-lead VT/VF, and specific hyperkalemia are genuinely absent (see `finding-ptbxl-coverage`). It is, however, *rich* in exactly the findings that drive most real ward/ED ECG decisions.

**Design rule:** the situational frame sets the timer, stakes, and question framing; each situation maps to the pathologies the corpus actually supports. The acute "code/ED-STEMI" track is a **pluggable slot** filled by an ingested acute dataset.

**Acute data — FOUND** in the user's `ResearchGrind/#6-ECG-VCG` Drive folder (resolved 2026-06-28):
- **STAFF-III** (`staff-iii-database-1.0.0`) — **the near-term answer.** Real 12-lead ECGs from 104 patients during balloon-occlusion PCI = controlled *acute transmural ischemia / dynamic ST-change*. Standard **WFDB** (`.dat/.hea/.event` + RECORDS + annotations) → drops into our existing PTB-XL ingest pipeline. **Open license.** Use it for **acute ischemia / dynamic ST / territory practice ONLY** — the database *excluded VT and emergency-procedure patients*, so it is NOT a VT/code/arrest source. Needs our measurement/fiducial extraction (no PTB-XL+ features).
- **MIMIC-IV-ECG** — nuance matters: the **v1.0 waveforms themselves are OPEN** (ODC Open Database License, ~800k diagnostic ECGs). But the **Ext-ICD label linkage** (`mimic-iv-ecg-ext-icd…`, the table mapping ECGs to ED/discharge ICD-10 — i.e. what makes STEMI/hyperK/VT cohorts *pullable*) is **credentialed/DUA/training-restricted.** → the acute *labeling* is the gated part; acute-MIMIC stays gated for the product until that linkage's licensing is cleared.
- Breadth options (verify license each): CODE-15, SaMi-Trop (Chagas), Leipzig peds/CHD arrhythmias, Michigan HF.

So the acute track is **real-data-feasible now (STAFF-III)**, not synthetic and not coming-soon — pending a small ingest sub-project. v0 still ships chronic-first (clinic/ward/ED-non-arrest); STAFF-III acute is the immediate fast-follow.

| Situation | Clock (reasonable) | Built on (REAL corpus today) | Typical decision |
|---|---|---|---|
| **Clinic / pre-op** | relaxed (~90s) | LVH, axis, old MI/Q-waves, 1° AVB, RBBB, WPW, long-QTc | screen / clear / refer |
| **Ward / inpatient** | ~60–90s | brady, AV blocks (incl. 3°), AFib, ectopy, paced, long-QT (drug/lyte) | telemetry response, med safety, old-vs-new, call-or-watch |
| **ED (non-arrest)** | ~45–75s | AFib w/ rapid rate, SVT, 2°/3° AVB, BBB, ischemic ST-T / T-inversion, established MI territories | admit / cards / disposition |
| **Active code / arrest** *(pluggable)* | fast (~10–15s) | 3° AVB + severe brady (PTB-XL, real); **acute ST-elevation/ischemia via STAFF-III** (real, open — ingest sub-project); VT/VF still gap | act-now gestalt |

---

## 3. The acuity / danger dimension (builds pending task #6)

Situational framing + triage scoring need per-case **acuity**, which the backend lacks today. Build it as:
- A concept→danger base map authored once (e.g. `av_block_third_degree`/`wide_complex_tachycardia` = high; `atrial_fibrillation`/`mobitz_ii` = moderate-high; `qtc_prolongation` = moderate [drug safety]; `lvh`/`old MI`/`lafb` = low/chronic; `normal` = none).
- Per-case adjustment by measurements (e.g. AFib + HR 165 → higher; brady + HR 38 → higher).
- Stored as `acuity_tier` + `danger_score` on the case/item; drives the situation a case can appear in, the timer, and over/under-triage scoring.
- Honest framing: acuity here = "how much this finding *should* raise concern," a teaching signal — not a real-patient risk score.

---

## 4. Question types

**A. Validated in the mocks (reuse):**
1. **Stepwise read → disposition** (`c1`): branch rate → rhythm → axis → intervals → ST-T → cause → **action**; wrong step = a re-explain turn, then advance. The flagship.
2. **Single-best-answer MCQ**: rhythm / most-likely finding / next step / culprit territory. AI-generated stem + 1 keyed correct (from `supported_objectives`) + 3 grounded distractors (sibling concepts).
3. **Click-the-abnormality**: click the segment+lead where the finding lives (graded via existing ROI bounds + territory leads).
4. **Triage sick / not-sick under the clock** (`r1`): 3-way action (act-now / work-up / routine) with **over- and under-triage penalties** → calibration.
5. **Serial comparison + present-to-attending** (`c2`): "what changed?" then free-text one-line plan graded by an *attending* persona.
6. **Name-the-rhythm free-text** (`r2`): meaning-graded, near-miss coaching ("clock the irregularity — now name it").

**B. New ideas to trial & validate (my additions):**
7. **"Prove it" — find the diagnostic lead**: given a finding, click the single most diagnostic lead/region (teaches territories; uses ROI+lead grading).
8. **Spot-the-error (audit the machine read)**: show a read (sometimes the real 12SL interpretation, which is often wrong) with one bad call; flag it. Directly teaches the platform's core habit — *trust the machine's numbers, re-derive its interpretation*.
9. **First-action / order-the-steps**: pick the FIRST move, or drag management steps into order (e.g. 3°AVB: pads/pacing → atropine → cards). Teaches prioritization under the situation.
10. **Confidence-calibrated answer**: answer + confidence; high-confidence-wrong is penalized (the backend already tracks `high_confidence_wrong`). Teaches calibration.
11. **"What would change your mind?"**: pick the one extra datum (prior ECG / troponin / K⁺ / rhythm strip) that most changes management. Teaches Bayesian/serial thinking.
12. **Old-or-new?**: decide whether a finding is acute/new vs chronic/old (sometimes with a prior). Leans into PTB-XL's chronic strength and the single most important real-world ECG question.
13. **Telemetry-alarm triage (ward)**: a short stream of strips ("the monitor's alarming") → respond-now / watch / artifact. Teaches alarm-fatigue calibration; maps cleanly to the ward situation.
14. **Progressive reveal / anchor-and-adjust**: reveal stem → rhythm strip → 12-lead → labs in stages; learner commits and may revise; rewards updating on new data.

v0 will implement the core reasoning trio (1, 2, 3) + triage (4) + at least two new ones to trial (8 "spot-the-error" and 12 "old-or-new" are highest-yield + most differentiating); the rest are queued behind the same engine.

---

## 5. AI case-generation pipeline (pre-generated + vetted bank)

**Principle:** the *ECG tracing + its findings are real and curation-grounded*; the *clinical vignette is authored* (PTB-XL has no linked presentation). We are explicit about this — like board questions, the strip is real, the stem is written to be consistent with it.

**Offline generation (not live):**
1. **Input** per item: a real Tier-A/B case + its grounded packet — `supported_objectives`, measurements, ROIs/territories, `llm_allowed_claims`/`llm_forbidden_claims`, `report`, signal quality, metadata (age/sex).
2. **The LLM authors** (constrained to allowed claims): the situation (clinic/ward/ED) + a plausible stem consistent with the finding; the question(s) across types; MCQ keyed-correct (from supported objectives) + grounded distractors (sibling concepts that are *false for this case*); the correct disposition/action + its acuity; the reason-me-back explanation; the clinical-correlation teaching point.
3. **Guardrails (reuse existing):** the `_flag_unsupported_measurements` / `_flag_unsupported_diagnoses` claim-checkers reject any item asserting a finding not in `supported_objectives` or a measurement not in the packet. Distractors must be verifiably wrong for the case.
4. **Validation pass:** automated checks (keyed answer ∈ supported_objectives; distractors ∉; disposition consistent with acuity tier; stem mentions no ungrounded finding) + a second-model critique + human spot-check before a batch is marked `vetted`.
5. **Store** vetted items in a new `clinical_case_items` table (caseId, situation, type, stem, prompt, options/answer key, roiTarget, disposition, acuityTier, explanation, teachingPoint, conceptsTested, status). Served fast & deterministically at runtime.

**Why pre-generated:** deterministic, QA-able, cheap, safe — the learner never sees unvetted output. (Live LLM is reserved for the post-answer tutor below.)

---

## 6. The tutor — present but not front-facing

Unlike the guided modules (tutor is a constant co-pilot), here it stays out of the way:
- **Default:** silent during the answer.
- **Post-answer reason-me-back** (grounded, from the packet): correct → one-line *why + the clinical link*; wrong → **highlight the missed finding on the trace** (viewer actions: `highlightROI`/`zoom`) + the discriminator + why it matters clinically.
- **"Ask why / explain more"** affordance → opens the grounded post-answer tutor for a turn or two (packet-grounded, claim-checked). Optional, learner-initiated.
- **Present-to-attending** question type uses the tutor in an *attending* persona to grade the plan (validated in `c2`).
- **End-of-shift synthesis:** "you over-triaged 3 bradycardias — here's the rule," + links to the relevant **module/concept** (ties the modes together; e.g. "review Intervals & AV Conduction").

---

## 7. Session structure & scoring

- A **"shift" / set** = 30–50 cases, either themed by situation ("ED evening, 35 cases"), by concept ("AV conduction, 30"), or **adaptive** (serve-me-what-I-miss using the existing mastery + no-repeat infra in `review.py`).
- **Mixed question types** within a set; **adaptive sequencing** front-loads weak areas; unlock/streak milestones.
- **Scoring shown:** accuracy %, streak, average call-time, and **calibration** (over/under-triage rate). Speed is secondary to correctness (Foundations lesson).
- **Kind timeout:** time-up reveals the answer + full feedback and counts as "too slow," never "failed" (mock weakness we fix).
- **No-repeat**, mastery deltas per concept (reuse `grade_attempt` + `objective_mastery`), misconception tracking, **end-of-shift report** with what to review.

---

## 8. Build approach

- **Native React in the app** (NOT an embedded iframe like Foundations) — this mode needs real corpus cases + backend grounding and should reuse the app's `ECGViewer` (real 12-lead/median rendering, click ROIs), `TutorChat`, mastery widgets, and the `/api/backend` data flow. It becomes the real `/practice` (or `/cases`) mode. This is the "deeper React integration" path; the telemetry/progress contract is server-side (attempts/mastery) rather than postMessage.
- **Process mirrors Foundations:** (i) this storyboard → persona-test the *design* across the 10 profiles → iterate; (ii) build an interactive **mock/prototype** of the new question types (extend `mocks/`) → live persona-test → iterate; (iii) build **v0** real (backend generation pipeline + acuity dimension + the React mode) → live persona-test → iterate; (iv) GPT-Pro evaluation rounds (as we did for Foundations).

---

## 9. v0 scope

- **Backend:** acuity/danger dimension (task #6); `clinical_case_items` schema + the offline generation+validation pipeline; a vetted bank of ~30–50 items on real chronic findings across **ED + ward** situations; a `clinical_case` session type (extends review-session: per-case sub-question state, timing, calibration).
- **Frontend:** the `/practice` clinical-case mode — situation/shift picker, the clock, the core question-type components (stepwise→disposition, MCQ, click-the-abnormality, triage) + 2 trial types (spot-the-error, old-or-new), post-answer reason-me-back tutor, end-of-shift report.
- **Deferred to v1:** serial-comparison/present-to-attending; the remaining creative types; the acute "code" track (pending acute data); concept-themed + fully-adaptive shift modes.

---

## 10. Open decisions / risks

1. **Acute data path — RESOLVED (decision needed on licensing).** STAFF-III (open, WFDB, acute ST-elevation) is the product-safe acute source → ingest sub-project. MIMIC-IV-ECG (ICD-linked STEMI/hyperK/VT) is credentialed+DUA → **research-only unless a DUA review clears product use.** Decision: confirm STAFF-III-in / MIMIC-out-for-product, and whether the STAFF-III acute track is in this mode's build or a fast-follow.
2. **Vignette honesty** — the authored stem must never imply the ECG was recorded from that exact patient; UI labels it "illustrative clinical context for a real teaching ECG." Confirm tone.
3. **Generation QA cost** — the validation pass (2nd-model critique + spot-check) is where quality lives; budget for it.
4. **Distractor quality** — the hardest LLM task; needs the claim-checker + "distractor must be false-for-this-case" verification, else MCQs become guessable.

---

## 11. Persona-test plan

Done — see §12.

---

## 12. Persona test v0 (10 profiles) → design changes (v0.2)

Tested across the mastery/style spread (Maya M1-anxious, Sam M2-methodical, Devin M3-fast, Priya M4-strong, Leo visual, Aisha ESL, Marcus gunner, Carlos non-trad-rusty, Jenna mobile, Okafor IMG-resident). Scores 2.5–3.5/5, avg ~3.0. Verdict: the core (situation + decision-as-answer + reason-me-back) is right and beats Wave-Maven; but v0 as written assumes an intermediate desktop learner — it under-serves the on-ramp, reading-time fairness, mobile, advanced ambiguity, and grind depth. Changes:

**P0 — fold into v0:**
1. **Difficulty ramp (one dial serves everyone).** A **Learn tier** (untimed, single question-type, full stepwise scaffold, calibration *ungraded*) that graduates into timed mixed "shifts." Beginners (Maya/Carlos/Sam) get the ramp; advanced (Devin/Priya) crank it up. Introduce each new question type once, untimed, before it appears in a timed mixed set.
2. **Split the clock: read-time vs decide-time.** An untimed "read the stem" phase; the decision timer starts only when the learner is ready. Fixes the ESL/visual/mobile penalty (Aisha/Leo/Jenna/Maya) of timing language-reading as if it were ECG skill. Clock pauses on backgrounding.
3. **Decision-first path for the fluent.** Let the learner commit the disposition immediately; only force the stepwise breakdown if wrong or low-confidence (Devin/Priya/Marcus). Beginners still get the full guided sweep (tied to the ramp). Reward the fast-correct path; never make them dismiss tutor text to advance.
4. **On-trace visual reason-me-back.** Render the discriminator *on the waveform* — calipers/arrows, animate the abnormal complex, pulse the territory leads — with text secondary (Leo, + everyone). Spot-the-error is flagged by **clicking the trace**, not reading a paragraph.
5. **Resumable mini-shifts + phone-first viewer.** Make the unit a **resumable 5-case mini-shift** (hard pause/resume mid-set, exact position) inside the larger 30–50 "shift." Portrait viewer: one lead at a time, **swipe-to-compare** instead of side-by-side, fat tap targets (Jenna). Don't time fat-finger taps as if they were thinking time.
6. **Stem-acuity ≤ tracing-acuity guardrail.** Generation must police that the authored vignette never implies acuity the real (chronic) tracing can't support (Okafor/Devin "fake urgency" trap). Until STAFF-III, the ED track leans on what chronic honestly presents (old-vs-new, rate-control, chronic findings that do show up in the ED) — not dressed-up STEMIs.

**P1:**
7. **Ambiguity + restraint (for depth).** Add a **borderline/ambiguous case tier**; make MCQ distractors *defensible* (not wrong-on-sight); add a legitimate **"insufficient data → get prior / troponin / repeat"** answer; treat **disposition as a defensible range** with graded feedback, not one keyed correct (Priya/Okafor). This is what earns credibility with strong users.
8. **Tiered tutor.** Default mostly-silent + one-line on correct. Add a beginner **during-case lifeline/nudge** (costs points — Maya/Carlos), and an expert **contestable "ask why"** that defends the call against the learner's counter-argument + names the single feature that flips it (Priya/Okafor "sharper, not softer").
9. **Free-text out of timed sets + jargon glossary.** Keep meaning-graded free-text (present-to-attending, name-the-rhythm) in *untimed* contexts (ESL fairness + grind flow: Aisha/Marcus/Devin); ensure phrasing-tolerant grading; add **tap-to-define** for jargon/idioms in stems (Aisha).
10. **Opt-in competitive layer.** A composite score, percentile/streak, **blitz/hard "boss" mode**, and per-concept mastery ranks (incl. calibration surfaced *as a rank*) for grinders (Marcus) — opt-in so it doesn't make the mode feel gamey to clinicians (Okafor).

**P2:** two-tier triage clock (≈5s gestalt + a read clock) for realism (Okafor); one-line clinical **outcome reveal** after disposition (mock note).

These are additive — they raise the floor (on-ramp/access/mobile) and the ceiling (ambiguity/depth/grind) without changing the core. v0 build scope (§9) now includes the ramp, split-clock, resumable mini-shifts, on-trace visual feedback, and the acuity guardrail; the ambiguous tier + competitive layer can be v0-stretch or v1.

---

## 13. Live mock test (10 profiles, working prototype) → v0.3 changes

Historical prototype: a synthetic six-case HTML mock was used for the early interaction study and then removed from the deployed frontend. The current Clinical mode uses the real-ECG case bank. In that prototype study, the same 10 personas averaged ~3.85/5 (up from ~3.0 on the design read). The v0.2 mechanics landed — every persona confirmed split-clock, Learn tier (untimed + calibration off), decision-first + branch-on-wrong, the on-trace highlight, stacked old/new strips, and the **single-beat click targets are phone-tappable** (~139px hit band). New, mostly-small fixes:

**P0 (cheap, clear):**
1. **Kill timed-vibe leakage into Learn** — "Sick or not? **Decide fast**" and the performance HUD still show in Learn mode, contradicting "untimed/calm" (Maya, Carlos). Hide the urgency copy + the perf HUD in Learn.
2. **Action options leak the answer** — e.g. "Pads on + call cards **(likely complete heart block)**" hands the diagnosis inside the disposition (Devin). Strip diagnosis parentheticals from action/disposition options.
3. **Lock all options uniformly post-answer** — currently the unchosen option greys out while others still look clickable → "can I still change my answer?" (Sam, Carlos).
4. **Mobile tap-targets** — the mode toggle is ~33px (< 44px min); old/new strips squish to ~80px (Jenna). Enlarge toggle; keep strips legible.

**P1:**
5. **On-trace feedback depth** — upgrade the static highlight box to **calipers/arrows + a label on the trace**, mark the repeating pattern (not just one beat), and on click/spot-error cases show **faint P/QRS ghost landmarks** so clicking is guided, not guessing (Leo, Maya). "Box says *look here*, not *here's why*."
6. **Ambiguity + insufficient-data (top depth ask)** — add a first-class, **scoreable "insufficient data → get prior / troponin / 12-lead"** answer and the borderline tier; make old-or-new less purely binary; make **"ask why" contestable** (defend/concede vs the learner's counter-argument), not just re-explain (Priya, Okafor).
7. **Sharper reason-me-back at higher levels** — name the discriminators (AV dissociation, QRS > 140, concordance), not slogans like "treat as VT" (Okafor). Tie depth to the difficulty tier.
8. **Persistent jargon glossary** — only "BP" is glossed; the real blockers (VT, wide-complex, hypotension) + the triage idioms ("act now/work up") + post-answer terms are unglossed (Aisha).
9. **During-case opt-in lifeline** ("nudge me", esp. in Learn) + show the rate→rhythm framework proactively in Learn rather than only on a wrong call (Carlos, Maya, Sam).
10. **Competitive layer** — composite score, persistent/percentile, blitz/boss mode, calibration surfaced as a **named rank**, confidence → a Brier-style payoff (Marcus).
11. **Mobile session model** — resumable **5-case mini-shifts** + pause/resume + portrait single-lead/swipe-to-compare viewer (Jenna).

**P2 / reinforced:** replace the synthetic "VT"/acute strips with **real STAFF-III acute traces** — clinicians (Okafor, Devin) clock the synthetic WCT as too-clean instantly. This is already the planned fast-follow; the live test confirms it's the top realism fix.

**Validated — do not regress:** split-clock, Learn untimed + calibration-off, decision-first + branch, on-trace highlight presence, stacked strips, single-beat phone-tappable click targets, confidence slider, kind timeout.

---

## 14. GPT external review → v0.4 design locks

GPT pre-build review: **4.1/5, green-light**, with one reframe — call it **"ECG-informed clinical decision drills"** (not "clinical cases") — and one warning: *don't ship something that looks like clinical judgment but is secretly single-keyed.* Most points confirmed v0.2/v0.3; the genuine upgrades, now **locked into v0**:

1. **Graded answer model (replaces single keys).** Every option is tagged one of `ideal · acceptable · over-triage-but-safe · under-triage · unsafe · appropriate-insufficient-data`, scored on **3 axes**: ECG recognition · acuity calibration · next-action safety. Partial credit + axis-specific feedback. **"Insufficient data → get prior / troponin / electrolytes / 12-lead" is a first-class scoreable answer in v0.** old-or-new becomes **ternary** (new / old-unchanged / cannot-determine) with the deciding constraint named.
2. **Per-item evidence manifest.** Each item carries 3 layers — **ECG-supports** (what the real tracing shows) · **stem-adds** (authored age/setting/vitals/meds/prior) · **action-rationale** — plus forbidden-claims, acuity-tier, and the acceptable-answer range. The validator checks **4 dimensions** (pathology specificity · patient stability · action urgency · clinical-claim support), superseding the one-dimensional stem-acuity≤tracing-acuity rule. UI provenance line: *"Board-style case. The ECG is real and curation-grounded. The clinical context is authored to practice a decision this ECG finding can reasonably trigger."*
3. **Distractor rubric + psychometrics.** A distractor must be: plausible-in-stem · wrong-for-a-visible-reason · same-specificity-as-key · defensible-elsewhere · safe-to-teach-against. **Nano LLM DRAFTS; the discriminator/rubric is rule-backed + human-reviewed.** Track per item: distractor survival rate, wrong-option distribution, item discrimination, timeout rate, confidence error, leakage audit. **Build the validation harness BEFORE scaling the generator.**
4. **Calibration presentation.** Lead with triage-style labels (well-calibrated / cautious over-caller / risky under-caller / confident-but-brittle); metrics (over/under-triage, high-conf-wrong, Brier) in an **expandable** view, surfaced in the **end-of-shift report**, not during answering. Anti-gaming: confidence locked before reveal; no speed bonus for insufficient-data; case mix must include routine + work-up + act-now; under-triage costs more than safe over-triage; unsafe over-treatment also costs.
5. **Difficulty is a hidden vector** (ECG complexity · ambiguity · time pressure · scaffold · feedback depth) even though the learner control stays Learn/Shift — so a future Challenge/Boss tier needs no rewrite. Maya-types and Priya-types both pick "Shift" but get different scaffold/ambiguity/distractor/feedback settings.
6. **v0 scope tweaks (adopted):** add a small **clinic/pre-op lane** (lowest-stakes chronic on-ramp, no faked urgency); ship **5- and 10-case mini-shifts** first (30–50 = an eventual marathon mode); insufficient-data + graded classes in v0. Defer (confirmed): active code, telemetry streams, present-to-attending free-text, full competitive percentile layer, fully-adaptive sequencing, acute STEMI/cath until STAFF-III is ingested + separately validated.

**Net effect:** the **graded-answer model** and the **evidence-manifest + 4-axis validator** become the *spine* of both the generation pipeline and the v0 build — that's where the review added the most, and it's the highest-risk area.

---

## 15. Corrections from user review (2026-06-28)

Two design errors the prototype masked:

**A. Display = full 12-lead by default.** The mock renders a single lead II (engine convenience + clean click targets); that is NOT the intended default and undersells the mode — most clinical decisions need the 12-lead (axis, territory, BBB, ischemia localization, old-vs-new). **v0: show the full 12-lead by default.** Use a single lead / rhythm strip ONLY where it's the right tool: rhythm/rate/triage gestalt, telemetry-alarm, the rhythm comparison in old-or-new, or a **zoom-to-lead** for a click/measure task (and the mobile portrait single-lead + swipe viewer). On-trace highlight/click then operates on the relevant lead panel or the zoomed lead. (The single-beat click trick used in the mock applies to the zoomed-lead case, not the 12-lead overview.)

**B. Clock realism — the split-clock is wrong for acute.** Exact current mechanic: the READ phase is untimed; the decision clock starts only when the learner clicks "I've read it," then drains. That's unrealistic — in a code/ED the clock is already running, the patient doesn't wait for you to feel ready, and reading fast under pressure IS the skill. **Fix = situation-scaled clock:** acute / triage / code → the clock runs from the moment the ECG appears (optionally two-tier: a short gestalt window + a read window); ward / clinic (low acuity) → a brief untimed orient is acceptable for fairness (slow/ESL readers), then the decision clock. The reading-speed/ESL accommodation shifts to **generous situation-scaled timers + the glossary + tap-to-define**, NOT an unlimited untimed read in acute lanes. Honest tradeoff (fairness vs realism), resolved per situation rather than globally.

---

## 16. GPT review round-2 → v0.5 locks (grading + honesty spine)

The sharp/targeted round-2 (`clinical-decisions-review-round2.md`) delivered the depth round-1 lacked, and **corrected our worked Case W**: the "insufficient data — get vitals/12-lead *while readying pads*" option is **ideal/acceptable, not low credit** — it contains the correct *parallel* safety action; the low-credit version is the one that says "...*before* deciding whether to escalate." That correction is generalized into rule A1 below.

### A. Grading-model corrections
1. **Compound-option parsing (HARD rule).** Parse each option into components before tagging. If it contains BOTH `get_more_data` and `safety_action_present`, do NOT auto-tag `appropriate-insufficient-data`; split into `data_request_component` + `safety_action_component` and grade the bundle. Insufficient-data is low-credit only when the required action is *delayed*; high-credit when a required *parallel* safety action is included.
2. **Per-question-type scoring schemas — the answer-class × 3-axis model is NOT universal.**
   - **MCQ / triage / stepwise-disposition** → answer-class (ideal/acceptable/over-triage-safe/under-triage/unsafe/insufficient-data) × axes.
   - **Triage** axes = `pattern_threshold_hit` (recognition is *inferred from the choice*, not observed) · `acuity_calibration` · `action_safety`. Don't score "ECG recognition" as if stated.
   - **Click-the-abnormality** → NOT clinical-action classes. Use **ROI geometry** + axes `concept_identification · lead_selection · endpoint/region_accuracy · measurement_precision`. No calibration accrues unless a follow-up action question is attached.
   - **Old-or-new** → add a 4th axis **`comparison_validity`**. "Cannot determine" is appropriate/high-credit only when the display lacks the leads to prove the claim; inappropriate/low when full comparable 12-leads are shown. (Couples to the display rule: a lead-II-only screen makes a keyed "old/unchanged for axis/wide-QRS" answer **invalid**.)
3. **Distractor realism.** Replace cartoonish distractors ("reassure + discharge" for an inpatient) with plausible-but-wrong ones ("repeat ECG in the a.m. unless symptoms worsen"). Obvious-dumb options inflate discrimination artificially.

### B. Honesty spine — the 4-axis validator is necessary but NOT sufficient
It checks finding- and stem-plausibility *individually*; it misses the **causal/temporal bridge** between tracing and vignette. Add (this **replaces** the 1-D stem-acuity ≤ tracing-acuity rule):
1. **`acute_temporal_causality_check`** — acute/escalating/evolving/dynamic/serial/crushing/diaphoresis/rising/new stem language requires ECG evidence of serial change OR acute-dataset provenance OR a prior comparison showing newness; else force wording to "abnormal ST-T finding; evaluate in context and compare prior." Reject "acute/evolving/new ST depression," "NSTEMI ECG" on a chronic strip.
2. **`symptom_causality_strength_matrix`** — per ECG concept, define symptoms it *may explain / may contextualize / must-not-explain*. (Isolated 1° AVB may contextualize med-review/teaching but **cannot be keyed as the cause of syncope** without extreme PR / pauses / high-grade block / rhythm correlation.)
3. **`transient_event_evidence_check`** — torsades / VT-runs / pauses / telemetry-alarm / syncope-rhythm claims require rhythm-strip/telemetry evidence or an explicit authored non-ECG data layer; never grade a transient dx as *ECG recognition* on a resting 12-lead.
4. **`evidence_binding_linter` (cheapest, highest-value).** Every `ecg_supports` claim binds to `supported_objective_id` + measurement threshold (if applicable) + accepted leads/ROI + `source_type` (measured | curated_label | authored_context). **Ban unbound adjectives**: dynamic, evolving, new, acute, territorial, reciprocal, hyperacute. Reject if no ROI/lead evidence backs a claimed territory. Stops "non-specific ST-T" inflating into "inferolateral dynamic NSTEMI."
5. **`required_safety_action_matrix`** — per high-acuity concept, the safety tokens an ideal/acceptable option MUST contain (symptomatic complete-block → pacing-pads | TCP-ready | call-help | bedside-assessment-now; unstable WCT → synchronized-cardioversion | pads | act-now). If absent → cap class at `under-triage`.
6. **`acuity_cap_by_ecg_concept`** — per concept `max_action_urgency` unless extra evidence (isolated 1°AVB → max low, can't key urgent-admission/pacing/syncope-causation; long-QT → max moderate w/o symptoms/med-context, can key med-review/lytes, can't key torsades-tx; chronic ST-T → workup, not activation). Stops calibration acuity following the *story* instead of the *finding*.

### C. Calibration anti-gaming
- **`avoidance_index`** — full insufficient-data credit ONLY when `manifest.epistemic_status == intentionally_underdetermined`; in *determined* high-acuity cases, insufficient-data must bundle a simultaneous safety action; cap unjustified "cannot determine" at ~40%; end-shift "Avoidant caller" label when insufficient-data rate >2 SD above expected.
- **Proper confidence scoring with upside cap** — low confidence caps max credit even when correct (correct@high 1.0 / @med 0.85 / @low 0.65; wrong@low 0.25; wrong@high 0.0 + flag); confidence **required** in Shift/Challenge (no default slider position), optional/hidden in Learn; show confidence-calibration **separately** from clinical-safety.

### D. Clock spec (replaces the opt-in decision clock)
Timer starts when ECG pixels + controls + stem are present (not during network/layout); answer-time stops on clinical choice; confidence-time logged separately; backgrounding pauses in Learn only (Shift >10s = abandoned — *soften for mobile, see §G*). Orient + decide = wall:

| Situation | Orient | Decide | Wall | Timeout = |
|---|---|---|---|---|
| Learn (any) | — | — | unlimited | no penalty |
| Clinic / pre-op | 15s | 90s | 105s | too-slow (not unsafe) |
| Clinic click/measure | 20s | 70s | 90s | too-slow |
| Old-or-new | 20s | 100s | 120s | too-slow |
| Ward noncritical | 10s | 65s | 75s | too-slow + mild calib |
| Ward telemetry/brady | 10s | 50s | 60s | under-triage if high-acuity |
| ED non-arrest | 8s | 37s | 45s | counts vs acuity calib |
| Critical / code | 5s | 10s | 15s | **unsafe delay** |

Labels: acute = "First look" / "Commit action"; clinic = "Orient" / "Decide". **Ban** "Read at your own pace" / "Start clock when ready" in acute lanes. Accommodation = globally-scaled timers (~1.5×, capped), **scored separately, not as lower skill**; NO unlimited read in ED/triage Shift. Fairness via **stem-length caps** (triage ≤18 / ED ≤28 / ward ≤35 / clinic ≤45 words) + structured chips (age/setting/symptom/BP/mental-status) + glossary (tap-to-define pauses only in clinic/Learn) + mobile (timer starts after viewer interactive; zoom/pan logged as UI-time, not decision-time).

### E. Display + universal click model
Default **full 12-lead**; pin a rhythm strip where rhythm/rate is central; single-lead/zoom only where the construct allows. **A rhythm-strip-only screen silently narrows the construct** for axis/territory/BBB/old-new/ST-audit — valid only when the item blueprint says `tested_scope: rhythm_only`. Per type: triage = 12-lead + pinned strip + vitals chips; stepwise = 12-lead + long II, each step highlights its own ROI; click = finding-dependent (interval → zoomed lead + calipers; ST → box ROI in accepted leads); old-or-new = **stacked full 12-leads, identical scale + lead order** + ghost-overlay toggle; spot-the-error = 12-lead + machine-read panel (select the bad sentence AND click proof). **Universal click record:** `lead_id, panel_id, x_ms_from_panel_start, y_mV, beat_index, viewport_state`; target_types = point/interval/segment/territory/lead_panel. Mobile: first tap zooms, second tap/drag submits, confirm button for click items.

### F. v0 acceptance checklist (hard-stops — don't ship until enforced)
Compound options component-parsed before tagging · atropine-only ≠ acceptable for symptomatic complete block without pacing readiness · insufficient-data low-credit when action delayed / high-credit when parallel safety action present · old-or-new verifies display comparability before keying "old/unchanged" · click items use ROI geometry not triage classes · acute temporal words require serial/acute-dataset evidence · transient-arrhythmia claims require telemetry/rhythm-strip evidence · isolated low-acuity findings can't be made causal for syncope/shock without extra evidence · ED/triage Shift never uses unlimited-read opt-in · rhythm-strip-only requires `tested_scope: rhythm_only`.

### G. My flags (apply judgment — don't adopt verbatim)
- **Scope triage.** Large validator/scoring surface. **v0 must-haves** = the honesty/safety spine (compound-parsing, evidence-binding linter, acuity-cap-by-concept, required-safety-action matrix, the 3 causal-bridge checks, per-type scoring schemas, the clock table, full-12-lead display). **Defer to v0.x** = full psychometrics/Brier, the SD-based "Avoidant caller" label, Challenge mode, the exact upside-cap weights. **Build the validation harness with these checks FIRST**, then run the nano generator against it.
- **Pilot, don't trust, the numbers.** Timer seconds (8+37, 5+10…), credit weights (1.0/0.85/0.65/0.25), the 40% cap, >10s-abandon, >2 SD — reasonable starting defaults, tune by playtest. The >10s background-abandon is likely too harsh for mobile; soften.
- **Clinician-reviewed content tables.** `required_safety_action_matrix`, `acuity_cap_by_ecg_concept`, and `symptom_causality_strength_matrix` are **clinical knowledge artifacts** — highest-risk-if-wrong and most authoring-heavy. They double as the long-pending **danger/acuity dimension** (task #6). Author + clinician-review before scaling the bank.

**Net:** round-2 converts the honesty spine from a 1-D rule into a real **causal-bridge validator + per-concept caps + evidence binding**, and makes scoring **per-question-type** rather than one model. These are the v0 validation-harness spec.

---

## 17. v0 BUILT + verified (validation-harness-first)

All four phases of the plan are implemented and tested (backend suite 63 passed/5 skipped; frontend typecheck clean; browser-verified end-to-end). Details: memory `build-clinical-decisions`.
- **Phase 0** — danger/acuity content tables (`backend/app/clinical/content_tables.py`); the long-pending acuity dimension, clinician-review-flagged.
- **Phase 1** — the honesty spine: `clinical/schemas.py`, `clinical/grounding.py`, `clinical/harness/*` (every §16B check), seed bank + adversarial tests. **Exit gate green:** 6 seed items pass; the 3 review overclaims are rejected by the expected check; the corrected Case W is high-credit.
- **Phase 2** — per-type grader (`clinical/clinical_grading.py`, the answer-class model — separate from the Foundations grader, reuses the grade-dict contract → mastery untouched), shift sessions (`clinical/shift.py` + `clinical_shift_sessions`), endpoints (`clinical_routes.py`).
- **Phase 3** — native React `/practice` (Clinical Decisions): picker → timed shift on real fixture tracings → answer-class grading → calibration report. The prior interpretation workflow moved to `/interpret`. Clock starts on ECG render (not opt-in), per §15B/§16D.
- **Phase 4** — nano generation **gated by the harness** (`clinical/generator.py`): drafts are accepted only if they pass; `measure_convergence` is ready for the real accept-rate run (needs a live model).

v0 served bank = 6 hand-authored fixture-backed items (renderable). **Follow-ups:** on-trace reason-me-back (add viewerActions to the grade), real generation-convergence run + scaling, clinician review of the content tables, STAFF-III acute lane.
