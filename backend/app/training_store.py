"""Durable, server-owned Training campaign ledger.

Each owner has at most one resumable campaign. Creation freezes a unique roster
of audited real ECGs, preferring cases outside the owner's latest 5,000 exact
independent Training attempts while preserving the canonical role/phase recipe.
After a committed response, only the still-unseen roster order may change so the
next case can remediate a miss or add an appropriate contrast. Answered/pending
rows never move and no new case can enter the roster, preserving resumability
and the within-campaign no-repeat guarantee at 5,000-case scale.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from collections import Counter, deque
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, ContextManager

from .account_boundary import (
    configure_account_boundary,
    ensure_account_boundary_schema,
    translate_account_boundary_error,
)
from .assessment_ledger import (
    LeaseNotFoundError,
    LeaseStateError,
    append_event,
    claim_submission,
    create_lease,
    ensure_schema as ensure_assessment_schema,
    mark_submitted,
    owner_exposure_ids,
    release_submission,
    terminal_event_id,
    terminalize_lease,
)
from .objectives import REGISTRY_VERSION


RECENT_INDEPENDENT_ECG_LIMIT = 5000
TRAINING_LEASE_TTL = timedelta(days=30)


class TrainingExposureConflictError(RuntimeError):
    """The requested exact roster cannot avoid another live assessment."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _utc(value: str) -> datetime:
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(candidate)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Training timestamps must include a UTC offset")
    return parsed.astimezone(UTC)


