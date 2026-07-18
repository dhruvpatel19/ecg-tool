# TRACE learning dashboard redesign

Status: implemented in the current feature branch. Local backend, frontend,
production-build, and focused browser gates pass; production review/merge and
user validation are still pending.

This document records the dashboard architecture that now exists, the evidence
and mutation boundaries it must preserve, and the intentionally deferred work.
It replaces the earlier assumption that dashboard, activity, competencies,
study planning, preferences, and coaching should remain separate learner
destinations.

## Product outcome

A student should have one answer to each question:

- What should I do now?
- Why was it chosen for me?
- What am I improving?
- What keeps going wrong?
- Where can I see every ECG skill?
- How do I continue unfinished work?

The dashboard is a learning workspace, not an administrative analytics page.
One primary action, a small number of honest progress signals, and an ECG-specific
coach dominate the Overview. Full records use progressive disclosure in the
other dashboard panels.

## Implemented canonical information architecture

`/home` is the canonical private learning dashboard and the default destination
after authentication. Signed-out `/` remains the public product landing page.
Authenticated navigation exposes one `Dashboard` destination rather than the
old competing `Today` and `My learning` destinations.

The dashboard has five URL-addressable panels:

1. **Overview** — `/home`
2. **Activity** — `/home?panel=activity`
3. **Competencies** — `/home?panel=competencies`
4. **Study plan** — `/home?panel=plan`
5. **Calendar** — `/home?panel=calendar`, with an optional validated
   `date=YYYY-MM-DD` deep link

Learning preferences are not a dashboard panel. They are implemented in Account
at `/account#learning-preferences`, alongside other user-controlled account
settings.

Implemented compatibility redirects preserve existing bookmarks and return
paths:

- `/dashboard` -> `/home`
- `/profile` and `/profile?tab=overview` -> `/home`
- `/profile?tab=activity` -> `/home?panel=activity`
- `/profile?tab=competencies` -> `/home?panel=competencies`
- `/profile?tab=plan` -> `/home?panel=plan`
- `/profile?tab=preferences` -> `/account#learning-preferences`
- `/review` -> `/home?panel=plan`

## Implemented panel responsibilities

### Overview

The Overview is intentionally concise:

1. **Continue or Next best step.** Resumable work takes precedence. Otherwise,
   the deterministic adaptive plan supplies one runnable recommendation and its
   reason. When no independent evidence exists, the starting check is explicitly
   labeled as not yet personalized even if the planner can emit a runnable route.
   A general practice fallback is also labeled as not personalized.
2. **Honest progress strip.** `Skills checked`, `Holding over time`, and
   `Review due` summarize independent evidence. A failed competency request
   renders unavailable values, never inferred zeroes.
3. **Recent sessions.** The two most recent completed Focused, Rapid, or
   Clinical sessions show mode, timing, completion, aggregate performance, and
   saved-review count. Each opens owner-bound, answer-safe outcome evidence and
   can then open a separate completed-attempt replay when reconstruction is
   available.
4. **Skills to strengthen.** At most three evidence-backed, runnable concept x
   subskill targets link directly to supported practice.
5. **Personal learning coach.** Luna can explain the current verified plan and
   help the learner reflect. Suggested questions prefill the composer without
   sending on the learner's behalf. Overview and Study plan open the same
   focus-trapped coach surface. Chat cannot update progress. History is scoped to
   a stable fingerprint of the evidence-backed plan, and an expired capability
   refreshes without automatically resending the learner's saved draft.
6. **Next seven days.** A bounded retention projection shows counts of
   independently checked skills whose `nextDueAt` falls on each of the next
   seven local calendar days. Every date opens that day in the in-app Calendar;
   due work remains a live evidence projection rather than being copied into an
   appointment.
7. **Learning modes.** Guided, Focused, Rapid, and Clinical launchers remain
   available behind a compact disclosure instead of competing with the primary
   recommendation.

### Activity

Activity is a completed-work review. Completed session cards open a safe
per-item outcome review, and a `Sessions with saved items` control narrows those sessions to the
learner's durable, server-filtered, paginated review queue, including flags from
older sessions outside the recent Overview window. The granular event log supports mode,
competency, outcome, and recommendation filtering over the currently loaded
page; pagination; and expandable
summaries of score, confidence, assistance, evidence level, and recorded
competencies.

