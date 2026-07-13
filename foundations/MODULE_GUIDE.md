# Foundations Module — Complete Guide (v1.6)

*"How to read an ECG" — the first module of the ECG_Tool learning platform. Full breakdown for review. Companion: MODULE_TEXT.md (verbatim copy).*

---

## 0. Changes since the last review (round-4 production hardening)

Round-3 was judged "very good pilot shape; final pre-pilot polish, not another architecture pass." Its P0 items remain in place. New in v1.6:

1. **Every P2 drag interaction now has a visible keyboard/tap path.** P/QRS/T placement uses selectable labels plus explicit waveform-target buttons; ruler and interval handles expose slider semantics, arrow-key control, trace tapping, and step buttons; ST, R-wave progression, and axis have labeled native ranges plus direct buttons. Focus indicators are visible throughout.
2. **Baseline-first micro-step.** S7 now asks the learner to identify the TP baseline before the ST comparison can open. The learner then moves ST off baseline and restores it, making the reference relationship explicit rather than implicit.
3. **Tangent-safe tutor return.** A learner may ask a relevant clinical tangent, receive a bounded answer, and use an explicit “Return to {scene}” control; the active scene and unfinished interaction remain unchanged and focus returns to the scene.
4. **Precise guided evidence bridge.** Key visual interactions post scene, interaction, concept, subskill, score, attempts, assistance, provenance, and eligibility to the host. The host records guided receipts; authored simulations are explicitly ineligible for independent visual mastery.

Previously delivered in v1.5:

1. **Grader comparator parsing.** "QRS under 3 boxes" → narrow (no longer mis-read as wide), "QRS over 3 boxes" → wide, "PR over 200 / over 5 boxes" → long, "PR less than 200" → normal, "rate over 100" → fast, "rate under 60" → slow. (Comparator nudges the boundary value by 1 before the box/ms conversion.)
2. **Left-axis rule wording fixed in the grader** so it can't reintroduce the false absolute: "Left axis in these teaching cases: lead I is up and aVF is **clearly** down. Borderline leftward cases are refined later." (+ matching right/normal rules.)
3. **`rhythmEvidence` honesty.** When a case has no real `lead_ii` (deviation categories use a median beat tiled at the real rate), S10 no longer asserts "a P before **every** QRS … **consistent** in shape." It says "on this teaching rhythm strip the visible P–QRS pattern is **sinus-appearing**." Real-lead-II cases keep the stronger wording.
4. **Tutor guard gained an interpretation redirect.** "What's wrong with this ECG?" now defers ("I won't interpret the tracing for you — describe what you see…"), while "what's wrong with my answer?" stays tutoring. Confirmed "how long should the QT be?" is **not** false-blocked by the "long qt" diagnosis term.
5. **S10 synthesis grammar** reads as a clean sentence for every rate ("sinus pattern, normal rate ~64 bpm, normal axis, PR 134 ms, QRS 74 ms, ST/T normal-appearing").
6. **Smaller polish:** Part-2 test-out matches the S5 checklist ("upright same-shaped P … steady PR … sinus pattern?"); S5 strips labeled "teaching strips"; T-wave KB "so they can **activate** again."

**Rounds 1–2 (already in place):** scope/overclaim fixes, the clinical/diagnosis/patient tutor guard, S9 left/right axis, S10 order (PR + QRS width separate), softened ST-T/transition/aVR absolutes, "not assessable" vocabulary, S2/S4/S7/S8/S9 understanding-gates, grader box-unit parsing + conditional ahead-credit, label consistency, payoff de-emphasis of time.

**Doc hygiene:** the verbatim doc now flags every templated line as "renders ONE of …" so a reviewer doesn't mistake shorthand (the "|", the S12 failed-end branch) for literal on-screen text.

Still deferred: optional re-export of real `lead_ii` for all categories if authentic beat-to-beat variability is wanted; a grader regression suite seeded from real pilot answers.