class TrainingCampaignStore:
    def __init__(
        self,
        db_path: Path | str,
        connection_provider: Callable[[], ContextManager[sqlite3.Connection]] | None = None,
    ):
        self.db_path = str(db_path)
        self._connection_provider = connection_provider
        self._lock = threading.Lock()
        self._memory_conn = (
            sqlite3.connect(":memory:", check_same_thread=False)
            if self.db_path == ":memory:" and connection_provider is None
            else None
        )
        if self._memory_conn is not None:
            self._memory_conn.row_factory = sqlite3.Row
            self._memory_conn.execute("PRAGMA foreign_keys=ON")
            configure_account_boundary(self._memory_conn)
        self.init_db()

    @contextmanager
    def connect(self):
        if self._connection_provider is not None:
            with self._connection_provider() as conn:
                yield conn
            return
        if self._memory_conn is not None:
            with self._lock:
                try:
                    yield self._memory_conn
                    self._memory_conn.commit()
                except sqlite3.IntegrityError as exc:
                    self._memory_conn.rollback()
                    translated = translate_account_boundary_error(exc)
                    if translated is exc:
                        raise
                    raise translated from None
                except Exception:
                    self._memory_conn.rollback()
                    raise
            return
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        configure_account_boundary(conn)
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
        except sqlite3.OperationalError:
            pass
        try:
            yield conn
            conn.commit()
        except sqlite3.IntegrityError as exc:
            conn.rollback()
            translated = translate_account_boundary_error(exc)
            if translated is exc:
                raise
            raise translated from None
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS training_campaigns (
                    campaign_id TEXT PRIMARY KEY,
                    learner_id TEXT NOT NULL,
                    concept_id TEXT NOT NULL,
                    subskill TEXT NOT NULL,
                    requested_length INTEGER NOT NULL,
                    length INTEGER NOT NULL,
                    pool_count INTEGER NOT NULL,
                    phases_json TEXT NOT NULL,
                    phase_counts_json TEXT NOT NULL,
                    position INTEGER NOT NULL DEFAULT 0,
                    pending_case_id TEXT,
                    feedback_case_id TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    context_key TEXT NOT NULL DEFAULT '',
                    roster_policy_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    abandoned_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_training_campaign_active
                    ON training_campaigns(learner_id, status, updated_at);

                CREATE TABLE IF NOT EXISTS training_campaign_slots (
                    campaign_id TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,
                    phase TEXT NOT NULL,
                    case_id TEXT NOT NULL,
                    case_focus TEXT NOT NULL,
                    target_present INTEGER NOT NULL,
                    selection_reason TEXT NOT NULL DEFAULT 'planned_sequence',
                    status TEXT NOT NULL DEFAULT 'queued',
                    served_at TEXT,
                    answered_at TEXT,
                    PRIMARY KEY (campaign_id, ordinal),
                    UNIQUE (campaign_id, case_id),
                    FOREIGN KEY (campaign_id) REFERENCES training_campaigns(campaign_id)
                );
                CREATE INDEX IF NOT EXISTS idx_training_slot_case
                    ON training_campaign_slots(campaign_id, case_id);
                CREATE INDEX IF NOT EXISTS idx_training_slot_adaptive
                    ON training_campaign_slots(
                        campaign_id, status, target_present, phase, ordinal
                    );

                CREATE TABLE IF NOT EXISTS training_campaign_answers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    campaign_id TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,
                    case_id TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    grade_json TEXT NOT NULL,
                    tutor_json TEXT NOT NULL,
                    receipt_json TEXT NOT NULL,
                    summary_json TEXT NOT NULL,
                    integrity_status TEXT NOT NULL DEFAULT 'legacy_two_phase',
                    attempt_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE (campaign_id, ordinal),
                    UNIQUE (campaign_id, case_id),
                    FOREIGN KEY (campaign_id) REFERENCES training_campaigns(campaign_id)
                );
                CREATE INDEX IF NOT EXISTS idx_training_answer_campaign
                    ON training_campaign_answers(campaign_id, ordinal);
                CREATE INDEX IF NOT EXISTS idx_training_answer_attempt
                    ON training_campaign_answers(attempt_id);
                """
            )
            slot_columns = {
                str(row["name"])
                for row in conn.execute("PRAGMA table_info(training_campaign_slots)").fetchall()
            }
            if "selection_reason" not in slot_columns:
                conn.execute(
                    "ALTER TABLE training_campaign_slots "
                    "ADD COLUMN selection_reason TEXT NOT NULL DEFAULT 'planned_sequence'"
                )
            campaign_columns = {
                str(row["name"])
                for row in conn.execute("PRAGMA table_info(training_campaigns)").fetchall()
            }
            if "roster_policy_json" not in campaign_columns:
                conn.execute(
                    "ALTER TABLE training_campaigns "
                    "ADD COLUMN roster_policy_json TEXT NOT NULL DEFAULT '{}'"
                )
            answer_columns = {
                str(row["name"])
                for row in conn.execute("PRAGMA table_info(training_campaign_answers)").fetchall()
            }
            if "integrity_status" not in answer_columns:
                conn.execute(
                    "ALTER TABLE training_campaign_answers "
                    "ADD COLUMN integrity_status TEXT NOT NULL DEFAULT 'legacy_two_phase'"
                )
            ensure_assessment_schema(conn)
            ensure_account_boundary_schema(conn)
            self._repair_duplicate_current_campaigns(conn)
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_training_campaign_current_learner "
                "ON training_campaigns(learner_id) "
                "WHERE status = 'active' OR feedback_case_id IS NOT NULL"
            )
            if self._table_exists(conn, "guided_learning_events"):
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_training_recent_independent_case "
                    "ON guided_learning_events("
                    "learner_id, module_id, effective_evidence_level, created_at DESC, case_id"
                    ")"
                )
            self._backfill_pending_leases(conn, now=_now())

    @staticmethod
    def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
        return conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table_name,)
        ).fetchone() is not None

    @staticmethod
    def _lease_evidence_level(slot: sqlite3.Row | None) -> str:
        return (
            "independent_transfer"
            if slot is not None and str(slot["phase"]) == "transfer"
            else "formative"
        )

    @staticmethod
    def _submission_key(campaign_id: str, position: int, case_id: str) -> str:
        # Training intentionally preserves first-write-wins replay semantics for
        # one frozen campaign slot, even if a later retry carries different UI
        # fields. The raw key never leaves the server or reaches durable storage.
        return f"training-submit:{campaign_id}:{position}:{case_id}"

    @staticmethod
    def _answer_event_id(campaign_id: str, position: int, case_id: str) -> str:
        return f"training-answer:{campaign_id}:{position}:{case_id}"

    @staticmethod
    def _current_assessment_lease(
        conn: sqlite3.Connection, *, learner_id: str, campaign_id: str
    ) -> sqlite3.Row | None:
        rows = conn.execute(
            "SELECT leases.*, cases.ecg_id FROM assessment_leases AS leases "
            "JOIN assessment_lease_cases AS cases "
            "ON cases.lease_id = leases.lease_id AND cases.ordinal = 0 "
            "WHERE leases.mode = 'training' AND leases.session_id = ? "
            "AND leases.state IN ('active', 'submitting') "
            "ORDER BY leases.lease_id",
            (campaign_id,),
        ).fetchall()
        if len(rows) > 1:
            raise RuntimeError(
                "Training session has more than one live assessment lease"
            )
        if rows and str(rows[0]["owner_id"]) != learner_id:
            # Account claim must re-key the normalized ledger in its own atomic
            # lifecycle transaction. Never create a second lease generation to
            # paper over a partial owner migration.
            raise RuntimeError(
                "Training campaign and assessment lease have different owners"
            )
        return rows[0] if rows else None

    @classmethod
    def _create_pending_lease_in_transaction(
        cls,
        conn: sqlite3.Connection,
        *,
        campaign: sqlite3.Row,
        slot: sqlite3.Row | None,
        case_id: str,
        now: str,
        integrity_status: str,
    ) -> sqlite3.Row:
        lease_id = f"tl_{uuid.uuid4().hex}"
        create_lease(
            conn,
            lease_id=lease_id,
            owner_id=str(campaign["learner_id"]),
            mode="training",
            session_id=str(campaign["campaign_id"]),
            ecg_ids=(case_id,),
            created_at=now,
            expires_at=_utc(now) + TRAINING_LEASE_TTL,
            integrity_status=integrity_status,
        )
        append_event(
            conn,
            event_id=f"{lease_id}:presented",
            owner_id=str(campaign["learner_id"]),
            mode="training",
            session_id=str(campaign["campaign_id"]),
            lease_id=lease_id,
            ecg_id=case_id,
            event_type="item_presented",
            evidence_level=cls._lease_evidence_level(slot),
            integrity_status=integrity_status,
            occurred_at=now,
        )
        lease = cls._current_assessment_lease(
            conn,
            learner_id=str(campaign["learner_id"]),
            campaign_id=str(campaign["campaign_id"]),
        )
        if lease is None:
            raise RuntimeError("Training lease creation lost its active boundary")
        return lease

    @classmethod
    def _append_terminal_lease_event(
        cls,
        conn: sqlite3.Connection,
        *,
        lease: sqlite3.Row,
        slot: sqlite3.Row | None,
        event_type: str,
        terminal_state: str,
        occurred_at: str,
    ) -> None:
        append_event(
            conn,
            event_id=terminal_event_id(str(lease["lease_id"]), terminal_state),
            owner_id=str(lease["owner_id"]),
            mode="training",
            session_id=str(lease["session_id"]),
            lease_id=str(lease["lease_id"]),
            ecg_id=str(lease["ecg_id"]),
            event_type=event_type,
            evidence_level=cls._lease_evidence_level(slot),
            integrity_status=str(lease["integrity_status"]),
            occurred_at=occurred_at,
        )

    @classmethod
    def _ensure_pending_lease_in_transaction(
        cls,
        conn: sqlite3.Connection,
        *,
        campaign: sqlite3.Row,
        slot: sqlite3.Row | None,
        case_id: str,
        now: str,
        backfilled: bool,
    ) -> sqlite3.Row:
        """Return the sole live lease, rotating an expired idle generation.

        Training is untimed. Expiry is therefore an inactivity/recovery
        boundary, not a forced wrong answer: the expired generation is audited
        once and a fresh lease for the same frozen ECG is created in this same
        transaction. A claimed generation is never expired underneath grading.
        """

        lease = cls._current_assessment_lease(
            conn,
            learner_id=str(campaign["learner_id"]),
            campaign_id=str(campaign["campaign_id"]),
        )
        if lease is not None and str(lease["ecg_id"]) != case_id:
            raise RuntimeError(
                "Training campaign and active assessment lease protect different ECGs"
            )
        if lease is not None and str(lease["state"]) == "submitting":
            return lease
        if lease is not None and _utc(str(lease["expires_at"])) <= _utc(now):
            terminalize_lease(
                conn,
                lease_id=str(lease["lease_id"]),
                owner_id=str(campaign["learner_id"]),
                terminal_state="expired",
                terminal_at=now,
            )
            cls._append_terminal_lease_event(
                conn,
                lease=lease,
                slot=slot,
                event_type="item_expired",
                terminal_state="expired",
                occurred_at=now,
            )
            lease = None
        if lease is None:
            lease = cls._create_pending_lease_in_transaction(
                conn,
                campaign=campaign,
                slot=slot,
                case_id=case_id,
                now=now,
                integrity_status="backfilled_v1" if backfilled else "atomic_v2",
            )
        return lease

    @classmethod
    def _abandon_pending_lease_in_transaction(
        cls,
        conn: sqlite3.Connection,
        *,
        campaign: sqlite3.Row,
        now: str,
    ) -> None:
        case_id = str(campaign["pending_case_id"] or "")
        if not case_id:
            return
        slot = conn.execute(
            "SELECT * FROM training_campaign_slots WHERE campaign_id = ? "
            "AND ordinal = ? AND case_id = ?",
            (campaign["campaign_id"], campaign["position"], case_id),
        ).fetchone()
        lease = cls._current_assessment_lease(
            conn,
            learner_id=str(campaign["learner_id"]),
            campaign_id=str(campaign["campaign_id"]),
        )
        if lease is None:
            lease = cls._ensure_pending_lease_in_transaction(
                conn,
                campaign=campaign,
                slot=slot,
                case_id=case_id,
                now=now,
                backfilled=True,
            )
        terminalize_lease(
            conn,
            lease_id=str(lease["lease_id"]),
            owner_id=str(campaign["learner_id"]),
            terminal_state="abandoned",
            terminal_at=now,
        )
        cls._append_terminal_lease_event(
            conn,
            lease=lease,
            slot=slot,
            event_type="item_abandoned",
            terminal_state="abandoned",
            occurred_at=now,
        )

    @classmethod
    def _backfill_pending_leases(
        cls, conn: sqlite3.Connection, *, now: str
    ) -> None:
        rows = conn.execute(
            "SELECT * FROM training_campaigns WHERE status = 'active' "
            "AND pending_case_id IS NOT NULL ORDER BY campaign_id"
        ).fetchall()
        for campaign in rows:
            slot = conn.execute(
                "SELECT * FROM training_campaign_slots WHERE campaign_id = ? "
                "AND ordinal = ? AND case_id = ?",
                (
                    campaign["campaign_id"],
                    campaign["position"],
                    campaign["pending_case_id"],
                ),
            ).fetchone()
            cls._ensure_pending_lease_in_transaction(
                conn,
                campaign=campaign,
                slot=slot,
                case_id=str(campaign["pending_case_id"]),
                now=now,
                backfilled=True,
            )

    @staticmethod
    def _repair_duplicate_current_campaigns(conn: sqlite3.Connection) -> None:
        """Deterministically quarantine legacy duplicate resumable campaigns.

        The newest durable row remains resumable. Older active/feedback rows are
        abandoned before the partial unique index is installed, so migration is
        safe even for databases written by the former check-then-insert flow.
        """

        rows = conn.execute(
            "SELECT campaign_id, learner_id FROM training_campaigns "
            "WHERE status = 'active' OR feedback_case_id IS NOT NULL "
            "ORDER BY learner_id, updated_at DESC, created_at DESC, campaign_id DESC"
        ).fetchall()
        keepers: set[str] = set()
        losers: list[str] = []
        for row in rows:
            learner_id = str(row["learner_id"])
            if learner_id in keepers:
                losers.append(str(row["campaign_id"]))
            else:
                keepers.add(learner_id)
        if not losers:
            return
        migrated_at = _now()
        conn.executemany(
            "UPDATE training_campaigns SET status = 'abandoned', pending_case_id = NULL, "
            "feedback_case_id = NULL, abandoned_at = COALESCE(abandoned_at, ?), "
            "updated_at = ? WHERE campaign_id = ?",
            [(migrated_at, migrated_at, campaign_id) for campaign_id in losers],
        )

    @staticmethod
    def _campaign(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "campaignId": row["campaign_id"],
            "learnerId": row["learner_id"],
            "conceptId": row["concept_id"],
            "subskill": row["subskill"],
            "requestedLength": int(row["requested_length"]),
            "length": int(row["length"]),
            "poolCount": int(row["pool_count"]),
            "phases": json.loads(row["phases_json"]),
            "phaseCounts": json.loads(row["phase_counts_json"]),
            "position": int(row["position"]),
            "pendingCaseId": row["pending_case_id"],
            "feedbackCaseId": row["feedback_case_id"],
            "status": row["status"],
            "contextKey": row["context_key"],
            "rosterPolicy": json.loads(row["roster_policy_json"] or "{}"),
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
            "abandonedAt": row["abandoned_at"],
        }

    @staticmethod
    def _slot(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "position": int(row["ordinal"]),
            "phase": row["phase"],
            "caseId": row["case_id"],
            "caseFocus": row["case_focus"],
            "targetPresent": bool(row["target_present"]),
            "selectionReason": row["selection_reason"],
            "status": row["status"],
            "servedAt": row["served_at"],
            "answeredAt": row["answered_at"],
        }

    @staticmethod
    def _answer(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "answerId": int(row["id"]),
            "campaignId": row["campaign_id"],
            "position": int(row["ordinal"]),
            "caseId": row["case_id"],
            "response": json.loads(row["response_json"]),
            "grade": json.loads(row["grade_json"]),
            "tutor": json.loads(row["tutor_json"]),
            "receipt": json.loads(row["receipt_json"]),
            "summary": json.loads(row["summary_json"]),
            "integrityStatus": row["integrity_status"],
            "attemptId": int(row["attempt_id"]),
            "createdAt": row["created_at"],
        }

    @staticmethod
    def _validate_plan(plan: list[dict[str, Any]]) -> None:
        if not plan:
            raise ValueError("Training campaign plan cannot be empty")
        case_ids = [str(slot["caseId"]) for slot in plan]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("Training campaign cases must be unique")

    @staticmethod
    def _recent_independent_case_ids(
        conn: sqlite3.Connection,
        learner_id: str,
        *,
        limit: int = RECENT_INDEPENDENT_ECG_LIMIT,
    ) -> list[str]:
        if limit <= 0 or not TrainingCampaignStore._table_exists(
            conn, "guided_learning_events"
        ):
            return []
        rows = conn.execute(
            "SELECT case_id, MAX(created_at) AS recent_at, MAX(id) AS recent_id "
            "FROM guided_learning_events WHERE learner_id = ? AND module_id = 'train' "
            "AND effective_evidence_level = 'independent_transfer' "
            "AND case_id IS NOT NULL AND TRIM(case_id) != '' GROUP BY case_id "
            "ORDER BY recent_at DESC, recent_id DESC, case_id ASC LIMIT ?",
            (learner_id, int(limit)),
        ).fetchall()
        return [str(row["case_id"]) for row in rows]

    @staticmethod
    def _apply_recent_independent_exclusion(
        pool: list[dict[str, Any]],
        canonical_plan: list[dict[str, Any]],
        recent_case_ids: list[str],
        *,
        requested_length: int,
        recent_limit: int,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Prefer unseen ECGs without changing canonical role/phase composition.

        Each canonical slot is replaced only by another ECG with the same role.
        Thus recency filtering cannot shrink the roster or silently turn a target,
        contrast, or transfer slot into a different exercise. A recently attempted
        ECG is reused only after the fresh queue for that exact role is exhausted.
        """

        TrainingCampaignStore._validate_plan(canonical_plan)
        pool_ids = [str(entry["caseId"]) for entry in pool]
        if len(pool_ids) != len(set(pool_ids)):
            raise ValueError("Training candidate pool cases must be unique")
        pool_by_id = {str(entry["caseId"]): entry for entry in pool}
        for slot in canonical_plan:
            if str(slot["caseId"]) not in pool_by_id:
                raise ValueError("Canonical Training plan contains a case outside its pool")

        recent = set(recent_case_ids)
        roles = ("target", "mimic", "negative")
        canonical_fresh_ids = {
            str(slot["caseId"])
            for slot in canonical_plan
            if str(slot["caseId"]) not in recent
        }
        replacement_queues: dict[str, deque[dict[str, Any]]] = {
            role: deque() for role in roles
        }
        fresh_by_role = {role: 0 for role in roles}
        for entry in pool:
            role = str(entry.get("role") or "")
            if role not in replacement_queues:
                raise ValueError(f"Unknown Training pool role: {role}")
            case_id = str(entry["caseId"])
            if case_id not in recent:
                fresh_by_role[role] += 1
                if case_id not in canonical_fresh_ids:
                    replacement_queues[role].append(entry)

        required_by_role = Counter(str(slot.get("role") or "") for slot in canonical_plan)
        reused_by_role: Counter[str] = Counter()
        final_plan: list[dict[str, Any]] = []
        for canonical in canonical_plan:
            role = str(canonical.get("role") or "")
            queue = replacement_queues.get(role)
            reused = False
            if queue is None:
                raise ValueError(f"Unknown canonical Training role: {role}")
            canonical_case_id = str(canonical["caseId"])
            if canonical_case_id not in recent:
                selected = pool_by_id[canonical_case_id]
            elif queue:
                selected = queue.popleft()
            else:
                selected = pool_by_id[canonical_case_id]
                reused = True
                reused_by_role[role] += 1
            final_plan.append(
                {
                    **selected,
                    "phase": str(canonical["phase"]),
                    "selectionReason": (
                        "recent_independent_reuse_unavoidable"
                        if reused
                        else str(
                            canonical.get("selectionReason") or "planned_sequence"
                        )
                    ),
                }
            )

        overlap_count = sum(1 for case_id in pool_ids if case_id in recent)
        reused_count = sum(reused_by_role.values())
        policy = {
            "version": "recent_independent_v1",
            "recentWindowLimit": int(recent_limit),
            "recentIndependentWindowCount": len(recent_case_ids),
            "eligibleRecentOverlapCount": overlap_count,
            "freshEligibleCount": len(pool) - overlap_count,
            "selectedFreshCount": len(final_plan) - reused_count,
            "excludedRecentCount": overlap_count - reused_count,
            "reusedRecentCount": reused_count,
            "reuseUnavoidable": reused_count > 0,
            "reuseReason": (
                "composition_preserving_role_depth_exhausted" if reused_count else None
            ),
            "requiredRoleCounts": {
                role: int(required_by_role.get(role, 0)) for role in roles
            },
            "freshRoleCounts": fresh_by_role,
            "reusedByRole": {role: int(reused_by_role.get(role, 0)) for role in roles},
            "requestedLength": int(requested_length),
            "plannedLength": len(final_plan),
            "requestedLengthSatisfied": len(final_plan) == int(requested_length),
            "selectionPolicy": "fresh_same_role_then_documented_recent_reuse",
        }
        return final_plan, policy

    @staticmethod
    def _exclude_live_owner_exposures(
        pool: list[dict[str, Any]],
        canonical_plan: list[dict[str, Any]],
        exposed_case_ids: set[str],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
        """Replace live cross-mode exposures without weakening slot roles.

        Committed feedback in one mode must never become an answer key for a
        still-pending item in another. Unlike ordinary recent-history reuse, a
        live lease is a hard exclusion. If exact role depth is unavailable, the
        campaign fails closed and the learner can finish that assessment or
        choose a shorter set.
        """

        if not exposed_case_ids:
            return pool, canonical_plan, 0
        TrainingCampaignStore._validate_plan(canonical_plan)
        filtered_pool = [
            entry for entry in pool if str(entry["caseId"]) not in exposed_case_ids
        ]
        overlap = len(pool) - len(filtered_pool)
        if not overlap:
            return pool, canonical_plan, 0
        filtered_by_id = {str(entry["caseId"]): entry for entry in filtered_pool}
        protected_canonical_ids = {
            str(slot["caseId"])
            for slot in canonical_plan
            if str(slot["caseId"]) in filtered_by_id
        }
        replacement_queues: dict[str, deque[dict[str, Any]]] = {
            role: deque() for role in ("target", "mimic", "negative")
        }
        for entry in filtered_pool:
            role = str(entry.get("role") or "")
            if role not in replacement_queues:
                raise ValueError(f"Unknown Training pool role: {role}")
            if str(entry["caseId"]) not in protected_canonical_ids:
                replacement_queues[role].append(entry)

        revised: list[dict[str, Any]] = []
        for canonical in canonical_plan:
            case_id = str(canonical["caseId"])
            role = str(canonical.get("role") or "")
            if case_id in filtered_by_id:
                selected = filtered_by_id[case_id]
            else:
                queue = replacement_queues.get(role)
                if not queue:
                    raise TrainingExposureConflictError(
                        "Not enough unexposed ECGs preserve this Training roster"
                    )
                selected = queue.popleft()
            revised.append(
                {
                    **selected,
                    "phase": str(canonical["phase"]),
                    "selectionReason": (
                        "live_assessment_exposure_avoided"
                        if case_id not in filtered_by_id
                        else str(
                            canonical.get("selectionReason") or "planned_sequence"
                        )
                    ),
                }
            )
        TrainingCampaignStore._validate_plan(revised)
        return filtered_pool, revised, overlap

    @staticmethod
    def _insert_campaign(
        conn: sqlite3.Connection,
        *,
        campaign_id: str,
        learner_id: str,
        concept_id: str,
        subskill: str,
        requested_length: int,
        pool_count: int,
        plan: list[dict[str, Any]],
        context_key: str,
        roster_policy: dict[str, Any],
        now: str,
    ) -> None:
        TrainingCampaignStore._validate_plan(plan)
        phases = [str(slot["phase"]) for slot in plan]
        phase_counts = {phase: phases.count(phase) for phase in ("target", "mimic", "negative", "transfer")}
        conn.execute(
            """
            INSERT INTO training_campaigns (
                campaign_id, learner_id, concept_id, subskill, requested_length,
                length, pool_count, phases_json, phase_counts_json, position,
                status, context_key, roster_policy_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 'active', ?, ?, ?, ?)
            """,
            (
                campaign_id, learner_id, concept_id, subskill, requested_length,
                len(plan), pool_count, json.dumps(phases), json.dumps(phase_counts),
                context_key, json.dumps(roster_policy), now, now,
            ),
        )
        conn.executemany(
            """
            INSERT INTO training_campaign_slots (
                campaign_id, ordinal, phase, case_id, case_focus, target_present,
                selection_reason, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'queued')
            """,
            [
                (
                    campaign_id, index, slot["phase"], str(slot["caseId"]),
                    str(slot["caseFocus"]), 1 if slot["targetPresent"] else 0,
                    str(slot.get("selectionReason") or "planned_sequence"),
                )
                for index, slot in enumerate(plan)
            ],
        )

    @staticmethod
    def _claim_next_in_transaction(
        conn: sqlite3.Connection, campaign_id: str, *, now: str
    ) -> sqlite3.Row | None:
        campaign = conn.execute(
            "SELECT * FROM training_campaigns WHERE campaign_id = ?", (campaign_id,)
        ).fetchone()
        if not campaign:
            return None
        if campaign["pending_case_id"] or campaign["feedback_case_id"]:
            if campaign["pending_case_id"]:
                pending_slot = conn.execute(
                    "SELECT * FROM training_campaign_slots WHERE campaign_id = ? "
                    "AND ordinal = ? AND case_id = ?",
                    (
                        campaign_id,
                        campaign["position"],
                        campaign["pending_case_id"],
                    ),
                ).fetchone()
                TrainingCampaignStore._ensure_pending_lease_in_transaction(
                    conn,
                    campaign=campaign,
                    slot=pending_slot,
                    case_id=str(campaign["pending_case_id"]),
                    now=now,
                    backfilled=True,
                )
            return campaign
        position = int(campaign["position"])
        if campaign["status"] != "active" or position >= int(campaign["length"]):
            return campaign
        slot = conn.execute(
            "SELECT * FROM training_campaign_slots WHERE campaign_id = ? AND ordinal = ?",
            (campaign_id, position),
        ).fetchone()
        if not slot:
            return campaign
        claimed = conn.execute(
            "UPDATE training_campaign_slots SET status = 'pending', "
            "served_at = COALESCE(served_at, ?) WHERE campaign_id = ? AND ordinal = ? "
            "AND status = 'queued'",
            (now, campaign_id, position),
        )
        if claimed.rowcount != 1:
            return conn.execute(
                "SELECT * FROM training_campaigns WHERE campaign_id = ?", (campaign_id,)
            ).fetchone()
        updated = conn.execute(
            "UPDATE training_campaigns SET pending_case_id = ?, updated_at = ? "
            "WHERE campaign_id = ? AND pending_case_id IS NULL AND feedback_case_id IS NULL",
            (slot["case_id"], now, campaign_id),
        )
        if updated.rowcount != 1:
            raise RuntimeError("Training campaign lost its pending exposure boundary")
        campaign = conn.execute(
            "SELECT * FROM training_campaigns WHERE campaign_id = ?", (campaign_id,)
        ).fetchone()
        if campaign is None:
            raise RuntimeError("Training campaign disappeared during item exposure")
        TrainingCampaignStore._ensure_pending_lease_in_transaction(
            conn,
            campaign=campaign,
            slot=slot,
            case_id=str(slot["case_id"]),
            now=now,
            backfilled=False,
        )
        return campaign

    def create_campaign(
        self,
        learner_id: str,
        concept_id: str,
        subskill: str,
        requested_length: int,
        pool_count: int,
        plan: list[dict[str, Any]],
        *,
        context_key: str = "",
        roster_policy: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Low-level creator retained for focused store tests.

        HTTP starts use ``start_or_return_campaign`` so active ownership and the
        recent-independent exclusion snapshot share the same write transaction.
        """

        self._validate_plan(plan)
        campaign_id = f"tc_{uuid.uuid4().hex[:20]}"
        now = _now()
        policy = roster_policy or {
            "version": "direct_unfiltered_v1",
            "requestedLength": int(requested_length),
            "plannedLength": len(plan),
            "requestedLengthSatisfied": len(plan) == int(requested_length),
        }
        with self.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            self._insert_campaign(
                conn,
                campaign_id=campaign_id,
                learner_id=learner_id,
                concept_id=concept_id,
                subskill=subskill,
                requested_length=requested_length,
                pool_count=pool_count,
                plan=plan,
                context_key=context_key,
                roster_policy=policy,
                now=now,
            )
        return self.get_campaign(campaign_id)  # type: ignore[return-value]

    def start_or_return_campaign(
        self,
        learner_id: str,
        concept_id: str,
        subskill: str,
        requested_length: int,
        pool_count: int,
        canonical_plan: list[dict[str, Any]],
        candidate_pool: list[dict[str, Any]],
        *,
        context_key: str = "",
        replace_active: bool = False,
        recent_limit: int = RECENT_INDEPENDENT_ECG_LIMIT,
    ) -> dict[str, Any]:
        """Atomically return the owner's current campaign or create one.

        ``BEGIN IMMEDIATE`` serializes same-owner starts before the current-row
        lookup. The partial unique index remains the database-level invariant;
        this method provides deterministic, non-exceptional conflict resolution.
        """

        self._validate_plan(canonical_plan)
        now = _now()
        with self.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            current = conn.execute(
                "SELECT * FROM training_campaigns WHERE learner_id = ? "
                "AND (status = 'active' OR feedback_case_id IS NOT NULL) "
                "ORDER BY updated_at DESC, created_at DESC, campaign_id DESC LIMIT 1",
                (learner_id,),
            ).fetchone()
            # A completed campaign can retain its final feedback ECG so the
            # learner can open the debrief after a reload. Starting a new set
            # acknowledges that feedback, but must never rewrite the finished
            # campaign as abandoned (completed sets back learning history).
            if current is not None and current["status"] == "complete":
                conn.execute(
                    "UPDATE training_campaigns SET feedback_case_id = NULL "
                    "WHERE campaign_id = ? AND status = 'complete'",
                    (current["campaign_id"],),
                )
                current = None
            if current and not replace_active:
                return {"status": "existing", "campaign": self._campaign(current)}
            if current:
                self._abandon_pending_lease_in_transaction(
                    conn,
                    campaign=current,
                    now=now,
                )
                conn.execute(
                    "UPDATE training_campaigns SET status = 'abandoned', "
                    "pending_case_id = NULL, feedback_case_id = NULL, "
                    "abandoned_at = COALESCE(abandoned_at, ?), updated_at = ? "
                    "WHERE learner_id = ? AND "
                    "(status = 'active' OR feedback_case_id IS NOT NULL)",
                    (now, now, learner_id),
                )

            recent_case_ids = self._recent_independent_case_ids(
                conn, learner_id, limit=recent_limit
            )
            live_exposures = set(owner_exposure_ids(conn, owner_id=learner_id))
            available_pool, exposure_safe_plan, active_overlap = (
                self._exclude_live_owner_exposures(
                    candidate_pool,
                    canonical_plan,
                    live_exposures,
                )
            )
            plan, roster_policy = self._apply_recent_independent_exclusion(
                available_pool,
                exposure_safe_plan,
                recent_case_ids,
                requested_length=requested_length,
                recent_limit=recent_limit,
            )
            roster_policy = {
                **roster_policy,
                "liveOwnerExposureCount": len(live_exposures),
                "eligibleLiveExposureOverlapCount": active_overlap,
                "liveExposureHardExcluded": active_overlap,
            }
            campaign_id = f"tc_{uuid.uuid4().hex[:20]}"
            self._insert_campaign(
                conn,
                campaign_id=campaign_id,
                learner_id=learner_id,
                concept_id=concept_id,
                subskill=subskill,
                requested_length=requested_length,
                pool_count=pool_count,
                plan=plan,
                context_key=context_key,
                roster_policy=roster_policy,
                now=now,
            )
            row = self._claim_next_in_transaction(conn, campaign_id, now=now)
            if not row:
                raise RuntimeError("New Training campaign could not claim its first slot")
            return {"status": "created", "campaign": self._campaign(row)}

    def get_campaign(self, campaign_id: str) -> dict[str, Any] | None:
        now = _now()
        with self.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM training_campaigns WHERE campaign_id = ?", (campaign_id,)
            ).fetchone()
            if row is not None and row["status"] == "active" and row["pending_case_id"]:
                slot = conn.execute(
                    "SELECT * FROM training_campaign_slots WHERE campaign_id = ? "
                    "AND ordinal = ? AND case_id = ?",
                    (campaign_id, row["position"], row["pending_case_id"]),
                ).fetchone()
                self._ensure_pending_lease_in_transaction(
                    conn,
                    campaign=row,
                    slot=slot,
                    case_id=str(row["pending_case_id"]),
                    now=now,
                    backfilled=True,
                )
        return self._campaign(row) if row else None

    def is_case_pending(self, case_id: str) -> bool:
        """Global secrecy guard for an uncommitted Training ECG.

        This intentionally does not take a learner id: dropping credentials or
        asking through another account must not turn a pending assessment case
        into a public answer key.
        """

        with self.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM assessment_leases AS leases "
                "JOIN assessment_lease_cases AS cases ON cases.lease_id = leases.lease_id "
                "WHERE leases.mode = 'training' AND cases.ecg_id = ? "
                "AND leases.state IN ('active', 'submitting') LIMIT 1",
                (case_id,),
            ).fetchone()
        return row is not None

    def is_case_pending_for_learner(self, case_id: str, learner_id: str) -> bool:
        """Whether this learner currently owns an uncommitted Training ECG."""

        with self.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM assessment_leases AS leases "
                "JOIN assessment_lease_cases AS cases ON cases.lease_id = leases.lease_id "
                "WHERE leases.owner_id = ? AND leases.mode = 'training' "
                "AND cases.ecg_id = ? "
                "AND leases.state IN ('active', 'submitting') LIMIT 1",
                (learner_id, case_id),
            ).fetchone()
        return row is not None

    def get_active(self, learner_id: str) -> dict[str, Any] | None:
        now = _now()
        with self.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM training_campaigns WHERE learner_id = ? "
                "AND (status = 'active' OR feedback_case_id IS NOT NULL) "
                "ORDER BY updated_at DESC LIMIT 1",
                (learner_id,),
            ).fetchone()
            if row is not None and row["status"] == "active" and row["pending_case_id"]:
                slot = conn.execute(
                    "SELECT * FROM training_campaign_slots WHERE campaign_id = ? "
                    "AND ordinal = ? AND case_id = ?",
                    (row["campaign_id"], row["position"], row["pending_case_id"]),
                ).fetchone()
                self._ensure_pending_lease_in_transaction(
                    conn,
                    campaign=row,
                    slot=slot,
                    case_id=str(row["pending_case_id"]),
                    now=now,
                    backfilled=True,
                )
        return self._campaign(row) if row else None

    def get_slot(self, campaign_id: str, position: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM training_campaign_slots WHERE campaign_id = ? AND ordinal = ?",
                (campaign_id, position),
            ).fetchone()
        return self._slot(row) if row else None

    def get_slot_for_case(self, campaign_id: str, case_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM training_campaign_slots WHERE campaign_id = ? AND case_id = ?",
                (campaign_id, case_id),
            ).fetchone()
        return self._slot(row) if row else None

    def claim_next(self, campaign_id: str) -> dict[str, Any] | None:
        now = _now()
        with self.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            row = self._claim_next_in_transaction(conn, campaign_id, now=now)
            return self._campaign(row) if row else None

    def acknowledge_feedback(self, campaign_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            conn.execute(
                # Clearing a presentation pointer is not a new learning event.
                # Preserve the completion timestamp used by Activity history.
                "UPDATE training_campaigns SET feedback_case_id = NULL "
                "WHERE campaign_id = ?",
                (campaign_id,),
            )
        return self.get_campaign(campaign_id)

    def claim_answer_submission(
        self,
        *,
        campaign_id: str,
        case_id: str,
        learner_id: str,
    ) -> dict[str, Any]:
        """Reserve the exact pending Training item before any grading runs."""

        now = _now()
        with self.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            campaign = conn.execute(
                "SELECT * FROM training_campaigns WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchone()
            if campaign is None or str(campaign["learner_id"]) != learner_id:
                return {"status": "missing"}
            existing = conn.execute(
                "SELECT * FROM training_campaign_answers WHERE campaign_id = ? "
                "AND case_id = ?",
                (campaign_id, case_id),
            ).fetchone()
            if existing is not None:
                return {"status": "replay", "answer": self._answer(existing)}
            if (
                campaign["status"] != "active"
                or str(campaign["pending_case_id"] or "") != case_id
            ):
                return {
                    "status": "not_pending",
                    "pendingCaseId": campaign["pending_case_id"],
                }
            position = int(campaign["position"])
            slot = conn.execute(
                "SELECT * FROM training_campaign_slots WHERE campaign_id = ? "
                "AND ordinal = ? AND case_id = ? AND status = 'pending'",
                (campaign_id, position, case_id),
            ).fetchone()
            if slot is None:
                return {
                    "status": "not_pending",
                    "pendingCaseId": campaign["pending_case_id"],
                }
            lease = self._ensure_pending_lease_in_transaction(
                conn,
                campaign=campaign,
                slot=slot,
                case_id=case_id,
                now=now,
                backfilled=True,
            )
            submission_key = self._submission_key(campaign_id, position, case_id)
            mutation = claim_submission(
                conn,
                lease_id=str(lease["lease_id"]),
                owner_id=learner_id,
                submission_key=submission_key,
                claimed_at=now,
            )
            return {
                "status": "claimed",
                "leaseId": mutation.lease_id,
                "submissionKey": submission_key,
                "position": position,
                "replayed": mutation.replayed,
            }

    def release_answer_submission(
        self,
        *,
        campaign_id: str,
        learner_id: str,
        lease_id: str,
        submission_key: str,
    ) -> bool:
        """Best-effort exact-key release after a recoverable grading failure.

        A concurrent answer commit or explicit abandonment may already have made
        the lease terminal. Those outcomes are never reversed.
        """

        now = _now()
        with self.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            campaign = conn.execute(
                "SELECT learner_id FROM training_campaigns WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchone()
            if campaign is None or str(campaign["learner_id"]) != learner_id:
                return False
            try:
                release_submission(
                    conn,
                    lease_id=lease_id,
                    owner_id=learner_id,
                    submission_key=submission_key,
                    released_at=now,
                )
            except (LeaseNotFoundError, LeaseStateError):
                return False
            return True

    def get_answer(self, campaign_id: str, case_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM training_campaign_answers WHERE campaign_id = ? AND case_id = ?",
                (campaign_id, case_id),
            ).fetchone()
        return self._answer(row) if row else None

    @staticmethod
    def _adapt_next_queued_slot(
        conn: sqlite3.Connection,
        *,
        campaign_id: str,
        next_position: int,
        preference: str,
        reason: str,
    ) -> sqlite3.Row | None:
        """Move the best still-unseen roster item into the next position.

        The operation swaps complete queued slot contracts. It cannot introduce
        a new ECG, move an answered/pending ECG, or duplicate a case id.
        """

        current = conn.execute(
            "SELECT * FROM training_campaign_slots WHERE campaign_id = ? "
            "AND ordinal = ? AND status = 'queued'",
            (campaign_id, next_position),
        ).fetchone()
        if not current:
            return None

        filters = {
            "target": (
                "target_present = 1 AND phase = 'target'",
                "target_present = 1 AND phase != 'transfer'",
                "target_present = 1",
                "1 = 1",
            ),
            "contrast": (
                "target_present = 0 AND phase = 'mimic'",
                "target_present = 0 AND phase = 'negative'",
                "target_present = 0 AND phase != 'transfer'",
                "target_present = 0",
                "1 = 1",
            ),
            "challenge": (
                "phase = 'transfer' AND target_present = 1",
                "phase = 'transfer'",
                "target_present = 1",
                "1 = 1",
            ),
        }.get(preference, ("1 = 1",))
        selected = None
        for clause in filters:
            selected = conn.execute(
                "SELECT * FROM training_campaign_slots WHERE campaign_id = ? "
                "AND ordinal >= ? AND status = 'queued' AND " + clause + " "
                "ORDER BY ordinal LIMIT 1",
                (campaign_id, next_position),
            ).fetchone()
            if selected:
                break
        if not selected:
            return None

        fulfilled = (
            (preference == "target" and bool(selected["target_present"]))
            or (preference == "contrast" and not bool(selected["target_present"]))
            or (preference == "challenge" and selected["phase"] == "transfer")
        )
        effective_reason = reason if fulfilled else "adaptive_fallback_roster"
        selected_position = int(selected["ordinal"])
        if selected_position == next_position:
            conn.execute(
                "UPDATE training_campaign_slots SET selection_reason = ? "
                "WHERE campaign_id = ? AND ordinal = ? AND status = 'queued'",
                (effective_reason, campaign_id, next_position),
            )
        else:
            temporary_case_id = f"__training_swap__{uuid.uuid4().hex}"
            conn.execute(
                "UPDATE training_campaign_slots SET case_id = ? "
                "WHERE campaign_id = ? AND ordinal = ? AND status = 'queued'",
                (temporary_case_id, campaign_id, next_position),
            )
            conn.execute(
                "UPDATE training_campaign_slots SET phase = ?, case_id = ?, case_focus = ?, "
                "target_present = ?, selection_reason = ? "
                "WHERE campaign_id = ? AND ordinal = ? AND status = 'queued'",
                (
                    current["phase"], current["case_id"], current["case_focus"],
                    current["target_present"], current["selection_reason"],
                    campaign_id, selected_position,
                ),
            )
            conn.execute(
                "UPDATE training_campaign_slots SET phase = ?, case_id = ?, case_focus = ?, "
                "target_present = ?, selection_reason = ? "
                "WHERE campaign_id = ? AND ordinal = ? AND status = 'queued'",
                (
                    selected["phase"], selected["case_id"], selected["case_focus"],
                    selected["target_present"], effective_reason, campaign_id, next_position,
                ),
            )
        return conn.execute(
            "SELECT * FROM training_campaign_slots WHERE campaign_id = ? AND ordinal = ?",
            (campaign_id, next_position),
        ).fetchone()

    def _finalization_checkpoint(self, label: str) -> None:
        """Private failure-injection seam for atomic Training tests."""

        hook = getattr(self, "_training_finalization_failure_hook", None)
        if callable(hook):
            hook(label)

    def finalize_answer(
        self,
        *,
        learning_store: Any,
        campaign_id: str,
        case_id: str,
        learner_id: str,
        lease_id: str,
        submission_key: str,
        response: dict[str, Any],
        grade: dict[str, Any],
        tutor: dict[str, Any] | None,
        receipt_event: dict[str, Any],
        summary: dict[str, Any],
        confidence: int | None,
        hints_used: int,
        adaptation_preference: str = "challenge",
        adaptation_reason: str = "challenge_after_success",
    ) -> dict[str, Any]:
        """Commit a complete Training response and every evidence effect once.

        The generic attempt, answer ledger, exact guided/retention receipt,
        subskill state, slot transition, campaign advance, and queued-roster
        adaptation all share this transaction. Any exception rolls every row
        back to the still-pending precommit state.
        """

        now = _now()
        with self.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            campaign = conn.execute(
                "SELECT * FROM training_campaigns WHERE campaign_id = ?", (campaign_id,)
            ).fetchone()
            if not campaign or str(campaign["learner_id"]) != learner_id:
                return {"status": "missing"}
            existing = conn.execute(
                "SELECT * FROM training_campaign_answers WHERE campaign_id = ? AND case_id = ?",
                (campaign_id, case_id),
            ).fetchone()
            if existing:
                answer = self._answer(existing)
                if (
                    answer["integrityStatus"] == "finalizing"
                    or not answer["receipt"]
                    or not answer["receipt"].get("eventId")
                ):
                    return {"status": "legacy_incomplete", "answer": answer}
                return {"status": "replay", "answer": answer}
            position = int(campaign["position"])
            if campaign["status"] != "active" or campaign["pending_case_id"] != case_id:
                return {
                    "status": "not_pending",
                    "pendingCaseId": campaign["pending_case_id"],
                }
            slot = conn.execute(
                "SELECT * FROM training_campaign_slots WHERE campaign_id = ? AND ordinal = ?",
                (campaign_id, position),
            ).fetchone()
            if not slot or slot["case_id"] != case_id:
                return {"status": "not_pending", "pendingCaseId": campaign["pending_case_id"]}

            expected_event_key = (
                f"train:{campaign_id}:{position}:{case_id}:{campaign['subskill']}"
            )
            if (
                receipt_event.get("eventKey") != expected_event_key
                or receipt_event.get("moduleId") != "train"
                or receipt_event.get("caseId") != case_id
                or receipt_event.get("interactionId")
                != f"{case_id}:{campaign['subskill']}"
                or list(receipt_event.get("subskills") or []) != [campaign["subskill"]]
                or receipt_event.get("trainingPhase") != slot["phase"]
                or receipt_event.get("_serverVerifiedScoring") is not True
            ):
                raise ValueError("Training receipt event does not match the pending slot contract")
            lease_contract = conn.execute(
                "SELECT integrity_status FROM assessment_leases WHERE lease_id = ? "
                "AND owner_id = ? AND mode = 'training' AND session_id = ?",
                (lease_id, learner_id, campaign_id),
            ).fetchone()
            if lease_contract is None:
                raise LeaseNotFoundError(
                    "Training answer reservation is not owned by this campaign"
                )

            attempt_cursor = conn.execute(
                """
                INSERT INTO attempts (
                    learner_id, case_id, mode, structured_answer_json, free_text_answer,
                    confidence, hints_used, score, correct_objectives_json,
                    missed_objectives_json, misconception_tags_json, feedback,
                    registry_version, created_at
                ) VALUES (?, ?, 'concept_practice', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    campaign["learner_id"], case_id,
                    json.dumps(response.get("structuredAnswer") or {}),
                    str(response.get("freeTextAnswer") or ""),
                    0 if confidence is None else confidence,
                    hints_used,
                    float(grade.get("score", 0.0)),
                    json.dumps(grade.get("correctObjectives") or []),
                    json.dumps(grade.get("missedObjectives") or []),
                    json.dumps(grade.get("misconceptions") or []),
                    str(grade.get("feedback") or ""), REGISTRY_VERSION, now,
                ),
            )
            self._finalization_checkpoint("after_attempt")
            answer_cursor = conn.execute(
                """
                INSERT INTO training_campaign_answers (
                    campaign_id, ordinal, case_id, response_json, grade_json,
                    tutor_json, receipt_json, summary_json, integrity_status,
                    attempt_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, '{}', ?, 'finalizing', ?, ?)
                """,
                (
                    campaign_id, position, case_id, json.dumps(response), json.dumps(grade),
                    json.dumps(tutor), json.dumps(summary), int(attempt_cursor.lastrowid), now,
                ),
            )
            answer_id = int(answer_cursor.lastrowid)
            self._finalization_checkpoint("after_answer")

            receipt = learning_store.save_guided_learning_event(
                str(campaign["learner_id"]),
                receipt_event,
                occurred_at=now,
                _connection=conn,
            )
            if not receipt.get("eventId") or len(receipt.get("receipts") or []) != 1:
                raise RuntimeError("Training finalization requires one exact subskill receipt")
            self._finalization_checkpoint("after_receipt")
            durable_summary = {
                **summary,
                "evidenceLevel": receipt["effectiveEvidenceLevel"],
            }
            normalized_score = float(receipt_event.get("score", 0.0))
            receipt_concept = str(receipt_event.get("concept") or campaign["concept_id"])
            competency_id = f"{receipt_concept}:{campaign['subskill']}"
            append_event(
                conn,
                event_id=self._answer_event_id(campaign_id, position, case_id),
                owner_id=learner_id,
                mode="training",
                session_id=campaign_id,
                lease_id=lease_id,
                ecg_id=case_id,
                event_type="answer_committed",
                evidence_level=str(receipt["effectiveEvidenceLevel"]),
                integrity_status=str(lease_contract["integrity_status"]),
                score=normalized_score,
                competencies={competency_id: normalized_score},
                submission_key=submission_key,
                occurred_at=now,
            )
            self._finalization_checkpoint("after_learner_event")
            mark_submitted(
                conn,
                lease_id=lease_id,
                owner_id=learner_id,
                submission_key=submission_key,
                submitted_at=now,
            )
            self._finalization_checkpoint("after_lease_submitted")
            promoted = conn.execute(
                "UPDATE training_campaign_answers SET receipt_json = ?, summary_json = ?, "
                "integrity_status = 'atomic_v2' WHERE id = ? AND integrity_status = 'finalizing'",
                (json.dumps(receipt), json.dumps(durable_summary), answer_id),
            )
            if promoted.rowcount != 1:
                raise RuntimeError("Training answer receipt promotion lost its finalizing boundary")
            self._finalization_checkpoint("after_receipt_persisted")

            answered = conn.execute(
                "UPDATE training_campaign_slots SET status = 'answered', answered_at = ? "
                "WHERE campaign_id = ? AND ordinal = ? AND case_id = ? AND status = 'pending'",
                (now, campaign_id, position, case_id),
            )
            if answered.rowcount != 1:
                raise RuntimeError("Training slot transition lost its pending boundary")
            self._finalization_checkpoint("after_slot_answered")
            next_position = position + 1
            status = "complete" if next_position >= int(campaign["length"]) else "active"
            advanced = conn.execute(
                "UPDATE training_campaigns SET position = ?, pending_case_id = NULL, "
                "feedback_case_id = ?, status = ?, updated_at = ? WHERE campaign_id = ? "
                "AND position = ? AND pending_case_id = ? AND status = 'active'",
                (next_position, case_id, status, now, campaign_id, position, case_id),
            )
            if advanced.rowcount != 1:
                raise RuntimeError("Training campaign advance lost its pending-item boundary")
            self._finalization_checkpoint("after_campaign_advance")
            adapted_next = None
            if status == "active":
                adapted_next = self._adapt_next_queued_slot(
                    conn,
                    campaign_id=campaign_id,
                    next_position=next_position,
                    preference=adaptation_preference,
                    reason=adaptation_reason,
                )
            self._finalization_checkpoint("after_adaptation")
            row = conn.execute(
                "SELECT * FROM training_campaign_answers WHERE id = ?", (answer_id,)
            ).fetchone()
        return {
            "status": "recorded",
            "answer": self._answer(row),
            "adaptedNext": self._slot(adapted_next) if adapted_next else None,
        }

    def summary(self, campaign_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT summary_json FROM training_campaign_answers WHERE campaign_id = ? ORDER BY ordinal",
                (campaign_id,),
            ).fetchall()
        attempts = [json.loads(row["summary_json"]) for row in rows]
        by_phase: dict[str, dict[str, int]] = {
            phase: {"attempted": 0, "correct": 0}
            for phase in ("target", "mimic", "negative", "transfer")
        }
        for attempt in attempts:
            phase = str(attempt.get("phase") or "transfer")
            bucket = by_phase.setdefault(phase, {"attempted": 0, "correct": 0})
            bucket["attempted"] += 1
            bucket["correct"] += 1 if attempt.get("correct") else 0
        return {
            "attempted": len(attempts),
            "correct": sum(1 for attempt in attempts if attempt.get("correct")),
            # `correct` is the selected subskill outcome.  Keep the blinded
            # target decision and the joint outcome visible as separate axes so
            # clients cannot accidentally present a correct mechanism or
            # calibration task as a correct ECG classification (or vice versa).
            "classificationCorrect": sum(
                1 for attempt in attempts if attempt.get("classificationCorrect")
            ),
            "fullTaskCorrect": sum(
                1
                for attempt in attempts
                if attempt.get("correct") and attempt.get("classificationCorrect")
            ),
            "independentReceipts": sum(
                1 for attempt in attempts if attempt.get("evidenceLevel") == "independent_transfer"
            ),
            "byPhase": by_phase,
            "recent": attempts[-25:],
        }

    def abandon(self, campaign_id: str, *, learner_id: str) -> dict[str, Any] | None:
        now = _now()
        with self.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            campaign = conn.execute(
                "SELECT * FROM training_campaigns WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchone()
            if campaign is None or str(campaign["learner_id"]) != learner_id:
                return None
            # Completion is an immutable learner-history boundary. An old UI,
            # retry, or concurrent navigation request may still call abandon;
            # return the finished campaign unchanged instead of erasing it
            # from completed-session review.
            if campaign["status"] == "complete":
                return self._campaign(campaign)
            if campaign["status"] != "abandoned":
                self._abandon_pending_lease_in_transaction(
                    conn,
                    campaign=campaign,
                    now=now,
                )
            conn.execute(
                "UPDATE training_campaigns SET status = 'abandoned', pending_case_id = NULL, "
                "feedback_case_id = NULL, abandoned_at = ?, updated_at = ? "
                "WHERE campaign_id = ? AND status != 'abandoned'",
                (now, now, campaign_id),
            )
            row = conn.execute(
                "SELECT * FROM training_campaigns WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchone()
        return self._campaign(row) if row else None

    def all_slots(self, campaign_id: str) -> list[dict[str, Any]]:
        """Test/diagnostic read of the frozen roster in its current adaptive order."""
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM training_campaign_slots WHERE campaign_id = ? ORDER BY ordinal",
                (campaign_id,),
            ).fetchall()
        return [self._slot(row) for row in rows]
