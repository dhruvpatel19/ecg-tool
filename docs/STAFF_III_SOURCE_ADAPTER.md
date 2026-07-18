# STAFF III serial-comparison source adapter

STAFF III 1.0.0 is integrated as an **offline authoring source**, not as a
serve-time dependency. The adapter in `backend/app/ingest/staff_iii.py` and CLI
in `scripts/import_staff_iii.py` build opaque, review-required comparison
candidates from the local version-pinned dataset.

## Evidence contract

The source can establish:

- same-source-patient protocol grouping offline;
- the order baseline → controlled PTCA balloon occlusion → recovery;
- event timing, occlusion ordinal, the source artery text, and documented
  contrast-injection times;
- standard precordial leads and Mason–Likar limb-lead configuration.

It cannot establish, without separate review:

- the ECG regions that changed or remained unchanged;
- spontaneous ACS, STEMI, OMI, infarction, symptoms, prognosis, or treatment
  response;
- hemodynamics, medication, intervention, disposition, or management.

Every generated episode therefore has an empty morphology answer key,
`eligibleModes: []`, and false Rapid, Clinical, management, and mastery flags.
Promotion requires clinician-adjudicated changed and unchanged ROIs, an
allowed-claims ceiling, and an explicit mode-specific release step.

## Source integrity and transformation

- Dataset: [STAFF III Database 1.0.0](https://physionet.org/content/staffiii/1.0.0/)
- DOI: [10.13026/C20P4H](https://doi.org/10.13026/C20P4H)
- License: ODC Attribution 1.0
- Source release: 520 records, 104 described patients, 3.2 GB uncompressed
- Pinned `SHA256SUMS.txt` SHA-256:
  `e4c71aa1b47b8fd17b1549b5f650770df63f4cb795388d129c6ca78cd7a78269`

The importer verifies the checksum manifest before trusting any row, verifies
`RECORDS` and the protocol workbook, verifies selected headers and waveform
files, and accepts only the expected 9 measured channels at 1000 Hz. It derives
aVR/aVL/aVF from I/II, applies deterministic anti-aliased decimation to 250 Hz,
and writes 10-second, 12-lead frames. Patients identified by the source
workbook as having possible lead/sign reversal are excluded.

Documented contrast injections are conservatively kept outside the selected
occlusion window. Because the source says injection annotation is incomplete,
the public artifact retains `contrastAnnotationComplete: false`.

Raw patient numbers and record names are never serialized. Frame and episode
identities are TRACE-generated and waveform identity is content-fingerprinted.

## Safe operation

Dry-run inventory is default. A bounded scan validates only enough complete
protocols to produce the requested bound:

```powershell
python scripts/import_staff_iii.py `
  --source-root $env:STAFF_III_DATA_ROOT `
  --limit 10
```

Writing requires `--apply` and a new, empty dedicated output directory:

```powershell
python scripts/import_staff_iii.py `
  --source-root $env:STAFF_III_DATA_ROOT `
  --limit 25 `
  --apply `
  --out data/comparison_sources/staff-iii-v1
```

The output contains opaque waveform arrays, `comparison-episodes.json`, and a
`manifest.json` written last. An interrupted or invalid import cannot look
ready. Source windows with missing/non-finite samples are excluded by a typed
quality gate, and candidate, exclusion, episode, and frame counts must reconcile
before the manifest can be written.

The complete pinned-source build on 2026-07-17 scanned 102 protocol-eligible
patients and found 141 complete protocol sequences. One sequence contained
non-finite samples in its selected occlusion window and was explicitly excluded,
leaving 140 review-required comparison episodes / 420 ECG frames. The artifact
records that single `non_finite_source_samples` exclusion, contains no raw record
tokens, and remains `currentRuntimeConnected: false` and
`reviewRequiredBeforeLearnerServing: true`.

The output is not added to the ordinary ECG `CaseStore`, and the backend never
reads Drive or PhysioNet at runtime.
