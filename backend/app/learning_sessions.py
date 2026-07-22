"""Owner-bound, answer-free summaries and reviews of reviewable sessions.

This read model projects only aggregate outcomes and normalized learning
evidence already committed by the server-owned assessment lifecycles. Raw
responses, grades, answer manifests, ECG identifiers, and internal session ids
never cross this boundary.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import math
import re
import sqlite3
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs

from .objectives import objective_definition


SESSION_REF_VERSION = "learning-session-ref-v1"
MAX_SESSION_PAGE = 50
MAX_SESSION_OFFSET = 100_000
_FOCUS_TOKEN = re.compile(r"^[A-Za-z0-9_-]{1,120}$")

_COMPLETED_SESSIONS_CTE = """
WITH completed_sessions AS (
    SELECT
        'training' AS mode,
        1 AS mode_rank,
        campaigns.status AS session_status,
        campaigns.campaign_id AS session_id,
        campaigns.concept_id AS focus_objective,
        campaigns.subskill AS focus_subskill,
        campaigns.context_key AS focus_context,
        campaigns.length AS total,
        campaigns.created_at AS started_at,
        CASE
            WHEN campaigns.status = 'abandoned'
            THEN COALESCE(campaigns.abandoned_at, campaigns.updated_at)
            ELSE campaigns.updated_at
        END AS completed_at,
        (
            SELECT COUNT(*)
            FROM training_campaign_answers AS answers
            WHERE answers.campaign_id = campaigns.campaign_id
              AND answers.integrity_status IN ('atomic_v1', 'atomic_v2')
        ) AS attempted,
        NULL AS score,
        (
            SELECT COALESCE(SUM(
                CASE
                    WHEN json_valid(answers.summary_json)
                     AND json_type(answers.summary_json, '$.correct') = 'true'
                    THEN 1 ELSE 0
                END
            ), 0)
            FROM training_campaign_answers AS answers
            WHERE answers.campaign_id = campaigns.campaign_id
              AND answers.integrity_status IN ('atomic_v1', 'atomic_v2')
        ) AS correct_count,
        (
            SELECT COUNT(*)
            FROM learning_session_flags AS flags
            WHERE flags.owner_id = campaigns.learner_id
              AND flags.mode = 'training'
              AND flags.session_id = campaigns.campaign_id
              AND (
                  (
                      flags.source_answer_id IS NOT NULL
                      AND EXISTS (
                          SELECT 1
                          FROM training_campaign_answers AS flagged_answer
                          WHERE flagged_answer.campaign_id = campaigns.campaign_id
                            AND flagged_answer.id = flags.source_answer_id
                            AND flagged_answer.integrity_status
                                IN ('atomic_v1', 'atomic_v2')
                      )
                  )
                  OR (
                      flags.source_answer_id IS NULL
                      AND flags.attempt_index BETWEEN 1 AND (
                          SELECT COUNT(*)
                          FROM training_campaign_answers AS valid_answers
                          WHERE valid_answers.campaign_id = campaigns.campaign_id
                            AND valid_answers.integrity_status
                                IN ('atomic_v1', 'atomic_v2')
                      )
                  )
              )
        ) AS flagged_count
    FROM training_campaigns AS campaigns
    WHERE campaigns.learner_id = ?
      AND campaigns.status IN ('complete', 'abandoned')
      AND EXISTS (
          SELECT 1
          FROM training_campaign_answers AS reviewable_answer
          WHERE reviewable_answer.campaign_id = campaigns.campaign_id
            AND reviewable_answer.integrity_status IN ('atomic_v1', 'atomic_v2')
      )

    UNION ALL

    SELECT
        'rapid' AS mode,
        2 AS mode_rank,
        rounds.status AS session_status,
        rounds.round_id AS session_id,
        rounds.focus_concept AS focus_objective,
        rounds.focus_subskill AS focus_subskill,
        NULL AS focus_context,
        rounds.length AS total,
        rounds.created_at AS started_at,
        rounds.updated_at AS completed_at,
        (
            SELECT COUNT(*)
            FROM rapid_round_answers AS answers
            WHERE answers.round_id = rounds.round_id
              AND answers.integrity_status IN ('atomic_v1', 'atomic_v2')
        ) AS attempted,
        (
            SELECT AVG(
                CASE
                    WHEN json_valid(answers.result_json)
                     AND json_type(answers.result_json, '$.score') IN ('integer', 'real')
                     AND json_extract(answers.result_json, '$.score') BETWEEN 0.0 AND 1.0
                    THEN json_extract(answers.result_json, '$.score')
                    ELSE NULL
                END
            )
            FROM rapid_round_answers AS answers
            WHERE answers.round_id = rounds.round_id
              AND answers.integrity_status IN ('atomic_v1', 'atomic_v2')
        ) AS score,
        NULL AS correct_count,
        (
            SELECT COUNT(*)
            FROM learning_session_flags AS flags
            WHERE flags.owner_id = rounds.learner_id
              AND flags.mode = 'rapid'
              AND flags.session_id = rounds.round_id
              AND (
                  (
                      flags.source_answer_id IS NOT NULL
                      AND EXISTS (
                          SELECT 1
                          FROM rapid_round_answers AS flagged_answer
                          WHERE flagged_answer.round_id = rounds.round_id
                            AND flagged_answer.id = flags.source_answer_id
                            AND flagged_answer.integrity_status
                                IN ('atomic_v1', 'atomic_v2')
                      )
                  )
                  OR (
                      flags.source_answer_id IS NULL
                      AND flags.attempt_index BETWEEN 1 AND (
                          SELECT COUNT(*)
                          FROM rapid_round_answers AS valid_answers
                          WHERE valid_answers.round_id = rounds.round_id
                            AND valid_answers.integrity_status
                                IN ('atomic_v1', 'atomic_v2')
                      )
                  )
              )
        ) AS flagged_count
    FROM rapid_rounds AS rounds
    WHERE rounds.learner_id = ?
      AND rounds.status IN ('complete', 'abandoned')

    UNION ALL

    SELECT
        'clinical' AS mode,
        3 AS mode_rank,
        sessions.status AS session_status,
        sessions.session_id AS session_id,
        sessions.focus_objective AS focus_objective,
        sessions.focus_subskill AS focus_subskill,
        NULL AS focus_context,
        sessions.length AS total,
        sessions.created_at AS started_at,
        sessions.updated_at AS completed_at,
        (
            SELECT COUNT(*)
            FROM clinical_shift_answers AS answers
            WHERE answers.session_id = sessions.session_id
        ) AS attempted,
        (
            SELECT AVG(answers.score)
            FROM clinical_shift_answers AS answers
            WHERE answers.session_id = sessions.session_id
              AND answers.score BETWEEN 0.0 AND 1.0
        ) AS score,
        (
            SELECT COALESCE(SUM(CASE WHEN answers.correct = 1 THEN 1 ELSE 0 END), 0)
            FROM clinical_shift_answers AS answers
            WHERE answers.session_id = sessions.session_id
        ) AS correct_count,
        (
            SELECT COUNT(*)
            FROM learning_session_flags AS flags
            WHERE flags.owner_id = sessions.learner_id
              AND flags.mode = 'clinical'
              AND flags.session_id = sessions.session_id
              AND (
                  (
                      flags.source_answer_id IS NOT NULL
                      AND EXISTS (
                          SELECT 1
                          FROM clinical_shift_answers AS flagged_answer
                          WHERE flagged_answer.session_id = sessions.session_id
                            AND flagged_answer.id = flags.source_answer_id
                      )
                  )
                  OR (
                      flags.source_answer_id IS NULL
                      AND flags.attempt_index BETWEEN 1 AND (
                          SELECT COUNT(*)
                          FROM clinical_shift_answers AS valid_answers
                          WHERE valid_answers.session_id = sessions.session_id
                      )
                  )
              )
        ) AS flagged_count
    FROM clinical_shift_sessions AS sessions
    WHERE sessions.learner_id = ? AND sessions.status = 'complete'
)
"""


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def issue_learning_session_ref(
    *, secret: str, learner_id: str, mode: str, session_id: str
) -> str:
    """Return a deterministic opaque signature for one owner/session tuple."""

    material = "\0".join(
        (SESSION_REF_VERSION, learner_id, mode, session_id)
    ).encode("utf-8")
    digest = hmac.new(
        secret.encode("utf-8"),
        b"ecg-tool\0learning-session-ref\0" + material,
        hashlib.sha256,
    ).digest()
    return f"lsr1_{_b64encode(digest)}"


def _focus_competencies(
    objective: object, subskill: object
) -> list[dict[str, str]]:
    if not isinstance(objective, str) or not isinstance(subskill, str):
        return []
    if not _FOCUS_TOKEN.fullmatch(objective) or not _FOCUS_TOKEN.fullmatch(subskill):
        return []
    return [
        {
            "objectiveId": objective,
            "subskill": subskill,
            "mappingSource": "session_focus",
        }
    ]


def _session_focus_competencies(row: sqlite3.Row) -> list[dict[str, str]]:
    """Return the requested objective, not only its grounded ECG case family."""

    objective = row["focus_objective"]
    subskill = row["focus_subskill"]
    if str(row["mode"]) == "training" and isinstance(objective, str) and isinstance(subskill, str):
        values = parse_qs(str(row["focus_context"] or ""), keep_blank_values=False)
        requested = str((values.get("receiptConcept") or [objective])[0]).strip()
        definition = objective_definition(requested)
        if (
            definition is not None
            and subskill in definition.allowed_subskills
            and objective in definition.case_concepts
        ):
            objective = requested
    return _focus_competencies(objective, subskill)


def _bounded_score(value: object) -> float | None:
    if value is None:
        return None
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(score) or score < 0.0 or score > 1.0:
        return None
    return round(score, 3)


def _bounded_confidence(value: object) -> int | None:
    try:
        confidence = int(value)
    except (TypeError, ValueError):
        return None
    return confidence if 1 <= confidence <= 5 else None


def _assistance(value: object) -> dict[str, int] | None:
    try:
        hints_used = int(value)
    except (TypeError, ValueError):
        return None
    if hints_used < 0:
        return None
    return {"hintsUsed": min(hints_used, 1000)}


def _completed_session_rows(
    conn: sqlite3.Connection,
    learner_id: str,
    *,
    limit: int | None = None,
    offset: int = 0,
    saved_only: bool = False,
) -> list[sqlite3.Row]:
    sql = (
        _COMPLETED_SESSIONS_CTE
        + "SELECT * FROM completed_sessions WHERE attempted > 0 "
        + ("AND flagged_count > 0 " if saved_only else "")
        + "ORDER BY completed_at DESC, mode_rank DESC, session_id DESC"
    )
    params: list[object] = [learner_id, learner_id, learner_id]
    if limit is not None:
        sql += " LIMIT ?"
        params.append(max(1, min(int(limit), MAX_SESSION_PAGE + 1)))
        if offset:
            sql += " OFFSET ?"
            params.append(max(0, min(int(offset), MAX_SESSION_OFFSET)))
    return conn.execute(sql, params).fetchall()


def _total_saved_items(conn: sqlite3.Connection, learner_id: str) -> int:
    row = conn.execute(
        _COMPLETED_SESSIONS_CTE
        + "SELECT COALESCE(SUM(flagged_count), 0) FROM completed_sessions",
        (learner_id, learner_id, learner_id),
    ).fetchone()
    return max(0, int(row[0] or 0))


def _summary_item(
    row: sqlite3.Row, *, learner_id: str, secret: str
) -> dict[str, Any]:
    mode = str(row["mode"])
    raw_status = str(row["session_status"])
    session_status = (
        "abandoned"
        if mode in {"rapid", "training"} and raw_status == "abandoned"
        else "complete"
    )
    attempted = max(0, int(row["attempted"] or 0))
    correct_count = (
        max(0, int(row["correct_count"]))
        if row["correct_count"] is not None
        else None
    )
    return {
        "sessionRef": issue_learning_session_ref(
            secret=secret,
            learner_id=learner_id,
            mode=mode,
            session_id=str(row["session_id"]),
        ),
        "mode": mode,
        "status": session_status,
        "attempted": attempted,
        "total": max(0, int(row["total"] or 0)),
        "score": _bounded_score(row["score"]),
        "correctCount": correct_count,
        "flaggedCount": max(0, int(row["flagged_count"] or 0)),
        "focusCompetencies": _session_focus_competencies(row),
        "startedAt": str(row["started_at"]),
        "completedAt": str(row["completed_at"]),
        "reviewAvailable": attempted > 0,
    }


def _resolve_completed_session(
    conn: sqlite3.Connection,
    learner_id: str,
    *,
    secret: str,
    session_ref: str,
) -> sqlite3.Row | None:
    """Resolve only against this owner's reviewable rows without early exit."""

    supplied = session_ref.encode("utf-8")
    matched: sqlite3.Row | None = None
    for row in _completed_session_rows(conn, learner_id):
        candidate = issue_learning_session_ref(
            secret=secret,
            learner_id=learner_id,
            mode=str(row["mode"]),
            session_id=str(row["session_id"]),
        ).encode("ascii")
        if hmac.compare_digest(supplied, candidate):
            matched = row
    return matched


