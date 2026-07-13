# Storyboard v7 — Foundations / "How to read an ECG: rate, rhythm, axis, and the waveform"

The first module. Audience: someone seeing their first ECG. **Scope: teach how to READ an ECG end to end at
the component level — the grid, every wave/segment/interval and its NORMAL value, rate, rhythm/sinus, AXIS
(basics), morphology + R-wave progression — and then build the systematic-read HABIT through worked examples
and embedded practice. We teach what each component IS, its expected/normal value, and how to read it; we
DEFER the *clinical meaning* (causes / significance / urgency) to later modules — while still teaching
learners to OBSERVE AND DESCRIBE deviations from normal in finding-language.** Tone: warm, encouraging,
confidence-building, never clinical-scary. By the end the learner can take a 12-lead, run the sweep, and say
e.g. "sinus, ~95 (mild tachy), PR a touch long ~210 ms, QRS normal, normal axis, normal-looking beats —
nothing I'd call abnormal" — i.e. describe, not yet diagnose.

Lineage: v2 → v3 (10-persona test) → v4 (physiology + realistic measurement) → v5 (over-deferred
axis/segments) → v6 (axis + segments + normal values back; added worked→guided→independent spine) →
**v7 (10-persona DEEP scene-by-scene test: fixed the axis rule/range contradiction, T-concordance,
sinus definition, the rate-before-regularity dependency, R-wave transition; split the overloaded S6;
de-loaded S1; made worked examples active; hardened the practice release + free-text grading spec).**

Locked: standard sweep is the framework AND it is performed (Rate → Rhythm → Axis → Intervals →
QRS/morphology → ST-T → Synthesis), ST-T taught only at the *normal-appearance* level; static/measure
tracings render from **real PTB-XL median beats**; multi-lead scenes + practice use **real 12-lead corpus
records** (incl. describable deviations: tachycardia, long PR, wide QRS, axis deviation); the quality
example uses a real flagged record.

## What the deep persona test changed (v6 → v7)
Scored ~3.6/5, "build-ready after a fix pass." Strongest moment (9/10): the drag-the-axis-vector. Fixes:
- **Axis (was a real error, 8/8):** the I+aVF "both up" rule covers ~0°→+90°, but the card said −30°→+90°.
  Now reconciled — the taught normal IS the quadrant the rule delivers; the −30° extension is named as a
  *forthcoming refinement* (lead II), and the hexaxial circle **shades the normal sector green** so rule,
  picture, and card agree. "aVF down but I up = *borderline*, pinned with lead II later" (not "abnormal").
- **T-wave concordance:** no longer stated flatly — "upright where QRS is dominantly upright (e.g. II);
  **aVR and V1 are normal exceptions**."
- **Sinus definition:** dropped "sensible rate" (sinus brady/tach are still sinus); **added "same P
  morphology beat-to-beat"**; taught on lead-II-visible criteria, aVR check moved to the 12-lead scene.
- **Rate:** an **eyeball-regularity precheck** comes first; the 300-rule is flagged **regular-rhythm-only**
  (irregular → 6-second × 10).
- **R-wave progression:** transition = the **R/S ratio crossing 1** (R grows *and* S shrinks), normally V3–V4.
- **Split the overloaded S6** into intervals (PR/QRS, measured) and segments+template (ST/T, QT/U footnote).
- **De-loaded S1** to name only P/QRS/T; other labels are introduced where measured.
- **Active worked examples** (predict-before-reveal, max 2 narrated); **fading guided practice** with ≥2 axis
  reps; **solo read keeps the sweep rail visible** as silent structure; **per-component free-text grading spec.**
- Per-scene test-out; scoring starts at S2; deferral stated once per part + always paired with an on-trace
  highlight; minor numeric/physiology cleanups (QRS box-count, AV-delay wording).

## Benchmarked against existing tools (gap analysis)
Dubin (Rate→Rhythm→Axis→…), LITFL, Geeky Medics, Ninja Nerd, and HEARTS all treat **axis** and **R-wave
progression** as *basic-read* steps (the clinical *causes* of deviation are not). Good tools always give
explicit normals (PR 120–200 ms, QRS <120 ms, axis quadrant, rate 60–100) → the **normal-values card**. The
hardest thing for beginners is "understanding abstract graphical information" (BMC Med Educ) → lean into the
wavefront animation, on-trace highlighting, and the drag-the-axis-vector. The biggest training gap is no
structured practice + feedback; deliberate practice with immediate feedback (ECG Wave-Maven) builds
competence → Part 4 is **gradual release: modeled → guided → independent**, each with immediate reason-me-back.

