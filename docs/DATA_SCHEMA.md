# Data schema and API contracts

## Built waveform corpus

The runtime serves one manifest-gated corpus directory, normally `data/ecg_corpus/`:

- `corpus.db` — SQLite packet/index store behind `CaseStore`.
- `waveforms/<bucket>/<case_id>.npy` — compact int16-microvolt waveform arrays behind `LocalWaveformStore`.
- `manifest.json` — source catalog, counts, versions, license identifiers, concept depth, and `"complete": true`. License-contract v2 records PTB-XL 1.0.3 and PTB-XL+ 1.0.1 as `CC-BY-4.0`, and Leipzig 1.0.0 as `ODC-BY-1.0`. This file is written last; a missing/incomplete manifest makes the corpus ineligible for learner startup.
- `.leipzig-import-state.json` — present only during/resuming a gated supplemental import and removed after the complete manifest is atomically restored.

Learner-facing configuration defaults to `ECG_REQUIRE_REAL_DATA=1`. If no complete corpus is available, startup fails; synthetic fixtures require an explicit test-only opt-out and never enter production learning modes.

The installed corpus can contain more than one source. Each normalized supplemental packet carries an immutable source identity, version, license, label authority, patient/source-record identity, educational-use contract, eligible modes/subskills, and signal fingerprint. Source-specific policy is evaluated before selection and before evidence is written.

## Disconnected rhythm-stream foundation

VFDB is imported into a separate manifest-gated directory, normally
`data/rhythm_streams/vfdb/`, rather than the serving 12-lead corpus:

- `rhythm_streams.db` — source/window/patient identity, exact rhythm label,
  artifact provenance, eligibility contract, and packet JSON behind
  `RhythmStreamStore`;
- `waveforms/` — two-channel int16-microvolt arrays behind a channel-specific
  `LocalWaveformStore`;
- `manifest.json` — source/version/license, counts, checksum-manifest identity,
  and `runtimeStatus: foundation_only_not_connected`, written last;
- `.vfdb-import-state.json` — resumable gated-import state.

These packets are not `CaseStore` rows and no current learner route reads this
store. Their exact future ceiling is rhythm `recognize`/`discriminate`; pulse,
perfusion, arrest, shockability, management, treatment, and action-sequence
claims are explicitly false until separately sourced/reviewed.

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

### Learner-facing ECG references

Canonical corpus keys (`case_id`, PTB record numbers, Leipzig record/window names,
patient/source identifiers, file paths, and signal fingerprints) remain
server-side in Training, Rapid, and Clinical. Each mode response instead issues
a payload-free `ec_…` HMAC capability bound to the learner, mode, session, and
canonical ECG. The reference is deterministic across refresh/resume but cannot
be decoded; the server validates it only against the exact pending or
post-commit ECG already named by durable session state.

Assessment waveforms use owner/session-scoped routes. Submissions accept the
opaque reference, resolve it in constant time against the current session, and
store/grade only the canonical id. Public summaries, packets, results, errors,
tutor threads, profile history, and progress exports replace or pseudonymize
corpus identity. Source-neutral labels such as `Training ECG 0001` preserve
orientation without exposing a public-dataset lookup key. Tutor providers
receive the same sanitized identity boundary, so a model cannot echo backing
storage coordinates into its answer.

## Corpus database tables

- `cases` — one packet row per unique source-namespaced ECG/window, with source identity and packet JSON.
- `case_concepts` — concept-specific confidence tier/score index.
- `clinical_case_items` — versioned authored Clinical scenario/item definitions. The learner bank is replaced atomically only after all new items pass startup validation.

## Learner and authentication database

Identity/security tables:

- `users` — canonical user id, private normalized compatibility username,
  unique normalized email, email-verification state, display name, PBKDF2
  password hash, and timestamps. The retired email-2FA column is kept only for
  migration safety. Legacy username-only rows remain only so their owners can
  complete the required email-upgrade flow.
- `sessions` — SHA-256 hashes of random session tokens, owner, expiry, and revocation state. Reusable tokens are not stored in plaintext or exposed to browser JavaScript.
- `auth_challenges` — purpose-bound, expiry/attempt/resend-limited email
  verification, password-reset, and email-change challenges. Only a
  keyed digest of the one-time secret is stored; credential fingerprints bind
  sensitive grants to the password state that requested them.
