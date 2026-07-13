# ECG instructional source-content inventory

Status: source audit, July 2026. This inventory records the ECG teaching requirements that existed before the nine-module TRACE synthesis, identifies their authority, and checks whether `docs/CURRICULUM_STORYBOARD_SYSTEM_V2.md` covers them. It is a curriculum-source audit, not evidence that the current alpha implements every storyboard action.

## 1. Authority rules

| Level | Source | How it is used |
|---|---|---|
| **A — canonical minimum** | `ECG_PLATFORM_SPEC.md`, especially §7 and §11 (`:305-347`, `:604-665`) | Governs the minimum concept ontology and the minimum 16-topic guided curriculum. A later draft may reorganize these topics, but may not silently omit them. |
| **B — authored module authority** | `docs/storyboard-foundations.md` v7; `foundations/MODULE_GUIDE.md` v1.5; `foundations/MODULE_TEXT.md` v1.5 | Governs the detailed beginner scope, sequence, teaching language, normal values, interactions, assessment release, and known limitations of Foundations. The storyboard is the design authority; Guide/Text document the subsequently built v1.5 behavior. |
| **C — clinical-mode design and safety locks** | `docs/storyboard-clinical-case.md`, especially its later §§15–16 (`:208-271`) | Governs Clinical Decisions mode. Within this file, later user corrections and v0.5 locks supersede earlier prototype rules. In particular, the situation-scaled clock at `:214`, `:244-258` supersedes the earlier split/opt-in clock at `:150` and the review-packet summary at `docs/clinical-case-review-packet.md:19-24`. |
| **C-draft — requires clinician approval** | `docs/clinical-content-tables-review.md` | Inventories proposed acuity, action-cap, safety-action, symptom-causality, and measurement-bump rules. It states that it is generated and pending clinician sign-off (`:1-5`, `:58-65`); its values are not clinical truth or pilot authority yet. |
| **D — product contract/supporting summary** | `docs/RESEARCH_AND_PRODUCT_PLAN.md` | Confirms the four original learning contracts, deterministic grounding, Tier A/B gating, adaptive review priorities, and fixture disclosure (`:3-38`). It does not add pathology content beyond the canonical spec. |
| **Coverage target, not historical authority** | `docs/CURRICULUM_STORYBOARD_SYSTEM_V2.md` | The July synthesis reorganizes and expands the sources into nine modules. Its detailed tables are the current production target, but its additions are not retroactively part of the original minimum. Lines `:10-12` explicitly distinguish the 65-scene alpha from the full storyboard actions. |
| **Pointer only** | `docs/ECG_PLATFORM_SPEC.md` | Contains no independent requirements; it points to the canonical root specification (`:1-7`). |

Generated implementation summaries, persona reviews, and later rebuild documents were not used to create new source requirements in this inventory. They may provide implementation evidence, but they do not change the authority hierarchy above.

Citation shorthand used below: `MODULE_GUIDE.md` = `foundations/MODULE_GUIDE.md`; `MODULE_TEXT.md` = `foundations/MODULE_TEXT.md`; `storyboard-foundations.md` = `docs/storyboard-foundations.md`; `storyboard-clinical-case.md` = `docs/storyboard-clinical-case.md`; `clinical-content-tables-review.md` = `docs/clinical-content-tables-review.md`; `RESEARCH_AND_PRODUCT_PLAN.md` = `docs/RESEARCH_AND_PRODUCT_PLAN.md`; and `V2:n` = `docs/CURRICULUM_STORYBOARD_SYSTEM_V2.md:n`. In a V2-coverage cell, a bare `:n`/`:n-m` continues the immediately named V2 file; in any multi-range citation, a bare range continues the immediately preceding file path.

### Coverage labels

- **Covered** — the V2 storyboard contains the topic, its dependency, and an appropriate learning/transfer beat.
- **Covered, gated** — the V2 storyboard includes it but explicitly prevents unsupported scored competence.
- **Partial** — V2 mentions the requirement but does not preserve all source-specified detail or mode behavior.
- **Not explicit** — no adequate V2 storyboard requirement was found.
- **Conflict** — V2 intentionally changes an earlier source rule; curriculum ownership must ratify the change.

## 2. Shared corpus, grounding, and governance constraints

The codes below are used throughout the tables so each row retains an exact, auditable constraint reference.

| Code | Constraint | Exact source |
|---|---|---|
| **R-A** | Tier A is required for guided tutorials, detailed feedback, explicit visual explanation, and ROI teaching; it requires concordant labels/statements/features, acceptable quality, and concept-specific rules. | `ECG_PLATFORM_SPEC.md:163-180` |
| **R-B** | Tier B supports rapid/broad practice and cautious feedback; fine lead/ROI evidence may be incomplete. | `ECG_PLATFORM_SPEC.md:182-195` |
| **R-PC** | Reliability is per concept, not one global score; student-facing practice is enabled only with enough Tier A/B cases. | `ECG_PLATFORM_SPEC.md:220-229`, `:305-347`, `:739-741` |
| **R-NORMAL** | A normal teaching case requires concordant normal evidence, acceptable quality, near-normal measurements, and no major rhythm/conduction/MI/ST-T/chamber label. | `ECG_PLATFORM_SPEC.md:355-364` |
| **R-RHYTHM** | Rate/rhythm teaching requires a reliable measurement/estimate, rhythm evidence when naming rhythm, and acceptable signal quality. | `ECG_PLATFORM_SPEC.md:365-371`, `:424-431` |
| **R-AXIS** | Axis teaching requires a PTB-XL+ axis measurement or reliable frontal-plane evidence without major conflict. | `ECG_PLATFORM_SPEC.md:373-378` |
| **R-PR** | PR/AV-block teaching requires PR/fiducial evidence, a supporting label/statement, and no relevant contradictory rhythm classification. | `ECG_PLATFORM_SPEC.md:380-386` |
| **R-QRS** | QRS/BBB teaching requires duration plus a compatible label/statement; without morphology support, lead-specific claims must remain cautious. | `ECG_PLATFORM_SPEC.md:388-395` |
| **R-ISCH** | MI/ST-T teaching requires concordant diagnostic evidence; localization additionally requires lead/territory evidence. Without it, only broad MI/ST-T practice is allowed. | `ECG_PLATFORM_SPEC.md:397-405` |
| **R-CHAMBER** | Hypertrophy teaching requires voltage/axis/statement support and caution when only one weak criterion exists. | `ECG_PLATFORM_SPEC.md:407-413` |
| **R-QT** | QT/QTc teaching requires QT and QTc sources, rate context, confidence/source, and no required-measurement missingness. | `ECG_PLATFORM_SPEC.md:415-423` |
| **R-VIEW** | Instruction uses a real interactive, calibrated 12-lead viewer with correct axes, zoom/pan/reset, lead/ROI highlighting, calipers, click/drag annotations, coordinates, and validated AI actions. | `ECG_PLATFORM_SPEC.md:491-517`, `:519-600` |
| **R-LLM** | The LLM receives grounded packets, is not the diagnostic source of truth, and may reference only available findings/measurements/ROIs. | `ECG_PLATFORM_SPEC.md:18-20`, `:435-487`, `:830-883` |
| **R-SYNTH** | Synthetic waveforms are acceptable for manipulable causal tools or a clearly labeled demo fallback, not as undisclosed real clinical evidence. | `foundations/MODULE_GUIDE.md:69-71`; `ECG_PLATFORM_SPEC.md:1095-1100`; `docs/storyboard-clinical-case.md:78-89` |
| **R-FOUND22** | The built Foundations slice has 22 targeted chronic PTB-XL records; several deviation groups use tiled median beats rather than authentic beat-to-beat lead II. | `foundations/MODULE_GUIDE.md:54-71` |
| **R-CHRONIC** | PTB-XL/PTB-XL+ is a resting/chronic corpus; it cannot honestly supply acute STEMI evolution, VT/VF arrest, specific hyperkalemia, telemetry evolution, or true serial change. | `docs/storyboard-clinical-case.md:22-33`; corroborated by `docs/clinical-case-review-packet.md:11-14` |
| **R-STAFF** | STAFF-III is a candidate for controlled acute ischemia/dynamic ST teaching only; it excluded VT/emergency-procedure patients and is not a VT/code/arrest source. Licensing and ingest still require independent validation. | `docs/storyboard-clinical-case.md:28-33` |
| **R-AUTHCTX** | A real ECG may receive an authored board-style context only when the separation is explicit and all claims bind to ECG evidence, authored stem data, or action rationale. | `docs/storyboard-clinical-case.md:78-89`, `:197-204`, `:231-239` |
| **R-TRANSIENT** | Torsades, VT runs, pauses, telemetry alarms, and syncope-rhythm claims require rhythm-strip/telemetry evidence or an explicit non-ECG authored layer; they cannot count as resting-ECG recognition. | `docs/storyboard-clinical-case.md:233-238` |
| **R-CLINREV** | Clinical action caps, required safety actions, symptom-causality rules, numeric criteria, and scaled case content require named clinician review before bank scaling or scored action claims. | `docs/storyboard-clinical-case.md:263-269`; `docs/clinical-content-tables-review.md:1-5`, `:58-65` |
| **R-PRECISION** | The canonical spec permits 100 Hz default and optional 500 Hz; V2 tightens this by prohibiting overconfident fine-fiducial precision from the current 100 Hz derivative. | `ECG_PLATFORM_SPEC.md:515-517`; `docs/CURRICULUM_STORYBOARD_SYSTEM_V2.md:129-137` |

## 3. Canonical minimum guided curriculum

