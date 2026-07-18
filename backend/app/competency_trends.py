"""Owner-bound performance timelines for one exact competency.

The competency ledger records observations, not historical mastery snapshots.
This read model therefore exposes only the scored evidence that was committed at
the time of each learning event.  It intentionally omits event, session, lease,
and ECG identifiers.
"""

from __future__ import annotations

import sqlite3
from typing import Any


MAX_COMPETENCY_TREND_POINTS = 50


def get_competency_trend(
    conn: sqlite3.Connection,
    *,
    learner_id: str,
    objective_id: str,
    subskill: str,
    limit: int = 20,
) -> dict[str, Any]:
    """Return chronological, answer-free observations for one competency."""

    bounded_limit = max(1, min(int(limit), MAX_COMPETENCY_TREND_POINTS))
    competency_id = f"{objective_id}:{subskill}"
    rows = conn.execute(
        """
        SELECT recent.mode, recent.event_type, recent.evidence_level,
               recent.integrity_status, recent.occurred_at,
               recent.competency_score
        FROM (
            SELECT events.event_id AS sort_event_id,
                   events.mode, events.event_type, events.evidence_level,
                   events.integrity_status, events.occurred_at,
                   competencies.competency_score
            FROM learner_event_competencies AS competencies
            JOIN learner_events AS events ON events.event_id = competencies.event_id
            WHERE events.owner_id = ?
              AND competencies.competency_id = ?
              AND events.event_type IN ('interaction_committed', 'answer_committed')
              AND events.integrity_status IN ('atomic_v2', 'backfilled_v1')
            ORDER BY events.occurred_at DESC, events.event_id DESC
            LIMIT ?
        ) AS recent
        ORDER BY recent.occurred_at ASC, recent.sort_event_id ASC
        """,
        (learner_id, competency_id, bounded_limit + 1),
    ).fetchall()

    has_more = len(rows) > bounded_limit
    rows = rows[-bounded_limit:]

    points = [
        {
            "occurredAt": str(row["occurred_at"]),
            "score": round(float(row["competency_score"]), 3),
            "mode": str(row["mode"]),
            "evidenceLevel": str(row["evidence_level"]),
            "independent": row["evidence_level"] == "independent_transfer",
            "recordStatus": (
                "verified" if row["integrity_status"] == "atomic_v2" else "legacy"
            ),
        }
        for row in rows
    ]
    return {
        "version": "competency-trend-v1",
        "objectiveId": objective_id,
        "subskill": subskill,
        "points": points,
        "pointCount": len(points),
        "hasMore": has_more,
        "interpretation": (
            "Scored evidence over time; this is not a historical mastery estimate."
        ),
    }


__all__ = ["MAX_COMPETENCY_TREND_POINTS", "get_competency_trend"]