- `export_authorizations` — one-use, short-lived progress-export grants stored only as token, session, and password-state digests.
- `auth_login_throttle` — HMAC-derived source/username-pair, source-IP, and deployment-wide pre-hash buckets. There is intentionally no username-only lockout, so one source cannot globally lock a known learner account.
- `auth_registration_throttle` — independently namespaced HMAC-derived source/username-pair, source-IP, and deployment-wide registration buckets; no raw IP address or username is stored.
- `guest_progress_claims` — immutable guest→account ownership receipt used for idempotent replay and cross-account conflict rejection.
- `account_tombstones` — durable non-identifying retirement boundary containing
  only a domain-separated digest of a deleted random internal user generation,
  deletion time, bounded reason, and schema version. It retains no raw account
  id or contact/profile data and is not part of progress export.
- `maintenance_job_state` / `maintenance_leases` — next-due state and opaque expiring cross-worker claims for bounded privacy cleanup; these tables contain no learner identifiers.

Learning evidence tables:

- `learner_profiles` — learner identity and display metadata.
- `attempts` — case response, confidence, assistance, score, errors, feedback, and timestamp.
- `objective_mastery` — legacy concept aggregate retained for compatibility.
- `subskill_mastery` — concept × subskill formative and independent aggregates, calibration errors, unique ECG/mode/morphology counts, retention state, stability, lapse, and due timestamps.
- `subskill_retention_events` — append-only server-verified evidence used to recompute diversity/retention.
- `guided_learning_events` — idempotent scene/task receipts. The public Guided endpoint is always formative; private Training/Rapid/Clinical graders add server verification.
- `pathway_progress` — authenticated Guided scene/action state.
- `learner_preferences` — owner-bound training stage, learning goal, default
  session length, Rapid pace, Guided support level, and display preferences.
  Untouched defaults are projected by `GET` and are not inserted until a
  learner intentionally saves a change, so a read cannot manufacture guest
  activity.
- `tutor_threads` / `tutor_messages` — context-scoped persistent conversations and grounded viewer actions.

Normalized assessment integrity tables:

- `assessment_leases` / `assessment_lease_cases` — one owner/mode/session
  exposure contract with frozen ECG ids, inclusive expiry, claim state, and an
  opaque submission-key digest. An expired active row stops cross-mode
  exclusion immediately; a genuinely submitting row stays protected through
  commit or rollback.
- `learner_events` / `learner_event_competencies` — answer-free, append-only
  session/item/commit/expiry/abandon events plus normalized competency scores.
  These tables deliberately contain no response JSON, diagnosis, rationale, or
  answer key; those remain in the protected mode-specific stores.

Server-owned mode ledgers:

- `training_campaigns`, `training_campaign_slots`, `training_campaign_answers` — immutable target/mimic/negative/transfer plan, pending/feedback state, and exactly-once answers.
- `rapid_rounds`, `rapid_round_answers` — pace/deadline policy, exclusions, served set, pending/feedback state, complete result ledger, and receipts.
- `clinical_shift_sessions`, `clinical_shift_answers` — lane/tier, orient/decide timing, first-look/context boundary, served ECGs, calibration, grade, and formative receipts.
- `review_sessions` — legacy adaptive-review state; the student-facing `/review` page uses the verified cross-mode mastery planner.

SQLite uses WAL, busy timeouts, guarded shared-memory connections in tests, and
explicit immediate transactions for ownership-changing guest claims, account
deletion, and atomic login/registration throttle reservations. Schema v4
registers a deterministic account-generation digest function on every writable
connection. Generated `BEFORE INSERT/UPDATE` triggers cover every direct
`user_id`/`learner_id`/`owner_id` table; child-ledger triggers require their
owner-scoped parent and reject a retired parent generation. The trigger
inventory is centralized and schema-audited so a newly introduced owner table
cannot silently omit the deletion boundary.

Retention cleanup uses the same immediate writer boundary. Expiry is inclusive;
legacy anonymous inactivity is strict, and activity in any owned parent or
child ledger preserves the whole record. A never-verified registration shell is
removed after the configured seven-day default only when it has no session,
assessment exposure, learning evidence, preference write, or guest-claim
receipt. Verified users and claimed legacy records are never candidates.
Authenticated-record duration remains an externally documented policy/readiness
decision rather than an automatic deletion rule.

Long-mode response contracts are bounded: Rapid keeps the complete served set server-side and returns `servedCount` with a 25-reference `recentServed` tail; Training keeps the complete immutable phase sequence in its slot ledger and returns only the current slot plus `phaseCounts`. Per-case Training/Rapid answers store `tutor: null`; deterministic grading never invokes a model. Conversational tutor output is created only through the explicit tutor endpoint, while Rapid round debriefs receive a bounded deterministic receipt sample with sequence numbers rather than corpus ids.

