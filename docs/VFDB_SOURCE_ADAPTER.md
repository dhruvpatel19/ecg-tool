# MIT-BIH VFDB real-rhythm source foundation

The MIT-BIH Malignant Ventricular Ectopy Database (VFDB) is connected as an
**offline, foundation-only rhythm-stream source**. The executable adapter is
`backend/app/ingest/vfdb.py`; the gated importer is
`scripts/import_vfdb.py`; packets are written to a dedicated
`RhythmStreamStore`, never to the serving 12-lead `CaseStore`.

This separation is deliberate. It makes real VT/VF/asystole waveforms
available for a future reviewed resuscitation-rhythm lane without silently
unlocking the current Clinical UI or turning an ambulatory ECG into a patient
case.

## Versioned source and attribution

- Dataset: [MIT-BIH Malignant Ventricular Ectopy Database 1.0.0](https://physionet.org/content/vfdb/1.0.0/)
- Version DOI: [10.13026/C22P44](https://doi.org/10.13026/C22P44)
- File license: [Open Data Commons Attribution 1.0](https://physionet.org/content/vfdb/view-license/1.0.0/)
- PhysioNet published uncompressed size: **33.1 MB**
- Source description: 22 two-channel ambulatory ECG recordings with reference
  rhythm-change annotations and no reference beat labels
- Exact headers: 250 Hz, 525,000 samples (35 minutes) and two calibrated `ECG`
  channels per record

Use of derived windows must retain source/version/DOI/license attribution and
identify TRACE's guarded-window extraction as a transformation. Also cite the
source-requested Greenwald work and the standard PhysioNet paper listed on the
versioned dataset page. TRACE is not endorsed by the dataset authors.

## Checksum and identity contract

The importer trusts no local artifact until all of the following pass:

1. `SHA256SUMS.txt` itself matches the pinned VFDB 1.0.0 SHA-256
   `1157e2168f131f2c53e6eb0e3263c0835d286fc05de94066e069e29b810cd6f6`.
2. `RECORDS` matches its published checksum and the exact ordered set of 22
   record identifiers.
3. Every selected `.hea`, `.atr`, and `.dat` artifact matches the corresponding
   source-published checksum.
4. The header remains two channels, 250 Hz, 525,000 samples, mV-calibrated,
   format 212, gain 200, and points to the expected record `.dat` file.

Each derived packet preserves the parent record, window record id, source
patient grouping, annotation index/code, episode and window sample boundaries,
all three source-artifact checksums, extraction version, and a SHA-256 waveform
content fingerprint. VFDB publishes one described source subject per record;
the de-identified record id is therefore retained as the patient-group key so
windows from one record cannot masquerade as independent patients.

## Rhythm and eligibility contract

All source annotation codes remain distinct in provenance:

| Source code | Preserved canonical rhythm |
|---|---|
| `AFIB` | `atrial_fibrillation` |
| `ASYS` | `asystole` |
| `B` | `ventricular_bigeminy` |
| `BI` | `av_block_first_degree` |
| `HGEA` | `high_grade_ventricular_ectopy` |
| `N`, `NSR` | `sinus_rhythm` (never `normal_ecg`) |
| `NOD` | `junctional_rhythm` |
| `PM` | `paced_rhythm` |
| `SBR` | `bradycardia` |
| `SVTA` | `supraventricular_tachyarrhythmia` |
| `VER` | `ventricular_escape_rhythm` |
| `VF`, `VFIB` | `ventricular_fibrillation` |
| `VFL` | `ventricular_flutter` |
| `VT` | `ventricular_tachycardia` |
| `NOISE` | retained exclusion interval; never a learner window |

Every non-noise source label has one narrow future contract:

- mode: `clinical_resuscitation_rhythm`;
- subskills: `recognize`, `discriminate` only;
- source-label evidence only;
- current runtime connection: false;
- Clinical case, management, pulse/perfusion, arrest, shockability, treatment,
  and action-sequence eligibility: false.

The waveform alone never establishes a pulse, perfusion, arrest, stability,
shockability, symptoms, intervention, response, or an action algorithm. A
future action question must separately supply and review those facts. The two
channels are ambulatory ECG channels, not represented as a 12-lead tracing or
as a monitor/defibrillator export.

## Guarded window extraction

- Windows are 10 seconds / 2,500 samples per channel at native 250 Hz.
- Every window remains within one expert rhythm interval.
- A 0.5-second guard is kept inside both annotation boundaries.
- Windows never overlap; the default stride is 10 seconds.
- Short labelled episodes remain visible in inventory but are never padded or
  manufactured into a learner waveform.
- `NOISE` intervals yield no windows.

A checksum-verified read-only inventory of all 22 headers/annotation files on
2026-07-13 found 592 rhythm-change annotations and **3,780** eligible guarded
windows. This includes 71 asystole, 224 ventricular-fibrillation (`VF`/`VFIB`),
36 ventricular-flutter, and 484 ventricular-tachycardia windows: **815** real
critical-rhythm windows before any further review/deduplication. These are
inventory candidates, not a claim that 3,780 cases are deployed or reviewed.

## Safe operation

Obtain the exact public release using a method documented on PhysioNet, for
example its anonymous S3 mirror:

```powershell
aws s3 sync --no-sign-request s3://physionet-open/vfdb/1.0.0/ data/rhythm_sources/vfdb/1.0.0
```

Dry-run inventory is the default and does not create a database:

```powershell
python scripts/import_vfdb.py --source-root data/rhythm_sources/vfdb/1.0.0
python scripts/import_vfdb.py --source-root data/rhythm_sources/vfdb/1.0.0 --rhythm ventricular_fibrillation
```

Mutation requires both `--apply` and an explicit dedicated output:

```powershell
python scripts/import_vfdb.py `
  --source-root data/rhythm_sources/vfdb/1.0.0 `
  --apply `
  --out data/rhythm_streams/vfdb
```

The importer removes the output readiness manifest before mutation, resumes by
source-namespaced window id, stores two-channel int16-microvolt arrays separately
from packet metadata, and writes `manifest.json` atomically as its final action.
An error leaves that manifest absent. Even a complete import manifest says
`runtimeStatus: foundation_only_not_connected`; importing data does not unlock
student access.