---

## 1. What this module is, and its pedagogy

- **Audience:** medical students / complete beginners. No prior ECG knowledge assumed.
- **Goal:** independently perform the **beginner descriptive sweep** of a 12-lead — Rate → Rhythm → Axis → PR → QRS width → ST-T → Synthesis.
- **Core constraint — "describe, don't diagnose."** Names + measures every component (and its normal value); defers all **clinical meaning** (what it means, causes, danger, diagnoses) to later modules. Enforced in the tutor (scope split + diagnosis/patient guards), the grader (credits "ahead" answers only for the descriptive finding they imply; steers back to description), and the copy. **"Not assessable" is a valid, taught answer.**
- **Finding-language:** narration/grading is descriptive ("wide QRS", "long PR", "left axis", "not clearly sinus") — never diagnoses.
- **Format:** 13 scenes (S0–S12), 4 parts, about 25 minutes for the core path (longer with tutor tangents, accessibility exploration, or retries), self-paced; each scene has a checkpoint that unlocks "Next"; any scene/part can be skipped or tested-out of.

---

## 2. Architecture & how to run it

Self-contained static web app, vanilla JS, no build step, under `foundations/`:

| File | Role |
|---|---|
| `index.html` | Shell: header (progress, Normal-values), 4-part rail, scene area, AI tutor panel, nav. |
| `ecg.js` | Calibrated rendering (`ECG`, 25 mm/s · 10 mm/mV). Synthetic-parameterized leads + real-data rendering from PTB-XL median beats (12-lead **with a tiled/real lead-II rhythm strip**). `caseTruth()` derives ground truth. |
| `engines.js` | Interaction engines (`Engines`): conduction-heart animation and label placement, box-count ruler, rate lab, interval calipers (text verdict), TP-baseline selection, ST comparison, R-wave progression (reports transition lead), hexaxial axis dial (names left/right). Each direct-manipulation engine has a visible non-drag path. |
| `ui.js` | AI tutor (live LLM + grounded KB; clinical/diagnosis/patient guards), meaning-based grader (box parsing, conditional ahead-credit), Normal-values card. |
| `scenes.js` | 13 scenes (`SCENES`) + `miniCheck()` concept-check helper (dedupes by question). |
| `app.js` | Routing, progress, per-scene skip (tracked), per-part test-out, resume. |
| `data.js` + `data/cases.json` | 22 real PTB-XL cases → `CASES` / `pickCase()`. |

**Run (two servers):** static — `python -m http.server 8080 --directory foundations`; live tutor (optional) — from project root `python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000`. Offline → grounded local KB.

---

## 3. The data — which ECGs, and ground truth

**22 real PTB-XL records** (chronic resting 12-leads) via `scripts/export_foundations_cases.py`. Targeted, not volume.

| Category | Count | IDs | rhythm strip |
|---|---|---|---|
| Normal | 4 | #3, #10, #14, #21 | real lead_ii |
| Brady | 2 | #2, #12 | real lead_ii |
| Tachy | 3 | #108, #222, #548 | real lead_ii |
| Long PR | 3 | #102, #191, #209 | tiled median |
| Wide QRS | 4 | #279 (axis −39° → also left axis), #286, #172, #195 | tiled median |
| Left axis | 2 | #41 (−74°), #103 (−43°) | tiled median |
| Right axis | 2 | #1516 (+107°), #3514 (+106°) | tiled median |
| Noisy | 2 | #38, #100 | real lead_ii |

Each case: `features` (HR/PR/QRS/QT/QTc/axis/…), `median` beats (12 leads), `lead_ii` where available, `sinus`/`st_normal` flags. **`caseTruth`** thresholds: rate <60 brady / >100 tachy; axis <−30 left / >90 right; PR >200 long; QRS ≥120 wide; rhythm `sinus` unless noisy/`sinus===false` → **null (ungraded)**; ST `flat_st` unless `st_normal===false` → **null**. **Capstone truth:** S12 case 2 = #279 → wide QRS (160 ms) **and** left axis (−39°).

