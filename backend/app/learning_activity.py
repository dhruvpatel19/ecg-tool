"""Owner-bound, answer-key-free learning history projection.

The activity feed is deliberately a narrow projection over durable commit
tables. It never returns corpus ids, responses, grades, feedback, tutor prose,
assessment manifests, or authored answer keys. The normalized learner-event
ledger can replace this compatibility projection without changing the public
contract once its backfill is complete.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import sqlite3
from dataclasses import dataclass
from typing import Any


ACTIVITY_MODES = {"all", "guided", "training", "rapid", "clinical"}
MAX_ACTIVITY_PAGE = 50
CURSOR_VERSION = "learning-activity-cursor-v1"


class ActivityCursorError(ValueError):
    """Raised for every invalid, tampered, or cross-owner cursor."""


@dataclass(frozen=True)
class _Cursor:
    occurred_at: str
    source_rank: int
    source_id: int


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _sign(secret: str, purpose: str, value: str) -> str:
    return _b64encode(
        hmac.new(
            secret.encode("utf-8"),
            f"learning-activity:{purpose}:{value}".encode("utf-8"),
            hashlib.sha256,
        ).digest()
    )


def _owner_digest(secret: str, learner_id: str) -> str:
    return _sign(secret, "owner", learner_id)[:24]


def _encode_cursor(
    *, secret: str, learner_id: str, mode: str, cursor: _Cursor
) -> str:
    payload = {
        "v": CURSOR_VERSION,
        "o": _owner_digest(secret, learner_id),
        "m": mode,
        "t": cursor.occurred_at,
        "r": cursor.source_rank,
        "i": cursor.source_id,
    }
    encoded = _b64encode(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    return f"{encoded}.{_sign(secret, 'cursor', encoded)}"


def _decode_cursor(
    value: str | None, *, secret: str, learner_id: str, mode: str
) -> _Cursor | None:
    if value is None:
        return None
    try:
        encoded, supplied = value.split(".", 1)
        expected = _sign(secret, "cursor", encoded)
        if not hmac.compare_digest(expected, supplied):
            raise ActivityCursorError("invalid_activity_cursor")
        payload = json.loads(_b64decode(encoded))
        if (
            not isinstance(payload, dict)
            or payload.get("v") != CURSOR_VERSION
            or payload.get("o") != _owner_digest(secret, learner_id)
            or payload.get("m") != mode
            or not isinstance(payload.get("t"), str)
            or not isinstance(payload.get("r"), int)
            or not isinstance(payload.get("i"), int)
            or payload["r"] not in {1, 2}
            or payload["i"] < 1
        ):
            raise ActivityCursorError("invalid_activity_cursor")
        return _Cursor(payload["t"], payload["r"], payload["i"])
    except ActivityCursorError:
        raise
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise ActivityCursorError("invalid_activity_cursor") from exc


def _json(value: Any, fallback: Any) -> Any:
    try:
        decoded = json.loads(value or "")
    except (TypeError, json.JSONDecodeError):
        return fallback
    return decoded


def _receipt_projection(
    row: sqlite3.Row,
) -> tuple[str | None, str | None, str, list[dict[str, str]]]:
    """Project every accepted competency without exposing an answer contract.

    One assessment remains one activity row. ``testedCompetencies`` preserves
    the grouped exact-skill evidence so a multi-domain Rapid read is not
    mislabeled as only whichever receipt happened to be serialized first.
    """

    def projected(
        values: list[Any], *, default_evidence: str, require_accepted: bool = False
    ) -> list[dict[str, str]]:
        results: list[dict[str, str]] = []
        seen: set[tuple[str, str, str]] = set()
        for value in values:
            if not isinstance(value, dict):
                continue
            if require_accepted and value.get("accepted") is not True:
                continue
            concept = _safe_token(value.get("concept"))
            subskill = _safe_token(value.get("subskill"))
            if not concept or not subskill:
                continue
            evidence = (
                "independent"
                if value.get("evidenceLevel") == "independent_transfer"
                else default_evidence
            )
            key = (concept, subskill, evidence)
            if key in seen:
                continue
            seen.add(key)
            results.append(
                {
                    "objectiveId": concept,
                    "subskill": subskill,
                    "evidence": evidence,
                }
            )
        return results

    mode = str(row["mode"])
    if mode == "training":
        if row["integrity_status"] not in {"atomic_v1", "atomic_v2"}:
            return None, None, "legacy_unverified", []
        envelope = _json(row["receipt_json"], {})
        receipts = envelope.get("receipts") if isinstance(envelope, dict) else None
        if not isinstance(receipts, list):
            return None, None, "legacy_unverified", []
        competencies = projected(receipts, default_evidence="formative")
        if not competencies:
            return None, None, "legacy_unverified", []
        primary = competencies[0]
        return primary["objectiveId"], primary["subskill"], primary["evidence"], competencies

    if mode == "rapid":
        if row["integrity_status"] not in {"atomic_v1", "atomic_v2"}:
            return None, None, "legacy_unverified", []
        receipts = _json(row["receipt_json"], [])
        if not isinstance(receipts, list):
            return None, None, "legacy_unverified", []
        competencies = projected(
            receipts,
            default_evidence="formative",
            require_accepted=True,
        )
        if not competencies:
            return None, None, "legacy_unverified", []
        primary = competencies[0]
        return primary["objectiveId"], primary["subskill"], primary["evidence"], competencies

    if mode == "clinical":
        if row["integrity_status"] != "atomic_v1":
            return None, None, "legacy_unverified", []
        receipts = _json(row["receipt_json"], [])
        competencies = (
            projected(receipts, default_evidence="formative")
            if isinstance(receipts, list)
            else []
        )
        if not competencies:
            return None, None, "formative", []
        primary = competencies[0]
        return primary["objectiveId"], primary["subskill"], "formative", competencies

    return None, None, "legacy_unverified", []


def _safe_token(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or len(value) > 120:
        return None
    return value if all(character.isalnum() or character in {"_", "-"} for character in value) else None


def _opaque_event_id(
    *, secret: str, learner_id: str, source: str, source_id: int, occurred_at: str
) -> str:
    material = f"{learner_id}:{source}:{source_id}:{occurred_at}"
    return f"evt_{_sign(secret, 'event', material)[:32]}"


def _project_row(row: sqlite3.Row, *, secret: str, learner_id: str) -> dict[str, Any]:
    source = str(row["source"])
    mode = str(row["mode"])
    score: float | None = float(row["score"]) if row["score"] is not None else None
    confidence = int(row["confidence"]) if row["confidence"] is not None else None
    assistance = str(row["assistance"] or "unknown")
    if assistance not in {"unassisted", "assisted", "unknown"}:
        assistance = "unknown"

    if source == "guided":
        objective = _safe_token(row["concept"])
        subskills = _json(row["subskills_json"], [])
        subskill = _safe_token(subskills[0]) if isinstance(subskills, list) and subskills else None
        level = str(row["evidence_level"] or "guided")
        evidence = "independent" if level == "independent_transfer" else "formative"
        tested_competencies = (
            [{"objectiveId": objective, "subskill": subskill, "evidence": evidence}]
            if objective and subskill
            else []
        )
        review_recommended = bool(row["correct"] == 0 or (score is not None and score < 0.7))
    else:
        objective, subskill, evidence, tested_competencies = _receipt_projection(row)
        if evidence == "legacy_unverified":
            score = None
        misconceptions = _json(row["misconceptions_json"], [])
        review_recommended = bool(
            evidence != "legacy_unverified"
            and ((score is not None and score < 0.7) or (isinstance(misconceptions, list) and misconceptions))
        )

    occurred_at = str(row["occurred_at"])
    source_id = int(row["source_id"])
    return {
        "id": _opaque_event_id(
            secret=secret,
            learner_id=learner_id,
            source=source,
            source_id=source_id,
            occurred_at=occurred_at,
        ),
        "mode": mode,
        "kind": "guided_task" if source == "guided" else "ecg_attempt",
        "occurredAt": occurred_at,
        "objectiveId": objective,
        "subskill": subskill,
        "testedCompetencies": tested_competencies,
        "score": None if score is None else round(max(0.0, min(score, 1.0)), 3),
        "confidence": confidence if confidence is None else max(1, min(confidence, 5)),
        "assistance": assistance,
        "evidence": evidence,
        "reviewRecommended": review_recommended,
    }


def get_learning_activity(
    conn: sqlite3.Connection,
    learner_id: str,
    *,
    secret: str,
    mode: str = "all",
    limit: int = 20,
    cursor: str | None = None,
) -> dict[str, Any]:
    """Return a stable, cursor-paginated safe history page for one owner."""

    if mode not in ACTIVITY_MODES:
        raise ValueError("invalid_activity_mode")
    page_size = max(1, min(int(limit), MAX_ACTIVITY_PAGE))
    decoded = _decode_cursor(
        cursor, secret=secret, learner_id=learner_id, mode=mode
    )
    params: list[Any] = [learner_id, learner_id]
    predicates: list[str] = []
    if mode != "all":
        predicates.append("mode = ?")
        params.append(mode)
    if decoded is not None:
        predicates.append(
            "(occurred_at < ? OR (occurred_at = ? AND "
            "(source_rank < ? OR (source_rank = ? AND source_id < ?))))"
        )
        params.extend(
            [
                decoded.occurred_at,
                decoded.occurred_at,
                decoded.source_rank,
                decoded.source_rank,
                decoded.source_id,
            ]
        )
    where = f"WHERE {' AND '.join(predicates)}" if predicates else ""
    params.append(page_size + 1)

    rows = conn.execute(
        f"""
        WITH activity AS (
            SELECT
                'attempt' AS source,
                2 AS source_rank,
                a.id AS source_id,
                CASE a.mode
                    WHEN 'concept_practice' THEN 'training'
                    WHEN 'rapid_practice' THEN 'rapid'
                    WHEN 'clinical_decision' THEN 'clinical'
                    ELSE NULL
                END AS mode,
                a.created_at AS occurred_at,
                a.score AS score,
                a.confidence AS confidence,
                CASE WHEN a.hints_used > 0 THEN 'assisted' ELSE 'unassisted' END AS assistance,
                NULL AS correct,
                NULL AS concept,
                NULL AS subskills_json,
                NULL AS evidence_level,
                a.misconception_tags_json AS misconceptions_json,
                COALESCE(ta.receipt_json, ra.receipts_json, ca.receipts_json) AS receipt_json,
                CASE
                    WHEN ta.id IS NOT NULL THEN ta.integrity_status
                    WHEN ra.id IS NOT NULL THEN ra.integrity_status
                    WHEN ca.id IS NOT NULL THEN 'atomic_v1'
                    ELSE 'legacy_incomplete'
                END AS integrity_status
            FROM attempts a
            LEFT JOIN training_campaign_answers ta ON ta.attempt_id = a.id
            LEFT JOIN rapid_round_answers ra ON ra.attempt_id = a.id
            LEFT JOIN clinical_shift_answers ca ON ca.attempt_id = a.id
            WHERE a.learner_id = ?
              AND a.mode IN ('concept_practice', 'rapid_practice', 'clinical_decision')

            UNION ALL

            SELECT
                'guided' AS source,
                1 AS source_rank,
                g.id AS source_id,
                'guided' AS mode,
                g.created_at AS occurred_at,
                g.score AS score,
                g.confidence AS confidence,
                CASE
                    WHEN g.assistance IN ('unassisted', 'assisted') THEN g.assistance
                    ELSE 'unknown'
                END AS assistance,
                g.correct AS correct,
                g.concept AS concept,
                g.subskills_json AS subskills_json,
                g.effective_evidence_level AS evidence_level,
                g.misconception_tags_json AS misconceptions_json,
                NULL AS receipt_json,
                'atomic_v1' AS integrity_status
            FROM guided_learning_events g
            WHERE g.learner_id = ?
              AND g.module_id NOT IN ('train', 'rapid', 'clinical')
        )
        SELECT * FROM activity
        {where}
        ORDER BY occurred_at DESC, source_rank DESC, source_id DESC
        LIMIT ?
        """,
        params,
    ).fetchall()
    has_more = len(rows) > page_size
    visible = rows[:page_size]
    items = [_project_row(row, secret=secret, learner_id=learner_id) for row in visible]
    next_cursor = None
    if has_more and visible:
        last = visible[-1]
        next_cursor = _encode_cursor(
            secret=secret,
            learner_id=learner_id,
            mode=mode,
            cursor=_Cursor(
                occurred_at=str(last["occurred_at"]),
                source_rank=int(last["source_rank"]),
                source_id=int(last["source_id"]),
            ),
        )
    return {
        "version": "learning-activity-v1",
        "items": items,
        "nextCursor": next_cursor,
        "hasMore": has_more,
    }