These rows reproduce every topic and subtopic explicitly labeled “Minimum curriculum” in the root specification.

| ID | Required topic/subtopic | Exact source | Dependency | Corpus/reliability | V2 coverage |
|---|---|---|---|---|---|
| MIN-01 | ECG orientation | `ECG_PLATFORM_SPEC.md:617-625` | None | R-A, R-VIEW | **Covered** in M1 `:143-161`. |
| MIN-01a | Paper speed | `ECG_PLATFORM_SPEC.md:619-624` | Orientation | R-VIEW; alternate speed must be explicit | **Covered** in M1.2 `:151`; realism rule `:131`. |
| MIN-01b | Calibration | `ECG_PLATFORM_SPEC.md:619-624` | Grid/time/voltage | R-VIEW | **Covered** in M1.2 `:151` and M1.10 `:159`. |
| MIN-01c | Amplitude/voltage | `ECG_PLATFORM_SPEC.md:619-624` | Calibration | R-VIEW | **Covered** in M1.1–1.2 `:150-151`. |
| MIN-01d | Time | `ECG_PLATFORM_SPEC.md:619-624` | Calibration | R-VIEW | **Covered** in M1.2, M1.4, M1.6 `:151`, `:153`, `:155`. |
| MIN-01e | Standard 12-lead layout | `ECG_PLATFORM_SPEC.md:619-624` | Basic waveform | R-A, R-VIEW | **Covered** in M1.8 `:157`, deepened in M2 `:163-180`. |
| MIN-02 | Lead anatomy | `ECG_PLATFORM_SPEC.md:626-630` | 12-lead orientation | R-A, R-VIEW | **Covered** in M2 `:163-180`. |
| MIN-02a | Limb leads | `ECG_PLATFORM_SPEC.md:626-630` | Electrode/lead distinction | R-VIEW | **Covered** in M2.3–2.4 `:172-173`. |
| MIN-02b | Precordial leads | `ECG_PLATFORM_SPEC.md:626-630` | Lead anatomy | R-VIEW | **Covered** in M2.5 `:174`. |
| MIN-02c | Territories | `ECG_PLATFORM_SPEC.md:626-630` | Limb + chest leads | R-ISCH for diagnostic localization | **Covered** in M2.6 `:175`, reused in M8. |
| MIN-02d | Contiguous leads | `ECG_PLATFORM_SPEC.md:626-630` | Territories | R-ISCH | **Covered** in M2.6 `:175`, M8.2 `:288`. |
| MIN-03 | Rate | `ECG_PLATFORM_SPEC.md:632` | Calibration/time; regularity chooses method | R-RHYTHM | **Covered** in M1.4 `:153`, M3.1 `:189`. |
| MIN-04 | Rhythm | `ECG_PLATFORM_SPEC.md:634-637` | Rate + readable tracing | R-RHYTHM | **Covered** in M1.5 `:154`, M3 `:182-198`. |
| MIN-04a | P waves | `ECG_PLATFORM_SPEC.md:634-637` | Wave anatomy | R-RHYTHM | **Covered** in M1.1/M1.5 `:150`, `:154`, then M3/M4. |
| MIN-04b | Regularity | `ECG_PLATFORM_SPEC.md:634-637` | QRS identification/time | R-RHYTHM | **Covered** in M1.4 `:153`, M3.0–3.1 `:188-189`. |
| MIN-04c | Sinus rhythm | `ECG_PLATFORM_SPEC.md:634-637` | P morphology + P–QRS relationship | R-RHYTHM | **Covered** in M1.5 `:154`, M3.2 `:190`. |
| MIN-05 | PR interval | `ECG_PLATFORM_SPEC.md:639` | P and QRS onset; box measurement | R-PR, R-PRECISION | **Covered** in M1.6 `:155`, M4.2–4.3 `:208-209`. |
| MIN-06 | Axis | `ECG_PLATFORM_SPEC.md:641` | Limb-lead geometry/QRS polarity | R-AXIS | **Covered** in M1.9 `:158`, M2.7–2.8 `:176-177`. |
| MIN-07 | QRS duration and conduction delay | `ECG_PLATFORM_SPEC.md:643` | QRS boundaries | R-QRS, R-PRECISION | **Covered** in M1.6 `:155`, M5.1–5.2 `:226-227`. |
| MIN-08 | Bundle branch blocks | `ECG_PLATFORM_SPEC.md:645` | QRS duration + V1/V6/vector concepts | R-QRS | **Covered** in M5.2–5.5 `:227-230`. |
| MIN-09 | R-wave progression | `ECG_PLATFORM_SPEC.md:647` | Precordial layout | R-A; lead placement/rotation must be considered | **Covered** in M1.8 `:157`, M2.9–2.10 `:178-179`. |
| MIN-10 | Chamber enlargement/hypertrophy basics, if supported | `ECG_PLATFORM_SPEC.md:649` | Lead vectors, voltage, axis, P morphology | R-CHAMBER, R-PC | **Covered, gated** in M5.10–5.11 `:235-236`. |
| MIN-11 | ST elevation/depression and T-wave changes | `ECG_PLATFORM_SPEC.md:651` | Baseline, J point, normal repolarization, QRS context | R-ISCH, R-A | **Covered** descriptively in M7 `:260-278`, etiologically in M8. |
| MIN-12 | MI localization | `ECG_PLATFORM_SPEC.md:653` | Territories, contiguity, ST/T/Q-wave evidence | R-ISCH, R-CHRONIC | **Covered, gated** in M8 `:280-299`; acute competence remains locked. |
| MIN-13 | Bradyarrhythmias and AV block | `ECG_PLATFORM_SPEC.md:655` | Rate, sinus/P–QRS relation, PR | R-PR, R-RHYTHM | **Covered** in M4 `:200-217`; sparse Wenckebach is gated. |
| MIN-14 | Tachyarrhythmias | `ECG_PLATFORM_SPEC.md:657-661` | Rhythm ladder + QRS morphology | R-RHYTHM, R-QRS | **Covered** in M6 `:240-258`. |
| MIN-14a | AF/flutter | `ECG_PLATFORM_SPEC.md:657-659` | P-wave/regularity analysis | R-RHYTHM | **Covered** in M6.5–6.7 `:251-253`. |
| MIN-14b | SVT | `ECG_PLATFORM_SPEC.md:657-660` | Narrow/wide + regularity + atrial evidence | R-RHYTHM | **Covered** in M6.3–6.4 `:249-250`. |
| MIN-14c | Wide-complex tachycardia only if reliably supported | `ECG_PLATFORM_SPEC.md:657-661` | M3 rhythm + M5 conduction | R-QRS, R-TRANSIENT, R-CHRONIC | **Covered, gated** in M6.8–6.12 `:254-258`; current PTB-XL cannot certify VT/WCT competence. |
| MIN-15 | QT/QTc and electrolyte/drug patterns, if supported | `ECG_PLATFORM_SPEC.md:663` | Rate, QT boundary, QRS/repolarization | R-QT, R-PC, R-CLINREV | **Covered, gated** in M7 `:260-278`. |
| MIN-16 | Integrated clerkship-style ECG interpretation | `ECG_PLATFORM_SPEC.md:665` | All prior descriptive domains | R-A/B, R-LLM | **Covered** in M1.10–1.12 `:159-161` and clinical prioritization in M9 `:301-318`. |

## 4. Required concept inventory and clinical-table additions

The first 37 rows are the canonical “at minimum” ontology in `ECG_PLATFORM_SPEC.md:305-347`. Rows marked **C-draft addition** occur in the unsigned clinical content table but not in that original minimum. For all C-draft rows, the concept may be taught, but the table's proposed acuity/action cap/safety/causality values remain unusable for pilot scoring until R-CLINREV is satisfied.

