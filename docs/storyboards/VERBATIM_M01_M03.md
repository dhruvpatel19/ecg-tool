# TRACE production storyboard — Modules 01–03 (verbatim specification)

**Status:** production-authoring source of truth  
**Scope:** Module 01, *Foundations: from signal to a complete descriptive read*; Module 02, *Leads, vectors, axis, and territories*; Module 03, *Rhythm logic: sinus, irregularity, pauses, and ectopy*  
**Audience:** medical students beginning ECG interpretation, including anxious novices, learners with prior informal exposure, keyboard/screen-reader users, and advanced learners using placement checks  
**Clinical boundary:** formative education. These three modules teach observation, measurement, mechanism, description, and evidence-bounded clinical connections. They do not supply patient-specific diagnosis, urgency, treatment, or medication advice.

This document replaces abbreviated scene cards for Modules 01–03. Every quoted string is approved learner-facing copy. Text in square brackets is a runtime token, not prose to improvise. Examples: `[learner name]`, `[lead]`, `[value]`, `[scene title]`, `[return waypoint]`. The tutor may paraphrase only in a learner-requested tangent; instructions, checkpoints, feedback, transitions, safety language, and return controls are deterministic.

---

## 0. Production contract shared by all three modules

### 0.1 What counts as a scene

A scene is a resumable learning episode with one primary objective. It has these states:

1. `not_started`: no learning claim.
2. `viewed`: the learner reached the scene; no performance claim.
3. `attempted`: an assessable action was submitted.
4. `needs_review`: the learner exhausted the supported retry or selected “Review later.”
5. `complete`: the scene action and its equivalent transfer met the scene rubric.
6. `skipped`: the learner deliberately bypassed the scene; never counted as complete or mastered.
7. `mastered`: assigned only by later mixed evidence, never by the tutorial scene alone.

Persistent progress copy, exactly:

- Scene status: `Not started`, `Viewed`, `Attempted`, `Needs review`, `Complete`, `Skipped`, `Mastered later`.
- Progress disclosure: `Scene completion records this learning action. Mastery requires later mixed practice.`
- Skip dialog heading: `Leave this scene for later?`
- Skip dialog body: `You can continue, but this scene will stay marked Skipped and will return in your review plan.`
- Skip controls: `Keep learning here` and `Skip and mark for review`.
- Resume toast: `Welcome back. Your tracing, notes, and place in the lesson are restored.`

### 0.2 Shell, layout, and responsive behavior

Every scene uses the same semantic order in the DOM: module header; context strip; scene title and objective; primary learning surface; instruction/feedback region; evidence panel; tutor; navigation. Visual rearrangement must not change screen-reader order.

**Desktop, at least 1280 px:** 12-column grid. A 220 px scene rail uses columns 1–2; the primary surface uses columns 3–9; the 300 px tutor uses columns 10–12. The module header is 72 px high and sticky. The context strip is directly below it and is not sticky. The ECG surface is at least 720 × 360 px. Only the page scrolls; no nested vertical scroll region is permitted.

**Laptop, 900–1279 px:** 10-column grid. The rail collapses to a `Scenes` button and a horizontal breadcrumb. The primary surface uses columns 1–7; the tutor uses columns 8–10 and may collapse to a 48 px tab. ECG width is at least 600 px or it receives an explicit horizontal pan region whose label is `Scrollable ECG; use Shift plus mouse wheel, or the horizontal scrollbar, to inspect all leads.`

**Mobile, 360–899 px:** one column. Order is context strip, scene copy, interaction, feedback, then tutor. ECG lead tiles stack as limb leads followed by precordial leads; a `Standard 3 by 4 view` toggle opens a pannable, non-scored reference. Tap targets are at least 44 × 44 px. Drag interactions have tap-select alternatives and never require two-finger precision. Sticky bottom bar contains `Previous`, scene status, and `Next`.

**Focus and announcements:** when a state changes, focus moves only after learner activation. Correct/incorrect feedback uses `role="status"`; safety and data-conflict messages use `role="alert"`. The first invalid control receives focus after a submit. Completing a scene announces: `Scene complete. [next scene title] is available.`

**Persistent controls and exact accessible names:**

| Visible control | Accessible name / helper copy |
|---|---|
| `Scenes` | `Open the scene map for [module title]` |
| `Ask` | `Ask the tutor; the lesson will pause at [return waypoint]` |
| `Notes` | `Open personal notes for this module` |
| `Normal values` | `Open the normal-values reference card` |
| `ECG tools` | `Open pointer, zoom, caliper, march, and box tools` |
| `Replay` | `Replay this animation from the beginning` |
| `Reduce motion` | `Show the same explanation without animation` |
| `Previous` | `Go to the previous scene; current work is saved` |
| `Next` | `Go to the next scene` |
| `Review later` | `Mark this scene Needs review and continue` |

### 0.3 Visual language and animation rules

- ECG paper uses a warm off-white ground, 1 mm muted rose lines, 5 mm slightly darker lines, and a charcoal trace. Grid contrast meets 3:1 without competing with the trace.
- Instructional color is never the sole carrier of meaning. Activation is cobalt plus an arrow; recovery is violet plus a dotted halo; correct is teal plus a check; retry is amber plus a circular arrow; unsupported is slate plus an em dash.
- Waveform overlays sit above the grid but below learner marks. Selected evidence receives an outline and named label, not a translucent block that hides morphology.
- Default animation is 600–900 ms per causal step. Nothing instructional auto-advances. `prefers-reduced-motion` replaces movement with numbered frames and a `Next frame` control.
- Tutor text never types itself. It appears immediately so reading pace is learner-controlled.
- “Real ECG” is shown only when provenance and source geometry pass preflight. Synthetic or transformed content is labeled `Teaching simulation` adjacent to the tracing.

### 0.4 Tutor tangent and exact-return protocol

When `Ask` is opened, the application stores module, scene, micro-step, selected lead, selected point/box, zoom window, active tool, learner answer draft, feedback state, elapsed active time, and open reference cards. The lesson freezes; timers pause.

Tutor opening, exactly:

> `You paused at [return waypoint]. Ask about this idea, the visible tracing, or a connection you are curious about. I will separate what this tracing shows from general ECG teaching.`

Every answer has three labeled blocks:

- `On this tracing` — only grounded packet facts or `This tracing does not establish that.`
- `General connection` — bounded conceptual answer.
- `Where we paused` — one sentence naming the original action.

Exact return control: `Return to [return waypoint]`. Accessible name: `Return to [return waypoint] with my tracing and answer restored`. Return toast: `You are back at [return waypoint]. Your view and unfinished work are unchanged.`

Real-patient branch, exact:

> `I can teach the ECG concept, but I cannot assess a real patient from this lesson. If this is about a current patient, use your clinical team and local escalation process now. For the learning question: [bounded general explanation].`

Unsupported case-claim branch, exact:

> `This tracing does not provide enough evidence for that case-specific claim. We can inspect [available evidence], or I can explain the concept generally.`

Tutor responses never complete a scored action, fill an answer, move a caliper, or reveal a target before commitment. After a first incorrect attempt, the tutor may offer a principle-level hint. After a second incorrect attempt, it may demonstrate on a different tracing; the learner still completes an equivalent target.

### 0.5 Case and scoring invariants

Every case packet must declare:

`case_id`, `source_dataset`, `source_record_id`, `license`, `synthetic_or_real`, `sampling_hz`, `paper_speed_mm_s`, `gain_mm_mV`, `lead_names`, `lead_layout`, `duration_s`, `quality_by_lead`, `transformations`, `clinician_review_status`, `permitted_claims`, `forbidden_claims`, `ground_truth_values`, `target_geometry`, and `difficulty_tags`.

Preflight fails closed when required leads, calibration, target geometry, provenance, morphology, or clinician review do not match the scene. Failure copy:

> `This learning case did not pass its content check. Your progress is safe; choose another case or try again later.`

No synthetic pacing spike or sub-sample precision may be inferred from a 100 Hz derivative. At 100 Hz, numeric point readouts show two decimal places in seconds and the note `Source resolution: approximately 10 ms.` Findings that require unavailable temporal or morphology fidelity remain demonstration-only or locked.

Scoring stores separate axes: `observation`, `measurement`, `mechanism`, `discrimination`, `evidence_link`, `communication`, and `confidence_calibration`. Time, number of hints, and number of actions are descriptive analytics, never accuracy points. High confidence on a wrong answer adds a delayed equivalent retry; it does not subtract a punitive score.

### 0.6 Common feedback and retry copy

| State | Exact copy |
|---|---|
| Correct, first attempt | `Yes. [specific evidence sentence]` |
| Correct after hint | `Yes. The hint helped you find [evidence]. You will see an equivalent example before this scene completes.` |
| Partially correct | `You have [correct element]. Add [missing observable element] before naming the pattern.` |
| Incorrect, first attempt | `Not yet. Keep your label open and inspect [specific observable].` |
| Incorrect, second attempt | `Let’s rebuild the rule on a different example. Then you will retry on an equivalent tracing.` |
| Correct-but-ahead | `That connection is reasonable. For this scene, record the finding we can support now: [finding-language]. We will test the diagnosis in [later module/scene].` |
| Unsupported specificity | `The evidence supports [broader description], but not [narrow claim]. Choose the broader description or identify additional evidence you would need.` |
| Low-confidence correct | `Your evidence is correct. Before changing confidence, say which visible feature made the answer defensible.` |
| Exhausted supported retry | `This objective is not complete yet. Choose Review later, or work through one more coached example.` |

Equivalent retry means same objective and difficulty band, different source record, non-overlapping memorization cue, and the same required action. The retry never reuses the identical waveform with labels removed.

---

# Module 01 — Foundations: from signal to a complete descriptive read

## M01.0 Module contract

**Module card title:** `1 · Signal, paper, and your first complete read`  
**Card description:** `Learn what the trace represents, measure its basic parts, and complete a descriptive 12-lead sweep without diagnosing disease.`  
**Duration label:** `About 25 minutes for the core path · longer with tutor tangents or retries · four resumable chapters`  
**Prerequisite label:** `No prerequisite`  
**Outcome shown before launch:** `By the end, you can check calibration and quality, estimate rate, identify a sinus pattern, describe axis and intervals, review QRS and ST–T appearance, and communicate one evidence-based summary.`

Entry controls: `Start from the beginning`, `Resume at [scene title]`, and `Show me the placement check`. The placement check never completes scenes. Passing it changes support density and marks earlier objectives `review suggested` or `review optional`; the learner can open any scene.

Chapter headings:

1. `What am I looking at?`
2. `Measure one beat`
3. `One beat, twelve views`
4. `The systematic read`

The 13-scene numbering below intentionally reconciles the existing Foundations implementation: S0–S12 remain stable deep-link identifiers.

## M01.S0 — A gentle start

**Purpose and timing:** orientation, affective safety, scope, and route selection; 2–3 minutes; no scored evidence.

**Case contract:** teaching simulation; lead II; 8 seconds; 25 mm/s; 10 mm/mV; clean signal; normal-appearing sinus pattern; no clinical claims; geometry includes one P, one QRS, and one T target per complete beat.

**Layout:** Desktop/laptop: full-width 180 px tracing above a centered 680 px copy column; four chapter cards beneath. Mobile: tracing 120 px high, copy, then horizontally stacked chapter cards. Reduced motion: a static beat and three numbered snapshots replace scrolling.

**Screen/state script:**

| State | Exact learner-facing copy and controls | Visual / interaction |
|---|---|---|
| Entry | Heading: `An ECG is the heart’s electrical signal, drawn over time.` Body: `In Foundations, you will learn a beginner sweep from start to finish: find the main waves, measure the basics, and describe what the tracing supports. No prior knowledge is needed.` Scope note: `We will describe before we diagnose. Clinical meaning, urgency, and management belong to later modules and supervised clinical practice.` | A heart icon contracts once; a cobalt electrical path sweeps; the lead-II trace draws in synchrony. Pause after one beat. |
| Tutor welcome | `Hi. I’m your tutor. I can slow down, explain a why, or follow a useful tangent. When we return, your exact place and tracing will still be here.` | Tutor opens but does not steal focus. |
| Path | Heading: `Your path` Cards: `1 · What am I looking at? — signal, waves, paper, quality`; `2 · Measure one beat — regularity, rate, sinus, intervals, recovery`; `3 · One beat, twelve views — layout, progression, axis`; `4 · The systematic read — watch, practise, transfer`. Footer: `About 25 minutes for the core path; tutor tangents and retries may take longer. Stop after any scene; your work saves automatically.` | Cards are informational, not progress claims. |
| Choice | Prompt: `How would you like to begin?` Controls: `I am new to ECGs`; `I have seen a few`; `Show me the placement check`. Helper: `This changes the amount of guidance, not the learning standard.` | Selection sets support preference. `Continue to one electrical wave` advances. |
| Transition | `First, connect one heartbeat to the shapes on the page.` | Button: `Continue to one electrical wave`. |

**Accessibility labels:** animation `Electrical activation moving through a simplified heart while one lead-II heartbeat is drawn`; path group `Four resumable chapters in Foundations`; support choice group `Choose the amount of initial guidance`.

**Tangent example:** learner asks, “Does electricity mean the heart is being shocked?” Tutor: `On this tracing — This is a recording, not an electrical treatment. General connection — Skin electrodes sense tiny voltage differences produced as heart muscle cells activate and recover; the ECG machine draws those differences over time. Where we paused — You were choosing how much guidance you want.` Return: `Return to S0 · Choose how to begin`.

**Connections:** incoming: platform onboarding. Outgoing: S1 causal waveform; every later module reuses “recording, not treatment.”

## M01.S1 — One beat, one electrical wave

**Purpose and timing:** causal mental model of P, QRS, and T; 5–7 minutes.

**Case contract:** teaching simulation for animation plus a real, morphology-reviewed normal median beat for frozen labeling; lead II; 25 mm/s; 10 mm/mV; ≥250 Hz preferred, 100 Hz permitted for gross labels; target polygons for P, QRS, T; forbidden claims: chamber size, conduction disease, ischemia, electrolyte state.

**Layout:** Desktop: heart/conduction schematic left 5 columns, waveform right 7; label bank below. Laptop: heart 4, trace 6. Mobile: numbered heart frame above trace; `Previous frame`/`Next frame`; label buttons beneath. Keyboard: Space plays/pauses, Left/Right scrubs, `1` selects P, `2` QRS, `3` T, Tab reaches target regions. Touch: tap label then tap waveform; drag is optional.

**Screen/state script:**

| Micro-step | Exact copy | Frames and mechanics |
|---|---|---|
| Hook | Heading: `One heartbeat becomes a sequence of shapes.` Body: `The ECG does not draw the squeeze itself. It draws electrical activation and recovery that help organize the squeeze.` Tutor: `Watch once in plain language. On the second pass, you will name the three large landmarks.` Control: `Watch one beat`. | F0 rest; F1 impulse begins high in right atrium; F2 atria activate and P draws; F3 AV region pauses and baseline holds; F4 ventricles activate rapidly and QRS draws; F5 ventricles recover and T draws; F6 labels remain hidden. Each frame 800 ms; learner controls replay. |
| Plain-language narration | `The upper chambers activate.` `The signal pauses briefly at the hand-off.` `The lower chambers activate quickly.` `The lower chambers recover.` | Caption changes with frames; spoken audio is optional and duplicates captions exactly. |
| Named replay | `Now add the waveform names.` Captions: `P wave — atrial activation`; `QRS complex — ventricular activation`; `T wave — ventricular recovery`. Why chips: `Why is P smaller?`; `Why is QRS taller?`; `Why is QRS narrow?`. | Selecting a why chip opens: `The atria have less muscle mass, so their summed signal is usually smaller.`; `The ventricles have more muscle mass, so their summed activation is usually larger.`; `A specialized conduction network spreads normal ventricular activation quickly, so the QRS is normally brief.` |
| Label task | Prompt: `Place P, QRS, and T on this unlabeled beat.` Labels: `P wave`, `QRS complex`, `T wave`. Control: `Check labels`. | All three must be placed. Snap radius is visual only; scoring uses target polygon. |
| Correct | `Yes. P comes first, QRS follows, and T is the later recovery wave.` | Correct regions gain named outlines. |
| P on T | `Not yet. P is the small wave before the QRS. T comes after the QRS during ventricular recovery.` | Replay frames F1–F5, stopping before each target. |
| QRS on P/T | `Not yet. Find the brief, usually tallest cluster of deflections. That is the QRS complex.` | QRS silhouette pulses once; no target reveal after first miss. |
| T on P | `Not yet. T is the broader wave after the QRS, not the small wave before it.` | Timeline arrow appears left-to-right. |
| Explain check | Prompt: `Why is the QRS usually larger than the P wave?` Choices: `The ventricles contribute more muscle mass to the recorded signal`; `The ECG magnifies the QRS with a different scale`; `The QRS represents the atria squeezing harder`. | Correct choice 1. Correct: `Yes. More ventricular muscle contributes to the summed electrical signal.` Choice 2: `The scale stays the same across this beat. The size difference comes mainly from the tissue contributing to the signal.` Choice 3: `P and QRS represent electrical activation, not squeeze strength. Compare the amount of atrial and ventricular muscle.` |
| Equivalent transfer | Prompt: `Find the T wave on a different normal beat.` | New real median beat, altered amplitude and rate; target click/tap required. Correct: `Yes. You used sequence and shape, not the exact height of the first example.` |
| Transition | `You can now locate the three main waveform landmarks. Next, the paper turns their distance and height into measurements.` | Button `Continue to the ECG ruler`. |

**Mastery evidence:** `observation.waveform_landmarks`: 3/3 labels on teaching beat and T on equivalent real beat; `mechanism.activation_sequence`: 1/1 causal check. Tutorial cap 0.65; later mixed evidence required for mastery.

**Misconception branches:** “T always upright” → `T direction depends on the lead and context. In this lead-II teaching example it is upright; later scenes show normal exceptions.` “QRS is contraction” → `QRS is ventricular electrical activation. Mechanical contraction follows; the ECG does not directly measure squeeze strength.`

**Tangent example:** “What is the flat part between P and QRS?” → `On this tracing — The short flat stretch after P is visible. General connection — It is the PR segment, part of the atrial-to-ventricular hand-off. We will measure the whole PR interval in S6. Where we paused — You were placing P, QRS, and T.` Return: `Return to S1 · Place the three waveform labels`.

**Connections:** incoming S0. Outgoing S2 timing; S5 P–QRS relation; M4 AV conduction; M5 ventricular activation; M7 recovery.

## M01.S2 — The grid is your ruler

**Purpose and timing:** calibration, time, voltage, box arithmetic, honest precision; 7–9 minutes.

**Case contract:** standard simulated calibration panel and two real clean leads; paper speed 25 mm/s; gain 10 mm/mV; visible 1 mV × 200 ms calibration pulse; sampling ≥100 Hz; target spans exactly 200 ms, 80 ms, 1.0 mV, and a novel 120–240 ms span. Nonstandard speed/gain appears only in a non-scored contrast.

**Layout:** Desktop/laptop: magnified grid 8 columns, measurement notebook 4; time lesson precedes voltage vertically. Mobile: grid fills width; readout is pinned below, never over trace. Keyboard handles: Tab selects left/right handle, Arrow keys move 1 small box, Shift+Arrow moves 1 big box. Touch alternatives: `Set start`, tap; `Set end`, tap; `Nudge −1`, `Nudge +1`.

**Screen/state script:**

| Step | Exact copy / branch | Interaction |
|---|---|---|
| Calibration hook | Heading: `The grid turns distance into time and voltage.` Body: `Before measuring, check the calibration marks. At the standard settings used here, the paper moves at 25 mm/s and the signal gain is 10 mm/mV.` Habit callout: `If speed or gain changes, the boxes mean something different.` | Calibration pulse outlined; labels appear only after learner selects `Show calibration`. |
| Time build | `Read across for time.` Facts appear one at a time: `1 small box = 0.04 s = 40 ms`; `5 small boxes = 1 big box = 0.20 s = 200 ms`; `5 big boxes = 1 second.` | Learner groups five small boxes, then five big boxes. |
| Time task A | Prompt: `Mark a span of exactly one big box.` Readout: `[n] small boxes · [value] ms`. Control: `Check span`. | Pass 180–220 ms only if endpoints align within half a small box; display target is 200 ms. |
| A correct | `Yes. One big box is five small boxes: 5 × 40 ms = 200 ms.` | Add `Time` to reference card. |
| A short | `Your span is shorter than one big box. Move the end marker right until it covers five small boxes.` | No target snap. |
| A long | `Your span is longer than one big box. Bring one marker inward until five small boxes remain between them.` | — |
| Time task B | `Now mark 80 ms on a different part of the grid.` | Equivalent blank grid. Correct: `Yes. Eighty milliseconds is two small boxes.` Wrong: `Count in 40 ms steps: one small box is 40 ms.` |
| Voltage build | `Read up or down for voltage.` Facts: `1 small box = 0.1 mV`; `5 small boxes = 0.5 mV`; `10 small boxes = 1 mV.` | Grid rotates emphasis from x-axis arrow to y-axis arrow; never rotates the actual paper. |
| Voltage task | `Resize the calibration pulse to 1 mV at standard gain.` Readout: `[n] mm · [value] mV`. | Correct height 10±0.5 mm. Correct: `Yes. At 10 mm/mV, a 1 mV pulse is 10 mm tall.` Wrong: `At standard gain, 1 mV is ten small boxes tall.` |
| Nonstandard contrast | Heading: `Same boxes, different setting` Body: `This copy is displayed at 50 mm/s. A small box is now 20 ms wide. Do not reuse the 25 mm/s conversion without checking.` Check: `What must you inspect before timing a waveform?` Choices: `Paper speed`; `Lead name only`; `Screen brightness`. | Correct: `Yes. Speed determines the time scale.` Other: `That does not determine the time represented by each box. Check paper speed.` |
| Precision note | `Estimate from boxes first. Compare with printed measurements when available. Use calipers for a borderline value—not as a ritual on every beat.` | Optional `Try calipers` sandbox has no score. |
| Transfer | `This unseen span begins at one marker and ends at the other. Enter its duration in milliseconds.` Input label `Duration in milliseconds`; tolerance is max(20 ms, 10% grounded span). | Correct: `Yes. Your estimate is within the grid’s practical resolution.` Partial: `Your arithmetic is close, but your endpoint is one small box away. Recheck the boundary.` Incorrect numeric: `Use the visible box count. A number without matching the span is not evidence.` |
| Transition | `You can read the ruler. Before using it, decide whether the signal is readable for the task.` | `Continue to signal quality`. |

**Mastery evidence:** box grouping, calibration pulse, 80 ms transfer, unseen duration. Store raw endpoints, box count, grounded value, error, method, and resolution. Any answer containing a plausible number but wrong endpoint fails `measurement.boundary` even if within numeric tolerance by coincidence.

**Tangent example:** “Why are ECGs sometimes at 50 mm/s?” → `On this tracing — The current panel is explicitly labeled 50 mm/s. General connection — Faster paper spreads events across more horizontal space, which can help inspect rapid timing, but every conversion must use the displayed speed. Where we paused — You were comparing standard and nonstandard time scales.` Return: `Return to S2 · Compare the 50 mm/s panel`.

**Connections:** incoming S1 waveform boundaries. Outgoing S4 rate, S6 intervals, M3 timing, M7 QT/ST measurement. Clinical bridge: `A correct-looking number is unsafe if calibration is wrong; report the setting or uncertainty.`

## M01.S3 — Readable for what?

**Purpose and timing:** task-specific quality judgment and artifact localization; 5–7 minutes.

**Case contract:** four real corpus strips and two equivalent retries: clean; baseline wander with visible QRS; muscle/tremor artifact obscuring P/ST but not every QRS; dropout/unusable segment. Lead II plus one comparison lead when available; 8–10 s; standard calibration; quality labels clinician-reviewed; artifact polygons supplied; report/diagnosis hidden.

**Layout:** Desktop/laptop: one strip at a time at 760 × 180 px, four assessability chips below, artifact box tool to right. Mobile: strip horizontally pannable with overview; chips 2 × 2. Keyboard: `R` rate, `P` P/PR, `S` ST–T, `N` none; box tool has start/end keyboard markers.

**Exact opening:** Heading `Readable for what?` Body `Noise does not make every question equally impossible. Decide which tasks the visible signal can support. Do not force a measurement the tracing cannot defend.` Tutor: `For each strip, select every assessable domain. If noise is present, mark the region that limits the read.`

**Domain controls:** `Rate / QRS timing`; `P waves / rhythm`; `PR interval`; `ST–T shape`; `None of these reliably`. Helper: `Select all that apply.` Artifact control `Box the limiting artifact`; accessible name `Draw a rectangle around the segment that limits interpretation`.

**Deterministic branch copy:**