## Measurement philosophy (don't over-promote calipers)
Everyday methods, in order: (1) **eyeball / count boxes** to approximate; (2) **read the machine's printed
numbers** (rate/PR/QRS/QT/axis) and check them against the tracing — for a beginner, "the computer already
measured these; let's read them ourselves and check them" (the deeper "trust the *numbers*, re-derive the
*diagnosis*" lesson is a LATER module); (3) **calipers** = a precision tool for a borderline value, NOT the
default. Accuracy scoring rewards the learner's *estimate/read*; no scene is gated behind caliper use.

## Design rules (every scene)
- **Ground-up, dependency-forced.** Nothing used before taught: grid → waves → readability → regularity+rate
  → rhythm/sinus → intervals → segments/template → (expand to 12 leads) → R-wave progression → axis → the
  systematic read → practice. (No criterion may reference a lead/concept not yet on screen.)
- **Animate the concept, freeze (on real median beats / real 12-leads) for the skill.**
- **Grounded in numbers + the image.** Boxes→ms/mV; estimates/printed values tied to the tracing; every
  normal value stated explicitly and added to the **normal-values card** (summonable any time, incl. mid-practice).
- **Physiology-grounded depth, gently.** The cardiac *why* — P small (thin atria), QRS tall (thick
  ventricles), PR-segment flat (the AV node briefly *delays* the impulse — the atrial-to-ventricular
  electrical hand-off, which also lets the atria finish contracting before the ventricles fire), narrow QRS
  (fast His–Purkinje), QT scales with rate, axis = net ventricular-depolarization direction (down-and-left
  because LV mass dominates), R-wave progression (the precordial "camera" pans across the septum toward LV).
  Physiology for intuition — *not* pathology.
- **Teach components + normal values; defer clinical MEANING; still teach observe-and-describe.** Name
  deviations in finding-language ("PR is long ~220 ms"; "QRS is wide"; "axis is left") and defer *what they
  mean*. State the deferral **once per part, not once per component**, and **always pair a deferral with an
  on-trace highlight** of the thing (a cliffhanger, not a withholding) plus a one-line "what's coming"
  breadcrumb. **Never penalize a correct-but-ahead answer** — "right, and we'll formalize that later."
- **Measure realistically** (boxes + read-and-verify the printed numbers; calipers optional precision).
- **Mixed layouts**; teaching text in a caption panel or the tutor stream per scene.
- **Manipulable where it builds intuition** (draggable handles/sliders/vector over static labels).
- **Define on first use + persistent glossary/hover + gloss bare terms inline in the spoken voice** — e.g.
  "J point (where the QRS ends and the ST begins)," "isoelectric (flat, on baseline)"; idiom-free tutor
  voice. Free-text graded on **meaning, not keywords**.
- **Warm, show-don't-scold error tone.** Wrong answers are reframed and re-offered; the tutor reasons the
  learner back on the trace rather than marking it.
- **Progress + resume + test-out.** Show the map on S0 ("Foundations · 0/13 · ~25 min · test out of any
  part or scene"); persistent "Part X/4 · scene Y/N" + completion meter; save/resume; **per-scene AND
  per-part test-out** (so a strong learner can skip rate/rhythm and still reach axis).

## Ask-anything workflow
Persistent Ask in every scene → pause lesson state → answer grounded only in what's been taught (won't leap
ahead) → **the answer highlights/replays on the tracing** → tight (≤1 short paragraph) → one-tap "back to
the lesson." The tutor proactively offers help at likely-confusion beats. In the independent read the tutor
is silent unless asked (learner-led), then drops back to coaching on request.

---

# PART 1 — "What am I looking at?" (S0–S3)
## S0 — A gentle start (+ the map)
Full-bleed: a heart beats, a tracing scrolls out beneath it. Tutor (warm, no stakes): "An ECG is just the
heart's electrical signal, drawn over time. We'll learn to read one end to end, one piece at a time — no
prior knowledge needed. Ask me anything, anytime." **On-screen: the progress/test-out map** ("4 parts ·
~25 min · skip any part or scene you already know"). State the throughline once: "we'll learn to *describe*
what we see first; what each finding *means* comes in later modules." → Begin (skippable for returners).

