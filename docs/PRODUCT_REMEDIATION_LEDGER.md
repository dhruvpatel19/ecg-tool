# Student product remediation ledger

This is the working defect ledger for the ECG learning product. It is intentionally stricter than a feature checklist: an item is **verified** only after its focused automated test passes. The combined local gate now passes against the complete real-data corpus, but that does not satisfy the external clinical-governance, production-deployment, institutional-identity, retention-policy, or representative-user validation gates. External items stay visible instead of being bridged with synthetic or unsupported content.

Status legend: **verified** · **verified locally** · **implemented / combined test pending** · **in progress** · **open** · **external gate**

## Reopened release audit — 2026-07-14

The earlier combined green run at the bottom of this document is a historical
snapshot, not the status of the current worktree. Persona testing and
adversarial assessment review reopened material product defects that the older
feature-oriented gate did not detect. The release is therefore **not green** and
the production Vercel site remains the prior demo.

Current repair state:

| Area | Current evidence | Status |
|---|---|---|
| Guided precommit privacy | Opaque owner/lesson-bound ECG capabilities now replace corpus ids; source labels, reports, measurements, ROIs, answer objectives, and tutor answer context stay withheld. Focused backend: 46 passed / 4 skipped; fresh isolated-stack browser privacy proof: 1 passed. | verified locally |
| Guided cross-mode launches | Every remaining Rapid/Clinical launch names an exact executable destination; unsupported ectopy, serial, device, chest-pain, and capstone launches were removed rather than proxied. Contract suite: 14 passed. | verified locally |
| Training scoring integrity | Pattern classification and the selected subskill now score and render as separate axes; campaign summaries report both and their joint outcome. The stabilized Rapid/Training/Guided integrity slice is 105 passed, and the reviewed mechanism browser flow passes on the fresh stack. | verified locally |
| Training student feedback | Single-choice keys are revealed postcommit, disabled Commit shows a missing-requirements checklist, visual hints disclose the coached/no-independent-receipt consequence, source dataset names stay blinded precommit, and a compact mobile task dock precedes the ECG. Focused mobile and structured-application browser checks pass. | verified locally |
| Training item quality | Mechanism distractors now come from electrically adjacent families and vary deterministically. Focused adversarial tests: 2 passed. | verified locally |
| Rapid mastery integrity | Synthesis is formative-only until deterministic per-domain grading exists; filler sweeps, select-all, unsupported extras, and incidental findings cannot mint mastery. Affected backend suite: 47 passed. | verified locally |
| Rapid recovery/privacy | A temporarily unavailable completed-result ledger preserves an explicitly partial cached review instead of erasing it; source dataset name is hidden until commit. Fresh-stack recovery browser check passes. | verified locally |
| Clinical longitudinal adaptation | Prior exact formative application history now changes later case priority without inflating independent mastery. Clinical regression: 48 passed. | verified locally |
| Clinical timed mobile workflow | At 320/390 px the server clock, ECG, task, confidence, and submit controls remain reachable without document-level scrolling; focused mobile, progressive-flow, and desktop workspace checks pass. | verified locally |
| Dashboard / My Learning coherence | The existing functional contracts remain intact, but user review rejected the current information architecture, visual hierarchy, and separation between dashboard, objectives, mastery, and coaching. A consolidated student home and evidence-aware coach redesign is now in progress. | in progress |
| Student authentication | Account-required routes, verified-email registration, username-or-email sign-in, generic password recovery, optional email-code protection, email/password change, session inventory/revocation, legacy-record migration, export/deletion, and owner boundaries are implemented. The focused email/auth/retention/readiness backend gate passes 49 checks; final combined browser regression is in progress. Sender-domain/provider activation, institutional SSO, and production edge smoke remain external. | implemented / combined test pending |
| Clinical content depth | 103 patient cases backed by 106 distinct real PTB-XL ECGs exist, but they currently derive from 22 base templates / 34 surfaces rather than 100 materially distinct governed clinical decisions. | open |
| Clinical bedside realism | Stable/unstable perfusion variation, preserved vitals, authentic serial pairs, validated rhythm streams for resuscitation, and drug/lab timing joins are not all available. | open / external data gate |
| Clinical governance | Named clinician review/version manifest and policy sign-off are absent; learner UI must continue to call the cases supervised formative prototypes. | external gate |
| Public entry and onboarding | Signed-out `/` is now a real public landing page rather than the private dashboard, with clear student-oriented mode explanations, an explicit account requirement, responsive navigation, and distinct focused sign-in versus contextual registration. Focused landing/public trust checks pass locally; final email-state and full-browser regression is in progress. In-product first-run guidance remains open. | implemented / combined test pending |
| AI content coverage | Reviewed deterministic teaching and precise phrase routing now cover all 46/46 canonical concepts, with ambiguous-word and no-management-overreach tests. Paid deployed-model smoke is still outstanding. | verified locally / external provider gate |
| Full release regression | The fresh full backend suite passes (538 passed). Full frontend TypeScript, ESLint, and production build pass after the public-entry redesign. Focused public/auth/shell browser gates pass; the complete browser, corpus-artifact, dependency, paid-provider, and deployed-host matrix is still running or outstanding. | in progress |