| Concept | Authority and exact source | Instructional dependency | Corpus/reliability constraint | V2 coverage |
|---|---|---|---|---|
| `normal_ecg` | A: `ECG_PLATFORM_SPEC.md:309`; C-draft signal `clinical-content-tables-review.md:9` | Calibration, quality, complete sweep | R-NORMAL | **Covered** M1 and M9.2 (`:143-161`, `:309`). |
| `rate` | A: `ECG_PLATFORM_SPEC.md:310`; C-draft `clinical-content-tables-review.md:10` | Time calibration, R-wave detection, regularity | R-RHYTHM | **Covered** M1.4/M3.1 (`:153`, `:189`). |
| `sinus_rhythm` | A: `ECG_PLATFORM_SPEC.md:311`; C-draft `clinical-content-tables-review.md:11` | P morphology, P–QRS relation, lead II/aVR | R-RHYTHM | **Covered** M1.5/M3.2 (`:154`, `:190`). |
| `atrial_fibrillation` | A: `ECG_PLATFORM_SPEC.md:312`; C-draft `clinical-content-tables-review.md:12` | Atrial activity, irregularity, ventricular rate | R-RHYTHM | **Covered** M6.6–6.7 (`:252-253`). |
| `atrial_flutter` | A: `ECG_PLATFORM_SPEC.md:313`; C-draft `clinical-content-tables-review.md:13` | Atrial activity, conduction ratio, AF/SVT contrasts | R-RHYTHM | **Covered** M6.5–6.7 (`:251-253`). |
| `supraventricular_tachycardia` | A: `ECG_PLATFORM_SPEC.md:314`; C-draft `clinical-content-tables-review.md:14` | Tachy matrix, P/RP evidence, onset/context | R-RHYTHM | **Covered** M6.3–6.4 (`:249-250`). |
| `wide_complex_tachycardia` | A: `ECG_PLATFORM_SPEC.md:315`; C-draft `clinical-content-tables-review.md:15` | Rhythm ladder, QRS/BBB/pre-excitation/pacing | R-QRS, R-TRANSIENT, R-CHRONIC | **Covered, gated** M6.8–6.12 (`:254-258`). |
| `bradycardia` | A: `ECG_PLATFORM_SPEC.md:316`; C-draft `clinical-content-tables-review.md:16` | Rate, rhythm, perfusion context | R-RHYTHM, R-CLINREV for actions | **Covered** M3.2/M4.9–4.11 (`:190`, `:215-217`). |
| `av_block_first_degree` | A: `ECG_PLATFORM_SPEC.md:317`; C-draft `clinical-content-tables-review.md:17` | PR boundaries, 1:1 conduction | R-PR | **Covered** M4.2–4.3 (`:208-209`). |
| `av_block_second_degree_mobitz_i` | A: `ECG_PLATFORM_SPEC.md:318`; C-draft `clinical-content-tables-review.md:18` | Serial PR behavior and dropped QRS | R-PR, R-PC; source corpus is sparse | **Covered, gated** M4.4 (`:210`). |
| `av_block_second_degree_mobitz_ii` | A: `ECG_PLATFORM_SPEC.md:319`; C-draft `clinical-content-tables-review.md:19` | Constant conducted PR, nonconducted P, mimic exclusion | R-PR; actions require R-CLINREV | **Covered** M4.5 (`:211`). |
| `av_block_third_degree` | A: `ECG_PLATFORM_SPEC.md:320`; C-draft `clinical-content-tables-review.md:20` | Independent atrial/ventricular activity, escape rhythm | R-PR/R-RHYTHM; actions require R-CLINREV | **Covered** M4.7–4.10 (`:213-216`). |
| `axis_normal` | A: `ECG_PLATFORM_SPEC.md:321`; C-draft `clinical-content-tables-review.md:21` | Limb-lead polarity/vector projection | R-AXIS | **Covered** M1.9/M2.7–2.8 (`:158`, `:176-177`). |
| `left_axis_deviation` | A: `ECG_PLATFORM_SPEC.md:322`; C-draft `clinical-content-tables-review.md:22` | I/aVF plus lead-II refinement | R-AXIS | **Covered** M2.7–2.8 (`:176-177`). |
| `right_axis_deviation` | A: `ECG_PLATFORM_SPEC.md:323`; C-draft `clinical-content-tables-review.md:23` | Limb-lead polarity/vector projection | R-AXIS | **Covered** M2.7–2.8 (`:176-177`). |
| `qrs_duration` | A: `ECG_PLATFORM_SPEC.md:324`; C-draft `clinical-content-tables-review.md:24` | QRS onset/end, time calibration | R-QRS, R-PRECISION | **Covered** M1.6/M5.1 (`:155`, `:226`). |
| `right_bundle_branch_block` | A: `ECG_PLATFORM_SPEC.md:325`; C-draft `clinical-content-tables-review.md:25` | QRS width, terminal vectors, V1/lateral leads | R-QRS | **Covered** M5.2–5.3 (`:227-228`). |
| `left_bundle_branch_block` | A: `ECG_PLATFORM_SPEC.md:326`; C-draft `clinical-content-tables-review.md:26` | QRS width, altered LV activation, secondary ST-T | R-QRS; ischemia claims require R-ISCH | **Covered** M5.4 (`:229`), reused in M8.9. |
| `nonspecific_intraventricular_conduction_delay` | A: `ECG_PLATFORM_SPEC.md:327`; C-draft `clinical-content-tables-review.md:28` | Width versus incomplete morphology criteria | R-QRS | **Covered** M5.5/M5.13 (`:230`, `:238`). |
| `r_wave_progression` | A: `ECG_PLATFORM_SPEC.md:328`; C-draft `clinical-content-tables-review.md:35` | Precordial layout, R/S ratio, placement/rotation | R-A; avoid infarct inference without R-ISCH | **Covered** M1.8/M2.9–2.10 (`:157`, `:178-179`). |
| `left_ventricular_hypertrophy` | A: `ECG_PLATFORM_SPEC.md:329`; C-draft `clinical-content-tables-review.md:36` | Voltage, axis, chamber/vector model | R-CHAMBER | **Covered, gated** M5.10–5.11 (`:235-236`). |
| `right_ventricular_hypertrophy` | A: `ECG_PLATFORM_SPEC.md:330`; C-draft `clinical-content-tables-review.md:37` | Voltage, rightward forces, mimic comparison | R-CHAMBER | **Covered, gated** M5.10–5.11 (`:235-236`). |
| `atrial_enlargement` | A: `ECG_PLATFORM_SPEC.md:331`; C-draft `clinical-content-tables-review.md:38` | P-wave morphology/duration | R-CHAMBER, R-PRECISION | **Covered, gated** M5.10–5.11 (`:235-236`). |
| `st_elevation` | A: `ECG_PLATFORM_SPEC.md:332`; C-draft `clinical-content-tables-review.md:39` | Baseline/J point, distribution, QRS context | R-ISCH, R-CHRONIC/R-STAFF | **Covered, gated** M7/M8; acute mastery locked (`:266-299`). |
| `st_depression` | A: `ECG_PLATFORM_SPEC.md:333`; C-draft `clinical-content-tables-review.md:40` | Baseline/J point, morphology/distribution | R-ISCH | **Covered** M7.4/M8.7 (`:270`, `:293`). |
| `t_wave_inversion` | A: `ECG_PLATFORM_SPEC.md:334`; C-draft `clinical-content-tables-review.md:41` | Normal lead-specific polarity and QRS/recovery context | R-ISCH | **Covered** M7.1/M7.4/M8.7 (`:267`, `:270`, `:293`). |
| `nonspecific_st_t_change` | A: `ECG_PLATFORM_SPEC.md:335`; C-draft `clinical-content-tables-review.md:42` | Descriptive ST/T morphology + mimic restraint | R-ISCH | **Covered** M7.4/M8.7/M8.10 (`:270`, `:293`, `:296`). |
| `myocardial_infarction` | A: `ECG_PLATFORM_SPEC.md:336`; C-draft `clinical-content-tables-review.md:43` | Territories, Q waves/R progression, ST-T, priors | R-ISCH, R-CHRONIC | **Covered, gated** M8.8–8.13 (`:294-299`). |
| `anterior_mi` | A: `ECG_PLATFORM_SPEC.md:337`; C-draft `clinical-content-tables-review.md:44` | Anterior/septal precordial territories | R-ISCH | **Covered** M8.4 (`:290`), with chronic/acute separation. |
| `inferior_mi` | A: `ECG_PLATFORM_SPEC.md:338`; C-draft `clinical-content-tables-review.md:45` | II/III/aVF and reciprocal/right-sided checks | R-ISCH | **Covered** M8.5 (`:291`). |
| `lateral_mi` | A: `ECG_PLATFORM_SPEC.md:339`; C-draft `clinical-content-tables-review.md:46` | I/aVL/V5–V6 territory | R-ISCH | **Covered** M8.4 (`:290`). |
| `septal_mi` | A: `ECG_PLATFORM_SPEC.md:340`; C-draft `clinical-content-tables-review.md:47` | V1–V2 territory and mimic caution | R-ISCH | **Covered** M8.4 (`:290`). |
| `posterior_mi` | A: `ECG_PLATFORM_SPEC.md:341`; C-draft `clinical-content-tables-review.md:48` | Anterior mirror pattern + posterior leads | R-ISCH; current pool is sparse | **Covered, gated** M8.6 (`:292`). |
| `qt_interval` | A: `ECG_PLATFORM_SPEC.md:342`; C-draft `clinical-content-tables-review.md:51` | QRS onset/T end, lead selection, repeated beats | R-QT, R-PRECISION | **Covered** M7.5 (`:271`). |
| `qtc_prolongation` | A: `ECG_PLATFORM_SPEC.md:343`; C-draft `clinical-content-tables-review.md:52` | QT measure, rate correction, QRS confound | R-QT, R-CLINREV | **Covered, gated** M7.6–7.8 (`:272-274`). |
| `electrolyte_drug_pattern` | A: `ECG_PLATFORM_SPEC.md:344`; C-draft `clinical-content-tables-review.md:53` | Repolarization/QT/QRS + medication/lab context | R-QT, R-PC, R-CLINREV | **Covered, gated** M7.9–7.12 (`:275-278`). |
| `pericarditis_pattern` | A: `ECG_PLATFORM_SPEC.md:345`; C-draft `clinical-content-tables-review.md:54` | ST/T distribution, PR/baseline, ischemia/variant mimics | R-ISCH, R-PC | **Covered** as a comparison in M7.11/M8.10 (`:277`, `:296`); score only with adequate cases. |
| `incomplete_right_bundle_branch_block` | **C-draft addition:** `clinical-content-tables-review.md:27` | RBBB morphology + width context | R-QRS, R-PC | **Covered** under incomplete conduction in M5.3/M5.5 (`:228`, `:230`). |
| `left_anterior_fascicular_block` | **C-draft addition:** `clinical-content-tables-review.md:29` | Full axis and fascicular vector model | R-AXIS/R-QRS, R-PC | **Covered** M5.6 (`:231`). |
| `left_posterior_fascicular_block` | **C-draft addition:** `clinical-content-tables-review.md:30` | Full axis; exclusion of alternative right-axis causes | R-AXIS/R-QRS, R-PC | **Covered** M5.6 (`:231`). |
| `wolff_parkinson_white` | **C-draft addition:** `clinical-content-tables-review.md:31` | PR, delta wave, fused wide QRS, tachy context | R-QRS/R-PR, R-PC | **Covered** M5.8 (`:233`), reused in M6. |
| `paced_rhythm` | **C-draft addition:** `clinical-content-tables-review.md:32` | Spike timing, chamber, capture/sensing, altered QRS/ST-T | R-QRS; device actions require R-CLINREV | **Covered** M5.9 (`:234`). |
| `premature_ventricular_complex` | **C-draft addition:** `clinical-content-tables-review.md:33` | Prematurity, P relation, QRS width, pause | R-RHYTHM/R-QRS | **Covered** M3.3/M3.5 (`:191`, `:193`). |
| `premature_atrial_complex` | **C-draft addition:** `clinical-content-tables-review.md:34` | Premature abnormal P, QRS/aberrancy, pause | R-RHYTHM | **Covered** M3.3/M3.4 (`:191-192`). |
| `myocardial_ischemia` | **C-draft addition:** `clinical-content-tables-review.md:49` | ST/T evidence, distribution, symptoms/serial context | R-ISCH, R-AUTHCTX | **Covered** M8.7/M8.10–8.13 (`:293`, `:296-299`). |
| `pathologic_q_waves` | **C-draft addition:** `clinical-content-tables-review.md:50` | Q-wave measurement, territory, R progression, prior | R-ISCH, R-PRECISION | **Covered** M8.8 (`:294`). |

