"""Server-owned lifecycle and evidence boundary for Rapid ECG rounds."""

from __future__ import annotations

from collections import OrderedDict
from datetime import UTC, datetime
import hashlib
from threading import RLock
from typing import Any, Callable, Literal
from urllib.parse import parse_qs

from fastapi import APIRouter, Cookie, Header, HTTPException
from pydantic import BaseModel, Field

from .adaptive import next_case
from .auth import SESSION_COOKIE_NAME
from .data_sources import case_summary
from .grading import grade_attempt, grade_click_answer
from .objectives import objective_definition
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

PACE_SECONDS: dict[str, int | None] = {"ward": 75, "emergency": 20, "untimed": None}
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
    if focus not in definition.case_concepts:
        return receipt_concept, False, "The focused ECG family cannot prove the requested synthesis objective."
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


PUBLIC_SERVED_TAIL = 25


def _public_round(session: dict[str, Any]) -> dict[str, Any]:
    """Bound learner-facing metadata without weakening durable uniqueness.

    The complete served ledger remains in server storage and drives selection.
    Returning all 5,000 ids after every case would make round bandwidth
    quadratic, so clients receive a count and small diagnostic tail instead.
    """
    public = dict(session)
    served = [str(case_id) for case_id in (public.pop("served", []) or [])]
    public["servedCount"] = len(served)
    public["recentServed"] = served[-PUBLIC_SERVED_TAIL:]
    return public