- Clean, all domains chosen: `Yes. The baseline and waveform boundaries are clear enough for these tasks.`
- Clean, domain omitted: `This strip is cleaner than your selection suggests. Inspect the P-wave boundary and the baseline, then add the supported domain.`
- Baseline wander, rate only: `Good boundary. The QRS complexes remain countable, but the moving baseline weakens ST–T measurement.`
- Baseline wander marked “none”: `The baseline wanders, but the QRS complexes still stand out. Rate may remain assessable.`
- Tremor artifact with P/PR/ST selected: `Not yet. Fine noise overlaps the low-amplitude atrial and ST–T signal. Keep only the domains whose boundaries remain visible.`
- Unusable segment with any domain: `This segment does not show repeatable boundaries for the selected task. “None of these reliably” is the defensible choice.`
- Box overlaps <50% supplied artifact: `Your box misses most of the limiting region. Follow the irregular high-frequency or drifting signal, not the regular QRS peaks.`
- Correct classification but no required box: `Your assessability decision is sound. Add evidence by boxing the artifact.`
- Partial selection: `You identified [supported domain]. Recheck whether [missing domain] has a visible start, end, or baseline.`

**Equivalent retry:** one new signal-quality strip with prompt `A colleague asks only for ventricular rate. Is this strip adequate for that task? Mark the evidence.` Correct requires binary choice plus two QRS marks; feedback `Yes. You limited the claim to a task the tracing can support.`

**Mastery evidence:** 4/4 corrected classifications, required artifact boxes IoU ≥0.35 or center inside supplied broad ROI, transfer claim limited appropriately. Scene completion allows corrected errors; `needs_review` if >2 domain overclaims or high-confidence “fully readable” on unusable strip.

**Tangent:** “Can artifact look like ventricular fibrillation?” → `On this tracing — Organized QRS complexes continue through the noisy segment. General connection — Artifact can imitate dangerous rhythms, so compare leads, look for an underlying marching QRS, and assess the patient rather than trusting one noisy channel. This lesson cannot assess a real patient. Where we paused — You were boxing the limiting artifact.` Return `Return to S3 · Box the limiting artifact`.

**Connections:** incoming S2. Outgoing all measurement scenes; M2 lead-placement integrity; M3 artifact mimic. Clinical bridge exact: `When the question matters clinically, name what is and is not assessable instead of converting noise into certainty.`

## M01.S4 — Regular first, then rate

**Purpose and timing:** choose a rate method from regularity and produce a grounded estimate; 7–9 minutes.

**Case contract:** one real regular sinus strip, one real irregular strip, one equivalent regular/irregular transfer; lead II rhythm strip ≥6 s, ideally 10 s; calibration visible; grounded ventricular rate; R-peak geometry; no rhythm label exposed; quality sufficient for R peaks. No rate scoring from median-beat tiling.

**Layout:** Desktop: strip top, march tool and method cards center, spacing slider sandbox below. Mobile: strip then large `Mark next R` button; method cards stacked. Keyboard: press `M` to drop each march marker, arrows nudge; numeric input has unit suffix `bpm` outside text field.

**Screen/state script:**

| Step | Exact copy and branches | Mechanics |
|---|---|---|
| Hook | Heading `Regular first, then rate` Body `R–R regularity chooses the rate method. Check spacing before doing arithmetic.` | R peaks unmarked. |
| March | Prompt `Mark four consecutive R peaks.` Correct `Yes. These R–R intervals are [regular / irregular].` Missed peak `That mark is not on the main ventricular peak. Use the repeating QRS landmark.` | Each mark within 80 ms of any grounded R peak; four chronological marks required. |
| Regularity | Choices `Regular`; `Regularly irregular`; `Irregular`. For regular case correct: `Yes. The R–R intervals are similar enough for one representative interval.` Incorrect: `Compare the gaps, not the height of the QRS complexes.` | Show interval bands only after commitment. |
| Method | Prompt `Which method fits this regular strip?` Choices `300 ÷ large boxes between R waves`; `Count QRS complexes in 6 seconds × 10`; `Read one P wave and multiply by 60`. Correct `Yes. The 300 rule is efficient when the rhythm is regular.` Six-second choice: `That can estimate an average, but the regular strip supports the more precise box method taught here.` P choice: `Ventricular rate is counted from QRS complexes, not from one P wave.` | — |
| Estimate | Prompt `Enter your ventricular rate estimate.` Helper `A beginner estimate within [tolerance] bpm is accepted.` | Value must be 20–250 and within max(5 bpm, 10%) grounded HR; selected method must match regularity. |
| Estimate correct | `Yes. [boxes] large boxes gives about [estimate] bpm; the grounded rate is [value] bpm.` | Machine value is revealed only now. |
| Arithmetic wrong | `Your R marks are sound, but the arithmetic is off. Use 300 ÷ [boxes].` | Does not reset marks. |
| Boundary wrong | `The number happens to be near the rate, but the selected R–R interval is not anchored to two R peaks. Re-mark the interval.` | Prevent lucky numeric pass. |
| Irregular case | Prompt `The gaps now vary. Choose a method that estimates the average ventricular rate across the available time.` Correct choice `Count QRS complexes in 6 seconds × 10`. Feedback `Yes. A longer sample is more representative when the rhythm is irregular.` | Learner shades exactly 6 s using grid, counts QRS, enters count and rate. |
| Slider sandbox | Heading `Feel the inverse relationship` Copy `Move the R waves closer together. The rate rises because more beats fit into one minute.` | Not scored; screen-reader alternative is a three-row table of R–R and rate. |
| Transfer | `New strip: mark regularity, choose a method, and estimate the rate.` | New case; all three actions required. |
| Transition | `Rate describes speed. The next question asks where the rhythm appears to begin and how P waves relate to QRS complexes.` | `Continue to the sinus pattern`. |

**Misconceptions:** “300 rule on irregular” branch above; atrial versus ventricular rate: `This scene asks for ventricular rate, so count QRS complexes. Atrial and ventricular rates can differ; M4 returns to that relationship.` “Machine says 72” before work: `Use the printed value as a check after your own estimate, not as a substitute for locating R waves.`

**Mastery evidence:** method selection, R marks, time span, count, numeric rate, transfer. Incoming S2; outgoing S5, M3.1–3.2, M4 atrial-versus-ventricular rates, M6 tachycardia.

**Tangent:** “What if the rate changes during the strip?” → `On this tracing — The R–R intervals [do/do not] vary over the displayed sample. General connection — Report the observed range or an average with the method and duration; one number can hide variation. Where we paused — You were choosing the method for an irregular strip.` Return `Return to S4 · Choose the irregular-rate method`.

## M01.S5 — Is there a sinus pattern?

**Purpose and timing:** sinus as atrial origin/relationship, separate from rate; 8–10 minutes.

**Case contract:** three teaching simulations (sinus brady, normal-rate sinus, sinus tachy) and three real/reviewed transfer strips (sinus, ectopic atrial/not-sinus, ambiguous/noisy). Lead II and aVR for full check; ≥8 s; P polygons and P–QRS links; rate hidden until source judgment; no unsupported etiologic label.

**Layout:** Desktop: lead II and aVR aligned; P–QRS relationship board below. Laptop/mobile: lead II first; aVR revealed in second half. Pairing uses click/tap P then QRS; keyboard uses numbered beats and `Link selected P to QRS`.

**Exact checklist card:** Heading `A sinus pattern is a relationship, not a speed.` Items: `A P wave before every QRS`; `A QRS after every P`; `P waves with the same shape from beat to beat`; `A stable PR relationship`; `P usually upright in lead II`; `P usually inverted in aVR`. Footer: `Slow sinus and fast sinus are still sinus.`

**Interaction sequence and copy:**

1. `Mark three P waves in lead II.` Correct: `Yes. Each selected P is small, upright, and similar in shape.` P-on-T: `That later rounded wave is T. Look immediately before each QRS for P.`
2. `Link each selected P to the QRS it precedes.` Correct: `Yes. Each P has one following QRS, and each QRS has one preceding P.` Wrong pairing: `Follow time from left to right. Pair each P with the next QRS, not the previous one.`
3. `Compare the PR relationship. Is it stable across these beats?` Correct stable: `Yes. The P-to-QRS timing stays consistent.` Incorrect: `Place the march guides at P onset and QRS onset; compare the gaps.`
4. Reveal aVR. `What should the sinus P usually do in aVR?` Choices `Point downward`; `Point upward`; `Disappear`. Correct: `Yes. The atrial activation vector usually moves away from aVR, so P is commonly inverted there.` Up: `aVR views from the opposite shoulder; normal sinus atrial activation usually moves away from it.` Disappear: `The P wave may be small, but disappearance is not a sinus criterion.`
5. Compare rate simulations. Prompt `The rate changes from 46 to 72 to 118 bpm while the P-wave source and P–QRS relationship stay the same. Which statement is strongest?` Choices `All three can retain a sinus pattern`; `Only 60–100 bpm can be sinus`; `A fast rate proves a ventricular origin`. Correct: `Yes. Sinus describes origin and relationship; bradycardia and tachycardia describe rate.` Others: `Do not use the 60–100 range as a sinus-source test.`
6. Discrimination cards: `Sinus pattern`; `Not a sinus pattern`; `Not assessable`. Learner must select one evidence chip: `P morphology`; `P–QRS relationship`; `Lead-II/aVR direction`; `Signal quality`.

**Feedback by card:**

- Sinus brady called non-sinus: `The rate is slow, but the P–QRS evidence remains sinus. Separate speed from source.`
- Sinus tachy called non-sinus: `The rate is fast, but every visible P still precedes a QRS with stable morphology and timing.`
- Ectopic atrial strip called sinus: `The P direction or shape does not satisfy the full sinus pattern. Describe “not clearly sinus” without naming a mechanism not yet taught.`
- Ambiguous/noisy called sinus or non-sinus: `The P waves are not reliable enough for that claim. “Not assessable” is the evidence-bounded answer.`
- Correct label without evidence: `Your label is defensible. Select the visible criterion that supports it.`

**Equivalent transfer:** unseen strip, six P marks, label, evidence sentence. Exact prompt: `Complete the sentence: “This is [sinus / not clearly sinus / not assessable] because [visible evidence].”` Meaning rubric requires label plus at least two supported criteria; unsupported diagnosis is broadened without penalty if evidence is correct.

**Mastery evidence:** P localization, 1:1 pairing, stability judgment, aVR direction, rate-source separation, transfer evidence. High-confidence false sinus on ambiguous strip adds M3 artifact/reliability review.

**Tangent:** “Can a rhythm be sinus and irregular?” → `On this tracing — The displayed example has [regular/variable] R–R spacing while its visible P–QRS relationship remains [description]. General connection — Yes. Sinus describes the origin; respiratory sinus arrhythmia can vary the timing. M3 separates those patterns. Where we paused — You were comparing sinus source with rate.` Return `Return to S5 · Compare rate without changing source`.

**Connections:** incoming S1, S4. Outgoing S6; M3 sinus variants/PAC; M4 block; M6 tachyarrhythmias.

## M01.S6 — Measure PR and QRS

**Purpose and timing:** boundary-based interval measurement and descriptive categorization; 8–10 minutes.

**Case contract:** real median beats plus rhythm context; one normal PR, one prolonged PR, one narrow QRS, one wide QRS; lead II or lead with clearest boundary; standard calibration; grounded PR/QRS; onset/end geometry clinician-reviewed; at 100 Hz report to 10 ms resolution; permitted claims only `PR within/above reference` and `QRS narrow/wide`; diagnosis labels hidden.

**Layout:** beat 8 columns; definition/normal band 4. Mobile magnifies one interval at a time. Two-handle measurement with keyboard/touch alternatives from S2. Printed measurement is concealed until `Compare with report` after learner submission.

**Exact copy and branches:**

| Stage | Copy |
|---|---|
| Intro | Heading `Boundaries first: PR and QRS` Body `An interval is only as good as its start and end marks. Locate the waveform boundaries, estimate from the grid, then compare with the printed measurement.` |
| PR definition | `PR interval: start of P to start of QRS. It represents atrial-to-ventricular electrical conduction.` Reference `Common adult reference taught here: 120–200 ms, or 3–5 small boxes at 25 mm/s.` |
| PR prompt | `Place the start marker at P onset and the end marker at QRS onset. Enter your estimate.` |
| PR correct normal | `Yes. Your boundaries give about [value] ms, within the 120–200 ms reference.` |
| PR correct long | `Yes. Your boundaries give about [value] ms, above the reference. Describe “long PR”; do not assign a cause yet.` |
| PR starts at P peak | `Your start marker is on the P peak. PR begins where P first leaves the baseline.` |
| PR ends after QRS starts | `Your end marker is late. Stop where the QRS first leaves the baseline.` |
| PR number right/boundaries wrong | `The number is close, but the marks do not span PR. Correct boundaries are required evidence.` |
| QRS definition | `QRS duration: first ventricular deflection to the end of the last ventricular deflection.` Reference `Narrow: less than 120 ms. At 25 mm/s, 120 ms is three small boxes.` |
| QRS prompt | `Mark QRS onset and QRS end, then classify the duration.` Controls `Narrow`; `Wide`; `Not assessable`. |
| QRS narrow correct | `Yes. The measured QRS is [value] ms, below 120 ms.` |
| QRS wide correct | `Yes. The measured QRS is [value] ms, at or above 120 ms. “Wide QRS” is the supported description.` |
| Miss terminal S/R′ | `Your end marker stops before the final ventricular deflection returns to baseline. Include the full QRS.` |
| Includes ST | `Your end marker extends into ST. Stop where the final QRS deflection returns to baseline.` |
| Compare report | Heading `Estimate, then verify` Copy `Your measurement: [learner value] ms. Printed value: [packet value] ms. Difference: [difference] ms.` Branch agreement: `These agree within the source resolution.` Branch discrepancy: `Recheck boundary visibility and calibration before choosing either number.` |
| Limits | `A long PR or wide QRS is a finding, not a complete diagnosis. Mechanisms return in Modules 4 and 5.` |
| Transfer | `On a new beat, measure either PR or QRS without being told whether it is normal.` |
| Transition | `You have measured activation. Next, identify the baseline, ST segment, T wave, and the full normal reference.` |

**Scoring:** boundary hit within max(20 ms, 1 sample plus visual tolerance), numeric within max(20 ms, 10%), category correct, and evidence sentence. Complete requires both PR and QRS plus one unseen transfer. Store precision disclosure. Calibration mismatch or unreadable boundary makes `Not assessable` correct.

**Tangent:** “Does a wide QRS mean bundle branch block?” → `On this tracing — The QRS measures [value] ms, so “wide” is supported. This scene does not establish its mechanism. General connection — Bundle-branch block is one cause of a wide QRS, but ventricular pacing, pre-excitation, ventricular origin, and other conduction patterns can also widen it. M5 uses morphology and context to discriminate them. Where we paused — You were marking QRS end.` Return `Return to S6 · Mark QRS end`.

**Connections:** incoming S2/S5. Outgoing S7/S10; M4 PR/conduction; M5 QRS morphology; M6 wide tachycardia.

## M01.S7 — ST, T, QT, and the normal reference

**Purpose and timing:** baseline/J point, recovery landmarks, normal-appearing template, QT preview; 7–9 minutes.

**Case contract:** clean normal real beat and teaching simulation for movable ST; lead II plus aVR/V1 exception tiles; standard calibration; baseline and J-point geometry; no ischemia or QT threshold claims; QT shown conceptually from QRS onset to T end.

**Layout:** Desktop/laptop trace 8 columns, normal-reference builder 4. Mobile sequential panels. Point tool keyboard alternative uses `Select baseline`, `Select J point`, and arrow nudge. ST drag alternative buttons `Raise one small box`, `Lower one small box`, `Return to baseline`.

**Screen/state script:**

1. Heading `Recovery landmarks: baseline, ST, T, and QT`. Body `Describe the shape and reference before assigning a cause.`
2. Prompt `Mark a flat TP segment to use as the baseline.` Correct: `Yes. This flat interval between the end of T and the next P is a defensible baseline here.` PR selected: `That is the PR segment. It can sometimes help, but this task asks for a TP reference.` Wave selected: `A baseline should be a stable flat reference, not a waveform peak.`
3. Prompt `Mark the J point, where QRS ends and ST begins.` Correct: `Yes. The J point is the junction from ventricular activation into the ST segment.` Too early: `You are still inside the QRS. Follow the final deflection until it returns to the ST level.` Too late: `You are already on the ST segment. Move back to the end of QRS.`
4. Definition `ST segment: the interval after the J point and before the T wave. In this normal reference it lies near the baseline.` Interaction heading `Move it, then restore it`. Copy `Raise or lower the simulated ST segment once. Then return it near baseline.` Raised feedback: `You created visible ST elevation in a simulation. Shape, amount, lead distribution, and context determine meaning later.` Lowered: `You created visible ST depression in a simulation. Description comes before cause.` Restored: `Yes. This example is back near its baseline.`
5. T copy `T wave: ventricular recovery. In lead II it is commonly upright when the main QRS is upright. aVR and V1 are common normal exceptions; “T always follows QRS” is not a rule.` Check: `Which statement is safe?` Correct option `T direction depends on the lead; lead II is often upright, with normal exceptions such as aVR and V1.` Feedback `Yes. Use the actual lead and distribution.` Distractor `Every normal T wave must be upright in every lead.` Feedback `Normal T-wave direction varies by lead.`
6. QT preview `QT interval: QRS onset to the end of T. It spans ventricular activation through recovery and changes with heart rate. Rate correction and clinical thresholds come in Module 7.` Prompt `Place the start and end of QT without measuring it.` Correct `Yes. You included QRS and T, but not the following U wave or P wave.`
7. Builder heading `Assemble the beginner normal reference`. Cards: `P: small and upright in II`; `PR: 120–200 ms`; `QRS: less than 120 ms`; `ST: near a defensible baseline`; `T: expected direction for the lead`; `QT: begins at QRS onset and ends at T end; interpretation is rate-aware.` Learner places cards in temporal order. Correct `Yes. This is a reference pattern, not a promise that every normal person looks identical.`
8. Equivalent transfer prompt `On a new normal-appearing beat, mark baseline, J point, and T wave.` All required.
9. Clinical bridge `Later, changed ST–T or QT findings will be interpreted by distribution, dynamics, activation pattern, medications, electrolytes, and patient context. This scene establishes the landmarks only.`
10. Transition `One lead shows timing well. To understand direction and location, expand to twelve views.` Control `Continue to twelve views`.

**Mastery evidence:** baseline, J point, ST restoration, lead-aware T statement, QT endpoints, ordered template, unseen transfer.

**Tangent:** “Does an inverted T wave mean a heart attack?” → `On this tracing — This teaching beat has an upright T wave in lead II. General connection — T-wave inversion is a description with many possible contexts, including normal variants, altered ventricular activation, strain, ischemia, and other causes. Distribution, change from prior, symptoms, and the rest of the ECG matter. Where we paused — You were assembling the normal reference.` Return `Return to S7 · Assemble the normal reference`.

**Connections:** incoming S6. Outgoing S8/S10; M5 secondary recovery; M7 full QT/ST–T; M8 ischemia.

## M01.S8 — One event, twelve views

**Purpose and timing:** standard layout, simultaneous-view concept, normal R/S progression, aVR sinus closure; 7–9 minutes.

**Case contract:** morphology-reviewed real normal 12-lead; standard sequential 3 × 4 layout plus lead-II rhythm strip; all 12 leads named; timing contract states whether columns are sequential or simultaneous; median beats for V1–V6 permitted only when labeled; R/S amplitudes and transition ground truth; aVR P visible; no territory diagnosis.

**Layout:** Desktop: 3 × 4 ECG at least 860 × 420; synchronized “one event” overlay. Laptop: 720 px and collapsible explanation. Mobile default `Study view` stacks leads; scored locator uses named lead tiles, not horizontal precision. Standard layout toggle is reference only.

**Screen/state script:**

- Heading `One electrical event, twelve directed views`.
- Body `A 12-lead ECG does not show twelve different hearts. Each lead reports the heart’s electrical event from a different direction.`
- Timing note for sequential display: `This printout uses sequential columns. Leads in different columns are recorded at different moments; the long lead-II strip shows rhythm continuously.` Or, if simultaneous: `These leads are aligned in time; the cursor marks the same moment in each view.` This token is selected by packet metadata and may not be improvised.
- Interaction `Scrub one beat`. Helper `Move the time cursor. Watch the corresponding waveform moment across every displayed lead.` Correct check prompt `Why do the shapes differ?` Correct `Each lead views the same evolving electrical vector from a different direction.` Feedback `Yes. Viewpoint changes polarity and amplitude.` Distractor `Each lead records a separate heartbeat.` Feedback `The leads are viewpoints; consult the packet timing note for simultaneity versus sequential columns.`
- Lead scavenger prompt `Find lead II, aVR, V1, V3, and V6.` Each selection announces `[lead] selected, row [n], column [n].` Wrong: `That tile is [actual lead]. Use the printed lead label, not waveform shape.`
- R progression heading `Watch R grow and S shrink across V1 to V6.` Body `The transition is the first precordial lead where R becomes taller than S. It is often around V3–V4, with normal variation.` Control `Scrub V1 → V6`. For each lead, accessible text reports `R/S ratio [value rounded to one decimal]` only if grounded.
- Prompt `Mark the transition lead on this tracing.` Correct: `Yes. In [lead], R first becomes taller than S.` One lead early: `Not yet. In [lead], S is still at least as large as R.` One late: `R already exceeded S in the preceding lead. Choose the first crossover.` Ambiguous/no clear transition: correct option `No single clear transition is assessable`; copy `Yes. Do not invent a transition when the visible R/S relation is equivocal.`
- aVR closure: `Return to the sinus clue from S5. In this tracing, P is upright in II and inverted in aVR because the atrial activation direction moves toward II and away from aVR.` Prompt `Select the P wave in aVR.` Correct `Yes. Its downward direction is the expected opposite view here.`
- Transfer prompt `On a second normal 12-lead, locate V1 and V6, mark the transition, and explain “twelve views” in one sentence.` Rubric accepts semantic equivalent only if same-event/directed-view relationship is present.
- Clinical bridge `Lead location becomes clinically useful only after the viewpoint map is understood. Module 2 builds that map; Module 8 uses it for regional patterns.`
- Transition `You can navigate the page. Next, turn the limb-lead views into one coarse direction: the QRS axis.`

**Mastery evidence:** 5 lead locations, transition mark, aVR P, explanation, equivalent transfer. False precision warning if 100 Hz or median composite.

**Tangent:** “Are all twelve leads recorded at exactly the same time?” → `On this tracing — [packet timing note]. General connection — Acquisition systems can record channels simultaneously while printed 3 × 4 formats may display sequential time windows. Always read the format marker rather than assume. Where we paused — You were marking the R/S transition.` Return `Return to S8 · Mark the transition lead`.

**Connections:** incoming S5/S7. Outgoing S9/M2; M5 V1/V6 morphology; M8 territories.

## M01.S9 — Axis: the coarse direction

**Purpose and timing:** net frontal QRS direction and beginner quadrant screen; 7–9 minutes.

**Case contract:** vector simulation plus three real, clinician-reviewed ECGs: normal quadrant, clear left-axis deviation, clear right-axis deviation. Limb leads I, II, aVF readable; grounded axis degrees; no cause labels. Borderline I-positive/aVF-negative/II-positive case is a teaching contrast, not scored as definite LAD.

**Layout:** Desktop: hexaxial wheel 6 columns, live limb leads 6. Laptop: 5/5. Mobile: wheel above three live lead cards; rotation by slider plus `Rotate −10°/+10°`. Screen reader receives `Vector at [degrees]; lead I [positive/negative/nearly isoelectric]; aVF [...]`.

**Screen/state script:**

1. Heading `Axis is the ventricles’ net frontal direction.` Body `Imagine compressing the QRS activity into one arrow. In most hearts it points generally down and left because left-ventricular muscle contributes strongly.`
2. Prompt `Rotate the arrow into lead I’s positive direction.` Feedback `As the vector points toward lead I, the net QRS in I becomes positive.` Then perpendicular: `Near perpendicular, positive and negative portions balance and the QRS approaches isoelectric.`
3. Rule card `Coarse quadrant screen`: `Lead I positive + aVF positive → normal quadrant, about 0° to +90°`; `Lead I positive + aVF negative → leftward; use lead II for the −30° refinement in Module 2`; `Lead I negative + aVF positive → rightward`; `Lead I negative + aVF negative → extreme quadrant; full interpretation later.` Footer `Do not call every I-positive/aVF-negative axis abnormal.`
4. Exploration prompt `Reach the green normal sector, then a clearly leftward and a clearly rightward sector.` Status strings `Normal sector reached`; `Leftward sector reached`; `Rightward sector reached`.
5. Classification case A prompt `Use only QRS polarity in I and aVF. Choose the coarse category.` Controls `Normal quadrant`; `Leftward`; `Rightward`; `Extreme quadrant`; `Not assessable`. Correct copy includes observed polarities. Wrong copy `Read net QRS polarity, not the tallest single spike.`
6. Borderline contrast exact copy: `Lead I is positive and aVF is negative, but lead II remains positive. Call this “leftward, possibly within the normal extension” at this stage. Module 2 refines the boundary near −30°.` Check correct option `Leftward; use lead II before definite left-axis deviation.`
7. Equivalent transfer: two unseen cases, one clear deviation and one normal. Requires polarity marks on both leads plus category. Correct `Yes. Your category follows both lead polarities.`
8. Clinical boundary `Axis is evidence about ventricular activation direction. Its causes require morphology and context; those return in Modules 2 and 5.`
9. Transition `You now have every ingredient of the beginner read. Next, watch the complete sweep and predict each step.`