### Clinical-table measurement bumps

| Proposed rule | Exact source | Dependency/constraint | V2 coverage |
|---|---|---|---|
| AF/flutter/SVT with HR ≥150 increases teaching acuity one tier | `clinical-content-tables-review.md:58-60` | Requires grounded rhythm + rate and clinician approval (R-RHYTHM, R-CLINREV) | **Partial.** M6 teaches rate/stability/context, but V2 does not ratify this exact bump. |
| Any rhythm with HR ≤40 increases teaching acuity one tier | `clinical-content-tables-review.md:58-60` | Requires grounded rate, rhythm, perfusion context, and clinician approval | **Partial.** M4.10 covers perfusion-aware bradycardia; exact bump remains governance. |
| Supported QTc ≥500 ms increases teaching acuity one tier | `clinical-content-tables-review.md:61` | R-QT plus clinician-reviewed threshold and wide-QRS handling | **Partial.** M7.7 explicitly requires numeric-policy sign-off (`V2:273`). |

## 5. Foundations: authoritative detailed instructional requirements

The root minimum names topics; the v7 storyboard and v1.5 Guide/Text define how the first module must teach them. The `F-*` rows are therefore source-authoritative for M1 unless explicitly adjudicated.

| ID | Required content or behavior | Exact source | Dependency | Corpus/reliability | V2 coverage |
|---|---|---|---|---|---|
| F-01 | Audience is a complete beginner; outcome is an independent descriptive sweep. | `foundations/MODULE_GUIDE.md:26-32`; `storyboard-foundations.md:3-11` | None | None | **Covered** by M1 outcome `V2:143-145`. |
| F-02 | Describe and measure before diagnosing; use finding-language and treat “not assessable” as valid. Clinical causes, danger, diagnoses, and urgency are deferred. | `MODULE_GUIDE.md:28-31`, `:139-142`; `storyboard-foundations.md:3-11`, `:74-78` | Applies throughout M1 | R-LLM; no acute cases | **Covered with a boundary change.** M1 remains descriptive (`V2:145`), but V2 adds bedside consequences; those must not become diagnosis/action teaching in M1. |
| F-03 | 13 scenes, four self-paced parts, progress/resume, scene/part skip or test-out; skip is not mastery. | `MODULE_GUIDE.md:32`; `:133-135`; `storyboard-foundations.md:87-89` | Navigation/state | None | **Covered conceptually** by V2 grammar/state `:34-45`, `:51-59`, but the duration changes; see conflicts. |
| F-04 | ECG is voltage over time; P = atrial activation, QRS = rapid ventricular activation, T = ventricular recovery; AV delay/flat PR segment and P/QRS size differences are taught physiologically. | `MODULE_TEXT.md:26-43`, `:151-154`; `storyboard-foundations.md:107-115` | None | Synthetic causal animation + real freeze (R-SYNTH) | **Covered** M1.1 `V2:150`. |
| F-05 | The wavefront animation must be scrubbable/replayable and followed by active P/QRS/T labeling, not passive watching. | `storyboard-foundations.md:107-115`, `:235-244` | F-04 | R-SYNTH | **Covered** in M1.1 interaction `V2:150`; V2 accessibility rules require pause/skip/keyboard `:59`. |
| F-06 | Grid calibration: small box 40 ms and 0.1 mV; big box 200 ms; calibration pulse habit; time and voltage taught separately. | `MODULE_TEXT.md:45-51`, `:183-193`; `storyboard-foundations.md:117-123` | P/QRS/T identified | R-VIEW | **Covered** M1.2 `V2:151`; exact normal-value card remains inherited from source. |
| F-07 | Everyday measurement order is eyeball/count boxes → read and verify printed measurement → optional calipers only near a cutoff. | `storyboard-foundations.md:54-59`; `MODULE_TEXT.md:19`, `:51` | Calibration/grid | R-PRECISION | **Covered** in M1.2/M1.6 and machine comparison (`V2:151`, `:155`); retain optional-caliper emphasis. |
| F-08 | Signal quality is task-specific: decide “readable for what,” classify multiple real strips, box artifact, and do not force PR/ST-T when noise obscures them. | `MODULE_TEXT.md:53-58`; `MODULE_GUIDE.md:80-81`; `storyboard-foundations.md:125-129` | Grid/waves | R-A, quality flags; R-FOUND22 | **Covered** M1.3 `V2:152`. |
| F-09 | Regularity is checked before choosing the rate method; 300 rule for regular rhythms, six-second ×10 for irregular rhythms; normal 60–100; estimate against grounded value with tolerance. | `MODULE_TEXT.md:60-65`, `:157`; `storyboard-foundations.md:132-139` | Calibration + QRS detection | R-RHYTHM | **Covered** M1.4/M3.1 `V2:153`, `:189`. |
| F-10 | Sinus criteria: P before every QRS, QRS after every P, upright P in II, same P shape beat-to-beat, constant PR; rate is not part of the definition; aVR P is usually inverted. | `MODULE_TEXT.md:67-72`, `:89-95`; `storyboard-foundations.md:141-148`, `:174-181` | Rate/regularity + P recognition | R-RHYTHM; tiled rhythm strips require cautious “sinus-appearing” wording (`MODULE_GUIDE.md:11-16`, `:69`) | **Covered** M1.5/M1.8 `V2:154`, `:157`; M3.2 deepens it. |
| F-11 | PR is start of P to start of QRS, normal 120–200 ms; measure on a real beat and describe normal/long/short without diagnosing. | `MODULE_TEXT.md:74-78`, `:155`, `:187`; `storyboard-foundations.md:150-156` | P/QRS boundaries + grid | R-PR, R-PRECISION | **Covered** M1.6 `V2:155`, M4.2. |
| F-12 | QRS is first deflection to final return to baseline; normal <120 ms/narrow, ≥120 ms/wide; relate narrowness to His–Purkinje activation. | `MODULE_TEXT.md:74-78`, `:188`; `storyboard-foundations.md:150-156` | QRS anatomy + grid | R-QRS, R-PRECISION | **Covered** M1.6/M5.1–5.2 `V2:155`, `:226-227`. |
| F-13 | ST segment starts at the J point and is judged against the TP baseline; near-baseline is normal-appearing, and small elevation can be normal. | `MODULE_TEXT.md:80-87`, `:161`, `:189`; `storyboard-foundations.md:159-164` | QRS end/baseline | R-A; abnormal etiology deferred | **Covered** M1.7 `V2:156`, deepened in M7.2. |
| F-14 | T wave is repolarization and is usually concordant where QRS is dominant upright; aVR and V1 are common normal exceptions. | `MODULE_TEXT.md:84-86`, `:165`, `:190`; `storyboard-foundations.md:165-166` | QRS direction + lead identity | R-A | **Covered** M1.7/M7.1 `V2:156`, `:267`. |
| F-15 | QT runs QRS onset to T end and changes with rate; QTc is previewed, not fully taught or measured in Foundations. | `MODULE_TEXT.md:84-86`, `:162`, `:191`; `storyboard-foundations.md:167-168` | QRS/T boundaries + rate | R-QT; no fine precision at 100 Hz | **Covered** M1.7 `V2:156`, full treatment M7. |
| F-16 | Assemble a summonable normal-reference/template as concepts are learned. | `storyboard-foundations.md:66-67`, `:159-170`; `MODULE_TEXT.md:183-193` | F-06, F-09–F-15 | R-NORMAL | **Partial.** M1.7 assembles the template (`V2:156`), but the persistent progressive normal-values card is not restated in V2. Source remains governing. |
| F-17 | Twelve leads are simultaneous views of one cardiac event; rhythm strip II is used for rate/rhythm. | `MODULE_TEXT.md:89-95`; `storyboard-foundations.md:174-181` | Single-beat concepts | R-VIEW | **Covered** M1.8/M2 `V2:157`, `:163-180`. |
| F-18 | Normal R-wave progression: R grows, S shrinks, and transition is first lead with R>S, commonly V3–V4; abnormal progression is deferred. | `MODULE_TEXT.md:89-95`, `:163`, `:192`; `storyboard-foundations.md:174-181` | Precordial lead order | R-A; placement/rotation caveats later | **Covered** M1.8/M2.9–2.10 `V2:157`, `:178-179`. |
| F-19 | Basic axis is net ventricular-depolarization direction; I+aVF both positive is a coarse normal screen; I positive/aVF negative is leftward and needs lead II refinement; clearly I negative/aVF positive is rightward. | `MODULE_TEXT.md:97-103`, `:159`, `:193`; `storyboard-foundations.md:183-194` | Limb leads + QRS polarity | R-AXIS | **Covered** M1.9/M2.7–2.8 `V2:158`, `:176-177`. |
| F-20 | Axis must be learned through a draggable hexaxial vector with live limb-lead polarity and a visually consistent normal sector, not only a mnemonic. | `storyboard-foundations.md:183-194`, `:235-244` | F-19 | R-SYNTH for causal model; R-A for real transfer | **Covered as target** M1.9/M2.7 `V2:158`, `:176`. |
| F-21 | The standard beginner sweep is calibration/quality then Rate → Rhythm → Axis → PR/intervals → QRS/morphology → ST-T → Synthesis. | `MODULE_GUIDE.md:28-31`, `:93-96`; `MODULE_TEXT.md:105-116`; `storyboard-foundations.md:19-23`, `:198-207` | All prior M1 concepts | R-A | **Covered** M1.10 `V2:159`; M9 supports alternative framework mapping. |
| F-22 | Modeled examples are active predict-before-reveal, use no more than two real ECGs, highlight evidence as named, and include normal plus a describable deviation. | `storyboard-foundations.md:199-207`; `MODULE_GUIDE.md:93-95` | F-21 | R-A, R-FOUND22 | **Covered** M1.10 `V2:159`. |
| F-23 | Guided practice fades across 2–3 real cases; answers are meaning-graded per component; corrections reason back on the trace; axis receives repeated practice; correct-but-ahead answers are credited. | `storyboard-foundations.md:209-218`; `MODULE_GUIDE.md:94-96`, `:105-109` | Modeled sweep | R-A, R-LLM | **Covered as target** M1.11 and grammar `V2:38-45`, `:160`; pilot gate `:348` prevents MCQ substitution. |
| F-24 | Independent release uses one rail-visible solo case and one blank read; tutor is silent unless asked; score components separately and teach uncertainty. | `storyboard-foundations.md:220-231`; `MODULE_TEXT.md:126-136` | Guided practice | R-A; independent evidence required | **Covered** M1.12 `V2:161`; general mode contract `:92-96`. |
| F-25 | Checkpoints test the actual action: label, box-count, classify quality, choose rate method, identify sinus, measure PR/QRS, restore ST, identify transition/axis, then graded reads. | `MODULE_GUIDE.md:113-129`; interaction inventory `storyboard-foundations.md:235-244` | Scene-specific | R-A/R-VIEW/R-PRECISION | **Covered by detailed M1 storyboard**, but V2 itself defers exact legacy thresholds to source. Pilot gate `V2:348` preserves the action requirement. |
| F-26 | Tutor is persistent, warm, brief, visually demonstrative, and returns to the paused lesson; in independent practice it is learner-invoked. | `storyboard-foundations.md:82-95`; `MODULE_TEXT.md:17-20`, `:140-167` | Exact scene state | R-LLM | **Conflict/intentional expansion.** Source says “won't leap ahead” and only taught concepts (`storyboard:92-95`); V2 permits broader safe educational tangents with epistemic separation (`V2:76-86`). User intent favors V2, but this should be ratified as a superseding rule. |
| F-27 | Free text is graded on meaning, numbers/box units/comparators, partial components, negation, and conditional ahead-credit—not keywords. | `storyboard-foundations.md:82-86`, `:209-218`; `MODULE_GUIDE.md:105-107`; `MODULE_TEXT.md:171-179` | Grounded rubric/synonym map | R-LLM; regression answers needed | **Covered as target** in M1.11 and Explain stage (`V2:41`, `:160`), but source remains the detailed rubric. |
| F-28 | Error tone is show-don't-scold; wrong work is re-offered with a trace-based explanation. | `storyboard-foundations.md:85-86`; `MODULE_TEXT.md:118-124`, `:131-135` | Feedback system | R-LLM/R-A | **Covered** grammar feedback/equivalent retry `V2:41`, `:56`. |
| F-29 | Every drag interaction needs a non-drag/tap/keyboard alternative before broader release. | `MODULE_GUIDE.md:22`, `:145-155` | Accessibility | None | **Covered and elevated** to a general V2 requirement `:59`, pilot gate `:345`. |
| F-30 | Real-data use is explicit: synthetic for manipulable causal tools, real median beats for measurement, real 12-leads for practice, real quality-flagged records for artifact. | `storyboard-foundations.md:19-23`, `:246-253`; `MODULE_GUIDE.md:54-71` | Case contract per scene | R-A, R-SYNTH, R-FOUND22 | **Covered** V2 realism/data rules `:129-137` and M1 scene contracts. |