def build_rapid_router(
    repo,
    store,
    packet_provider: PacketProvider,
    blind_packet: PacketTransformer,
    blind_summary: PacketTransformer,
    resolve_learner: LearnerResolver,
) -> APIRouter:
    router = APIRouter(prefix="/rapid/rounds", tags=["rapid-rounds"])
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
        return session

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
                current = {
                    "kind": "pending",
                    "case": blind_summary(case_summary(case)),
                    "packet": blind_packet(packet_provider(case)),
                    "startedAt": session.get("pendingStartedAt"),
                    "deadlineAt": session.get("pendingDeadlineAt"),
                }
        elif feedback_id:
            answer = store.get_rapid_answer(session["roundId"], feedback_id)
            case = repo.get_case(feedback_id)
            if answer and case:
                current = {
                    "kind": "feedback",
                    "case": blind_summary(case_summary(case)),
                    "packet": packet_provider(case),
                    "answer": answer,
                }
        return {
            "round": _public_round(session),
            "current": current,
            "results": [answer["result"] for answer in answers],
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
        session = store.create_rapid_round(
            learner,
            body.pace,
            body.length,
            PACE_SCOPE[body.pace],
            PACE_SECONDS[body.pace],
            focus_concept=body.focusConcept,
            focus_subskill=body.focusSubskill if body.focusSubskill in ALLOWED_SUBSKILLS else None,
            context_key=body.contextKey,
            exclusions=body.exclusions,
        )
        return payload(session)

    @router.get("/active")
    def active_round(
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ) -> dict[str, Any]:
        learner = resolve_learner(authorization, "demo", session_cookie)
        return payload(store.get_resumable_rapid_round(learner))

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
        owned_round(round_id, authorization, session_cookie)
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
            "results": [answer["result"] for answer in answers],
        }

    @router.post("/{round_id}/next")
    def next_round_case(
        round_id: str,
        body: RapidNextBody = RapidNextBody(),
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ) -> dict[str, Any]:
        session = owned_round(round_id, authorization, session_cookie)
        if body.activate:
            return payload(store.activate_rapid_pending(round_id))
        if session.get("feedbackCaseId"):
            session = store.acknowledge_rapid_feedback(round_id) or session
        if session.get("status") == "complete" or session["position"] >= session["length"]:
            broad_orders.release(round_id)
            return payload(session)
        if session.get("pendingCaseId"):
            return payload(session)

        exclusions = set(session.get("exclusions") or []) | set(session.get("served") or [])
        focus = session.get("focusConcept") if session["position"] == 0 else None
        require_trace_proof = session["pace"] != "emergency"
        if focus and session["position"] == 0:
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
        if focus and focus not in selected.get("targetObjectives", []):
            raise HTTPException(status_code=409, detail="Rapid selector could not honor the focused first case")
        claimed = store.set_rapid_pending(round_id, case_id)
        response = payload(claimed)
        response["selectionReason"] = selected.get("reason")
        response["targetObjectives"] = selected.get("targetObjectives", [])
        return response

    @router.post("/{round_id}/submit")
    def submit_round_case(
        round_id: str,
        body: RapidSubmitBody,
        authorization: str | None = Header(default=None),
        session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    ) -> dict[str, Any]:
        session = owned_round(round_id, authorization, session_cookie)
        prior = store.get_rapid_answer(round_id, body.caseId)
        if prior:
            response = payload(store.get_rapid_round(round_id))
            response.update({"answer": prior, "receipts": prior["receipts"], "replay": True})
            return response
        if session.get("pendingCaseId") != body.caseId:
            raise HTTPException(
                status_code=409,
                detail={"code": "rapid_case_not_pending", "pendingCaseId": session.get("pendingCaseId")},
            )
        case = repo.get_case(body.caseId)
        if not case:
            raise HTTPException(status_code=404, detail="Rapid case not found")

        pre_submit_timed_out = _deadline_elapsed(session)
        trace_grade: dict[str, Any] | None = None
        trace = body.traceEvidence or {}
        point = trace.get("point") if trace.get("mode") == "point" else None
        if session["pace"] != "emergency":
            if isinstance(point, dict):
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
            if not pre_submit_timed_out and not bool(trace_grade and trace_grade.get("correct")):
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "rapid_trace_proof_required",
                        "message": "Ward and untimed submissions require a server-verified QRS localization proof.",
                    },
                )

        target_only = _target_only_source(case)
        assessment_scope = "dominant_finding" if target_only else session["assessmentScope"]
        focus_objective = str(session.get("focusConcept") or "") if target_only else None
        if target_only and not focus_objective:
            raise HTTPException(
                status_code=409,
                detail="A target-only rhythm source requires an explicit focused Rapid objective.",
            )
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
                concept for concept in body.structuredAnswer.selectedConcepts
                if concept != focus_objective
            ]
            grade.update({
                "score": 1.0 if correct_focus else 0.0,
                "correctObjectives": [focus_objective] if correct_focus else [],
                "missedObjectives": [] if correct_focus else [focus_objective],
                "overcalledObjectives": [],
                "unassessedClaims": unassessed,
                "feedback": (
                    f"Focused expert-label check: {focus_objective.replace('_', ' ')} matched."
                    if correct_focus
                    else f"Focused expert-label check: review {focus_objective.replace('_', ' ')}."
                ) + (
                    " Other 12-lead claims were not scored because this rhythm-stream source is not exhaustively morphology-labelled."
                    if unassessed else ""
                ),
                "assessmentScope": "dominant_finding",
                "labelCompleteness": "target_only",
            })
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
        recorded = store.record_rapid_answer(
            round_id=round_id,
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
            confidence=body.confidence,
            result=result,
        )
        if recorded["status"] == "not_pending":
            prior = store.get_rapid_answer(round_id, body.caseId)
            if prior:
                response = payload(store.get_rapid_round(round_id))
                response.update({"answer": prior, "receipts": prior["receipts"], "replay": True})
                return response
            raise HTTPException(status_code=409, detail="Rapid case is no longer pending")
        if recorded["status"] == "missing":
            raise HTTPException(status_code=404, detail="Rapid round not found")
        if recorded["status"] == "replay":
            answer = recorded["answer"]
            response = payload(store.get_rapid_round(round_id))
            response.update({"answer": answer, "receipts": answer["receipts"], "replay": True})
            return response

        answer = recorded["answer"]
        timed_out = bool((answer.get("result") or {}).get("timedOut"))
        supported = set(case.get("supported_objectives") or [])
        morphology_key = retention_morphology_key(case)
        selected_concepts = list(dict.fromkeys(body.structuredAnswer.selectedConcepts))
        receipts: list[dict[str, Any]] = []
        for concept in selected_concepts:
            exact_policy = packet_allows_learning_evidence(
                case, "rapid", concept, "recognize"
            )
            if concept not in supported or not exact_policy.allowed:
                receipts.append({
                    "concept": concept,
                    "subskill": "recognize",
                    "accepted": False,
                    "evidenceLevel": "none",
                    "reason": exact_policy.reason,
                })
                continue
            if timed_out:
                receipts.append({
                    "concept": concept,
                    "subskill": "recognize",
                    "accepted": False,
                    "evidenceLevel": "none",
                    "reason": "The server deadline elapsed; a stored answer cannot earn positive evidence.",
                })
                continue
            event = store.save_guided_learning_event(session["learnerId"], {
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
            })
            receipts.append({
                "concept": concept,
                "subskill": "recognize",
                "accepted": True,
                "evidenceLevel": event["effectiveEvidenceLevel"],
            })

        # A focused round defines one recognition construct in advance. If that
        # supported finding is missed, record exactly one independent lapse. In
        # an unscoped round we do not penalize every unselected co-label.
        focus_concept = session.get("focusConcept")
        missed = set(grade.get("missedObjectives") or [])
        focus_policy = packet_allows_learning_evidence(
            case, "rapid", str(focus_concept or ""), "recognize"
        )
        focus_failed = bool(
            timed_out
            or (
                focus_concept in missed
                and focus_concept not in selected_concepts
            )
        )
        if (
            focus_concept
            and focus_concept in supported
            and focus_failed
            and focus_policy.allowed
        ):
            event = store.save_guided_learning_event(session["learnerId"], {
                "eventKey": f"rapid:{round_id}:{body.caseId}:recognize-lapse:{focus_concept}",
                "moduleId": "rapid",
                "sceneId": f"{session['pace']}:{session['assessmentScope']}",
                "interactionId": f"{body.caseId}:missed-focus:{focus_concept}",
                "concept": focus_concept,
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
            })
            receipts.append({
                "concept": focus_concept,
                "subskill": "recognize",
                "accepted": True,
                "correct": False,
                "evidenceLevel": event["effectiveEvidenceLevel"],
                "reason": (
                    "The server deadline elapsed; the focused timed task records a lapse, never a success."
                    if timed_out
                    else "The supported focus finding was missed on an eligible real ECG."
                ),
            })

        if trace_grade and trace_grade.get("correct"):
            trace_policy = packet_allows_learning_evidence(
                case, "rapid", "qrs_complex", "localize"
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
                event = store.save_guided_learning_event(session["learnerId"], {
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
                })
                receipts.append({
                    "concept": "qrs_complex",
                    "subskill": "localize",
                    "accepted": True,
                    "evidenceLevel": event["effectiveEvidenceLevel"],
                })

        if session.get("focusSubskill") == "synthesize":
            receipt_concept, synthesis_allowed, synthesis_reason = _synthesis_contract(
                case, session
            )
            task_complete = _synthesis_task_complete(body.structuredAnswer)
            if not synthesis_allowed:
                receipts.append({
                    "concept": receipt_concept or str(session.get("focusConcept") or ""),
                    "subskill": "synthesize",
                    "accepted": False,
                    "evidenceLevel": "none",
                    "reason": synthesis_reason,
                })
            elif not task_complete and not timed_out:
                receipts.append({
                    "concept": receipt_concept,
                    "subskill": "synthesize",
                    "accepted": False,
                    "evidenceLevel": "none",
                    "reason": "Complete all eight sweep fields, select at least one finding, and write an evidence-limited synthesis before committing.",
                })
            else:
                focus = str(session.get("focusConcept") or "")
                explicit_overcalls = [
                    concept for concept in body.structuredAnswer.selectedConcepts
                    if concept not in supported
                    and (case.get("concept_confidence", {}).get(concept) or {}).get("tier")
                    in {"C", "D"}
                ]
                synthesis_correct = bool(
                    not timed_out
                    and task_complete
                    and focus in set(grade.get("correctObjectives") or [])
                    and not explicit_overcalls
                    and float(grade.get("score", 0.0)) >= 0.75
                )
                event = store.save_guided_learning_event(session["learnerId"], {
                    "eventKey": f"rapid:{round_id}:{body.caseId}:synthesize:{receipt_concept}",
                    "moduleId": "rapid",
                    "sceneId": f"{session['pace']}:full_read",
                    "interactionId": f"{body.caseId}:structured-sweep:{receipt_concept}",
                    "concept": receipt_concept,
                    "subskills": ["synthesize"],
                    "score": max(0.0, min(1.0, float(grade.get("score", 0.0)))),
                    "correct": synthesis_correct,
                    "attempts": 1,
                    "assistance": "independent",
                    "hintsUsed": 0,
                    "confidence": body.confidence,
                    "evidenceLevel": "independent_transfer",
                    "evidenceSource": "structured_sweep",
                    "caseId": body.caseId,
                    "caseProvenance": "real_eligible",
                    "caseEligible": True,
                    "misconceptions": (
                        grade.get("misconceptions", [])
                        if not synthesis_correct else []
                    ),
                    "_retentionVerified": True,
                    "_retentionMorphologyKey": morphology_key,
                    "_serverVerifiedScoring": True,
                })
                receipts.append({
                    "concept": receipt_concept,
                    "subskill": "synthesize",
                    "accepted": True,
                    "correct": synthesis_correct,
                    "evidenceLevel": event["effectiveEvidenceLevel"],
                    "reason": (
                        "The complete structured sweep met the packet-grounded synthesis rubric."
                        if synthesis_correct
                        else "The complete independent sweep was recorded, but it missed the focus, overcalled an unsupported finding, scored below 75%, or exceeded the deadline."
                    ),
                })

        answer = store.set_rapid_answer_receipts(round_id, body.caseId, receipts) or answer
        response = payload(store.get_rapid_round(round_id))
        response.update({
            "answer": answer,
            "receipts": receipts,
            "replay": False,
            "profile": store.get_profile(session["learnerId"]),
        })
        return response

    return router
