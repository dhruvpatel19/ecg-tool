# Testing and Verification

## Full verification

```powershell
.\scripts\verify.ps1
```

Runs the backend pytest suite, the frontend coordinate test, TypeScript typecheck, the Next.js production build, and a corpus-pinned production-style smoke flow (it pins `ECG_CORPUS_ROOT` to a complete corpus and reports the active source).

## Individual checks

```powershell
$env:PYTHONPATH="backend"; python -m pytest backend/tests -q
cd frontend; npm run test:coords; npm run typecheck; npm run build
```

Tests use an isolated in-memory learner DB and pin the complete checked corpus (`backend/tests/conftest.py`), so they never pollute a real guest or account record.

## Test coverage

- **Ingestion** (`test_ingest.py`) — real PTB-XL+ column → canonical measurement mapping; noise-based signal quality; readable statements; word-boundary + field-aware grading; a corpus smoke check (measurements, 12-lead ROIs, median beats, readable statements).
- **Curation & packets** (`test_curation_and_packets.py`) — fixture fallback, tier exclusion, packet grounding, BBB specificity, lead-name normalization, LLM schema validation + the OpenAI-compatible request/response path against a local stub server.
- **Tutor & review** (`test_tutor_review.py`) — multi-turn grounded tutor, refusal of unsupported findings, review-session progression to mastery.
- **Auth and persistence integrity** (`test_auth.py`, `test_persistence_integrity.py`) — password hashing, HttpOnly cookie sessions, throttling/rotation, per-user isolation, server-owned pathway progress, full unseen competency matrix, and exactly-once evidence replay.
- **Guest claim and authentication security** (`test_guest_progress_claim.py`, `test_login_throttle.py`, `test_registration_throttle.py`) — transactional all-mode guest→account ownership transfer, collision/idempotency rules, resumable-session resolution, cookie rotation, HMAC pair/IP/global pre-hash buckets, cross-source lockout resistance, spoofed-header resistance, hierarchical no-broader-debit behavior, and concurrent quota consumption.
- **Durable modes** (`test_training_campaigns.py`, `test_rapid_rounds.py`, `test_clinical_shift.py`) — server ownership/resume, immutable no-repeat ledgers up to 5,000, deadline/replay behavior, exact receipts, blinding/context boundaries, and 103-case Clinical coverage.
- **Multisource policy** (`test_multisource_contract.py`, `test_leipzig_ingest.py`, `test_dynamic_objective_availability.py`, `test_rapid_source_policy.py`) — exact source identity/version/license, GCS path construction, target-only label behavior, checksum/fingerprint gates, dynamic WCT unlock, and research/fixture rejection.
- **Retention/adaptation** (`test_subskill_mastery.py`, `test_retention_model.py`, `test_mastery_planner.py`) — formative/independent separation, morphology/mode diversity, due/lapse behavior, runtime subskill eligibility, and cross-mode plan construction.
- **Executable adaptive receipts** (`test_mastery_planner.py`, `test_training_campaigns.py`, `test_rapid_rounds.py`) — every prescribed stage names the exact receipt it can emit; labeled-contrast, reviewed-mechanism, confidence-calibration, and complete-sweep synthesis graders fail closed against free text, proxy targets, leaked slot truth, or unsupported Clinical evidence.
- **Coordinates** (`test_coordinates.py` + frontend `check-coordinate.mjs`) — parallel backend/frontend pixel→(lead, time, mV) mapping.
- **LLM schema** (`test_llm_schema.py`) — structured-output validation and graceful fallback.

## Browser end-to-end (Playwright)

```powershell
cd frontend; npx playwright install
# with the backend running on :8000 and a built corpus:
npm run e2e
```

The current Playwright registry declares 39 Chromium journeys across 12 files. They cover explicit guest claiming and account isolation; dashboard/navigation; all four learning modes; the production curriculum registry; Guided evidence integrity; scalable Training setup plus durable resume/replay, keyboard measurement, and the 130-record expert WCT source contract; Rapid pace/trace/recovery/AI-debrief contracts; Clinical first-look/context/stepwise/exact-receipt/governance behavior; the adaptive mastery coach; responsive layouts; and novice-persona desktop/mobile journeys.

## Manual local run

```powershell
# Terminal 1
$env:PYTHONPATH="backend"; python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-proxy-headers
# Terminal 2
cd frontend; $env:ECG_BACKEND_API_BASE="http://127.0.0.1:8000"; npm run dev
```

Open `http://localhost:3000`.