The session summary exposes only item order, committed outcome, normalized
competencies, confidence, and hints used. Item competency mappings identify
whether they came from a committed event or only the session focus. Learners can
save or remove an item from their review queue. The public API remains ordinal,
while the durable flag uses a private stable answer-row identity with a preserved
legacy-ordinal fallback. It does not expose or copy the original question, ECG,
answer, answer key, corpus identifier, or internal session identifier.

An explicit `Review question & ECG` action opens a separate, lazy replay read
model for a completed attempt. Focused, Rapid, and Clinical replays reconstruct
the submitted task, the learner's response, committed feedback, and a bounded
waveform from current audited content. They are labeled `reconstructed`, not
presented as immutable snapshots of the historical screen. Replay references
are owner- and attempt-bound, pending assessment material fails closed, and the
ordinary session summary remains answer-free.

The event log deliberately does not imply that legacy data changed current
competency estimates. `Review recommended` means that fresh practice is
appropriate; it is distinct from a learner-created saved flag.

### Competencies

Competencies is the complete, filterable evidence map. It exposes current states,
independent checks, review timing, confidence rechecks, and verified practice
routes. It distinguishes missing evidence from poor performance and keeps
unrunnable cells out of action lists. Each evidence disclosure can lazily open a
bounded chronological timeline of committed scored observations for that exact
objective x subskill. The timeline distinguishes independent from formative
evidence and explicitly does not claim to be a historical mastery estimate.

### Study plan

Study plan presents the same deterministic recommendation used by Overview,
along with its rationale, verified destination, evidence basis, and ordered next
stages. It is not a second scheduler and must not independently re-rank work.
Its coach can explain the plan but cannot rewrite mastery or silently change the
plan.

### Calendar

Calendar is a learner-controlled, in-app study planner. It provides a desktop
month view, a compact mobile seven-day view, and a daily agenda. Learners can
create, edit, reschedule, complete, reopen, and delete bounded study blocks;
choose their time zone and week start; and add a plan tied to an exact runnable
competency. Optimistic revisions prevent one stale browser tab from silently
overwriting a newer edit.

Retention reviews shown in Calendar are live projections from competency
evidence. Completing a calendar block records only that the plan was completed:
it never updates score, mastery, confidence, or retention evidence. Calendar
data is account-owned, included in progress export, transferred by the existing
guest-claim boundary, and deleted with the learner account. There is no external
calendar synchronization, reminder delivery, or coach-controlled mutation.

## Current read contracts

The dashboard composes existing owner-bound read models rather than creating a
second learner record:

- `learningResume()` supplies unfinished work across supported learning modes.
- `adaptivePlan()` supplies the deterministic recommendation, reasons, verified
  destinations, ordered stages, and bounded coach context.
- `competencies()` supplies the objective and subskill evidence map, retention
  state, and safe practice receipts.
- `learningActivity()` supplies the paginated, normalized event log inside
  Activity. The panel mounts only after the learner opens it.
- `GET /learning/sessions` supplies paginated completed-session aggregates,
  server-side `savedOnly` filtering, an owner-wide saved-item count, and opaque
  evidence references; `GET /learning/sessions/{sessionRef}` supplies the
  answer-safe per-item outcome evidence.
- Owner-authenticated PUT/DELETE flag endpoints persist submitted-item review
  flags. Summaries expose only `flaggedCount`; review items expose only the
  flag's boolean state.
- `GET /learning/sessions/{sessionRef}/attempts/{attemptIndex}/replay` supplies
  the strict completed-attempt replay projection; its sibling `/waveform/{ecgRef}`
  endpoint supplies only a bounded waveform window for the opened attempt.
- `GET /learners/{learnerId}/competencies/{objectiveId}/{subskill}/trend`
  supplies up to 50 answer-free observations for one owned competency.
- `/learning/calendar` supplies the date-range snapshot and live due-review
  projections. Settings, item CRUD, completion/reopen, and exact-competency
  scheduling use the owner-bound calendar mutation endpoints.
- The authenticated user projection supplies the learner-facing name; Overview
  does not issue a separate profile read.

Recommendation and fallback presentation is centralized in the learning-home
helper. It must not be reimplemented independently by Overview and Study plan.

