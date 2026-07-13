# Foundations Module — Complete Verbatim Text (v1.6)

> **Reviewer note on conditional/templated lines:** where this doc shows alternatives, the runtime renders exactly ONE branch — it is never displayed with a "|" or both options. These are transcription conveniences, not literal on-screen text.


*Every learner-facing string, transcribed from source. Companion to MODULE_GUIDE.md.*
*Conventions: `**bold**`/`*italic*` = in-app emphasis. `{…}` = a runtime value. Tutor lines in firing order.*

---

## A. Global UI chrome (`index.html`)

- **Browser title:** Foundations — How to read an ECG
- **Brand:** ❤ Foundations · reading an ECG
- **Header button:** 📋 Normal values · **Skip button:** Skip for now ›
- **Nav:** ‹ Back · "Take your time — ask the tutor about any concept →" · Next ›
- **Tutor header:** AI tutor — `grounded · tangents return safely`
- **Tutor input placeholder:** Ask about any concept…  (e.g. "what is the PR segment?") · **Send:** Ask · **Tangent return:** ↩ Return to {scene}; “Back to **{scene}**. Your scene and unfinished interaction are unchanged. Continue with: {active checkpoint}.”
- **Normal-values footer:** Reference values for this Foundations module. Everyday method: estimate from the boxes, then compare with the printed measurements when available. Calipers are for values close to a cutoff.
- **Completion cue:** ✓ Nice — you've got **{thing}**. Continue when you're ready.  (labels: the waves · reading the grid · quality check · rate · rhythm / sinus · intervals · segments + reference · 12-lead + R-wave · the idea of axis direction · the read, modeled · guided read · the foundational read)

---

## B. Scenes S0–S12

### S0 · A gentle start
**Hero:** An ECG is the heart's electrical signal, drawn over time. In Foundations you'll learn the **beginner sweep**, start to finish: find the main waves, measure the basics, and **describe** what the tracing supports — one piece at a time. No prior knowledge needed. Clinical meaning, diagnoses, and urgency come in later modules.
**Tutor:** Hi — I'm your tutor. I'll guide each step, and you can **ask me about any Foundations concept** any time in the box below — I'll help you *find, measure, and name* things, and save clinical meaning for later modules. Take a look at the path above, then hit **Next** to start.

### S1 · One beat, one wave
**Lesson:** Watch the electrical wave sweep the heart and **draw the tracing in real time**. Then you'll name the three parts.
**Tutor (open):** Press **▶ Watch one beat**. I'll narrate in plain words first — then we'll put names to the shapes.
**Tutor (labels):** Now tap **Show P / QRS / T**. Select each name, then tap its wave or use the matching waveform-target button. **P** = the atria electrically activating (small), **QRS** = the ventricles activating (tall), **T** = the ventricles resetting.
**Animation captions:**
- (initial) Press ▶ to watch the wave draw the trace — or use the slider to step through it yourself.
- (resting) Resting — between beats the tracing sits on the baseline.
- (P) The atria electrically activate — a small, gentle bump, the P wave.
- (PR/AV) A brief hold at the AV node — the line rests flat for a moment while the signal is delayed.
- (QRS) The ventricles activate quickly — a tall, sharp spike, the QRS.
- (ST) A short flat stretch — the ventricles are fully active.
- (T) The ventricles reset (repolarize) — a rounded bump, the T wave.
- (rest) And back to rest. That whole shape was one heartbeat.
**Label task success:** That's the whole vocabulary of a heartbeat: **P** = atrial activation, **QRS** = ventricular activation, **T** = ventricular reset. Everything else we measure hangs off these three.

