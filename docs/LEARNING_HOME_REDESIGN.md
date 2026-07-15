# TRACE learning home redesign

Status: approved implementation direction; detailed user review pending.

This document defines the smallest coherent redesign that combines the current
dashboard, objectives, mastery, activity, study plan, and adaptive coach without
creating another competing learner surface. It deliberately separates what the
existing product can support now from the event-level misconception work still
needed.

## Product outcome

A student should have one answer to each question:

- What should I do now?
- Why was it chosen for me?
- What am I improving?
- What keeps going wrong?
- Where can I see every ECG skill?
- How do I continue unfinished work?

The page should feel like a learning workspace, not an administrative analytics
dashboard. One primary action, a small number of honest progress signals, and an
ECG-specific coach should dominate. Full records remain available through
progressive disclosure.

## Canonical information architecture

Use `/home` as the authenticated and guest learning home. Signed-out `/` remains
the public product landing page.

Compatibility routes:

- `/profile?tab=plan` -> `/home#next`
- `/profile?tab=competencies` -> `/home?panel=skills`
- `/profile?tab=activity` -> `/home?panel=activity`
- `/profile?tab=preferences` -> `/account?section=learning`
- `/review` -> `/home#next`

Navigation should expose one `Learning home` destination rather than separate
`Today` and `My learning` destinations. Preferences belong in Account. Activity
and the complete objective map remain inside Learning home as expandable views.

## Page hierarchy

1. **Continue** — shown only when a saved activity exists. This is the single
   primary action. The recommendation moves under `After you finish` so it does
   not compete.
2. **Next up** — one deterministic, evidence-backed recommendation with a concise
   reason, `Why this?`, and `Ask your coach`.
3. **Progress strip** — `Skills checked`, `Holding over time`, and `Review due`.
   Do not display a global percentage averaged only over attempted skills.
4. **Skills to strengthen** — at most three runnable concept x subskill targets,
   with the observed pattern and an exact supported next activity.
5. **Learning modes** — compact four-card launcher; explanatory marketing copy
   belongs on the public landing page, not here.
6. **Recent practice** — the five most recent committed activities with a safe
   review destination.
7. **All ECG skills** — lazy-loaded, collapsed by domain, and explicit about
   `Learned with guidance`, `Checked on a new ECG`, `Holding`, `Due`, and
   `Guided practice available`.

## Existing read contracts for phase 1

The first frontend merge does not require a new backend schema:

- `learningResume()` supplies unfinished work.
- `adaptivePlan()` supplies the verified queue, recommendation reasons,
  integration links, and owner-bound coach context.
- `competencies()` supplies the lazy objective map.
- `learningActivity("all", 5)` supplies the recent preview.
- `profile()` temporarily supplies aggregate evidence and legacy misconception
  counts.

Recommendation/fallback presentation must live in one shared function or one
future read model. It must not remain reimplemented independently by the root
dashboard, Profile, and Study Plan panel.

## Honest progress semantics

- `Skills checked`: distinct objectives with independent evidence.
- `Holding over time`: independently assessed objectives whose retention state
  is durable and not currently due.
- `Review due`: independently assessed objectives currently due or overdue.
- `Domains explored`: optional secondary detail; never substitute breadth with
  a high average from a few easy objectives.
- Guided completion is learning progress, not independent mastery.
- Formative coaching and assisted attempts can shape recommendations but cannot
  mint mastery.
- Unavailable or unrunnable objective cells stay out of `Skills to strengthen`.

## Exact misconception insights — phase 2

Do not add another mastery store. Extend the normalized answer-free learner
event ledger.

Add event-safe fields:

- `confidence`
- `assistance`
- explicit outcome: `correct`, `incorrect`, `partial`, or `unverified`

Add `learner_event_errors`:

- `event_id`
- `competency_id`
- stable `error_code`
- optional student-facing label version

Every Guided, Focused, Rapid, and Clinical commit should write the event and its
error rows atomically. Historical rows may be backfilled only when the mapping is
unambiguous.

Expose a versioned `GET /learning/insights` read model:

- recurring patterns: code, student label, count, last seen, affected skills,
  and high-confidence count;
- recent misses: mode, time, objective, subskill, confidence, safe error labels,
  and a verified review destination.

The response must never expose answer keys, pending items, raw corpus ids, source
coordinates, or uncommitted clinical context.

## Adaptive coach responsibilities

The deterministic scheduler owns ranking and destinations. The coach may:

- explain why the current activity was selected;
- answer questions using the bounded objective and committed evidence context;
- compare concepts and prompt reflection;
- explain a verified recurring error pattern;
- prepare the learner for the next scheduled task.

The coach may not:

- score or update mastery;
- alter the verified plan;
- invent a case or destination;
- reveal an active answer;
- treat absence of data as poor performance;
- provide patient-specific clinical direction.

Post-generation enforcement must strip objective updates and viewer actions and
replace unverified steering with the deterministic plan explanation. This guard
is implemented and covered by adversarial tests.

## Copy to remove

Remove normal student-facing uses of:

- `Independent estimate`
- `Objective checks recorded`
- `server-synced`, `server rubric`, or `active corpus`
- `Planner returned no runnable stage`
- `Legacy record · not used for mastery`
- operational provider/budget labels unless an outage affects the learner

Prefer:

- `Skills checked`
- `Checks completed`
- `Learn with guidance, then check it on a new ECG`
- `Ready to practise`
- `Guided practice available`
- `Your next recommendation is temporarily unavailable`

## Persona acceptance matrix

- **New preclinical learner:** gets an honest baseline, never a fabricated weak
  skill.
- **Overconfident learner:** a high-confidence miss triggers a precise repair and
  later recheck.
- **Returning learner:** overdue retrieval outranks new content.
- **Unfinished-session learner:** Continue is primary; Next up is secondary.
- **Medication-safety learner:** preferences shape tie-breaking and defaults, not
  earned mastery.
- **Strong learner:** durable skills never appear under Needs attention;
  cross-concept integration unlocks correctly.
- **Mobile/keyboard learner:** primary action, coach, skills, and activity remain
  usable at 320 px, 200% zoom, and keyboard-only navigation.
- **Partial API failure:** loaded sections remain usable; a missing request never
  becomes a zero score.
- **Tampered/stale coach context:** fails closed, refreshes safely, and preserves
  committed progress.

## Implementation order

1. Create shared recommendation and compact progress presentation functions.
2. Build `/home` from the existing read contracts.
3. Replace duplicate navigation and add compatibility redirects/return paths.
4. Remove the old Profile/Study Plan duplicate surfaces after browser-contract
   parity.
5. Add the normalized error ledger and `/learning/insights`.
6. Feed only bounded verified insights into the read-only adaptive coach.
7. Run novice, clerkship, advanced, mobile, keyboard, failure, and adversarial
   personas before deployment review.