## 6. Product-wide instructional contracts

| ID | Requirement | Exact source | Dependency/constraint | V2 coverage |
|---|---|---|---|---|
| P-01 | AI is the learning operating system: it guides tutorials, controls the viewer, asks questions, gives feedback, identifies weakness, and selects future cases; it must not feel like a chatbot add-on. | `ECG_PLATFORM_SPEC.md:3-20` | R-LLM | **Covered** through the AI contract, competency selector, and handoffs `V2:61-127`. |
| P-02 | Deterministic data/curation, not the LLM, is the source of diagnoses, measurements, fiducials, lead findings, and ROIs. | `ECG_PLATFORM_SPEC.md:18-22`, `:289-301`; `RESEARCH_AND_PRODUCT_PLAN.md:3-5`, `:27-33` | R-LLM | **Covered** `V2:74`, `:129-137`. |
| P-03 | Every guided lesson includes concise explanation, viewer interaction, useful AI highlight/zoom/annotation, an annotation/text task, immediate feedback, and mastery/profile update. | `ECG_PLATFORM_SPEC.md:604-616` | R-A, R-VIEW, R-LLM | **Covered as storyboard grammar** `V2:32-45`; pilot gate `:348` rejects prose-only substitution. |
| P-04 | The ECG viewer is an instructional instrument: actual waveform, 12-lead grid/labels, correct time/amplitude, zoom/pan/reset, lead/ROI highlight, calipers, click/drag annotation, coordinates, and structured AI actions. | `ECG_PLATFORM_SPEC.md:491-600` | R-VIEW | **Partial in V2 text.** Calibration, geometry, visibility, and validated actions are preserved (`V2:129-137`), but the exact source capability list remains governing. |
| P-05 | Invalid/unavailable AI viewer actions are ignored safely with a warning. | `ECG_PLATFORM_SPEC.md:547-600` | R-LLM/R-VIEW | **Covered conceptually** by “validated, currently visible actions” `V2:81`, case contracts `:347`; warning behavior is not explicit. |
| P-06 | Support both a standard clerkship framework and a coherent HEARTS-style framework; the tutor adapts to the learner's choice. | `ECG_PLATFORM_SPEC.md:669-695` | Complete basic sweep | **Covered** M9.0 `V2:307`. |
| P-07 | Rapid practice hides answers, collects structured/free-text interpretation plus confidence, grades against grounded evidence, gives concise highlighted feedback, updates profile, reveals teaching, and selects adaptively. | `ECG_PLATFORM_SPEC.md:699-719`; `RESEARCH_AND_PRODUCT_PLAN.md:7-12` | R-B, R-LLM, no answer leakage | **Covered at contract level** in tutor modes/hand-offs/M9 `V2:88-127`, `:310`, `:317-318`; detailed Rapid behavior remains a separate mode requirement. |
| P-08 | Concept practice includes normal, MI, ST-T, conduction/BBB, axis, chamber, brady/tachy, AF/flutter, AV block, and QT; unsupported concepts are unavailable rather than forced. | `ECG_PLATFORM_SPEC.md:722-741`; `RESEARCH_AND_PRODUCT_PLAN.md:9-12` | R-PC | **Covered** across M1–M8 and data gates `V2:18-30`, `:113`, `:137`. |
| P-09 | Learner evidence includes correctness, confidence, time, hints, ROI accuracy, misconceptions, recency, trend, and per-objective mastery. | `ECG_PLATFORM_SPEC.md:745-759` | Shared attempt model | **Covered and strengthened** to `concept × subskill` `V2:98-113`; streak/trend is not explicit in V2. |
| P-10 | Mastery rewards correct independent work more than hinted work, penalizes wrong/high-confidence wrong work, and prioritizes staleness and repeated misses. | `ECG_PLATFORM_SPEC.md:761-785` | Valid independent/assisted evidence separation | **Covered and strengthened** `V2:100-113`. |
| P-11 | Avoid duplicate cases; use reliability, diversity, recency, prior exposure, hint level, response time, confidence, and near-mimic errors for selection. | `ECG_PLATFORM_SPEC.md:773-785`; `RESEARCH_AND_PRODUCT_PLAN.md:12` | Adequate diverse Tier A/B pools | **Covered** `V2:111-113`. |
| P-12 | Tutor input includes mode, lesson/module, case packet, evidence, learner profile, viewer state, learner message/answer, action schema, and grounding constraints. | `ECG_PLATFORM_SPEC.md:830-844` | R-LLM | **Covered and made scene-specific** by waypoint contract `V2:63-74`. |
| P-13 | Tutor output is schema-validated and includes message/feedback, viewer actions, objective updates, misconceptions, uncertainty, and suggested next step; failures degrade safely. | `ECG_PLATFORM_SPEC.md:846-867` | R-LLM | **Partial.** V2 specifies pedagogic behavior and epistemic sources, but not this full transport/fallback schema. Root spec remains governing. |
| P-14 | Tutor explains at clerkship level, uses available visual evidence only, asks Socratic questions in tutorials, stays concise in Rapid, names uncertainty, and avoids individualized clinical advice. | `ECG_PLATFORM_SPEC.md:869-883` | R-LLM | **Covered** `V2:76-96`. |
| P-15 | Tutorial UI shows viewer, active lesson step, integrated tutor, question, feedback, progress, and previous/next; the viewer is the visual focus and UI is uncluttered/laptop-tablet usable. | `ECG_PLATFORM_SPEC.md:966-976`, `:1014-1029` | R-VIEW | **Covered** screen design `V2:47-59`. |
| P-16 | Fixture fallback remains usable but is clearly labeled non-clinical; dataset status distinguishes it from real PTB-XL/PTB-XL+. | `ECG_PLATFORM_SPEC.md:1095-1100`; `RESEARCH_AND_PRODUCT_PLAN.md:14-25`, `:35-38` | R-SYNTH | **Covered and tightened** `V2:135-137`; simulated assessment still requires explicit validation. |