**Feedback details:** I/aVF one wrong → `You have lead [correct lead] right. Recheck whether the net area of [other lead] lies mostly above or below baseline.` Tall R but deep S → `Axis uses the net QRS, not R height alone.` Machine disagreement → `Record your visible polarity judgment, then compare the machine degree. A disagreement is a reason to recheck lead placement and boundaries, not to hide either result.`

**Mastery evidence:** three exploration sectors; borderline rule; two unseen classifications with lead marks. Incoming S8; outgoing S10/M2.7–2.9/M5 fascicular block.

**Tangent:** “What does left axis deviation mean clinically?” → `On this tracing — The net QRS is [grounded category and degree if supplied]. The current scene supports direction, not cause. General connection — Leftward axis can reflect normal variation or altered ventricular activation; morphology, age, prior ECGs, and clinical context narrow the explanation. M2 refines measurement and M5 connects axis with conduction patterns. Where we paused — You were classifying the coarse axis.` Return `Return to S9 · Classify the coarse axis`.

## M01.S10 — The complete sweep, modeled actively

**Purpose and timing:** demonstrate ordered evidence, uncertainty, and synthesis on two real ECGs; 8–10 minutes.

**Case contract:** Case A normal-appearing; Case B one describable non-acute deviation among rate, PR, QRS, or clear axis; real, standard 12-lead, clinician-reviewed; all ground truth fields present; diagnostic report hidden; ST–T claims limited to `normal-appearing` or `not assessable` unless reviewed; no acute exemplars.

**Layout:** ECG 8 columns, sweep rail 4; tutor below rail rather than covering tracing. Mobile: rail is a seven-step accordion above each focused lead crop; full tracing remains one tap away.

**Persistent rail copy:** `1 Calibration & quality`; `2 Rate`; `3 Rhythm`; `4 Axis`; `5 PR & QRS`; `6 ST–T`; `7 Synthesis`. Intro: `Use the same order every time. A systematic sweep prevents the most visually dramatic feature from erasing the rest of the ECG.`

**Case A script, exact:**

| Rail step | Learner prompt | Reveal narration |
|---|---|---|
| 1 | `Predict: Is calibration standard, and which domains are readable?` | `Calibration is [speed] mm/s and [gain] mm/mV. The visible signal supports rate, P–QRS, interval, QRS, and gross ST–T review.` |
| 2 | `Mark two R waves and estimate the rate.` | `The R–R spacing gives about [learner estimate] bpm; the grounded value is [rate] bpm.` |
| 3 | `Before reveal: sinus, not clearly sinus, or not assessable? Select one visible criterion.` | `P waves are [description] in II, [description] in aVR, and have a [relationship] with QRS. I would describe [rhythm description].` |
| 4 | `Predict the coarse axis from I and aVF.` | `Lead I is [polarity] and aVF is [polarity], supporting [axis description].` |
| 5 | `Mark PR and QRS once each.` | `PR is about [value] ms, [within/above] the reference. QRS is about [value] ms, [narrow/wide].` |
| 6 | `Choose a baseline and describe ST–T appearance without assigning a cause.` | `In the readable leads, ST is [near baseline/not confidently assessable] and T-wave direction is [description].` |
| 7 | `Which summary preserves the evidence and uncertainty?` | `My one-line read: “[calibration/quality]; [rate and rhythm]; [axis]; PR [value/category]; QRS [value/category]; ST–T [description].”` |

**Case B uses the same exact prompts.** Its reveal must foreground the observed deviation and say: `I am naming [finding], not its cause. [later module] will test the mechanism.` Case B cannot reveal a diagnosis label from source metadata.

**Prediction feedback:** correct `Yes. Now compare your evidence with the modeled wording.` partial `You found [element]. Listen for how the model adds [missing boundary/evidence/uncertainty].` incorrect `Hold the label. Watch where the model places its marks; you will perform an equivalent step in S11.` Predictions are formative and required to advance but do not complete M01 objectives.

**Completion check:** prompt `Put the sweep in order.` Seven cards. Correct: `Yes. Quality and calibration first; synthesis last. The middle steps stay reproducible even when one finding is striking.` Wrong: `Keep measurement dependencies together: rate/rhythm before axis and intervals, waveform description before synthesis.`

**Tangent:** “Why put axis before intervals?” → `On this tracing — Both can be reviewed independently after rate and rhythm. General connection — Different clinical frameworks order the middle steps differently; completeness and consistency matter more than one sacred order. TRACE uses axis before intervals so later vector reasoning stays visible. Where we paused — You were ordering the sweep.` Return `Return to S10 · Order the sweep`.

**Connections:** incoming S0–S9. Outgoing S11 and persistent framework in M2–M9.

## M01.S11 — Guided sweep with fading support

**Purpose and timing:** perform the sweep on three real ECGs with full, partial, then minimal scaffolding; 12–16 minutes.

**Case contract:** three unseen, clinician-reviewed cases: A clean normal; B one clear non-acute deviation; C normal/mimic contrast with at least one `not assessable` domain. Standard 12-lead; required measurements and geometry; no exposed labels; equivalent retry pool ≥3 per critical subskill.

**Layout:** Case A rail expands into one field per step. Case B groups rate/rhythm, axis/intervals, ST–T/synthesis. Case C shows only rail labels and one evidence notebook. Mobile preserves same fading; it never removes access to full tracing.

**Tutor opening:** `Now you lead. I will ask for visible evidence, then fade the prompts. A corrected answer can complete the action; a critical miss returns on an equivalent case.`

**Case A exact prompts:**

1. `Calibration and quality: enter speed, gain, and any domain you would not assess.`
2. `Rate: mark an R–R interval, choose the method, and enter bpm.`
3. `Rhythm: choose sinus, not clearly sinus, or not assessable. Cite two P–QRS features.`
4. `Axis: mark net polarity in I and aVF, then choose the coarse category.`
5. `Intervals: measure one PR and one QRS.`
6. `ST–T: mark a baseline and describe the readable leads.`
7. `Synthesis: write one sentence. Lead with rate and rhythm, then axis, intervals, QRS, ST–T, and uncertainty.`

**Case B exact prompts:**

- `Rate + rhythm: give the ventricular rate, regularity, source description, and visible evidence.`
- `Direction + timing: give axis, PR, and QRS with one mark for each claim.`
- `Recovery + synthesis: describe ST–T and write the one-line read.`

**Case C exact prompt:** `Complete the sweep in your evidence notebook. Add at least one mark for every claim and use “not assessable” where the tracing does not support a conclusion.`

**Meaning rubric and deterministic feedback:**

| Axis | Full | Partial | Incorrect branch |
|---|---|---|---|
| Calibration/quality | correct speed/gain and bounded readability | one setting or domain omitted | `Check the printed calibration before interpreting distance or height.` |
| Rate | method, marks, number within tolerance | number right but method/marks missing | `A rate number needs an R–R or timed-count anchor.` |
| Rhythm | supported label + two criteria | label + one criterion | `Add P morphology or the P–QRS relationship; rate alone does not establish sinus.` |
| Axis | I/aVF marks + category | category only | `Show the two limb-lead polarities that produced the category.` |
| Intervals | boundaries + values + categories | correct category without one boundary/value | `Mark the waveform boundary; do not grade a number detached from the trace.` |
| ST–T | baseline + bounded description | plausible description without reference | `Anchor the description to a visible baseline and lead distribution.` |
| Synthesis | all supported domains, prioritized, uncertainty | ≥5 domains with no false claim | `Do not hide a missing domain inside a fluent sentence. Reopen the sweep rail.` |

Critical miss = false sinus at high confidence, axis direction reversed, wide QRS called narrow, long PR called normal, or unsupported acute/urgent claim. Exact response: `This miss changes the evidence chain. We will pause this case and practise the same subskill on a different tracing.` The remedial card gives one principle, one coached example, then returns to an equivalent case. The original case is not reused.

**Correct-but-ahead example:** learner writes “first-degree AV block.” Response: `Your long-PR observation is correct, and that later label may fit. Foundations records the supported finding: “PR [value] ms, long.” Module 4 will test the conduction diagnosis.`

**Completion:** ≥0.8 weighted accuracy, no unresolved critical miss, all seven domains attempted, equivalent retries passed. Feedback summary exact: `You completed three guided sweeps. Strongest evidence: [axes]. Review target: [axis]. Next, you will complete two transfers without coaching.`

**Tangent:** “Can I use a different order?” → `On this tracing — Your marks cover [domains present]. General connection — A different named framework is acceptable if it consistently covers calibration/quality, rate, rhythm, axis, intervals/QRS, ST–T, and synthesis. For this module, use the visible rail so feedback maps cleanly. Where we paused — You were writing the Case [n] synthesis.` Return `Return to S11 · Case [n] synthesis`.

**Connections:** incoming S10. Outgoing S12; weak axes deep-link to S2–S9.

## M01.S12 — Independent transfer and handoff

**Purpose and timing:** two independent reads, calibrated confidence, remediation route, cross-mode transfer; 12–16 minutes.

**Case contract:** two unseen cases, no source-label leakage. Case 1 clean normal or single descriptive deviation with empty rail. Case 2 mixed but non-acute, blank evidence notebook. All grading manifests complete. Tutor does not proactively cue. Equivalent retry pool for every critical axis.

**Layout:** Case 1 has collapsed rail labels and structured fields. Case 2 presents ECG plus one evidence-linked sentence editor; clicking a sentence clause selects its trace annotation. Desktop/laptop tutor is collapsed with label `Ask for coaching`; mobile tutor follows submit controls. Timer is off by default; optional `Track my time` reports but never scores.

**Entry copy:** Heading `Your read` Body `Two transfers. The first keeps the sweep as an empty checklist. The second gives you a blank evidence notebook. The tutor stays quiet unless you ask.` Confidence note `Confidence is not courage. Match it to the quality and completeness of your evidence.`

**Case 1 fields and placeholders:**

- `Calibration / quality` — `speed, gain, readable domains`
- `Rate` — `method + bpm`
- `Rhythm` — `description + two visible criteria`
- `Axis` — `I/aVF evidence + category`
- `PR and QRS` — `boundaries + values + categories`
- `ST–T` — `baseline + bounded description`
- `Synthesis` — `one evidence-based sentence`
- `Confidence` — controls `Low`; `Moderate`; `High`; helper `Choose confidence in the read, not in the patient’s safety.`

Submit control `Submit Case 1 read`. Blank field message `Complete this domain or write “not assessable” with a reason.` Feedback heading `Evidence review`, rows `Supported`; `Needs correction`; `Not assessable`; `Unsupported claim`. Exact overall branches:

- Full pass: `Your read is complete, evidence-linked, and appropriately bounded.`
- Pass with minor omission: `Your core read is sound. Add [missing noncritical domain] before the blank transfer.`
- Critical miss: `Pause. [claim] conflicts with [visible evidence]. Complete an equivalent [subskill] check before Case 2.`
- Overconfident uncertainty: `The description is reasonable, but High confidence is not supported because [quality/missing boundary]. Recalibrate confidence; accuracy credit is unchanged.`
- Underconfident complete: `Your evidence supports more confidence than you selected. Name the strongest visible anchor, then choose again.`

**Case 2 prompt:** `Write one complete descriptive read. Select each clause and attach it to a lead, interval, or quality observation on the tracing.` Placeholder `Example structure: “Standard calibration; readable tracing; …”` Control `Attach evidence`; accessible name `Attach the selected sentence clause to visible ECG evidence`. Submit `Submit independent read`.

Case 2 deterministic rubric: calibration/quality 10%; rate 15%; rhythm 20%; axis 10%; PR/QRS 15%; ST–T 15%; synthesis 10%; confidence calibration 5%. A supported `not assessable` earns full domain credit. A diagnosis beyond permitted claims is ignored if the descriptive evidence is correct and receives the correct-but-ahead response; a false urgent claim triggers review.

**Payoff copy:**

> `You completed a beginner 12-lead sweep from calibration to synthesis.`
>
> `You did more than name shapes: you linked claims to waveform evidence, limited conclusions when quality was weak, and communicated uncertainty.`

Score labels: `Component accuracy`; `Evidence links`; `Confidence calibration`; `Active time`; `Hints used`. Disclosure: `Time and hints are descriptive. They do not reduce your score.`

**Adaptive handoff card:** Heading `Choose the next useful challenge`. Routes:

- `Build the lead map in Module 2` — `Recommended next: understand why each lead looks different and refine axis.`
- `Practise normal versus deviation` — opens Train with objective tokens from weakest two M01 axes, target/mimic/normal ratio 2:2:1, return path to S12.
- `Try one untimed complete read` — opens Rapid in untimed novice mode with tutor silent until commitment.
- `Review [weak scene]` — exact deep link.

**Module transition:** `Next in the guided path: electrodes, leads, vectors, axis, and normal 12-lead variation.`

**Tangent:** “Is this ECG normal?” → `On this tracing — The supported descriptive read is [grounded summary]. General connection — “Normal” is broader than one tutorial checklist and depends on age, context, comparison, and clinically reviewed criteria. In Foundations, communicate the observed domains and their limits. Where we paused — You were attaching evidence to your independent synthesis.` Return `Return to S12 · Attach evidence to the synthesis`.

## M01 acceptance checklist

- [ ] S0–S12 deep links, resume state, and existing learner records migrate without converting skipped scenes to complete.
- [ ] Every quoted string above is implemented or explicitly versioned; the validated ~25-minute core promise remains distinct from optional tangent and retry time.
- [ ] The wavefront animation has synchronized captions, reduced-motion frames, keyboard controls, and a real-beat transfer.
- [ ] Grid scoring requires both correct boundaries and a grounded value; settings other than 25 mm/s/10 mm/mV are visible and handled.
- [ ] Quality judgments are task-specific and artifact boxes are stored.
- [ ] Rate grading checks regularity, method, marks, and a grounded numeric tolerance.
- [ ] Sinus grading checks source/relationship criteria and never uses rate as the definition.
- [ ] PR/QRS scoring respects source resolution and does not infer a diagnosis.
- [ ] ST/T/QT copy stays descriptive and contains the aVR/V1 exception.
- [ ] The 12-lead timing note reflects actual packet metadata; sequential display is never called simultaneous.
- [ ] Axis normal-quadrant and −30° refinement copy do not contradict each other.
- [ ] Modeled, guided, and independent cases are unseen across stages and have complete evidence manifests.
- [ ] Wrong answers, skips, and one-question placement checks never complete a scene or grant mastery.
- [ ] All critical misses require an equivalent retry; the exact same waveform is not recycled.
- [ ] Tutor tangents restore scene, micro-step, viewport, tool, selections, draft answer, and timer.
- [ ] Desktop, laptop, mobile, keyboard-only, touch, screen reader, 200% zoom, and reduced-motion paths pass human QA.
- [ ] Five true novices complete S0–S5 without facilitator help; observed median duration is within 20% of the displayed estimate.
- [ ] Clinical/content reviewer signs every permitted claim, reference range, target geometry, and case manifest.

## M01 exact hint, visual, input-equivalence, and scoring matrix

Scene bodies contain the primary script. This matrix fixes the remaining hint ladder and implementation states. The second hint always demonstrates on a different example; it never moves the learner’s target.

| Scene | Hint 1 / Hint 2 | Desktop / laptop / mobile and visual states | Keyboard/touch mechanics and deterministic pass |
|---|---|---|---|
| S0 | `There is no graded task here. Choose the support level that feels useful; you may change it later.` / not applicable | D/L full-width tracing then centered path; M 120 px trace then cards. F0 rest, F1 activation, F2 drawn beat, F3 path. | Choice fieldset; arrows choose, Enter continues; touch tap. Orientation completes only as viewed, never mastery. |
| S1 | `Use time order: P before QRS, T after QRS.` / `Watch a different labeled beat once; then label this new beat yourself.` | D heart 5/trace 7; L 4/6; M frames above trace. F0–F6 defined in scene. | Space play; arrows scrub; label then target via keyboard/tap. Pass 3/3 + mechanism + different-beat T. |
| S2 | `Count small boxes between your two markers.` / `I will group five boxes on a blank grid; now mark a different span.` | D grid 8/notebook 4; L 7/3; M grid then pinned readout. V0 calibration, V1 time, V2 voltage, V3 nonstandard, V4 transfer. | Handle arrows/Shift; touch set-start/end. Pass all build tasks plus unseen span with boundary and numeric tolerance. |
| S3 | `Ask which waveform boundaries remain visible for the requested task.` / `On a different noisy strip, I will show why rate can remain assessable when P/ST cannot.` | D/L strip 760 × 180 and domain chips; M pannable strip/chips. V0 raw, V1 selection, V2 box, V3 domain feedback. | R/P/S/N shortcuts plus box form; touch chips/two-corner box. Pass all corrected classifications, boxes, and transfer; overclaim retry uses new artifact. |
| S4 | `Mark R waves before choosing the method.` / `I will solve a different regular or irregular example, then replace this case.` | D strip/march/method, L same compressed, M strip then controls. V0 R marks, V1 regularity, V2 method, V3 rate, V4 report, V5 transfer. | M to march; method radios; numeric input. Pass marks + regularity + method + value on both forms and transfer. |
| S5 | `Look immediately before each QRS and compare P shape beat to beat.` / `On a different strip, I will link one P to one QRS and compare II with aVR.` | D aligned II/aVR + relationship board; L same; M II then aVR. V0 P, V1 links, V2 PR, V3 aVR, V4 rate variants, V5 transfer. | Numbered P/QRS pairs; Link button; tap/tap. Pass all criteria and equivalent evidence sentence; ambiguous overclaim retries new strip. |
| S6 | `Find waveform onset before doing box arithmetic.` / `I will mark PR or QRS on a different beat; your case will be replaced for retry.` | D beat 8/reference 4; L 7/3; M one interval at a time. V0 definition, V1 boundaries, V2 number, V3 category, V4 report, V5 transfer. | Two handles or set-start/end; numeric field/radios. Both intervals plus unseen one; correct number with wrong boundary is partial only. |
| S7 | `Use a flat TP segment before selecting the J point.` / `On a different beat, I will mark baseline and QRS end once; then you will retry unseen.` | D trace 8/builder 4; L 7/3; M sequential panels. V0 baseline, V1 J, V2 ST simulation, V3 T, V4 QT, V5 builder, V6 transfer. | Point tool with named alternatives; ST step buttons. Pass all landmarks, restoration, rule, ordered builder, transfer. |
| S8 | `Read the printed lead label, then compare R and S across V1–V6.` / `I will identify transition on a different 12-lead; apply the first-crossover rule here.` | D ECG ≥860×420; L ≥720 or labeled pan; M study stack + reference toggle. V0 full layout, V1 cursor, V2 lead hunt, V3 R/S scrub, V4 transition, V5 aVR, V6 transfer. | Lead list, cursor arrows, R/S selection; touch taps. Pass 5 locators + transition + aVR + explanation + transfer. |
| S9 | `Read net QRS in I and aVF; do not choose by R height.` / `I will shade positive/negative area on a different pair, then return to new unseen cases.` | D wheel 6/live leads 6; L 5/5; M wheel then three cards. V0 vector, V1 sectors, V2 rule, V3 real cases, V4 borderline, V5 transfer. | Slider/±10°, polarity buttons; touch same. Pass sectors, boundary item, two unseen with evidence; reversed axis retries new cases. |
| S10 | `Follow the highlighted rail step; predict only the evidence requested.` / `Replay the corresponding step on the other modeled case before this one reveals.` | D ECG 8/rail 4; L 7/3; M rail accordion + crop. V0 case, V1 prompt, V2 commitment, V3 reveal repeated ×7, V4 order check. | Predict controls and lead/mark form; touch same. Required predictions + exact seven-card order; formative only. |
| S11 | `Open the current rail step and attach one visible mark before writing the label.` / `Review one coached example from the exact source scene; return to a different guided case.` | D rail/ECG/evidence; L collapsed rail; M accordion. Case A seven steps, B three groups, C notebook; each has commit/feedback/retry states. | All draw tools mirrored by lead/feature forms. Pass ≥0.8, all domains attempted, all critical equivalent retries resolved. |
| S12 | `The empty rail names domains but does not reveal this case.` / `Review one passed example from the weakest source scene; the independent case will be replaced.` | D structured Case1 then blank Case2; L same 7/3; M tutor after submit. V0 case, V1 evidence, V2 submit, V3 audit, V4 retry, V5 payoff/handoff. | Structured fields and clause-to-evidence form; touch tool/tap. Weighted rubric, no unresolved critical miss, confidence calibrated; new equivalent transfer required. |

---

# Module 02 — Leads, vectors, axis, and territories

## M02.0 Module contract and expanded sequence

**Module card title:** `2 · Leads, vectors, axis, and territories`  
**Card description:** `Turn electrodes into directed views, predict waveform polarity, navigate frontal and horizontal planes, refine QRS axis, and distinguish normal variation from a possible acquisition problem.`  
**Duration label:** `Usually 60–80 minutes · five resumable chapters`  
**Prerequisite label:** `Recommended: Module 1 complete, or pass the lead-map placement check`  
**Outcome:** `You will be able to explain why a waveform is positive, negative, or isoelectric; place and navigate the standard leads; identify contiguous and opposite views; estimate frontal QRS axis; describe R-wave progression; and flag patterns that need placement verification before pathology claims.`

**Launch heading:** `Build the spatial model behind the 12-lead.`  
**Launch body:** `You already know that twelve leads show directed views of the heart’s electrical activity. Now you will build those views from the electrodes, predict waveform direction, map neighboring leads, refine axis, and test whether an unusual pattern could come from acquisition.`  
**Launch controls:** `Begin with retrieval`; `Resume at [scene title]`; `Show the lead-map placement check`.  
**Placement-check disclosure:** `The placement check changes guidance and review recommendations. It does not complete scenes or grant mastery.`

The compressed eight-scene native module is replaced by 15 production scenes:

- Chapter A, `Retrieve the trace`: M02.S0–S1
- Chapter B, `Build a directed view`: M02.S2–S4
- Chapter C, `Map the body`: M02.S5–S8
- Chapter D, `Read direction and progression`: M02.S9–S12
- Chapter E, `Verify and transfer`: M02.S13–S14

## M02.S0 — Retrieval: navigate before explaining

**Timing:** 4–5 minutes. **Objective:** retrieve M01 calibration, waveform, lead labels, and coarse axis without reteaching.

**Case contract:** unseen normal real 12-lead, standard calibration, all labels present, clinician-reviewed normal axis and progression; no report text; geometry for cal pulse, P/QRS/T, I/aVF, V1/V6.

**Layout:** full 12-lead 8 columns, 60-second scavenger notebook 4; mobile stacked lead navigator. Timer is optional and untied to score.

**Verbatim flow:** Heading `Before geometry, find your bearings.` Body `Retrieve four Foundations habits on a new tracing. This sets support; it does not erase earlier learning.` Tasks: `Mark the calibration pulse.` `Mark one P, one QRS, and one T.` `Select lead I and aVF; record each net QRS as positive, negative, or not assessable.` `Select V1 and V6.` Controls `Check retrieval`; `Show one hint`; `Review the linked Foundations scene`.

Feedback: all correct `Your bearings are intact. We can use the tracing to build geometry.` P/QRS/T miss `Review the temporal sequence: P before QRS, T after QRS.` I/aVF miss `Use the net QRS area, not the tallest spike.` V1/V6 miss `Read the printed lead labels; waveform shape is not a safe locator yet.` Calibration miss `Find the square step before measuring the grid.` Transition `The same beat looks different across these leads. The next scene asks why.`

**Evidence:** retrieval vector stored separately; it changes `full`, `standard`, or `compressed` scaffolding. No M02 mastery. **Connections:** incoming M01.S2/S8/S9; outgoing S1.

**Tangent:** “Can I skip if I know this?” → `On this tracing — You have completed [n] of four retrieval actions. General connection — A placement check can reduce repetition, but each production objective still needs unseen evidence. Where we paused — You were locating [target].` Return `Return to M02.S0 · Locate [target]`.

## M02.S1 — Why does one beat look different twelve times?

**Timing:** 4–6 minutes. **Objective:** establish viewpoint problem and predict that direction changes polarity/amplitude.

**Case contract:** teaching simulation plus M02.S0 real 12-lead; a single evolving cardiac vector with synchronized directed views; no territory/pathology claims.

**Layout:** real 12-lead fades to three exemplar leads (II, aVR, near-perpendicular aVL) around a heart. Mobile uses three vertically aligned tiles. Reduced motion uses three static vector frames.

**Exact script:** Heading `One event can look upright, downward, or small.` Tutor `Do not memorize these three shapes. Predict them from where each lead looks.` Prompt `The activation arrow points down and left. Which view should see the largest upward projection?` Learner rotates through three view arrows. Explanatory reveal: `A lead reports the portion of the electrical vector aligned with its positive direction.` Three labels: `Toward the positive direction → positive deflection`; `Away from the positive direction → negative deflection`; `Nearly perpendicular → small or biphasic net deflection`.

Checkpoint `Complete the sentence: “The waveform changes across leads because …”` Full semantic answer must include one event plus different directed views. Correct `Yes. You explained difference without inventing twelve separate events.` Partial `You have “different views.” Add that the leads report the same evolving electrical event.` Incorrect `Return to the same-event model from Foundations: the heart does not restart for each lead.`