## Product shell and information architecture

| # | Issue / acceptance condition | Status |
|---:|---|---|
| 1 | One canonical name and route for each of the four learning modes | verified |
| 2 | Legacy Tutorial, Concepts, and Interpret URLs redirect without reviving duplicate UIs | verified |
| 3 | Student navigation separates learning modes from the learner record | verified |
| 4 | Navigation remains compact and usable inside ECG workspaces | verified |
| 5 | Dashboard recommendation comes from the server planner, not client guesswork | verified |
| 6 | Dashboard distinguishes a personalized recommendation from a general fallback | verified |
| 7 | Dashboard loading actions cannot be clicked before their destination exists | verified |
| 8 | Dashboard metrics say mastery estimate, assessed skills, due skills, and recorded attempts honestly | verified |
| 9 | Progress view and study-plan view do not present conflicting next actions | verified |
| 10 | Guided hub no longer opens as a marketing-heavy scroll wall | verified |
| 11 | Guided modules are collapsed until the learner asks for detail | verified |
| 12 | Curriculum lesson chips deep-link to their actual scene | verified |
| 13 | Canonical mode handoffs preserve a safe return destination | verified |
| 14 | Desktop ECG workspaces keep the trace and current task above the fold | verified |
| 15 | Automated mobile, 200% zoom, keyboard, touch-target, focus, and accessibility contracts pass; representative assistive-technology review remains separate | verified locally; manual validation external gate |

## ECG viewer and Guided learning

| # | Issue / acceptance condition | Status |
|---:|---|---|
| 16 | A case change can never leave the prior waveform visible | verified |
| 17 | Viewer exposes loading, failure, retry, and `aria-busy` states | verified |
| 18 | Pre-commit Training/Rapid cannot receive grading ROIs or answer annotations | verified |
| 19 | Viewer controls have task-specific accessible names | verified |
| 20 | Guided production modules use a trace-first two-column workspace | verified |
| 21 | Guided scene completion stays distinct from competency mastery | verified |
| 22 | “Review later” stays distinct from completion | verified |
| 23 | Tutor thread scope is exact module + scene, not only lesson-wide | verified |
| 24 | Tutor failure restores the learner’s question and does not mark assistance | verified |
| 25 | Tutor cannot invent case facts, labels, or ROIs outside the current packet | verified |
| 26 | Foundations synthetic visual exercises cannot mint independent evidence | verified |
| 27 | Foundations uses real PTB teaching traces and fails closed when its real bundle is absent | verified |
| 28 | Embedded Foundations and native Guided progress agree after refresh/account transition | verified |

## Focused Practice (Training)