### Required misconception targets

Every misconception below is explicitly required to feed adaptive practice (`ECG_PLATFORM_SPEC.md:789-806`).

| Misconception | Exact source | V2 location/coverage |
|---|---|---|
| Flutter confused with sinus tachycardia | `ECG_PLATFORM_SPEC.md:793` | **Covered** M6.3/M6.5 `V2:249`, `:251`. |
| AF missed by focusing only on rate | `ECG_PLATFORM_SPEC.md:794` | **Covered** M6.6 `V2:252`. |
| MI overcalled from nonspecific ST-T change | `ECG_PLATFORM_SPEC.md:795` | **Covered** M7.4/M8.7/M8.10 `V2:270`, `:293`, `:296`. |
| ST elevation recognized but localized incorrectly | `ECG_PLATFORM_SPEC.md:796` | **Covered** M2.6/M8.2–8.6 `V2:175`, `:288-292`. |
| Reciprocal changes ignored | `ECG_PLATFORM_SPEC.md:797` | **Covered** M8.1–8.2 `V2:287-288`. |
| LBBB and RBBB confused | `ECG_PLATFORM_SPEC.md:798` | **Covered** M5.2–5.5 `V2:227-230`. |
| QT used instead of QTc | `ECG_PLATFORM_SPEC.md:799` | **Covered** M7.5–7.7 `V2:271-273`. |
| Limb leads misused for axis | `ECG_PLATFORM_SPEC.md:800` | **Covered** M2.3–2.8 `V2:172-177`. |
| AV-block types confused | `ECG_PLATFORM_SPEC.md:801` | **Covered** M4.3–4.7 `V2:209-213`. |
| Wide QRS missed | `ECG_PLATFORM_SPEC.md:802` | **Covered** M1.6/M5.1 `V2:155`, `:226`. |
| Paced rhythm or artifact confused with arrhythmia | `ECG_PLATFORM_SPEC.md:803` | **Covered** M3.8/M5.9/M6.9 `V2:196`, `:234`, `:255`. |
| Normal variants under-recognized | `ECG_PLATFORM_SPEC.md:804` | **Covered** M2.10/M7.3/M9.2 `V2:179`, `:269`, `:309`. |

## 7. Clinical Decisions instructional and safety requirements

Clinical Decisions is a separate learning mode, but M9 must prepare and connect to it. **Partial** below is acceptable only when the referenced clinical storyboard remains an active governing specification; it is not permission to discard the requirement.

### 7.1 Core learning construct, data boundary, and question types

| ID | Requirement | Exact source | Dependency/corpus constraint | V2 coverage |
|---|---|---|---|---|
| C-01 | Cases are situation-framed and reasonably timed; context changes stakes and framing. | `docs/storyboard-clinical-case.md:9-17`, `:22-40` | R-AUTHCTX; final clock rule is C-37 below | **Covered** M9 clinic/ward/ED chapters `V2:301-318`. |
| C-02 | The answer is the decision/action, not merely the diagnosis; teach the ECG → implication/cause hypothesis → action chain. | `storyboard-clinical-case.md:13-16` | Recognition must remain separately scored | **Covered** M9.1/M9.3–9.7 `V2:308`, `:310-314`. |
| C-03 | Wrong calls receive waveform-based reason-me-back with the visible discriminator, not a detached red X. | `storyboard-clinical-case.md:15`, `:93-100` | R-A/R-LLM; accepted geometry | **Covered** general feedback contract `V2:56`, tutor contract `:90-96`. |
| C-04 | Selection is adaptive and grounded; the tutor cannot invent findings. | `storyboard-clinical-case.md:16`, `:93-100` | R-PC/R-LLM | **Covered** `V2:98-127`. |
| C-05 | Clinic/ward/ED-non-arrest use only findings supported by the resting corpus; acute/code is a separate pluggable lane. | `storyboard-clinical-case.md:22-40` | R-CHRONIC/R-STAFF | **Covered, gated** M8.13/M9.5/M9.8 `V2:299`, `:312`, `:315`. |
| C-06 | Acuity is a teaching signal, stored separately from real-patient risk; concept base + grounded measurement/context can adjust it. | `storyboard-clinical-case.md:44-50` | R-CLINREV; unsigned table | **Partial.** M4/M6/M9 connect stability and consequence, but V2 does not reproduce the acuity schema. |
| C-07 | Stepwise read → disposition: rate, rhythm, axis, intervals, ST-T, cause hypothesis, action; wrong step receives a re-explain turn. | `storyboard-clinical-case.md:54-58` | Full sweep + reviewed action rubric | **Partial.** M9 stages decisions, but this exact question contract remains in the Clinical storyboard. |
| C-08 | Single-best-answer items may ask rhythm, finding, next step, or territory; distractors must be grounded sibling concepts false for that case. | `storyboard-clinical-case.md:58`; strengthened `:197-200` | R-AUTHCTX/R-CLINREV | **Partial.** V2 requires target/mimic/normal and case contracts (`:39`, `:347`), not the full MCQ generator rubric. |
| C-09 | Click-the-abnormality is graded by ROI geometry and accepted leads, not a diagnosis-only key. | `storyboard-clinical-case.md:59`; scoring lock `:224-228` | R-VIEW; visible/valid ROI | **Partial.** V2 repeatedly requires marking/clicking and target geometry (`:40`, `:340`, `:347-348`); per-type axis schema remains external. |
| C-10 | Triage uses act-now/work-up/routine calibration with over- and under-triage consequences. | `storyboard-clinical-case.md:60` | R-CLINREV and authored stability context | **Partial.** M6.0/M9 prioritize stability, but exact triage scoring remains external. |
| C-11 | Serial comparison asks “what changed?” and may include a present-to-attending plan. | `storyboard-clinical-case.md:61` | Requires true comparable prior/serial ECGs; R-CHRONIC | **Covered, gated** M8.11/M9.5/M9.9 `V2:297`, `:312`, `:316`. |
| C-12 | Name-the-rhythm free text is meaning-graded with near-miss coaching. | `storyboard-clinical-case.md:62` | R-RHYTHM/R-LLM | **Covered conceptually** M3/M6 Explain/Transfer; exact free-text rubric is not explicit. |
| C-13 | “Prove it”: given a finding, choose the most diagnostic lead/region. | `storyboard-clinical-case.md:64-65` | R-VIEW plus accepted-lead geometry | **Covered conceptually** throughout M2/M5/M8; pilot gate `V2:348` requires actual localization. |
| C-14 | Spot-the-error audits a machine statement and requires visible proof. | `storyboard-clinical-case.md:66`; full display rule `:260-261` | Full 12-lead unless construct narrows it | **Covered** M9.2 `V2:309`; M9.7 also critiques a device label. |
| C-15 | First-action/order-the-steps teaches prioritization, not just final disposition. | `storyboard-clinical-case.md:67` | R-CLINREV | **Partial.** M4.10/M6.11/M9 stage action categories, but V2 does not retain the order-task contract. |
| C-16 | Confidence accompanies answers and high-confidence wrong work is penalized. | `storyboard-clinical-case.md:68`; final scoring lock `:240-243` | Confidence must be committed before reveal | **Covered** competency model and M6/M9 `V2:100-113`, `:258`, `:317`. |
| C-17 | “What would change your mind?” asks for the next datum—prior, troponin, potassium, rhythm strip—that changes the decision. | `storyboard-clinical-case.md:69` | Context must be authored and evidence-layered | **Covered** M3.10/M4.9/M7.12/M9.4–9.6 `V2:198`, `:215`, `:278`, `:311-313`. |
| C-18 | Old-or-new is a real comparison task, not a binary guess. | `storyboard-clinical-case.md:70`; later ternary/validity locks `:197-198`, `:224-228`, `:260-261` | Requires comparable full 12-leads and prior data | **Covered, gated** M8.11/M9.2/M9.5 `V2:297`, `:309`, `:312`. |
| C-19 | Telemetry-alarm triage uses rhythm streams to distinguish respond/watch/artifact. | `storyboard-clinical-case.md:71` | R-TRANSIENT/R-CHRONIC; separate telemetry corpus | **Covered only as a locked boundary** M9.8 `V2:315`; no scored lane without data. |
| C-20 | Progressive reveal supports commit-and-revise as stem, strip, 12-lead, and labs arrive. | `storyboard-clinical-case.md:72` | Each layer must declare its source | **Covered conceptually** M4.9–4.10/M7.12/M9 case chapters; not specified as a reusable question type. |