## Learner memory model

Personalization is a layered model, not one opaque AI memory blob. The layers
have different authority and mutation rules.

### 1. Explicit preferences — implemented

The learner directly controls training stage, primary goal, default session
length, Rapid pace, guidance level, reduced motion, and large controls. These
preferences are account-bound, editable in Account, and may shape defaults or
tie-breaking. They cannot create earned evidence or mastery.

### 2. Observed learning evidence — implemented

Committed activity, session-review flags, competency observations, evidence
level, score, confidence when recorded, assistance, retention timing, and
resumable work come from owner-bound learning records and safe read models.
Independent and formative evidence remain distinct. A missing request, absent
datum, or old unverified record is never converted into a weakness.

Saved-review flags are explicit learner memory. They are persistently stored
only for authenticated owners, included in progress export through a private-ID-
free session alias, and removed with account deletion. They do not alter scores,
mastery, retention timing, or recommendation evidence.

The current data is not yet a complete event-level misconception memory. Exact
cross-mode error codes and recurring-pattern analysis remain deferred as
described below. Completed-attempt replay is a separate review capability and
does not turn reconstructed answer content into recommendation evidence.

### 3. Plan state — implemented as a derived projection

The deterministic scheduler derives the current recommendation and ordered
stages from supported evidence and verified destinations. Resumable work has
explicit precedence. Competency `nextDueAt` values drive the bounded seven-day
retention view.

This derived state remains separate from the learner-authored Calendar. The
dashboard does not persist seven day-cells as appointments, penalize a missed
day, or claim that the coach rescheduled external commitments. Calendar plans
may target a verified competency, but they never replace or re-rank the
deterministic recommendation.

### 4. Coach threads and context — implemented with a bounded scope

Tutor threads and messages are persisted per owner. The adaptive plan supplies
bounded coach context for the current recommendation. Dashboard history is
partitioned by a stable fingerprint of the plan inputs and destinations: a
refreshed short-lived capability can continue the same plan conversation, while
materially changed evidence starts a new scope. Conversation history provides
continuity inside that scope, but it is not authoritative evidence and cannot
mint mastery.

There is currently no UI for AI-inferred, cross-thread learner traits. No hidden
inference from chat should be promoted into an explicit preference or durable
plan setting without a visible proposal and learner confirmation.

## Honest evidence semantics

- `Skills checked`: distinct objective x subskill cells with independent evidence.
- `Holding over time`: independently assessed skills whose retention state
  is durable and not currently due.
- `Review due`: independently assessed skills currently due or overdue.
- `Domains explored`: optional secondary detail; never substitute breadth with
  a high average from a few easy objectives.
- Guided completion is learning progress, not independent mastery.
- Formative coaching and assisted attempts can shape recommendations but cannot
  mint mastery.
- A correct result does not prove durable mastery without the required evidence
  breadth and retention state.
- Unavailable or unrunnable objective cells stay out of `Skills to strengthen`.
- Partial API failure preserves loaded sections and displays unavailable state;
  it never fabricates a zero, a due date, or a weak competency.

## Bounded seven-day plan

The implemented `Your next seven days` strip is deliberately small and honest:

- It always covers today plus six days.
- It counts only already checked skills with a recorded due time. Overdue work
  rolls into Today rather than disappearing from all seven buckets.
- It derives from competency evidence at render time; it is not a separate
  calendar database.
- An open day means that no recorded review is due, not that the learner has no
  useful study options.
- Missing days do not create penalties; overdue review remains visible in Today
  without pretending the learner missed a calendar appointment.
- Selecting a date opens that date in Calendar. The deterministic adaptive plan
  remains a separate view and remains the authority for ranking what comes next.

## Adaptive coach responsibilities and mutation boundary

The deterministic scheduler owns ranking and destinations. The coach may:

- explain why the current activity was selected;
- answer questions using bounded objective and committed-evidence context;
- compare concepts and prompt reflection;
- explain a verified recurring pattern when one is available;
- prepare the learner for the next scheduled task.

The coach may not:

- score work or update mastery;
- alter the verified plan, preferences, due dates, or calendar state;
- perform any mutation merely because it appeared in model output;
- invent a case, competency result, memory, or destination;
- reveal an active answer;
- treat absence of data as poor performance;
- provide patient-specific clinical direction.