### S2 · The grid is your ruler
**Lesson:** Now that you can spot P, QRS and T, let's measure the distance between them. The pink grid is calibrated: **across** = time, **up/down** = voltage. A **small box is 40 ms wide and 0.1 mV tall**; **5 small = 1 big box = 200 ms**. The little step on the left is the **calibration pulse** — it tells you the tracing is drawn at standard size, so glance at it every time.
**Tutor:** Let's prove the ruler works. Move the two markers exactly **one big box apart** — that's 5 small boxes — then **Check my count**. Drag or tap, use the marker buttons, or focus a handle and press the arrow keys. Each small box is 40 ms, so you're aiming for 200 ms.
- success (tutor): That's the measurement trick: once you find a waveform's start and end, the grid turns distance into time.
- success (engine): Nailed it — you read **{ms} ms** for one big box (true value 200 ms). Box-counting works.
- **Concept-check (gates):** "Quick check: one big box is 5 small boxes — how many ms is that?" → **200 ms** ("✓ Right — 5 × 40 ms = 200 ms.") / 40 ms / 1 second
**Aside:** **Calipers?** There's a precision tool for borderline values, but most of the time you estimate from the boxes and compare with the printed measurements. Use calipers when a value is close to a cutoff.

### S3 · Is it readable?
**Lesson:** Before measuring, ask: **readable for what?** A strip can be clear enough for rate but too noisy for the P waves or ST/T — a good reader doesn't force a measurement the tracing can't support. Tag each strip.
**Buttons:** Readable · Too noisy
**Tutor:** Four strips. Two are clean enough for detailed measuring; two are too noisy for the P waves / ST-T. Tag each one.
- per-strip: ✓ · ✗ this one's clean — re-tag it / ✗ too noisy — re-tag it
- all correct (must get all right): All {n} right. When noise hides the waves or the baseline, don't force a measurement — you may still estimate rate if the QRS complexes are clear, but avoid PR / ST-T calls.

### S4 · Regular? then rate
**Lesson:** **First glance: are the R's evenly spaced?** … If **regular** → **300 ÷ big boxes** *(why 300? one minute is 300 big boxes wide…)*. If **irregular** → count beats in 6 seconds × 10.
**Concept-check 1 (gates):** "First, the method. The R waves here are evenly spaced (regular) — which method?" → **Regular → 300 ÷ big boxes** ("✓ Right…") / Irregular → 6-second count ("That's for an irregular rhythm; when it's regular, 300 ÷ big boxes is quicker.")
**Concept-check 2 (gates):** "And if the R waves were unevenly spaced (irregular)?" → **Count beats in 6 seconds × 10** ("✓ Right — the 300-rule only works when the rhythm is regular.") / Still use 300 ÷ big boxes ("The 300-rule assumes even spacing…")
**Tutor:** Drag the spacing slider and feel it: closer R's = faster. Then estimate the rate yourself and compare with the printed value on the quiz strip. Within ~10–12 bpm is a good beginner estimate.
**Rate lab success:** Yes — about **{truth} bpm**. Your estimate is close — the printed measurement is {truth} bpm on this real strip. Within ~10–12 bpm is a great read.

### S5 · Sinus pattern? — *follow the P waves*
**Lesson:** **Sinus pattern** means the beat *appears* to start in the SA node — we infer it from the P waves. Checklist (all on lead II): a **P before every QRS**, a QRS after every P, the **P upright in II**, the **same P shape every beat**, a **constant PR**. Regularity helps, but sinus is mainly this P–QRS checklist. *Rate is NOT part of it* — a slow sinus and a fast sinus are both sinus.
**Buttons:** Sinus pattern · Not sinus pattern
**Tutor:** Three lead-II teaching strips. Use the checklist — remember, rate doesn't decide sinus.
**Feedback:** (1) Upright P before every QRS, same shape, steady PR — sinus. (2) Slow, yes — but every P still conducts… This is a **sinus pattern with a slow rate** (later called sinus bradycardia). Slow ≠ not-sinus. (3) …it's **inverted in lead II** and its shape shifts beat to beat… so it isn't sinus.
**Tutor (done):** Nicely done. There's one extra 12-lead clue: in **aVR**, the normal P usually points *down*. We'll see why when the 12 leads appear.

