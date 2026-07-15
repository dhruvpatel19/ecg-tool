"""Server-owned lifecycle and evidence boundary for Rapid ECG rounds."""

from __future__ import annotations

import base64
from collections import OrderedDict
from datetime import UTC, datetime
import hashlib
import hmac
import json
from threading import RLock
from typing import Any, Callable, Literal
from urllib.parse import parse_qs, parse_qsl, urlencode

from fastapi import APIRouter, Cookie, Header, HTTPException, Query, Response
from pydantic import BaseModel, Field

from .adaptive import next_case
from .auth import SESSION_COOKIE_NAME
from .assessment_presentation import (
    assessment_display_id,
    public_assessment_record,
    public_case_packet,
    public_case_summary,
    public_waveform,
)
from .config import get_settings
from .data_sources import case_summary
from .ecg_capability import issue_ecg_capability, matches_ecg_capability
from .grading import grade_attempt, grade_click_answer
from .ontology import CONCEPT_BY_ID
from .objectives import REGISTRY_VERSION, objective_definition
from .assessment_contracts import (
    RAPID_SYNTHESIS_RECEIPT_UNAVAILABLE_REASON,
    RAPID_TESTED_OBJECTIVE_MANIFEST_VERSION,
    bound_rapid_grade_to_manifest,
    finalize_rapid_tested_objective_manifest,
    rapid_synthesis_contract_available,
    rapid_tested_objective_manifest,
)
from .assessment_ledger import AssessmentLedgerError
from .rapid_assessment import (
    RapidAssessmentStore,
    RapidExposureConflictError,
)
from .schemas import AttemptRequest, StructuredInterpretation
from .source_policy import (
    eligible_packet_objectives,
    packet_allows_learning_evidence,
    packet_mode_policy,
    retention_morphology_key,
)


LearnerResolver = Callable[[str | None, str, str | None], str]
PacketProvider = Callable[[dict[str, Any]], dict[str, Any]]
PacketTransformer = Callable[[dict[str, Any]], dict[str, Any]]

PACE_SECONDS: dict[str, int | None] = {"ward": 120, "emergency": 20, "untimed": None}
PACE_SCOPE = {"ward": "full_read", "emergency": "dominant_finding", "untimed": "full_read"}
ALLOWED_SUBSKILLS = {
    "recognize", "localize", "measure", "discriminate", "explain_mechanism",
    "synthesize", "apply_in_context", "calibrate_confidence",
}

_SYNTHESIS_FIELDS = (
    "rate", "rhythm", "axis", "intervals", "conduction", "st_t",
    "hypertrophy", "synthesis",
)


class RapidRoundStartBody(BaseModel):
    learnerId: str = "demo"
    pace: Literal["ward", "emergency", "untimed"] = "ward"
    length: int = Field(default=5, ge=1, le=5000)
    focusConcept: str | None = Field(default=None, max_length=160)
    secondaryConcept: str | None = Field(default=None, max_length=160)
    focusSubskill: str | None = Field(default=None, max_length=80)
    contextKey: str = Field(default="", max_length=1000)
    exclusions: list[str] = Field(default_factory=list, max_length=5000)


class RapidNextBody(BaseModel):
    activate: bool = False


class RapidSubmitBody(BaseModel):
    caseId: str = Field(min_length=1, max_length=160)
    structuredAnswer: StructuredInterpretation = Field(default_factory=StructuredInterpretation)
    freeTextAnswer: str = Field(default="", max_length=10_000)
    confidence: int = Field(default=3, ge=1, le=5)
    traceEvidence: dict[str, Any] | None = None


_INTEGRATION_ROSTER_VERSION = "rapid-integration-roster-v1"
_INTEGRATION_ROSTER_PARAM = "__integrationRoster"


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _roster_signature(secret: str, encoded: str) -> str:
    return _b64encode(
        hmac.new(
            secret.encode("utf-8"),
            f"rapid-integration-roster:{encoded}".encode("utf-8"),
            hashlib.sha256,
        ).digest()
    )