| # | Issue / acceptance condition | Status |
|---:|---|---|
| 29 | Campaign lengths include 10 through 5,000 unique real ECGs selected from the 21,855-record eligible Training/Rapid corpus | verified |
| 30 | The exact concept × subskill pool determines the honest maximum length | verified |
| 31 | A frozen campaign roster never repeats an ECG | verified |
| 32 | Target, close-mimic, other-negative, and hidden transfer roles are represented | verified |
| 33 | Queued cases adapt after each committed answer without changing the frozen roster | verified |
| 34 | Adaptation records a learner-facing target/contrast reason | verified |
| 35 | Pending transfer remains unannounced | verified |
| 36 | Prompt wording and binary option order vary deterministically | verified |
| 37 | Handoff intent can replace a conflicting saved campaign only with an explicit warning | verified |
| 38 | Ungrounded measurement/application tasks are labeled formative rehearsal | verified |
| 39 | Unseen, formative-only, and independently assessed states never show fake mastery | verified |
| 40 | Answer, campaign advance, attempt, receipts, and retention commit atomically | verified |
| 41 | Database enforces at most one active campaign per learner or resolves start races safely | verified |
| 42 | Recent independent ECGs are excluded across campaigns where pool depth permits | verified |
| 43 | Matching and grounded fill-in variants supplement choice tasks | verified |

## Rapid Practice

| # | Issue / acceptance condition | Status |
|---:|---|---|
| 44 | Rounds of 5 through 5,000 use unique server-owned ECG ledgers over the complete 21,855-record eligible corpus | verified |
| 45 | Ward provides a 120-second, eight-domain sweep with quick structured choices, a precise-entry fallback, and an evidence-limited synthesis; untimed retains the same complete read | verified |
| 46 | Emergency first-look asks for one dominant finding rather than a fake full interpretation | verified |
| 47 | Ward/untimed reads require trace-native localization evidence before an on-time submit | verified |
| 48 | Timeout is recorded but can never create positive mastery | verified |
| 49 | Emergency finding selection is a visible, filtered, keyboard-operable combobox and includes explicit uncertainty | verified |
| 50 | Pause-between-ECGs and timed/untimed controls have keyboard and ARIA behavior | verified |
| 51 | Round resume, result pagination, and exact replay are server-authoritative | verified |
| 52 | Pre-contract incomplete answer rows are quarantined, not treated as complete | verified |
| 53 | Claim-before-grade answer, round advance, attempt, receipts, mastery evidence, normalized answer-free event, and terminal owner-bound lease commit atomically; replay, expiry, abandonment, and cross-mode exposure are isolated | verified |
| 54 | Post-round integration uses deterministic receipts and only live handoff destinations | verified |

## Clinical cases

| # | Issue / acceptance condition | Status |
|---:|---|---|
| 55 | At least 100 distinct real-ECG cases are learner-serving | verified (103 cases backed by 106 distinct real PTB-XL ECGs) |
| 56 | ECG-first commitment occurs before symptoms/context cross the API boundary | verified |
| 57 | Server owns stage, deadlines, answer keys, scoring, and context reveal | verified |
| 58 | First-look category and confidence receive explicit feedback | verified |
| 59 | Stepwise decisions are server-gated and cannot be answered out of sequence | verified |
| 60 | Click and numeric tasks bind to packet-derived geometry/measurement | verified |
| 61 | Case result separates ECG recognition, reasoning, decision, and calibration | verified |
| 62 | Case detail/review modal is a real accessible dialog with recovery behavior | verified |
| 63 | Clinical formative receipts shape future recommendations without claiming independent competence | verified |
| 64 | True serial comparison uses an authentic patient-linked prior/current pair | external gate |
| 65 | ACLS/resuscitation uses a validated rhythm stream plus pulse/perfusion/timing state | external gate |
| 66 | Medication/electrolyte causality uses reviewed dose, timing, interaction, clearance, and lab data | external gate |
| 67 | Named clinician reviews and versions every management policy and pilot item | external gate |

## Authentication, privacy, and persistence

