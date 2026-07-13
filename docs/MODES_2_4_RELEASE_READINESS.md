# Modes 2–4 release readiness

**Audit date:** 2026-07-12 (implementation updated through 2026-07-13)  
**Scope:** Training, Rapid, Clinical, authentication, objective evidence, adaptive planning, AI support, and learner-facing data provenance.

## Release posture

The student product is implemented as a **formative release candidate**. Training and Rapid are backed by the complete audited eligible ECG corpus, support server-owned sessions as long as 5,000 unique recordings, and fail closed when an exact concept/subskill pool is too small. Clinical serves 103 unique real PTB-XL ECGs with 103 separately authored, startup-validated scenarios.

This is not a competence-certification product. Clinical action content remains visibly formative and pending named clinician sign-off; ACLS/arrest, evolving acute ischemia, true serial comparison, and medication/electrolyte causality remain locked where the installed sources cannot support them. Automated harness success is never called clinician review.

## Executable product contract

| Area | Current contract | Status |
|---|---|---|
| Learner waveform corpus | 22,497 records: 21,799 PTB-XL plus 698 imported Leipzig expert rhythm windows; 21,855 Tier A/B student-facing records. | Implemented |
| Synthetic-data boundary | Learner-facing startup requires a complete real corpus by default. Synthetic packets remain explicit test/harness fixtures and cannot enter production Clinical, Training, Rapid, independent evidence, or retention. | Implemented and regression-tested |
| Training | Server-owned campaigns of 10, 25, 50, 100, 500, 1,000, or 5,000 distinct ECGs, capped honestly by the exact concept × subskill pool. Plans interleave target, close mimic, other negative, and unannounced transfer roles without replacement. | Implemented |
| Rapid | Server-owned rounds of 5, 10, 25, 50, 100, 500, 1,000, or 5,000 unique ECGs with durable served and answer ledgers, refresh/login resume, exact replay, server deadlines, result pagination, and complete-pool selection. | Implemented |
| Clinical | 103 unique real PTB ECGs; 103 complete authored scenario signatures across clinic, ward, and ED-non-arrest lanes and at least eight declared families. Startup atomically replaces the bank only after every item passes provenance and clinical harness checks. | Implemented as formative content |
| Question variety | Training rotates classification, target/mimic comparison, trace localization, caliper/numeric measurement, evidence notes, and transfer roles where the selected subskill supports them. Rapid separates a structured eight-domain read from emergency dominant-finding tasks and requires trace proof in ward/untimed reads. Clinical includes MCQ, click, spot-error, old/new/insufficient-data, triage, and stepwise tasks; no type exceeds the bank diversity ceiling and at least 30% are trace-native. | Implemented |
| Authentication | Username/password accounts, PBKDF2 hashing, HttpOnly SameSite cookies, hashed server session tokens, revocation/logout-all, password change, strict invalid-session behavior, login/registration throttling, and per-account ownership checks. | Implemented; institutional SSO/recovery is a deployment follow-up |
| Guest continuity | Every browser receives an opaque server guest identity. Registration/login offers an explicit, default-off claim choice; a transactional, idempotent claim moves server-owned guest learning records, resolves active-session collisions, rotates identity cookies, and clears guest browser caches. | Implemented |
| Objective registry | 115 objective definitions with concept mappings, eight subskills, allowed task templates, evidence ceilings, and live corpus depth. Every served task binds to an exact objective/subskill source contract. | Implemented |
| Competency/retention | Formative and independent evidence are separate. The store tracks assistance, high-confidence errors, unique ECGs, morphology/source diversity, modes, lapses, spaced retrieval, stability, and next-due state. Client-declared scoring cannot mint independent evidence. | Implemented as a transparent learning model, not psychometric certification |
| Adaptive planner | A separate verified scheduler ranks due/overdue retrieval, high-confidence misses, weak independent evidence, diversity gaps, and unseen eligible cells. It prescribes Training → Rapid → eligible Clinical stages and a cross-concept integration read. | Implemented |
| Adaptive plan coach | A persistent conversational role can explain the server-issued queue and study sequence from the verified plan summary. It cannot score, alter the queue, invent a case, or create ground truth. | Implemented |
| ECG tutor | Persistent, context-scoped threads support questions in Guided, Training, Rapid, Clinical, debrief, and adaptive-plan contexts. Model responses are schema-validated; case claims and viewer actions are clamped to packet evidence and real ROIs. | Implemented with deterministic fallback |
| Clinical scenario control | The server, not the model, owns context reveal, phase deadlines, branching, answer keys, and exactly-once receipts. AI may coach after commitment but cannot invent vitals, labs, outcomes, actions, or a new scenario state. | Implemented |

## Data-source boundaries