Transition `To make a directed view, separate the sensor on the skin from the lead the ECG calculates.`

**Evidence:** explanation; three direction predictions. **Tangent:** “Is a negative QRS always abnormal?” → `On this tracing — aVR is negative because the net vector points away from its positive direction. General connection — Negative can be expected from lead geometry; abnormality depends on the lead, waveform, and pattern. Where we paused — You were predicting polarity from viewpoint.` Return `Return to M02.S1 · Predict polarity`.

## M02.S2 — Electrodes sense; leads compare

**Timing:** 6–8 minutes. **Objective:** distinguish physical electrodes, reference, lead direction, and display orientation.

**Case contract:** interactive body schematic, no patient tracing required; teaching simulation labeled as such. Electrode positions RA, LA, LL, RL; Wilson central terminal concept is preview-only for chest leads.

**Layout:** torso 6 columns, build-a-lead board 6. Mobile torso first, then equations in plain language. Drag alternative: select electrode card then body target.

**Verbatim sequence:**

1. Heading `An electrode is a sensor. A lead is a directed comparison.`
2. Cards: `Electrode — a physical sensor on the body`; `Lead — a calculated voltage view with a positive direction`; `Ground/reference support — helps acquisition; it is not a displayed lead by itself.`
3. Prompt `Place RA, LA, LL, and RL electrodes on the limb diagram.` Accessible targets `patient’s right arm`, `patient’s left arm`, `patient’s left leg`, `patient’s right leg`. Screen-orientation note `The patient’s right appears on your left when you face the diagram.`
4. Build lead I: `Lead I compares left arm with right arm and points toward the left arm.` Plain equation `Lead I = LA − RA.` Prompt `Choose the positive electrode.` Correct LA `Yes. Lead I’s positive direction points toward LA.` RA `That reverses lead I. Follow the arrow toward the positive pole.`
5. Build II `Lead II = LL − RA`; build III `Lead III = LL − LA`.
6. Check `Which statement is accurate?` Correct `Ten electrodes are used to calculate twelve standard leads.` Feedback `Yes. A lead is not a one-to-one synonym for an electrode.` Distractors `Twelve electrodes create twelve leads`; `Each electrode records only one chamber`. Feedback `Count physical sensors separately from calculated views.`
7. Clinical bridge `A misplaced or reversed electrode changes the calculated view and can imitate an abnormal pattern. Verify acquisition before assigning a new diagnosis.`

**Feedback:** wrong body side `Use the patient’s perspective, not the screen’s.` RL as a displayed lead `RL supports acquisition but is not one of the standard displayed leads.` Completing by trial without correct final placement gets action credit but requires equivalent unlabeled torso.

**Equivalent retry:** randomized torso orientation; place four electrodes and rebuild one randomly chosen bipolar lead. **Evidence:** electrode placement, positive pole, lead equation in words. **Connections:** incoming S1; outgoing S3/S5/S13.

**Tangent:** “Why are there twelve leads but ten electrodes?” → `On this tracing — The displayed twelve views are calculated from ten physical electrodes. General connection — Four limb electrodes support six frontal leads, while six chest electrodes form six precordial leads relative to a composite reference. Where we paused — You were building lead [I/II/III].` Return `Return to M02.S2 · Build lead [lead]`.

## M02.S3 — Projection turns direction into waveform

**Timing:** 7–9 minutes. **Objective:** use qualitative vector projection to predict polarity and magnitude; optional math tangent.

**Case contract:** teaching simulation with adjustable vector and lead direction; amplitude is normalized, not diagnostic; exact equation optional `projection = |vector| cos θ`; no claims from real case.

**Layout:** vector canvas 7 columns, live waveform and prediction controls 5. Mobile uses angle slider and three snapshot buttons `Toward`, `Perpendicular`, `Away`. Screen-reader table gives angle and normalized projection.

**Exact script:** Heading `A lead records the projection along its axis.` Body `Ask two questions: Is the wave moving toward or away from the positive direction? How parallel is it to that direction?` Interaction prompt `Set the angle, predict the waveform, then reveal.` Choices `Large positive`; `Small or biphasic`; `Large negative`.

Angles/tasks: 0–20° → large positive; 70–110° → small/isoelectric; 160–200° → large negative; 40–60° → moderate positive transfer. Exact correct feedback: `Yes. At [angle]°, the vector is [nearly parallel/nearly perpendicular/opposed], so the net projection is [description].` Sign-correct/magnitude-wrong: `You have the direction right. Now use how parallel the vectors are to judge size.` Magnitude-right/sign-wrong: `The size fits, but the sign is reversed. Follow the wave toward or away from the positive pole.`

Optional `Show the math` copy: `If you want the formal model, projection equals vector magnitude × cos(angle). The course never requires trigonometry; the visual relationship is the learning target.` Accessible table includes cos rounded to two decimals. Hide control `Return to the visual model`.

Mechanism check prompt `Why can a large cardiac vector look small in one lead?` Correct `It may be nearly perpendicular to that lead.` Feedback `Yes. A small deflection does not necessarily mean a small cardiac event.`

Equivalent transfer uses a rotated lead rather than moved cardiac vector. **Evidence:** four predictions plus mechanism explanation. **Connections:** axis S9–S10, R progression S11, M5 terminal forces, M8 reciprocal patterns.

**Tangent:** “Can you explain the dot product?” Tutor may give formula and geometric explanation; exact return `Return to M02.S3 · Predict the [angle]° projection`.

## M02.S4 — Moving vectors create P, QRS, ST, and T shapes

**Timing:** 6–8 minutes. **Objective:** extend static projection to evolving activation/recovery without oversimplifying every waveform to one arrow.

**Case contract:** teaching simulation; three time-varying vector loops; explicitly conceptual, not a diagnostic vectorcardiogram; paired real normal lead II/aVR morphology only after prediction.

**Layout:** timeline 12 columns; below, vector loop 6 and two live leads 6. Mobile uses five numbered frames.

**Exact copy:** Heading `The heart’s direction changes during each beat.` Body `A real waveform is not one frozen arrow. As activation spreads, the net vector changes in direction and size; the lead draws that history over time.` Frames: `1 Atrial activation begins`; `2 Atrial activation spreads`; `3 Ventricular activation crosses the septum`; `4 Ventricular mass activates`; `5 Ventricles recover`.

Prompt per frame `Predict whether lead II moves mainly up, down, or near baseline at this moment.` Feedback names projection only. Key caution: `This animation builds intuition. It does not claim that one arrow explains every notch, conduction pattern, or repolarization change.`

Checkpoint `Why can one QRS contain both upward and downward deflections?` Correct `The net activation direction changes during the QRS.` Feedback `Yes. A lead records a changing projection over time.` Wrong `Do not treat the QRS as one stationary vector; replay the numbered frames.`

Transfer: paired real II/aVR, prompt `Use the overall direction to explain why the dominant complexes point oppositely.` Correct `The dominant activation moves toward II and away from aVR.`

**Evidence:** sequential predictions, causal explanation. **Connections:** M01.S1/S7; outgoing limb/chest maps, M5 conduction morphology, M7 secondary recovery. **Tangent:** “Why can T point the same direction if repolarization is opposite?” → bounded general explanation that both direction of recovery and sign of repolarization contribute, with `M7 builds this carefully`; return exact.

## M02.S5 — Build the bipolar limb-lead triangle

**Timing:** 7–9 minutes. **Objective:** I/II/III orientation, Einthoven relationship as internal consistency, patient-right display awareness.

**Case contract:** simulated torso and one real clean limb-lead set; equations grounded; lead reversal example separate and labeled teaching comparison.

**Layout:** torso triangle left, live leads right; mobile sequential build. Touch uses tap endpoints.

**Verbatim flow:** Heading `Three bipolar leads form a frontal triangle.` Body `Lead I points toward LA. Lead II points toward LL from RA. Lead III points toward LL from LA.` Prompt `Draw each positive direction on the patient.` Correct after all `Yes. The three arrows now form Einthoven’s triangle.`

Internal consistency reveal: `At the same instant, lead II is approximately lead I plus lead III. Use this as a conceptual consistency check, not hand arithmetic on every ECG.` Prompt with normalized numbers `If I = +0.6 and III = +0.4, what should II be approximately?` Correct `+1.0` → `Yes. +0.6 + +0.4 ≈ +1.0.` Incorrect `Add signed values; do not add waveform heights from different moments.`

Reversal preview: heading `What changes if RA and LA are swapped?` Copy `Lead I reverses direction, and other limb-lead relationships change. Chest leads are not physically swapped by this limb reversal.` Interaction toggles electrodes; learner selects changed leads. Feedback exact: `Good. This is an acquisition hypothesis, not a pathology diagnosis. M02.S13 tests the full clue pattern.`

Equivalent transfer: unlabeled triangle rotated; assign I/II/III by positive pole. **Evidence:** geometry, signed consistency, reversal hypothesis. **Connections:** S2/S3; S6 hexaxial; S13 placement.

## M02.S6 — Add aVR, aVL, and aVF: the hexaxial plane

**Timing:** 7–9 minutes. **Objective:** augmented lead directions, six-axis wheel, neighboring and opposite directions.

**Case contract:** simulation plus real limb leads; standard angles declared: I 0°, II +60°, III +120°, aVF +90°, aVL −30°, aVR −150°; convention shown with positive angles downward on patient’s left; no axis pathology.

**Layout:** assemble-wheel center, lead cards perimeter. Mobile wheel remains 320 px minimum or uses accessible list by angle.

**Exact copy:** Heading `Six frontal views complete the compass.` Body `The augmented leads use one limb electrode as the positive view against a combined reference from the other limbs.` Cards `aVR — toward the right arm`; `aVL — toward the left arm`; `aVF — toward the feet`.

Prompt `Place all six leads on the hexaxial wheel.` Correct `Yes. Neighboring directions are 30° apart once bipolar and augmented leads are combined.` Wrong/opposite `That position is the opposite of [lead]. Follow [lead] toward its positive pole.`

Neighbor task `Select the two immediate neighbors of lead II.` Correct `aVF and I` → `Yes. aVF (+90°) and I (0°) border II (+60°) on the wheel.` Opposite task `Which displayed standard lead lies closest to the direction opposite aVL?` Correct `Lead III` with feedback `Yes. The exact opposite of aVL at −30° is +150°. Lead III at +120° is the closest displayed standard lead, not an exact 180° pair. Use the drawn axes, not a memorized territory slogan.` A second canvas task asks the learner to draw the exact +150° opposite vector rather than select a named lead.

Clinical bridge `Neighboring leads often show related regional changes; opposite directions can show reciprocal projections. A coherent pattern still requires morphology and context.`

Transfer: learner clicks any lead and states positive body direction and nearest neighbors. **Evidence:** six placements, two neighbor/opposite tasks. **Connections:** M02.S7–S10, M8 territories.

## M02.S7 — Place V1–V6 on the chest

**Timing:** 8–10 minutes. **Objective:** precordial placement landmarks and horizontal-plane order; no unsafe landmark shortcuts.

**Case contract:** anatomically reviewed torso illustration with inclusive body representation; targets: V1 fourth intercostal space right sternal border, V2 fourth left sternal border, V4 fifth intercostal space midclavicular line, V3 midway V2–V4, V5 same horizontal level as V4 anterior axillary line, V6 same level midaxillary line. V3 placed after V2/V4. This is education, not a substitute for supervised placement.

**Layout:** large torso 7 columns, instruction/landmark checklist 5. Mobile tap-to-place with zoom. Keyboard navigates anatomical grid landmarks; all visuals have text alternatives.

**Exact opening:** Heading `Chest leads map the horizontal plane.` Safety copy `Learn the landmarks here, then practise placement with supervised clinical equipment. Respect privacy, consent, and local procedure.`

Placement prompts and exact correct feedback:

- `Place V1: fourth intercostal space at the right sternal border.` → `V1 placed at the patient’s right sternal border.`
- `Place V2: fourth intercostal space at the left sternal border.` → `V2 mirrors V1 across the sternum.`
- `Place V4: fifth intercostal space at the midclavicular line.` → `V4 establishes the horizontal level used by V5 and V6.`
- `Place V3 midway between V2 and V4.` → `V3 belongs between those established landmarks.`
- `Place V5 at the same horizontal level as V4, at the anterior axillary line.`
- `Place V6 at the same horizontal level as V4 and V5, at the midaxillary line.`

Branches: V1/V2 too high `High V1/V2 placement can alter morphology. Count to the fourth intercostal space rather than estimating from the clavicle.` V4 too high/low `Recheck the fifth intercostal space and midclavicular line.` V5/V6 diagonal `Keep V4, V5, and V6 on the same horizontal level.` V3 before anchors `Place V2 and V4 first; V3 is defined between them.` Screen/patient side `Use the patient’s right and left.`

Sequence check `Put the reliable placement sequence in order.` Correct order V1, V2, V4, V3, V5, V6; feedback `Yes. Establish the fixed landmarks before the between-point and lateral leads.`

Equivalent retry uses mirrored clinician perspective and text-only landmark form. **Evidence:** all positions, sequence, side. **Connections:** S2 electrodes; S8 horizontal plane; S11 progression; S13 placement errors; M5 BBB anchors.

## M02.S8 — Horizontal-plane viewpoint and the normal precordial sweep

**Timing:** 6–8 minutes. **Objective:** connect physical V1–V6 placement to changing viewpoint and normal morphology without diagnosing variants.

**Case contract:** simulated horizontal vector and clinician-reviewed normal real V1–V6; R/S ground truth; no coronary territory labels yet except descriptive `septal/anterior/lateral view` as localization vocabulary reviewed.

**Layout:** axial torso slice 6 columns; V1–V6 wave tiles 6. Mobile slider moves one lead at a time.

**Exact copy:** Heading `The chest leads move from right/anterior to left/lateral.` Body `As the positive viewpoint travels from V1 to V6, the normal ventricular projection usually shifts from a dominant S toward a dominant R.` Interaction `Move the viewing electrode from V1 to V6.` Captions: `V1: right/anterior view`; `V2: anterior/septal transition view`; `V3–V4: anterior views and common R/S transition`; `V5–V6: left/lateral views`.

Caution exact: `These labels describe viewpoints, not a diagnosis or a guaranteed coronary artery.` Check `Why does R commonly grow across V1–V6?` Correct `The positive viewpoint moves toward the dominant left-ventricular activation direction.` Feedback `Yes. Changing projection explains the general trend.` Incorrect `Use viewpoint and projection, not “the heart gets more electrical.”`

Transfer asks learner to order scrambled V1–V6 by label and predict dominant R/S at anchors V1/V6. **Evidence:** order, anchor predictions, explanation. **Connections:** S7, S11, M5, M8.

## M02.S9 — Contiguous and opposing views

**Timing:** 8–10 minutes. **Objective:** group anatomically adjacent lead views and distinguish localization from diagnosis.

**Case contract:** interactive body/lead map, one normal 12-lead and neutral highlighted waveform feature; no acute change; groups reviewed: inferior II/III/aVF; high lateral I/aVL; lateral V5/V6; septal V1/V2; anterior V3/V4, with overlap explicitly shown. Opposite relationships are approximate/view-based, not rigid one-to-one disease rules.

**Layout:** body map 5, 12-lead 7. Mobile chooses region then highlights tiles. Non-color patterns and labels accompany region shading.

**Exact script:** Heading `A pattern gains meaning when its views form a coherent neighborhood.` Body `Contiguous leads look at adjacent regions. A territory name is a localization hypothesis—not a disease label and not proof of one culprit vessel.`

Map buttons and exact labels: `Inferior views — II, III, aVF`; `High lateral views — I, aVL`; `Lateral precordial views — V5, V6`; `Septal/right-anterior views — V1, V2`; `Anterior views — V3, V4`; note `Boundaries overlap; anatomy varies.`

Tasks:

1. `Select the inferior group.` Correct `II, III, and aVF are neighboring inferior frontal views.` Single lead selected `One changed lead is less coherent than a contiguous pattern. Complete the group.`
2. `Select the high-lateral group.` Correct `I and aVL form the high-lateral frontal pair.`
3. `Choose a roughly opposing frontal view to the inferior direction.` Correct accepted I/aVL group with copy `Yes. High-lateral views look broadly opposite the inferior direction; exact projections vary.`
4. `A neutral marker appears in V3 and V4. Describe location only.` Correct `Anterior precordial distribution` → `Yes. You localized without assigning a cause.` Diagnosis answer `That may be a later hypothesis, but the supported statement now is “anterior precordial distribution in V3–V4.”`

Equivalent transfer: highlight a benign calibration marker across lead tiles; learner names contiguous/noncontiguous distribution. **Evidence:** three maps, bounded description. **Connections:** M8 distribution/reciprocity, M7 ST/T distribution.

**Tangent:** “Which artery is each lead?” → `On this tracing — The selected leads form [distribution]. General connection — Lead territories help localize electrical changes, but coronary anatomy overlaps and varies; lead pattern alone does not guarantee one culprit artery. M8 combines distribution, morphology, reciprocity, dynamics, and context. Where we paused — You were naming the selected distribution.` Return exact.

## M02.S10 — Axis quadrants from real QRS polarity

**Timing:** 8–10 minutes. **Objective:** apply I/aVF quadrant method on real ECGs with net-area reasoning.

**Case contract:** simulation plus four real cases: normal, clear LAD, clear RAD, extreme/not assessable; readable I/aVF, grounded degrees, no lead reversal; target QRS regions; cause labels hidden.

**Layout:** quadrant card 4 columns, real leads/12-lead 8. Mobile displays I/aVF aligned, full ECG accessible. Keyboard polarity annotation `P` positive, `N` negative, `E` nearly equal.

**Exact opening:** `Axis starts with two net QRS decisions.` Rule table repeats M01 but adds extreme quadrant. Prompt sequence per case: `Shade the positive and negative QRS area in lead I.` `Choose net polarity.` Repeat aVF. `Choose the quadrant.`

Feedback: correct normal `I positive + aVF positive supports the normal quadrant.` clear left `I positive + aVF negative supports a leftward quadrant; lead II will refine the boundary.` right `I negative + aVF positive supports right-axis deviation.` extreme `I negative + aVF negative supports the extreme quadrant; verify acquisition and interpret in context.` Net-area error `Do not vote by R height alone. Compare total area above and below baseline across the QRS.` Nearly isoelectric `If positive and negative areas nearly cancel, mark “nearly isoelectric” and lower confidence.`

Equivalent retry two cases. Completion ≥2/2 transfer, correct lead evidence. **Connections:** M01.S9, S11 refinement.

## M02.S11 — Refine axis with lead II and the isoelectric lead

**Timing:** 9–11 minutes. **Objective:** resolve I+/aVF−, estimate degrees using perpendicular lead, compare machine axis and confidence.

**Case contract:** five real cases spanning −20°, −45°, +60°, +110°, and one near-boundary/ambiguous; grounded axis; I/II/aVF and all limb leads readable; clinician-reviewed; no fascicular cause label.

**Layout:** three-lead decision tree above, hexaxial wheel and six limb leads below. Mobile decision tree linearizes.

**Exact script:** Heading `Quadrant first; lead II and the most isoelectric lead refine it.` Decision copy: `If I is positive and aVF is negative, inspect lead II.` `Lead II positive → axis is leftward but may remain within the normal extension to about −30°.` `Lead II negative → definite left-axis deviation by this convention.`

Task A borderline prompt and feedback as above. Task B `Find the limb lead whose QRS is most nearly isoelectric.` Then `The axis lies roughly perpendicular to that lead. Choose the perpendicular direction consistent with the observed positive leads.` Correct `Yes. The polarity of neighboring leads selects the correct of the two perpendicular directions.` Wrong perpendicular `A perpendicular line has two directions 180° apart. Use a clearly positive lead to choose between them.`

Degree entry helper `Estimate to the nearest 15°. Do not imply precision beyond the visible morphology.` Tolerance ±15° for canonical, ±20° near boundary. Comparison card `Your estimate: [x]°. Machine value: [y]°. Difference: [d]°.` Agreement `These are reasonably aligned.` Disagreement `Recheck the most isoelectric lead and verify lead placement. Preserve uncertainty if morphology is borderline.`

Confidence prompt `How confident is the quadrant and approximate degree?` High allowed only readable/canonical; feedback calibrates.

Transfer: two unseen real ECGs, one borderline and one clear. **Evidence:** I/II/aVF, isoelectric lead, degree, confidence. **Connections:** M5 fascicular block/chamber forces, M9 synthesis.

**Tangent:** “Is −25° normal or left axis?” → `On this tracing — The supplied axis is [value]° with [lead II polarity]. General connection — Common adult conventions extend normal frontal QRS axis to about −30°, but boundaries and populations vary. Describe the degree and method rather than turning a border into false certainty. Where we paused — You were refining an I-positive/aVF-negative axis.` Return exact.

## M02.S12 — R-wave progression, transition, and normal rotation

**Timing:** 8–10 minutes. **Objective:** measure R/S trend, mark transition, recognize normal variation without infarction overcall.

**Case contract:** three reviewed real 12-leads: transition V3–V4, early transition, late transition/poor progression with no diagnostic claim; correct placement status when known; R/S amplitude geometry; source labels hidden.

**Layout:** V1–V6 tiles and R/S plot; full ECG available. Mobile one lead per swipe with persistent mini-plot. Keyboard selects lead and R/S peak points.

**Exact copy:** Heading `Progression is a trend, not one R-wave height.` Body `Across V1 to V6, R usually grows while S shrinks. Transition is the first lead where R becomes larger than S.` Prompt `Mark R peak and S nadir in each precordial lead.` Plot labels `R amplitude`; `S magnitude`; `R/S = 1 transition line`.

Branch copy: correct transition `Yes. [lead] is the first lead with R greater than S.` early transition `This tracing transitions earlier than the common V3–V4 range. Describe “early transition”; do not assign a cause here.` late `This tracing transitions later or not clearly by V4. Describe the observed progression and check placement/context before cause.` Poor progression called infarction `That diagnosis is not supported by progression alone. Record the lead-by-lead R/S pattern and seek placement, prior, and clinical evidence.` One isolated low R `Use the full V1–V6 trend; one amplitude is not progression.`

Variant comparison controls `Common transition`; `Early transition`; `Late/poor progression`; `Not assessable`. Equivalent transfer includes differing body habitus tag hidden from learner; no demographic normality claim unless reviewed.

Clinical bridge `Rotation, body habitus, placement, conduction, chamber forces, and prior infarction can alter progression. The ECG pattern is the observation; cause requires more evidence.`

**Evidence:** 12 points, transition, bounded category, transfer. **Connections:** M01.S8, M02.S7–S8, S13, M5/M8.

## M02.S13 — Acquisition errors and normal-variant laboratory

**Timing:** 10–13 minutes. **Objective:** distinguish `likely acquisition problem`, `plausible variation`, and `unexplained finding` without diagnosing from one clue.

**Case contract:** paired reviewed comparisons for RA/LA reversal, high V1/V2 placement, misplaced V4–V6 level, stable early/late transition variant, and one genuine unexplained morphology requiring later module. Pairs must be real pre/post placement when available; otherwise clearly labeled `Teaching simulation of electrode movement`. Prior comparison metadata explicit.

**Layout:** before/after ECG compare slider 8 columns; acquisition checklist 4. Mobile uses synchronized stacked panels, not overlaid traces.

**Exact opening:** Heading `Before pathology, ask whether the view itself changed.` Checklist: `Confirm patient identity and date`; `Check calibration and signal quality`; `Inspect limb-lead relationships`; `Inspect V1–V6 placement and progression`; `Compare a prior ECG when available`; `Describe what remains unexplained.`

Station 1 prompt `The limb pattern changes after RA and LA are swapped in this teaching comparison. Select the clues.` Reviewed clues shown only after answer. Correct summary `Possible right-arm/left-arm reversal; repeat or verify acquisition before assigning new axis or infarct claims.` Overclaim `Electrode reversal is a hypothesis until acquisition is checked.`

Station 2 `V1 and V2 were intentionally moved one intercostal space higher in this teaching comparison. Mark the morphology that changed.` Correct `High placement can alter anterior morphology. Record the concern and verify position.`

Station 3 `R progression is unusual but stable on a correctly acquired prior.` Correct option `Plausible stable variant; describe and compare, without inventing pathology.` Feedback `Yes. Stability and verified placement reduce—but do not eliminate—concern; context still matters.`

Station 4 `A new coherent abnormal pattern remains after acquisition checks.` Correct `Unexplained finding; route to the appropriate pathology module or clinical review.` Feedback `Yes. “Not an acquisition explanation” does not itself name the diagnosis.`

Deterministic labels: `Possible placement/reversal`; `Plausible stable variation`; `Finding needs pathology reasoning`; `Not assessable`. Every choice requires selected evidence and one next information step. Scoring rejects diagnosis-only answers.

Equivalent retry is a new pair. **Connections:** M8 mimics; all clinical cases. **Tangent:** “Should I repeat every unusual ECG?” → `On this tracing — [available acquisition evidence]. General connection — Repeating or verifying acquisition is most useful when placement error is plausible and the result would change interpretation; local clinical workflow and patient context govern real decisions. Where we paused — You were classifying the comparison.` Return exact.

## M02.S14 — Independent lead-map transfer