## Authentication boundary

- Browser authentication uses an `HttpOnly`, `SameSite=Lax` cookie (`Secure` in production).
- All learner, progress, tutor, dashboard, and mode APIs require an authenticated
  account with a verified email. An invalid presented credential returns 401;
  an unverified or legacy email-upgrade account returns 403; neither silently
  downgrades to a guest.
- Current-password confirmation is independently pre-hash throttled for password changes and account deletion. Other-session revocation preserves only the credential presented by the authenticated request.
- Progress export uses an explicit owner-scoped table allowlist and excludes password/session material. Account deletion verifies the current password plus exact username and transactionally removes every owned parent/child ledger and session from the live database.
- Explicit deletion, pending-registration cancellation, and expiry of an empty
  never-verified shell retire that exact random account generation in the same
  transaction before removing it. The non-identifying tombstone is intentionally
  retained indefinitely; a stale pre-deletion request receives neutral 409
  `account_unavailable` and cannot recreate any owner row. Guest erasure does
  not retire the guest namespace.
- The server never mints or refreshes a guest identity. A valid pre-existing beta
  cookie is migration-only and can neither start new anonymous learning nor
  authorize a learner API.
- Registration may defer a requested legacy claim, but the data stays in the
  guest namespace until email verification succeeds. The verified owner may
  alternatively attach that positive record once through the explicit claim
  endpoint, or discard only the presented namespace.
- Claiming is one transaction across all learning/evidence/mode tables. It is
  owner-bound, idempotent for the same account, conflict-safe across accounts,
  merge-monotonic, and leaves at most one resumable session per mode.
- The same-origin Next proxy strips forwarding identity headers. Supported Uvicorn launches use `--no-proxy-headers`, so registration throttling uses only the socket peer.

## Primary API surface

Data and registry:

- `GET /health`, `GET /dataset/status`
- `GET /concepts`, `GET /objectives`, `GET /curriculum`
- `GET /cases`, `/cases/{id}`, `/cases/{id}/packet`, `/cases/{id}/waveform`, `/cases/{id}/ptbxl-plus`

Authentication/profile:

- `POST /auth/register`, `/auth/login`, `/auth/logout`, `/auth/logout-all`,
  `/auth/logout-others`, `/auth/change-password`
- `POST /auth/email/verify/confirm`, `/auth/email/verify/resend`,
  `/auth/password-reset/request`, `/auth/password-reset/confirm`,
  `/auth/email/upgrade/request`, `/auth/email/change/request`,
  `/auth/email/change/confirm`, and `/auth/email/change/resend`
- `GET /auth/capabilities`, `/auth/me`, `/auth/sessions`,
  `/auth/guest-progress`; `POST /auth/guest-progress/claim`,
  `/auth/export/authorize`, `/auth/export`;
  `DELETE /auth/sessions/{session_id}`, `/auth/guest-progress`, `/auth/account`
- `GET /learners/{id}`, `/learners/{id}/mastery`, `/learners/{id}/competencies`, `/learners/{id}/pathway-progress`
- `PUT /learners/{id}`, `POST /learners/{id}/pathway-progress`
- `GET` / `PUT /learning/preferences`

Mode state machines:

- `GET /training/campaigns/pool`, `POST /training/campaigns`, then `/active`, `/{id}`, `/{id}/next`, `/{id}/submit`, `/{id}/abandon`, and `/{id}/waveform/{ecg_ref}`
- `POST /rapid/rounds`, then `/active`, `/{id}`, `/{id}/next`, `/{id}/submit`, `/{id}/results`, and `/{id}/waveform/{ecg_ref}`
- `GET /clinical/bank/status`, `/clinical/bank/coverage`; `POST /clinical/shift/start`, then `/active`, `/{id}/next`, `/{id}/phase`, `/{id}/context`, `/{id}/answer`; `GET /clinical/shift/{id}/report` and `/clinical/shift/{id}/waveform/{ecg_ref}`

Learning/adaptation/tutor:

- `POST /learning-events/guided`
- `GET /learning/resume`, `/learning/activity`, `/adaptive/plan`
- `POST /tutor/message`; `GET /tutor/threads`, `/tutor/thread/{id}`
- deterministic case grading/viewer endpoints under `/grade/*` and `/viewer/map-point`

All learner-id request fields are advisory compatibility fields. Stateful
handlers resolve the effective learner from the authenticated, verified account
and enforce ownership on every resumable session/thread. A legacy guest cookie
is consulted only by the explicit preview, claim, and discard migration APIs.
