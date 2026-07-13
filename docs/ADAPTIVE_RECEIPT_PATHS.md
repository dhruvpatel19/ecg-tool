# Adaptive independent-receipt paths

The adaptive scheduler may prescribe a concept × subskill only when the linked
mode has a deterministic server grader capable of writing that exact receipt.
Conversational AI may explain the queue or debrief a committed response; it
does not select the answer key, grade a task, or change mastery.

| Subskill | Mastery destination | Independent evidence contract |
| --- | --- | --- |
| recognize | Rapid | Explicit selection of a source-supported finding on a blinded real ECG; a focused miss is also recorded as a lapse. |
| localize | Training | Server-verified waveform coordinate on an unannounced transfer ECG. |
| measure | Training | Server-verified caliper value and allowed lead on an unannounced transfer ECG. |
| discriminate | Training | Single-choice target-versus-mimic task regenerated from the durable slot and audited packet label. `caseFocus` and `targetPresent` are never returned before commitment. |
| explain mechanism | Training | Single-choice reviewed causal chain for the exact corpus concept. The key describes electrical mechanism only and cannot infer symptoms, acuity, etiology, or treatment. |
| synthesize | Rapid | Ward/untimed full read with all eight sweep fields, an explicit supported finding, a 12+ character evidence-limited synthesis, no unsupported explicit selection, and a packet-grounded score of at least 75%. |
| calibrate confidence | Training | Confidence committed before feedback and scored against classification correctness with a bounded Brier-style observation. Recognition correctness remains separate; durable calibration requires repeated cases. |
| apply in context | Not currently in the independent queue | Clinical receipts remain formative until named clinician sign-off. The planner fails closed instead of linking to Clinical as if it could award independent mastery. |

Training recognition remains formative because naming a known campaign target is
not a blinded recognition transfer. Rapid owns independent recognition. Free
text alone cannot create discrimination, mechanism, or synthesis evidence.

Each planner stage returns `receiptConcept`, `receiptSubskill`, and
`evidenceKind=independent_transfer`. URLs carry both the underlying real-ECG
family and the exact educational receipt target. Proxy Training objectives stay
formative; authored synthesis objectives may use an explicitly mapped real-ECG
family because the structured sweep is graded at the objective level.

Regression coverage lives in:

- `backend/tests/test_mastery_planner.py`
- `backend/tests/test_training_campaigns.py`
- `backend/tests/test_rapid_rounds.py`
- `frontend/e2e/adaptive.spec.ts`
