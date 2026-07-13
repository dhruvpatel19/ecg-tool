# Autonomous Curation

`backend/app/curation.py` assigns a per-concept reliability tier to every ECG with no human curator. It is conservative: it excludes cases when evidence is missing, discordant, or too weak for student-facing teaching.

## Tiers

- **Tier A** — high-confidence teaching case (tutorials, explicit visual explanation, detailed feedback). Requires **clean signal AND ≥2 concordant concept-level evidence sources** — concordance, not a single label.
- **Tier B** — usable practice case (broad practice, cautious feedback).
- **Tier C** — uncertain/discordant; not student-facing.
- **Tier D** — unsupported; not surfaced.

`supported_objectives` = concepts at Tier A/B with score ≥ 0.58. A case can be Tier A for one concept and Tier D for another — scores are always per-concept.

## Evidence sources (independent, for real concordance)

- **PTB-XL SCP labels** + diagnostic super/subclass (`SCP_TO_CONCEPTS`)
- **PTB-XL+ 12SL SNOMED statements** — an *independent algorithmic* read, so agreement with the SCP labels is genuine concordance (not circular)
- **PTB-XL+ measurements** — `qtc_ms`, `pr_ms`, `axis_deg`, voltages (Sokolow-Lyon/Cornell), per-lead ST
- **PTB-XL report text** keywords
- **Noise-based signal quality** (`static_noise`/`burst_noise`/`baseline_drift`/`electrodes_problems`)

The LLM is explanation-only and cannot change any tier. Fiducial ROIs are **neutral segment locations** and are deliberately **not** used as diagnostic evidence (an ST-segment window exists on every beat; it does not imply ST elevation).

## Concept rules (selected)

- **Normal ECG** — concordant normal label + no major abnormal conflict + acceptable signal + normal rate/QRS/QTc/axis when present.
- **Rate** — grounded directly in a reliable heart-rate measurement (the German reports never contain the English keyword "rate").
- **Axis / PR / AV block** — require the corresponding measurement (`axis_deg` / `pr_ms`); higher-degree AV block also needs an explicit rhythm label.
- **QRS / bundle branch block** — QRS duration + a compatible label/statement; wide QRS alone cannot teach a specific block.
- **ST-T / MI** — require a **real diagnostic label or statement**. Territory subtypes (anterior/inferior/lateral/septal MI) need their own label, *or* a general MI label backed by qualifying ST elevation in that territory's leads. Without a label, the concept is capped at Tier C (this prevents teaching MI on normal ECGs).
- **Hypertrophy** — voltage support (Sokolow ≥ 3.5 mV / Cornell ≥ 2.8 mV adds confidence); taught cautiously on a single weak criterion.
- **QT/QTc** — require an available QTc measurement; prolongation also needs QTc ≥ 480 ms.
- **AF/flutter** — rhythm label/statement support, no contradictory sinus-only claim.
