# Research and Product Plan

> **Archived initial V1 plan.** The Drive/fallback behavior and mode descriptions below predate the real-data fail-closed runtime, normalized supplemental-source adapters, server-owned 5,000-ECG sessions, and explicit guest-progress claim flow. Use `docs/MODES_2_4_RELEASE_READINESS.md`, `docs/MIMIC_GCS_SOURCE_POLICY.md`, and `docs/DATA_SCHEMA.md` for current behavior.

## Product Thesis

ECG learning improves when the student interacts with a real waveform, receives immediate grounded feedback, and practices cases selected by mastery rather than by a static list. V1 treats AI as the learning operating system while keeping deterministic data and curation as the source of truth.

## V1 Learning Modes

- Guided tutorials: fixed curriculum with tutor prompts and viewer actions.
- Rapid practice: ECG-first workflow, structured interpretation, confidence rating, feedback, diagnosis reveal, mastery update.
- Concept practice: enabled only for concepts with reliable Tier A/B cases.
- Adaptive review: prioritizes low mastery, stale objectives, repeated misses, high-confidence wrong answers, and unseen concepts.

## Dataset Plan

PTB-XL supplies metadata, SCP labels, reports, folds, and waveform references. PTB-XL+ supplies measurements, statements, features, fiducials, and median-beat references when present.

Google Drive is the storage source, but the backend reads local or synced folders through:

- `PTBXL_DATA_ROOT`
- `PTBXL_PLUS_DATA_ROOT`

When those folders are missing, V1 uses synthetic fixture cases that are clearly marked non-clinical.

The backend now also attempts local/synced Drive auto-discovery for the observed dataset folder names before falling back to fixtures. This keeps the product usable with Google Drive for Desktop while preserving explicit env-var configuration for reproducible runs.

## Product Safety

- The platform is educational only.
- The LLM cannot override curation.
- The LLM receives case packets, not arbitrary raw files.
- Viewer actions are schema-validated before execution.
- Sparse or unreliable concepts are disabled rather than forced.

## V1 Success Criteria

- A student can open the dashboard, learn with a tutorial, practice an ECG, receive feedback, see viewer highlights, and get an adaptive next case.
- Dataset status clearly reports real PTB-XL/PTB-XL+ or fixture fallback.
- Verification commands pass locally.
