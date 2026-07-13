# MIMIC-IV-ECG GCS source policy

## Storage boundary

The waveform source of record is a credentialed private bucket prefix configured
through `MIMIC_ECG_GCS_PROJECT` and `MIMIC_ECG_GCS_PREFIX`, for example:

```text
gs://example-private-bucket/mimic-iv-ecg-1.0/physionet.org/files/mimic-iv-ecg/1.0/files
```

The project and bucket identifiers remain local deployment configuration; the
example bucket above is only a placeholder. The Drive mirror is not assumed
complete. Import/inventory code must resolve an
exact `study_id` path and stream the `.hea`/`.dat` pair from GCS using
Application Default Credentials. It must never infer waveform availability
from a locally present metadata row. The non-existent path-shaped placeholder
below is covered by a regression test; it deliberately contains no real study
or subject identifier:

```text
p0000/p00000000/s00000000/00000000.dat
```

`scripts/inventory_mimic_gcs.py` is read-only, checks object metadata without
downloading signals, and prints aggregate counts only. No GCS import was run in
the current release because this machine did not have usable ADC for the
bucket, and the added Leipzig source already supplied the needed labelled
rhythm depth.

## Labels are separate evidence sources

- MIMIC-IV-ECG `machine_measurements.csv` contains automated report statements
  and intervals. These are useful candidate assertions, not independent human
  morphology truth.
- MIMIC-IV-ECG-Ext-ICD links ECG times to ED/hospital discharge ICD-10 codes.
  Those codes are encounter/outcome labels and may include non-cardiac
  diagnoses; they do not prove that a morphology is present on a particular
  ECG.
- MIMIC-ECG-EXT is credentialed/research-only in this product. Its rows and
  subject/study identifiers are never exposed to learners, and its source
  descriptor has no learner-facing educational use.

The streaming join in `backend/app/ingest/mimic_gcs.py` therefore emits both
`morphology_eligible=False` and `learner_facing_eligible=False`. A future MIMIC
adapter may admit a waveform only after separately validating license/access,
patient-level identity, exact report provenance, signal quality, label
confidence, and an explicit concept × subskill educational contract. An ICD
code alone can never clear that gate.

Authoritative dataset descriptions:

- https://physionet.org/content/mimic-iv-ecg/1.0/
- https://physionet.org/content/mimic-iv-ecg-ext-icd-labels/1.0.1/
