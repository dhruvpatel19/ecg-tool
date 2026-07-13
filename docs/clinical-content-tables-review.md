# Clinical Decisions — danger/acuity content tables (clinician review)

*Generated from backend/app/clinical/content_tables.py. Every value is a TEACHING signal, not a patient risk score, and is a first-draft pending clinician sign-off before the item bank scales (storyboard §16G). Edit the verdict column; changes get applied back to the code table.*

Legend — **acuity**: none/low/moderate/moderate_high/high. **cap** (max action urgency without extra evidence): routine < workup < admit < urgent < act_now. **safety**: tokens an ideal/acceptable option MUST include. **symptoms**: may_explain (E) / may_contextualize (C) / must_not_explain (X).

| Concept [id] | Acuity | Action cap | Required safety actions | Symptom causality | Clinician verdict |
|---|---|---|---|---|---|
| Normal ECG [normal_ecg] | none | routine | — | — |  |
| Rate [rate] | none | routine | — | — |  |
| Sinus rhythm [sinus_rhythm] | none | routine | — | — |  |
| Atrial fibrillation [atrial_fibrillation] | moderate | admit | — | palpitations:E, dyspnea:C, lightheadedness:C |  |
| Atrial flutter [atrial_flutter] | moderate | admit | — | palpitations:E, dyspnea:C |  |
| Supraventricular tachycardia [supraventricular_tachycardia] | moderate | urgent | — | palpitations:E, lightheadedness:E, presyncope:E |  |
| Wide-complex tachycardia [wide_complex_tachycardia] | high | act_now | synchronized_cardioversion, defib_pads, act_now | palpitations:E, lightheadedness:E, presyncope:E, syncope:E, chest_pain:C, dyspnea:C |  |
| Bradycardia [bradycardia] | low | admit | — | syncope:C, presyncope:C, dizziness:C, fatigue:C |  |
| First-degree AV block [av_block_first_degree] | low | routine | — | syncope:X, presyncope:X, palpitations:X, dizziness:C |  |
| Mobitz I AV block [av_block_second_degree_mobitz_i] | low | workup | — | — |  |
| Mobitz II AV block [av_block_second_degree_mobitz_ii] | moderate_high | urgent | tcp_ready, call_help, bedside_now | syncope:E, presyncope:E, dizziness:E |  |
| Third-degree AV block [av_block_third_degree] | high | act_now | pacing_pads, tcp_ready, call_help, bedside_now | syncope:E, presyncope:E, dizziness:E, lightheadedness:E, fatigue:C |  |
| Normal axis [axis_normal] | none | routine | — | — |  |
| Left axis deviation [left_axis_deviation] | low | routine | — | — |  |
| Right axis deviation [right_axis_deviation] | low | routine | — | — |  |
| QRS duration [qrs_duration] | low | routine | — | — |  |
| Right bundle branch block [right_bundle_branch_block] | low | workup | — | — |  |
| Left bundle branch block [left_bundle_branch_block] | moderate | workup | — | — |  |
| Incomplete right bundle branch block [incomplete_right_bundle_branch_block] | low | routine | — | — |  |
| Nonspecific intraventricular conduction delay [nonspecific_intraventricular_conduction_delay] | low | workup | — | — |  |
| Left anterior fascicular block [left_anterior_fascicular_block] | low | routine | — | — |  |
| Left posterior fascicular block [left_posterior_fascicular_block] | low | workup | — | — |  |
| Wolff-Parkinson-White (pre-excitation) [wolff_parkinson_white] | moderate | admit | — | — |  |
| Paced rhythm [paced_rhythm] | low | workup | — | — |  |
| Premature ventricular complex (PVC) [premature_ventricular_complex] | low | workup | — | — |  |
| Premature atrial complex (PAC) [premature_atrial_complex] | none | routine | — | — |  |
| R-wave progression [r_wave_progression] | low | routine | — | — |  |
| Left ventricular hypertrophy [left_ventricular_hypertrophy] | low | workup | — | — |  |
| Right ventricular hypertrophy [right_ventricular_hypertrophy] | low | workup | — | — |  |
| Atrial enlargement [atrial_enlargement] | low | routine | — | — |  |
| ST elevation [st_elevation] | high | urgent | — | — |  |
| ST depression [st_depression] | moderate | admit | — | chest_pain:C, dyspnea:C |  |
| T-wave inversion [t_wave_inversion] | low | workup | — | — |  |
| Nonspecific ST-T change [nonspecific_st_t_change] | low | workup | — | chest_pain:C |  |
| Myocardial infarction [myocardial_infarction] | moderate | workup | — | — |  |
| Anterior MI [anterior_mi] | moderate | workup | — | — |  |
| Inferior MI [inferior_mi] | moderate | workup | — | — |  |
| Lateral MI [lateral_mi] | moderate | workup | — | — |  |
| Septal MI [septal_mi] | moderate | workup | — | — |  |
| Posterior MI [posterior_mi] | moderate | workup | — | — |  |
| Myocardial ischemia (ST-T) [myocardial_ischemia] | moderate | admit | — | chest_pain:C |  |
| Pathologic Q waves [pathologic_q_waves] | low | workup | — | — |  |
| QT interval [qt_interval] | low | routine | — | — |  |
| QTc prolongation [qtc_prolongation] | moderate | admit | — | syncope:C, presyncope:C, palpitations:C |  |
| Electrolyte/drug pattern [electrolyte_drug_pattern] | moderate | admit | — | — |  |
| Pericarditis pattern [pericarditis_pattern] | moderate | admit | — | — |  |

*cap marked workup\* = default (concept has no explicit cap entry; cannot be keyed urgent).*

## Measurement-driven acuity bumps (review thresholds)
- AFib/flutter/SVT with heart rate ≥ 150 → +1 tier
- Any rhythm with heart rate ≤ 40 → +1 tier
- QTc ≥ 500 ms (QTc-prolongation supported) → +1 tier

## Sign-off

Reviewer: __________   Date: ______   Overall: ☐ approved  ☐ approved with edits  ☐ needs rework
