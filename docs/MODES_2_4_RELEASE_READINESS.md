# Modes 2–4 release readiness

**Audit date:** 2026-07-12 (implementation updated through 2026-07-17)
**Scope:** Training, Rapid, Clinical, authentication, objective evidence, adaptive planning, AI support, and learner-facing data provenance.

## Release posture

The student product is implemented as a **formative release candidate**. Training and broad Rapid are backed by the complete audited eligible ECG corpus, while an explicit Emergency-rhythm Rapid lane uses a separately manifest-gated 584-fragment MLII supplement. Server-owned sessions fail closed when an exact concept/subskill pool is too small. Clinical serves 103 patient cases backed by 106 unique real PTB-XL ECG records, including three authenticated prior/current pairs; every materialized item is startup-validated.

This is not a competence-certification product. Clinical action content remains visibly formative and pending named clinician sign-off. Emergency rhythm recognition may earn exact waveform evidence, but the separately authored 2025 AHA patient-state/action questions are formative and cannot infer pulse, stability, arrest, or management from the strip. Evolving acute ischemia, acute treatment-response comparison, and medication/electrolyte causality remain locked where installed sources cannot support them. The three chronic same-patient comparisons establish chronology, not admission, intervention, or causation. Automated harness success is never called clinician review.

## Executable product contract

| Area | Current contract | Status |
|---|---|---|
| Learner waveform corpus | Core: 22,497 records (21,799 PTB-XL + 698 Leipzig rhythm windows), with 21,855 Tier A/B student-facing records. Explicit Emergency-rhythm supplement: 584 reviewed single-lead ventricular-rhythm fragments, isolated from broad selection. | Implemented and exhaustively release-audited |
| Synthetic-data boundary | Learner-facing startup requires a complete real corpus by default. Synthetic packets remain explicit test/harness fixtures and cannot enter production Clinical, Training, Rapid, independent evidence, or retention. | Implemented and regression-tested |
| Training | Server-owned campaigns of 10, 25, 50, 100, 500, 1,000, or 5,000 distinct ECGs, capped honestly by the exact concept × subskill pool. Plans interleave target, close mimic, other negative, and unannounced transfer roles without replacement. | Implemented |
| Rapid | Server-owned rounds of 5, 10, 25, 50, 100, 500, 1,000, or 5,000 unique ECGs with durable ledgers, owner-bound leases, answer-free events, refresh/login resume, exact replay, server deadlines, result pagination, and complete-pool selection. Adaptive/mixed practice uses the broad corpus; Emergency rhythm practice opts into only the manifest-gated supplement and separates waveform recognition from formative patient-state/AHA application. | Implemented |
| Clinical | 103 patient cases backed by 106 unique real PTB ECGs and 103 ECG-specific authored vignettes across clinic, ward, and ED-non-arrest lanes, materialized from 22 core graded templates. Startup atomically replaces the bank only after every item passes provenance and clinical harness checks. The audit endpoint reports lane, interaction, authored-setting, unique-ECG, and source counts from the live serving bank. | Implemented as formative content; template breadth still expanding |
| Question variety | Training rotates classification, target/mimic comparison, trace localization, packet-grounded numeric fill-in, deterministic single-choice mechanism/synthesis/context-boundary work, evidence-source matching, and transfer roles where the selected subskill supports them. Rapid separates a structured eight-domain read from emergency dominant-finding tasks and requires trace proof in ward/untimed reads. Ward provides fast structured choices for seven sweep domains plus a precise-entry fallback and synthesis; Emergency uses a visible, filtered, keyboard-operable finding combobox. The audited Clinical bank contains 20 stepwise, 18 triage, 18 spot-error, 17 MCQ, 15 trace-click, 12 evidence-source matching, and 3 numeric fill-in interactions. Three stepwise cases now use authenticated same-patient, time-ordered PTB-XL pairs; the generic old/new item format remains absent from learner serving. | Implemented interaction mix and three authenticated longitudinal pilots; broader acute serial coverage remains open |
| Authentication | Account-required learning; unique verified email; username-or-email sign-in; PBKDF2 hashing; HttpOnly SameSite cookies; hashed server session tokens; verification/resend; generic password recovery; optional email-code protection; verified email change; current/other/all-device revocation; password change; strict invalid-session behavior; pre-hash throttling; owner-scoped export; and confirmed transactional deletion. | Implemented and security-tested locally; sender-domain/provider activation, institutional SSO, and production edge smoke remain external gates |
| Assessment identity | Training, Rapid, and Clinical expose only payload-free learner/mode/session-bound `ec_…` ECG capabilities and source-neutral ordinal labels. Canonical dataset ids, patient/record identity, file paths, signal fingerprints, and diagnosis-bearing authored ids remain server-side across payloads, waveforms, errors, tutor context, profile history, and progress export. | Implemented and regression-tested |
| Account-only continuity | Production creates no guest identity and permits no anonymous learning. A pre-existing beta browser record remains separate during registration and delivery failure, then may be attached only after successful verification through an owner/cookie-bound transaction; a verified learner may instead attach or discard it explicitly. | Implemented; bounded legacy migration only |
| Objective registry | 123 objective definitions with concept mappings, eight subskills, allowed task templates, evidence ceilings, and live corpus depth. Ventricular-rhythm objectives become available only when the exact audited supplement is installed. Every served task binds to an exact objective/subskill source contract. | Implemented |
| Competency/retention | Formative and independent evidence are separate. The store tracks assistance, high-confidence errors, unique ECGs, morphology/source diversity, modes, lapses, spaced retrieval, stability, and next-due state. Client-declared scoring cannot mint independent evidence. | Implemented as a transparent learning model, not psychometric certification |
| Adaptive planner | A separate verified scheduler ranks due/overdue retrieval, high-confidence misses, weak independent evidence, diversity gaps, and unseen eligible cells. It prescribes Training → Rapid → eligible Clinical stages and a cross-concept integration read. | Implemented |
| Adaptive plan coach | A persistent conversational role can explain the server-issued queue and study sequence from the verified plan summary. It cannot score, alter the queue, invent a case, or create ground truth. | Implemented |
| ECG tutor | Persistent, context-scoped threads support questions in Guided, Training, Rapid, Clinical, debrief, and adaptive-plan contexts. Model responses are schema-validated; case claims and viewer actions are clamped to packet evidence and real ROIs. | Implemented with deterministic fallback |
| Clinical scenario control | The server, not the model, owns the current two-stage ECG-first/context-reveal flow, phase deadlines, answer keys, and exactly-once receipts. Conditional scenario graphs are not yet implemented. AI may coach only after commitment and cannot invent vitals, labs, outcomes, actions, or a new scenario state. | Two-stage flow implemented; branching graph open |