| # | Issue / acceptance condition | Status |
|---:|---|---|
| 68 | Passwords are slow-hashed and sessions use hashed HttpOnly SameSite tokens | verified |
| 69 | Login, registration, and reauthentication are throttled | verified |
| 70 | A pre-existing beta browser record is offered only after positive detection and verified sign-in, with explicit attach/discard | verified locally |
| 71 | Current/other/all-device sessions can be listed and revoked with opaque public IDs | verified |
| 72 | Sign-out actions require explicit confirmation | verified |
| 73 | No new guest identity is created; a presented legacy browser record can be explicitly discarded without touching the signed-in account | verified locally |
| 74 | Account deletion is transactional, confirmed, and owner-scoped | verified |
| 75 | Progress export is owner-scoped and withholds pending/reassessment answer keys | verified |
| 76 | Export uses an explicit schema allowlist rather than `SELECT *` | verified |
| 77 | Export requires fresh reauthentication before download | verified |
| 78 | Password recovery uses a generic non-enumerating request, hashed one-time proof, session revocation, and a production-safe SMTP boundary | verified locally; sender/provider activation external gate |
| 79 | Public registration requires a unique verified email before learning routes open | verified locally |
| 80 | Legacy-browser and never-verified account cleanup enforce configured retention windows automatically | verified locally; production policy acknowledgement external gate |

## Learning record and adaptive system

| # | Issue / acceptance condition | Status |
|---:|---|---|
| 81 | Objective registry covers every concept × subskill pair already stored | verified |
| 82 | New attempts, Guided events, retention events, and receipts carry registry version | verified |
| 83 | Foreign keys are enabled and the database passes integrity/foreign-key checks | verified |
| 84 | Readiness fails when verified Rapid rows lack receipts or registry cells are unknown | verified |
| 85 | Unseen objectives never receive a fabricated prior percentage in curriculum UI | verified |
| 86 | Formative and independent evidence remain separate throughout planner/profile APIs | verified |
| 87 | Planner ranks due retrieval, confident misses, weak independent evidence, diversity, then unseen cells | verified |
| 88 | AI plan coach can explain but cannot alter the verified server queue | verified |
| 89 | Scenario/tutor AI cannot grade, select ground truth, or write mastery directly | verified |
| 90 | Pending assessment leases expire safely without leaking keys or trapping a learner forever | verified |
| 91 | A unified answer-free learner-event ledger supports recovery and audit across all four modes | verified |

## Data, deployment, and release operations

| # | Issue / acceptance condition | Status |
|---:|---|---|
| 92 | Training/Rapid selector sees the complete installed eligible corpus, not a demo subset | verified locally: 22,497 installed / 21,855 eligible |
| 93 | Release audit proves at least 5,000 unique selectable ECGs from the release index | verified locally (21,855); deployed-index confirmation remains a deployment gate |
| 94 | No learner-serving Training, Rapid, or Clinical item uses a synthetic ECG | verified locally |
| 95 | MIMIC private GCS is not assumed complete in Drive and is not served without validated joins | verified boundary |
| 96 | Public rhythm-source imports preserve checksum, license, and target-only label limitations | verified adapter; serving open |
| 97 | Sparse rhythm/critical-care concepts fail closed instead of padding or relabeling PTB | verified |
| 98 | Deployment architecture and cost decision preserves durable full function at the lowest justified current cost | verified decision: retain one `e2-small` with hydrated local corpus/SQLite plus GCS artifacts/backups for the low-volume release; live billing approval remains external |
| 99 | Managed database, backups, monitoring, alerting, and privacy operations are configured | external deployment gate |
| 100 | Full backend, typecheck, lint, build, dependency audit, and browser suites pass together | implemented / current combined run pending; the older green snapshot below is superseded |

## Post-ledger hardening and verification