## S1 — One beat = one electrical wave (keystone)
Split: conduction schematic | a beat drawing in. **Signature animation:** the depolarization wavefront
sweeps the heart and **draws the waveform in real time** — atria→P, AV delay→flat PR segment, ventricles→QRS,
repolarization→T. **First pass in plain words** ("the top chambers fire… now the big ones"); **names only
P, QRS, T** (the three things the animation actually draws) + label-drag on the second pass. (PR-segment,
the Q/R/S split, ST segment, and the U-wave are introduced later, *where they're measured* — not pre-loaded
here.) **Physiology (intuition):** P small (thin atria), QRS tall (thick ventricles), PR segment flat
(the AV node briefly *delays* the impulse — the atria finish contracting before the ventricles fire),
T points the same way as the big spike *in this lead* (lead II). Interaction: scrub/replay → drag P/QRS/T.

## S2 — The graph paper is your ruler (+ calibration habit + first scoring)
Zoomed grid + cal pulse. Animate rulers — **do the time axis fully, then the voltage axis** (don't interleave):
small 0.04 s / big 0.2 s; 5 small = 1 big; 5 big = 1 s; then 0.1 mV / 0.5 mV; cal pulse = 10 mm = 1 mV /
0.2 s. **Box-count accuracy scoring starts here** (you/actual/% on a span), so the skill is practiced, not
lectured; the **box-math entry lands on the normal-values card** immediately. Habit seed: "glance at the cal
pulse every time — if the paper isn't standard, the measurements lie (the box sizes would be wrong)."
Calipers introduced risk-free as **one precision tool**, explicitly not the default.

## S3 — Is it readable? (a quick scored quality check)
A short **scored rapid-classify** of 3–4 strips (clean vs too-noisy) + bounding-box the artifact — not a
single binary. "The first question is always 'can I even read this?'" Lead-misplacement is *not* mentioned
here (it dangled with no payoff). Keep it the shortest scene. **Bridge → Part 2:** "We can read it. Now
let's measure one beat."

# PART 2 — "Measure one beat" (single-lead, on lead II) (S4–S7)
## S4 — Regular? then Rate (count boxes; read the report)
**Regularity first:** eyeball the R–R — evenly spaced or not? (full rhythm treatment is S5; here it's just
the precheck that picks the rate method). Then rate on a lead-II strip: animate box-counting + a
**spacing→rate slider** (closer = faster). **300-rule (primary) — regular rhythms only;** if irregular,
**6-second × 10**; 1500-rule as an aside. Box-count estimate **scored vs the real value with a stated
tolerance** ("within ~10 bpm = nailed it"), and the tutor frames the estimate-vs-printed gap as *normal
and expected* before the learner sees it. Physiology: the SA node sets the rate. Normal **60–100** → card;
<60 "bradycardia" / >100 "tachycardia" as *descriptions*. **Mastery: rate.**

## S5 — Sinus? (rhythm + the P–QRS relationship)
On the lead-II strip. **Sinus (lead-II-visible criteria) = P before every QRS, a QRS after every P, P
upright in II, P the *same shape every beat*, constant PR.** (Rate is NOT part of the definition — sinus
brady and sinus tach are still sinus; that's called out explicitly.) **march-out** as the precision check;
bounding-box a P; check 1:1 and same-shape. Physiology: the impulse starts at the SA node high in the right
atrium and spreads down-and-left, so its P points toward II (upright) — the same directional logic that
returns for axis. ("There's one more confirmation — the P is *inverted in aVR* — which we'll add once the
12 leads are on screen in Part 3.") **Mastery: rhythm/sinus.**

## S6 — Intervals you measure: PR & QRS
Zoomed real beat. Measure by **counting boxes** and by **reading the printed PR/QRS**, checked against the
tracing; a **draggable handle recolors at the normal threshold**; calipers offered to pin a borderline.
- **PR interval** = AV-node conduction time; normal **120–200 ms (3–5 small)**.
- **QRS duration** = ventricular activation; normal **up to ~3 small boxes (<120 ms)** — narrow because
  His–Purkinje spreads it fast (wider when conduction is abnormal — *causes are a later module*).
Both scored vs the real value. → card. Describe-don't-diagnose: "long PR," "wide QRS" are observations.
**Mastery: intervals.**

## S7 — Segments, the T wave, and the normal template
Same beat, lighter/visual. Teach what each IS + normal appearance (meaning deferred):
- **ST segment** = the flat stretch from the **J point (where the QRS ends and the ST begins)** to the T;
  **normally at/near the baseline** (compared to the TP baseline) — *a small amount of elevation can be
  normal; how much, and when it matters, is a later module* (defuses over-calling at the root). Let the
  learner **drag the ST off baseline once** to *see* "flat = normal" by contrast.
- **T wave** = repolarization; **upright where the QRS is dominantly upright (e.g. lead II); aVR and V1 are
  normal exceptions** (don't teach "T always follows QRS").
- **QT/QTc** = depolarization + repolarization, so it **scales with rate** → one-line concept + footnote
  (like the U-wave); not measured here.
Assemble the **normal template** (upright P in II, narrow QRS, flat ST at baseline, T concordant in II) =
the picture every later abnormality is judged against. **Mastery: segments + template.**
**Bridge → Part 3:** "One lead gives you rate, rhythm, and the intervals. To see *direction*, we need all twelve."

# PART 3 — "From one lead to twelve" (S8–S9)
## S8 — Twelve views of one heart (+ normal R-wave progression + the aVR sinus check)
One beat fans out to 12: "twelve cameras on the same beats, each from a different angle. We read rhythm on
lead II; *which* camera looks at *which* wall is its own later module — but two things are basic reads now."
(1) **R-wave progression:** scrub V1→V6 — **watch the R grow *and* the S shrink**; the **transition (where
R first becomes taller than S) is normally V3–V4.** Teach the normal pattern; abnormal progression deferred.
→ card. (2) **The deferred sinus check from S5:** now that aVR is on screen, confirm **P inverted in aVR**
(SA impulse heading away from aVR) — close the loop. Keep this the short scene; the six frontal-plane leads
are introduced here only as the setup that opens S9. **Mastery: 12-lead layout + R-wave progression.**

## S9 — Axis — the heart's main direction (basics)
Hexaxial circle beside a live 12-lead. **Concept:** axis = the **net direction of ventricular depolarization**
in the frontal plane — one arrow summarizing where the QRS points; **down-and-left in most hearts because LV
muscle mass dominates.** **Read it the simple way:** look at **lead I and aVF** — both QRS up = **normal
axis.** **Signature interaction:** **drag the QRS vector** around the hexaxial circle and watch each
limb-lead's QRS flip positive/negative live. **The normal sector is shaded green on the circle; the vector
turns red when it leaves it** — so the rule, the picture, and the card all agree. **Honest boundary:**
"I up + aVF up = definitely normal. If aVF is *down* but lead I is up, that's **borderline** — we pin it
with lead II in the axis module, where the normal range extends a little further (to about −30°)." The card
shows normal as **the green sector the rule delivers (≈ 0° to +90°), with the −30° extension marked
'refinement, later.'** Describe-don't-diagnose: "normal vs deviated" is the foundational call; causes are
later. **Mastery: axis basics.**
**Bridge → Part 4:** "You can read every piece. Time for the order that turns pieces into a read — then you
do it yourself."

# PART 4 — "The systematic read" (S10–S12)
## S10 — The sweep, modeled, but active (worked examples — *I do, with you*)
Introduce the **standard order** (calibration check first): **Rate → Rhythm → Axis → Intervals →
QRS/morphology → ST-T → Synthesis.** The tutor reads **2 real 12-leads** on the trace **in finding-language
only, no clinical backing**, e.g.: *"Sinus — P before every QRS, same shape, upright II / inverted aVR. Rate
~95, mild tachycardia. Axis: I up, aVF up — normal. PR a touch long ~210 ms. QRS a bit wide. ST flat, T's
upright. So: sinus tachycardia, long-ish PR, wide-ish QRS — all described, nothing diagnosed yet."* **Not
passive:** each example has **≥1 predict-before-reveal step** ("we measured rate two scenes ago — what's the
rate here? …now watch me check"). Each step **highlights on the trace** as it's named. ST-T read only at the
*normal-appearance* level. Examples span a clean normal + one with a describable rate/PR/QRS/axis deviation.

## S11 — Guided practice (*we do*, scaffolding fades)
**2–3 real 12-leads** the learner sweeps step-by-step, with prompts that **visibly decrease across cases**
(full scaffold → half → minimal): "Rate? → Regular? Sinus? → Axis (I + aVF)? → PR/QRS? → ST/T normal-looking?"
Free-text or quick-select per step, **graded on meaning**, with **reason-me-back** correction on the trace.
**Axis gets ≥2 guided reps here** (it's brand-new from S9 and otherwise under-rehearsed). Correct-but-ahead
answers are accepted ("right, formalize later"), never penalized. The tutor assembles the learner's confirmed
findings into a one-line finding read. **Free-text grading spec (built in here, not just a principle):**
per-component meaning-matching against a finding-language synonym map (e.g. "normal axis" ≡ "points normal,
down-left" ≡ "I up aVF up"), **partial credit per sweep component**, and "credit the physiology, supply the
term" on a near-miss.

## S12 — Independent read (*you do*) + payoff
**Two solo cases with a graded release:** the **first keeps the 6-step sweep rail visible** as silent
structure (the order shown as empty fields to fill, but no coaching — an optional one-tap axis hint only);
the **second is a blank-page read.** Tutor **silent unless asked** (Ask is there on demand; learner-led).
The learner enters the full sweep (rate, rhythm, axis, intervals, morphology, ST-T-normal?), submits; the
tutor compares to the record's ground truth, **credits what they got, reasons back anything missed**, and
produces the final finding-line together. **Scoreboard:** sweep-accuracy % + time + personal best (a number
to beat). Encouraging payoff: "You just read a 12-lead start to finish — rate, rhythm, axis, intervals,
morphology — and described exactly what you saw." Forward pointer, exciting not scary: "Next: what the
rhythms are called and look like, what abnormal intervals/axis/ST-T *mean*, and which findings are urgent."
**Mastery: the foundational systematic read.** This sweep + practice loop is the **template every later
module reuses.**

---

## Interaction inventory
scrub/replay · drag-label · click-select · box-count estimate (scored vs real value, with tolerance) ·
scored rapid-classify (quality) · spacing→rate slider · march-out (precision check) · draggable interval
handle (recolors at threshold) · drag-the-ST-off-baseline (see "flat = normal") · R-wave-progression scrub
V1→V6 (R up / S down) · **drag-the-axis-vector on a green-shaded hexaxial circle (limb leads flip live,
vector reddens outside normal)** · caliper (optional precision) · read-the-report-number · bounding-box draw
· **normal-values card (summonable, fills as taught, openable mid-practice)** · **predict-before-reveal
worked examples** · **scaffolded sweep-step prompts + reason-me-back (fading across cases)** · **rail-visible
solo → blank-page solo** · per-component meaning-graded free-text (LLM, draws-on-trace, synonym map, partial
credit) · sweep scoreboard (accuracy/time/personal best) · per-scene + per-part test-out.

## Real-data hooks
Single-lead measure scenes (S1–S7) = PTB-XL **median beats** (true values power accuracy scoring). 12-lead
scenes + practice (S8–S12) = **real 12-lead corpus records**, including curated **describable-deviation**
exemplars (sinus tachycardia; long-PR / 1AVB-labeled; wide-QRS / BBB-labeled; axis-deviation-labeled) —
described in finding-language only, never diagnosed here. Axis read uses the record's computed net-QRS axis
as ground truth; R-wave progression uses the real precordial R/S amplitudes. Quality scene = corpus
signal-quality-flagged records. (No danger/acute exemplars here — deferred, pending the supplementary
acute-dataset ingest.)

## Build approach (next, per the loop)
Build the reusable engines first, then assemble: (1) **wavefront-draws-the-waveform** animation (S1);
(2) **measurement engine** — box-reading + read-the-report core, calipers optional, estimates scored vs real
median-beat values, scoring live from S2 (S2/S4/S6); (3) **12-lead renderer + R-wave-progression scrub**
(S8); (4) **hexaxial axis engine** (S9) — drag-the-vector, live limb-lead polarity, **green normal sector +
red-outside**, ground-truth from the record's net-QRS axis; (5) **sweep-practice engine** (S10–S12) —
predict-before-reveal worked examples, fading scaffolded steps, rail-visible→blank solo, **per-component
meaning-graded free-text via the nano LLM with a finding-language synonym map + partial credit +
reason-me-back**, scoreboard; plus shared **normal-values card** + **ask-anything** primitives. Validate each
engine, then assemble the 13 scenes wiring real median beats + real 12-leads + the nano LLM. Then
persona-test the BUILD across all 10 → iterate → fix → user refines.

## Iteration loop status
(1) persona-test storyboard ✓ → (2) iterate storyboard ✓ (v3→v4→v5→v6→v7; v7 from a deep scene-by-scene
10-persona test) → (3) **build (next)** → (4) persona-test build across all 10 → (5) iterate → (6) fix →
(7) user refines via testing.