### S6 · Intervals: PR & QRS
**Lesson:** Now that you can find P and QRS, you can measure from the **start of P to the start of QRS** (the PR), and across the QRS itself. Two intervals you try to measure on every *readable* ECG: span each one and read the boxes, then compare with the printed value.
**Headers:** 1 · PR interval *(start of P → start of QRS)* · 2 · QRS duration *(start of the first deflection → return to baseline)*
**Caliper readout:** {ms} ms ({n} small boxes) · "normal 120–200 ms · current: {in range ✓ / long / short}" or "normal < 120 ms · current: {in range ✓ / wide}" · "printed value on report: {trueMs} ms"
**Tutor:** Move the two handles to span the **PR**. Drag or tap, use the marker buttons, or focus a handle and press the arrow keys… *(after PR)* PR done. Now the **QRS** on a real beat that runs wide… *(done)* You can now measure both — and describe "long PR" / "wide QRS" without needing to know yet what they mean.

### S7 · Segments & the normal reference
**Lesson:** The last pieces: the **ST segment** (from the end of the QRS — the **J point** — toward the T) and the **T wave**. Then we'll assemble a simple picture of a **normal-appearing** beat.
**Baseline first:** “Before moving ST, identify its reference. Tap the flat **TP baseline** between the end of T and the next P, or use the labeled target buttons.” · correct: “Correct — the TP stretch is the baseline used to judge ST level.”
**Tutor (ST):** Now move the ST segment away from the baseline once, then settle it back. Drag, use the ST-level slider, or use Lower ST / Raise ST / Set at baseline.
**ST comparison (engine):** “Move the **ST segment** up or down by dragging it, using the level slider, or choosing the buttons. It’s judged against the baseline…” · (off) “…off the baseline. A small amount can be normal; *how much, and what it means, is a later module.* Settle it back near the baseline.”
**Normal-reference header:** A simple normal reference — later modules compare findings against this
**List:** P small & upright (in II) · PR 120–200 ms · QRS narrow (<120 ms) · **ST near the baseline (no obvious lift or drop)** · **T usually follows the main QRS direction** (in II, both point up) *(aVR & V1 are common exceptions)*
**Tutor:** There it is — the normal reference. The **QT** runs from the start of the QRS to the end of the T — ventricular activation through recovery; because it changes with heart rate, we often use the rate-corrected QTc. When QT matters is a later module.
**Concept-check (gates):** "Quick check: the ST segment is judged against which line?" → **The baseline** ("✓ Right — ST is read relative to the baseline (the flat TP stretch between beats).") / The T wave / The QRS

### S8 · One lead → twelve
**Lesson:** Twelve leads = **twelve cameras** on the same beats — different views recorded at the *same time*, not twelve separate events. One quick orientation now: how the **R wave grows** across V1→V6 (and a glance at aVR).
**Tutor:** Step through V1→V6 with the slider, lead buttons, or Previous/Next — watch the R grow and the S shrink (transition often around V3–V4). Then glance at the full 12-lead below and notice aVR pointing the opposite way.
**R-wave scrub:** (V1) V1 starts as a small r with a deep S… (transition) **Transition!** At {lead} the R finally becomes taller than the S — the transition is often around V3–V4. (Real case {id}.)
**Aside:** **Also — the aVR glance.** For the sinus check, the **P wave** in aVR usually points **down**. The QRS and T often point down too, because aVR looks from the opposite shoulder.
**Concept-check (gates):** "On this tracing, which lead was the first where R became taller than S (the transition)?" → {transition lead} ("✓ Right — that's where R first became taller than S (the transition).") / two neighbor leads
**Rhythm strip label (in every real 12-lead):** II — rhythm strip (use for rate & rhythm)