| Source | Installed use | Explicitly disallowed use |
|---|---|---|
| PTB-XL + PTB-XL+ | Static 12-lead Guided examples, Training, broad/focused Rapid, and the 103-ECG Clinical waveform bank. | Unsupported acute timing, event causality, arrest state, or serial change. |
| Leipzig Heart Center | 698 checksum-verified expert-labelled 10-second rhythm windows in focused Training/Rapid. Current import: 180 sinus, 279 SVT, 77 paced, 130 WCT, 32 AF. | Broad full-read scoring, Clinical management, symptoms, hemodynamics, or ACLS. Labels are target-only rather than exhaustive morphology truth. |
| MIMIC-IV-ECG private GCS | Inventory/join adapter only. The source of waveform truth is an environment-configured private prefix such as `gs://example-private-bucket/...`; Drive is not treated as complete. | No learner-facing import in this release. MIMIC-ECG-EXT ICD rows are encounter outcomes, not per-ECG morphology truth; machine reports are candidate assertions, not independent human labels. |
| STAFF III | Documented future candidate for acute ischemia/dynamic ST-change after local hydration, license review, and source-contract validation. | VT/arrest/ACLS or any unsupported outcome claim. |

## Mode-specific evidence rules

### Training

- The setup shows the exact number of distinct eligible ECGs and target/mimic/negative role depth before start.
- A requested campaign is shortened rather than padded if the exact pool is smaller.
- Every slot has an immutable server position, phase, ECG id, target presence, and response ledger.
- Resume restores pending or feedback state; replay cannot duplicate a receipt.
- Only a no-hint, exact-target, trace-native transfer can enter the independent-evidence path. Other coached, explanatory, synthesis, and application work remains formative.
- Submit, grading, and evidence persistence are deterministic and never wait for an LLM. The grounded tutor is available on explicit post-commit use and never supplies the answer key.
- The immutable 5,000-slot phase sequence stays server-side; responses expose the current slot and aggregate phase counts instead of repeating the complete plan.

### Rapid

- Emergency is a 20-second dominant-finding first look, not a simulated code or full interpretation.
- Ward uses 75 seconds; untimed has no deadline. Timed deadlines are server-owned and survive refresh.
- Ward/untimed submissions require a server-verified QRS localization action before an on-time answer is accepted.
- Timeout records are retained for calibration, but cannot create positive mastery.
- Mixed rounds select without replacement from the complete audited broad PTB pool. Focused expert rhythm windows are admitted only for their exact target and never penalize unassessed morphology claims.
- Per-case submit, feedback, and receipts are provider-independent. AI is available through the explicit post-commit tutor and the bounded round debrief, so provider latency cannot stall a long round.
- The complete served ledger remains durable and selector-authoritative on the server; learner responses expose `servedCount` plus only the 25 most recent ids to keep 5,000-case response size bounded.
- Post-round AI synthesis receives deterministic receipts, not hidden labels, and offers only live-coverage Training/Clinical handoffs.

### Clinical

- The learner first commits an ECG-only category and confidence. Authored symptoms/context are withheld at the API boundary until that commitment is persisted.
- The server owns orient/decide phases, deadlines, current item, context reveal, grading, and exactly-once receipts.
- A handoff requesting `apply_in_context` or `localize` serves only an item that can issue that exact receipt; unsupported requests fail closed.
- Apply-in-context receipts are always formative while named clinician sign-off is pending. Localize receipts require server grading against packet-derived ROI geometry.
- “Old/new” items can award only what the supplied comparison evidence permits; a missing authentic prior makes “cannot determine / obtain a prior” the supported construct.
- Resting PTB ECGs are never relabelled as arrest rhythms or used to award ACLS, transient-event, acute-timing, or causal treatment mastery.

## AI separation of duties

1. **Truth and scoring:** deterministic corpus labels, measurements, ROIs, source policy, and server graders.
2. **Session/scenario driver:** deterministic server state machines with immutable authored contracts.
3. **Case tutor/attending:** conversational explanation and Socratic support constrained to the current packet and learner assistance state.
4. **Debrief/integration coach:** summarizes only deterministic result receipts and connects concepts after a set.
5. **Adaptive scheduler:** a separate non-generative service reads competency, spacing, calibration, and source eligibility to choose the next verified destinations.
6. **Adaptive plan coach:** conversationally explains that fixed plan but has no authority to change it or write evidence.

This separation is deliberate: generative fluency is useful for explanation and reflection, while source selection, clinical facts, scoring, and mastery updates require auditable deterministic contracts.

## Remaining external release gates

These are not implementation shortcuts and must remain visible:

- A named clinician must review/version the Clinical action policies, scenario language, distractors, acuity limits, and every pilot item before the bank is presented as clinically reviewed.
- ACLS/resuscitation requires a validated rhythm stream plus pulse/perfusion state, event timing, response data, and a current reviewed algorithm.
- Acute/evolving ischemia requires a validated acute/serial source; chronic resting patterns cannot prove acuity.
- True old-versus-new mastery requires authentic paired recordings with valid timestamps and comparison governance.
- Medication/electrolyte causality requires separately reviewed medication, dose/timing, interaction, clearance, and laboratory data.
- Formal screen-reader, 200% zoom, touch, reduced-motion, and representative-learner validation must supplement the automated accessibility/responsive suite.
- Institutional deployment still needs its chosen password-recovery/SSO policy, managed database/object storage, backups, monitoring, and privacy operations.
- Prospective learner studies and item calibration are required before any score is called competence, readiness, or certification.

## Verification bar

Release verification must run against a complete real corpus and includes:

```powershell
$env:PYTHONPATH="backend"
python -m pytest backend/tests -q

cd frontend
npm run test:coords
npm run typecheck
npm audit --omit=dev --audit-level=moderate
npm run build
npm run e2e
```

The final handoff should report the observed counts from that run, not a stale checked-in number.