## Data-source boundaries

| Source | Installed use | Explicitly disallowed use |
|---|---|---|
| PTB-XL + PTB-XL+ | Static 12-lead Guided examples, Training, broad/focused Rapid, and 103 Clinical patient cases backed by 106 distinct ECGs, including three authenticated chronic same-patient comparisons. | Unsupported acute timing, treatment causality, arrest state, or broad acute-serial coverage. |
| Leipzig Heart Center | 698 checksum-verified expert-labelled 10-second rhythm windows in focused Training/Rapid. Current import: 180 sinus, 279 SVT, 77 paced, 130 WCT, 32 AF. | Broad full-read scoring, Clinical management, symptoms, hemodynamics, or ACLS. Labels are target-only rather than exhaustive morphology truth. |
| ECG Fragment Database for the Exploration of Dangerous Arrhythmia | 584 release-audited, source-author-labelled MLII fragments in the explicit Rapid Emergency-rhythm scope: VF 240, ventricular flutter 97, ventricular tachycardia 175, polymorphic VT 72. Exact recognition/discrimination only. | Ordinary mixed selection, Clinical cases, 12-lead interpretation, pulse/stability/arrest/shockability claims, treatment response, or management evidence. VTTdP is not called torsades without preceding long-QT evidence. |
| MIMIC-IV-ECG private GCS | Inventory/join adapter only. The source of waveform truth is an environment-configured private prefix such as `gs://example-private-bucket/...`; Drive is not treated as complete. | No learner-facing import in this release. MIMIC-ECG-EXT ICD rows are encounter outcomes, not per-ECG morphology truth; machine reports are candidate assertions, not independent human labels. |
| STAFF III | Checksum-gated offline authoring adapter built from the pinned 1.0.0 source: 140 review-required baseline → controlled balloon-occlusion → recovery episodes / 420 frames after one explicit source-quality exclusion. Protocol order only; no learner runtime connection yet. | Student serving before ROI/morphology adjudication; spontaneous ACS, STEMI/OMI, treatment response, VT/arrest/ACLS, symptoms, outcomes, or management. |

## Mode-specific evidence rules

### Training

- The setup shows the exact number of distinct eligible ECGs and target/mimic/negative role depth before start.
- A requested campaign is shortened rather than padded if the exact pool is smaller.
- Every slot has an immutable server position, phase, canonical server-only ECG id, target presence, and response ledger. The browser receives only the owner/session capability for the active tracing.
- Resume restores pending or feedback state; replay cannot duplicate a receipt.
- Only a no-hint, exact-target, trace-native transfer can enter the independent-evidence path. Other coached, explanatory, synthesis, and application work remains formative.
- Submit, grading, and evidence persistence are deterministic and never wait for an LLM. The grounded tutor is available on explicit post-commit use and never supplies the answer key.
- The immutable 5,000-slot phase sequence stays server-side; responses expose the current slot and aggregate phase counts instead of repeating the complete plan.