| # | Issue / acceptance condition | Status |
|---:|---|---|
| 101 | Recent answer-bearing Guided packet deliveries and legacy generic attempts enter the same finite owner exposure boundary used by independent Training, Rapid, Clinical, review, and adaptive selection | verified |
| 102 | Request-validation failures never echo submitted passwords or other raw invalid input, and validation responses are non-cacheable | verified |
| 103 | Password change, replacement-session issuance, revocation of every old session, and outstanding export-grant revocation commit atomically | verified |
| 104 | Public readiness checks use a short concurrency-safe cache so probes cannot amplify repeated database/corpus work while still failing closed | verified |
| 105 | Immutable concept-availability counts are prewarmed and cached instead of repeatedly scanning the 879 MiB corpus index | verified |
| 106 | The objective registry has no `unmapped` learner-facing domains, including pre-excited atrial fibrillation and resuscitation source-boundary concepts | verified |
| 107 | Rapid debrief and cross-concept follow-on guidance are server-authoritative, receipt-grounded, answer-safe, and unable to create mastery | verified |
| 108 | The production same-origin proxy preserves the validated public Host/Origin contract instead of forwarding an internal deployment host | verified locally; deployed-host smoke test remains a deployment gate |
| 109 | Guided packet-exposure event identity is owner-scoped, answer-free, refresh-idempotent within one generation, and collision-safe across learners | verified |
| 110 | Clinical session capacity excludes the owner's live/recently shown ECGs and reports an honest distinct eligible length while retaining no-repeat serving | verified |
| 111 | Mobile ECG-first scene entry, dialogs, and recovery actions move focus to a visible target instead of leaving keyboard focus off-screen | verified |
| 112 | Production readiness requires an explicit authenticated-retention-policy acknowledgement and configured policy version; no policy was invented in code | verified fail-closed mechanism; policy selection/approval external gate |
| 113 | Learning preferences are intentionally saved, owner-scoped, cached/coalesced, and applied consistently to plan length, pace, Guided support, and mode setup | verified |
| 114 | Cross-mode resume and activity APIs reconstruct pending/feedback work, group multi-skill evidence honestly, and do not mutate progress during reads | verified |
| 115 | Completed Rapid rounds restore the complete owner-authorized server result ledger, including 500- and 5,000-item rounds, instead of treating the bounded browser recovery tail as complete | verified |
| 116 | Training concept/subskill inputs fail validation before any corpus scan, and its 21k-record pool cache is bounded without reducing 5,000-ECG support | verified |
| 117 | Corpus construction cannot publish a false complete manifest after missing inputs, bounded scans, skipped records, disabled required enrichment, source-count mismatch, or interrupted/degraded work | verified |
| 118 | Release verification checks every native command result, requires the exhaustive corpus audit, and refuses release mode without the configured live-LLM credential | verified locally; live paid-provider smoke and deployment remain external gates |
| 119 | The obsolete Review session API is owner-only and read-only; new starts and mutation attempts fail closed with the canonical adaptive-plan replacement instead of claiming legacy mastery | verified |
| 120 | Clinical lane and pacing-tier inputs accept only the supported server contracts and reject oversized focus/subskill values before selection | verified |
| 121 | The operational smoke uses a real cookie-bound, blinded Rapid round, activation, trace evidence, atomic answer/receipt commit, post-commit tutor, activity/profile projection, adaptive plan, and clean abandonment instead of a generic assessment bypass | verified locally against the complete corpus; deployed-host smoke remains a deployment gate |
| 122 | Training, Rapid, Clinical, and Guided saved-work/case discovery failures are announced and recover in place; Rapid no longer hides setup errors or duplicates runner errors, and mobile retry actions retain the 44 px target contract | verified |
| 123 | Unknown `/practice/next` concepts and subskills fail validation before adaptive selection or any unscoped corpus candidate load | verified |
| 124 | Generic Tutorial submissions remain auditable attempts but cannot mutate or advertise the legacy objective-mastery table | verified |
| 125 | Malformed or whitespace-only Bearer credentials return an ordinary authentication failure instead of a server error | verified |
| 126 | Diagnosis-bearing Clinical authoring ids never cross the learner boundary; keyed opaque `ci_…` handles survive refresh/replay and raw-id probes fail without echoing the internal id | verified |
| 127 | Historical persona reports are labeled as dated defect-discovery snapshots and point to this reconciled ledger instead of masquerading as current release status | verified |
| 128 | The executable verification gate includes ESLint and pinned production-Python dependency auditing in addition to typecheck, build, frontend audit, corpus audit, smoke, browser journeys, and the separately announced live-LLM check | verified locally |
| 129 | Training, Rapid, and Clinical use owner/mode/session-scoped opaque ECG capabilities so public-dataset record ids cannot be used for out-of-band label lookup | verified locally; the product remains formative learning/practice, not a summative certification exam |
| 130 | Assessment waveforms, feedback, tutor/provider context, activity, profile history, and progress export remove source coordinates and replace corpus identities with owner-scoped non-dataset references | verified |
| 131 | Training precise-entry evidence survives asynchronous waveform arrival, zoom, and pan instead of being reset to generic defaults before commit | verified |
| 132 | Clinical ECG readiness activates only a pending timed phase; untimed, resumed, and context-revealed phases do not issue duplicate transitions or learner-visible conflicts | verified |
| 133 | Signed-out `/` uses a dedicated public shell and product landing page; authenticated learners retain the student workspace and dashboard without duplicating either experience | verified locally |
| 134 | Public landing and authentication screens explain the learning experience in student language, keep implementation details out of the primary UI, and remain usable at 320 px and desktop widths | verified locally |
| 135 | Registration can be opened directly from `/login?mode=register`, while sign-in, guest exploration, guest-progress transfer, validation, and privacy behaviors remain intact | verified locally |
| 136 | The public document title and description identify TRACE as an ECG-learning platform rather than labeling the whole site as the private `Today` dashboard | verified locally |
| 137 | Adaptive-coach responses are read-only after generation: objective updates and viewer actions are stripped, and unverified or external destinations are replaced with a deterministic explanation of the server-owned plan | verified |
| 138 | Exact, event-level misconception episodes are normalized across Guided, Focused, Rapid, and Clinical work and exposed through an answer-safe learner-insights API for the unified dashboard and coach | open |