**Timing:** 12–16 minutes. **Objective:** integrate geometry, map, axis, progression, acquisition quality, delayed M01 retrieval, and cross-mode handoff.

**Case contract:** two unseen reviewed real ECGs. A clean normal/variant; B possible placement issue or clear non-acute axis deviation. No labels leaked. All lead/axis/progression/quality geometry and prior metadata complete.

**Layout:** Case 1 structured evidence map; Case 2 blank annotation canvas. Tutor silent until ask. Mobile provides named tool palette and stacked leads.

**Case 1 exact tasks:**

1. `Delayed retrieval: measure one QRS duration and state the calibration.`
2. `Locate and name three randomly selected leads.`
3. `For each, draw its positive viewing direction on the body map.`
4. `Select one contiguous group and describe its region without diagnosis.`
5. `Estimate frontal QRS axis: I, aVF, lead II if needed, most isoelectric lead, degree, confidence.`
6. `Mark V1–V6 transition and classify progression.`
7. `State whether acquisition is internally plausible and what you would verify.`

Case 2 prompt: `Annotate the tracing and deliver a three-sentence explanation: (1) lead geometry and axis, (2) precordial progression, (3) acquisition confidence and limits.`

Rubric: lead location 15%; viewing direction 15%; contiguity 10%; axis 25%; progression 20%; acquisition reasoning 10%; delayed QRS/calibration 5%. Required evidence marks. Full pass ≥80%, no reversed patient-side map, no definite pathology claim from placement/progression alone. Critical retry for axis reversal, electrode-side reversal, or false pathology with high confidence.

Feedback summary exact: `You can now turn the 12-lead page into a spatial model. Strongest subskill: [x]. Next retrieval target: [y].` Handoff controls:

- `Train lead locations and opposites`
- `Train axis with target, mimic, and normal cases`
- `Try an untimed localization quick-look`
- `Continue to Module 3: rate, sinus rhythm, pauses, and ectopy`

Cross-mode payload includes `objective_ids`, `weak_error_class`, `case_exclusions`, `return_to=M02.S14`, `scaffold_level`, and `review_after`.

**Tangent:** “Why do I need vectors if I can memorize territories?” → `On this tracing — The selected leads form [distribution], and their directions explain [visible polarity]. General connection — Memorized maps help retrieval; vectors explain polarity, axis, reciprocal directions, conduction morphology, and why a pattern changes when placement changes. Where we paused — You were writing the spatial explanation.` Return exact.

## M02 acceptance checklist

- [ ] All 15 scenes exist; the former eight-scene compression is not presented as the full module.
- [ ] Every lead/electrode/body-side label uses the patient’s perspective and has a text alternative.
- [ ] Projection predictions score sign and magnitude separately.
- [ ] Time-varying vectors are explicitly conceptual and do not overclaim a frozen-arrow model.
- [ ] Limb equations, standard angles, and placement landmarks receive clinical/content review.
- [ ] V1–V6 placement works with tap, keyboard, zoom, mobile, inclusive anatomy, privacy copy, and supervised-practice boundary.
- [ ] Contiguous groups are presented with overlap and without deterministic artery claims.
- [ ] Axis grading uses net QRS, I/aVF, lead II refinement, grounded degrees, and calibrated confidence.
- [ ] R progression uses R and S, first crossover, and a full trend; it never equates poor progression with infarction.
- [ ] Placement-error exemplars are paired/verified or labeled simulations; no synthetic difference is presented as a real patient repeat.
- [ ] Transfer cases have complete provenance, geometry, permitted claims, and no report-label leakage.
- [ ] M01 delayed retrieval and outgoing M03/M05/M08 links work with exact return.
- [ ] All critical errors receive a different equivalent case.
- [ ] Keyboard, touch, screen reader, reduced motion, 200% zoom, and mobile standard-layout reference pass.
- [ ] At least five novices and five clerkship learners complete observed usability sessions; lead-side reversals, task abandonment, and scroll traps are zero P0/P1 issues before pilot.

## M02 exact state-copy supplement

The strings below fill every standard state that is not already given more specifically in the scene body. A scene-specific string in the body wins over this supplement. `Hint 2` is shown only after another learner attempt and always before an equivalent retry.

| Scene | Tutor opening | Hint 1 | Hint 2 / coached contrast | Partial branch | Clinical bridge and exit transition |
|---|---|---|---|---|---|
| S0 | `Use the page as evidence. Find the labels and landmarks before you explain their geometry.` | `Start with printed labels and the calibration pulse; waveform shape comes second.` | `On this separate example, I will mark lead I and V1 once. Now return to the unseen tracing.` | `You found [items]. Add [missing item] so the spatial model starts from complete bearings.` | `Localization fails when orientation is wrong.` → `You are oriented. Now explain why the same event changes shape across leads.` |
| S1 | `Predict before I reveal. Toward, away, and perpendicular will do most of the work.` | `Follow the activation arrow relative to the lead’s positive arrow.` | `Compare lead II, which the arrow approaches, with aVR, which it leaves.` | `Your sign is right. Add whether the view is parallel enough to make the deflection large.` | `A downward waveform can be expected in one lead and concerning in another; viewpoint comes first.` → `Next, separate the physical sensor from the calculated lead.` |
| S2 | `Build each lead from the patient’s body. I will not correct left and right until you commit.` | `Face the patient in the diagram, then use the patient’s own right and left.` | `Watch me construct lead I on a different torso: positive LA, negative RA. Rebuild the assigned lead yourself.` | `The electrodes are placed correctly. Add the positive pole and directed comparison.` | `Verifying electrodes can prevent a manufactured axis or morphology claim.` → `You have built a lead. Now predict the waveform it records.` |
| S3 | `Choose polarity and size separately; one can be right while the other needs revision.` | `First decide toward or away. Then decide parallel or perpendicular.` | `At 90°, the projection nearly cancels. Use that anchor to judge the new angle.` | `Your polarity is correct, but the expected magnitude does not match the angle.` | `Small amplitude in one lead can reflect geometry rather than a small cardiac event.` → `A heartbeat changes direction over time; animate the projection next.` |
| S4 | `Advance one frame at a time and say what changed in the net direction.` | `Compare the arrow at this frame with the positive direction of the selected lead.` | `Replay the same frame in lead II and aVR; the event is shared while the projections oppose.` | `You predicted the final sign. Add how the direction changed during the waveform.` | `Changing activation sequence later explains conduction morphology and secondary recovery changes.` → `Now anchor these directions to the three bipolar limb leads.` |
| S5 | `Place the positive poles first; the lead names follow from those directions.` | `Lead I points to LA; both II and III point toward LL from different negative poles.` | `I will show the completed triangle for two seconds, then hide it and rotate the torso.` | `The triangle is correct. Recheck the signed addition before you call the set internally consistent.` | `Unexpected limb relationships can be an acquisition clue.` → `Add the augmented directions to turn the triangle into a six-axis compass.` |
| S6 | `Use the angle labels as a compass, not as a list to memorize.` | `Begin with I at 0° and aVF at +90°, then place the directions between them.` | `Overlay the three bipolar leads first; now insert the augmented leads in the 30° gaps.` | `You placed [n] of six directions. Recheck the positive pole of [lead].` | `Neighboring and opposing projections become distribution and reciprocity evidence later.` → `Leave the frontal plane and place the six chest electrodes.` |
| S7 | `Place fixed landmarks before between-points. Use the patient’s side and preserve dignity in real practice.` | `Find V1 and V2 at the fourth intercostal space, then establish V4 before V3.` | `On a separate torso, I will mark the fourth spaces and V4’s horizontal level. Complete the new torso yourself.` | `The lead order is right. Correct the anatomical level of [lead].` | `High or misplaced chest electrodes can change morphology enough to redirect interpretation.` → `Now connect those body positions to the horizontal-plane waveforms.` |
| S8 | `Move one viewpoint at a time and predict the R/S balance before revealing the tile.` | `Ask whether the positive electrode is moving toward the dominant left-ventricular activation.` | `Compare only the anchors: V1 commonly has dominant S, while V6 commonly has dominant R.` | `Your endpoint predictions are correct. Add the projection reason for the trend.` | `V1 and V6 later anchor bundle-branch morphology; the same sweep localizes precordial patterns.` → `Combine frontal and horizontal views into contiguous groups.` |
| S9 | `Select a geographic group before any disease label. The lead distribution is the evidence.` | `Look for adjacent directions or neighboring chest positions, not similar-looking waveforms.` | `I will shade the inferior body region on a separate map. Match its directed frontal views on the assessment map.` | `You identified part of the group. Add the remaining contiguous lead and describe location only.` | `Regional interpretation is stronger when readable contiguous leads form a coherent pattern.` → `Use the frontal map to classify QRS axis on real cases.` |
| S10 | `Shade net positive and negative QRS area before choosing an axis quadrant.` | `Compare total QRS area above and below baseline; ignore the height contest between R and S.` | `On a separate QRS, I will shade positive and negative lobes. Repeat the method on the unseen lead.` | `Lead [I/aVF] is correct. Recalculate net polarity in the other lead.` | `Axis is a measured activation direction, not a standalone diagnosis.` → `Refine the quadrant with lead II and the most isoelectric lead.` |
| S11 | `State the quadrant first, then earn any degree estimate from visible limb-lead evidence.` | `If I is positive and aVF negative, let lead II decide whether the axis is beyond about −30°.` | `Find the most isoelectric limb lead; the axis is roughly perpendicular, with two candidate directions.` | `Your quadrant is supported. Add the isoelectric lead or lower the precision of the degree estimate.` | `Borderline axis language prevents an arbitrary threshold from becoming false certainty.` → `Return to the horizontal plane and measure the full R/S trend.` |
| S12 | `Mark both R and S in every precordial lead; progression is a relationship across leads.` | `Find the first lead where R exceeds S, not the lead with the largest R.` | `Plot R and S for a different tracing, then apply the same first-crossover rule here.` | `Your trend description is sound. Recheck which lead crosses first.` | `Unusual progression can reflect placement, variation, activation, chamber forces, or prior injury; one pattern does not choose the cause.` → `Test acquisition and normal-variation hypotheses before pathology.` |
| S13 | `Treat placement as a hypothesis that needs a clue pattern and verification.` | `Compare what changed, which leads changed together, and whether a verified prior is stable.` | `On a labeled simulation, move one electrode and observe the constrained lead changes; now classify the unseen pair.` | `Your category is reasonable. Add the acquisition clue or the next verification step.` | `Verification can prevent both missed findings and unnecessary alarm.` → `Integrate lead geometry, axis, progression, and acquisition on unseen ECGs.` |
| S14 | `I will stay quiet until you submit. Attach every spatial claim to a lead, vector, or measured pattern.` | `Open the evidence checklist; it names domains but does not reveal this case.` | `Review one completed example from S13, then return to a different transfer case.` | `Your explanation covers [domains]. Add [missing domain] or mark it not assessable.` | `A spatially grounded read gives later morphology and ischemia claims an auditable foundation.` → `Module 2 is complete. Continue to rhythm logic or enter targeted lead/axis practice.` |

### M02 tangent-and-return inventory

| Scene | Learner tangent | Exact tutor answer and return control |
|---|---|---|
| S0 | `Why does aVR look so strange?` | `On this tracing — aVR’s dominant waveform points [grounded direction]. General connection — aVR views from the right shoulder, broadly opposite the usual down-left activation direction, so several normal waveforms often appear negative. Where we paused — You were locating lead [target].` `Return to M02.S0 · Locate [target]` |
| S1 | `Is an upward wave always good?` | `On this tracing — The selected waveform is positive because the vector points toward this lead. General connection — Upward and downward are geometric descriptions, not “good” and “bad.” Meaning depends on the waveform, lead, distribution, and context. Where we paused — You were predicting [lead] polarity.` `Return to M02.S1 · Predict [lead] polarity` |
| S2 | `What does the right-leg electrode do?` | `On this tracing — RL is not displayed as its own standard lead. General connection — It supports stable acquisition and noise rejection as the system’s ground/reference electrode. Where we paused — You were placing [electrode].` `Return to M02.S2 · Place [electrode]` |
| S3 | `Do I need trigonometry for axis?` | `On this tracing — The visual prediction needs only toward, away, and perpendicular. General connection — Cosine formalizes the same projection, but the assessed skill is geometric reasoning. Where we paused — You were predicting the [angle]° projection.` `Return to M02.S3 · Predict the [angle]° projection` |
| S4 | `Is a vector loop the same as vectorcardiography?` | `On this tracing — The animation is a simplified teaching loop. General connection — Clinical vectorcardiography is a formal representation of time-varying cardiac vectors; this scene uses only its core intuition and does not reproduce a diagnostic system. Where we paused — You were on frame [n].` `Return to M02.S4 · Frame [n] prediction` |
| S5 | `Is Einthoven’s law exact?` | `On this tracing — The displayed values are a teaching consistency example. General connection — Simultaneously measured limb leads should satisfy II = I + III within acquisition and display limits; do not add unrelated peaks from different moments. Where we paused — You were checking signed consistency.` `Return to M02.S5 · Check signed consistency` |
| S6 | `Why are the augmented leads called augmented?` | `On this tracing — aVR, aVL, and aVF fill frontal directions between the bipolar leads. General connection — Their historical construction increases the recorded amplitude relative to the original unipolar method; the learning target here is their positive direction. Where we paused — You were placing [lead].` `Return to M02.S6 · Place [lead]` |
| S7 | `Where do I place leads on someone with breast tissue?` | `On this tracing — This is an anatomical teaching diagram, not a real patient. General connection — Use intercostal and line landmarks, preserve V4–V6’s horizontal level, communicate respectfully, obtain consent, and follow supervised local procedure rather than placing electrodes on breast tissue by guesswork. Where we paused — You were placing [lead].` `Return to M02.S7 · Place [lead]` |
| S8 | `Does V1 see the right ventricle?` | `On this tracing — V1 is the right/anterior precordial viewpoint. General connection — It is influenced by septal and right-sided/anterior forces, but no lead records one chamber in isolation. Where we paused — You were predicting the V1 R/S balance.` `Return to M02.S8 · Predict V1` |
| S9 | `Are V1 and V2 septal or anterior?` | `On this tracing — The selected group is [grounded group]. General connection — Territory labels overlap and conventions vary; describe the exact leads first, then use a reviewed regional term. Where we paused — You were selecting [group].` `Return to M02.S9 · Select [group]` |
| S10 | `What if the QRS is equally positive and negative?` | `On this tracing — [lead] is nearly isoelectric. General connection — Mark it as near-balanced and lower polarity confidence; in the full method it can help estimate a perpendicular axis. Where we paused — You were shading net QRS area.` `Return to M02.S10 · Shade [lead] QRS` |
| S11 | `Why does the machine axis differ from mine?` | `On this tracing — Your estimate is [x]° and the packet value is [y]°. General connection — Boundary selection, near-isoelectric morphology, noise, beat averaging, and lead placement can create differences. Recheck the trace and report appropriate precision. Where we paused — You were comparing axis estimates.` `Return to M02.S11 · Compare axis estimates` |
| S12 | `Does poor R progression mean old anterior MI?` | `On this tracing — The observed pattern is [grounded R/S description]. This scene does not establish a cause. General connection — Placement, rotation, body habitus, conduction, chamber forces, normal variation, and prior infarction can all affect progression. M7 and M9 discriminate those possibilities. Where we paused — You were marking the transition.` `Return to M02.S12 · Mark the transition` |
| S13 | `Can I diagnose lead reversal from aVR alone?` | `On this tracing — [available clue set]. General connection — One unusual lead is not enough; use a coherent limb-lead pattern, chest-lead preservation, identity/prior checks, and acquisition verification. Where we paused — You were classifying the comparison.` `Return to M02.S13 · Classify the comparison` |
| S14 | `How much axis precision should I report?` | `On this tracing — The morphology supports approximately [grounded range]. General connection — Report a quadrant or rounded degree that the visible evidence and source resolution can defend; do not turn a borderline vector into single-degree certainty. Where we paused — You were writing the spatial explanation.` `Return to M02.S14 · Spatial explanation` |

### M02 visual, input-equivalence, and scoring matrix

`D`, `L`, and `M` below refine the shared responsive contract. Static scenes still declare visual states so screenshots and screen-reader output can be regression-tested. Pointer coordinates are stored in source-signal coordinates, never screenshot pixels.

| Scene | Desktop / laptop / mobile and visual states | Keyboard and touch-equivalent mechanics | Deterministic pass / equivalent retry |
|---|---|---|---|
| S0 | D: 12-lead 8/12 + notebook 4/12; L: 7/10 + 3/10; M: lead stack then tasks. V0 unmarked; V1 learner marks; V2 feedback outlines. | Tab to named task; Enter activates pointer; arrows nudge; touch tap-to-mark with `Undo last mark`. | 4/4 retrieval actions; corrected errors set scaffold only. No mastery/retry gate. |
| S1 | D/L three lead cards orbit a central vector; M cards stack. F0 real shapes; F1 common event; F2 view arrows; F3 learner prediction; F4 projection reveal. | Arrow keys rotate selected view by 10°; buttons `Toward`, `Perpendicular`, `Away`; touch drag or tap a preset. | 3/3 sign predictions, ≥2/3 magnitude predictions, same-event explanation; retry rotates both event and lead on new seed. |
| S2 | D torso 6/12 + lead board 6/12; L 5/10 + 5/10; M torso then board. V0 sensors bank; V1 placements; V2 lead arrow; V3 comparison; V4 randomized torso. | Select electrode then target; Space places; arrow keys move target focus; touch tap card/tap body. Drag optional. | All four electrodes, positive pole, and one lead equation; equivalent retry changes orientation and requested lead. |
| S3 | D vector 7/12 + waveform 5/12; L 6/10 + 4/10; M vector then waveform. F0 lead axis; F1 angle set; F2 prediction; F3 waveform; F4 qualitative projection bar. | Slider arrows 1°, Shift+arrow 10°; preset buttons; touch slider or presets. | 4/4 sign, ≥3/4 magnitude, mechanism; retry changes vector magnitude and rotates lead so screen-position memory fails. |
| S4 | D/L 12-column timeline with 6/6 loop/leads below; M five vertical frames. F0–F5 exactly as scene script; no autoplay advance. | Left/Right frames; Space play/pause; touch `Previous frame`/`Next frame`; scrub optional. | ≥4/5 directional predictions + changing-vector explanation + II/aVR transfer; retry uses different initial direction. |
| S5 | D torso 6 + leads 6; L 5 + 5; M triangle then leads. F0 poles; F1 I; F2 II; F3 III; F4 sum relation; F5 reversal simulation. | Select start/end electrodes; Enter draws; signed values via radio + numeric field; touch two taps. | 3/3 directions, signed equation, reversal changed-lead set, rotated unlabeled triangle; retry randomizes numeric signs and torso rotation. |
| S6 | D wheel ≥420 px; L ≥360; M ≥320 or ordered list. F0 I/aVF anchors; F1 bipolar; F2 augmented; F3 full compass; F4 neighbor highlight. | Six lead buttons then six angle slots; Space places; list alternative pairs lead/angle; touch tap/tap. | 6/6 final placement after correction, 2/2 neighbor/opposite transfer; retry rotates visual wheel while degrees remain labeled. |
| S7 | D torso 7 + checklist 5; L 6 + 4; M zoomable torso. F0 landmarks; F1 V1/V2; F2 V4; F3 V3; F4 V5/V6; F5 privacy/supervision card. | Anatomical landmark grid; lead button then landmark; zoom controls; touch tap with magnified confirmation. | All six within reviewed tolerance, sequence correct, patient side correct; retry mirrored clinician-view torso. |
| S8 | D axial slice 6 + tiles 6; L 5 + 5; M slice then one lead/tile. F0 V1; F1 V2; F2 V3/V4; F3 V5/V6; F4 anchor compare. | Lead-step buttons or Left/Right; prediction radios; touch swipe is optional and buttons remain. | V1/V6 anchor predictions, six-lead order, causal explanation; retry reverses screen order but retains printed lead labels. |
| S9 | D body 5 + ECG 7; L 4 + 6; M map then lead tiles. V0 uncolored; V1 learner selection patterns; V2 named group; V3 approximate opposition. | Region buttons and lead checkboxes; no color-only selection; touch same controls. | Inferior/high-lateral groups exact, approximate opposite accepted set, location-only transfer; retry uses a different neutral feature/distribution. |
| S10 | D rule 4 + aligned leads 8; L 3 + 7; M I/aVF then full reference. V0 trace; V1 area marks; V2 net sign; V3 quadrant. | `Positive`, `Negative`, `Nearly equal`; area marking via baseline-separated lasso or interval buttons; touch tap regions. | Net sign and quadrant on four teaching plus 2/2 unseen; any lucky quadrant without correct sign is partial; retry new degree/case. |
| S11 | D tree full width then wheel 6/leads 6; L same 5/5; M linear tree then list. V0 quadrant; V1 lead II; V2 isoelectric; V3 perpendiculars; V4 degree compare. | Decision buttons; choose lead by key; degree slider arrows 5°; touch stepper. | Two transfers: quadrant, II refinement, isoelectric lead, degree within tolerance, confidence calibrated; retry new borderline/clear pair. |
| S12 | D tiles/plot 8 + notebook 4; L 7 + 3; M one tile + persistent mini-plot. V0 raw; V1 R/S marks; V2 plot; V3 crossover; V4 category. | Lead list; `Mark R`, `Mark S`; arrows nudge; touch tap after selecting marker type. | ≥10/12 amplitude marks within broad morphology ROI, correct first crossover/category, bounded transfer; retry different transition category. |
| S13 | D compare 8 + checklist 4; L 7 + 3; M synchronized stack. V0 A; V1 B; V2 difference map after commit; V3 category/evidence. | Toggle A/B and difference; lead navigation; touch buttons rather than scrub-only slider. | 4/4 stations corrected plus evidence and next datum; one new paired transfer without diagnosis overcall; retry different error/variant family. |
| S14 | D structured map then blank canvas, ECG 8/notebook 4; L 7/3; M lead stack then evidence clauses. V0 case; V1 marks; V2 synthesis; V3 audit; V4 handoff. | All drawing tools have select-lead/select-feature forms; clauses attached through accessible dropdown; touch tap/tap. | Weighted ≥80%, no critical spatial reversal/false pathology, all required evidence; retry new case targeted to failed dimension. |

---

# Module 03 — Rhythm logic: sinus, irregularity, pauses, and ectopy

## M03.0 Module contract and expanded sequence

**Module card title:** `3 · Rhythm logic: sinus, irregularity, pauses, and ectopy`  
**Card description:** `Use a reproducible rhythm ladder, choose rate methods for real strips, distinguish sinus variants, and reason from timing and morphology through PACs, PVCs, pauses, escape beats, patterned ectopy, and artifact.`  
**Duration label:** `Usually 70–90 minutes · five resumable chapters`  
**Prerequisite label:** `Recommended: Module 1 rhythm/interval readiness and Module 2 lead orientation`  
**Outcome:** `You will produce an evidence-based rhythm description; distinguish early from late events; identify common atrial and ventricular premature-beat patterns; describe pauses and escape without exceeding the evidence; recognize patterned ectopy and artifact; and state what the ECG cannot tell about symptoms or stability.`

**Launch heading:** `Build separate atrial and ventricular timelines before naming the rhythm.`  
**Launch body:** `Rate is only one clue. You will march P waves and QRS complexes, compare their timing and relationship, distinguish premature from late events, and preserve uncertainty when the signal cannot support a narrow label.`  
**Launch controls:** `Begin with P–QRS retrieval`; `Resume at [scene title]`; `Show the rhythm placement check`.  
**Placement-check disclosure:** `A placement check may reduce scaffolding. It never substitutes for independent evidence on unseen rhythm strips.`

Expanded 16-scene sequence:

- Chapter A, `Build the rhythm ladder`: M03.S0–S3
- Chapter B, `Keep sinus separate from speed`: M03.S4–S5
- Chapter C, `Reason from timing and origin`: M03.S6–S10
- Chapter D, `Patterns, mimics, and mixed practice`: M03.S11–S13
- Chapter E, `Clinical transfer and independent test`: M03.S14–S15

## M03.S0 — Retrieval: the P–QRS relationship

**Timing:** 4–6 minutes. **Objective:** retrieve M01/M02 rate, P–QRS, QRS width, lead II/aVR orientation.

**Case contract:** unseen real sinus strip and one non-sinus/ambiguous strip; II/aVR, ≥8 s; P/R geometry; QRS duration; no labels.

**Layout:** two aligned strips 8 columns, retrieval cards 4. Mobile one strip at a time.

**Exact tasks:** Heading `Rhythm starts with evidence, not a rhythm name.` Body `Retrieve the observations that every rhythm interpretation needs.` Prompts `Mark four R peaks.` `Mark visible P waves.` `State R–R regularity.` `Describe the P–QRS relationship.` `Measure one QRS.` `Which lead gives the clearest atrial evidence here, and what does aVR add?`

Feedback all correct `You recovered the timing and relationship evidence. Now organize it into a reusable ladder.` Rate-only label `A rate is one dimension. Add atrial activity, P–QRS relationship, and QRS width before naming a rhythm.` Ambiguous P overclaim `The signal does not support a confident P-wave claim; preserve “not assessable.”`

