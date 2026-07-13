# Leipzig Heart Center rhythm-stream adapter

The Leipzig Heart Center source is admitted as an expert-labelled **rhythm
stream**, not as an authored clinical case. The offline adapter is
`backend/app/ingest/leipzig.py`; the resumable command is
`scripts/import_leipzig.py`.

## Admission boundary

- Only 10-second, non-overlapping windows fully inside an expert WFDB rhythm
  interval are eligible.
- A 0.5-second guard is kept inside both rhythm boundaries by default.
- Windows overlapping paired expert `~` signal-quality intervals are excluded.
- Every admitted window must have at least two expert beat annotations.
- Only the 12 surface leads are read. Intracardiac channels are not exported.
- Signals are polyphase-downsampled from 977 Hz to exactly 100 Hz / 1,000
  samples per lead.
- Heart rate is the median annotated RR rate. QRS ROIs are neutral locations
  projected from expert beat times; they are not diagnostic morphology labels.

| Source rhythm | Corpus objective |
|---|---|
| `N` | `sinus_rhythm` (never `normal_ecg`) |
| `AVNRT`, `AVRT` | `supraventricular_tachycardia` |
| `VT` | `wide_complex_tachycardia` |
| `AFIB` | `atrial_fibrillation` |
| `/A`, `/V` | `paced_rhythm` |

Other rhythm markers remain visible in dry-run inventory but are not silently
mapped. Packets preserve source record/window, patient, source version 1.0.0,
expert-label authority, extraction version, and ODC-BY-1.0 provenance.

These labels are eligible for Training and Rapid only. The packet contract
explicitly disallows Clinical-case and management use because the source does
not supply symptoms, hemodynamics, encounter context, or management ground
truth.

In Rapid, these packets are **target-only rhythm evidence**, not exhaustively
labelled 12-lead interpretations. They may appear for an explicit focused
rhythm objective; they are excluded from blind mixed/full-read selection, and
non-rhythm claims are reported as unassessed rather than penalized as false
overcalls.

The WCT objective is runtime-gated. It becomes independently assessable only
when the repository contains a packet that passes the complete expert
rhythm-source audit (source descriptor, identity, version/license, label
authority, episode containment, 10-second 12-lead waveform, eligibility lane,
confidence, quality, and content fingerprint). The active corpus now contains
130 such target-only windows, so focused `recognize` and `discriminate` are
available. Mechanism/application/management, broad full-read scoring, and
Clinical/ACLS remain locked separately.

## Safe operation

Dry run is the default and does not open or create a corpus database:

```powershell
python scripts\import_leipzig.py
python scripts\import_leipzig.py --record x109 --concept wide_complex_tachycardia
```

Mutation requires both `--apply` and an explicit target corpus:

```powershell
python scripts\import_leipzig.py --apply --corpus data\ecg_corpus --limit 25
```

Before applying, the command verifies that every selected `.dat` file is
locally readable. It writes an import-state file, removes `manifest.json` to
gate runtime selection, resumes by namespaced case id, and writes a complete
manifest atomically as the final corpus mutation. Any failed window leaves the
manifest absent and prints a rerun/resume instruction.

## Current local inventory snapshot

The read-only inventory on 2026-07-13 found 5,424 eligible unique windows across
39 patients: 4,235 sinus, 593 SVT, 424 paced, 130 VT/WCT, and 42 AF. Annotation
and header inventory completed without errors.

Nine additional WCT-bearing records were hydrated from PhysioNet's documented
anonymous S3 mirror with `scripts/hydrate_leipzig_records.ps1`. Every download
was checked against the release `SHA256SUMS.txt` before its `.part` file could be
promoted. The locally readable set is now 26 of 39 records / 2,438 eligible
windows. The bounded pathological import admitted all locally readable AF, paced,
SVT, and WCT windows plus the previously installed sinus sample:

- 180 sinus
- 279 SVT
- 77 paced
- 130 WCT/VT
- 32 AF

The resulting 698 Leipzig windows were imported with zero errors and zero
signal-fingerprint duplicates. The active manifest contains 22,497 total
records (21,799 PTB-XL + 698 Leipzig) and 21,855 student-facing Tier A/B records.
The 1,740 additional locally readable sinus windows were deliberately not
imported because PTB-XL already supplies abundant sinus diversity; this bounded
addition targeted pathological rhythm depth. Thirteen source waveform records
remain unhydrated, so their 2,986 windows remain absent rather than being inferred
from annotations or Drive placeholders.