### 7.2 Generation, tutoring, progression, and usability

| ID | Requirement | Exact source | Dependency/corpus constraint | V2 coverage |
|---|---|---|---|---|
| C-21 | Real, grounded tracing and authored vignette are separate and disclosed. | `storyboard-clinical-case.md:78-89`, `:197-198` | R-AUTHCTX | **Covered** data rules and M9.6 `V2:135-137`, `:312`. |
| C-22 | Clinical items are generated offline from allowed packet claims, then validated; learners never receive unvetted live generation. | `storyboard-clinical-case.md:82-89` | R-LLM/R-CLINREV | **Partial.** V2 demands evidence manifest/provenance/review (`:339-341`, `:347`) but does not restate the pipeline. |
| C-23 | Generation validation checks key support, false distractors, acuity consistency, and ungrounded stem claims; second critique and human review are required before `vetted`. | `storyboard-clinical-case.md:83-89`; strengthened `:197-204` | R-CLINREV | **Partial.** V2 has pilot gates but not the full generator validation/psychometric contract. |
| C-24 | Tutor is silent while answering; afterward it gives a concise grounded explanation, highlights the missed discriminator, supports optional “ask why,” and links errors to modules. | `storyboard-clinical-case.md:93-100` | R-LLM/R-VIEW | **Covered** tutor-by-mode and exact remediation `V2:88-127`, M9.11 `:318`. |
| C-25 | Sessions mix question types, adapt to weak areas, avoid repeats, track mastery/misconceptions, and end with accuracy/time/calibration plus targeted review. | `storyboard-clinical-case.md:104-110` | Sufficient item diversity; valid axes | **Covered conceptually** competency/handoff/M9.10–9.11 `V2:98-127`, `:317-318`. |
| C-26 | Learn is untimed and scaffolded; Shift is timed/mixed; new question types are introduced untimed first. | `storyboard-clinical-case.md:148-149`; do-not-regress `:189`; final clock `:244-258` | Timer accommodations; R-CLINREV | **Covered** tutor modes `V2:90-96`, M9.10; exact onboarding sequence is not explicit. |
| C-27 | Fluent learners may commit the decision first; detailed steps appear after error/low confidence, while beginners retain scaffold. | `storyboard-clinical-case.md:151`, `:170`, `:189` | Difficulty/scaffold state | **Partial.** V2 supports scaffold level/fading (`:34-45`, `:68-71`) but not this decision-first branch explicitly. |
| C-28 | Visual feedback uses calipers/arrows/repeating patterns/territory pulses and trace proof; text is secondary. | `storyboard-clinical-case.md:152`, `:179` | R-VIEW/validated geometry | **Covered as target** grammar and module interactions; pilot gate `V2:348` rejects prose substitutes. |
| C-29 | Use resumable 5-case mini-shifts; mobile uses adequate targets and construct-appropriate lead navigation/comparison. | `storyboard-clinical-case.md:153`, `:176`, `:185`, `:202` | Viewer/display validity | **Partial.** V2 requires ≥44 px and touch alternatives (`:59`, `:345`), but not mini-shift length or portrait comparison behavior. |
| C-30 | Ambiguous/borderline cases and a defensible “insufficient data/get more” option are first-class; disposition can be an acceptable range. | `storyboard-clinical-case.md:157`, `:180`, `:197-198` | Intentional underdetermination must be declared | **Covered conceptually** uncertainty throughout M4/M7/M8/M9; exact answer-class mechanics remain external. |
| C-31 | Tutor depth is tiered: beginner nudge, concise default, expert contestable explanation naming the discriminator. | `storyboard-clinical-case.md:158`, `:181`, `:183` | Scaffold/feedback-depth state | **Partial.** V2 carries scaffold level and mode behavior (`:68-71`, `:88-96`) but does not define expert contestability. |
| C-32 | Timed sets avoid free-text language penalties; terms/idioms have persistent tap-to-define glossary. | `storyboard-clinical-case.md:159`, `:182`, `:258` | Accessibility/ESL fairness | **Partial.** V2 requires minimal timer-appropriate response and accessibility (`:59`, `:317`, `:345`), but glossary is not explicit. |
| C-33 | Calibration is surfaced separately from clinical safety; confidence locks before reveal and insufficient-data receives no speed bonus. | `storyboard-clinical-case.md:197-201`, `:240-243` | Per-axis grading | **Partial.** V2 separates confidence calibration (`:100-109`, `:317`) but not all anti-gaming rules. |
| C-34 | Difficulty is a vector—ECG complexity, ambiguity, time, scaffold, feedback depth—even if UI exposes only Learn/Shift. | `storyboard-clinical-case.md:201` | Selector/competency model | **Covered conceptually** by V2 state and adaptive selector `:68-71`, `:111-113`. |
| C-35 | Full 12-lead is the default; rhythm-only/zoom views are allowed only when the tested construct permits. | `storyboard-clinical-case.md:208-214`, `:260-261` | R-VIEW; display spec declares tested scope | **Covered** V2 case-contract and visibility rules `:132`, `:347`. |
| C-36 | Acute language and urgency cannot be manufactured from a chronic tracing; current ED content must remain honest. | `storyboard-clinical-case.md:154`, superseded/strengthened by `:231-239` | R-CHRONIC/R-AUTHCTX | **Covered, gated** V2 `:137`, M8.13/M9.5 `:299`, `:312`. |
| C-37 | Situation-scaled timing: timer starts only after pixels/controls/stem are present; Learn unlimited; clinic/ward/ED/code have distinct walls; response and confidence time are separate; accommodations scale time without lowering skill. | `storyboard-clinical-case.md:214`, `:244-258` | Final rule; overrides earlier opt-in split clock | **Partial.** V2 specifies 20-second quick-look and timer appropriateness (`:258`, `:310`, `:317`) but not the full clock table. Clinical storyboard remains governing. |

### 7.3 Grading and honesty hard-stops

| ID | Requirement | Exact source | Dependency/constraint | V2 coverage |
|---|---|---|---|---|
| C-38 | Compound clinical options are parsed into components; parallel safety action can preserve high credit while delayed action cannot. | `storyboard-clinical-case.md:220-224` | R-CLINREV | **Not explicit.** V2 defers governed action scoring but does not carry this parser rule. Keep Clinical source active. |
| C-39 | Grading is question-type-specific: decision classes for MCQ/triage/stepwise; ROI axes for click; comparison validity for old/new. | `storyboard-clinical-case.md:224-228` | Typed scoring schema | **Partial.** V2 tracks subskills and separate axes (`:100-109`) but not each question schema. |
| C-40 | Distractors are plausible, same-specificity, wrong for a visible reason, defensible elsewhere, and safe to teach against. | `storyboard-clinical-case.md:229`, `:197-200` | Rule-backed/human-reviewed discriminator | **Covered at high level** by target/mimic/normal (`V2:39`, `:121`); detailed rubric remains external. |
| C-41 | Acute/evolving/new/dynamic language requires serial change, an acute-data source, or a prior showing newness. | `storyboard-clinical-case.md:231-233` | R-CHRONIC/R-STAFF | **Covered, gated** M8.11–8.13/M9.5 `V2:297-299`, `:312`. |
| C-42 | Symptom-causality strength is concept-specific; low-acuity findings cannot be keyed as causes without supporting evidence. | `storyboard-clinical-case.md:234` | R-CLINREV/R-AUTHCTX | **Partial.** V2 repeatedly separates ECG description from context, but exact causality matrix remains unsigned. |
| C-43 | Transient-event claims require telemetry/rhythm-strip or explicit authored evidence and cannot inflate ECG-recognition mastery. | `storyboard-clinical-case.md:235` | R-TRANSIENT | **Covered, gated** M6.9–6.10/M9.8 `V2:255-256`, `:315`. |
| C-44 | Every ECG-support claim binds to objective, measurement threshold when needed, accepted leads/ROI, and source type; unbound acute/territorial adjectives are rejected. | `storyboard-clinical-case.md:236` | R-AUTHCTX/R-VIEW | **Covered** V2 epistemic source split and case-contract gate `:74`, `:340`, `:347`. |
| C-45 | High-acuity concepts require reviewed safety-action tokens in ideal/acceptable options. | `storyboard-clinical-case.md:237` | R-CLINREV | **Not explicit.** V2 says governed content is required before action scoring (`:257`, `:339`) but not the token matrix. |
| C-46 | Action urgency is capped by ECG concept unless extra evidence supports escalation. | `storyboard-clinical-case.md:238` | R-CLINREV/R-AUTHCTX | **Partial.** V2 teaches context/uncertainty but does not retain the cap table. |
| C-47 | Insufficient-data credit depends on intentional underdetermination and simultaneous safety action; confidence scoring is separate and properly bounded. | `storyboard-clinical-case.md:240-243` | Typed manifest and confidence lock | **Partial.** V2 values insufficient data and confidence but not the numeric/avoidance rules. |
| C-48 | Universal click records lead/panel/time/amplitude/beat/viewport; target may be point, interval, segment, territory, or lead panel; mobile requires confirm behavior. | `storyboard-clinical-case.md:260-261` | R-VIEW | **Partial.** V2 requires target geometry and input alternatives (`:59`, `:347-348`) but not the full click record. |
| C-49 | Hard stop: do not ship until compound parsing, safe complete-block handling, insufficient-data logic, comparison validity, ROI scoring, acute/transient evidence checks, acuity caps, clock rules, and tested-scope rules are enforced. | `storyboard-clinical-case.md:263-269` | R-CLINREV | **Covered as governance intent** by V2 pilot gates `:335-348`, but the source remains the detailed hard-stop list. |