No mastery assigned. Incoming M01.S4–S6/M02 orientation; outgoing S1.

## M03.S1 — Build the rhythm ladder

**Timing:** 6–8 minutes. **Objective:** ordered rhythm analysis and explicit clinical-state boundary.

**Case contract:** neutral clean strip; shuffled cards; no diagnosis. Stability vignette has only explicitly supplied vitals/symptoms.

**Layout:** strip top, five-slot ladder center, evidence notebook right. Mobile ladder vertical.

**Exact ladder cards:** `1 Rate and R–R pattern`; `2 Atrial activity: are P waves present and consistent?`; `3 P–QRS relationship: who conducts to whom?`; `4 QRS width and morphology`; `5 Evidence-based rhythm description and uncertainty`.

Opening: `The ladder prevents a fast or irregular strip from becoming a reflex label.` Prompt `Put the five rhythm questions in a defensible order.` Correct `Yes. Start with timing, then atrial evidence and relationship, then ventricular activation, then synthesize.` Alternate ordering of rate/regularity same card only.

Clinical boundary card: heading `What the ECG cannot show by itself`. Copy `The tracing can show rate, regularity, atrial activity, AV relationship, and QRS morphology. It cannot reveal blood pressure, perfusion, chest pain, mental status, or acute heart failure unless the case supplies those data.` Check correct option `Assess patient stability from clinical data; do not infer it from the waveform alone.`

Transfer: learner applies five headings to an unseen strip without naming. **Evidence:** order and all five observations. **Connections:** M4/M6 rhythm frameworks.

**Tangent:** “Why not start with ‘is the patient stable?’” → `On this tracing — Stability is not encoded in the waveform. General connection — In real care, assess the patient immediately while using the rhythm ladder to describe the ECG; the two processes are complementary, not competing. Where we paused — You were ordering the rhythm ladder.` Return exact.

## M03.S2 — Regular, regularly irregular, or irregularly irregular

**Timing:** 7–9 minutes. **Objective:** describe R–R pattern before mechanism.

**Case contract:** three real reviewed strips: regular; repeating short-long pattern; irregularly irregular; ≥10 s preferred; R peaks supplied; no rhythm labels; quality adequate.

**Layout:** strip 9 columns, interval ladder/plot 3. Mobile mark R peaks then inspect an interval table.

**Exact copy:** Heading `Irregularity has a pattern—or it does not.` Definitions: `Regular: R–R intervals are similar.` `Regularly irregular: the variation repeats in a pattern.` `Irregularly irregular: intervals vary without a repeating pattern over the sample.` Caution `These are timing descriptions, not diagnoses.`

Task each strip `Mark at least six R peaks, then classify the R–R pattern.` Correct feedback names interval sequence. Regularly irregular called irregularly irregular: `The gaps vary, but the short–long sequence repeats. Describe the repetition before choosing a mechanism.` Irregularly irregular called regular: `Compare at least six intervals; one similar pair does not make the whole strip regular.` Height confusion `R–R concerns horizontal timing, not QRS height.`

Check `Can a 10-second strip prove a lifelong pattern?` Correct `No; describe the recorded sample and seek longer monitoring when the question requires it.` Feedback `Yes. State the duration observed.`

Equivalent retry: a new patterned strip with different sequence. **Evidence:** R marks, interval variance/pattern, label. **Connections:** S3 rate, S5 sinus arrhythmia, S11 bigeminy, M6 AF/flutter.

## M03.S3 — Rate when rhythm is not tidy

**Timing:** 8–10 minutes. **Objective:** choose and execute method for regular, patterned, and irregular samples; report average/range honestly.

**Case contract:** four real strips: regular; irregular ≥6 s; rate-changing ≥10 s; atrial/ventricular dissociation deferred (no atrial rate task). Grounded R peaks and rate statistics; paper speed visible.

**Layout:** split strip/tool notebook. Methods card accessible persistently.

**Exact method card:** `Regular: use a representative R–R interval, such as 300 ÷ large boxes at 25 mm/s.` `Irregular: count QRS complexes over a known duration; six seconds × 10 estimates average bpm.` `Changing rate: report an average and visible range or describe the change.` `Always state the method and sample length when precision matters.`

Prompts:

- `Choose the method before entering a number.`
- `Mark the interval or timed window used.`
- `Enter ventricular rate in bpm.`
- For changing strip: `Enter average, lowest visible interval-based estimate, highest visible estimate, and “over [duration] seconds.”`

Feedback correct regular `Your representative R–R interval and number agree with the grounded rate.` Incorrect number `Your method fits; recheck box arithmetic.` Wrong method `One R–R interval is not representative of this variable strip.` Count mismatch `You marked [n] QRS complexes but entered a rate based on [m]. Reconcile the count.` False precision `The visible grid and source resolution do not support [three-decimal value]. Round to a defensible estimate.`

Equivalent transfer chooses method unseen. Scoring numeric tolerance max(5 bpm, 10%); method and geometry mandatory. **Connections:** M01.S4, M6 rapid rhythm.

## M03.S4 — Sinus is a source, not a speed

**Timing:** 7–9 minutes. **Objective:** identify sinus brady/normal/tach as source + rate description; state contextual limits.

**Case contract:** three reviewed real sinus strips spanning rates, plus one ectopic atrial mimic; P morphology/II/aVR, stable PR, rate; no cause context unless vignette supplied.

**Layout:** aligned three-strip compare with locked scale; mobile swipe with fixed checklist.

**Exact opening:** `Keep two labels separate: where the impulse appears to begin, and how fast the ventricles respond.` Table column headings `Source evidence`; `Rate`; `Combined description`.

Learner completes:

- sinus at 48 → `sinus pattern`; `slow`; combined `sinus bradycardia pattern`.
- sinus at 76 → `sinus pattern`; `within 60–100`; `sinus rhythm at about 76 bpm`.
- sinus at 118 → `sinus pattern`; `fast`; `sinus tachycardia pattern`.

Exact correct feedback `Yes. The P-wave source and relationship remain sinus while the rate label changes.` Slow called non-sinus `Slow does not erase the sinus P–QRS evidence.` Fast called SVT `Rate alone does not establish a re-entrant supraventricular mechanism. Describe sinus evidence first.`

Context cards provide explicit scenarios only to teach limits: `sleeping healthy adult`; `after running`; `fever and pain`; `no context supplied`. Prompt `Which cause is proven by the ECG?` Correct `None; the ECG describes source and rate, while cause needs context.` Feedback `Yes. Do not reverse-engineer symptoms from a rate.`

Transfer ectopic atrial mimic: correct `not clearly sinus; P direction/morphology differs` without needing named diagnosis. **Evidence:** three combined descriptions, limits, mimic. **Connections:** S5, M4 brady, M6 tachy.

## M03.S5 — Respiratory sinus arrhythmia and gradual variability

**Timing:** 7–9 minutes. **Objective:** recognize cyclic R–R variation with preserved sinus P–QRS, distinguish from ectopy/AF without clinical overreach.

**Case contract:** reviewed sinus arrhythmia strip with respiratory trace if truly recorded, otherwise label `Teaching alignment`; sinus fixed P morphology, cyclic R–R; comparisons PAC and AF held for later/debrief; no age-normality claims unless metadata reviewed.

**Layout:** ECG and optional respiration curve aligned; mobile toggles curve. Reduced motion static phases.

**Exact copy:** Heading `Sinus timing can vary while the source stays sinus.` Body `Look for gradual, cyclic R–R shortening and lengthening with consistent sinus P waves before each QRS.` Interaction `March P waves and R waves through one full cycle.`

Prompt `Which evidence supports respiratory sinus arrhythmia rather than a premature beat?` Correct `The interval change is gradual and cyclic, and P morphology remains consistent.` Feedback `Yes. Prematurity is an abrupt timing event; this pattern breathes in and out.` AF distractor feedback `Organized consistent P waves argue against atrial fibrillation on this sample.`

Boundary copy `The ECG pattern does not prove a benign context in every patient. Symptoms, age, medications, and clinical circumstances remain separate data.`

Equivalent transfer without respiration overlay; requires rhythm description and evidence. **Connections:** S2, S6, M6 AF discrimination.

## M03.S6 — Early, on time, or late: the timing engine

**Timing:** 8–10 minutes. **Objective:** use expected sinus ticks to distinguish premature and escape events before origin labels.

**Case contract:** teaching simulator plus reviewed PAC/PVC/escape examples; expected sinus cycle grounded; no AV block example yet; target geometry for expected ticks and ectopic beats.

**Layout:** rhythm strip 9 columns, timing timeline 3. Mobile timeline below. Keyboard `E` expected tick, `B` beat marker.

**Exact script:** Heading `Timing narrows the mechanism before morphology does.` Body `First establish the expected sinus cycle. Then ask whether the unusual event arrives early, on time, or late.`

Interaction steps:

1. `Use three ordinary beats to place expected sinus ticks.` Correct `Your expected cycle is about [value] ms.`
2. Simulated event slider `Move the event earlier and later.` Captions `Early event → premature`; `Expected-time event → on time`; `Late event after a pause → escape candidate`.
3. Check `An unusual beat arrives before the next expected sinus tick. What can you say first?` Correct `It is premature.` Feedback `Yes. Timing is established before atrial versus ventricular origin.`
4. Check `A beat appears only after the expected beat fails to appear. What can you say first?` Correct `It is late and may be an escape beat.` Feedback `Yes. “Escape” requires lateness; do not call an early beat an escape.`

Misconception wide=PVC `Width can suggest altered ventricular activation, but timing must still be premature for a PVC.` Narrow=sinus `A narrow early beat can still be ectopic above the ventricles.`

Equivalent transfer asks mark expected tick and early/late. **Evidence:** cycle, tick, timing class. **Connections:** S7–S10, M4 dropped conduction/pacing.

## M03.S7 — Premature atrial complexes: find the early P

**Timing:** 9–11 minutes. **Objective:** locate premature P including T-wave deformation; relate QRS and pause; distinguish artifact.

**Case contract:** three reviewed real PAC morphologies: obvious early abnormal P/narrow QRS; P hidden in preceding T; blocked PAC optional only if reviewed and labeled advanced branch; QRS may be aberrant only in S9; lead II plus best atrial lead; target P geometry and expected sinus ticks.

**Layout:** full strip top, magnified preceding T/P window bottom; compare toggle preserves scale. Mobile tap magnifier.

**Exact opening:** `A PAC begins with an atrial impulse that arrives early.` Evidence card: `Premature timing`; `An early P wave with morphology different from the sinus P`; `The P may deform the preceding T wave`; `The following QRS is often narrow when conducted normally`; `The pause is commonly noncompensatory because atrial timing resets.` Caution `Not every PAC shows every feature clearly.`

Tasks:

1. `Place expected sinus tick; then mark the early atrial deflection.` Correct obvious `Yes. The different P arrives before the expected sinus P.` T-hidden correct `Yes. The changed contour on the preceding T is the premature P evidence.` Mark T peak only `Compare this T with ordinary T waves. Look for the extra notch or altered contour before the early QRS.`
2. `Compare the ectopic QRS with ordinary QRS complexes.` Correct narrow/similar `Yes. Atrial prematurity can conduct through the usual ventricular pathway.`
3. `Measure the pre- and post-event timing. Does the ectopic event reset the atrial cycle?` Correct reviewed case copy `Here, the next sinus timing is shifted, supporting a noncompensatory pause.` If not assessable `The strip does not expose enough atrial timing to classify the pause confidently.`
4. Evidence-before-label prompt `Select two strongest visible features, then choose PAC.` Label cannot be chosen first.

Feedback false PAC on artifact `The marked deflection does not maintain a physiologic P–QRS relationship. Check whether the ordinary QRS rhythm continues underneath noise.` False rejection because no obvious P `A PAC P can hide in T. Compare the altered T contour with neighboring beats.` Overclaim atrial location `The strip supports atrial prematurity, not a precise atrial focus location.`

Equivalent retry two morphologies, one obvious and one T-hidden. **Evidence:** timing tick, P mark, QRS compare, pause statement, label. **Connections:** M4 blocked PAC mimic, M6 narrow tachy/AF.

**Tangent:** “Can a PAC have a wide QRS?” → `On this tracing — The ectopic QRS is [grounded description]. General connection — Yes. An early atrial impulse can encounter part of the conduction system while refractory and conduct aberrantly, producing a wide QRS. M03.S9 compares that pattern with PVC. Where we paused — You were comparing the ectopic QRS.` Return exact.

## M03.S8 — Premature ventricular complexes: timing plus altered activation

**Timing:** 9–11 minutes. **Objective:** identify a premature wide complex with no supported preceding sinus P and characterize pause/morphology without overclaim.

**Case contract:** three reviewed real PVCs of differing morphology; premature timing; QRS ≥120 ms when claim used; P relationship annotated; post-event timing; no localization or treatment claims; paced beats excluded unless pacing fidelity adequate and reviewed.

**Layout:** strip and paired normal/PVC morphology overlay; overlay can be toggled and never used for scoring hidden morphology.

**Exact opening:** `A PVC is premature and activates the ventricles outside the usual conducted sequence.` Evidence card: `Earlier than the expected beat`; `Wide and different QRS morphology`; `No clearly related sinus P immediately before it`; `A compensatory pause may follow, but is not required in every visible example.`

Tasks: expected tick; mark QRS boundaries; search preceding P; compare ordinary/ectopic morphology; measure coupling and pause. Exact correct summary `This beat is premature, [value] ms wide, morphologically different, and has no supported preceding sinus P: a PVC pattern.`

Branches: wide but late `A wide late beat may be an escape or conducted/paced pattern. PVC requires prematurity.` P visible before wide beat `A related early P raises atrial prematurity with aberrant conduction; compare S9.` Pause not compensatory `A noncompensatory pause does not erase ventricular prematurity, but it should lower certainty if other evidence is weak.` QRS number only `Width alone does not prove ventricular origin; add timing and atrial evidence.`

Coupling copy `Coupling interval describes timing from the preceding ordinary beat to the PVC. It is an observation, not a burden or prognosis.`

Equivalent transfer requires evidence chain on two PVCs. **Evidence:** timing, width boundaries, P search, morphology, bounded label. **Connections:** S9/S11, M6 WCT, clinical palpitations.

## M03.S9 — PAC with aberrancy, PVC, or not enough evidence?

**Timing:** 10–12 minutes. **Objective:** discriminate wide premature beats using P evidence, morphology, timing, and uncertainty.

**Case contract:** reviewed comparison bank: PAC with aberrant QRS, PVC, pre-excitation/paced mimic only if appropriate fidelity and reviewed, plus ambiguous noisy beat. Multi-lead rhythm context required; target P geometry; diagnoses allowed only at category level.

**Layout:** side-by-side matched strips and evidence matrix. Mobile one case then compare summary.

**Evidence matrix exact headings:** `Premature?`; `Early P visible or T deformed?`; `QRS width/morphology`; `P–QRS relationship`; `Pause`; `Best-supported category`; `Confidence`.

Prompt `Complete evidence before choosing a category.` Categories `PAC with aberrant conduction`; `PVC`; `Wide premature beat—origin uncertain`; `Artifact / not assessable`.

Deterministic feedback:

- PAC aberrancy correct `The early atrial deflection precedes the wide QRS, so atrial prematurity with aberrant ventricular conduction is better supported.`
- PVC correct `No related premature P is supported, and the early wide morphology differs from ordinary conducted QRS complexes.`
- Ambiguous broader correct `Yes. The visible evidence supports a wide premature beat but not confident origin.`
- PVC chosen despite clear early P `Do not discard the atrial evidence because the QRS is wide.`
- PAC chosen on absent/unreadable P `An unseen P is not proof of no P, but it also cannot support PAC. Preserve uncertainty or use other morphology evidence only if reviewed.`
- Paced label from 100 Hz derivative `This source cannot resolve pacing spikes reliably. Pacing is not a permitted claim for this case.`

Equivalent retry: target/mimic/ambiguous trio. Pass ≥2/3 and no high-confidence origin error; otherwise new trio. **Evidence:** complete matrix, label, confidence. **Connections:** M5 conduction/pacing; M6 WCT.

## M03.S10 — Pauses, blocked impulses, and escape beats

**Timing:** 10–12 minutes. **Objective:** describe pause timing, identify late escape, distinguish pause from artifact; defer AV block specificity.

**Case contract:** reviewed sinus pause/arrest pattern, blocked PAC, junctional/ventricular escape examples, artifact dropout; P and QRS marching geometry; sufficient duration around pause; labels permitted only where clinician-reviewed. AV block mechanisms route to M4.

**Layout:** strip top, separate P and QRS timelines below. Mobile timelines stack with synchronized cursor.

**Exact opening:** `A pause is an observation. Its mechanism depends on what the atria and ventricles do during the gap.` Checklist: `March expected P timing`; `Look for an early hidden P`; `March QRS separately`; `Ask whether a late rescue beat appears`; `Check another lead for artifact`.

Stations:

1. `Mark expected sinus P ticks through the pause.` Feedback aligns.
2. Blocked PAC case: `Find the early P deforming T; no QRS follows it.` Correct description `Premature atrial impulse not followed by QRS; blocked PAC pattern.` Wrong “sinus pause” `The atrial event is early, not missing. Inspect the preceding T contour.`
3. Escape case: prompt `Does the unusual beat arrive early or late?` Correct late `Yes. A late beat after a pause is an escape candidate.` Then morphology category `narrow escape pattern`; `wide escape pattern`; `not assessable`, without precise focus unless reviewed.
4. P marches through dropped QRS case: correct response `Atrial activity continues while ventricular conduction fails; route to Module 4 for AV-block classification.` Feedback `Yes. Do not call this sinus arrest when P waves continue.`
5. Artifact dropout: `A second lead continues the rhythm; the apparent pause is channel artifact.`

Summary prompt `Write: “Pause of [duration]; atrial activity [description]; ventricular activity [description]; best-supported mechanism category [category]; uncertainty [reason].”`

Equivalent transfer one new pause. Critical error = early event called escape, marching P ignored, artifact called asystole/high confidence. Clinical boundary `A rhythm strip cannot determine perfusion during a pause; symptoms and clinical assessment are separate.`

**Connections:** M4 AV block/brady; M9 syncope. **Tangent:** current patient safety branch required.

## M03.S11 — Patterned ectopy without false burden

**Timing:** 7–9 minutes. **Objective:** bigeminy/trigeminy/couplets/run descriptors, observed frequency versus burden.

**Case contract:** reviewed examples of bigeminy, trigeminy, couplet, ≥3-beat sequence labeled only per local reviewed convention; strip duration explicit; no prognostic claims; ectopic classification inherited from prior evidence.

**Layout:** beat-tag row under strip, pattern counter. Mobile each beat has `N` normal and `E` ectopic buttons.

**Exact copy:** Heading `Pattern names describe sequence, not risk.` Definitions: `Bigeminy: every other beat is ectopic in the observed sequence.` `Trigeminy: every third beat is ectopic.` `Couplet: two consecutive ectopic beats.` `Three or more consecutive ventricular beats may be described as a run; rate and clinical context determine later classification.` `Observed frequency: what appears in this strip.` `Burden: proportion over a longer recording; ten seconds cannot establish daily burden.`

Task `Tag each beat N or E, then choose every pattern present.` Correct feedback names pattern and denominator. Wrong phase `Start at the first ordinary–ectopic pair and inspect whether the sequence repeats.` Calls 30% burden from strip `You observed [n]/[total] beats in [duration] seconds. Do not generalize that sample to daily burden.`

Transfer includes broken bigeminy pattern; correct description `intermittent bigeminy` rather than all-or-none. **Evidence:** beat tags, pattern, observed fraction, duration limitation. **Connections:** clinical monitoring, M6 runs.

## M03.S12 — Artifact can imitate rhythm change

**Timing:** 8–10 minutes. **Objective:** identify underlying marching QRS across noise using multi-lead consistency.

**Case contract:** real artifact cases with clinician-reviewed underlying rhythm; at least two simultaneous leads or explicit timing; tremor/motion/electrode artifact; no dangerous label leakage; geometry for underlying QRS and artifact.

**Layout:** two aligned leads 9 columns, artifact layer control 3. Mobile stacked synchronized leads.

**Exact opening:** `When one channel looks chaotic, ask whether the heart’s ordinary signal continues underneath.` Evidence checklist `Compare simultaneous leads`; `March likely QRS complexes`; `Look for physiologic consistency`; `Inspect abrupt onset/offset or baseline disturbance`; `Assess the patient in real care.`

Prompt `Mark every QRS you can defend in both leads.` Then `Box artifact rather than waveform.` Toggle `Fade teaching artifact overlay` appears only after commitment and, for real signals, uses an explanatory mask rather than altering source data.

Correct `Yes. The underlying QRS timing marches through the noisy channel and remains clearer in [lead].` False VF/VT branch `The label exceeds this strip’s evidence. Organized complexes continue in the comparison lead. In real care, assess the patient and verify the signal immediately.` False dismiss artifact when no QRS `Do not invent an underlying rhythm where no reliable complex is visible; choose not assessable.`

Equivalent transfer has artifact in different lead. **Evidence:** multi-lead QRS marks, artifact box, bounded label. **Connections:** S13, M6 rapid, clinical resuscitation (later, only validated data).

## M03.S13 — Mixed discrimination laboratory

**Timing:** 12–15 minutes. **Objective:** target/mimic/normal discrimination across sinus variation, PAC, PVC, pause/escape, pattern, artifact.

**Case contract:** minimum 10 reviewed cases in blocked bank: two canonical targets for each major category, two near-mimics, two normals; balanced lead/source cues; no case reused from teaching; all evidence geometry complete.

**Layout:** one strip at a time, evidence-first notebook. No diagnosis chips visible until evidence fields have entries. Mobile same.

**Exact per-case prompt:** `1 Mark expected timing.` `2 Mark atrial evidence.` `3 Mark QRS width/morphology.` `4 Describe the pause or artifact, if present.` `5 Choose the best-supported category.` `6 Set confidence.` Categories: `Sinus rhythm / sinus variation`; `PAC`; `PVC`; `Pause with escape candidate`; `Patterned ectopy`; `Artifact with underlying rhythm`; `Not enough evidence`.

Feedback sequence: first commit shows `Evidence agreement` rather than answer. Correct exact `Your label follows the timing, atrial, and ventricular evidence.` Partial `Your timing is right, but [atrial/QRS/pause] evidence is missing.` Incorrect `Keep the label provisional. Compare [specific observable] with an ordinary beat.` High-confidence wrong `This high-confidence miss will return as an equivalent case after two intervening examples.` Low-confidence correct asks strongest anchor.

Pass rule: ≥8/10, ≥80% evidence links, no unresolved high-confidence target/mimic confusion. Any miss returns in interleaved equivalent case; completion can exceed 10 cases. Score by category and evidence, not number of clicks or speed.

Adaptive logic: two PAC misses → one mechanism refresher, PAC/mimic/normal block, then delayed mixed; PAC-vs-PVC confusion → S9 exact waypoint; artifact miss → S12; escape timing miss → S6/S10. Copy `Your next three cases are changing because [observable error], not because you were slow.`

**Connections:** outgoing Train/Rapid, M4/M6. Tutor remains available only after commitment per case.

## M03.S14 — Clinical bridge: palpitations, dizziness, and monitoring context

**Timing:** 10–12 minutes. **Objective:** integrate ECG description with explicitly supplied symptoms/duration and choose next information category without treatment claims.

**Case contract:** three educational cases with explicit de-identified context and reviewed ECG: incidental PAC; symptomatic ectopy with stable supplied vitals; pause/escape with incomplete symptom correlation. No management prescription; options are information/escalation categories reviewed by clinicians.

**Layout:** context card 4, ECG 8; on mobile context collapses only after learner reads/acknowledges it. Vitals never inferred.

**Exact framework:** Heading `The ECG is one part of the clinical case.` Cards `What is the rhythm evidence?`; `What symptoms occurred, and when?`; `How long was the rhythm recorded?`; `Are stability data supplied?`; `What additional information would resolve the question?`

Case prompt `Write a rhythm description, link it to the supplied context without claiming causation, and choose the next information category.` Categories `Longer rhythm monitoring / symptom correlation`; `Medication and stimulant history`; `Electrolyte/clinical data review`; `Prior ECG comparison`; `Immediate clinical escalation because supplied instability criteria are present`; `Insufficient case data—seek supervising clinician`. The escalation option appears only if reviewed case explicitly supplies qualifying instability; none inferred from ECG.

Correct incidental copy `You described the ectopy and separated its presence from symptom causation or long-term burden.` Correct symptomatic copy `The temporal association raises relevance, but the strip alone does not prove cause.` Pause copy `You described the pause mechanism to supported specificity and identified missing symptom/stability data.` Treatment-answer branch `This module does not support a patient-specific treatment choice. First communicate rhythm evidence, supplied stability, and the missing data category.`

Transfer: one new context with ECG; rubric rhythm 50%, evidence 20%, context boundary 20%, next-data category 10%. **Connections:** M9 cases, M4/M6. Current-patient tangent uses mandatory safety branch.

## M03.S15 — Independent rhythm transfer and adaptive handoff

**Timing:** 12–16 minutes. **Objective:** independently analyze two unseen rhythms, explain one mechanism, calibrate confidence, and enter personalized practice.

