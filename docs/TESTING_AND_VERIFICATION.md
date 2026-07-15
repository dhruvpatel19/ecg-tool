# Testing and Verification

## Full verification

```powershell
.\scripts\verify.ps1
```

Runs the backend pytest suite, pinned production-Python dependency audit, frontend coordinate test, TypeScript typecheck, ESLint, production dependency audit, Next.js production build, exhaustive release-corpus audit, a corpus-pinned production-style smoke through the real blinded Rapid lifecycle, four-mode Playwright journeys, and the optional live-LLM smoke. `-Release` fails closed unless a live LLM credential is supplied; the deterministic Rapid smoke explicitly uses the no-cost mock provider so the paid provider is exercised only by the separate announced live check.

## Individual checks

```powershell
$env:PYTHONPATH="backend"; python -m pytest backend/tests -q
cd frontend; npm run test:coords; npm run typecheck; npm run build
```

Tests use an isolated in-memory learner DB and pin the complete checked corpus (`backend/tests/conftest.py`), so they never pollute a real guest or account record.

## Test coverage

- **Ingestion** (`test_ingest.py`) — real PTB-XL+ column → canonical measurement mapping; noise-based signal quality; readable statements; word-boundary + field-aware grading; a corpus smoke check (measurements, 12-lead ROIs, median beats, readable statements).
- **Curation & packets** (`test_curation_and_packets.py`) — fixture fallback, tier exclusion, packet grounding, BBB specificity, lead-name normalization, LLM schema validation + the OpenAI-compatible request/response path against a local stub server.
- **Tutor & adaptive review** (`test_tutor_review.py`) — multi-turn grounded tutor, refusal of unsupported or assessment-pending findings, owner/waypoint partitioning, and fail-closed retirement of the legacy mutable Review API in favor of the verified adaptive plan.
- **Auth and persistence integrity** (`test_auth.py`, `test_email_auth.py`,
  `test_auth_mailer.py`,
  `test_persistence_integrity.py`) — password hashing,
  HttpOnly cookie sessions, email-first registration/login, required six-digit
  email verification, generic asynchronous password recovery, migration of
  retired pilot 2FA flags, provider-neutral SMTP/STARTTLS readiness,
  post-commit delivery-failure recovery, session rotation/revocation,
  fresh-password-confirmed single-use progress export, confirmed transactional
  deletion, per-user isolation, and exactly-once evidence replay.
- **Deletion/storage integrity** (`test_account_deletion_integrity.py`) — schema
  v4 migration and complete owner-table trigger inventory, non-identifying
  durable tombstone retention, unchanged legacy guest erasure, and deterministic
  deletion-winning races against profile, attempt, pathway, Training, Rapid,
  Clinical, tutor, Guided activity, and auth writes with zero owner residue.
- **Legacy claim and authentication security** (`test_guest_progress_claim.py`,
  `test_guest_identity.py`, `test_auth_owner_boundary_audit.py`,
  `test_login_throttle.py`, `test_registration_throttle.py`) — no new guest
  identity, anonymous learner-route rejection, deferred claim until verification,
  transactional owner-bound all-mode transfer, foreign-cookie and empty-record
  rejection, idempotency, resumable-session resolution, HMAC pair/IP/global
  pre-hash buckets, cross-source lockout resistance, spoofed-header resistance,
  hierarchical no-broader-debit behavior, and concurrent quota consumption.
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

The Playwright registry declares Chromium journeys across the student product.
They cover verified account entry, recovery/security settings, migration-only
legacy claiming, account isolation/lifecycle controls; dashboard/navigation; all
four learning modes; the production curriculum registry; Guided evidence
integrity; scalable Training setup plus durable resume/replay, keyboard
measurement, and the 130-record expert WCT source contract; Rapid
pace/trace/recovery/AI-debrief contracts; Clinical
first-look/context/stepwise/exact-receipt/governance behavior; the adaptive
mastery coach; responsive layouts; and novice-persona desktop/mobile journeys.

### 2026-07-14 public entry and authentication gate

- Full backend regression: **575 passed, 5 intentional skips**.
- Focused backend auth/privacy/readiness regression: **112 passed**.
- Email-entry browser journeys: **6/6 passed**, including 320 px registration,
  direct email/password login, explicit verification with password reproof,
  signed-out email-change handoff, and legacy-record cleanup.
- Recovery and security-header checks passed. New email secrets were absent from
  the browser URL after capture, every observed HTTP request URL, and every
  observed `Referer`; the public shell sends `Referrer-Policy: no-referrer`.
- Landing, sign-in, and registration passed automated WCAG A/AA checks at
  desktop and 320 px. TypeScript, full ESLint, production build, dependency
  audit, and `git diff --check` passed.
- Nine older private-route browser specs still need the shared verified-owner
  fixture before an honest all-spec Playwright run. This is recorded as test
  maintenance debt; it is not represented as a passing full E2E run.

### Automated accessibility gate

`e2e/accessibility.spec.ts` runs axe WCAG 2.0/2.1 A and AA rules over the student shell, both Guided workspaces, and active Training, Rapid, and Clinical workspaces. Detected violations are release failures; they are not allowlisted.

```powershell
cd frontend
$env:E2E_BASE_URL="http://localhost:3111"
npx playwright test e2e/accessibility.spec.ts
```

This complements—rather than replaces—the keyboard, focus-order, 200% zoom, touch-target, and screen-reader journeys in the responsive mode suites.

## Manual local run

```powershell
# Terminal 1
$env:PYTHONPATH="backend"; python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-proxy-headers
# Terminal 2
cd frontend; $env:ECG_BACKEND_API_BASE="http://127.0.0.1:8000"; npm run dev
```

Open `http://localhost:3000`.
