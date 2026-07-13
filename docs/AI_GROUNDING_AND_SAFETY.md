# AI Grounding and Safety

## Source of Truth Boundary

The LLM may tutor, explain, quiz, summarize, and recommend viewer actions. It may not invent or override:

- diagnoses
- measurements
- intervals
- fiducials
- lead-level findings
- ROIs
- curation tier

## Providers

`MockProvider` supports local development and deterministic tutor-contract tests without API keys. It is not evidence that a remote LLM provider is reachable.

`OpenAICompatibleProvider` uses:

- `LLM_PROVIDER=openai-compatible`
- `LLM_API_KEY`
- `LLM_MODEL`
- `LLM_BASE_URL`

Keys remain server-side.

Verification split:

- Backend tests validate schema handling, viewer-action safety, missing-key behavior, and an OpenAI-compatible request/response path against a local stub server.
- `scripts/llm_smoke.ps1` performs a live OpenAI-compatible provider check. It fails immediately if `LLM_API_KEY` is not set.

## Conversation

The tutor is multi-turn with persistent threads (`/tutor/message`, `/tutor/thread/{id}`). In tutorial mode it asks one Socratic question per turn and allows tangents (`onLessonTopic=false` lets the UI offer "return to lesson"). When a learner asks about a finding **not** in the case packet, the tutor refuses plainly and sets an `uncertaintyWarning` — even when the case has other supported concepts.

## Schema Validation

Tutor responses must match:

```json
{
  "tutorMessage": "...",
  "feedback": "...",
  "viewerActions": [],
  "objectiveUpdates": [],
  "misconceptions": [],
  "uncertaintyWarnings": [],
  "suggestedNextStep": "...",
  "socraticQuestion": "...",
  "citedEvidence": [],
  "onLessonTopic": true
}
```

If parsing or validation fails, the backend returns a grounded fallback response and includes the schema error instead of crashing.

## Claim check

Beyond schema validation, a post-generation guard flags any tutor prose that cites a measurement absent from the packet (e.g. mentioning "QTc" when no QTc is present), appending an `uncertaintyWarning` and a `claimCheck` field. The deterministic mock never trips it; this protects the real-LLM path.

## Viewer Actions

Supported validated actions:

- `zoom`
- `highlightLead`
- `highlightROI`
- `circleROI`
- `drawCaliper`
- `showFiducial`
- `resetView`

Actions referencing unavailable leads or invalid time windows are discarded safely.