## 8. V2 additions beyond the historical minimum

These are not defects. They are useful expansions, but they should be labeled so a later author knows which material came from the original authority and which was added during the nine-module synthesis.

| V2 area | Addition beyond the root 16-topic minimum | Provenance classification |
|---|---|---|
| M1 | Lead-reversal preview inside “Readable for what?” and a 50–70 minute duration | **Resolved in favor of the validated source.** Lead-misplacement remains in M2 where it has a spatial/acquisition payoff; M1 keeps the ~25-minute core promise and distinguishes optional tutor/retry time. |
| M2 | Electrode-versus-lead distinction, vector projection/dot-product intuition, full lead placement, reversal, body-habitus/rotation/age/sex/athlete variants | **Pedagogic expansion.** Root lead anatomy/axis supports the domain; Foundations physiology supports vector intuition, but this depth is V2-authored. |
| M3 | PAC/PVC, escape beats, pauses, patterned ectopy, and artifact mimic | **Source-supported expansion.** These were absent from the canonical minimum list but present in the clinical table (`:33-34`) and clinical-mode needs. |
| M4 | Nodal-versus-infranodal mechanism, 2:1 uncertainty, escape-focus comparison, reversible-cause/context map, and AHA action-category case | **Mixed.** AV-block variants are canonical; detailed mechanism/context/action progression is V2 expansion and action scoring is clinician-governed. |
| M5 | Fascicular blocks, combined conduction, pre-excitation, pacing capture/sensing, low voltage, and nuanced chamber mimics | **Source-supported expansion** for fascicles/WPW/pacing via the clinical table (`:29-32`); low-voltage and combined-conduction depth are V2 elaborations. |
| M6 | Automaticity/triggered activity/reentry, focal atrial tachycardia, AVNRT/AVRT, MAT, mono/polymorphic WCT, torsades preview, and reviewed action algorithm | **V2 enrichment with safety-source support.** AF/flutter/SVT/WCT are canonical; exact subtypes/mechanisms are not historical minima. Transient rhythms remain data-gated. |
| M7 | Recovery-vector model, early-repolarization/juvenile variants, tangent/threshold QT methods, Bazett-versus-Fridericia behavior, JT/wide-QRS handling, medication licensing workflow, and K/Ca/Mg causal experiments | **V2 enrichment.** QT/QTc, drug/electrolyte, ST/T, and pericarditis are canonical; this depth and formula selection are later additions requiring clinical/numeric review. |
| M8 | Injury-vector simulation, right-sided/posterior leads, occlusion criteria governance, large mimic laboratory, and synchronized serial comparison | **Mixed.** MI territories/posterior MI are canonical; right-sided leads, advanced criteria, and serial tooling are V2 expansions and corpus-gated. |
| M9 | Machine-read audit, prioritized communication, staged syncope/QT/chest-pain/device chapters, resuscitation boundary, 20-second handoff, and exact cross-mode remediation | **Source-supported expansion** from the Clinical Decisions storyboard, not from the root guided-minimum list. |

## 9. Conflicts and adjudication decisions

| Conflict | Earlier source | Later/current direction | Required decision |
|---|---|---|---|
| Autonomous curation versus human clinical review | Root spec says there will be no human case curation/validation (`ECG_PLATFORM_SPEC.md:26-32`). | Clinical design requires human-reviewed distractors/content tables (`docs/storyboard-clinical-case.md:83-89`, `:197-204`, `:263-269`); V2 requires human-reviewed scored clinical ECGs and owner/reviewer metadata (`V2:135`, `:339-340`). | Treat autonomous *record selection/confidence gating* as valid, but require human review for clinical policy, action items, generated pilot cases, and disputed morphology. Document this as a superseding governance rule. |
| Mode taxonomy | Original plan lists Guided tutorials, Rapid practice, Concept practice, and Adaptive review (`docs/RESEARCH_AND_PRODUCT_PLAN.md:7-12`); the root spec has no Clinical Decisions mode. | The later clinical storyboard adds Clinical Decisions, while adaptivity becomes an engine across modes (`docs/storyboard-clinical-case.md:1-18`, `:93-110`). | User direction ratifies Guided/Train/Rapid/Clinical as the four learner modes. Preserve adaptive review as cross-mode orchestration rather than a fifth learner-facing mode. |
| Foundations duration | Built source says 13 scenes, ~25 minutes (`foundations/MODULE_GUIDE.md:32`; `docs/storyboard-foundations.md:100-105`). | V2 specified 50–70 minutes (`V2:145`). | **Resolved:** retain the validated ~25-minute core promise; explicitly separate optional tutor tangents, accessibility exploration, and retries. |
| Foundations tangent scope | v7 says answer only what has been taught and “won't leap ahead” (`docs/storyboard-foundations.md:91-95`). | V2 answers broader safe educational tangents while separating general knowledge from current-case evidence (`V2:76-86`). | User intent favors V2. Mark it as an explicit supersession and keep the original no-diagnosis/current-case grounding boundary. |
| Foundations clinical meaning | Source defers causes/significance/urgency (`docs/storyboard-foundations.md:3-11`, `:74-78`). | V2 places a bedside consequence in every scene (`V2:55`, M1 table). | Retain a short relevance bridge, but M1 may not require clinical action or imply diagnosis. Later modules own mechanisms/pathology/urgency. |
| S3 lead-placement content | v7 explicitly removes lead misplacement from the short quality scene (`docs/storyboard-foundations.md:125-129`). | V2 M1.3 previews lead reversal (`V2:152`). | Either move reversal entirely to M2.10 or add an immediate payoff in M1.3; do not leave an unassessed aside. |
| Clinical clock | Early persona revision used an untimed read then opt-in decision clock (`docs/storyboard-clinical-case.md:148-150`; review packet `:19-24`). | User correction and v0.5 lock require situation-scaled timing from interactive render (`docs/storyboard-clinical-case.md:208-214`, `:244-258`). | Resolved: later situation-scaled rule is authoritative. Remove the old split-clock description from future summaries. |
| Acute-data readiness | Clinical storyboard calls STAFF-III “real-data-feasible now” pending ingest (`:28-33`). | V2 keeps acute/serial competence locked until licensed, ingested, curated, reviewed, and validated (`V2:137`, `:299`, `:312`). | V2 is the safer rule. Independently verify license/provenance before treating STAFF-III as available. |
| Synthetic fallback | Root spec allows a clearly labeled realistic fixture when datasets are absent (`ECG_PLATFORM_SPEC.md:1095-1100`). | Clinical design requires real grounded ECGs for the production bank; V2 allows synthetic causal models and only explicitly validated simulation for scoring (`V2:135`). | Fixtures may demonstrate UI/causal models but must not create real-ECG or clinical mastery evidence unless a separate simulation validation standard is approved. |
| Acuity/action values | The clinical table lists exact caps, symptoms, and thresholds. | The same document states it is generated and unsigned (`docs/clinical-content-tables-review.md:1-5`, `:63-65`); V2 requires clinician ownership. | Do not copy values into authoritative module content or scoring until reviewed/versioned. |
| Foundations text version label | `foundations/MODULE_TEXT.md:1` identifies v1.5. | Its footer says v1.4 (`foundations/MODULE_TEXT.md:240`). | Treat the header/Guide chronology as current and fix the stale footer before using version labels in a review packet. |
| Storyboard coverage versus alpha implementation | V2 tables specify direct waveform actions. | V2's own implementation note says the 65-scene alpha often substitutes reveal-chain + MCQ (`V2:10-12`). | Inventory status means storyboard coverage only. A topic is not implemented until its named action on an unseen/equivalent tracing governs completion (`V2:347-348`). |

## 10. Coverage conclusion

1. **No canonical curriculum topic is absent from V2.** All 31 minimum-topic/subtopic rows are Covered or Covered, gated.
2. **All 37 canonical ontology concepts are represented.** The nine additional concepts introduced by the unsigned clinical table are also represented, but their proposed clinical acuity/action policies remain unapproved.
3. **Foundations content is substantially preserved.** The persistent normal-values card is only implicit in V2, and duration, tangent breadth, and the S3 lead-reversal preview require explicit ownership decisions.
4. **V2 does not replace the Clinical Decisions safety specification.** It covers the clinical learning arc, data boundaries, provenance, uncertainty, and remediation, but it does not restate all per-type grading, compound-option, safety-token, acuity-cap, clock, click-record, and generator-validation rules.
5. **The central remaining content risk is not omission; it is authority drift.** Later enrichments, unsigned clinical rules, and alpha MCQs must not be mistaken for historically required or clinically validated content.

## 11. Authoring rule going forward

For every production scene, its authoring record should include:

- source requirement ID(s) from this inventory;
- exact module/scene dependency;
- concept and subskill;
- required interaction and completion evidence;
- real/synthetic/authored-context provenance;
- reliability tier and concept-specific inclusion rule;
- required leads, geometry, measurements, and sampling precision;
- clinical rule owner, version, and reviewer when relevant;
- V2 storyboard line and implementation status;
- explicit statement when the content is an enrichment rather than an authoritative minimum.

This prevents three failure modes: omitting a historical requirement, turning a later draft into accidental authority, or marking a concept “covered” when only its label—not its ECG skill—was implemented.
