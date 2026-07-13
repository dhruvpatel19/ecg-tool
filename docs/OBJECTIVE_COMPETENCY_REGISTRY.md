# ECG objective and competency registry

## 1. Two linked identifiers

The platform distinguishes:

- **Case concept:** a finding that can be confidence-curated on a recording, such as `right_bundle_branch_block` or `qtc_prolongation`.
- **Educational objective:** the narrower thing a learner is asked to do, such as `qrs_width_morphology`, `pr_qrs_boundaries`, `lead_territories`, or `wide_qrs_qt_confound`.

An educational objective may use a broader case family only through an explicit mapping and a task that still proves the requested skill. A normal ECG can support lead-territory mapping; it cannot award ischemia recognition. If no case/task combination can prove the objective, the activity is unavailable rather than silently substituted.

## 2. Case-concept domains

The active corpus is tiered across 46 concepts:

| Domain | Concepts |
| --- | --- |
| Foundations | normal ECG, rate, sinus rhythm |
| Rhythm | AF, flutter, SVT, bradycardia, paced rhythm, PAC, PVC; WCT has 130 audited target-only expert rhythm windows and remains source/subskill-limited |
| AV conduction | first-degree, Mobitz I, Mobitz II, third-degree block |
| Axis | normal, left, and right axis |
| Ventricular conduction | QRS duration, complete/incomplete RBBB, LBBB, nonspecific IVCD, left anterior/posterior fascicular block, pre-excitation |
| Morphology/chambers | R-wave progression, LVH, RVH, atrial enlargement |
| ST–T/infarction | ST elevation/depression, T inversion, nonspecific change, ischemia, infarction, anterior/inferior/lateral/septal/posterior patterns, pathologic Q waves, pericarditis pattern |
| QT/drug/electrolyte | QT interval, QTc prolongation, electrolyte/drug pattern |

The runtime registry must return current A/B counts and never assume the same depth for every concept.

## 3. Educational-objective families

The guided curriculum contributes narrower objectives grouped as follows:

- recording quality and framework: interpretation framework mapping, integrated interpretation, prioritized synthesis, machine-read audit;
- lead/vector literacy: lead anatomy, projection, frontal lead map, precordial placement, territories, contiguous/reciprocal mapping;
- rhythm evidence: rhythm basics/regularities, atrial–ventricular relationship, ectopy timing, pause/escape, artifact;
- AV/brady reasoning: PR/QRS boundaries, PR sequence, 2:1 conduction, block-versus-blocked-PAC, bradycardia-with-pulse transfer;
- conduction mechanics: bundle activation, width-versus-morphology, IVCD claim strength, mixed ventricular conduction, device/pacing boundaries;
- tachycardia reasoning: tachycardia matrix, sinus-versus-SVT, atrial timing, irregular narrow rhythm, wide-complex uncertainty, tachycardia-with-pulse transfer;
- chamber/voltage: voltage projection, mixed chamber patterns, chronic-context claim limits, poor R-wave progression;
- repolarization/QT: ST–T morphology, primary/secondary change, recovery boundaries, wide-QRS QT confound, medication-QT workflow;
- ischemia/infarction: claim layers, localization, posterior mirror, contiguous/reciprocal evidence, mimic discrimination, chest-pain transfer, serial-comparison boundary;
- integration/clinical: comparison, chest pain, medication QT, wide-QRS/device, resuscitation source boundary, capstone.

The executable registry must enumerate every objective emitted by a guided handoff. Build/test validation fails if a handoff objective lacks a mapping, allowed subskills, or a declared unavailable reason.

## 4. Eight tracked subskills

| Subskill | Required observation |
| --- | --- |
| Recognize | Correctly identify a finding or valid negative control without answer leakage |
| Localize | Select the correct lead(s) and waveform point/region with spatial tolerance |
| Measure | Place defensible boundaries and obtain an interval/voltage within policy tolerance |
| Discriminate | Separate a target from a close mimic using positive and negative evidence |
| Explain mechanism | Link activation/recovery physiology to the observed waveform using a grounded rubric |
| Synthesize | Produce a complete, prioritized, evidence-limited interpretation |
| Apply in context | Combine the ECG with reviewed authored context without claiming unsupported causality |
| Calibrate confidence | Match confidence and claim strength to accuracy and evidence availability |

Not every objective supports all eight subskills. The registry declares allowed task predicates and a runtime source contract can narrow them further. The installed expert rhythm source currently supports independent `wide_complex_tachycardia × recognize` and `× discriminate`; mechanism/application/confidence work remains formative because those subskills are not part of that source label contract.

## 5. Evidence state shown to learners

Each objective×subskill cell reports:

- state: unseen, acquiring, developing, consolidating, or durable;
- formative score and independent score;
- number of independent distinct cases;
- morphology clusters represented;
- most recent practice and next retrieval due;
- high-confidence misses and misconception tags;
- timed-transfer and clinical-transfer evidence when applicable;
- uncertainty/reason when evidence is insufficient.

This is an educational scheduling estimate, not a certification of clinical competence.

## 6. Adaptive scheduling order

The deterministic scheduler prioritizes, in order:

1. overdue retrieval for previously learned objectives;
2. due retrievals, then high-confidence wrong or unsafe errors;
3. low independent evidence on a high-yield prerequisite;
4. inadequate case/morphology diversity;
5. unobserved objectives whose prerequisites are ready;
6. cross-concept interleaving after a focused streak;
7. transfer under time pressure and reviewed clinical context.

The AI may explain this recommendation in learner-friendly language. It does not choose an unvalidated case, alter the objective mapping, or write the mastery value.