The current coach is read-only. A future feature that lets it propose a plan or
preference change must show the exact change, require explicit learner
confirmation, validate it through an authoritative server contract, and retain
an audit trail. Chat text alone is never confirmation.

Post-generation enforcement strips objective updates and viewer actions and
replaces unverified steering with the deterministic plan explanation. This guard
remains a production safety requirement.

## Intentionally deferred

The following are not represented as implemented capabilities:

- **External calendar and automatic planning.** The in-app Calendar does not
  synchronize with Google/Outlook, send reminders, infer free time, automatically
  reschedule missed work, or let the coach mutate plans. Those integrations need
  separate consent, delivery, and conflict-resolution designs.
- **Inferred editable memory.** There is no learner-facing store of traits or
  preferences inferred from chat and no UI to inspect, accept, edit, expire, or
  delete those inferences. Explicit Account preferences remain the authority.
- **Immutable historical assessment snapshots.** Completed-attempt replay is
  reconstructed from committed answers and current audited content. Exact
  pixel-identical historical screens would require a versioned, immutable review
  snapshot captured at submission time and a separate storage/migration review.
- **Exact misconception timeline.** Stable error codes and event-level recurring
  pattern analysis are not yet available across every mode.
- **Server-wide Activity search.** Search and outcome filters apply to loaded
  recent items. Older records require pagination; the empty state says so rather
  than claiming the full history has no match.
- **Peer percentiles, pass prediction, and ornamental streaks.** These require
  valid calibration or a demonstrated learning benefit and are not part of this
  dashboard pass.

## Deferred exact misconception insights

Do not add another mastery store. If exact recurring-error insight is added,
extend the normalized answer-free learner event ledger.

The event contract needs safe fields or normalized children for:

- `confidence`
- `assistance`
- explicit outcome: `correct`, `incorrect`, `partial`, or `unverified`

Add `learner_event_errors` only when stable cross-mode mappings exist:

- `event_id`
- `competency_id`
- stable `error_code`
- optional student-facing label version

Every Guided, Focused, Rapid, and Clinical commit should write its event and
error rows atomically. Historical rows may be backfilled only when the mapping is
unambiguous.

A future versioned `GET /learning/insights` read model may expose:

- recurring patterns: code, student label, count, last seen, affected skills,
  and high-confidence count;
- recent misses: mode, time, objective, subskill, confidence, safe error labels,
  and a verified fresh-practice destination.

It must never expose answer keys, pending items, raw corpus ids, source
coordinates, or uncommitted clinical context.

## Copy contract

Avoid normal student-facing uses of:

- `Independent estimate`
- `Objective checks recorded`
- `server-synced`, `server rubric`, or `active corpus`
- `Planner returned no runnable stage`
- operational provider or budget labels unless an outage affects the learner

Prefer:

- `Skills checked`
- `Checks completed`
- `Learn with guidance, then check it on a new ECG`
- `Ready to practise`
- `Guided practice available`
- `Your next recommendation is temporarily unavailable`

Legacy records may be described as unverified evidence in Activity when that
distinction is necessary, but operational storage language does not belong in
the primary dashboard.

## Persona acceptance matrix

- **New preclinical learner:** gets an honest starting check, never a fabricated weak
  skill.
- **Overconfident learner:** a high-confidence miss triggers a precise repair and
  later recheck.
- **Returning learner:** overdue retrieval outranks new content.
- **Unfinished-session learner:** Continue is primary; Next up is secondary.
- **Medication-safety learner:** preferences shape tie-breaking and defaults, not
  earned mastery.
- **Strong learner:** durable skills stay out of Needs attention until a real
  spaced review becomes due; cross-concept integration unlocks correctly.
- **Mobile/keyboard learner:** tabs, primary action, coach, skills, and activity
  remain usable at 320 px, 200% zoom, and keyboard-only navigation.
- **Partial API failure:** loaded sections remain usable; a missing request never
  becomes a zero score.
- **Tampered or stale coach context:** fails closed, refreshes safely, and
  preserves committed progress.

## July 2026 audit hardening

The post-implementation UI and feature audit made the following bounded changes:

- removed false cold-start personalization and heuristic mastery percentages;
- standardized Overview counts on objective x subskill units and aligned overdue
  priority ordering with the scheduler;