### S9 · Axis — the heart's direction
**Lesson:** With the 12 leads as 12 views, the **axis** is the overall direction they reveal… Quick read off the limb leads: **I up + aVF up = normal**; I up but aVF down = **leftward** (call it left axis only when it's clearly past the normal zone); I down + aVF up = **right axis**.
**Zone tracker:** **Explore both:** ○ normal (green) · ○ left / right axis (amber–red)
**Tutor (open):** Rotate the arrowhead by dragging, using the QRS-axis slider or arrow keys, or choosing a zone button. Watch each limb lead flip up/down… Reach the **green (normal)** zone and then any **off-normal** spot.
**Axis readout:** "Lead I is {up/down}, aVF is {up/down}. " → (normal) Both up → **normal axis**. (border) I up but aVF down → **borderline left**… (dev) This is **a left axis** / **a right axis** / **an extreme axis** — we just name it for now; what causes it is a later module.
**Tutor (done):** …**I up + aVF up = normal**; I up but aVF down = **leftward** (call it left axis only when it's clearly past the normal zone); I down + aVF up = **right axis**. Borderline leftward cases get pinned with lead II later…
**Concept-check (gates):** "Name it: if lead I is up but aVF is clearly down, the axis is…" → **Left axis** ("✓ Right — I up, aVF down points up-and-left (left axis).") / Right axis / Normal

### S10 · The sweep, modeled
**Lesson:** Time to put it together. The order, every time: **Rate → Rhythm → Axis → PR → QRS width → ST-T → Synthesis.** (We learned axis alongside the 12-lead, but in the sweep it comes earlier.) Watch two real 12-leads read out loud — in **finding-language only**.
**Tutor (each case):** Here's case {i} (real ECG {id}). Step through the sweep with the buttons **right under the ECG** — each reveal shows the finding and its evidence (predict first where it asks).
**Predict prompts:** 🔮 Predict first: what's the rate (bpm)? · 🔮 Predict first: is the QRS normal or wide?
**Narration steps (Rate → Rhythm → Axis → PR → QRS width → ST-T → Synthesis):**
- **Rate:** ~{bpm} bpm — {fast rate (>100; tachycardia) / slow rate (<60; bradycardia) / normal}.
- **Rhythm** (renders ONE of): (real lead-II) "a P before every QRS, upright in II and consistent in shape — a **sinus pattern**. (aVR points the opposite way, which fits.)" · (tiled median strip) "on this teaching rhythm strip the visible P–QRS pattern is **sinus-appearing** — a P before each QRS, upright in II. (aVR points the opposite way, which fits.)" · (non-sinus) "…I can't confirm all of it, so I'd say **'not clearly sinus'** and leave the name for a later module."
- **Axis:** {normal axis / left axis / right axis} (~{deg}°), read off lead I & aVF.
- **PR:** {pr} ms ({normal/long}) — start of P to start of QRS.
- **QRS width:** {qrs} ms ({narrow/normal / wide}). We name it; meaning is a later module.
- **ST-T** (renders ONE of): "ST is near baseline; T is normal-appearing for this teaching case. (Reading abnormal ST/T is a later module.)" · "I wouldn't make a confident ST/T call from this tracing — I'd mark it **not assessable** here."
- **Synthesis:** e.g. "**sinus pattern, normal rate ~64 bpm, normal axis, PR 134 ms, QRS 74 ms, ST/T normal-appearing**" — all *described*, nothing diagnosed yet. *(rate phrase = fast/slow/normal rate ~{bpm} bpm; ST/T clause renders one of "ST/T normal-appearing" or "ST/T not assessable here".)*

### S11 · Guided practice
**Lesson:** Now you run the sweep, step by step. I'll prompt you — and I'll ease off as you go.
**Tutor:** Case 1. I'll prompt each step. Answer in your own words — a number or a word is fine (e.g. "about 75, normal rate" or "PR 260, long"). *(then)* Case 2 — I'll step back a bit; you carry more of it.
**Case 1 prompts:** Rate? Count big boxes… · **Rhythm?** … Sinus pattern, not sinus pattern, or not clear / not assessable? · **Axis?** Check lead I and aVF: normal, leftward / left axis, or right axis? · **PR** normal or long? · **QRS width** narrow or wide? · **ST/T:** is the ST near the baseline and the T normal-appearing — or not assessable?
**Case 2 prompts:** Your turn with less help. **Rate?** · And the **axis**? Check lead I and aVF — normal, left, or right? Look carefully at aVF here. · In one line, give the **rhythm + intervals + ST/T**. Try: "sinus pattern, PR …, QRS …, ST/T …".
**Feedback:** pass → ✓ {grader message} · retry → "Let me reason it back on the trace: {grader message} Take one more look and try again." · move on → "{grader message} We'll move on — keep that rule in mind." *(critical findings — wide QRS / long PR / left/right axis — force a retry even at score ≥0.5.)*
**Tutor (done):** You ran the whole sweep — twice, with me fading out. Last step: do one entirely on your own.

### S12 · Your read
**Lesson:** Two on your own. First with the step-rail as a checklist (no coaching), then a blank read. **"Not assessable"** is a good answer when the tracing doesn't support a confident call. I'm here only if you ask.
**Case 1:** fill Rate · Rhythm · Axis · PR · QRS · ST / T → "**{got}/{total}** components".
**Axis hint:** Axis hint: glance at lead I and aVF — both up = normal; I up but aVF down means leftward (call left axis when clearly past normal); I down + aVF up = right axis.
**Case 2 header:** Case 2 — blank read, one line covering rhythm, rate, axis, intervals, ST/T (order doesn't matter — just include each part).
**Tutor:** Now a blank one — no fields, no rail prompts. Describe everything you see in one line.
- **pass:** ✓ {grader message} You caught the key findings and covered the sweep.
- **failed end (after 2 tries)** — renders ONE of: "{grader message} The key thing to catch here was {missed}. Re-look next time." — or (if deviations were caught but coverage was thin) — "{grader message} Try to cover the whole sweep next time: rate, rhythm, axis, PR, QRS, ST/T."
- **retry (before 2 tries):** {grader message} One more look — you haven't called: **{missed}** (or, if coverage is thin, "try to cover the whole sweep"). Keep the whole sweep in your answer (rate, rhythm, axis, PR, QRS, ST/T), then submit again.
**Payoff:** Sweep accuracy **{acc}%** *· {secs}s* — **You completed your first beginner 12-lead sweep.** You checked rate, rhythm pattern, axis, PR, QRS width, and ST/T appearance — and **described exactly what the tracing supported.** … **Coming next:** what the rhythms are called … what abnormal intervals / axis / ST-T *mean* … which findings are urgent.
**Tutor (final):** That's Foundations done. You went from "what is this?" to a full descriptive sweep on your own. That's a real milestone — see you in the next module.

---

## C. AI tutor — guard, deflections & local KB (`ui.js`)

**Guard (`isClinical`)** defers a question if it matches **CLINICAL** (cause/danger/diagnosis/treatment/urgency), **DIAGNOSIS** (`av block|heart block|first-degree|lbbb|rbbb|bundle branch|nstemi|stemi|mi|infarct|ischem|lvh|rvh|hypertrophy|wpw|pre-excit|pericarditis|afib|atrial flutter|flutter|long qt|vt|vf|tachyarr|brugada|wellens`), **PATIENT** (`my ecg/ekg|i have/feel|patient|chest pain|shortness of breath|palpitations|syncope|faint|dizzy|emergency room|ambulance|should i worry…`), **INTERP** ("what's wrong/abnormal" + an ECG referent, but NOT "…with my answer/read"), or **MEANING ∧ FINDING**. Foundational "what is / what does X represent" — and "how long should the QT be?" — pass through to the LLM/KB.

**Deflections:**
- **Patient/safety:** I can't help with a real ECG, symptoms, or anyone's care — for that, use a qualified clinical workflow. In this teaching module I can help you practice the **descriptive steps** on the teaching tracing. Want to name or measure what's on screen?
- **Interpretation ("what's wrong with this ECG?"):** I won't interpret the tracing for you — that's the skill you're building. Walk the sweep and **describe** what you see (rate, rhythm, axis, PR, QRS, ST/T), and I'll help you name and measure each part.
- **Danger:** I can't judge urgency or real-patient risk — Foundations is descriptive practice on teaching tracings only, and whether a finding is serious comes in a later module. For now, can you name or measure what's on the trace?
- **Diagnosis:** That's a named diagnosis — its definition, causes, and ECG criteria come in a later module. In Foundations we just **describe** the findings (e.g. "wide QRS", "long PR", "not clearly sinus"). Want to name or measure what's on the trace?
- **Standard clinical:** Good question — that's the next layer. In Foundations we stop at the **finding**: how to spot it, measure it, and name it… What it *means* clinically, what causes it, and whether it's serious all come in a later module. Want to name or measure what's on the trace first?

**Local KB (offline fallback):**
- **P wave:** The **P wave** is the small wave before the QRS — it's the atria (the top chambers) **electrically activating**. It's small because the atria have much less muscle than the ventricles.
- **QRS:** The **QRS** is the tall, sharp spike — the ventricles … **electrically activating**, quickly. It's tall because the ventricular muscle is thick.
- **T wave:** …the ventricles electrically *resetting* (repolarizing) so they can fire again.
- **PR:** Two things share the name: the **PR segment** is the flat part after the P wave …; the **PR interval** is the whole stretch from the *start of P to the start of QRS* — that's the one with the normal value of **120–200 ms**.
- **Boxes:** Each **small box is 40 ms wide and 0.1 mV tall**; 5 small = 1 big box = 200 ms. Once you find a waveform's start and end, the grid turns distance into time.
- **Rate:** First check the rhythm is regular. If so: **300 ÷ the number of big boxes between two R's**. If irregular, count beats in 6 seconds × 10. Normal 60–100.
- **Sinus:** **Sinus** means the beat appears to start in the SA node — we *infer* it from the P waves…
- **Axis:** Quick read off the limb leads: **I up + aVF up = normal**; I up but aVF down = leftward (toward left axis); I down + aVF up = right axis. Borderline cases get refined later.
- **aVR:** In **aVR** a normal P (and usually the QRS and T) points *down*…
- **ST:** …from the end of the QRS (the **J point**) to the T. Normally it sits **near the baseline** — no obvious lift or drop.
- **QT/QTc:** The **QT** covers ventricular electrical activation through recovery (QRS start → T end) — so it stretches when the heart is slow… (rate-correct as QTc).
- **R-wave progression:** …transition (R first taller than S) is **often around V3–V4**.
- **Why so tall:** …the thick ventricles activate quickly, so it's big. Height = voltage (10 mm = 1 mV).
- **Inverted leads:** Some leads are normally "down": the P/QRS/T are **usually** inverted in **aVR**, and the T can normally be flat or slightly inverted in **V1**.
- **Baseline:** …the **baseline** (the TP segment) — your reference line.
- **Fallback:** I can help with anything we've covered so far — the waves (P/QRS/T), the grid and boxes, rate, rhythm/sinus, intervals, axis, or R-wave progression…

---

## D. Grader feedback (`ui.js → grade`)

- (all correct) Spot on — you described {got}. · (partial) Good — you got **{got}**. Now re-check the trace for: **{missing}**. · (none) Let's reason it back on the trace — look for **{missing}** …
- (rule appended on any miss, e.g.) "QRS is wide at ≥120 ms (≥3 small boxes) — measure first deflection to the final return to baseline." · "PR is long over 200 ms (>5 small boxes)…" · "**Left axis in these teaching cases: lead I is up and aVF is clearly down. Borderline leftward cases are refined later.**" · "Right axis: lead I down and aVF up." · "Normal quick check: lead I and aVF both mostly up." · "Fast rate (tachycardia) is over 100 bpm." · "Sinus pattern: an upright P (in II) before every QRS…" · "ST is judged against the baseline — near-baseline is normal-appearing." …
- (conditional ahead-credit) "You named a possible diagnosis — I credited only the descriptive part it implies (**{finding}**); the label and causes come later." (e.g. LBBB → wide QRS, first-degree → long PR)
- (ahead, no implied finding) "(You named a possible diagnosis — in Foundations we just describe the finding; the label comes later.)"
- (uncertainty acknowledged) "Good instinct to flag uncertainty — but on this teaching tracing it's readable. …"
- **Box-unit + comparator parsing:** "3 small boxes" → 120 ms, "5.5 boxes" → 220 ms, "one big box" → 200 ms; comparators shift the boundary so "QRS under 3 boxes" → narrow, "QRS over 3 boxes" → wide, "PR over 200 / over 5 boxes" → long, "PR less than 200" → normal, "rate over 100" → fast, "rate under 60" → slow.
- **Concept labels:** sinus rhythm · fast rate (tachycardia) · slow rate (bradycardia) · normal rate · normal/long PR · narrow/wide QRS · normal/left/right axis · **ST near baseline** · **T normal-appearing**

---

## E. Normal-values card rows (`ui.js`)

- **Grid:** 1 small box = 40 ms wide / 0.1 mV tall · 5 small = 1 big = 200 ms
- **Rate:** 60–100 normal · <60 slow · >100 fast (300 ÷ big boxes, if regular)
- **PR interval:** start of P → start of QRS · 120–200 ms (3–5 small boxes)
- **QRS duration:** <120 ms = narrow · ≥120 ms = wide
- **ST segment:** near the baseline; an obvious lift or drop is noted (for later)
- **T wave:** usually follows the main QRS direction (aVR & V1 are common exceptions)
- **QT / QTc:** start of QRS → end of T; scales with rate (rate-corrected = QTc)
- **R-wave progression:** R grows / S shrinks V1→V6; transition (R>S) often ~ V3–V4
- **Axis:** I & aVF both up = normal · clear left/right deviations named in the axis step

---

## F. Per-part "test out" (`app.js`)

- **Part 1:** A small box is how much time? → **40 ms** / 200 ms / 1 second
- **Part 2:** A slow rate, with an upright same-shaped P before every QRS and a steady PR. Sinus pattern? → **Yes — sinus pattern (just a slow rate)** / No — too slow to be sinus
- **Part 3:** Lead I points up but aVF points down. The axis is: → **Leftward — left axis if clearly past normal** / Normal / Right axis
- **Part 4:** First step of the sweep? → **Rate** / ST-T / Axis
- (correct) Correct — Part {n} unlocked (tested out).

---

## G. Backend AI system prompts (`backend/app/llm.py`) — verbatim

### G.1 `FOUNDATIONS_SYSTEM_PROMPT` (used by `/tutor/foundations`)
```
You are a warm, plain-spoken tutor for someone learning to READ AN ECG for the very first time
(the "Foundations" module). You teach the fundamentals only: the waves (P, QRS, T), the graph-paper grid
and boxes, heart rate, rhythm/sinus, the PR/QRS/QT intervals, the ST segment, axis (basics), and R-wave
progression — plus the cardiac physiology behind them.

HARD RULES:
- You do NOT have or need an ECG image. Answer the learner's concept question directly from general
  ECG knowledge. NEVER ask the learner to upload, attach, or provide an ECG / image / tracing.
- Scope is DESCRIBE, not diagnose. If they ask what a finding MEANS clinically, what CAUSES it, whether
  it is DANGEROUS/serious, or any diagnosis, treatment, or urgency — gently defer: tell them that comes in
  a later module and steer them back to naming or measuring what's on the trace. Give NO clinical
  interpretation, differentials, or management.
- Beginner level: 1-3 short sentences, plain words, define any jargon. Tie to physiology when it builds
  intuition (e.g., the QRS is tall because the ventricles are thick-walled).
- Educational use only; not medical advice.

Reply with ONE JSON object only, no markdown fences: {"tutorMessage": string}
```

### G.2 `SYSTEM_PROMPT` (platform case-grounded tutor, `/tutor/chat`; NOT Foundations — for completeness)
```
You are an ECG tutor for medical students entering clerkship. Reply with ONE JSON object only … Every field is required …
You are NOT the source of truth. Use ONLY the supplied GROUNDED CONTEXT … NEVER invent diagnoses, measurements,
intervals, fiducials, or ROIs. If asked about a finding not in the packet, say so plainly and add an
uncertaintyWarning. … Teach reasoning, not labels. Educational use only; no clinical advice.
```

---

*End of verbatim text (v1.4).*
