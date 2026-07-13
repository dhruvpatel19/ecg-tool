# Data schema and API contracts

## Built waveform corpus

The runtime serves one manifest-gated corpus directory, normally `data/ecg_corpus/`:

- `corpus.db` — SQLite packet/index store behind `CaseStore`.
- `waveforms/<bucket>/<case_id>.npy` — compact int16-microvolt waveform arrays behind `LocalWaveformStore`.
- `manifest.json` — source catalog, counts, versions, license identifiers, concept depth, and `"complete": true`. License-contract v2 records PTB-XL 1.0.3 and PTB-XL+ 1.0.1 as `CC-BY-4.0`, and Leipzig 1.0.0 as `ODC-BY-1.0`. This file is written last; a missing/incomplete manifest makes the corpus ineligible for learner startup.
- `.leipzig-import-state.json` — present only during/resuming a gated supplemental import and removed after the complete manifest is atomically restored.

Learner-facing configuration defaults to `ECG_REQUIRE_REAL_DATA=1`. If no complete corpus is available, startup fails; synthetic fixtures require an explicit test-only opt-out and never enter production learning modes.

The installed corpus can contain more than one source. Each normalized supplemental packet carries an immutable source identity, version, license, label authority, patient/source-record identity, educational-use contract, eligible modes/subskills, and signal fingerprint. Source-specific policy is evaluated before selection and before evidence is written.

## Case packet

Common fields include:

- `case_id`, `display_id`, `source`, `teaching_tier`, `clinical_stem`.
- `record_identity` and `source_provenance` for source/version/license identity. PTB packets additionally keep distinct nested PTB-XL waveform/label provenance and PTB-XL+ derived-evidence provenance.
- `educational_eligibility` — educational use, exact eligible modes/subskills, and explicit Clinical/management exclusions.
- `waveform` — sampling frequency, duration, lead list, and storage metadata.
- `ptbxl` — PTB source codes, diagnostic groupings, report, fold, and metadata when applicable.
- `ptbxl_plus.statements` / `statements_detailed` — independent automated statement evidence and provenance.
- `ptbxl_plus.features` / `measurements` — canonical rate, PR, QRS, QT/QTc, axis, voltage, and per-lead ST values when present.
- `ptbxl_plus.fiducials.rois` — neutral waveform-segment geometry by lead. An ROI locates a component; it is not itself a diagnostic assertion.
- `ptbxl_plus.median_beats` — packet-derived median complexes when supported.
- `signal_quality`, `concept_confidence`, `supported_objectives`, `unsupported_objectives`.
- `llm_allowed_claims`, `llm_forbidden_claims`, `teaching_points`.
- `source_labels` and `signal_fingerprint` for expert rhythm windows.

Precommit routes return a blinded packet: reports, diagnoses, statements, supported concepts, and answer-bearing Clinical context are removed at the server boundary. Waveform arrays are served separately and are never embedded in tutor prompts.

## Corpus database tables

- `cases` — one packet row per unique source-namespaced ECG/window, with source identity and packet JSON.
- `case_concepts` — concept-specific confidence tier/score index.
- `clinical_case_items` — versioned authored Clinical scenario/item definitions. The learner bank is replaced atomically only after all new items pass startup validation.

## Learner and authentication database

Identity/security tables:

- `users` — canonical user id, normalized username, display name, PBKDF2 password hash, timestamps.
- `sessions` — SHA-256 hashes of random session tokens, owner, expiry, and revocation state. Reusable tokens are not stored in plaintext or exposed to browser JavaScript.
- `auth_login_throttle` — HMAC-derived source/username-pair, source-IP, and deployment-wide pre-hash buckets. There is intentionally no username-only lockout, so one source cannot globally lock a known learner account.
- `auth_registration_throttle` — independently namespaced HMAC-derived source/username-pair, source-IP, and deployment-wide registration buckets; no raw IP address or username is stored.
- `guest_progress_claims` — immutable guest→account ownership receipt used for idempotent replay and cross-account conflict rejection.

Learning evidence tables:

- `learner_profiles` — learner identity and display metadata.
- `attempts` — case response, confidence, assistance, score, errors, feedback, and timestamp.
- `objective_mastery` — legacy concept aggregate retained for compatibility.
- `subskill_mastery` — concept × subskill formative and independent aggregates, calibration errors, unique ECG/mode/morphology counts, retention state, stability, lapse, and due timestamps.
- `subskill_retention_events` — append-only server-verified evidence used to recompute diversity/retention.
- `guided_learning_events` — idempotent scene/task receipts. The public Guided endpoint is always formative; private Training/Rapid/Clinical graders add server verification.
- `pathway_progress` — authenticated Guided scene/action state.
- `tutor_threads` / `tutor_messages` — context-scoped persistent conversations and grounded viewer actions.

Server-owned mode ledgers:

- `training_campaigns`, `training_campaign_slots`, `training_campaign_answers` — immutable target/mimic/negative/transfer plan, pending/feedback state, and exactly-once answers.
- `rapid_rounds`, `rapid_round_answers` — pace/deadline policy, exclusions, served set, pending/feedback state, complete result ledger, and receipts.
- `clinical_shift_sessions`, `clinical_shift_answers` — lane/tier, orient/decide timing, first-look/context boundary, served ECGs, calibration, grade, and formative receipts.
- `review_sessions` — legacy adaptive-review state; the student-facing `/review` page uses the verified cross-mode mastery planner.

SQLite uses WAL, busy timeouts, guarded shared-memory connections in tests, and explicit immediate transactions for ownership-changing guest claims and atomic login/registration throttle reservations.

Long-mode response contracts are bounded: Rapid keeps the complete served set server-side and returns `servedCount` with a 25-id `recentServed` tail; Training keeps the complete immutable phase sequence in its slot ledger and returns only the current slot plus `phaseCounts`. Per-case Training/Rapid answers store `tutor: null`; deterministic grading never invokes a model. Conversational tutor output is created only through the explicit tutor endpoint, while Rapid round debriefs receive a bounded deterministic receipt sample.

## Authentication boundary

- Browser authentication uses an `HttpOnly`, `SameSite=Lax` cookie (`Secure` in production).
- An invalid presented credential returns 401; stateful routes never silently downgrade it to a guest.
- A browser without an account receives a separate opaque guest cookie/learner namespace.
- Guest progress is claimed only when the learner explicitly checks the default-off transfer control during login/registration.
- Claiming is one transaction across all learning/evidence/mode tables. It is idempotent for the same account, conflict-safe across accounts, merge-monotonic, and leaves at most one resumable session per mode.
- The same-origin Next proxy strips forwarding identity headers. Supported Uvicorn launches use `--no-proxy-headers`, so registration throttling uses only the socket peer.

## Primary API surface

Data and registry:

- `GET /health`, `GET /dataset/status`
- `GET /concepts`, `GET /objectives`, `GET /curriculum`
- `GET /cases`, `/cases/{id}`, `/cases/{id}/packet`, `/cases/{id}/waveform`, `/cases/{id}/ptbxl-plus`

Authentication/profile:

- `POST /auth/register`, `/auth/login`, `/auth/logout`, `/auth/logout-all`, `/auth/change-password`
- `GET /auth/me`, `/auth/guest-progress`
- `GET /learners/{id}`, `/learners/{id}/mastery`, `/learners/{id}/competencies`, `/learners/{id}/pathway-progress`
- `PUT /learners/{id}`, `POST /learners/{id}/pathway-progress`

Mode state machines:

- `GET /training/campaigns/pool`, `POST /training/campaigns`, then `/active`, `/{id}`, `/{id}/next`, `/{id}/submit`, `/{id}/abandon`
- `POST /rapid/rounds`, then `/active`, `/{id}`, `/{id}/next`, `/{id}/submit`, `/{id}/results`
- `GET /clinical/bank/status`, `/clinical/bank/coverage`; `POST /clinical/shift/start`, then `/active`, `/{id}/next`, `/{id}/phase`, `/{id}/context`, `/{id}/answer`; `GET /clinical/shift/{id}/report`

Learning/adaptation/tutor:

- `POST /learning-events/guided`
- `GET /adaptive/plan`
- `POST /tutor/message`; `GET /tutor/threads`, `/tutor/thread/{id}`
- deterministic case grading/viewer endpoints under `/grade/*` and `/viewer/map-point`

All learner-id request fields are advisory compatibility fields. Stateful handlers resolve the effective learner from the authenticated or opaque guest cookie and enforce ownership on every resumable session/thread.