**Case contract:** Case 1 target/mimic from weak area; Case 2 mixed rhythm with normal/variant possibility; real reviewed ≥10 s, multi-lead where needed, no labels; complete evidence manifests; equivalent bank.

**Layout:** blank rhythm ladder that fills from learner annotations; tutor collapsed. Mobile one evidence layer at a time with persistent strip overview.

**Exact entry:** Heading `Independent rhythm read` Body `Use the ladder on two unseen recordings. The tutor stays quiet until you submit or ask. Speed is not scored.`

**Required response form:**

- `Rate and method`
- `R–R pattern`
- `Atrial activity`
- `P–QRS relationship`
- `QRS width and morphology`
- `Premature, paused, escape, patterned, or artifact evidence`
- `Best-supported rhythm description`
- `Confidence: low / moderate / high`
- `What the ECG cannot establish`

Case 1 submit `Submit evidence`. Feedback gives per-axis support. Case 2 is blank prose plus evidence attachment. Complete ≥80%, no unresolved early/late reversal, no false high-confidence origin, no instability inferred.

Mechanism explain prompt randomly chosen from passed evidence: `Explain why this event is premature rather than escape`; `Explain why atrial evidence supports PAC over PVC`; `Explain how QRS marches through artifact`; `Explain why the sample does not establish burden.` Correct requires causal relationship, not keywords.

Payoff copy:

> `You can now move from timing to atrial evidence to ventricular morphology, then stop at the specificity the tracing supports.`
>
> `That reasoning is the bridge to AV block in Module 4 and tachyarrhythmias in Module 6.`

Handoffs:

- `Train my weakest rhythm distinction` — blocked target/mimic/normal, then delayed mixed.
- `Try untimed mixed rhythm quick-looks` — one dominant finding and confidence, full debrief after commitment.
- `Continue to Module 4: AV conduction and bradyarrhythmias`.
- `Preview Module 6 only after conduction and wide-QRS readiness`.
- `Return to [exact weak scene]`.

Cross-mode copy: `Your practice queue will emphasize [weak distinction] until two equivalent successes, then mix it with prior rhythms. Time alone will not raise mastery.`

**Tangent:** “Am I ready to read telemetry?” → `On this tracing — You demonstrated [grounded strengths] and still need review on [grounded axes]. General connection — This module supports formative rhythm description; real telemetry requires local workflow, artifact awareness, escalation expectations, and supervised clinical practice. Where we paused — You were choosing the next practice route.` Return exact.

## M03 acceptance checklist

- [ ] All 16 scenes exist; timing, sinus, PAC, PVC, pause, escape, patterns, artifact, clinical context, and independent transfer are not compressed into generic MCQs.
- [ ] Rhythm ladder always separates visible ECG evidence from patient stability.
- [ ] Rate scoring checks method, R/timed geometry, duration, numeric tolerance, and false precision.
- [ ] Sinus source is never defined by 60–100 bpm; sinus brady/tach and sinus variability are tested.
- [ ] Regularly irregular and irregularly irregular are distinguished using at least six intervals and sample-duration language.
- [ ] Early versus late timing is assessed before PAC/PVC/escape labels.
- [ ] PAC cases include obvious and T-hidden P morphology; PVC cases require prematurity, width/morphology, and atrial evidence.
- [ ] PAC-aberrancy/PVC discrimination includes an uncertainty option and prohibits unsupported pacing-spike claims at low sampling rates.
- [ ] Pause cases march P and QRS separately and route AV-conduction specificity to M4.
- [ ] Patterned ectopy copy distinguishes observed strip frequency from longer-term burden.
- [ ] Artifact requires multi-lead or otherwise validated evidence and never substitutes screen appearance for patient assessment.
- [ ] Mixed discrimination uses at least ten unseen cases, interleaved equivalent retries, evidence-first commitment, and confidence calibration.
- [ ] Clinical bridge supplies rather than invents symptoms/vitals and makes no patient-specific treatment claim.
- [ ] Cross-mode handoff preserves objective, error class, case exclusions, scaffold, return waypoint, and delayed review.
- [ ] Tutor general teaching is direct, case claims are grounded, real-patient questions invoke the safety branch, and return restores exact state.
- [ ] Keyboard, touch, screen reader, mobile, 200% zoom, reduced motion, and optional-timer accommodations pass.
- [ ] Reviewed morphology/provenance/geometry exists for every scored case; absent cases make a scene demonstration-only or fail closed.
- [ ] Novice, clerkship, advanced, visual, verbal, anxious, attention-variable, keyboard-only, and low-vision learner sessions produce no unresolved P0/P1 issue before pilot.

## M03 exact state-copy supplement

| Scene | Tutor opening | Hint 1 | Hint 2 / coached contrast | Partial branch | Clinical bridge and exit transition |
|---|---|---|---|---|---|
| S0 | `Mark what you can see before naming anything. I will use the gaps to adjust support.` | `Begin with R peaks, then search immediately before QRS for atrial activity.` | `I will mark one P–QRS pair on a separate strip. Repeat the search on the unseen strip.` | `You recovered [evidence]. Add [missing timing or relationship evidence].` | `A reproducible rhythm description is easier for another clinician to verify.` → `Organize the observations into the rhythm ladder.` |
| S1 | `Build the ladder once; every later rhythm will use it.` | `Timing and atrial evidence come before a narrow rhythm name.` | `Use the neutral strip: rate/R–R, P activity, P–QRS, QRS, then synthesis.` | `The same five questions are present, but [card] is out of dependency order.` | `In real care, assess the patient while analyzing the rhythm; the ECG cannot supply perfusion.` → `First, give irregularity precise language.` |
| S2 | `March at least six R waves. A pair is not a pattern.` | `Compare the sequence of gaps, not the heights of the complexes.` | `I will plot six intervals from a different strip. Look for repetition versus nonrepetition.` | `You detected variation. Decide whether that variation repeats.` | `Sample duration limits certainty; describe what was actually recorded.` → `Use the pattern to choose an honest rate method.` |
| S3 | `Choose the method before the number, and anchor the method on the trace.` | `Regular strips can use one representative interval; variable strips need a timed sample.` | `On a different irregular strip, I will mark six seconds and count QRS complexes. Repeat on this case.` | `The numeric estimate is close. Add the matching method, duration, or trace marks.` | `An average rate may hide clinically relevant variation, so state the sample and range when visible.` → `Now separate sinus source from slow or fast rate.` |
| S4 | `Use two columns in your mind: source and speed.` | `Run the P–QRS sinus checklist without looking at the rate label.` | `Compare the 48 bpm and 118 bpm strips with rate hidden; the source evidence remains visible.` | `Your rate description is right. Add whether the P–QRS evidence supports sinus.` | `The ECG describes source and rate; fever, exercise, medications, or illness require supplied context.` → `See how sinus timing can vary gradually with the source preserved.` |
| S5 | `March the P waves as carefully as the R waves and watch whether change is gradual.` | `Look for cyclic shortening and lengthening rather than one abrupt early event.` | `Overlay the interval trend on a different sinus-arrhythmia strip, then classify the unseen one.` | `You preserved the sinus source. Add whether the timing change is gradual, repeating, or abrupt.` | `A sinus-variation pattern does not by itself establish a benign clinical situation.` → `Next, reduce every unusual beat to early, expected, or late.` |
| S6 | `Do not ask “PAC or PVC?” until expected timing is visible.` | `Use three ordinary beats to predict where the next sinus event belongs.` | `I will place expected ticks on a separate rhythm. Now place them on the unseen strip.` | `You located the unusual event. Add whether it precedes or follows the expected tick.` | `Early-versus-late reasoning prevents a rescue beat from being mislabeled as premature.` → `Use early atrial evidence to build the PAC pattern.` |
| S7 | `Compare the suspicious T wave with ordinary T waves before deciding that no P exists.` | `Search just before the early QRS for a changed notch or contour.` | `I will magnify a labeled hidden-P example, then give you a different unlabeled morphology.` | `The event is premature. Add the atrial deflection or state why it is not assessable.` | `A short strip identifies an observed PAC pattern; it does not establish symptom cause or long-term burden.` → `Now test a premature beat with altered ventricular activation.` |
| S8 | `Build the PVC claim from timing, width, atrial evidence, and morphology—not width alone.` | `Place the expected tick first, then compare the unusual QRS with ordinary complexes.` | `On a separate PVC, I will mark onset/end and the absent related P region. Repeat on the new case.` | `You identified a wide different QRS. Add prematurity and the P-wave relationship.` | `PVC presence on a teaching strip does not by itself determine prognosis or treatment.` → `Compare PVC with an aberrantly conducted PAC.` |
| S9 | `Complete the evidence matrix before the category buttons unlock.` | `A clear early P favors atrial prematurity even when the QRS is wide.` | `Contrast one reviewed PAC-aberrancy and one PVC, then classify an equivalent third case.` | `The strip supports a wide premature beat. Add only the origin specificity the atrial evidence can defend.` | `Preserving “origin uncertain” is safer than manufacturing certainty from width.` → `Use separate P and QRS timelines to analyze pauses.` |
| S10 | `March atria and ventricles separately through the gap.` | `Look for an early hidden P, continuing P waves, and the timing of any rescue beat.` | `On a different pause, I will draw both timelines. Rebuild them on the assessment case.` | `You described the gap. Add what the atria do and whether the next ventricular beat is early or late.` | `Symptoms and perfusion during a pause are clinical data, not waveform deductions.` → `Next, describe repeating ectopic sequences without inventing burden.` |
| S11 | `Tag every beat before naming bigeminy, trigeminy, or a couplet.` | `Write the N/E sequence and look for a repeating unit.` | `I will segment one different pattern into groups; identify the repeated unit in this strip.` | `Your ectopic beats are correct. Recheck the repetition or consecutive grouping.` | `Observed frequency over ten seconds is not the same as burden over hours or days.` → `Now expose a rhythm mimic: artifact over an organized rhythm.` |
| S12 | `Compare leads and march QRS complexes before reacting to the noisiest channel.` | `Look for organized complexes at the same times in the clearer lead.` | `I will fade the explanatory artifact mask on a separate case, then restore the original and give you a new one.` | `You recognized artifact. Add the underlying rhythm evidence or choose not assessable.` | `In real care, verify the patient and signal immediately when a dangerous rhythm and artifact are both plausible.` → `Mix sinus variation, ectopy, pauses, patterns, and artifact without advance labels.` |
| S13 | `Evidence fields unlock the category. I will not cue a diagnosis before commitment.` | `Open the five-rung rhythm ladder and inspect the first incomplete evidence row.` | `Return to one mechanism scene for a different coached example; this case will be replaced on return.` | `Your category is plausible. Complete [missing evidence row] before confidence is scored.` | `Adaptive practice should repair the reason for an error, then test it later among alternatives.` → `Apply the rhythm description to supplied symptoms and monitoring context.` |
| S14 | `Separate three statements: what the ECG shows, what the case supplies, and what remains unknown.` | `Use the case card for symptoms and stability; do not read them from the waveform.` | `I will model observation versus context on a different vignette. Your transfer case remains unrevealed.` | `The rhythm description is supported. Add whether symptom timing or stability data are supplied.` | `Clinical relevance requires symptom correlation, duration, stability, and other data; this lesson does not prescribe treatment.` → `Finish with two independent rhythm transfers.` |
| S15 | `I will stay quiet until you submit. Complete every rung or write why it is not assessable.` | `Open the empty ladder labels; they reveal the framework, not the answer.` | `Review one passed example from your weakest source scene, then return to a new independent case.` | `Your read covers [evidence]. Add [missing rung] or explicitly bound it.` | `Independent rhythm evidence is the prerequisite for AV-conduction and tachyarrhythmia reasoning.` → `Module 3 is complete. Choose targeted practice or continue to Module 4.` |

### M03 tangent-and-return inventory

| Scene | Learner tangent | Exact tutor answer and return control |
|---|---|---|
| S0 | `Which lead is best for P waves?` | `On this tracing — [lead] provides the clearest supplied atrial evidence. General connection — Lead II often displays sinus P waves well, while V1 can also help atrial activity; use whichever readable lead makes the relationship visible and cross-check others. Where we paused — You were marking P waves.` `Return to M03.S0 · Mark P waves` |
| S1 | `Can the ECG show whether the patient has a pulse?` | `On this tracing — A perfusing pulse is not established by the waveform. General connection — Electrical activity and mechanical perfusion are related but not identical; assess the patient and clinical signals directly. Where we paused — You were building the rhythm ladder.` `Return to M03.S1 · Build the rhythm ladder` |
| S2 | `How irregular is irregularly irregular?` | `On this tracing — The marked intervals [do/do not] show a repeating sequence over [duration]. General connection — The phrase describes variable R–R timing without a repeating pattern in the observed sample; it is not a numeric cutoff or a diagnosis by itself. Where we paused — You were classifying R–R pattern.` `Return to M03.S2 · Classify R–R pattern` |
| S3 | `Should I report atrial and ventricular rate separately?` | `On this tracing — This task requests ventricular rate from QRS complexes. General connection — Report atrial and ventricular rates separately when P waves and QRS complexes are dissociated or conduct in a ratio; Module 4 teaches that explicitly. Where we paused — You were entering ventricular rate.` `Return to M03.S3 · Enter ventricular rate` |
| S4 | `What rate counts as sinus tachycardia?` | `On this tracing — The grounded rate is [value] bpm and the sinus criteria are [description]. General connection — In the adult reference used here, more than 100 bpm is called tachycardia, but source and clinical cause require separate evidence. Where we paused — You were combining source and speed.` `Return to M03.S4 · Combine source and speed` |
| S5 | `Is sinus arrhythmia always respiratory?` | `On this tracing — [respiratory alignment is/is not] supplied. General connection — Respiratory sinus arrhythmia is a common cyclic pattern, but rate variation should not be assigned to breathing unless timing/context supports it. Where we paused — You were marching one cycle.` `Return to M03.S5 · March one cycle` |
| S6 | `What if the sinus rate itself is changing?` | `On this tracing — Expected ticks are estimated from [grounded ordinary beats]. General connection — When the baseline cycle changes gradually, use the local cycle around the event and lower certainty; do not force one global interval. Where we paused — You were placing the expected tick.` `Return to M03.S6 · Place the expected tick` |
| S7 | `Are PACs dangerous?` | `On this tracing — The supported claim is [PAC evidence] over [duration]. General connection — Clinical significance depends on frequency over longer monitoring, symptoms, structural context, and other patient data; this tutorial strip cannot determine risk or treatment. Where we paused — You were marking the premature P.` `Return to M03.S7 · Mark the premature P` |
| S8 | `Does every PVC have a full compensatory pause?` | `On this tracing — The post-event timing is [grounded description]. General connection — A compensatory pause is common but not universal or always measurable; PVC evidence should combine prematurity, QRS morphology, and atrial relationship. Where we paused — You were measuring the pause.` `Return to M03.S8 · Measure the pause` |
| S9 | `Can morphology rules always separate PAC aberrancy from PVC?` | `On this tracing — [grounded atrial and QRS evidence]. General connection — Multi-lead morphology can change probability, but visible premature P evidence and uncertainty remain important; some cases cannot be resolved confidently from a short strip. Where we paused — You were completing the evidence matrix.` `Return to M03.S9 · Complete the evidence matrix` |
| S10 | `How long a pause is dangerous?` | `On this tracing — The measured pause is [value] over a [duration]-second recording, with [atrial/ventricular evidence]. General connection — Clinical importance depends on symptoms, context, rhythm mechanism, and local standards; the waveform duration alone does not determine danger or treatment. If this is a current patient, use your clinical team and local escalation process now. Where we paused — You were marching P waves through the pause.` `Return to M03.S10 · March P waves through the pause` |
| S11 | `How many PVCs count as a high burden?` | `On this tracing — [n] of [total] observed beats are ectopic during [duration] seconds. General connection — Longer monitoring and clinical interpretation are required to estimate burden; this short sample cannot establish a daily percentage or its significance. Where we paused — You were tagging the sequence.` `Return to M03.S11 · Tag the sequence` |
| S12 | `Could this be ventricular fibrillation?` | `On this tracing — Organized QRS complexes [are/are not] supported in [comparison lead], and the noisy region is [description]. General connection — Artifact can imitate dangerous rhythms. In real care, assess the patient and verify the signal immediately rather than deciding from one channel. Where we paused — You were marking QRS complexes through artifact.` `Return to M03.S12 · Mark QRS through artifact` |
| S13 | `Why did the next cases become PAC-heavy?` | `On this tracing — Your recent errors involved [grounded evidence class]. General connection — The queue is temporarily blocking target, near-mimic, and normal cases to repair that distinction; after two equivalent successes it returns to mixed rhythms. Where we paused — You were on mixed case [n].` `Return to M03.S13 · Mixed case [n]` |
| S14 | `What should I do for this patient?` | `I can teach the ECG concept, but I cannot assess a real patient from this lesson. If this is about a current patient, use your clinical team and local escalation process now. On this teaching case — The supplied rhythm evidence is [grounded summary], and [stability data] are [supplied/not supplied]. General connection — Communicate the rhythm, supplied stability, timing, and uncertainty before a supervised management decision. Where we paused — You were choosing the next information category.` `Return to M03.S14 · Choose the next information category` |
| S15 | `Can I jump directly to wide-complex tachycardia?` | `On this tracing — Your current evidence profile is [grounded strengths and gaps]. General connection — Wide-complex tachycardia depends on rhythm timing plus ventricular-conduction morphology; complete M5 readiness or use the informed override with review links. Where we paused — You were choosing a handoff.` `Return to M03.S15 · Choose a handoff` |

### M03 visual, input-equivalence, and scoring matrix

| Scene | Desktop / laptop / mobile and visual states | Keyboard and touch-equivalent mechanics | Deterministic pass / equivalent retry |
|---|---|---|---|
| S0 | D aligned strips 8 + cards 4; L 7 + 3; M one strip at a time. V0 raw; V1 marks; V2 relationship lines; V3 readiness summary. | `Mark P`, `Mark R`, `Measure QRS`; arrows nudge; touch select tool then tap. | Retrieval completeness only; no mastery. Missing dimensions set scaffold and deep links. |
| S1 | D strip then five-slot ladder; L same; M vertical ladder. V0 shuffled; V1 learner order; V2 rationale; V3 applied evidence. | Card select + destination slot; Alt+Up/Down reorders; touch tap card/tap slot. | Exact dependency order, all five observations on transfer, clinical-data boundary check; retry reshuffles and changes neutral strip. |
| S2 | D strip 9 + plot 3; L 7 + 3; M strip then interval table. V0 raw; V1 six R marks; V2 intervals; V3 class; V4 duration limit. | `Mark R` then arrows; table automatically derives grounded intervals; touch tap. | Six valid chronological R marks, pattern label on three strips, duration-limit item, new equivalent pattern; retry changes pattern phase. |
| S3 | D/L strip and worksheet split; M strip then method. V0 regularity; V1 method; V2 geometry; V3 number; V4 report. | Method radios, R/window marking, numeric fields with units outside; touch set-start/set-end. | Method + anchored geometry + value tolerance on four tasks and unseen transfer; false-precision answer fails value expression. |
| S4 | D three equal strips; L three at ≥260 px each or paged; M swipe with persistent checklist. V0 rates hidden; V1 source evidence; V2 rates; V3 combined descriptions; V4 context limit. | Numbered strip tabs, P/R mark tools, source/rate form; touch same. | Three combined descriptions, no-cause item, ectopic mimic with two criteria; retry changes rate bands and morphology. |
| S5 | D ECG/respiration aligned; L same; M ECG then optional curve. V0 raw; V1 P/R marches; V2 interval cycle; V3 overlay if true/labeled; V4 transfer without overlay. | P/R marking keys; interval table; curve described textually; touch taps. | Preserved sinus evidence + gradual cyclic description + AF/PAC discriminator + overlay-free transfer; retry different cycle length. |
| S6 | D strip 9 + timeline 3; L 7 + 3; M strip then timeline. V0 ordinary beats; V1 local cycle; V2 expected ticks; V3 event slider; V4 class. | `E` expected, `B` beat, arrows nudge; preset early/on-time/late; touch buttons/tap. | Expected cycle within 10%, correct early/late on four examples and new transfer; retry varies baseline cycle to prevent fixed-gap memory. |
| S7 | D strip top, magnifier bottom; L same; M tap-to-magnify. V0 ordinary T; V1 suspicious contour; V2 early P; V3 QRS compare; V4 pause; V5 evidence chain. | Lead/beat navigator; `Mark expected`, `Mark P`; magnifier zoom buttons; touch tap. | PAC evidence chain on obvious + hidden-P teaching and two unseen transfers; origin without marked P/timing is partial; retry different PAC morphology. |
| S8 | D strip + morphology overlay; L same; M sequential normal/PVC compare. V0 tick; V1 QRS boundaries; V2 P search; V3 overlay after commit; V4 pause; V5 summary. | Expected/P/QRS tools; overlay toggle; interval fields; touch tap after tool choice. | Full evidence chain on three teaching and two transfer PVCs; wide-only label is partial; retry different coupling/morphology. |
| S9 | D matched strips + matrix; L paged strips + fixed matrix; M one strip then matrix. V0 hidden categories; V1 timing/P/QRS rows; V2 categories unlock; V3 confidence; V4 compare. | Each matrix cell is a fieldset; waveform evidence attached via lead/beat dropdown or pointer; touch same. | Target/mimic/ambiguous trio ≥2/3, all evidence rows, no high-confidence origin error; retry entirely new trio. |
| S10 | D strip + two timelines; L same; M atrial then ventricular timeline. V0 raw; V1 expected P; V2 actual P; V3 QRS; V4 escape/artifact compare; V5 bounded summary. | `Mark expected P`, `Mark actual P`, `Mark QRS`; arrow nudge; text/list alternative; touch tap. | Correct atrial/ventricular description on all stations and unseen pause; early-as-escape, ignored marching P, or artifact-as-asystole requires equivalent retry. |
| S11 | D strip + tag row/counter; L same; M N/E buttons per beat. V0 raw; V1 tags; V2 grouping; V3 pattern; V4 fraction/duration. | Arrow selects beat, N/E applies tag, Space groups; touch explicit N/E. | ≥90% beat tags, exact supported patterns, observed fraction/duration, burden limit; retry changes starting phase and intermittent pattern. |
| S12 | D aligned leads 9 + checklist 3; L 7 + 3; M synchronized stack. V0 raw; V1 QRS marks; V2 artifact box; V3 explanatory mask after commit; V4 bounded category. | Lead-synchronized cursor; mark/box tools with form alternative; touch tap/drag or two-corner box. | ≥80% grounded QRS marks, box center/IoU threshold, underlying/not-assessable choice, unseen transfer; retry moves artifact to another lead/type. |
| S13 | D/L one case + notebook; M one lead stack/case. V0 evidence only; V1 marks; V2 categories; V3 confidence; V4 feedback; V5 interleaved retry. | Evidence fields precede category in DOM; all marks have dropdown alternative; touch same. | ≥8/10 labels, ≥80% evidence, no unresolved high-confidence miss; equivalent cases appear after two intervening items. |
| S14 | D context 4 + ECG 8; L context 3 + ECG 7; M context first and acknowledgement before collapse. V0 context; V1 ECG evidence; V2 linkage; V3 missing data; V4 category. | Context data table; ECG marks; sentence clause association; touch controls. | Rhythm 50%, evidence 20%, context boundary 20%, next-data 10%; ≥80% and no invented vitals/management; retry new context/rhythm pair. |
| S15 | D ECG 8 + blank ladder 4; L 7 + 3; M ECG overview then evidence layers. V0 unseen; V1 learner marks; V2 submit; V3 per-axis audit; V4 mechanism; V5 handoff. | Full accessible evidence form mirrors drawing; tutor collapsed; touch tool/tap. | Two cases ≥80%, mechanism explanation, calibrated confidence, no critical unresolved error; retry new weak-axis case, then delayed mixed case. |

---

# Cross-module connection inventory for M01–M03

| Evidence established | Incoming use | Immediate outgoing use | Later explicit reuse |
|---|---|---|---|
| Waveform timing and labels | M01.S1 | grid/boundaries | M4 AV relationship; M5 ventricular activation; M7 recovery |
| Calibration and resolution | M01.S2 | every measurement | M03 rate | M7 QT/ST; M8 criteria; M9 complete read |
| Task-specific readability | M01.S3 | M01 measures | M02 placement and M03 artifact | every clinical case |
| R–R method and grounded rate | M01.S4 | M03.S2–S3 | sinus source separation | M4 brady; M6 tachy |
| Sinus P–QRS relationship | M01.S5 | M03.S4–S5 | ectopy discrimination | M4 block; M6 AF/flutter/SVT |
| PR/QRS boundaries | M01.S6 | M03 rhythm ladder | pauses/PVC evidence | M4/M5/M6 |
| Baseline/J/ST/T/QT | M01.S7 | complete sweep | distribution language | M7/M8 |
| One event/twelve views | M01.S8 | M02 vector model | lead map | M5/M8 |
| Coarse axis | M01.S9 | M02.S10 | axis refinement | M5 fascicular/chamber forces |
| Complete sweep | M01.S10–S12 | module retrieval | M02/M03 transfer | M9 integration |
| Directed projection | M02.S1–S4 | lead geometry | axis/progression | M5/M7/M8 |
| Electrode/lead map | M02.S2/S5–S8 | contiguity | acquisition checks | M5/M8 |
| Axis degrees/confidence | M02.S10–S11 | transfer | morphology linkage | M5/M9 |
| R progression/placement | M02.S12–S13 | transfer | mimic awareness | M5/M8 |
| Rhythm ladder | M03.S1 | all M03 cases | clinical transfer | M4/M6/M9 |
| Timing before origin | M03.S6 | PAC/PVC/escape | mixed practice | M4/M6 |
| PAC/PVC uncertainty | M03.S7–S9 | mixed practice | adaptive Train | M5/M6 |
| P/QRS through pauses | M03.S10 | clinical transfer | M4 AV block | M9 syncope |
| Artifact and sampling limits | M03.S12 | mixed/rapid | clinical transfer | all monitored/acute modes |