**Synthetic vs real:** manipulable concept tools synthetic (S1/S2/S4 slider/S5/S7/S9); real PTB-XL for quality, rate quiz, intervals, 12-lead, all practice.

---

## 4. The 13 scenes

**PART 1 — What am I looking at?**
- **S0** — promises the beginner descriptive sweep; tutor offers help with *find/measure/name*, defers clinical meaning/diagnoses/urgency.
- **S1** — conduction-heart animation draws the trace; place P/QRS/T. Captions/gloss: "atria/ventricles **electrically activate**", "ventricles reset".
- **S2** — calibration (small box 40 ms wide / 0.1 mV tall; big = 200 ms; calibration pulse). Box-count (±25 ms) → **gated check** ("one big box = ? ms").
- **S3** — "**readable for what?**" Tag 4 real strips; **all-correct** required (re-tag wrong). Teaches rate-from-clear-QRS vs avoiding PR/ST-T on noise.

**PART 2 — Measure one beat**
- **S4** — "why 300?"; **two gated method checks** (regular → 300-rule; irregular → 6-sec) before the rate lab + real rate quiz (±12 bpm).
- **S5** ("Sinus pattern?") — checklist ("we infer from P waves"; rate isn't part of it). Tag 3 strips Sinus-pattern / Not-sinus-pattern; sinus-brady framed as vocabulary.
- **S6** — PR (start of P → start of QRS) on #3, then QRS width (first deflection → return to baseline) on #172; calipers show a text verdict; "measure first, then compare."
- **S7** ("…the normal reference") — identify the **TP baseline** first; then move ST from the **J point** away from and back to that reference; the **normal reference** (ST near baseline, T usually follows main QRS); QT reworded; **gated check** ("ST judged against which line?").

**PART 3 — One lead → twelve**
- **S8** — "12 cameras, same beats, not 12 events." Scrub V1→V6; **gated transition check** ("which lead first R>S?"). aVR aside: the **P wave** in aVR usually points down (QRS/T often too).
- **S9** — hexaxial dial; lesson/readout **name left/right** and separate "leftward" from "left axis." Reach normal + off-normal → **gated "name it" check**.

**PART 4 — The systematic read**
- **S10** — two real 12-leads narrated; rail **Rate first**, PR and QRS width separate steps; predict-rate / predict-wide micro-quizzes; synthesis includes ST/T (or "not assessable"). Rate narrated as "fast rate (>100; tachycardia)".
- **S11** — real normal (#14, full) then deviation (lighter); free-text per step (sentence frames; ternary "sinus / not / not clear / not assessable"; left/right axis prompts); one retry; **critical findings (wide QRS / long PR / left/right axis) can't be skipped** at ≥0.5.
- **S12** — fill 6 fields (real normal #21); then blank one-line read (#279), order-agnostic, must catch the real deviations **and cover ≥4 of 6 domains**, ≥0.6, ≤2 tries; **separate pass vs failed-end messages**; payoff = accuracy% (time secondary).

---

## 5. AI components

### 5.1 Tutor (ask about any concept)
Resolution: **guard** (`isClinical`) defers — clinical terms, **named diagnoses** (`DIAGNOSIS`), **real-patient/symptoms** (`PATIENT` → safety redirect), or (`MEANING` ∧ `FINDING`); foundational "what is/represents" passes → **live nano LLM** (`/tutor/foundations`, `FOUNDATIONS_SYSTEM_PROMPT`) → **degenerate-reply filter** → **grounded local KB** (offline). Three deflection variants: patient-safety, danger, diagnosis, plus the standard clinical one.

### 5.2 Grader (`grade`/`matchConcept`)
Meaning-based: tokenization, **numeric + box-unit parsing**, negation guards, concept-scoping, partial credit, per-miss **teachable rule**. **Conditional ahead-credit**: a diagnosis credits only its implied descriptive finding when expected. Recognizes uncertainty phrases ("not assessable") to acknowledge restraint without mis-crediting.

### 5.3 Platform claim-check (context)
Backend's case-grounded tutor (`SYSTEM_PROMPT`) flags unsupported measurement/diagnosis claims — same "LLM is never the source of truth" philosophy (not used by Foundations directly).

---

## 6. Quizzing & checkpoints

| Scene | Task | Pass |
|---|---|---|
| S1 | place P/QRS/T | ±70 px |
| S2 | box span **+ check** | ±25 ms, then "200 ms" |
| S3 | tag 4 strips | **all correct** |
| S4 | **2 gated method checks** + rate read | both checks + ±12 bpm |
| S5 | 3× sinus-pattern / not | all answered |
| S6 | PR then QRS | each ±30 ms |
| S7 | identify TP baseline, contrast/restore ST **+ check** | correct baseline + off/on comparison + "baseline" |
| S8 | scrub **+ transition check** | identify transition lead |
| S9 | zones **+ name-it check** | both zones + "left axis" |
| S10 | predict ×2 cases | step through |
| S11 | free-text ×2 (fading) | ≥0.5 multi (no critical miss) / full single, 1 retry |
| S12 | 6 fields + blank one-liner | deviations + ≥4/6 domains, ≥0.6, ≤2 tries |
| Per-part test-out | 1 MCQ/part (Part 3 now tests left axis) | correct → "unlocked (tested out)" |

---

## 7. Reference card & navigation

Normal-values card (9 rows, beginner-safe wording, progressive unlock; footer: estimate from boxes then compare with printed). 4-part rail + progress %; Next gated; "Skip for now" (tracked as skipped ≠ mastered); per-part test-out; resume via localStorage.

---

## 8. Deferred to later modules

Rhythm names (AFib, flutter, blocks), what abnormal intervals/axis/ST-T mean, which lead sees which wall, urgency/danger. Previewed in the S12 payoff.

---

## 9. Open questions / watch-items (round 4)

Resolved across rounds 1–4: scope/overclaim, the clinical/diagnosis/patient/interpretation tutor guard, tangent-safe return, S9 left/right + "leftward vs left axis" consistency, S10 order + synthesis grammar, ST-T/transition/aVR absolutes, "not assessable", S2/S4/S7/S8/S9 understanding-gates, grader box-unit **and comparator** parsing, conditional ahead-credit, tiled-strip rhythm honesty, label/wording consistency, payoff metrics, review-doc shorthand hygiene, all six P2 non-drag paths, the TP-baseline micro-step, and guided evidence receipts that exclude authored simulations from independent visual mastery.

Round-3 marked these as **post-first-pilot watch-items** (observe real learners, don't redesign blind):
1. Do learners understand "leftward but not always left axis," or do they still over-call left axis?
2. Do learners overuse "not assessable" on readable cases?
3. Can learners produce the S12 one-liner without just listing deviations? (Now nudged by the ≥4/6-domain pass condition.)
4. Are the S8 transition-lead choices visually obvious, or too dependent on UI hints?

Remaining pre-broader-release work: consider real `lead_ii` re-export for authentic variability; seed a grader regression suite from real pilot free-text answers; observe real keyboard, touch, and screen-reader learners and refine from evidence.

---

*Build state: v1.6, embedded in the main Next.js app at `/learn/foundations`. JavaScript syntax and Next.js TypeScript checks pass; focused Playwright coverage verifies keyboard-only S1 completion, guided synthetic-receipt semantics, tangent return with checkpoint/focus preservation, and visible non-drag paths for the ruler, calipers, ST comparison, R-wave progression, and axis dial. Functional module on a curated 22-case slice.*