def _roster_case_digest(secret: str, case_id: str) -> str:
    # Case ids are never embedded in the resumable round. The server can locate
    # the frozen case by scanning the named concept family and matching this
    # secret-keyed digest; a learner cannot reverse it against enumerable ids.
    return hmac.new(
        secret.encode("utf-8"),
        f"rapid-integration-case:{case_id}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _encode_integration_roster(
    secret: str,
    *,
    learner_id: str,
    primary_concept: str,
    secondary_concept: str,
    primary_case_id: str,
    secondary_case_id: str,
) -> str:
    payload = {
        "v": _INTEGRATION_ROSTER_VERSION,
        "o": hmac.new(
            secret.encode("utf-8"),
            f"rapid-integration-owner:{learner_id}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()[:32],
        "p": primary_concept,
        "s": secondary_concept,
        "ph": _roster_case_digest(secret, primary_case_id),
        "sh": _roster_case_digest(secret, secondary_case_id),
    }
    encoded = _b64encode(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    return f"{encoded}.{_roster_signature(secret, encoded)}"


def _query_pairs(context_key: str) -> list[tuple[str, str]]:
    return parse_qsl(str(context_key or "").lstrip("?"), keep_blank_values=True)


def _requested_secondary_concept(context_key: str) -> str | None:
    values = [value.strip() for key, value in _query_pairs(context_key) if key == "secondaryConcept"]
    if not values:
        return None
    if len(values) != 1 or values[0] not in CONCEPT_BY_ID:
        raise ValueError("invalid_secondary_concept")
    return values[0]


def _with_integration_roster(context_key: str, token: str) -> str:
    pairs = [
        (key, value)
        for key, value in _query_pairs(context_key)
        if key != _INTEGRATION_ROSTER_PARAM
    ]
    pairs.append((_INTEGRATION_ROSTER_PARAM, token))
    query = urlencode(pairs)
    return f"?{query}" if str(context_key or "").startswith("?") else query


def _public_context_key(context_key: str) -> str:
    pairs = [
        (key, value)
        for key, value in _query_pairs(context_key)
        if key != _INTEGRATION_ROSTER_PARAM
    ]
    query = urlencode(pairs)
    if not query:
        return ""
    return f"?{query}" if str(context_key or "").startswith("?") else query


def _decode_integration_roster(
    context_key: str, *, secret: str, learner_id: str, focus_concept: str
) -> dict[str, str] | None:
    values = [value for key, value in _query_pairs(context_key) if key == _INTEGRATION_ROSTER_PARAM]
    if not values:
        return None
    try:
        if len(values) != 1:
            raise ValueError("invalid_integration_roster")
        encoded, supplied = values[0].split(".", 1)
        if not hmac.compare_digest(_roster_signature(secret, encoded), supplied):
            raise ValueError("invalid_integration_roster")
        payload = json.loads(_b64decode(encoded))
        expected_owner = hmac.new(
            secret.encode("utf-8"),
            f"rapid-integration-owner:{learner_id}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()[:32]
        secondary = _requested_secondary_concept(context_key)
        if (
            not isinstance(payload, dict)
            or payload.get("v") != _INTEGRATION_ROSTER_VERSION
            or payload.get("o") != expected_owner
            or payload.get("p") != focus_concept
            or payload.get("s") != secondary
            or secondary == focus_concept
            or not all(
                isinstance(payload.get(key), str)
                and len(payload[key]) == 64
                and all(character in "0123456789abcdef" for character in payload[key])
                for key in ("ph", "sh")
            )
        ):
            raise ValueError("invalid_integration_roster")
        return {
            "primaryConcept": str(payload["p"]),
            "secondaryConcept": str(payload["s"]),
            "primaryDigest": str(payload["ph"]),
            "secondaryDigest": str(payload["sh"]),
        }
    except ValueError:
        raise
    except (TypeError, KeyError, json.JSONDecodeError) as exc:
        raise ValueError("invalid_integration_roster") from exc


def _receipt_concept(session: dict[str, Any]) -> str:
    values = parse_qs(str(session.get("contextKey") or ""), keep_blank_values=False)
    requested = str((values.get("receiptConcept") or [""])[0]).strip()
    return requested or str(session.get("focusConcept") or "")


def _synthesis_contract(
    case: dict[str, Any], session: dict[str, Any]
) -> tuple[str, bool, str]:
    focus = str(session.get("focusConcept") or "")
    receipt_concept = _receipt_concept(session)
    if session.get("focusSubskill") != "synthesize" or not focus or not receipt_concept:
        return receipt_concept, False, "This round did not prescribe a synthesis receipt."
    if session.get("assessmentScope") != "full_read":
        return receipt_concept, False, "Synthesis receipts require a ward or untimed complete-read round."
    definition = objective_definition(receipt_concept)
    if not definition or "synthesize" not in definition.allowed_subskills:
        return receipt_concept, False, "The requested objective has no reviewed synthesis task contract."
    if not rapid_synthesis_contract_available(receipt_concept, focus):
        return receipt_concept, False, RAPID_SYNTHESIS_RECEIPT_UNAVAILABLE_REASON
    if definition.evidence_ceiling != "eligible_real_case":
        return receipt_concept, False, "This synthesis objective is formative-only under the current source contract."
    source = packet_allows_learning_evidence(case, "rapid", focus, "synthesize")
    if not source.allowed:
        return receipt_concept, False, source.reason
    return receipt_concept, True, ""


def _synthesis_task_complete(answer: StructuredInterpretation) -> bool:
    values = answer.model_dump()
    return all(str(values.get(field) or "").strip() for field in _SYNTHESIS_FIELDS) \
        and len(answer.synthesis.strip()) >= 12 \
        and bool(answer.selectedConcepts)


def _manifest_for_pending_case(
    case: dict[str, Any],
    session: dict[str, Any],
    *,
    focus_concept: str | None,
) -> dict[str, Any]:
    """Create the private assessment contract frozen with one pending ECG."""

    focus_subskill = str(session.get("focusSubskill") or "") if focus_concept else ""
    receipt_concept = _receipt_concept(session) if focus_concept else ""
    synthesis_allowed = False
    if focus_concept and focus_subskill == "synthesize":
        _, synthesis_allowed, _ = _synthesis_contract(case, session)
    assessment_scope = (
        "dominant_finding"
        if _target_only_source(case)
        else str(session.get("assessmentScope") or "full_read")
    )
    return rapid_tested_objective_manifest(
        case,
        assessment_scope=assessment_scope,
        focus_concept=focus_concept,
        focus_subskill=focus_subskill or None,
        receipt_concept=receipt_concept or None,
        synthesis_allowed=synthesis_allowed,
    )


def _deadline_elapsed(session: dict[str, Any], now: datetime | None = None) -> bool:
    deadline = session.get("pendingDeadlineAt")
    if not deadline:
        return False
    try:
        parsed = datetime.fromisoformat(str(deadline))
    except ValueError:
        # A malformed server deadline must never open the positive-evidence path.
        return True
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return (now or datetime.now(UTC)) >= parsed


def _rapid_packet_targets(case: dict[str, Any]) -> list[str]:
    return eligible_packet_objectives(case, "rapid", "recognize")


def _target_only_source(case: dict[str, Any] | None) -> bool:
    if not isinstance(case, dict):
        return False
    decision = packet_mode_policy(case, "rapid")
    eligibility = case.get("educational_eligibility") or {}
    return bool(
        decision.source_kind == "normalized"
        and isinstance(eligibility, dict)
        and eligibility.get("educationalUse") == "rhythm_stream"
    )


def _case_can_enter_rapid(
    case: dict[str, Any] | None,
    require_trace_proof: bool,
    *,
    allow_target_only: bool = False,
) -> bool:
    if not packet_mode_policy(case, "rapid").allowed or not isinstance(case, dict):
        return False
    # Expert rhythm streams do not provide exhaustive 12-lead morphology
    # labels. They may support an explicitly focused rhythm check, but never a
    # blind mixed/full-read slot where an unlabelled true finding could be
    # falsely penalized as an overcall.
    if _target_only_source(case) and not allow_target_only:
        return False
    if not _rapid_packet_targets(case):
        return False
    return bool(
        not require_trace_proof
        or packet_allows_learning_evidence(case, "rapid", "qrs_complex", "localize").allowed
    )


def _stable_round_order(
    candidates: list[dict[str, Any]], round_id: str
) -> list[dict[str, Any]]:
    """Return the restart-stable pseudorandom order for one Rapid round."""
    return sorted(
        candidates,
        key=lambda row: hashlib.sha256(
            f"{round_id}:{row['case_id']}".encode("utf-8")
        ).digest(),
    )


class _BroadRoundOrderCache:
    """Bounded, thread-safe cache for full-corpus Rapid permutations.

    Only the case id is retained from the repository's lightweight candidate
    rows. This keeps 16 concurrent/abandoned 21k-record round permutations
    modest in memory, and prevents an accidental mutation of repository rows
    from changing an active round. Eviction never affects correctness: the
    order is rebuilt from ``round_id`` and uniqueness remains owned by the
    durable served ledger.
    """

    def __init__(self, repo: Any, max_rounds: int = 16) -> None:
        self._repo = repo
        self._max_rounds = max(1, int(max_rounds))
        self._candidate_index: list[dict[str, Any]] | None = None
        self._orders: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
        self._rejections: dict[str, set[str]] = {}
        self._lock = RLock()

    def get(self, round_id: str) -> tuple[list[dict[str, Any]], set[str]]:
        with self._lock:
            cached = self._orders.get(round_id)
            if cached is not None:
                self._orders.move_to_end(round_id)
                return cached, self._rejections.setdefault(round_id, set())

            if self._candidate_index is None:
                # De-duplicate and freeze the minimum selector contract. Empty
                # or malformed ids fail closed instead of breaking every round.
                seen: set[str] = set()
                index: list[dict[str, Any]] = []
                for row in self._repo.candidates(None):
                    case_id = str(row.get("case_id") or "") if isinstance(row, dict) else ""
                    if not case_id or case_id in seen:
                        continue
                    seen.add(case_id)
                    index.append({"case_id": case_id})
                self._candidate_index = index

            ordered = _stable_round_order(self._candidate_index, round_id)
            self._orders[round_id] = ordered
            self._rejections[round_id] = set()
            while len(self._orders) > self._max_rounds:
                evicted_id, _ = self._orders.popitem(last=False)
                self._rejections.pop(evicted_id, None)
            return ordered, self._rejections[round_id]

    def release(self, round_id: str) -> None:
        with self._lock:
            self._orders.pop(round_id, None)
            self._rejections.pop(round_id, None)


def _broad_corpus_selection(
    repo,
    excluded: set[str],
    seed: str,
    *,
    require_trace_proof: bool = False,
    ordered_candidates: list[dict[str, Any]] | None = None,
    rejected_candidates: set[str] | None = None,
) -> dict[str, Any]:
    """Choose deterministically across the entire eligible corpus.

    Rapid is mixed interpretation practice, not a small pathology bank. A stable
    hash order gives every Tier A/B record a path into a long round while the
    durable served ledger guarantees no repeats.
    """
    rejected = rejected_candidates if rejected_candidates is not None else set()
    candidates = ordered_candidates
    if candidates is None:
        candidates = _stable_round_order(repo.candidates(None), seed)
    if not candidates:
        return {"case": None, "reason": "The eligible unique ECG pool is exhausted.", "targetObjectives": []}
    for selected in candidates:
        case_id = str(selected["case_id"])
        if case_id in excluded or case_id in rejected:
            continue
        case = repo.get_case(selected["case_id"])
        if not _case_can_enter_rapid(case, require_trace_proof, allow_target_only=False):
            # In a long server round, remember source-policy/trace rejections so
            # a bad candidate is parsed at most once. The durable served ledger
            # still owns learner-visible uniqueness.
            rejected.add(case_id)
            continue
        return {
            "case": case_summary(case),
            "reason": "Selected without replacement from the full audited Rapid ECG corpus.",
            "targetObjectives": _rapid_packet_targets(case)[:3],
        }
    return {
        "case": None,
        "reason": "No remaining ECG passes the audited Rapid source and evidence contract.",
        "targetObjectives": [],
    }


def _focused_corpus_selection(
    repo,
    store,
    session: dict[str, Any],
    excluded: set[str],
    *,
    require_trace_proof: bool,
) -> dict[str, Any]:
    focus = str(session.get("focusConcept") or "")
    subskill = str(session.get("focusSubskill") or "recognize")
    rejected = set(excluded)
    try:
        maximum = len(repo.candidates(None)) + 1
    except Exception:
        maximum = 10_000
    last_reason = "No focused Rapid case is available."
    for _ in range(maximum):
        selected = next_case(
            repo,
            store,
            learner_id=session["learnerId"],
            concept_id=focus,
            subskill_id=subskill,
            exclude_case_ids=rejected,
            selector_context="rapid",
        )
        summary = selected.get("case")
        if not summary:
            last_reason = selected.get("reason") or last_reason
            break
        case_id = str(summary.get("caseId") or "")
        case = repo.get_case(case_id) if case_id else None
        exact = packet_allows_learning_evidence(case, "rapid", focus, subskill)
        trace_ok = bool(
            not require_trace_proof
            or packet_allows_learning_evidence(case, "rapid", "qrs_complex", "localize").allowed
        )
        if exact.allowed and trace_ok and isinstance(case, dict):
            return {
                "case": case_summary(case),
                "reason": "Selected an exact source-contracted focused Rapid ECG.",
                "targetObjectives": [focus],
            }
        if not case_id or case_id in rejected:
            break
        rejected.add(case_id)
        last_reason = exact.reason if not exact.allowed else "The case lacks server-grade trace proof."
    return {"case": None, "reason": last_reason, "targetObjectives": []}


def _frozen_integration_selection(
    repo,
    *,
    concept: str,
    subskill: str,
    case_digest: str,
    secret: str,
    excluded: set[str],
    require_trace_proof: bool,
) -> dict[str, Any]:
    """Resolve one opaque, preflighted integration slot without substitution."""

    for candidate in repo.candidates(concept):
        case_id = str(candidate.get("case_id") or "")
        if not case_id or not hmac.compare_digest(
            _roster_case_digest(secret, case_id), case_digest
        ):
            continue
        if case_id in excluded:
            return {
                "case": None,
                "reason": "The frozen integration ECG is no longer unique within this round.",
                "targetObjectives": [],
            }
        case = repo.get_case(case_id)
        exact = packet_allows_learning_evidence(case, "rapid", concept, subskill)
        trace_ok = bool(
            not require_trace_proof
            or packet_allows_learning_evidence(
                case, "rapid", "qrs_complex", "localize"
            ).allowed
        )
        if not isinstance(case, dict) or not exact.allowed or not trace_ok:
            return {
                "case": None,
                "reason": (
                    exact.reason
                    if not exact.allowed
                    else "The frozen integration ECG no longer has server-grade trace proof."
                ),
                "targetObjectives": [],
            }
        return {
            "case": case_summary(case),
            "reason": (
                "Served the frozen primary-concept ECG from this integration set."
                if subskill == "synthesize"
                else "Served the frozen secondary-concept ECG from this integration set."
            ),
            "targetObjectives": [concept],
        }
    return {
        "case": None,
        "reason": "A frozen integration ECG is no longer present in the audited corpus.",
        "targetObjectives": [],
    }


PUBLIC_SERVED_TAIL = 25


def _public_round(
    session: dict[str, Any], *, case_reference: Callable[[str], str]
) -> dict[str, Any]:
    """Bound learner-facing metadata without weakening durable uniqueness.

    The complete served ledger remains in server storage and drives selection.
    Returning all 5,000 ids after every case would make round bandwidth
    quadratic, so clients receive a count and small diagnostic tail instead.
    """
    public = dict(session)
    served = [str(case_id) for case_id in (public.pop("served", []) or [])]
    # Exclusions are selection-only server state. Echoing caller-supplied raw
    # corpus identifiers would undo the opaque assessment boundary.
    public.pop("exclusions", None)
    # The tested-objective manifest is an answer key while the ECG is pending.
    # It remains durable in the server session and is released only with the
    # committed answer.
    public.pop("pendingTestedObjectiveManifest", None)
    public["contextKey"] = _public_context_key(str(public.get("contextKey") or ""))
    for key in ("pendingCaseId", "feedbackCaseId"):
        canonical_id = public.get(key)
        public[key] = case_reference(str(canonical_id)) if canonical_id else None
    public["servedCount"] = len(served)
    public["recentServed"] = [
        case_reference(canonical_id)
        for canonical_id in served[-PUBLIC_SERVED_TAIL:]
    ]
    return public


def _grade_claimed_rapid_submission(
    *,
    case: dict[str, Any],
    session: dict[str, Any],
    body: RapidSubmitBody,
    tested_manifest: dict[str, Any],
    selected_concepts: list[str],
    point: Any,
    assessment_scope: str,
    focus_objective: str | None,
    target_only: bool,
) -> tuple[dict[str, Any] | None, dict[str, Any], dict[str, Any]]:
    """Run deterministic graders only after the exact lease is reserved."""

    trace_grade: dict[str, Any] | None = None
    if session["pace"] != "emergency" and isinstance(point, dict):
        try:
            trace_grade = grade_click_answer(
                case,
                str(point["lead"]),
                float(point["timeSec"]),
                float(point["amplitudeMv"]),
                "qrs_complex",
            )
        except (KeyError, TypeError, ValueError):
            trace_grade = {
                "correct": False,
                "noTarget": False,
                "feedback": "Malformed trace proof.",
            }

    attempt = AttemptRequest(
        learnerId=session["learnerId"],
        caseId=body.caseId,
        mode="rapid_practice",
        assessmentScope=assessment_scope,
        focusObjective=focus_objective,
        structuredAnswer=body.structuredAnswer,
        freeTextAnswer=body.freeTextAnswer,
        confidence=body.confidence,
        hintsUsed=0,
    )
    grade = {
        **grade_attempt(case, attempt),
        "masteryDelta": {},
        "legacyObjectiveMasterySuppressed": True,
    }
    if target_only:
        correct_focus = focus_objective in set(grade.get("correctObjectives") or [])
        unassessed = [
            concept
            for concept in body.structuredAnswer.selectedConcepts
            if concept != focus_objective
        ]
        grade.update(
            {
                "score": 1.0 if correct_focus else 0.0,
                "correctObjectives": [focus_objective] if correct_focus else [],
                "missedObjectives": [] if correct_focus else [focus_objective],
                "overcalledObjectives": grade.get("overcalledObjectives", []),
                "unassessedClaims": unassessed,
                "feedback": (
                    f"Focused expert-label check: {str(focus_objective).replace('_', ' ')} matched."
                    if correct_focus
                    else f"Focused expert-label check: review {str(focus_objective).replace('_', ' ')}."
                )
                + (
                    " Other 12-lead claims cannot receive finding credit from this target-only source; non-A/B-supported selections still prevent a precision pass."
                    if unassessed
                    else ""
                ),
                "assessmentScope": "dominant_finding",
                "labelCompleteness": "target_only",
            }
        )
    manifest_recognition_targets = [
        str(entry.get("objectiveId") or "")
        for entry in tested_manifest.get("objectives") or []
        if entry.get("subskill") == "recognize" and entry.get("lapseEligible")
    ]
    if manifest_recognition_targets:
        verified_correct: list[str] = []
        for tested_objective in manifest_recognition_targets:
            scoped_grade = grade_attempt(
                case,
                attempt.model_copy(
                    update={
                        "focusObjective": tested_objective,
                        "assessmentScope": "dominant_finding",
                    }
                ),
            )
            if tested_objective in set(scoped_grade.get("correctObjectives") or []):
                verified_correct.append(tested_objective)
        grade.update(
            {
                "correctObjectives": verified_correct,
                "missedObjectives": [
                    objective_id
                    for objective_id in manifest_recognition_targets
                    if objective_id not in verified_correct
                ],
            }
        )
    grade = bound_rapid_grade_to_manifest(grade, tested_manifest, selected_concepts)
    result = {
        "caseId": body.caseId,
        "displayId": case.get("display_id") or body.caseId,
        "score": float(grade["score"]),
        "correctObjectives": grade.get("correctObjectives", []),
        "missedObjectives": grade.get("missedObjectives", []),
        "overcalledObjectives": grade.get("overcalledObjectives", []),
        "misconceptions": grade.get("misconceptions", []),
        "revealedDiagnosis": grade.get("revealedDiagnosis", ""),
    }
    return trace_grade, grade, result


def build_rapid_router(
    repo,
    store,
    packet_provider: PacketProvider,
    blind_packet: PacketTransformer,
    blind_summary: PacketTransformer,
    resolve_learner: LearnerResolver,
) -> APIRouter:
    router = APIRouter(prefix="/rapid/rounds", tags=["rapid-rounds"])
    assessments = RapidAssessmentStore(store)
    integration_roster_secret = get_settings().adaptive_plan_context_secret
    capability_secret = integration_roster_secret
    # A 5,000-case round must not query and hash-sort the 21k corpus before every
    # ECG. Cache the lightweight corpus index once, then one deterministic order
    # per active round. The small LRU bounds abandoned-round memory; an evicted or
    # restarted round is rebuilt deterministically from its id and durable ledger.
    broad_orders = _BroadRoundOrderCache(repo, max_rounds=16)

    bind_case_packets = getattr(store, "set_case_packet_provider", None)
    if callable(bind_case_packets):
        bind_case_packets(repo.get_case)

    def owned_round(
        round_id: str, authorization: str | None, session_cookie: str | None
    ) -> dict[str, Any]:
        session = store.get_rapid_round(round_id)
        learner = resolve_learner(authorization, "demo", session_cookie)
        if not session or session.get("learnerId") != learner:
            raise HTTPException(status_code=404, detail="Rapid round not found")
        try:
            assessments.ensure_pending_lease(round_id=round_id, learner_id=learner)
        except (AssessmentLedgerError, RapidExposureConflictError, RuntimeError) as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "rapid_assessment_integrity_conflict",
                    "message": "This Rapid item could not be verified against its assessment record.",
                },
            ) from exc
        session = store.get_rapid_round(round_id) or session
        return session

    def case_reference(session: dict[str, Any], canonical_id: str) -> str:
        return issue_ecg_capability(
            capability_secret,
            str(session["learnerId"]),
            "rapid",
            str(session["roundId"]),
            str(canonical_id),
        )

    def reference_matches(
        session: dict[str, Any], reference: object, canonical_id: str
    ) -> bool:
        return matches_ecg_capability(
            reference,
            capability_secret,
            str(session["learnerId"]),
            "rapid",
            str(session["roundId"]),
            str(canonical_id),
        )

    def public_result(
        session: dict[str, Any], result: dict[str, Any], ordinal: int
    ) -> dict[str, Any]:
        canonical_id = str(result.get("caseId") or "")
        return public_assessment_record(
            result,
            case_reference=case_reference(session, canonical_id),
            display_id=assessment_display_id("rapid", ordinal),
        )

    def public_answer(
        session: dict[str, Any], answer: dict[str, Any], ordinal: int
    ) -> dict[str, Any]:
        canonical_id = str(answer.get("caseId") or "")
        return public_assessment_record(
            answer,
            case_reference=case_reference(session, canonical_id),
            display_id=assessment_display_id("rapid", ordinal),
        )

    def answer_ordinal(session: dict[str, Any], canonical_id: str) -> int:
        if str(session.get("feedbackCaseId") or "") == canonical_id:
            return max(1, int(session.get("position") or 0))
        return int(session.get("position") or 0) + 1

    def payload(session: dict[str, Any] | None) -> dict[str, Any]:
        if not session:
            return {"round": None, "current": None, "results": []}
        result_count = store.rapid_answer_count(session["roundId"])
        answers = store.get_recent_rapid_answers(session["roundId"], limit=100)
        current: dict[str, Any] | None = None
        pending_id = session.get("pendingCaseId")
        feedback_id = session.get("feedbackCaseId")
        if pending_id:
            case = repo.get_case(pending_id)
            if case:
                reference = case_reference(session, str(pending_id))
                display_id = assessment_display_id(
                    "rapid", int(session.get("position") or 0) + 1
                )
                current = {
                    "kind": "pending",
                    "case": public_case_summary(
                        blind_summary(case_summary(case)),
                        case_reference=reference,
                        display_id=display_id,
                    ),
                    "packet": public_case_packet(
                        blind_packet(packet_provider(case)),
                        case_reference=reference,
                        display_id=display_id,
                    ),
                    "startedAt": session.get("pendingStartedAt"),
                    "deadlineAt": session.get("pendingDeadlineAt"),
                }
        elif feedback_id:
            answer = store.get_rapid_answer(session["roundId"], feedback_id)
            case = repo.get_case(feedback_id)
            if answer and case:
                ordinal = max(1, int(session.get("position") or 0))
                reference = case_reference(session, str(feedback_id))
                display_id = assessment_display_id("rapid", ordinal)
                current = {
                    "kind": "feedback",
                    "case": public_case_summary(
                        blind_summary(case_summary(case)),
                        case_reference=reference,
                        display_id=display_id,
                    ),
                    "packet": public_case_packet(
                        packet_provider(case),
                        case_reference=reference,
                        display_id=display_id,
                    ),
                    "answer": public_answer(session, answer, ordinal),
                }
        result_start = max(0, result_count - len(answers))
        return {
            "round": _public_round(
                session,
                case_reference=lambda canonical_id: case_reference(
                    session, canonical_id
                ),
            ),
            "current": current,
            "results": [
                public_result(session, answer["result"], result_start + index + 1)
                for index, answer in enumerate(answers)
            ],
            "resultCount": result_count,
            "resultsTruncated": result_count > len(answers),
        }

    @router.post("")
    def start_round(
        body: RapidRoundStartBody,
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ) -> dict[str, Any]:
        if len(set(body.exclusions)) != len(body.exclusions) or any(len(item) > 160 for item in body.exclusions):
            raise HTTPException(status_code=422, detail="Rapid exclusions must be unique bounded case ids")
        learner = resolve_learner(authorization, body.learnerId, session_cookie)
        live_exposures = assessments.live_exposure_ids(learner)
        selection_exclusions = set(body.exclusions) | live_exposures
        if any(key == _INTEGRATION_ROSTER_PARAM for key, _ in _query_pairs(body.contextKey)):
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "rapid_integration_roster_client_owned",
                    "message": "The integration roster is created only by the server.",
                },
            )
        try:
            requested_secondary = _requested_secondary_concept(body.contextKey)
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "rapid_secondary_concept_invalid",
                    "message": "Choose one supported secondary ECG concept.",
                },
            ) from exc
        if body.secondaryConcept != requested_secondary:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "rapid_secondary_concept_mismatch",
                    "message": "The secondary concept must match the validated launch link.",
                },
            )

        context_key = body.contextKey
        if requested_secondary:
            primary = str(body.focusConcept or "")
            if (
                primary not in CONCEPT_BY_ID
                or requested_secondary not in CONCEPT_BY_ID
                or primary == requested_secondary
            ):
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "rapid_integration_concepts_invalid",
                        "message": "Integration requires two different supported ECG concepts.",
                    },
                )
            if body.focusSubskill != "synthesize" or PACE_SCOPE[body.pace] != "full_read":
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "rapid_integration_scope_invalid",
                        "message": "Cross-concept integration requires a ward or untimed complete-read synthesis set.",
                    },
                )
            if body.length < 2:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "rapid_integration_length_too_short",
                        "message": "Cross-concept integration needs at least two unique ECGs.",
                    },
                )

            preflight_session = {
                "learnerId": learner,
                "focusConcept": primary,
                "focusSubskill": "synthesize",
                "assessmentScope": PACE_SCOPE[body.pace],
                "contextKey": body.contextKey,
            }
            require_trace_proof = body.pace != "emergency"
            primary_slot = _focused_corpus_selection(
                repo,
                store,
                preflight_session,
                selection_exclusions,
                require_trace_proof=require_trace_proof,
            )
            if not primary_slot.get("case"):
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "rapid_integration_primary_unavailable",
                        "message": primary_slot.get("reason")
                        or "No eligible primary-concept ECG can be frozen for this set.",
                    },
                )
            primary_case_id = str(primary_slot["case"]["caseId"])
            # Cross-concept comparison is useful formative practice even while
            # complete-read synthesis has no deterministic per-domain mastery
            # contract. The focused selector above still enforces real-source,
            # trace-proof, and exact-concept eligibility. At submission,
            # ``_manifest_for_pending_case`` and the synthesis receipt boundary
            # keep this work at accepted:false/evidenceLevel:none, so allowing
            # the round to start cannot mint synthesis mastery.

            secondary_session = {
                **preflight_session,
                "focusConcept": requested_secondary,
                "focusSubskill": "recognize",
            }
            secondary_slot = _focused_corpus_selection(
                repo,
                store,
                secondary_session,
                selection_exclusions | {primary_case_id},
                require_trace_proof=require_trace_proof,
            )
            if not secondary_slot.get("case"):
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "rapid_integration_secondary_unavailable",
                        "message": secondary_slot.get("reason")
                        or "No distinct eligible secondary-concept ECG can be frozen for this set.",
                    },
                )
            secondary_case_id = str(secondary_slot["case"]["caseId"])
            if secondary_case_id == primary_case_id:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "rapid_integration_unique_roster_unavailable",
                        "message": "Two distinct eligible ECGs are required for this integration set.",
                    },
                )
            context_key = _with_integration_roster(
                body.contextKey,
                _encode_integration_roster(
                    integration_roster_secret,
                    learner_id=learner,
                    primary_concept=primary,
                    secondary_concept=requested_secondary,
                    primary_case_id=primary_case_id,
                    secondary_case_id=secondary_case_id,
                ),
            )

        session = assessments.create_round(
            learner_id=learner,
            pace=body.pace,
            length=body.length,
            assessment_scope=PACE_SCOPE[body.pace],
            deadline_seconds=PACE_SECONDS[body.pace],
            focus_concept=body.focusConcept,
            focus_subskill=body.focusSubskill if body.focusSubskill in ALLOWED_SUBSKILLS else None,
            context_key=context_key,
            exclusions=body.exclusions,
        )
        return payload(session)

    @router.get("/active")
    def active_round(
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ) -> dict[str, Any]:
        learner = resolve_learner(authorization, "demo", session_cookie)
        session = store.get_resumable_rapid_round(learner)
        if session:
            try:
                assessments.ensure_pending_lease(
                    round_id=str(session["roundId"]), learner_id=learner
                )
            except (AssessmentLedgerError, RapidExposureConflictError, RuntimeError) as exc:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "rapid_assessment_integrity_conflict",
                        "message": "This Rapid item could not be verified against its assessment record.",
                    },
                ) from exc
            session = store.get_rapid_round(str(session["roundId"])) or session
        return payload(session)

    @router.get("/{round_id}")
    def get_round(
        round_id: str,
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ) -> dict[str, Any]:
        return payload(owned_round(round_id, authorization, session_cookie))

    @router.get("/{round_id}/results")
    def round_results(
        round_id: str,
        offset: int = 0,
        limit: int = 5000,
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ) -> dict[str, Any]:
        session = owned_round(round_id, authorization, session_cookie)
        bounded_offset = max(0, int(offset))
        bounded_limit = max(1, min(5000, int(limit)))
        answers = store.get_rapid_answers(
            round_id, limit=bounded_limit, offset=bounded_offset
        )
        return {
            "roundId": round_id,
            "offset": bounded_offset,
            "limit": bounded_limit,
            "total": store.rapid_answer_count(round_id),
            "results": [
                public_result(
                    session, answer["result"], bounded_offset + index + 1
                )
                for index, answer in enumerate(answers)
            ],
        }

    @router.get("/{round_id}/waveform/{case_ref}")
    def get_round_waveform(
        round_id: str,
        case_ref: str,
        response: Response,
        leads: str | None = Query(default=None, max_length=120),
        start: float = Query(default=0, ge=0),
        end: float | None = Query(default=None, ge=0),
        maxPoints: int = Query(default=1200, ge=100, le=5000),
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ) -> dict[str, Any]:
        session = owned_round(round_id, authorization, session_cookie)
        canonical_id = next(
            (
                str(candidate)
                for candidate in (
                    session.get("pendingCaseId"),
                    session.get("feedbackCaseId"),
                )
                if candidate and reference_matches(session, case_ref, str(candidate))
            ),
            None,
        )
        if canonical_id is None:
            raise HTTPException(status_code=404, detail="Rapid ECG not found")
        lead_list = [lead.strip() for lead in leads.split(",")] if leads else None
        if lead_list and (
            len(lead_list) > 12
            or any(not lead or len(lead) > 8 for lead in lead_list)
        ):
            raise HTTPException(status_code=422, detail="Invalid waveform lead selection")
        waveform = repo.get_waveform_window(
            canonical_id,
            leads=lead_list,
            start=start,
            end=end,
            max_points=maxPoints,
        )
        if not waveform:
            raise HTTPException(status_code=404, detail="Rapid ECG not found")
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["Pragma"] = "no-cache"
        response.headers["Vary"] = "Authorization, Cookie"
        return public_waveform(waveform, case_reference=case_ref)

    @router.post("/{round_id}/abandon")
    def abandon_round(
        round_id: str,
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ) -> dict[str, Any]:
        session = owned_round(round_id, authorization, session_cookie)
        if session.get("status") == "abandoned":
            # Safe retry: the first request already closed the pending-case and
            # timer boundary. Do not rewrite the transition timestamp.
            return payload(session)
        if session.get("status") != "active":
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "rapid_round_not_active",
                    "message": "Only an active Rapid round can be abandoned.",
                },
            )
        try:
            abandoned = assessments.abandon_round(
                round_id=round_id, learner_id=str(session["learnerId"])
            )
        except (AssessmentLedgerError, RuntimeError) as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "rapid_abandon_integrity_conflict",
                    "message": "The pending ECG changed before it could be left safely.",
                },
            ) from exc
        if not abandoned or abandoned.get("status") != "abandoned":
            # A concurrent final submission may have completed the round after
            # the ownership/read check. Never report a transition that did not
            # win the atomic store boundary.
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "rapid_round_transition_lost",
                    "message": "The Rapid round changed before it could be abandoned.",
                },
            )
        broad_orders.release(round_id)
        return payload(abandoned)

    @router.post("/{round_id}/next")
    def next_round_case(
        round_id: str,
        body: RapidNextBody = RapidNextBody(),
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ) -> dict[str, Any]:
        session = owned_round(round_id, authorization, session_cookie)
        if session.get("status") == "abandoned":
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "rapid_round_abandoned",
                    "message": "This Rapid round was abandoned and cannot serve another ECG.",
                },
            )
        if body.activate:
            return payload(store.activate_rapid_pending(round_id))
        if session.get("feedbackCaseId"):
            session = store.acknowledge_rapid_feedback(round_id) or session
        if session.get("status") == "complete" or session["position"] >= session["length"]:
            broad_orders.release(round_id)
            return payload(session)
        if session.get("pendingCaseId"):
            return payload(session)

        exclusions = (
            set(session.get("exclusions") or [])
            | set(session.get("served") or [])
            | assessments.live_exposure_ids(str(session["learnerId"]))
        )
        focus = session.get("focusConcept") if session["position"] == 0 else None
        require_trace_proof = session["pace"] != "emergency"
        try:
            integration_roster = _decode_integration_roster(
                str(session.get("contextKey") or ""),
                secret=integration_roster_secret,
                learner_id=str(session.get("learnerId") or ""),
                focus_concept=str(session.get("focusConcept") or ""),
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "rapid_integration_roster_invalid",
                    "message": "This integration roster could not be verified; no substitute ECG was served.",
                },
            ) from exc

        frozen_target: str | None = None
        manifest_focus: str | None = str(focus) if focus else None
        if integration_roster and session["position"] in {0, 1}:
            primary_slot = session["position"] == 0
            frozen_target = str(
                integration_roster[
                    "primaryConcept" if primary_slot else "secondaryConcept"
                ]
            )
            selected = _frozen_integration_selection(
                repo,
                concept=frozen_target,
                subskill="synthesize" if primary_slot else "recognize",
                case_digest=str(
                    integration_roster[
                        "primaryDigest" if primary_slot else "secondaryDigest"
                    ]
                ),
                secret=integration_roster_secret,
                excluded=exclusions,
                require_trace_proof=require_trace_proof,
            )
            # The secondary slot guarantees concept exposure but remains a
            # broad complete read. It must not mint the primary synthesis
            # receipt or pretend a Guided integration prompt was independently
            # graded against two concepts at once.
            manifest_focus = frozen_target if primary_slot else None
        elif focus and session["position"] == 0:
            # Focused selection owns a different, exact-contract query. Defer
            # the 21k broad permutation until a later mixed slot actually needs
            # it (and never build it for a one-item focused round).
            selected = _focused_corpus_selection(
                repo,
                store,
                session,
                exclusions,
                require_trace_proof=require_trace_proof,
            )
        else:
            order, rejected = broad_orders.get(round_id)
            selected = _broad_corpus_selection(
                repo,
                exclusions,
                round_id,
                require_trace_proof=require_trace_proof,
                ordered_candidates=order,
                rejected_candidates=rejected,
            )
        if not selected.get("case"):
            raise HTTPException(status_code=409, detail=selected.get("reason") or "No Rapid case is available")
        case_id = selected["case"]["caseId"]
        required_target = frozen_target or (str(focus) if focus else None)
        if required_target and required_target not in selected.get("targetObjectives", []):
            raise HTTPException(
                status_code=409,
                detail="Rapid selector could not honor the frozen focused concept slot",
            )
        selected_case = repo.get_case(case_id)
        if not isinstance(selected_case, dict):
            raise HTTPException(status_code=409, detail="Rapid selected case is no longer available")
        tested_manifest = _manifest_for_pending_case(
            selected_case,
            session,
            focus_concept=manifest_focus,
        )
        try:
            claimed = assessments.freeze_pending(
                round_id=round_id,
                learner_id=str(session["learnerId"]),
                case_id=case_id,
                tested_objective_manifest=tested_manifest,
            )
        except RapidExposureConflictError as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "rapid_live_exposure_conflict",
                    "message": "That ECG is already open in another assessment. Start the next item after leaving it there.",
                },
            ) from exc
        except (AssessmentLedgerError, RuntimeError) as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "rapid_pending_freeze_failed",
                    "message": "The selected ECG could not be frozen safely for this round.",
                },
            ) from exc
        response = payload(claimed)
        response["selectionReason"] = selected.get("reason")
        return response

    @router.post("/{round_id}/submit")
    def submit_round_case(
        round_id: str,
        body: RapidSubmitBody,
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ) -> dict[str, Any]:
        session = owned_round(round_id, authorization, session_cookie)
        submission_received_at = datetime.now(UTC)
        pending_id = str(session.get("pendingCaseId") or "")
        feedback_id = str(session.get("feedbackCaseId") or "")
        canonical_id = next(
            (
                candidate
                for candidate in (pending_id, feedback_id)
                if candidate and reference_matches(session, body.caseId, candidate)
            ),
            None,
        )
        if canonical_id is None:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "rapid_case_not_pending",
                    "pendingCaseId": (
                        case_reference(session, pending_id) if pending_id else None
                    ),
                },
            )
        body = body.model_copy(update={"caseId": canonical_id})
        prior = store.get_rapid_answer(round_id, canonical_id)
        if prior:
            if prior.get("integrityStatus") in {"legacy_incomplete", "finalizing"} or not prior.get("receipts"):
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "rapid_legacy_answer_quarantined",
                        "message": (
                            "This pre-atomic answer has an incomplete evidence ledger and cannot be "
                            "replayed or repaired without risking duplicate mastery credit."
                        ),
                    },
                )
            response = payload(store.get_rapid_round(round_id))
            response.update({
                "answer": public_answer(
                    session, prior, answer_ordinal(session, canonical_id)
                ),
                "receipts": prior["receipts"],
                "replay": True,
            })
            return response
        if pending_id != canonical_id:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "rapid_case_not_pending",
                    "pendingCaseId": (
                        case_reference(session, pending_id) if pending_id else None
                    ),
                },
            )
        case = repo.get_case(canonical_id)
        if not case:
            raise HTTPException(status_code=404, detail="Rapid case not found")

        frozen_manifest = session.get("pendingTestedObjectiveManifest") or {}
        manifest_valid = bool(
            isinstance(frozen_manifest, dict)
            and frozen_manifest.get("version")
            == RAPID_TESTED_OBJECTIVE_MANIFEST_VERSION
            and str(frozen_manifest.get("caseId") or "") == body.caseId
            and isinstance(frozen_manifest.get("objectives"), list)
        )
        if not manifest_valid:
            # Existing deployments can contain a pending row created before the
            # additive manifest migration. Rebuild it once from the immutable
            # round/case contract, then freeze it before grading.
            effective_focus = (
                str(session.get("focusConcept") or "")
                if int(session.get("position") or 0) == 0
                else ""
            )
            rebuilt_manifest = _manifest_for_pending_case(
                case,
                session,
                focus_concept=effective_focus or None,
            )
            session = (
                store.ensure_rapid_pending_manifest(
                    round_id, body.caseId, rebuilt_manifest
                )
                or session
            )
            frozen_manifest = session.get("pendingTestedObjectiveManifest") or {}
            manifest_valid = bool(
                isinstance(frozen_manifest, dict)
                and frozen_manifest.get("version")
                == RAPID_TESTED_OBJECTIVE_MANIFEST_VERSION
                and str(frozen_manifest.get("caseId") or "") == body.caseId
                and isinstance(frozen_manifest.get("objectives"), list)
            )
        if not manifest_valid:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "rapid_tested_manifest_missing",
                    "message": "The server could not recover this item's assessment contract.",
                },
            )
        selected_concepts = list(
            dict.fromkeys(body.structuredAnswer.selectedConcepts)
        )
        tested_manifest = finalize_rapid_tested_objective_manifest(
            frozen_manifest,
            case,
            selected_concepts,
        )

        pre_submit_timed_out = _deadline_elapsed(session, submission_received_at)
        trace = body.traceEvidence or {}
        point = trace.get("point") if trace.get("mode") == "point" else None
        if session["pace"] != "emergency":
            if not pre_submit_timed_out and not isinstance(point, dict):
                # Presence is a structural completion gate, not correctness
                # feedback. A wrong but well-formed point is committed below so
                # it cannot be refined through repeated pre-commit probes.
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "rapid_trace_proof_required",
                        "message": "Mark one QRS trace point before committing this read.",
                    },
                )
            # A wrong trace mark is assessment evidence, not a pre-commit
            # validation error. Persist and reveal its correctness together with
            # the interpretation grade below; otherwise repeated submit probes
            # become an answer oracle before durable commitment.

        if (
            session["assessmentScope"] == "full_read"
            and not pre_submit_timed_out
            and not _synthesis_task_complete(body.structuredAnswer)
        ):
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "rapid_systematic_sweep_required",
                    "message": (
                        "Complete all eight systematic sweep fields, select at least one supported finding "
                        "(including normal when appropriate), and write an evidence-limited synthesis."
                    ),
                },
            )

        target_only = _target_only_source(case)
        assessment_scope = "dominant_finding" if target_only else session["assessmentScope"]
        focused_recognition_target = next(
            (
                str(entry.get("objectiveId") or "")
                for entry in tested_manifest.get("objectives") or []
                if entry.get("subskill") == "recognize"
                and entry.get("role") == "required"
            ),
            "",
        )
        focus_objective = (
            focused_recognition_target
            if tested_manifest.get("taskKind") == "focused_handoff"
            else str(session.get("focusConcept") or "")
            if target_only
            else None
        )
        if target_only and not focus_objective:
            raise HTTPException(
                status_code=409,
                detail="A target-only rhythm source requires an explicit focused Rapid objective.",
            )
        try:
            reservation = assessments.claim_answer_submission(
                round_id=round_id,
                case_id=body.caseId,
                learner_id=str(session["learnerId"]),
            )
        except (AssessmentLedgerError, RuntimeError) as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "rapid_submission_reservation_failed",
                    "message": "This ECG changed before the answer could be reserved.",
                },
            ) from exc
        if reservation["status"] == "replay":
            prior = reservation["answer"]
            if prior.get("integrityStatus") in {"legacy_incomplete", "finalizing"} or not prior.get("receipts"):
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "rapid_legacy_answer_quarantined",
                        "message": "This earlier answer has an incomplete evidence record and cannot be replayed safely.",
                    },
                )
            response = payload(store.get_rapid_round(round_id))
            response.update({
                "answer": public_answer(
                    session, prior, answer_ordinal(session, canonical_id)
                ),
                "receipts": prior["receipts"],
                "replay": True,
            })
            return response
        if reservation["status"] == "missing":
            raise HTTPException(status_code=404, detail="Rapid round not found")
        if reservation["status"] == "not_pending":
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "rapid_case_not_pending",
                    "pendingCaseId": (
                        case_reference(
                            session, str(reservation.get("pendingCaseId"))
                        )
                        if reservation.get("pendingCaseId")
                        else None
                    ),
                },
            )

        try:
            trace_grade, grade, result = _grade_claimed_rapid_submission(
                case=case,
                session=session,
                body=body,
                tested_manifest=tested_manifest,
                selected_concepts=selected_concepts,
                point=point,
                assessment_scope=assessment_scope,
                focus_objective=focus_objective,
                target_only=target_only,
            )
        except Exception:
            assessments.release_answer_submission(
                round_id=round_id,
                learner_id=str(session["learnerId"]),
                lease_id=str(reservation["leaseId"]),
                submission_key=str(reservation["submissionKey"]),
            )
            raise
        def release_reserved_submission() -> None:
            assessments.release_answer_submission(
                round_id=round_id,
                learner_id=str(session["learnerId"]),
                lease_id=str(reservation["leaseId"]),
                submission_key=str(reservation["submissionKey"]),
            )

        def committed_evidence_policy(concept: str, subskill: str):
            try:
                return packet_allows_learning_evidence(
                    case, "rapid", concept, subskill
                )
            except Exception:
                release_reserved_submission()
                raise

        # Build a pure receipt/event plan first. The store applies the entire
        # plan together with the answer, generic attempt, and round advance in
        # one BEGIN IMMEDIATE transaction below.
        timed_out = pre_submit_timed_out
        supported = set(case.get("supported_objectives") or [])
        try:
            morphology_key = retention_morphology_key(case)
        except Exception:
            release_reserved_submission()
            raise
        durable_manifest = tested_manifest
        required_recognition = {
            str(entry.get("objectiveId") or "")
            for entry in durable_manifest.get("objectives") or []
            if entry.get("subskill") == "recognize"
            and entry.get("lapseEligible")
        }
        accountable_recognition = required_recognition
        graded_correct_recognition = set(grade.get("correctObjectives") or [])
        recognition_precision_ok = not bool(grade.get("overcalledObjectives"))
        receipts: list[dict[str, Any]] = []
        receipt_events: dict[int, dict[str, Any]] = {}

        def append_event_receipt(
            event: dict[str, Any], receipt: dict[str, Any]
        ) -> None:
            receipt_events[len(receipts)] = event
            receipts.append(receipt)
        for concept in selected_concepts:
            exact_policy = committed_evidence_policy(concept, "recognize")
            if concept not in supported or not exact_policy.allowed:
                receipts.append({
                    "concept": concept,
                    "subskill": "recognize",
                    "accepted": False,
                    "evidenceLevel": "none",
                    "reason": exact_policy.reason,
                })
                continue
            if concept not in accountable_recognition:
                receipts.append({
                    "concept": concept,
                    "subskill": "recognize",
                    "accepted": False,
                    "evidenceLevel": "none",
                    "reason": (
                        "This focused handoff records only its exact server-owned competency target."
                        if durable_manifest.get("taskKind") == "focused_handoff"
                        else "This finding was not part of the frozen Rapid assessment contract."
                    ),
                })
                continue
            if (
                concept not in graded_correct_recognition
                or not recognition_precision_ok
                or timed_out
            ):
                # Required targets that fail recall, precision, or timing are
                # recorded exactly once by the frozen lapse loop below.
                continue
            event = {
                "eventKey": f"rapid:{round_id}:{body.caseId}:recognize:{concept}",
                "moduleId": "rapid",
                "sceneId": f"{session['pace']}:{session['assessmentScope']}",
                "interactionId": f"{body.caseId}:explicit:{concept}",
                "concept": concept,
                "subskills": ["recognize"],
                "score": 1.0,
                "correct": True,
                "attempts": 1,
                "assistance": "independent",
                "hintsUsed": 0,
                "confidence": body.confidence,
                "evidenceLevel": "independent_transfer",
                "caseId": body.caseId,
                "caseProvenance": "real_eligible",
                "caseEligible": True,
                "misconceptions": [],
                "_retentionVerified": True,
                "_retentionMorphologyKey": morphology_key,
                "_serverVerifiedScoring": True,
            }
            append_event_receipt(event, {
                "concept": concept,
                "subskill": "recognize",
                "accepted": True,
                "evidenceLevel": "independent_transfer",
            })

        # Only the frozen, lapse-eligible recognition targets may create
        # negative competency evidence. Incidental packet co-labels and the
        # overcalled pathologies never become competency targets; an overcall
        # can only cause the frozen target task itself to fail precision.
        for tested_concept in sorted(required_recognition):
            tested_policy = committed_evidence_policy(
                tested_concept, "recognize"
            )
            tested_failed = bool(
                timed_out
                or tested_concept not in graded_correct_recognition
                or not recognition_precision_ok
            )
            if (
                not tested_failed
                or tested_concept not in supported
                or not tested_policy.allowed
            ):
                continue
            event = {
                "eventKey": f"rapid:{round_id}:{body.caseId}:recognize-lapse:{tested_concept}",
                "moduleId": "rapid",
                "sceneId": f"{session['pace']}:{session['assessmentScope']}",
                "interactionId": f"{body.caseId}:missed-tested:{tested_concept}",
                "concept": tested_concept,
                "subskills": ["recognize"],
                "score": 0.0,
                "correct": False,
                "attempts": 1,
                "assistance": "independent",
                "hintsUsed": 0,
                "confidence": body.confidence,
                "evidenceLevel": "independent_transfer",
                "caseId": body.caseId,
                "caseProvenance": "real_eligible",
                "caseEligible": True,
                "misconceptions": grade.get("misconceptions", []),
                "_retentionVerified": True,
                "_retentionMorphologyKey": morphology_key,
                "_serverVerifiedScoring": True,
            }
            append_event_receipt(event, {
                "concept": tested_concept,
                "subskill": "recognize",
                "accepted": True,
                "correct": False,
                "evidenceLevel": "independent_transfer",
                "reason": (
                    "The server deadline elapsed; the focused timed task records a lapse, never a success."
                    if timed_out
                    else "The tested target was included with one or more non-A/B-supported selections, so recognition precision did not pass."
                    if not recognition_precision_ok
                    else "A frozen tested objective was missed on an eligible real ECG."
                ),
            })

        if trace_grade and trace_grade.get("correct"):
            trace_policy = committed_evidence_policy(
                "qrs_complex", "localize"
            )
            if not trace_policy.allowed or timed_out:
                receipts.append({
                    "concept": "qrs_complex",
                    "subskill": "localize",
                    "accepted": False,
                    "evidenceLevel": "none",
                    "reason": (
                        "The server deadline elapsed; trace proof cannot earn positive evidence."
                        if timed_out
                        else trace_policy.reason
                    ),
                })
            else:
                event = {
                    "eventKey": f"rapid:{round_id}:{body.caseId}:qrs-trace",
                    "moduleId": "rapid",
                    "sceneId": f"{session['pace']}:{session['assessmentScope']}",
                    "interactionId": f"{body.caseId}:qrs-trace",
                    "concept": "qrs_complex",
                    "subskills": ["localize"],
                    "score": 1.0,
                    "correct": True,
                    "attempts": 1,
                    "assistance": "independent",
                    "hintsUsed": 0,
                    "confidence": body.confidence,
                    "evidenceLevel": "independent_transfer",
                    "caseId": body.caseId,
                    "caseProvenance": "real_eligible",
                    "caseEligible": True,
                    "misconceptions": [],
                    "_retentionVerified": True,
                    "_retentionMorphologyKey": morphology_key,
                    "_serverVerifiedScoring": True,
                }
                append_event_receipt(event, {
                    "concept": "qrs_complex",
                    "subskill": "localize",
                    "accepted": True,
                    "evidenceLevel": "independent_transfer",
                })

        tested_synthesis_target = next(
            (
                str(entry.get("objectiveId") or "")
                for entry in durable_manifest.get("objectives") or []
                if entry.get("subskill") == "synthesize"
                and entry.get("lapseEligible")
            ),
            "",
        )
        focused_synthesis_attempt = bool(
            durable_manifest.get("taskKind") == "focused_handoff"
            and session.get("focusSubskill") == "synthesize"
        )
        if tested_synthesis_target or focused_synthesis_attempt:
            # The complete read remains useful formative practice, but field
            # presence is not deterministic per-domain synthesis grading. Keep
            # this as a non-evidence boundary receipt and never append an event
            # (positive or negative) from prose or sweep completion alone.
            receipts.append({
                "concept": (
                    tested_synthesis_target
                    or _receipt_concept(session)
                    or str(session.get("focusConcept") or "")
                ),
                "subskill": "synthesize",
                "accepted": False,
                "evidenceLevel": "none",
                "reason": RAPID_SYNTHESIS_RECEIPT_UNAVAILABLE_REASON,
            })

        receipts = [
            {**receipt, "registryVersion": REGISTRY_VERSION}
            for receipt in receipts
        ]
        recorded = assessments.finalize_answer(
            round_id=round_id,
            learner_id=str(session["learnerId"]),
            lease_id=str(reservation["leaseId"]),
            submission_key=str(reservation["submissionKey"]),
            position=int(reservation["position"]),
            case_id=body.caseId,
            response={
                "structuredAnswer": body.structuredAnswer.model_dump(),
                "freeTextAnswer": body.freeTextAnswer,
                "confidence": body.confidence,
                "traceEvidence": body.traceEvidence,
            },
            grade=grade,
            # Per-case grading is deliberately provider-independent. Learners
            # can invoke the grounded tutor after commitment; completed-round
            # debriefing has its own bounded AI request.
            tutor=None,
            trace_grade=trace_grade,
            tested_objective_manifest=tested_manifest,
            confidence=body.confidence,
            result=result,
            receipts=receipts,
            receipt_events=receipt_events,
            submitted_at=submission_received_at,
            planned_timed_out=timed_out,
        )
        if recorded["status"] == "not_pending":
            prior = store.get_rapid_answer(round_id, body.caseId)
            if prior and prior.get("receipts") and prior.get("integrityStatus") not in {
                "legacy_incomplete", "finalizing"
            }:
                response = payload(store.get_rapid_round(round_id))
                response.update({
                    "answer": public_answer(
                        session, prior, answer_ordinal(session, canonical_id)
                    ),
                    "receipts": prior["receipts"],
                    "replay": True,
                })
                return response
            raise HTTPException(status_code=409, detail="Rapid case is no longer pending")
        if recorded["status"] == "missing":
            raise HTTPException(status_code=404, detail="Rapid round not found")
        if recorded["status"] == "manifest_mismatch":
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "rapid_tested_manifest_mismatch",
                    "message": "The tested-objective contract changed before commitment.",
                },
            )
        if recorded["status"] == "deadline_state_mismatch":
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "rapid_deadline_state_changed",
                    "message": "The server-owned deadline state changed before atomic commitment.",
                },
            )
        if recorded["status"] == "position_mismatch":
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "rapid_round_position_changed",
                    "message": "The Rapid round advanced before this answer could be committed.",
                },
            )
        if recorded["status"] == "legacy_incomplete":
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "rapid_legacy_answer_quarantined",
                    "message": (
                        "This pre-atomic answer has an incomplete evidence ledger and cannot be "
                        "replayed or repaired without risking duplicate mastery credit."
                    ),
                },
            )
        if recorded["status"] == "replay":
            answer = recorded["answer"]
            response = payload(store.get_rapid_round(round_id))
            response.update({
                "answer": public_answer(
                    session, answer, answer_ordinal(session, canonical_id)
                ),
                "receipts": answer["receipts"],
                "replay": True,
            })
            return response

        answer = recorded["answer"]
        durable_receipts = answer["receipts"]
        response = payload(store.get_rapid_round(round_id))
        response.update({
            "answer": public_answer(
                session, answer, int(session.get("position") or 0) + 1
            ),
            "receipts": durable_receipts,
            "replay": False,
            "profile": store.get_profile(session["learnerId"]),
        })
        return response

    return router