### Rapid

- The Emergency-rhythm practice mode presents a short MLII strip and 1, 3, or 3 questions depending on selected depth. Exact rhythm recognition is assessed separately from source-boundary and version-labelled AHA application questions; those contextual questions remain formative.
- The 20-second Emergency pace is a dominant-finding first look, not a simulated code or full interpretation. Focused/complete question depths receive larger server-owned allowances, and no clock starts until the waveform and prompts report ready.
- Ward uses 120 seconds; untimed has no deadline. Timed deadlines are server-owned and survive refresh.
- Ward exposes quick structured choices for seven sweep domains, retains a precise-entry fallback, and keeps the evidence-limited synthesis as an explicit final step. Emergency finding selection is visible, filtered, keyboard-operable, and includes uncertainty.
- Ward/untimed submissions require a server-verified QRS localization action before an on-time answer is accepted.
- Timeout records are retained for calibration, but cannot create positive mastery.
- Mixed rounds select without replacement from the complete audited broad PTB pool. The Emergency-rhythm supplement is reachable only through its explicit practice mode or an exact supported handoff; ordinary mixed/adaptive selectors cannot query it. Focused rhythm windows are admitted only for their exact target and never penalize unassessed morphology claims.
- Every pending ECG is frozen in an owner-bound assessment lease before presentation. The exact item is claimed before grading; answer, attempt, receipts, mastery evidence, normalized answer-free event, terminal lease, and round advance commit atomically under `atomic_v2` integrity. Idle expiry and abandonment are audited exactly once, same-item retries share one reservation generation, and ECGs live in another mode are excluded from selection.
- Per-case submit, feedback, and receipts are provider-independent. AI is available through the explicit post-commit tutor and the bounded round debrief, so provider latency cannot stall a long round.
- The complete served ledger remains durable and selector-authoritative on the server; learner responses expose `servedCount` plus only the 25 most recent opaque references to keep 5,000-case response size bounded.
- Post-round AI synthesis receives deterministic receipts, not hidden labels, and offers only live-coverage Training/Clinical handoffs.

### Clinical

- The learner first commits an ECG-only category and confidence. Authored symptoms/context are withheld at the API boundary until that commitment is persisted.
- The server owns orient/decide phases, deadlines, current item, context reveal, grading, and exactly-once receipts.
- A handoff requesting `apply_in_context`, `localize`, or `measure` serves only an item that can issue that exact receipt; unsupported requests fail closed.
- A handoff requesting `measure` can serve only a grounded numeric fill-in whose objective and packet feature match the requested cell. The response bounds are public; the packet feature and acceptance tolerance never cross the precommit boundary.
- Apply-in-context, localize, and measure receipts are always formative while named clinician sign-off is pending. Localize receipts require server grading against packet-derived ROI geometry; measure receipts require the exact packet value.
- The current release-bank audit is 103 serving cases / 106 distinct PTB ECGs: clinic 35, ward 34, ED 34; stepwise 20, triage 18, spot-error 18, MCQ 17, trace-click 15, evidence-source matching 12, and numeric fill-in 3. Matching is deliberately balanced 4 clinic / 4 ward / 4 ED, and the bank has at least 90 distinct authored setting labels. Synthetic or fixture provenance makes startup, audit, serving, and grading fail closed.
- Three stepwise episodes use authenticated patient-linked prior/current pairs and teach defensible comparison reasoning. The generic old/new item format still is not learner-serving, and these chronic pairs do not award acute treatment-response or causality mastery.
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
- Clinical ACLS/resuscitation mastery still requires validated pulse/perfusion state, event timing, response data, and named review of the current algorithm. The installed rhythm stream supports waveform recognition only; AHA application remains formative authored simulation.
- Acute/evolving ischemia requires reviewer-adjudicated morphology/ROI truth on a validated acute/serial source. The STAFF III candidate package is ingested but remains learner-locked; chronic resting patterns cannot prove acuity.
- True old-versus-new mastery requires authentic paired recordings with valid timestamps and comparison governance.
- Medication/electrolyte causality requires separately reviewed medication, dose/timing, interaction, clearance, and laboratory data.
- Formal screen-reader, 200% zoom, touch, reduced-motion, and representative-learner validation must supplement the automated accessibility/responsive suite.
- Institutional deployment still needs an approved transactional-email sender/provider,
  delivered-mail and background-queue monitoring, any chosen SSO policy, managed
  database/object storage, backups, and privacy operations.
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
