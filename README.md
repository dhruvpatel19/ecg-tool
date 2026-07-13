# TRACE ECG Learning Platform

TRACE is a four-mode ECG learning product for medical students entering clerkship. Guided learning, focused competency Training, Rapid interpretation, and Clinical Decisions share one calibrated ECG viewer, versioned objective registry, server-owned learner record, adaptive mastery planner, and grounded conversational tutor.

**Educational tool only — not a clinical diagnostic product or competence certification instrument.**

## Current release contract

- Learner workflows fail closed unless a complete real-data corpus is installed. Synthetic waveforms exist only as explicit test/harness fixtures and cannot enter learner Training, Rapid, Clinical, independent evidence, or retention.
- The active corpus has **22,497 unique recordings/windows**: 21,799 PTB-XL records plus 698 expert-labelled Leipzig rhythm windows. **21,855** are Tier A/B student-facing.
- Training and Rapid can run up to **5,000 unique ECGs** in one server-owned session. They use the complete exact eligible pool, not a small checked-in case list.
- Clinical has **103 unique real PTB ECGs and 103 distinct authored scenario signatures** across eight families and multiple question types. It is automated-screened formative content pending named clinician sign-off.
- Accounts, opaque per-browser guest records, objective evidence, competency/retention state, tutor threads, and every mode session are persisted server-side.
- The LLM explains and asks questions; deterministic packet evidence, source policy, graders, session state machines, and the verified adaptive scheduler own truth, scoring, selection, and mastery.

## Architecture

```text
PTB-XL + PTB-XL+                    Leipzig expert rhythm source
  raw WFDB + metadata                 WFDB + expert beat/rhythm annotations
            │                                      │
            ├─ offline atomic build                 ├─ source-specific audited adapter
            └──────────────────┬───────────────────┘
                               ▼
data/ecg_corpus/
  corpus.db                    grounded packets + concept/source index
  waveforms/                   compact source-namespaced waveform arrays
  manifest.json                complete:true, versions/licenses/counts/source policy
                               │
             FastAPI backend  ─┴─ auth, session ledgers, grading, retention,
                               adaptive planner, grounded tutor, Clinical bank
                               │
             Next.js frontend ─── Learn / Train / Rapid / Cases / Mastery coach
```

The browser uses the same-origin `/api/backend` proxy. Session and guest tokens are HttpOnly cookies; LLM credentials remain server-side.

## Four modes

| Mode | Route | Student workflow |
|---|---|---|
| Guided learning | `/learn` | Ten dependency-driven modules. The native interaction runtime supports vector/lead work, points/regions, calipers/numeric entry, march-out, ordering, matching, comparison, explanation, and staged clinical gates. |
| Competency Training | `/train` | Select an exact concept × subskill and a 10/25/50/100/500/1,000/5,000 campaign. The server interleaves target, close mimic, other negative, and unannounced transfer ECGs without replacement and shows the exact pool/role depth before start. |
| Rapid interpretation | `/rapid` | Run 5/10/25/50/100/500/1,000/5,000 mixed ECGs at 75-second ward, 20-second emergency first-look, or untimed pace. Ward/untimed reads require server-verified trace proof; deadlines and answers survive refresh/login. |
| Clinical Decisions | `/practice` | Work clinic, ward, or ED-non-arrest cases in Learn or timed Shift. Commit an ECG-only first look before authored context is revealed, then answer MCQ, click, spot-error, old/new/insufficient-data, triage, or stepwise tasks. |

The `/review` mastery coach reads the same evidence ledger and prescribes a focused → mixed transfer → eligible Clinical sequence plus a cross-concept integration read.

## Data sources

### Active corpus

| Source | Count | Permitted use |
|---|---:|---|
| PTB-XL 1.0.3 + PTB-XL+ 1.0.1 | 21,799 | Static 12-lead examples, Training, broad/focused Rapid, and the 103-ECG Clinical waveform bank. |
| Leipzig Heart Center 1.0.0 | 698 | Focused target-only rhythm Training/Rapid: 180 sinus, 279 SVT, 77 paced, 130 WCT, 32 AF. |