- made Activity and saved-session reads lazy and guarded Activity pagination from
  stale mode responses;
- replaced the expanded Activity policy legend and competency evidence rails with
  disclosures, increased small type and interaction targets, and fixed 320 px
  retention-strip overflow;
- changed the desktop Overview to two balanced work cards plus one horizontal
  coach band, added restrained drawer motion, and preserved reduced-motion behavior;
- rejected corrupt out-of-range persisted scores instead of clamping them into a
  believable result;
- stabilized saved-review identity, labeled session-focus fallback honestly,
  excluded zero-attempt technical sessions from performance lists, and added an
  independent competency-route retry in session review;
- blocked coach sends during history restoration and refreshed expired plan
  context while preserving—but never auto-sending—the learner's draft.
- added completed-only, owner-bound reconstructed replay with attempt-scoped ECG
  capabilities while preserving the answer-free session summary;
- added lazy, answer-free competency observation timelines instead of fabricating
  historical mastery curves;
- added a learner-owned in-app Calendar with optimistic edits, live retention
  projections, mobile agenda behavior, and an explicit no-evidence mutation boundary.

## July 2026 personalization integration pass

The student-journey and rendered UI audit tightened the path from recommendation
to action without letting chat or client state silently mutate the learning
record:

- the deterministic plan now exposes one signed, server-authored calendar action;
  Overview, Study plan, and the Luna drawer all hand it to the same explicit
  confirm-before-save editor;
- plan blocks and live retention reviews preserve exact objective, subskill,
  mode, case concept, and a strict Calendar return destination; manual blocks may
  optionally launch Guided, Focused, Rapid, or Clinical work through server-built
  routes;
- Calendar settings are authoritative across Calendar and the seven-day Overview
  projection. A browser time zone is only the unsaved fallback, and failed
  Calendar reads no longer render a false empty agenda;
- every due review remains available, while the first three are ordered using the
  verified plan and lower-priority work is progressively disclosed. Manually
  checking off a retention block now says that verified practice is still due;
- the first Rapid starting check is five untimed ECGs. Later sessions continue to
  honor saved length and pace preferences, and Training keeps its supported
  minimum;
- Activity rows lead with the practiced finding, deduplicate repeated competency
  mappings, and use `Recorded` / `Review suggested` instead of labels that could
  imply mastery. Competencies distinguish findings from skills, de-emphasize the
  untouched catalog, and expose mixed evidence and timelines honestly;
- Rapid and Clinical now detect when an unrelated active session would otherwise
  swallow a targeted recommendation. The saved work resumes unchanged with an
  explicit conflict notice; the recommended objective is never claimed to have
  been substituted into it;
- credential forms use POST as the pre-hydration fallback and keep submit controls
  disabled until client handlers are attached, preventing a fast click from
  placing passwords in a URL;
- clinical acronym rendering includes QT, navigation/main landmarks remain
  singular, and editor/delete confirmations restore keyboard focus.

Automatic `verified_practice` completion of a calendar item remains intentionally
unwired. Doing it safely requires a session-bound, owner-bound reference to the
specific calendar item carried through assessment creation and commit. Matching
an arbitrary completed ECG to a date/title after the fact would create false
calendar completion, so this belongs in the mode contract pass rather than a
heuristic dashboard write.

## Remaining validation and follow-up

1. Keep the full frontend and backend gates green before merge. Obsolete,
   unreferenced prototype duplicates that prevented TypeScript/build discovery
   were removed; they must not be reintroduced under alternate filenames.
2. Validate novice, clerkship, advanced, mobile, keyboard, partial-failure, and
   adversarial coach personas.
3. Inspect all compatibility redirects and return paths against the canonical
   `/home` panels.
4. Treat the exact misconception ledger, immutable replay snapshots, inferred
   memory UI, server-wide Activity search, and external calendar integrations as
   separate product changes with their own data-safety review. Bounded replay,
   observation timelines, the in-app planner, and the answer-safe flag queue are
   already implemented.
5. Add a large-history performance gate before long-lived learner records become
   common. Session-reference resolution currently verifies completed sessions in
   sequence, and saved-item totals reuse the completed-session projection; both
   are correct at current scale but should be indexed or materialized from measured
   evidence before they become a latency problem.
