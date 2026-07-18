# Clinical Case learning experience

This redesign treats Clinical Cases as a patient-management learning loop, not a
quiz skin around an ECG. The implementation follows four product principles:

1. Give the learner a concise ordering indication before interpretation.
2. Keep the 12-lead ECG visually dominant and make waveform tools contextual.
3. Separate the learner's ECG evidence, clinical decision, and post-commit review.
4. End every set with case-level replay and personalized next steps across modes.

## Experience direction

- [Setup and set review mockup](./setup-and-set-review-mockup.png)
- [Active case and immediate review mockup](./active-case-and-review-mockup.png)

The setup surface intentionally keeps the existing three choices: care setting,
guided versus time-aware practice, and set length. Topic and difficulty filters
are not exposed until the case bank has sufficiently authored difficulty metadata;
adaptive variety is preferable to allowing learners to over-narrow the case mix.

The active case uses a patient journey—presentation, ECG, decision, reassessment,
and handoff—as the organizing model. Current single-ECG cases can use the first
three stages honestly. Reassessment and handoff become fully interactive only for
source-verified longitudinal episodes.

## Learning and question design

Question format follows the clinical reasoning demand rather than defaulting to
multiple choice:

- initial broad interpretation checks recognition and understanding;
- fill-in measurements and ECG regions apply trace-native skills;
- matching separates ECG evidence, vignette facts, and unsupported claims;
- machine-read audits analyze competing interpretations;
- triage and case decisions apply findings to patient care; and
- stepwise cases require analysis and evaluation before a management choice.

Selectable questions use a one-best or explicitly tiered key. Distractors must be
clinically plausible near-misses, grammatically parallel, similar in specificity,
and free of self-refuting or diagnosis-revealing language. A startup quality gate
enforces option count, length balance, cue language, key structure, and stepwise
choice diversity before a case can enter the serving bank.

The set selector interleaves interaction types and cognitive demand when candidate
cases have comparable personalized value. A materially higher-priority learning
need still wins, and an explicit study-plan handoff is never displaced merely to
improve variety.

## Content and evidence boundary

The production bank now contains 103 patient cases backed by 106 distinct real,
deidentified ECG records. Three pilot episodes use authenticated PTB-XL pairs:

| Episode | Authenticated ECG evidence | Authored simulation layer |
| --- | --- | --- |
| Rhythm conversion and medication safety | same-patient rapid atrial fibrillation to sinus-rhythm comparison, 23 h 43 min apart | medication reconciliation, electrolytes, observation, and handoff |
| Heart failure and myocardial injury | same-patient rate/rhythm change with persistent ST–T abnormality, 25 h apart | symptoms, diuresis response, creatinine, serial troponin, and handoff |
| Syncope with bifascicular conduction disease | same-patient unchanged right-bundle/left-anterior-fascicular pattern, 5 d 19 h apart | witness history, orthostatics, medication review, monitoring availability, and transfer |

Every pair is revalidated at startup and before serving: distinct record ids,
one non-null patient identity, the same approved source/version/license, strict
time order, acceptable signal quality, and human validation. Comparison ECGs
are reserved from standalone cases so no waveform can silently play two roles.

Only the pair relationship, interval, and packet-supported ECG findings are
source facts. Symptoms, laboratory values, treatment, response, and handoff
events are labelled `Authored simulation` in the learner UI. The cases do not
claim treatment caused an ECG change, distinguish type 1 from type 2 myocardial
infarction without sufficient evidence, prove torsades, or turn an unchanged
conduction pattern into proof of intermittent complete heart block.

The staged transport reveals one patient update at a time and persists each
answer before exposing the next update. A learner cannot inspect future labs or
the final disposition choices in the browser before committing the current
stage. Timed sets add decision time for every episode stage.

Clinical branches were checked against current official guidance: serial ECG
and high-sensitivity troponin assessment and explicit separation of acute injury
from type 1/type 2 mechanism follow the [2022 ACC chest-pain pathway](https://www.acc.org/latest-in-cardiology/ten-points-to-remember/2022/10/10/23/15/2022-acc-expert-consensus-on-chest-pain);
the QT-risk branch emphasizes medication review, electrolyte correction, and
monitoring consistent with the [AHA drug-induced arrhythmia statement](https://professional.heart.org/en/science-news/drug-induced-arrhythmias/top-things-to-know).
The rhythm-conversion branch retains thromboembolic-risk assessment independent
of the observed AF pattern, consistent with the [2023 ACC/AHA/ACCP/HRS AF
guideline](https://www.acc.org/Latest-in-Cardiology/ten-points-to-remember/2023/11/27/19/46/2023-acc-guideline-for-af-gl-af).
The syncope branch uses monitored evaluation without claiming a pacing
indication, consistent with the [ACC/AHA/HRS syncope guidance](https://professional.heart.org/en/science-news/2017-acc-aha-hrs-guideline-for-the-evaluation-and-management-of-patients-with-syncope/top-things-to-know).

These remain automated-screened, formative cases pending named clinician
sign-off. They enable defensible chronic prior/current reasoning, not acute
treatment-response or causality mastery.

Case-level AI may explain the committed decision and use server-validated ECG
annotations. Set-level AI may connect patterns across completed cases and the
learner's independent competency history, but it must not invent measurements,
award mastery, or draw case-specific annotations without a single-case packet.