## Historical local gate snapshot — superseded

Before the reopened persona/adversarial audit, an earlier local candidate was
checked against the complete installed real-data corpus. These numbers are kept
for provenance only and must not be cited as evidence for the current worktree:

- Corpus audit: **22,497** installed unique ECG records; **21,855** eligible for Training/Rapid (21,157 PTB-XL and 698 Leipzig); **103** distinct real PTB-XL ECGs in Clinical.
- Backend: **520 passed**.
- Browser: **183/183 passed** against a fresh local full-corpus stack after the final UI race fixes.
- TypeScript typecheck: passed.
- ESLint: passed.
- Next.js production build: passed.
- Frontend production dependency audit: `npm audit --omit=dev` reported **0 vulnerabilities**.
- Production Python dependency audit: no known vulnerabilities in the fully pinned production requirements (`pip-audit --disable-pip --no-deps`; disabling resolution avoids trying to build the Linux-only `uvloop` dependency on Windows).
- Real-corpus operational smoke: passed through blinded Rapid serving, scoped waveform evidence, atomic grading/receipts, post-commit tutor, profile/activity projection, adaptive planning, and clean abandonment.
- Manual in-app review: Today, Guided hub/workspace, Focused Practice, Rapid, Clinical, My Learning, Account, and mobile sign-in rendered without console errors or horizontal overflow; the local stack used the production frontend build, complete corpus, and free mock tutor.

## Current release rule

The current worktree is an active release candidate repair, not a completed
product and not a deployment candidate. It becomes locally green only after the
fresh combined regression in the reopened audit passes. Production remains the
prior demo until a deliberately scoped release is reviewed and the applicable
external gates are recorded: named clinical review, institutional
identity/recovery and verified-email policy, authenticated retention-policy
approval, live GCP/Vercel/OpenAI cost and inventory confirmation, production
backup/monitoring/alert ownership, deployed Host/Origin and corpus smoke tests,
representative assistive-technology/student validation, a paid live-model
smoke, and an explicit release/deployment decision. Unsupported ACLS, authentic
serial comparison, and medication/electrolyte causality remain locked rather
than simulated.