See [Data sources and attribution](docs/DATA_SOURCES_AND_ATTRIBUTION.md) for
version-specific official dataset links, DOIs, requested citations, license
notices, and TRACE transformation disclosures. PTB-XL and PTB-XL+ are CC BY
4.0; Leipzig remains ODC-By 1.0.

The current Tier A/B distribution is 16,636 Tier A and 5,219 Tier B; 642 Tier C records remain excluded from normal student selection. Concept depth is deliberately uneven. Examples: rate 21,855, normal ECG 5,491, AF 1,491, SVT 646, paced rhythm 346, WCT 130, complete AV block 20, Mobitz II 30, and Mobitz I 1. Setup screens disclose exact task-eligible depth and shorten a request rather than padding it.

Leipzig windows are expert-labelled rhythm evidence, not exhaustive 12-lead morphology labels. They can support only their declared target/subskills and are excluded from blind broad Rapid reads. They never supply symptoms, pulse/perfusion, management, or ACLS truth.

### MIMIC boundary

The MIMIC-IV-ECG waveform source of record is a credentialed private GCS prefix configured through `MIMIC_ECG_GCS_PROJECT` and `MIMIC_ECG_GCS_PREFIX`, for example:

```text
gs://example-private-bucket/mimic-iv-ecg-1.0/physionet.org/files/mimic-iv-ecg/1.0/files
```

The example bucket is a placeholder; no private project or bucket identifier is committed. Drive is not assumed complete. `scripts/inventory_mimic_gcs.py` requires the project, prefix, and label path explicitly and performs aggregate, read-only object checks through Application Default Credentials. MIMIC-ECG-EXT ICD rows are encounter/outcome context—not proof that a morphology is present on an individual ECG—and machine reports are candidate assertions rather than independent human labels. No MIMIC record is learner-facing in this release. See `docs/MIMIC_GCS_SOURCE_POLICY.md`.

## Setup

```powershell
python -m pip install -r backend/requirements-dev.txt
python -m pip install -r backend/requirements-data.txt
cd frontend
npm install
cd ..
```

Copy `.env.example` to `.env`. Important settings:

```text
ECG_CORPUS_ROOT=                 # complete corpus directory; auto-discovered when empty
ECG_REQUIRE_REAL_DATA=1          # production/learner default
DATABASE_URL=sqlite:///./ecg_learning.db
AUTH_RATE_LIMIT_SECRET=          # required in production
LLM_PROVIDER=mock                # mock | openai-compatible
LLM_API_KEY=                     # server-side only
LLM_MODEL=gpt-5.6-luna           # deployment-configurable
LLM_BASE_URL=
ECG_BACKEND_API_BASE=http://127.0.0.1:8000
```

### Build PTB-XL offline

```powershell
$env:PYTHONPATH="backend"
python scripts/build_corpus.py --limit 0 --out data/ecg_corpus
```

The builder writes to a staging directory, resumes interrupted work, writes `manifest.json` last, and promotes atomically. Raw roots are configured with `PTBXL_DATA_ROOT` and `PTBXL_PLUS_DATA_ROOT`; there is no serve-time WFDB or Drive dependency.

### Inventory/import Leipzig

Dry run is the default:

```powershell
python scripts/import_leipzig.py --concept wide_complex_tachycardia
```

Mutation requires both `--apply` and an explicit corpus. `scripts/hydrate_leipzig_records.ps1` can resume selected official PhysioNet downloads and will not promote a file until it matches the publisher's SHA-256 list. See `docs/LEIPZIG_SOURCE_ADAPTER.md` for the exact source contract and current import.

## Run

```powershell
# terminal 1
$env:PYTHONPATH="backend"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-proxy-headers

# terminal 2
cd frontend
$env:ECG_BACKEND_API_BASE="http://127.0.0.1:8000"
npm run dev
```

Open `http://localhost:3000`.

## Authentication and learner continuity