def _competencies_for_event(
    conn: sqlite3.Connection,
    *,
    learner_id: str,
    mode: str,
    session_id: str,
    event_id: str,
    fallback: list[dict[str, str]],
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT competencies.competency_id, competencies.competency_score
        FROM learner_event_competencies AS competencies
        JOIN learner_events AS events ON events.event_id = competencies.event_id
        WHERE events.event_id = ? AND events.owner_id = ?
          AND events.mode = ? AND events.session_id = ?
          AND events.event_type = 'answer_committed'
          AND events.integrity_status IN ('atomic_v1', 'atomic_v2')
        ORDER BY competencies.competency_id
        """,
        (event_id, learner_id, mode, session_id),
    ).fetchall()
    projected: list[dict[str, Any]] = []
    for row in rows:
        objective, separator, subskill = str(row["competency_id"]).rpartition(":")
        if (
            not separator
            or not _FOCUS_TOKEN.fullmatch(objective)
            or not _FOCUS_TOKEN.fullmatch(subskill)
        ):
            continue
        projected.append(
            {
                "objectiveId": objective,
                "subskill": subskill,
                "score": _bounded_score(row["competency_score"]),
                "mappingSource": "committed_event",
            }
        )
    if projected:
        return projected
    # The session focus is routing metadata, not item-level competency
    # evidence. Preserve that label without inferring mastery from the answer.
    return [{**competency, "score": None} for competency in fallback]


def _flagged_attempt_keys(
    conn: sqlite3.Connection,
    *,
    learner_id: str,
    mode: str,
    session_id: str,
) -> tuple[set[int], set[int]]:
    rows = conn.execute(
        "SELECT attempt_index, source_answer_id FROM learning_session_flags "
        "WHERE owner_id = ? AND mode = ? AND session_id = ?",
        (learner_id, mode, session_id),
    ).fetchall()
    return (
        {
            int(row["source_answer_id"])
            for row in rows
            if row["source_answer_id"] is not None
        },
        {
            int(row["attempt_index"])
            for row in rows
            if row["source_answer_id"] is None
        },
    )


def _attempt_source_answer_ids(
    conn: sqlite3.Connection, *, mode: str, session_id: str
) -> list[int]:
    if mode == "training":
        sql = (
            "SELECT id FROM training_campaign_answers "
            "WHERE campaign_id = ? "
            "AND integrity_status IN ('atomic_v1', 'atomic_v2') "
            "ORDER BY ordinal, id"
        )
    elif mode == "rapid":
        sql = (
            "SELECT id FROM rapid_round_answers WHERE round_id = ? "
            "AND integrity_status IN ('atomic_v1', 'atomic_v2') ORDER BY id"
        )
    elif mode == "clinical":
        sql = "SELECT id FROM clinical_shift_answers WHERE session_id = ? ORDER BY id"
    else:
        return []
    return [
        int(row["id"])
        for row in conn.execute(sql, (session_id,)).fetchall()
    ]


def _attempt_is_flagged(
    *,
    source_answer_id: int,
    attempt_index: int,
    stable_answer_ids: set[int],
    legacy_attempt_indices: set[int],
) -> bool:
    return (
        source_answer_id in stable_answer_ids
        or attempt_index in legacy_attempt_indices
    )


def _review_attempt(
    conn: sqlite3.Connection,
    *,
    index: int,
    learner_id: str,
    mode: str,
    session_id: str,
    event_id: str,
    score: object,
    confidence: object,
    hints_used: object,
    fallback_competencies: list[dict[str, str]],
    flagged: bool,
) -> dict[str, Any]:
    bounded_score = _bounded_score(score)
    return {
        "index": index,
        "score": bounded_score,
        "competencies": _competencies_for_event(
            conn,
            learner_id=learner_id,
            mode=mode,
            session_id=session_id,
            event_id=event_id,
            fallback=fallback_competencies,
        ),
        "confidence": _bounded_confidence(confidence),
        "assistance": _assistance(hints_used),
        "flagged": flagged,
    }


def _training_attempts(
    conn: sqlite3.Connection, learner_id: str, row: sqlite3.Row
) -> list[dict[str, Any]]:
    session_id = str(row["session_id"])
    rows = conn.execute(
        """
        SELECT answers.id AS source_answer_id,
               answers.ordinal, answers.case_id,
               attempts.score AS attempt_score,
               attempts.confidence, attempts.hints_used,
               CASE
                   WHEN json_valid(answers.summary_json)
                    AND json_type(answers.summary_json, '$.correct') = 'true'
                   THEN 1.0
                   WHEN json_valid(answers.summary_json)
                    AND json_type(answers.summary_json, '$.correct') = 'false'
                   THEN 0.0
                   ELSE NULL
               END AS summary_score
        FROM training_campaign_answers AS answers
        LEFT JOIN attempts ON attempts.id = answers.attempt_id
          AND attempts.learner_id = ?
        WHERE answers.campaign_id = ?
          AND answers.integrity_status IN ('atomic_v1', 'atomic_v2')
        ORDER BY answers.ordinal, answers.id
        """,
        (learner_id, session_id),
    ).fetchall()
    fallback = _session_focus_competencies(row)
    stable_answer_ids, legacy_attempt_indices = _flagged_attempt_keys(
        conn,
        learner_id=learner_id,
        mode="training",
        session_id=session_id,
    )
    attempts: list[dict[str, Any]] = []
    for index, answer in enumerate(rows, start=1):
        # Focused Practice stores the selected-skill result in the authoritative
        # campaign summary. The generic attempt score is a legacy pattern
        # classification grade and can legitimately disagree with that skill.
        score = (
            answer["summary_score"]
            if answer["summary_score"] is not None
            else answer["attempt_score"]
        )
        attempts.append(
            _review_attempt(
                conn,
                index=index,
                learner_id=learner_id,
                mode="training",
                session_id=session_id,
                event_id=(
                    f"training-answer:{session_id}:{int(answer['ordinal'])}:"
                    f"{answer['case_id']}"
                ),
                score=score,
                confidence=answer["confidence"],
                hints_used=answer["hints_used"],
                fallback_competencies=fallback,
                flagged=_attempt_is_flagged(
                    source_answer_id=int(answer["source_answer_id"]),
                    attempt_index=index,
                    stable_answer_ids=stable_answer_ids,
                    legacy_attempt_indices=legacy_attempt_indices,
                ),
            )
        )
    return attempts


def _rapid_attempts(
    conn: sqlite3.Connection, learner_id: str, row: sqlite3.Row
) -> list[dict[str, Any]]:
    session_id = str(row["session_id"])
    rows = conn.execute(
        """
        SELECT answers.id AS source_answer_id,
               answers.case_id,
               (
                   SELECT COUNT(*)
                   FROM rapid_round_answers AS prior_answers
                   WHERE prior_answers.round_id = answers.round_id
                     AND prior_answers.id < answers.id
               ) AS event_position,
               attempts.score AS attempt_score,
               attempts.confidence, attempts.hints_used,
               CASE
                   WHEN json_valid(answers.result_json)
                    AND json_type(answers.result_json, '$.score') IN ('integer', 'real')
                    AND json_extract(answers.result_json, '$.score') BETWEEN 0.0 AND 1.0
                   THEN json_extract(answers.result_json, '$.score')
                   ELSE NULL
               END AS result_score
        FROM rapid_round_answers AS answers
        LEFT JOIN attempts ON attempts.id = answers.attempt_id
          AND attempts.learner_id = ?
        WHERE answers.round_id = ?
          AND answers.integrity_status IN ('atomic_v1', 'atomic_v2')
        ORDER BY answers.id
        """,
        (learner_id, session_id),
    ).fetchall()
    fallback = _focus_competencies(row["focus_objective"], row["focus_subskill"])
    stable_answer_ids, legacy_attempt_indices = _flagged_attempt_keys(
        conn,
        learner_id=learner_id,
        mode="rapid",
        session_id=session_id,
    )
    attempts: list[dict[str, Any]] = []
    for index, answer in enumerate(rows, start=1):
        score = (
            answer["result_score"]
            if answer["result_score"] is not None
            else answer["attempt_score"]
        )
        attempts.append(
            _review_attempt(
                conn,
                index=index,
                learner_id=learner_id,
                mode="rapid",
                session_id=session_id,
                event_id=(
                    f"rapid-answer:{session_id}:{int(answer['event_position'])}:"
                    f"{answer['case_id']}"
                ),
                score=score,
                confidence=answer["confidence"],
                hints_used=answer["hints_used"],
                fallback_competencies=fallback,
                flagged=_attempt_is_flagged(
                    source_answer_id=int(answer["source_answer_id"]),
                    attempt_index=index,
                    stable_answer_ids=stable_answer_ids,
                    legacy_attempt_indices=legacy_attempt_indices,
                ),
            )
        )
    return attempts


def _clinical_attempts(
    conn: sqlite3.Connection, learner_id: str, row: sqlite3.Row
) -> list[dict[str, Any]]:
    session_id = str(row["session_id"])
    rows = conn.execute(
        """
        SELECT answers.id AS source_answer_id,
               answers.item_id, answers.score,
               attempts.hints_used
        FROM clinical_shift_answers AS answers
        LEFT JOIN attempts ON attempts.id = answers.attempt_id
          AND attempts.learner_id = ?
        WHERE answers.session_id = ?
        ORDER BY answers.id
        """,
        (learner_id, session_id),
    ).fetchall()
    fallback = _focus_competencies(row["focus_objective"], row["focus_subskill"])
    stable_answer_ids, legacy_attempt_indices = _flagged_attempt_keys(
        conn,
        learner_id=learner_id,
        mode="clinical",
        session_id=session_id,
    )
    return [
        _review_attempt(
            conn,
            index=index,
            learner_id=learner_id,
            mode="clinical",
            session_id=session_id,
            event_id=f"clinical-answer:{session_id}:{answer['item_id']}",
            score=answer["score"],
            # Confidence controls were intentionally removed from Clinical
            # Cases.  Historical rows may still carry a legacy value in the
            # shared attempts table, but that value is not part of the current
            # learner-facing Clinical review contract.
            confidence=None,
            hints_used=answer["hints_used"],
            fallback_competencies=fallback,
            flagged=_attempt_is_flagged(
                source_answer_id=int(answer["source_answer_id"]),
                attempt_index=index,
                stable_answer_ids=stable_answer_ids,
                legacy_attempt_indices=legacy_attempt_indices,
            ),
        )
        for index, answer in enumerate(rows, start=1)
    ]


def get_learning_sessions(
    conn: sqlite3.Connection,
    learner_id: str,
    *,
    secret: str,
    limit: int = 10,
    offset: int = 0,
    saved_only: bool = False,
) -> dict[str, Any]:
    """Return a durable page of completed, answer-free session summaries."""

    bounded_limit = max(1, min(int(limit), MAX_SESSION_PAGE))
    bounded_offset = max(0, min(int(offset), MAX_SESSION_OFFSET))
    rows = _completed_session_rows(
        conn,
        learner_id,
        limit=bounded_limit + 1,
        offset=bounded_offset,
        saved_only=bool(saved_only),
    )
    has_more = len(rows) > bounded_limit
    page = rows[:bounded_limit]
    return {
        "version": "learning-sessions-v1",
        "items": [
            _summary_item(row, learner_id=learner_id, secret=secret)
            for row in page
        ],
        "hasMore": has_more,
        "nextOffset": bounded_offset + len(page) if has_more else None,
        "totalSavedItems": _total_saved_items(conn, learner_id),
    }


def get_learning_session_review(
    conn: sqlite3.Connection,
    learner_id: str,
    *,
    secret: str,
    session_ref: str,
) -> dict[str, Any] | None:
    """Resolve an opaque owner/session reference to a safe postcommit review."""

    row = _resolve_completed_session(
        conn,
        learner_id,
        secret=secret,
        session_ref=session_ref,
    )
    if row is None:
        return None
    mode = str(row["mode"])
    if mode == "training":
        attempts = _training_attempts(conn, learner_id, row)
    elif mode == "rapid":
        attempts = _rapid_attempts(conn, learner_id, row)
    else:
        attempts = _clinical_attempts(conn, learner_id, row)
    return {
        "version": "learning-session-review-v1",
        "session": _summary_item(row, learner_id=learner_id, secret=secret),
        "attempts": attempts,
    }


def set_learning_session_attempt_flag(
    conn: sqlite3.Connection,
    learner_id: str,
    *,
    secret: str,
    session_ref: str,
    attempt_index: int,
    flagged: bool,
) -> dict[str, Any] | None:
    """Idempotently update one submitted item without exposing its private key."""

    row = _resolve_completed_session(
        conn,
        learner_id,
        secret=secret,
        session_ref=session_ref,
    )
    if row is None:
        return None
    bounded_index = int(attempt_index)
    mode = str(row["mode"])
    private_session_id = str(row["session_id"])
    source_answer_ids = _attempt_source_answer_ids(
        conn,
        mode=mode,
        session_id=private_session_id,
    )
    if bounded_index < 1 or bounded_index > len(source_answer_ids):
        return None
    source_answer_id = source_answer_ids[bounded_index - 1]

    if flagged:
        now = datetime.now(UTC).isoformat()
        # Upgrade a resolvable legacy row in place before attempting an insert.
        # OR IGNORE preserves an ambiguous NULL row if another stable flag
        # already owns this answer identity.
        conn.execute(
            "UPDATE OR IGNORE learning_session_flags SET "
            "source_answer_id = ?, updated_at = ? "
            "WHERE owner_id = ? AND mode = ? AND session_id = ? "
            "AND attempt_index = ? AND source_answer_id IS NULL",
            (
                source_answer_id,
                now,
                learner_id,
                mode,
                private_session_id,
                bounded_index,
            ),
        )
        conn.execute(
            "INSERT OR IGNORE INTO learning_session_flags ("
            "owner_id, mode, session_id, attempt_index, source_answer_id, "
            "created_at, updated_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                learner_id,
                mode,
                private_session_id,
                bounded_index,
                source_answer_id,
                now,
                now,
            ),
        )
        # A stable flag can move to this public ordinal after an earlier answer
        # is quarantined. If a legacy NULL row also occupies that ordinal, the
        # explicit save confirms both rows refer to the same currently visible
        # item; keep the stable identity and remove only that redundant legacy
        # projection so aggregate counts cannot double-count it.
        conn.execute(
            "DELETE FROM learning_session_flags "
            "WHERE owner_id = ? AND mode = ? AND session_id = ? "
            "AND attempt_index = ? AND source_answer_id IS NULL "
            "AND EXISTS ("
            "SELECT 1 FROM learning_session_flags AS stable_flag "
            "WHERE stable_flag.owner_id = ? AND stable_flag.mode = ? "
            "AND stable_flag.session_id = ? "
            "AND stable_flag.source_answer_id = ?)",
            (
                learner_id,
                mode,
                private_session_id,
                bounded_index,
                learner_id,
                mode,
                private_session_id,
                source_answer_id,
            ),
        )
    else:
        conn.execute(
            "DELETE FROM learning_session_flags "
            "WHERE owner_id = ? AND mode = ? AND session_id = ? "
            "AND ((source_answer_id IS NOT NULL AND source_answer_id = ?) "
            "OR (source_answer_id IS NULL AND attempt_index = ?))",
            (
                learner_id,
                mode,
                private_session_id,
                source_answer_id,
                bounded_index,
            ),
        )
    stable_answer_ids, legacy_attempt_indices = _flagged_attempt_keys(
        conn,
        learner_id=learner_id,
        mode=mode,
        session_id=private_session_id,
    )
    effective_flags = [
        _attempt_is_flagged(
            source_answer_id=current_source_answer_id,
            attempt_index=index,
            stable_answer_ids=stable_answer_ids,
            legacy_attempt_indices=legacy_attempt_indices,
        )
        for index, current_source_answer_id in enumerate(source_answer_ids, start=1)
    ]
    flagged_count = sum(effective_flags)
    effective_flagged = effective_flags[bounded_index - 1]
    return {
        "sessionRef": session_ref,
        "attemptIndex": bounded_index,
        "flagged": effective_flagged,
        "flaggedCount": flagged_count,
    }


__all__ = [
    "MAX_SESSION_OFFSET",
    "MAX_SESSION_PAGE",
    "SESSION_REF_VERSION",
    "get_learning_session_review",
    "get_learning_sessions",
    "issue_learning_session_ref",
    "set_learning_session_attempt_flag",
]