Cross-link text is always action-specific. Approved patterns:

- Incoming chip: `Recall from [module · scene]: [one exact action].`
- Outgoing preview: `You will reuse this in [module · scene] to [one exact action].`
- Remediation: `Return to [scene] at [micro-step], complete one coached example, then come back to [current transfer].`
- Cross-mode: `Practise [subskill] with target, mimic, and normal cases; return here after [success criterion].`

---

# Scene traceability and implementation metadata

These matrices are binding metadata, not commentary. `SPEC-11.n` refers to `ECG_PLATFORM_SPEC.md` §11 item *n*; ontology identifiers are exact §7 keys; misconception identifiers quote §16 in normalized form. `TABLES.PAC_PVC` refers to the provisional, clinician-review-gated PAC/PVC expansion in `docs/clinical-content-tables-review.md`; it may not authorize management copy. Every primary-surface label is the accessible name for the corresponding ECG, animation, canvas, or assessment group. Common control labels from §0 still apply.

## M01 traceability

| Scene | `sourceRefs` | `prerequisiteObjectives` → `teachesObjectives` | `caseEligibility` / permitted claims | `masteryEvidence`, remediation, destinations | Primary-surface accessible label |
|---|---|---|---|---|---|
| M01.S0 | `SPEC-11.1`, `SPEC-11.16` | none → scope, descriptive-read promise, resume/test-out semantics | Clean lead-II teaching simulation; orientation only; no pathology or clinical claim | No mastery; support preference only; next M01.S1 | `Animated lead-II heartbeat introducing the four Foundations chapters` |
| M01.S1 | `SPEC-11.1`, `SPEC-7.normal_ecg` | recording-over-time → P/QRS/T location and activation/recovery sequence | Reviewed normal lead-II median beat; P/QRS/T geometry; gross morphology only | Three labels + mechanism + equivalent beat; remediate same scene at named label; later M04/M05/M08 | `Heart activation sequence drawing a P wave, QRS complex, and T wave` |
| M01.S2 | `SPEC-11.1` | waveform landmarks → calibration, paper speed, gain, time, voltage, precision | Calibration pulse and clean trace; explicit speed/gain; grounded spans | Boundaries + arithmetic + novel span; remediate time or voltage micro-step; Train measurement | `Magnified ECG grid with movable time and voltage markers` |
| M01.S3 | `SPEC-11.1`, `SPEC-16.paced_or_artifact_mistaken_for_arrhythmia` | calibration → task-specific readability and artifact localization | Reviewed quality labels, multi-domain quality and broad artifact ROI; no rhythm diagnosis | Domain classification + box + equivalent claim; remediate artifact/domain; later M03.S12 | `Rhythm strip quality assessment with assessable-domain choices and artifact box tool` |
| M01.S4 | `SPEC-11.3`, `SPEC-7.rate` | time grid, QRS → regularity-selected rate method | Real ≥6 s rhythm strip, R geometry, grounded ventricular rate; no median-beat tiling | R marks + method + numeric estimate + transfer; remediate method/arithmetic; Train rate | `Lead-II rhythm strip for marking R waves and estimating ventricular rate` |
| M01.S5 | `SPEC-11.4`, `SPEC-7.sinus_rhythm`, `SPEC-7.bradycardia` | P/QRS, rate → sinus source/relationship independent of speed | II/aVR; reviewed P geometry and P–QRS links; sinus/not-clear/not-assessable only | P marks, links, II/aVR, rate-source transfer; remediate P/T or relationship; M03.S4 | `Aligned lead II and aVR strips for assessing the sinus P-wave pattern` |
| M01.S6 | `SPEC-11.5`, `SPEC-11.7`, `SPEC-7.qrs_duration`, `SPEC-16.missing_wide_qrs` | grid, P/QRS → PR/QRS boundary measurement and broad category | Grounded PR/QRS, reviewed boundaries, standard calibration; `long PR`, `narrow/wide QRS`; no block/BBB label | Boundaries + value + category + transfer; remediate exact interval; M04/M05 | `Magnified beat for measuring PR interval and QRS duration` |
| M01.S7 | `SPEC-11.11`, `SPEC-11.15`, `SPEC-7.qt_interval`, `SPEC-16.mi_overcalled_from_nonspecific_st_t`, `SPEC-16.qt_measured_instead_of_qtc` | QRS boundary, grid → baseline/J/ST/T/QT landmarks and normal reference | Normal/reviewed morphology plus labeled simulation; no ischemia, QTc threshold, drug/electrolyte cause | Baseline, J, ST restore, T rule, QT endpoints, transfer; remediate landmark; M08 | `Normal lead-II beat for marking baseline, J point, ST segment, T wave, and QT endpoints` |
| M01.S8 | `SPEC-11.1`, `SPEC-11.2`, `SPEC-11.9`, `SPEC-7.r_wave_progression` | waveform sequence → 12-lead layout, display timing, normal R/S progression | Real reviewed normal 12-lead; display timing metadata; V1–V6 amplitudes; no territory diagnosis | Lead locations + transition + aVR + explanation + transfer; remediate locator/progression; M02 | `Standard 12-lead ECG and V1-to-V6 progression navigator` |
| M01.S9 | `SPEC-11.6`, `SPEC-7.axis_normal`, `SPEC-7.left_axis_deviation`, `SPEC-7.right_axis_deviation`, `SPEC-16.misusing_limb_leads_for_axis` | 12-lead views → coarse I/aVF axis and borderline boundary language | Simulation + clear reviewed axis cases with I/II/aVF and degree; no cause | Vector sectors + two unseen I/aVF classifications; remediate net polarity; M02.S10 | `Hexaxial axis wheel linked to live limb-lead QRS polarity` |
| M01.S10 | `SPEC-11.16`, `SPEC-12.1` | all M01 component objectives → active modeled standard sweep | Two reviewed non-acute complete packets; permitted descriptive claims only | Predictions + ordered rail; formative, no independent mastery; next S11 | `Complete 12-lead ECG beside the seven-step descriptive sweep` |
| M01.S11 | `SPEC-11.16`, `SPEC-12.1`, `SPEC-16.normal_variants_underrecognized` | modeled sweep → guided evidence-linked sweep | Three unseen reviewed complete packets, including normal/deviation/not-assessable | ≥0.8, all domains, equivalent critical retries; remediate smallest M01 scene; Train/Rapid | `Guided three-case 12-lead sweep with fading prompts and evidence notebook` |
| M01.S12 | `SPEC-11.16`, `SPEC-12.1`, `SPEC-7.normal_ecg`, `SPEC-16.normal_variants_underrecognized` | guided sweep → independent descriptive read and calibrated confidence | Two unseen complete packets; no label leakage; non-acute claims | Weighted two-case read, evidence links, confidence; remediate exact weak scene; M02/Train/Rapid | `Independent 12-lead interpretation with claim-to-waveform evidence links` |

## M02 traceability

| Scene | `sourceRefs` | `prerequisiteObjectives` → `teachesObjectives` | `caseEligibility` / permitted claims | `masteryEvidence`, remediation, destinations | Primary-surface accessible label |
|---|---|---|---|---|---|
| M02.S0 | `SPEC-11.1`, `SPEC-11.2`, `SPEC-11.6`, `SPEC-11.9` | M01 calibration/waves/axis/layout → readiness vector | Reviewed normal complete packet; no new claim | Four retrieval actions; support only; remediate M01 deep link | `Normal 12-lead ECG for locating calibration, waves, limb leads, and chest leads` |
| M02.S1 | `SPEC-11.2`, `SPEC-11.6` | one event/twelve views → directed-view explanation | Concept simulation + reviewed normal views; polarity only | Three predictions + explanation; remediate same-event model | `One activation vector viewed from lead II, aVR, and a near-perpendicular lead` |
| M02.S2 | `SPEC-11.2` | directed view → electrode/lead distinction and bipolar construction | Anatomical simulation; reviewed placements/equations; no diagnosis | Place 4 electrodes + build randomized lead; remediate patient side/pole | `Torso diagram for placing four limb electrodes and constructing a lead` |
| M02.S3 | `SPEC-11.2`, `SPEC-11.6`, `SPEC-16.misusing_limb_leads_for_axis` | positive lead direction → qualitative projection sign/magnitude | Normalized simulation; no patient claim | Four angle predictions + mechanism + rotated transfer; remediate sign/magnitude | `Adjustable cardiac vector and lead axis with live projected waveform` |
| M02.S4 | `SPEC-11.1`, `SPEC-11.2` | static projection, P/QRS/T → time-varying vector intuition | Concept simulation + normal II/aVR comparison; no diagnostic vector loop | Frame predictions + changing-direction explanation; remediate frame | `Five-frame changing cardiac vector drawing waveforms in lead II and aVR` |
| M02.S5 | `SPEC-11.2` | electrodes/leads → I/II/III triangle, signed consistency, reversal preview | Torso simulation + real clean limb set; reversal simulated/labeled | Directions + signed relation + unlabeled retry; remediate endpoint | `Einthoven triangle linked to live leads I, II, and III` |
| M02.S6 | `SPEC-11.2`, `SPEC-11.6` | bipolar leads → augmented leads and hexaxial neighbors | Reviewed standard axes; real limb leads; no pathology | Six placements + neighbor/opposite tasks; remediate exact lead | `Hexaxial wheel for placing six frontal-plane lead directions` |
| M02.S7 | `SPEC-11.2` | electrode concept → V1–V6 anatomical placement | Anatomically reviewed torso; supervised-practice boundary | Six positions + reliable sequence + mirrored retry; remediate landmark | `Torso diagram for placing precordial electrodes V1 through V6` |
| M02.S8 | `SPEC-11.2`, `SPEC-11.9`, `SPEC-7.r_wave_progression` | V1–V6 placement, projection → horizontal viewpoint and normal trend | Simulation + reviewed normal precordials; broad view labels only | Order + V1/V6 prediction + mechanism; remediate vector/placement | `Horizontal chest cross-section linked to V1-through-V6 waveform tiles` |
| M02.S9 | `SPEC-11.2`, `SPEC-11.12`, `SPEC-16.st_elevation_localized_incorrectly`, `SPEC-16.reciprocal_changes_ignored` | frontal/horizontal maps → contiguity, approximate opposites, bounded territory | Normal map/ECG; neutral marker; lead-level geometry; no MI cause/vessel | Group selections + location-only description + transfer; remediate map; M08/M09 | `Body territory map linked to contiguous lead groups on a 12-lead ECG` |
| M02.S10 | `SPEC-11.6`, `SPEC-7.axis_normal`, `SPEC-7.left_axis_deviation`, `SPEC-7.right_axis_deviation`, `SPEC-16.misusing_limb_leads_for_axis` | projection/hexaxial → net I/aVF quadrant on real cases | Four reviewed real axis cases; I/aVF geometry/degrees; no cause | Net-area marks + two-case transfer; remediate polarity; Train axis | `Aligned lead I and aVF QRS complexes for net-area axis classification` |
| M02.S11 | `SPEC-11.6`, `SPEC-7.axis_normal`, `SPEC-7.left_axis_deviation`, `SPEC-7.right_axis_deviation` | quadrant → lead-II refinement, isoelectric method, degree/confidence | Five reviewed axis cases including borderline; all limb leads/degree | I/II/aVF + isoelectric lead + degree + confidence on two transfers; remediate tree | `Six limb leads and hexaxial wheel for refining frontal QRS axis` |
| M02.S12 | `SPEC-11.9`, `SPEC-7.r_wave_progression`, `SPEC-16.normal_variants_underrecognized` | horizontal projection → R/S trend, transition, variation | Three reviewed real progressions; R/S geometry; no infarct cause | R/S marks + transition + bounded category + transfer; remediate first crossover; M07 | `V1-through-V6 ECG tiles with R and S amplitude progression plot` |
| M02.S13 | `SPEC-11.1`, `SPEC-11.2`, `SPEC-11.9`, `SPEC-16.normal_variants_underrecognized`, `SPEC-16.paced_or_artifact_mistaken_for_arrhythmia` | placement/map/progression → acquisition hypothesis vs stable variation | Verified real pairs or explicitly labeled simulations; prior metadata; no diagnosis | Four stations + evidence/next datum + new pair; remediate placement/progression; M07/M09 | `Synchronized before-and-after 12-lead comparison for electrode placement and normal variation` |
| M02.S14 | `SPEC-11.2`, `SPEC-11.6`, `SPEC-11.9`, `SPEC-11.16`, `SPEC-12.1` | all M02 + delayed M01 QRS/calibration → independent spatial explanation | Two unseen complete spatial packets; no label leakage | Weighted independent map, axis, progression, acquisition; remediate exact scene; Train/Rapid/M03 | `Independent 12-lead spatial annotation and lead-map transfer assessment` |

## M03 traceability

| Scene | `sourceRefs` | `prerequisiteObjectives` → `teachesObjectives` | `caseEligibility` / permitted claims | `masteryEvidence`, remediation, destinations | Primary-surface accessible label |
|---|---|---|---|---|---|
| M03.S0 | `SPEC-11.3`, `SPEC-11.4`, `SPEC-11.5`, `SPEC-11.7` | M01 rate/sinus/intervals + M02 orientation → atrial/ventricular readiness | Reviewed II/aVR strips; P/R/QRS geometry; no new label | Retrieval actions only; remediate M01.S4–S6 | `Lead II and aVR rhythm strips for retrieving P-wave, QRS, regularity, and width evidence` |
| M03.S1 | `SPEC-11.4`, `SPEC-11.14`, `SPEC-16.af_missed_by_focusing_only_on_rate`, `SPEC-16.flutter_confused_with_sinus_tachycardia` | P/QRS observations → evidence-first five-step rhythm ladder and stability boundary | Neutral strip; supplied clinical data only | Ordered ladder + five observations; remediate exact rung; later M04/M06 | `Rhythm strip with five-card evidence ladder from timing to synthesis` |
| M03.S2 | `SPEC-11.4`, `SPEC-7.sinus_rhythm`, `SPEC-7.atrial_fibrillation`, `SPEC-16.af_missed_by_focusing_only_on_rate` | R marks → regular/regularly irregular/irregularly irregular description | Three reviewed ≥10 s strips; R geometry; no mechanism label | ≥6 R marks + pattern + equivalent retry; remediate interval sequence | `Rhythm strip and R-to-R interval plot for classifying regularity patterns` |
| M03.S3 | `SPEC-11.3`, `SPEC-11.4`, `SPEC-7.rate` | regularity and calibration → method-selected average/range rate | Four real strips, R geometry, explicit duration and rates | Method + geometry + values + transfer; remediate arithmetic/method; Train rate | `Variable rhythm strip with timed window, R-wave markers, and rate worksheet` |
| M03.S4 | `SPEC-11.3`, `SPEC-11.4`, `SPEC-7.sinus_rhythm`, `SPEC-7.bradycardia`, `SPEC-16.flutter_confused_with_sinus_tachycardia` | sinus criteria + rate → sinus brady/normal/tach descriptions and cause limits | Three reviewed sinus rates + ectopic atrial mimic; II/aVR; no etiology | Three descriptions + no-cause check + mimic; remediate source-vs-speed; M04/M06 | `Three aligned sinus rhythm strips at slow, normal, and fast rates` |
| M03.S5 | `SPEC-11.4`, `SPEC-7.sinus_rhythm`, `SPEC-16.af_missed_by_focusing_only_on_rate`, `SPEC-16.normal_variants_underrecognized` | sinus/source + regularity → cyclic sinus variation | Reviewed sinus-arrhythmia strip; respiration only if true/labeled | P/R march + mechanism evidence + transfer; remediate gradual-vs-abrupt | `Sinus rhythm strip aligned with an optional reviewed respiratory cycle` |
| M03.S6 | `SPEC-11.4`, `SPEC-11.13`, `TABLES.PAC_PVC` | expected sinus cycle → early/on-time/late event class | Simulator + reviewed premature/escape examples; target timing | Expected ticks + timing categories + transfer; remediate timing engine; M04 | `Rhythm strip with expected sinus timeline for classifying early and late events` |
| M03.S7 | `SPEC-11.4`, `TABLES.PAC_PVC` | early event + P evidence → PAC evidence chain | Three reviewed PAC morphologies, including T-hidden P; no focus localization | Tick + P geometry + QRS/pause + two transfers; remediate T/P compare; Train PAC | `Rhythm strip and magnified T-wave window for locating a premature atrial complex` |
| M03.S8 | `SPEC-11.4`, `SPEC-11.7`, `TABLES.PAC_PVC`, `SPEC-16.missing_wide_qrs` | early timing + QRS boundaries → PVC evidence chain | Three reviewed PVCs; QRS/P/pause geometry; no prognostic/localization claim | Timing + width + P search + morphology + transfers; remediate exact axis; Train PVC | `Rhythm strip comparing an ordinary conducted QRS with a premature wide QRS` |
| M03.S9 | `SPEC-11.4`, `SPEC-11.7`, `TABLES.PAC_PVC`, `SPEC-16.missing_wide_qrs`, `SPEC-16.paced_or_artifact_mistaken_for_arrhythmia` | PAC/PVC evidence → aberrant PAC/PVC/uncertain discrimination | Reviewed multi-lead target/mimic/ambiguous bank; pacing only if fidelity supports | Full evidence matrix + 2/3 transfer, no high-confidence origin error; remediate S7/S8 | `Evidence matrix and matched rhythm strips for classifying a wide premature beat` |
| M03.S10 | `SPEC-11.13`, `SPEC-7.av_block_second_degree_mobitz_i`, `SPEC-7.av_block_second_degree_mobitz_ii`, `SPEC-7.av_block_third_degree`, `SPEC-16.av_block_types_confused` | expected timing/P–QRS → pause, blocked impulse, escape, route to M04 | Reviewed pause/blocked PAC/escape/artifact; separate P/QRS geometry; broad claims only | P/QRS timelines + bounded summary + transfer; remediate S6; M04 exact waypoint | `Rhythm strip with separate atrial and ventricular timelines through a pause` |
| M03.S11 | `SPEC-11.4`, `TABLES.PAC_PVC` | ectopic classification → bigeminy/trigeminy/couplet/run descriptors and burden limit | Reviewed pattern strips, explicit duration; no prognosis | Beat tags + pattern + observed fraction + limitation; remediate pattern counter | `Rhythm strip with normal-versus-ectopic beat tags and repeating-pattern counter` |
| M03.S12 | `SPEC-11.4`, `SPEC-16.paced_or_artifact_mistaken_for_arrhythmia` | quality + marching → multi-lead artifact discrimination | Reviewed artifact with simultaneous/comparable leads and underlying rhythm | Multi-lead QRS marks + artifact box + transfer; remediate M01.S3/M03.S12 | `Two synchronized ECG leads for finding organized QRS complexes through artifact` |
| M03.S13 | `SPEC-11.3`, `SPEC-11.4`, `SPEC-11.13`, `SPEC-16.af_missed_by_focusing_only_on_rate`, `SPEC-16.paced_or_artifact_mistaken_for_arrhythmia`, `TABLES.PAC_PVC` | all M03 taught objectives → mixed target/mimic/normal discrimination | ≥10 unseen reviewed cases, balanced cues, complete geometry | ≥8/10, evidence ≥80%, all high-confidence misses repaired; adaptive Train | `Mixed rhythm discrimination assessment with evidence-first annotations` |
| M03.S14 | `SPEC-11.16`, `SPEC-12.1` | rhythm description → bounded clinical-context/data reasoning | Three reviewed educational contexts; vitals/symptoms supplied; no treatment claim | Rhythm 50/evidence 20/context 20/next-data 10 + transfer; remediate source scene; Clinical | `Clinical context card beside a rhythm strip for linking symptoms, duration, and evidence` |
| M03.S15 | `SPEC-11.16`, `SPEC-12.1`, `SPEC-16.af_missed_by_focusing_only_on_rate`, `SPEC-16.paced_or_artifact_mistaken_for_arrhythmia` | all M03 → independent atrial/ventricular timing description and handoff | Two unseen reviewed cases + equivalent bank; no label leakage | ≥80%, mechanism explanation, calibrated confidence; exact remediation; M04/M06/Train/Rapid | `Independent rhythm assessment with atrial and ventricular evidence layers` |

---

# Global copy inventory

The scene sections above are the authoritative instructional copy. This inventory captures reusable interface strings so implementation does not invent inconsistent variants.

## Navigation and status

`Start module`; `Resume module`; `Start from the beginning`; `Show placement check`; `Previous`; `Next`; `Continue`; `Save and leave`; `Scenes`; `Complete`; `Needs review`; `Skipped`; `Mastered later`; `Scene complete. [next scene title] is available.`; `Your work is saved.`; `Welcome back. Your tracing, notes, and place in the lesson are restored.`

## Interaction controls

`Check`; `Check labels`; `Check span`; `Check evidence`; `Submit evidence`; `Submit read`; `Try again`; `Show one hint`; `Show principle`; `Compare with report`; `Replay`; `Pause`; `Previous frame`; `Next frame`; `Reduce motion`; `Set start`; `Set end`; `Nudge −1`; `Nudge +1`; `Reset marks`; `Clear my answer`; `Attach evidence`; `Not assessable`; `Review later`.

## ECG tools

`Pointer`; `Zoom`; `Caliper`; `March`; `Box artifact`; `Fit full ECG`; `Reset view`; `Lead [lead]`; `Time [value] seconds`; `Voltage [value] millivolts`; `Source resolution: approximately [value] ms.`; `Teaching simulation`; `Real ECG`; `Sequential display`; `Simultaneous display`; `Full provenance`; `Why this case?`.

## Tutor

`Ask the tutor`; `You paused at [return waypoint].`; `On this tracing`; `General connection`; `Where we paused`; `Return to [return waypoint]`; `This tracing does not establish that.`; `I can explain the concept generally.`; `Show me on a different example`; `Give me a principle-level hint`; `I want to keep trying`; `Your tracing and answer are restored.`

## Feedback

`Yes.`; `Not yet.`; `Partly.`; `Add visible evidence.`; `Keep the label provisional.`; `Your number needs a trace anchor.`; `Your observation is correct; the cause is not established here.`; `That connection is reasonable and belongs to [later scene].`; `This objective is not complete yet.`; `Try an equivalent tracing.`; `High confidence on a miss adds review; it does not subtract points.`; `Time and hints are descriptive. They do not reduce your score.`

## Safety and data integrity

`This learning case did not pass its content check. Your progress is safe; choose another case or try again later.`; `This source does not support that precision.`; `The required lead or waveform is not readable.`; `The visible evidence supports [broader claim], not [narrow claim].`; `I can teach the ECG concept, but I cannot assess a real patient from this lesson.`; `If this is about a current patient, use your clinical team and local escalation process now.`

---

# Content governance and source boundary

Numeric calibration, interval conventions, axis conventions, lead definitions, and clinical boundaries in this specification require clinician sign-off and version ownership before release. Governing primary sources already adopted by the platform include the AHA/ACCF/HRS recommendations for ECG standardization and interpretation, the 2018 ACC/AHA/HRS bradycardia and conduction-delay guideline for downstream conduction content, and current AHA/ACC guidance for later acute-care modules. These sources govern claims; they do not replace morphology review of each teaching case.

Review anchors:

- [AHA/ACCF/HRS recommendations for ECG standardization and interpretation, Part I](https://www.ahajournals.org/doi/10.1161/CIRCULATIONAHA.106.180200) — recording technology, calibration, and standard terminology.
- [2018 ACC/AHA/HRS guideline on bradycardia and cardiac conduction delay](https://www.acc.org/guidelines/guidelines/2018/11/05/06/18/bradycardia-and-cardiac-conduction-delay) — governs downstream M04 clinical/conduction boundaries; it is not used here to turn a tutorial pause into a patient-specific action.
- [2023 ACC/AHA/ACCP/HRS atrial-fibrillation guideline](https://www.acc.org/Guidelines/Guidelines/2023/11/30/12/05/Atrial-Fibrillation-2023-Guideline) — governs downstream atrial-arrhythmia clinical content; M03 teaches timing and organized atrial evidence without management prescriptions.

Each numeric or clinical rule in released content must additionally record `content_owner`, `reviewer`, `source_version`, `review_date`, `next_review_date`, and the exact claim authorized. A hyperlink in this document is not clinical sign-off.

No module is “fully implemented” merely because these words render. Release requires the module-specific acceptance checklist, a case-by-case evidence manifest, automated state/geometry/grading tests, and observed human usability across the declared personas and access paths.