- Passwords use PBKDF2; random session tokens are stored only as hashes.
- Browser sessions are HttpOnly, SameSite=Lax, and Secure in production. Logout-all and password change are available under `/account`.
- Login attempts and registration are rate limited. Registration buckets use HMAC-derived direct-peer/username keys and store no raw IP or username; supported Uvicorn commands disable proxy-header rewriting.
- Every guest browser receives a separate opaque learner identity. Login/registration shows a transfer option only when that browser has claimable work, and the checkbox is off by default.
- An explicit guest claim is one immediate transaction across evidence, Guided state, tutor history, and Training/Rapid/Clinical/Review sessions. It is idempotent, collision-safe, merge-monotonic, rotates the guest cookie, and leaves at most one resumable session per mode.
- Current local account recovery is administrator-mediated; institutional SSO/email recovery is a deployment decision rather than a fake local workflow.

## Evidence and adaptive learning

The executable registry currently defines 115 objectives across eight subskills: recognize, localize, measure, discriminate, explain mechanism, synthesize, apply in context, and calibrate confidence.

The learner record separates formative from independent evidence and tracks assistance, confidence errors, distinct ECGs/modes/morphologies, lapses, spaced retrieval, stability, and due dates. A public/client-declared Guided event is always formative. Independent evidence requires a private server grader, exact source contract, eligible real case, correct subskill, and the appropriate trace-native/transfer conditions.

The adaptive scheduler is separate from the conversational tutor. It ranks overdue retrieval, due work, high-confidence misses, weak independent evidence, diversity gaps, and unseen eligible cells. The plan coach may explain the server-issued queue, but it cannot alter it, score work, choose an unlisted case, or create ground truth.

## AI roles and safety

- Case/lesson tutor: persistent, context-scoped Socratic Q&A.
- Post-case and post-round coach: receipt-grounded misconception and cross-concept synthesis.
- Clinical attending: available only after required commitment; the deterministic Clinical state machine owns facts and branches.
- Plan coach: explains verified competency priorities and study sequencing.

Provider output is schema-validated. Diagnostic/measurement prose is checked against packet evidence; ROI-like viewer actions must bind to real packet geometry. Provider or schema failure returns a safe grounded fallback. The LLM never writes diagnoses, source labels, answer keys, timers, mastery, or retention.

## Verification

```powershell
.\scripts\verify.ps1

# or individually
$env:PYTHONPATH="backend"
python -m pytest backend/tests -q

cd frontend
npm run test:coords
npm run typecheck
npm audit --omit=dev --audit-level=moderate
npm run build
npm run e2e
```

Tests use isolated learner databases and explicit data roots; they do not write to a shared demo profile.

## Honest limits

- The 103 Clinical scenarios are automated-screened and visibly formative. A named clinician must review/version scenario language, distractors, acuity caps, and action policies before a clinical-content pilot.
- PTB-XL is predominantly chronic/resting. Leipzig supplies expert rhythm windows but not pulse, perfusion, treatment response, or management truth.
- ACLS/arrest, evolving acute ischemia, true paired serial comparison, transient-event causality, and medication/electrolyte causality remain locked until their required sources and governance are installed.
- Guided module completion is not synonymous with competency; only exact eligible task receipts enter independent/retention evidence.
- Automated keyboard/mobile/responsive coverage does not replace a formal screen-reader/200% zoom/reduced-motion audit or moderated representative-learner validation.
- The learning model is transparent and retention/diversity-aware, but it has not been psychometrically calibrated and must not be presented as certification or clinical readiness.
- Institutional release still needs the chosen managed database/object storage, backups, monitoring, privacy operations, and SSO/recovery policy.

Current implementation authority: `docs/MODES_2_4_RELEASE_READINESS.md`, `docs/DATA_SCHEMA.md`, `docs/LEIPZIG_SOURCE_ADAPTER.md`, `docs/MIMIC_GCS_SOURCE_POLICY.md`, and the active `data/ecg_corpus/manifest.json`. Older rebuild/persona/storyboard documents are retained as dated design/audit history.
