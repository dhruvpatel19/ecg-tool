# Dangerous-arrhythmia fragment source adapter

The ECG Fragment Database for the Exploration of Dangerous Arrhythmia 1.0.0 is
integrated as a checksum-gated, offline rhythm-recognition source. The adapter
is `backend/app/ingest/dangerous_arrhythmia.py`; the CLI is
`scripts/import_dangerous_arrhythmia.py`.

This dataset is distinct from the full MIT-BIH VFDB adapter. It contains 1,016
short, source-labelled fragments derived primarily from the MIT-BIH Malignant
Ventricular Ectopy Database, with one modified limb lead II signal per
fragment. The source was designed to evaluate arrhythmia-recognition
algorithms, not to reconstruct a clinical resuscitation encounter.

## Hard evidence ceiling

Allowed after runtime review:

- identify the reviewed source rhythm label;
- discriminate waveform alternatives visible in the short MLII sample;
- describe visible single-channel rhythm features.

Always prohibited from this source alone:

- pulse, perfusion, symptoms, stability, arrest, or etiology;
- shockability or an ACLS action category;
- medication, electricity, treatment sequence, response, or management;
- representation as a 12-lead ECG, monitor/defibrillator export, or clinical
  case.

Every disconnected source packet sets only `recognize` and `discriminate`
subskills. Clinical, management, hemodynamic, shockability, action-sequence,
and mastery eligibility are false at import time. A separate, release-audited
promotion step may project an approved subset into the explicit Rapid
`emergency` scope. That projection revalidates every packet, waveform,
fingerprint, opaque identity, source label, mapped learner target, content
index, and manifest hash before allowing exact rhythm recognition evidence.
Ordinary mixed Rapid and every Clinical selector remain unable to discover it.

The current promoted supplement contains 584 MLII fragments: 240 ventricular
fibrillation, 97 ventricular flutter, 175 ventricular tachycardia (169 VTHR +
6 VTLR), and 72 source-labelled VTTdP fragments mapped conservatively to
polymorphic ventricular tachycardia. A VTTdP source code does not establish
torsades de pointes without preceding long-QT evidence.

Patient-state, shockability, and action questions are separately authored,
version-labelled 2025 AHA simulations and remain formative. They never turn a
short rhythm strip into evidence of a pulse, stability, arrest, or management.

## Source integrity and privacy

- Dataset: [ECG Fragment Database for the Exploration of Dangerous Arrhythmia
  1.0.0](https://physionet.org/content/ecg-fragment-high-risk-label/1.0.0/)
- DOI: [10.13026/kpfg-xs25](https://doi.org/10.13026/kpfg-xs25)
- License: ODC Attribution 1.0
- Pinned `SHA256SUMS.txt` SHA-256:
  `3f6f16dd8904c433f049899b6bbef04efccc460ff6196e124e460b162d108dd5`

The importer requires the exact 1,016-entry `RECORDS` release, validates every
header during inventory, and verifies each selected header and signal before
read. Public packet IDs are content-addressed. Original record numbers, start
offsets, paths, and any source identity are not serialized.

## Safe operation

Dry-run inventory:

```powershell
python scripts/import_dangerous_arrhythmia.py
python scripts/import_dangerous_arrhythmia.py --rhythm VF --limit 20
```

Dedicated gated import:

```powershell
python scripts/import_dangerous_arrhythmia.py `
  --rhythm VF --rhythm VFL --rhythm VTHR --rhythm VTTdP `
  --max-per-rhythm 30 `
  --apply `
  --out data/rhythm_sources/dangerous-arrhythmia-v1
```

Packets and single-lead arrays are written to a dedicated `RhythmStreamStore`;
`manifest.json` is the final readiness write. The promotion builder writes a
separate `rapid_rhythm_supplement` only after the exact objective/subskill and
evidence-boundary contracts pass. The production corpus references that
supplement by a pinned runtime-manifest hash; hydration and readiness fail
closed if any file, count, mapping, or fingerprint changes.
