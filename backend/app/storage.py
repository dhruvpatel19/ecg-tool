from __future__ import annotations

import json
import re
import sqlite3
import threading
import hashlib
import hmac
import base64
from contextlib import contextmanager, nullcontext
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from .account_boundary import (
    configure_account_boundary,
    ensure_account_boundary_schema,
    retire_account_generation,
    translate_account_boundary_error,
)
from .ecg_capability import is_ecg_capability, issue_ecg_capability
from .assessment_ledger import (
    IdempotencyConflictError,
    append_event as append_learner_event,
    ensure_schema as ensure_assessment_ledger_schema,
    guided_interaction_event_id,
    owner_exposure_ids,
)
from .ontology import DEFAULT_MASTERY
from .objectives import (
    DYNAMIC_SOURCE_UNAVAILABLE,
    REGISTRY_VERSION,
    audited_source_packet_supports_objective,
    objective_definition,
    validate_objective_subskill,
)
from .retention import due_snapshot, parse_instant, retention_uncertainty, update_retention


LEARNER_SCHEMA_VERSION = 4
_SESSION_PUBLIC_ID_DOMAIN = b"ecg-learning-session-public-id-v1\x00"
_EXPORT_AUTH_KEY_DOMAIN = b"ecg-progress-export-authorization-v1\x00"
_PASSWORD_FINGERPRINT_DOMAIN = b"ecg-account-password-fingerprint-v1\x00"
_GUIDED_EVENT_REQUEST_FINGERPRINT_DOMAIN = (
    b"ecg-guided-event-request-fingerprint-v1\x00"
)
_LEARNING_RECORD_REFERENCE_DOMAIN = b"ecg-learning-record-reference-v1\x00"
_LOCAL_PUBLIC_REFERENCE_SECRET = (
    "ecg-tool-local-public-reference-secret-v1-change-in-production"
)
_LEARNING_RECORD_ECG_KEYS = frozenset({
    "caseId", "case_id", "ecgId", "ecg_id", "priorEcgId", "prior_ecg_id",
    "pendingCaseId", "pending_case_id", "feedbackCaseId", "feedback_case_id",
    "servedEcgs", "served_ecgs",
})
_LEARNING_RECORD_ITEM_KEYS = frozenset({
    "itemId", "item_id", "pendingItemId", "pending_item_id",
    "feedbackItemId", "feedback_item_id",
})
_LEARNING_RECORD_DISPLAY_KEYS = frozenset({"displayId", "display_id"})
_LEARNING_RECORD_EVENT_KEYS = frozenset({
    "eventKey", "event_key", "interactionId", "interaction_id",
})

_LEARNING_PREFERENCE_DEFAULTS: dict[str, Any] = {
    "trainingStage": "not_set",
    "primaryGoal": "build_fundamentals",
    "defaultSessionLength": 10,
    "rapidPace": "untimed",
    "guidanceLevel": "balanced",
    "reduceMotion": False,
    "largeControls": False,
}
_LEARNING_PREFERENCE_ALLOWED = {
    "trainingStage": {"not_set", "preclinical", "core_clerkship", "advanced_clerkship", "resident_review"},
    "primaryGoal": {"build_fundamentals", "exam_prep", "clinical_reading", "emergency_prioritization", "medication_safety"},
    "defaultSessionLength": {5, 10, 25, 50},
    "rapidPace": {"untimed", "ward", "emergency"},
    "guidanceLevel": {"step_by_step", "balanced", "minimal"},
    "reduceMotion": {False, True},
    "largeControls": {False, True},
}


# Only these authored Guided destinations may leave the learner store through
# the cross-mode resume projection. Pathway progress is a client-written
# record, so treating an arbitrary module/scene string as navigation would turn
# the resume endpoint into an open redirect in another form. The tuple is
# (pathway id, native scene prefix, authored scene count); Foundations owns its
# current scene inside the same-origin module and therefore has no scene query.
_GUIDED_RESUME_MODULES: dict[str, tuple[str, str | None, int]] = {
    "foundations": ("foundations-curriculum", None, 13),
    "leads-vectors": ("production-curriculum", "M02.S", 15),
    "rhythm-ectopy": ("production-curriculum", "M03.S", 16),
    "av-brady": ("production-curriculum", "m04-s", 11),
    "ventricular-conduction": ("production-curriculum", "m05-s", 11),
    "tachyarrhythmias": ("production-curriculum", "m06-s", 12),
    "chambers-voltage": ("production-curriculum", "m07-s", 8),
    "repolarization-safety": ("production-curriculum", "m08-s", 10),
    "ischemia-infarction": ("production-curriculum", "m09-s", 10),
    "integration-transfer": ("production-curriculum", "m10-s", 12),
}
_RESUME_MODE_ORDER = {"guided": 0, "training": 1, "rapid": 2, "clinical": 3}


# Anonymous-owner erasure and scheduled retention use the same reviewed table
# map as explicit guest deletion.  Keeping this allowlist centralized prevents a
# newly added mode ledger from being removed in one lifecycle path but orphaned
# in another.  Claim receipts are deliberately absent: they are authenticated
# account audit records, not anonymous-owner state.
_GUEST_CHILD_DELETE_SPECS = (
    (
        "learner_event_competencies",
        "event_id IN (SELECT event_id FROM learner_events WHERE owner_id = ?)",
    ),
    (
        "assessment_lease_cases",
        "lease_id IN (SELECT lease_id FROM assessment_leases WHERE owner_id = ?)",
    ),
    (
        "tutor_messages",
        "thread_id IN (SELECT thread_id FROM tutor_threads WHERE learner_id = ?)",
    ),
    (
        "rapid_round_answers",
        "round_id IN (SELECT round_id FROM rapid_rounds WHERE learner_id = ?)",
    ),
    (
        "clinical_shift_answers",
        "session_id IN (SELECT session_id FROM clinical_shift_sessions WHERE learner_id = ?)",
    ),
    (
        "training_campaign_answers",
        "campaign_id IN (SELECT campaign_id FROM training_campaigns WHERE learner_id = ?)",
    ),
    (
        "training_campaign_slots",
        "campaign_id IN (SELECT campaign_id FROM training_campaigns WHERE learner_id = ?)",
    ),
)
_GUEST_DIRECT_DELETE_TABLES = (
    "learner_events",
    "assessment_leases",
    "learner_preferences",
    "subskill_retention_events",
    "guided_learning_events",
    "objective_mastery",
    "subskill_mastery",
    "attempts",
    "pathway_progress",
    "tutor_threads",
    "review_sessions",
    "rapid_rounds",
    "clinical_shift_sessions",
    "training_campaigns",
    "learner_profiles",
)


class SchemaCompatibilityError(RuntimeError):
    """Raised before mutation when this binary cannot safely open the database."""


_PATHWAY_STATUS_RANK = {
    "not-started": 0,
    "viewed": 1,
    "skipped": 1,
    "attempted": 2,
    "needs-review": 3,
    "complete": 4,
}

# These modes use evidence ledgers with stronger provenance than the legacy
# objective summary. Clinical stays excluded even if a caller supplies a
# future-looking evidence label: reviewed Clinical content must gain an
# explicit, server-authorized exact receipt writer before it can affect mastery.
_LEGACY_MASTERY_EXCLUDED_MODES = frozenset(
    {"concept_practice", "rapid_practice", "tutorial", "clinical_decision"}
)


def _legacy_mastery_deltas(mode: str, grade: dict[str, Any]) -> dict[str, float]:
    if mode in _LEGACY_MASTERY_EXCLUDED_MODES:
        return {}
    return dict(grade.get("masteryDelta") or {})


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _guided_event_request_fingerprint(event: dict[str, Any]) -> str:
    """Bind a Guided idempotency key to the evidence operation it names."""

    semantic_request = {
        "moduleId": str(event["moduleId"]),
        "sceneId": str(event["sceneId"]),
        "interactionId": str(event["interactionId"]),
        "concept": str(event["concept"]),
        # These are competency/tag sets. Ordering differences from a retrying
        # client do not create a materially different learning event.
        "subskills": sorted(str(value) for value in event.get("subskills") or []),
        "score": float(event["score"]),
        "correct": bool(event["correct"]),
        "attempts": int(event["attempts"]),
        "assistance": str(event["assistance"]),
        "hintsUsed": int(event.get("hintsUsed", 0)),
        "confidence": (
            int(event["confidence"]) if event.get("confidence") is not None else None
        ),
        "evidenceLevel": str(event["evidenceLevel"]),
        "trainingPhase": event.get("trainingPhase"),
        "evidenceSource": event.get("evidenceSource"),
        "caseId": event.get("caseId"),
        "caseProvenance": str(event["caseProvenance"]),
        "caseEligible": bool(event["caseEligible"]),
        "misconceptions": sorted(
            str(value) for value in event.get("misconceptions") or []
        ),
        # Internal graders are allowed to strengthen evidence. A retry under a
        # different server authorization must conflict instead of replaying a
        # weaker/stronger receipt under the same key.
        "serverVerifiedScoring": event.get("_serverVerifiedScoring") is True,
        "retentionVerified": event.get("_retentionVerified") is True,
        "retentionMorphologyKey": event.get("_retentionMorphologyKey"),
    }
    encoded = json.dumps(
        semantic_request,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(
        _GUIDED_EVENT_REQUEST_FINGERPRINT_DOMAIN + encoded
    ).hexdigest()


def _legacy_guided_event_matches(
    row: sqlite3.Row,
    event: dict[str, Any],
    *,
    requested_level: str,
    effective_level: str,
) -> bool:
    """Best-effort compatibility check for rows created before fingerprints."""

    try:
        stored_subskills = sorted(
            str(value) for value in json.loads(row["subskills_json"])
        )
        stored_misconceptions = sorted(
            str(value) for value in json.loads(row["misconception_tags_json"])
        )
    except (TypeError, ValueError):
        return False
    return (
        str(row["module_id"]) == str(event["moduleId"])
        and str(row["scene_id"]) == str(event["sceneId"])
        and str(row["interaction_id"]) == str(event["interactionId"])
        and str(row["concept"]) == str(event["concept"])
        and stored_subskills
        == sorted(str(value) for value in event.get("subskills") or [])
        and float(row["score"]) == float(event["score"])
        and bool(row["correct"]) == bool(event["correct"])
        and int(row["attempts"]) == int(event["attempts"])
        and str(row["assistance"]) == str(event["assistance"])
        and int(row["hints_used"]) == int(event.get("hintsUsed", 0))
        and (
            int(row["confidence"]) if row["confidence"] is not None else None
        )
        == (int(event["confidence"]) if event.get("confidence") is not None else None)
        and str(row["requested_evidence_level"]) == requested_level
        and str(row["effective_evidence_level"]) == effective_level
        and row["case_id"] == event.get("caseId")
        and str(row["case_provenance"]) == str(event["caseProvenance"])
        and bool(row["case_eligible"]) == bool(event["caseEligible"])
        and stored_misconceptions
        == sorted(str(value) for value in event.get("misconceptions") or [])
    )


class LearningStore:
    def __init__(
        self,
        db_path: Path | str,
        public_reference_secret: str = _LOCAL_PUBLIC_REFERENCE_SECRET,
    ):
        self.db_path = str(db_path)
        if not str(public_reference_secret):
            raise ValueError("A public-reference secret is required")
        self._public_reference_secret = str(public_reference_secret)
        self._memory_conn: sqlite3.Connection | None = None
        self._case_packet_provider: Callable[[str], dict[str, Any] | None] | None = None
        # Serializes the shared in-memory connection across FastAPI's threadpool so
        # concurrent read-modify-write transactions can't interleave (V1 audit fix).
        self._lock = threading.Lock()
        if self.db_path == ":memory:":
            self._memory_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._memory_conn.row_factory = sqlite3.Row
            self._memory_conn.execute("PRAGMA foreign_keys=ON")
            configure_account_boundary(self._memory_conn)
        self.init_db()

    def set_case_packet_provider(
        self, provider: Callable[[str], dict[str, Any] | None]
    ) -> None:
        """Bind the read-only corpus lookup used by dynamic evidence ceilings.

        The store defaults to fail-closed when no provider is bound. Routers may
        call this repeatedly with the same repository method; no corpus state is
        mutated.
        """

        self._case_packet_provider = provider

    @contextmanager
    def connect(self):
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
        # File-backed: WAL + a busy timeout so concurrent writers wait instead of
        # raising "database is locked" (V1 audit fix).
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        configure_account_boundary(conn)
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            # Learner progress is acknowledged state. FULL keeps WAL commits
            # durable across host/persistent-disk power loss, not only process
            # crashes; performance changes must be justified by load evidence.
            conn.execute("PRAGMA synchronous=FULL")
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
            current_version = int(conn.execute("PRAGMA user_version").fetchone()[0])
            if current_version > LEARNER_SCHEMA_VERSION:
                raise SchemaCompatibilityError(
                    "learner database schema "
                    f"{current_version} is newer than this binary's supported "
                    f"schema {LEARNER_SCHEMA_VERSION}"
                )
            if current_version not in {0, 1, 2, 3, LEARNER_SCHEMA_VERSION}:
                raise SchemaCompatibilityError(
                    f"learner database schema {current_version} has no reviewed migration "
                    f"to {LEARNER_SCHEMA_VERSION}"
                )
            conn.executescript(
                """
                BEGIN IMMEDIATE;

                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL,
                    description TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS learner_profiles (
                    learner_id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_learner_profile_retention
                    ON learner_profiles(updated_at, learner_id);

                CREATE TABLE IF NOT EXISTS learner_preferences (
                    learner_id TEXT PRIMARY KEY,
                    training_stage TEXT NOT NULL DEFAULT 'not_set' CHECK (
                        training_stage IN ('not_set', 'preclinical', 'core_clerkship', 'advanced_clerkship', 'resident_review')
                    ),
                    primary_goal TEXT NOT NULL DEFAULT 'build_fundamentals' CHECK (
                        primary_goal IN ('build_fundamentals', 'exam_prep', 'clinical_reading', 'emergency_prioritization', 'medication_safety')
                    ),
                    default_session_length INTEGER NOT NULL DEFAULT 10 CHECK (
                        default_session_length IN (5, 10, 25, 50)
                    ),
                    rapid_pace TEXT NOT NULL DEFAULT 'untimed' CHECK (
                        rapid_pace IN ('untimed', 'ward', 'emergency')
                    ),
                    guidance_level TEXT NOT NULL DEFAULT 'balanced' CHECK (
                        guidance_level IN ('step_by_step', 'balanced', 'minimal')
                    ),
                    reduce_motion INTEGER NOT NULL DEFAULT 0 CHECK (reduce_motion IN (0, 1)),
                    large_controls INTEGER NOT NULL DEFAULT 0 CHECK (large_controls IN (0, 1)),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS objective_mastery (
                    learner_id TEXT NOT NULL,
                    objective TEXT NOT NULL,
                    mastery REAL NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    correct INTEGER NOT NULL DEFAULT 0,
                    high_confidence_wrong INTEGER NOT NULL DEFAULT 0,
                    last_practiced_at TEXT,
                    PRIMARY KEY (learner_id, objective)
                );

                CREATE TABLE IF NOT EXISTS attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    learner_id TEXT NOT NULL,
                    case_id TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    structured_answer_json TEXT NOT NULL,
                    free_text_answer TEXT NOT NULL,
                    confidence INTEGER NOT NULL,
                    hints_used INTEGER NOT NULL,
                    score REAL NOT NULL,
                    correct_objectives_json TEXT NOT NULL,
                    missed_objectives_json TEXT NOT NULL,
                    misconception_tags_json TEXT NOT NULL,
                    feedback TEXT NOT NULL,
                    registry_version TEXT NOT NULL DEFAULT 'legacy-unversioned',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_attempt_learner_created
                    ON attempts(learner_id, created_at);

                CREATE TABLE IF NOT EXISTS subskill_mastery (
                    learner_id TEXT NOT NULL,
                    concept TEXT NOT NULL,
                    subskill TEXT NOT NULL,
                    formative_score REAL NOT NULL DEFAULT 0.0,
                    independent_mastery REAL NOT NULL DEFAULT 0.15,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    independent_attempts INTEGER NOT NULL DEFAULT 0,
                    correct INTEGER NOT NULL DEFAULT 0,
                    high_confidence_wrong INTEGER NOT NULL DEFAULT 0,
                    last_practiced_at TEXT,
                    next_due_at TEXT,
                    stability_days REAL NOT NULL DEFAULT 0.0,
                    lapses INTEGER NOT NULL DEFAULT 0,
                    spaced_retrievals INTEGER NOT NULL DEFAULT 0,
                    distinct_eligible_ecgs INTEGER NOT NULL DEFAULT 0,
                    distinct_successful_ecgs INTEGER NOT NULL DEFAULT 0,
                    distinct_modes INTEGER NOT NULL DEFAULT 0,
                    distinct_morphologies INTEGER NOT NULL DEFAULT 0,
                    last_independent_at TEXT,
                    last_independent_correct INTEGER,
                    PRIMARY KEY (learner_id, concept, subskill)
                );

                CREATE TABLE IF NOT EXISTS subskill_retention_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guided_event_id INTEGER NOT NULL,
                    learner_id TEXT NOT NULL,
                    concept TEXT NOT NULL,
                    subskill TEXT NOT NULL,
                    case_id TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    morphology_key TEXT,
                    correct INTEGER NOT NULL,
                    registry_version TEXT NOT NULL DEFAULT 'legacy-unversioned',
                    occurred_at TEXT NOT NULL,
                    UNIQUE(guided_event_id, subskill)
                );
                CREATE INDEX IF NOT EXISTS idx_retention_competency
                    ON subskill_retention_events(learner_id, concept, subskill, occurred_at);

                CREATE TABLE IF NOT EXISTS guided_learning_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    learner_id TEXT NOT NULL,
                    module_id TEXT NOT NULL,
                    scene_id TEXT NOT NULL,
                    interaction_id TEXT NOT NULL,
                    concept TEXT NOT NULL,
                    subskills_json TEXT NOT NULL,
                    score REAL NOT NULL,
                    correct INTEGER NOT NULL,
                    attempts INTEGER NOT NULL,
                    assistance TEXT NOT NULL,
                    hints_used INTEGER NOT NULL DEFAULT 0,
                    confidence INTEGER,
                    requested_evidence_level TEXT NOT NULL,
                    effective_evidence_level TEXT NOT NULL,
                    case_id TEXT,
                    case_provenance TEXT NOT NULL,
                    case_eligible INTEGER NOT NULL,
                    misconception_tags_json TEXT NOT NULL DEFAULT '[]',
                    event_key TEXT,
                    request_fingerprint TEXT,
                    receipt_json TEXT NOT NULL DEFAULT '[]',
                    registry_version TEXT NOT NULL DEFAULT 'legacy-unversioned',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_guided_event_learner ON guided_learning_events(learner_id, created_at);

                CREATE TABLE IF NOT EXISTS pathway_progress (
                    learner_id TEXT NOT NULL,
                    pathway_id TEXT NOT NULL,
                    module_id TEXT NOT NULL,
                    scene_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    active_interaction_index INTEGER NOT NULL DEFAULT 0,
                    completed_action_ids_json TEXT NOT NULL DEFAULT '[]',
                    state_json TEXT NOT NULL DEFAULT '{}',
                    source TEXT NOT NULL DEFAULT 'server',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (learner_id, pathway_id, module_id, scene_id)
                );
                CREATE INDEX IF NOT EXISTS idx_pathway_progress_learner
                    ON pathway_progress(learner_id, pathway_id, updated_at);

                CREATE TABLE IF NOT EXISTS tutor_threads (
                    thread_id TEXT PRIMARY KEY,
                    learner_id TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    lesson_id TEXT,
                    case_id TEXT,
                    scope_key TEXT,
                    title TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_thread_learner ON tutor_threads(learner_id, updated_at);

                CREATE TABLE IF NOT EXISTS tutor_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    thread_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    actions_json TEXT NOT NULL DEFAULT '[]',
                    meta_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_msg_thread ON tutor_messages(thread_id, id);

                CREATE TABLE IF NOT EXISTS remote_tutor_quota_buckets (
                    scope TEXT NOT NULL,
                    key_hash TEXT NOT NULL,
                    window_start TEXT NOT NULL,
                    request_count INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (scope, key_hash, window_start)
                );
                CREATE INDEX IF NOT EXISTS idx_remote_tutor_quota_updated
                    ON remote_tutor_quota_buckets(updated_at);

                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    email_normalized TEXT,
                    email_verified_at TEXT,
                    email_two_factor_enabled INTEGER NOT NULL DEFAULT 0,
                    registration_reservation INTEGER NOT NULL DEFAULT 0,
                    account_origin TEXT NOT NULL DEFAULT 'established',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS auth_verification_budgets (
                    key_hash TEXT NOT NULL,
                    purpose_group TEXT NOT NULL,
                    window_started_at TEXT NOT NULL,
                    window_expires_at TEXT NOT NULL,
                    failure_count INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (key_hash, purpose_group)
                );
                CREATE INDEX IF NOT EXISTS idx_auth_verification_budget_expiry
                    ON auth_verification_budgets(window_expires_at, key_hash);

                CREATE TABLE IF NOT EXISTS auth_challenges (
                    challenge_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    purpose TEXT NOT NULL,
                    secret_hash TEXT NOT NULL,
                    credential_fingerprint TEXT,
                    context_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    consumed_at TEXT,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL,
                    last_sent_at TEXT NOT NULL,
                    send_count INTEGER NOT NULL DEFAULT 1
                );
                CREATE INDEX IF NOT EXISTS idx_auth_challenge_user
                    ON auth_challenges(user_id, purpose, created_at);
                CREATE INDEX IF NOT EXISTS idx_auth_challenge_expiry
                    ON auth_challenges(expires_at, consumed_at);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_auth_challenge_one_active
                    ON auth_challenges(user_id, purpose)
                    WHERE consumed_at IS NULL;

                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
                CREATE INDEX IF NOT EXISTS idx_sessions_expiry
                    ON sessions(expires_at, token);

                CREATE TABLE IF NOT EXISTS export_authorizations (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    session_hash TEXT NOT NULL,
                    password_fingerprint TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_export_authorization_owner
                    ON export_authorizations(user_id, session_hash, expires_at);
                CREATE INDEX IF NOT EXISTS idx_export_authorization_expiry
                    ON export_authorizations(expires_at, token_hash);

                CREATE TABLE IF NOT EXISTS maintenance_job_state (
                    job_name TEXT PRIMARY KEY,
                    next_run_at TEXT NOT NULL,
                    last_completed_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS maintenance_leases (
                    lease_name TEXT PRIMARY KEY,
                    token_hash TEXT NOT NULL,
                    acquired_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_maintenance_lease_expiry
                    ON maintenance_leases(expires_at);

                CREATE TABLE IF NOT EXISTS auth_registration_throttle (
                    scope TEXT NOT NULL,
                    key_hash TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    window_started_at TEXT NOT NULL,
                    blocked_until TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (scope, key_hash)
                );
                CREATE INDEX IF NOT EXISTS idx_registration_throttle_updated
                    ON auth_registration_throttle(updated_at);

                CREATE TABLE IF NOT EXISTS auth_login_throttle (
                    scope TEXT NOT NULL,
                    key_hash TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    window_started_at TEXT NOT NULL,
                    blocked_until TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (scope, key_hash)
                );
                CREATE INDEX IF NOT EXISTS idx_login_throttle_updated
                    ON auth_login_throttle(updated_at);

                CREATE TABLE IF NOT EXISTS review_sessions (
                    session_id TEXT PRIMARY KEY,
                    learner_id TEXT NOT NULL,
                    label TEXT,
                    objectives_json TEXT NOT NULL DEFAULT '[]',
                    target_mastery REAL NOT NULL DEFAULT 0.8,
                    max_cases INTEGER NOT NULL DEFAULT 30,
                    served_json TEXT NOT NULL DEFAULT '[]',
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_review_learner ON review_sessions(learner_id, status);

                CREATE TABLE IF NOT EXISTS rapid_rounds (
                    round_id TEXT PRIMARY KEY,
                    learner_id TEXT NOT NULL,
                    pace TEXT NOT NULL,
                    length INTEGER NOT NULL,
                    assessment_scope TEXT NOT NULL,
                    focus_concept TEXT,
                    focus_subskill TEXT,
                    context_key TEXT NOT NULL DEFAULT '',
                    exclusions_json TEXT NOT NULL DEFAULT '[]',
                    served_json TEXT NOT NULL DEFAULT '[]',
                    pending_case_id TEXT,
                    pending_manifest_json TEXT NOT NULL DEFAULT '{}',
                    feedback_case_id TEXT,
                    pending_started_at TEXT,
                    pending_deadline_at TEXT,
                    deadline_seconds INTEGER,
                    position INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_rapid_round_learner
                    ON rapid_rounds(learner_id, status, updated_at);

                CREATE TABLE IF NOT EXISTS rapid_round_answers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    round_id TEXT NOT NULL,
                    case_id TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    grade_json TEXT NOT NULL,
                    tutor_json TEXT NOT NULL DEFAULT '{}',
                    result_json TEXT NOT NULL,
                    trace_grade_json TEXT,
                    tested_manifest_json TEXT NOT NULL DEFAULT '{}',
                    receipts_json TEXT NOT NULL DEFAULT '[]',
                    integrity_status TEXT NOT NULL DEFAULT 'verified',
                    attempt_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(round_id, case_id)
                );
                CREATE INDEX IF NOT EXISTS idx_rapid_answers_round
                    ON rapid_round_answers(round_id, id);
                CREATE INDEX IF NOT EXISTS idx_rapid_answers_attempt
                    ON rapid_round_answers(attempt_id);

                CREATE TABLE IF NOT EXISTS clinical_shift_sessions (
                    session_id TEXT PRIMARY KEY,
                    learner_id TEXT NOT NULL,
                    lane TEXT NOT NULL,
                    tier TEXT NOT NULL,
                    focus_objective TEXT,
                    focus_subskill TEXT,
                    length INTEGER NOT NULL DEFAULT 5,
                    requested_length INTEGER NOT NULL DEFAULT 5,
                    available_length INTEGER NOT NULL DEFAULT 0,
                    length_reason TEXT,
                    served_json TEXT NOT NULL DEFAULT '[]',
                    served_ecgs_json TEXT NOT NULL DEFAULT '[]',
                    calibration_json TEXT NOT NULL DEFAULT '[]',
                    pending_item_id TEXT,
                    feedback_item_id TEXT,
                    pending_context_revealed INTEGER NOT NULL DEFAULT 0,
                    pending_first_look_json TEXT,
                    pending_step_answers_json TEXT NOT NULL DEFAULT '[]',
                    pending_orient_started_at TEXT,
                    pending_orient_deadline_at TEXT,
                    pending_decide_started_at TEXT,
                    pending_decide_deadline_at TEXT,
                    pending_decide_submitted_at TEXT,
                    position INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_shift_learner ON clinical_shift_sessions(learner_id, status);

                CREATE TABLE IF NOT EXISTS clinical_shift_answers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    ecg_id TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    grade_json TEXT NOT NULL,
                    receipts_json TEXT NOT NULL DEFAULT '[]',
                    score REAL NOT NULL,
                    correct INTEGER NOT NULL,
                    answer_time_ms INTEGER,
                    calibration_event_json TEXT,
                    attempt_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(session_id, item_id)
                );
                CREATE INDEX IF NOT EXISTS idx_shift_answers_session
                    ON clinical_shift_answers(session_id, id);
                CREATE INDEX IF NOT EXISTS idx_shift_answers_attempt
                    ON clinical_shift_answers(attempt_id);
                """
            )
            ensure_assessment_ledger_schema(conn)
            ensure_account_boundary_schema(conn)
            # Session credentials are stored only as SHA-256 lookup digests.
            # Invalidate pre-migration plaintext tokens instead of retaining a
            # raw reusable browser credential in the learner database.
            conn.execute(
                "DELETE FROM sessions WHERE length(token) != 64 "
                "OR token GLOB '*[^0-9a-f]*'"
            )
            # Additive migration for shift sessions created before guided→Clinical
            # handoffs carried a target objective.
            shift_columns = {row["name"] for row in conn.execute("PRAGMA table_info(clinical_shift_sessions)")}
            if "focus_objective" not in shift_columns:
                conn.execute("ALTER TABLE clinical_shift_sessions ADD COLUMN focus_objective TEXT")
            if "focus_subskill" not in shift_columns:
                conn.execute("ALTER TABLE clinical_shift_sessions ADD COLUMN focus_subskill TEXT")
            requested_length_was_missing = "requested_length" not in shift_columns
            additive_shift_columns = {
                "requested_length": "INTEGER NOT NULL DEFAULT 5",
                "available_length": "INTEGER NOT NULL DEFAULT 0",
                "length_reason": "TEXT",
                "served_ecgs_json": "TEXT NOT NULL DEFAULT '[]'",
                "pending_item_id": "TEXT",
                "feedback_item_id": "TEXT",
                "pending_context_revealed": "INTEGER NOT NULL DEFAULT 0",
                "pending_first_look_json": "TEXT",
                "pending_step_answers_json": "TEXT NOT NULL DEFAULT '[]'",
                "pending_orient_started_at": "TEXT",
                "pending_orient_deadline_at": "TEXT",
                "pending_decide_started_at": "TEXT",
                "pending_decide_deadline_at": "TEXT",
                "pending_decide_submitted_at": "TEXT",
            }
            for name, declaration in additive_shift_columns.items():
                if name not in shift_columns:
                    conn.execute(f"ALTER TABLE clinical_shift_sessions ADD COLUMN {name} {declaration}")
            # Existing sessions predate explicit request/availability metadata. Preserve
            # their effective length as the requested length rather than reporting the
            # migration default of five.
            if requested_length_was_missing:
                conn.execute("UPDATE clinical_shift_sessions SET requested_length = length")

            shift_answer_columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(clinical_shift_answers)")
            }
            if "receipts_json" not in shift_answer_columns:
                conn.execute(
                    "ALTER TABLE clinical_shift_answers "
                    "ADD COLUMN receipts_json TEXT NOT NULL DEFAULT '[]'"
                )

            guided_columns = {row["name"] for row in conn.execute("PRAGMA table_info(guided_learning_events)")}
            if "event_key" not in guided_columns:
                conn.execute("ALTER TABLE guided_learning_events ADD COLUMN event_key TEXT")
            if "request_fingerprint" not in guided_columns:
                conn.execute(
                    "ALTER TABLE guided_learning_events ADD COLUMN request_fingerprint TEXT"
                )
            if "receipt_json" not in guided_columns:
                conn.execute("ALTER TABLE guided_learning_events ADD COLUMN receipt_json TEXT NOT NULL DEFAULT '[]'")
            if "registry_version" not in guided_columns:
                conn.execute(
                    "ALTER TABLE guided_learning_events ADD COLUMN registry_version "
                    "TEXT NOT NULL DEFAULT 'legacy-unversioned'"
                )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_guided_event_idempotency "
                "ON guided_learning_events(learner_id, event_key) WHERE event_key IS NOT NULL"
            )

            tutor_columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(tutor_threads)")
            }
            if "scope_key" not in tutor_columns:
                conn.execute("ALTER TABLE tutor_threads ADD COLUMN scope_key TEXT")

            attempt_columns = {row["name"] for row in conn.execute("PRAGMA table_info(attempts)")}
            if "registry_version" not in attempt_columns:
                conn.execute(
                    "ALTER TABLE attempts ADD COLUMN registry_version "
                    "TEXT NOT NULL DEFAULT 'legacy-unversioned'"
                )
            retention_columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(subskill_retention_events)")
            }
            if "registry_version" not in retention_columns:
                conn.execute(
                    "ALTER TABLE subskill_retention_events ADD COLUMN registry_version "
                    "TEXT NOT NULL DEFAULT 'legacy-unversioned'"
                )

            rapid_round_columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(rapid_rounds)")
            }
            if "pending_manifest_json" not in rapid_round_columns:
                conn.execute(
                    "ALTER TABLE rapid_rounds "
                    "ADD COLUMN pending_manifest_json TEXT NOT NULL DEFAULT '{}'"
                )
            rapid_answer_columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(rapid_round_answers)")
            }
            if "tested_manifest_json" not in rapid_answer_columns:
                conn.execute(
                    "ALTER TABLE rapid_round_answers "
                    "ADD COLUMN tested_manifest_json TEXT NOT NULL DEFAULT '{}'"
                )
            if "integrity_status" not in rapid_answer_columns:
                conn.execute(
                    "ALTER TABLE rapid_round_answers "
                    "ADD COLUMN integrity_status TEXT NOT NULL DEFAULT 'verified'"
                )
            # Any pre-atomic answer with an empty receipt ledger is ambiguous:
            # the former two-phase route may have crashed before, during, or
            # after mastery events. Preserve it for audit, but never guess at a
            # repair that could double-apply evidence.
            conn.execute(
                "UPDATE rapid_round_answers SET integrity_status = 'legacy_incomplete' "
                "WHERE integrity_status = 'verified' AND receipts_json = '[]'"
            )

            subskill_columns = {row["name"] for row in conn.execute("PRAGMA table_info(subskill_mastery)")}
            additive_retention_columns = {
                "next_due_at": "TEXT",
                "stability_days": "REAL NOT NULL DEFAULT 0.0",
                "lapses": "INTEGER NOT NULL DEFAULT 0",
                "spaced_retrievals": "INTEGER NOT NULL DEFAULT 0",
                "distinct_eligible_ecgs": "INTEGER NOT NULL DEFAULT 0",
                "distinct_successful_ecgs": "INTEGER NOT NULL DEFAULT 0",
                "distinct_modes": "INTEGER NOT NULL DEFAULT 0",
                "distinct_morphologies": "INTEGER NOT NULL DEFAULT 0",
                "last_independent_at": "TEXT",
                "last_independent_correct": "INTEGER",
            }
            for name, declaration in additive_retention_columns.items():
                if name not in subskill_columns:
                    conn.execute(f"ALTER TABLE subskill_mastery ADD COLUMN {name} {declaration}")

            user_columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(users)")
            }
            additive_user_columns = {
                "email_normalized": "TEXT",
                "email_verified_at": "TEXT",
                "email_two_factor_enabled": "INTEGER NOT NULL DEFAULT 0",
                "registration_reservation": "INTEGER NOT NULL DEFAULT 0",
                "account_origin": "TEXT NOT NULL DEFAULT 'established'",
            }
            for name, declaration in additive_user_columns.items():
                if name not in user_columns:
                    conn.execute(f"ALTER TABLE users ADD COLUMN {name} {declaration}")
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_normalized_unique "
                "ON users(email_normalized) WHERE email_normalized IS NOT NULL"
            )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_auth_challenge_one_active "
                "ON auth_challenges(user_id, purpose) WHERE consumed_at IS NULL"
            )

            conn.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at, description) "
                "VALUES (?, ?, ?)",
                (
                    LEARNER_SCHEMA_VERSION,
                    utc_now(),
                    "Versioned baseline v4: durable privacy-preserving account-generation retirement guards",
                ),
            )
            conn.execute(f"PRAGMA user_version={LEARNER_SCHEMA_VERSION}")

    def ensure_profile(self, learner_id: str = "demo", display_name: str | None = None) -> dict[str, Any]:
        now = utc_now()
        supplied_name = (display_name or "").strip()
        default_name = (
            "Guest learner"
            if learner_id == "demo" or learner_id.startswith("g_")
            else "Learner"
        )
        resolved_name = supplied_name or default_name
        with self.connect() as conn:
            # Profile creation is a compare-and-insert operation at the database
            # boundary. A SELECT followed by INSERT lets simultaneous first-page
            # requests both observe a missing learner and one then violates the
            # primary key. SQLite serializes these idempotent writes safely.
            conn.execute(
                "INSERT OR IGNORE INTO learner_profiles "
                "(learner_id, display_name, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (learner_id, resolved_name, now, now),
            )
            if supplied_name:
                conn.execute(
                    "UPDATE learner_profiles SET display_name = ?, updated_at = ? "
                    "WHERE learner_id = ? AND display_name <> ?",
                    (supplied_name, now, learner_id, supplied_name),
                )
            # Run this on every idempotent ensure so newly introduced default
            # objectives are backfilled without a separate learner migration.
            for objective, mastery in DEFAULT_MASTERY.items():
                conn.execute(
                    "INSERT OR IGNORE INTO objective_mastery "
                    "(learner_id, objective, mastery) VALUES (?, ?, ?)",
                    (learner_id, objective, mastery),
                )
        return self.get_profile(learner_id)

    @staticmethod
    def _learning_preferences_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "trainingStage": str(row["training_stage"]),
            "primaryGoal": str(row["primary_goal"]),
            "defaultSessionLength": int(row["default_session_length"]),
            "rapidPace": str(row["rapid_pace"]),
            "guidanceLevel": str(row["guidance_level"]),
            "reduceMotion": bool(row["reduce_motion"]),
            "largeControls": bool(row["large_controls"]),
            "updatedAt": str(row["updated_at"]),
        }

    def get_learning_preferences(self, learner_id: str) -> dict[str, Any]:
        self.ensure_profile(learner_id)
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM learner_preferences WHERE learner_id = ?",
                (learner_id,),
            ).fetchone()
        if row is None:
            # Reading preferences must not manufacture learner activity. In
            # particular, the application shell reads this endpoint for signed
            # in learners, and a default row would make an untouched guest look
            # as if they had work worth claiming. Defaults remain a projection
            # until the learner intentionally saves a preference.
            return {**_LEARNING_PREFERENCE_DEFAULTS, "updatedAt": None}
        return self._learning_preferences_dict(row)

    def update_learning_preferences(
        self,
        learner_id: str,
        updates: dict[str, Any],
    ) -> dict[str, Any]:
        if not updates:
            return self.get_learning_preferences(learner_id)
        columns = {
            "trainingStage": "training_stage",
            "primaryGoal": "primary_goal",
            "defaultSessionLength": "default_session_length",
            "rapidPace": "rapid_pace",
            "guidanceLevel": "guidance_level",
            "reduceMotion": "reduce_motion",
            "largeControls": "large_controls",
        }
        normalized: dict[str, Any] = {}
        for key, value in updates.items():
            if key not in columns:
                raise ValueError(f"Unsupported learning preference: {key}")
            if key in {"reduceMotion", "largeControls"}:
                if not isinstance(value, bool):
                    raise ValueError(f"{key} must be a boolean")
                normalized[key] = int(value)
            elif key == "defaultSessionLength":
                if isinstance(value, bool) or not isinstance(value, int):
                    raise ValueError("defaultSessionLength must be an allowed integer")
                if value not in _LEARNING_PREFERENCE_ALLOWED[key]:
                    raise ValueError("Unsupported default session length")
                normalized[key] = value
            else:
                if not isinstance(value, str) or value not in _LEARNING_PREFERENCE_ALLOWED[key]:
                    raise ValueError(f"Unsupported {key}")
                normalized[key] = value
        now = utc_now()
        current = self.get_learning_preferences(learner_id)
        merged = {
            **{key: current[key] for key in _LEARNING_PREFERENCE_DEFAULTS},
            **{
                key: bool(value) if key in {"reduceMotion", "largeControls"} else value
                for key, value in normalized.items()
            },
        }
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO learner_preferences "
                "(learner_id, training_stage, primary_goal, default_session_length, "
                "rapid_pace, guidance_level, reduce_motion, large_controls, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(learner_id) DO UPDATE SET "
                "training_stage = excluded.training_stage, "
                "primary_goal = excluded.primary_goal, "
                "default_session_length = excluded.default_session_length, "
                "rapid_pace = excluded.rapid_pace, "
                "guidance_level = excluded.guidance_level, "
                "reduce_motion = excluded.reduce_motion, "
                "large_controls = excluded.large_controls, "
                "updated_at = excluded.updated_at",
                (
                    learner_id,
                    merged["trainingStage"],
                    merged["primaryGoal"],
                    merged["defaultSessionLength"],
                    merged["rapidPace"],
                    merged["guidanceLevel"],
                    int(merged["reduceMotion"]),
                    int(merged["largeControls"]),
                    now,
                    now,
                ),
            )
            conn.execute(
                "UPDATE learner_profiles SET updated_at = ? WHERE learner_id = ?",
                (now, learner_id),
            )
            row = conn.execute(
                "SELECT * FROM learner_preferences WHERE learner_id = ?",
                (learner_id,),
            ).fetchone()
        if row is None:
            raise RuntimeError("Learning preferences could not be saved")
        return self._learning_preferences_dict(row)

    def get_profile(self, learner_id: str = "demo") -> dict[str, Any]:
        result: dict[str, Any] | None = None
        with self.connect() as conn:
            profile = conn.execute(
                "SELECT learner_id, display_name, created_at, updated_at FROM learner_profiles WHERE learner_id = ?",
                (learner_id,),
            ).fetchone()
            if not profile:
                result = None
            else:
                mastery_rows = conn.execute(
                    """
                    SELECT objective, mastery, attempts, correct, high_confidence_wrong, last_practiced_at
                    FROM objective_mastery WHERE learner_id = ?
                    ORDER BY mastery ASC, attempts ASC
                    """,
                    (learner_id,),
                ).fetchall()
                attempts = conn.execute(
                    """
                    SELECT case_id, mode, score, confidence, misconception_tags_json, created_at
                    FROM attempts WHERE learner_id = ?
                    ORDER BY id DESC LIMIT 12
                    """,
                    (learner_id,),
                ).fetchall()
                attempt_count = int(
                    conn.execute(
                        "SELECT COUNT(*) AS n FROM attempts WHERE learner_id = ?",
                        (learner_id,),
                    ).fetchone()["n"]
                )
                misconceptions = self._misconception_counts(conn, learner_id)
                subskill_rows = conn.execute(
                    """
                    SELECT concept, subskill, formative_score, independent_mastery,
                           attempts, independent_attempts, correct, high_confidence_wrong,
                           last_practiced_at, next_due_at, stability_days, lapses,
                           spaced_retrievals, distinct_eligible_ecgs,
                           distinct_successful_ecgs, distinct_modes,
                           distinct_morphologies, last_independent_at,
                           last_independent_correct
                    FROM subskill_mastery WHERE learner_id = ?
                    ORDER BY independent_mastery ASC, formative_score ASC, attempts ASC
                    """,
                    (learner_id,),
                ).fetchall()
                as_of = parse_instant(utc_now()) or datetime.now(UTC)
                subskill_profile: list[dict[str, Any]] = []
                for row in subskill_rows:
                    retention_row = {
                        "independentAttempts": row["independent_attempts"],
                        "nextDueAt": row["next_due_at"],
                        "stabilityDays": row["stability_days"],
                        "lapses": row["lapses"],
                        "spacedRetrievals": row["spaced_retrievals"],
                        "distinctEligibleEcgs": row["distinct_eligible_ecgs"],
                        "distinctSuccessfulEcgs": row["distinct_successful_ecgs"],
                        "distinctModes": row["distinct_modes"],
                        "distinctMorphologies": row["distinct_morphologies"],
                        "lastIndependentAt": row["last_independent_at"],
                        "lastIndependentCorrect": (
                            bool(row["last_independent_correct"])
                            if row["last_independent_correct"] is not None
                            else None
                        ),
                    }
                    due = due_snapshot(retention_row, as_of=as_of)
                    subskill_profile.append({
                        "concept": row["concept"],
                        "subskill": row["subskill"],
                        "formativeScore": round(row["formative_score"], 3),
                        "independentMastery": round(row["independent_mastery"], 3),
                        "attempts": row["attempts"],
                        "independentAttempts": row["independent_attempts"],
                        "correct": row["correct"],
                        "highConfidenceWrong": row["high_confidence_wrong"],
                        "lastPracticedAt": row["last_practiced_at"],
                        **retention_row,
                        "dueState": due["dueState"],
                        "isDue": due["isDue"],
                        "overdueDays": due["overdueDays"],
                        "daysUntilDue": due["daysUntilDue"],
                        "retentionUncertainty": retention_uncertainty(retention_row, as_of=as_of),
                    })
                result = {
                    "learnerId": profile["learner_id"],
                    "displayName": profile["display_name"],
                    "createdAt": profile["created_at"],
                    "updatedAt": profile["updated_at"],
                    "attemptCount": attempt_count,
                    "mastery": [
                        {
                            "objective": row["objective"],
                            "mastery": round(row["mastery"], 3),
                            "attempts": row["attempts"],
                            "correct": row["correct"],
                            "highConfidenceWrong": row["high_confidence_wrong"],
                            "lastPracticedAt": row["last_practiced_at"],
                        }
                        for row in mastery_rows
                    ],
                    "subskillMastery": subskill_profile,
                    "recentAttempts": [
                        {
                            "caseId": self._learning_record_ecg_reference(
                                learner_id, row["case_id"]
                            ),
                            "mode": row["mode"],
                            "score": round(row["score"], 3),
                            "confidence": row["confidence"],
                            "misconceptions": json.loads(row["misconception_tags_json"]),
                            "createdAt": row["created_at"],
                        }
                        for row in attempts
                    ],
                    "misconceptions": misconceptions,
                    "weakObjectives": [
                        row["objective"] for row in mastery_rows if row["mastery"] < 0.45
                    ][:8],
                }
        if result is None:
            return self.ensure_profile(learner_id)
        return result

    @staticmethod
    def _pathway_progress_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "pathwayId": row["pathway_id"],
            "moduleId": row["module_id"],
            "sceneId": row["scene_id"],
            "status": row["status"],
            "activeInteractionIndex": int(row["active_interaction_index"]),
            "completedActionIds": json.loads(row["completed_action_ids_json"]),
            "state": json.loads(row["state_json"]),
            "source": row["source"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    def get_pathway_progress(
        self, learner_id: str, pathway_id: str | None = None
    ) -> list[dict[str, Any]]:
        self.ensure_profile(learner_id)
        sql = (
            "SELECT pathway_id, module_id, scene_id, status, active_interaction_index, "
            "completed_action_ids_json, state_json, source, created_at, updated_at "
            "FROM pathway_progress WHERE learner_id = ?"
        )
        params: list[Any] = [learner_id]
        if pathway_id:
            sql += " AND pathway_id = ?"
            params.append(pathway_id)
        sql += " ORDER BY pathway_id, module_id, scene_id"
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._pathway_progress_dict(row) for row in rows]

    @staticmethod
    def _guided_resume_destination(
        pathway_id: str, module_id: str, scene_id: str
    ) -> dict[str, Any] | None:
        authored = _GUIDED_RESUME_MODULES.get(module_id)
        if not authored:
            return None
        expected_pathway, scene_prefix, scene_count = authored
        if pathway_id != expected_pathway:
            return None
        if scene_prefix is None:
            return {
                "kind": "guided",
                "moduleId": module_id,
                "sceneId": None,
            }
        prefix = scene_prefix
        if not scene_id.startswith(prefix):
            return None
        ordinal = scene_id[len(prefix) :]
        if not ordinal.isdigit() or not 0 <= int(ordinal) < scene_count:
            return None
        return {
            "kind": "guided",
            "moduleId": module_id,
            "sceneId": scene_id,
        }

    @staticmethod
    def _resume_timestamp(value: str | None) -> float:
        if not value:
            return float("-inf")
        try:
            parsed = parse_instant(value)
            return parsed.timestamp() if parsed is not None else float("-inf")
        except (TypeError, ValueError):
            return float("-inf")

    def get_learning_resume_snapshot(self, learner_id: str) -> dict[str, Any]:
        """Project the owner's resumable work without mutating mode state.

        The four mode reads share one deferred SQLite transaction, so a
        concurrent submit cannot produce a dashboard assembled from different
        commits. Only a structured, allowlisted destination leaves this method:
        assessment ids, case ids, answer keys, context keys, and arbitrary URLs
        are deliberately absent.
        """

        snapshot_at = utc_now()
        snapshot_instant = self._resume_timestamp(snapshot_at)
        candidates: list[dict[str, Any]] = []

        with self.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN")
            tables = {
                str(row["name"])
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }

            guided_rows = conn.execute(
                "SELECT pathway_id, module_id, scene_id, status, state_json, "
                "created_at, updated_at FROM pathway_progress WHERE learner_id = ? "
                "AND pathway_id IN ('foundations-curriculum', 'production-curriculum') "
                "ORDER BY updated_at DESC, created_at DESC, pathway_id ASC, "
                "module_id ASC, scene_id ASC",
                (learner_id,),
            ).fetchall()
            guided_row: sqlite3.Row | None = None
            guided_destination: dict[str, Any] | None = None
            for row in guided_rows:
                if row["status"] not in {"viewed", "attempted", "needs-review"}:
                    continue
                destination = self._guided_resume_destination(
                    str(row["pathway_id"]),
                    str(row["module_id"]),
                    str(row["scene_id"]),
                )
                if destination:
                    guided_row = row
                    guided_destination = destination
                    break
            if guided_row is not None and guided_destination is not None:
                module_id = str(guided_row["module_id"])
                total = _GUIDED_RESUME_MODULES[module_id][2]
                if module_id == "foundations":
                    try:
                        state = json.loads(guided_row["state_json"] or "{}")
                    except (TypeError, json.JSONDecodeError):
                        state = {}
                    try:
                        completed = int(state.get("completedScenes") or 0)
                    except (TypeError, ValueError):
                        completed = 0
                else:
                    completed = sum(
                        1
                        for row in guided_rows
                        if row["module_id"] == module_id
                        and row["status"] == "complete"
                        and self._guided_resume_destination(
                            str(row["pathway_id"]),
                            str(row["module_id"]),
                            str(row["scene_id"]),
                        )
                    )
                candidates.append(
                    {
                        "mode": "guided",
                        "phase": "in_progress",
                        "completed": max(0, min(completed, total)),
                        "total": total,
                        "updatedAt": str(guided_row["updated_at"]),
                        "destination": guided_destination,
                        "_priority": 1,
                    }
                )

            if "training_campaigns" in tables:
                training = conn.execute(
                    "SELECT concept_id, subskill, length, position, feedback_case_id, "
                    "status, updated_at FROM training_campaigns WHERE learner_id = ? "
                    "AND (status = 'active' OR feedback_case_id IS NOT NULL) "
                    "ORDER BY updated_at DESC, created_at DESC, campaign_id DESC LIMIT 1",
                    (learner_id,),
                ).fetchone()
                if training:
                    total = max(0, int(training["length"]))
                    has_feedback = training["feedback_case_id"] is not None
                    candidates.append(
                        {
                            "mode": "training",
                            "phase": "feedback" if has_feedback else "in_progress",
                            "completed": max(0, min(int(training["position"]), total)),
                            "total": total,
                            "updatedAt": str(training["updated_at"]),
                            "destination": {"kind": "training"},
                            "_priority": 2 if has_feedback else 1,
                        }
                    )

            rapid = conn.execute(
                "SELECT length, position, feedback_case_id, pending_deadline_at, "
                "status, updated_at FROM rapid_rounds WHERE learner_id = ? "
                "AND (status = 'active' OR feedback_case_id IS NOT NULL) "
                "ORDER BY updated_at DESC, created_at DESC, round_id DESC LIMIT 1",
                (learner_id,),
            ).fetchone()
            if rapid:
                total = max(0, int(rapid["length"]))
                deadline = rapid["pending_deadline_at"]
                has_running_deadline = (
                    rapid["status"] == "active"
                    and self._resume_timestamp(deadline) > snapshot_instant
                )
                has_feedback = rapid["feedback_case_id"] is not None
                candidates.append(
                    {
                        "mode": "rapid",
                        "phase": "deadline" if has_running_deadline else "feedback" if has_feedback else "in_progress",
                        "completed": max(0, min(int(rapid["position"]), total)),
                        "total": total,
                        "updatedAt": str(rapid["updated_at"]),
                        "destination": {"kind": "rapid"},
                        "_priority": 3 if has_running_deadline else 2 if has_feedback else 1,
                    }
                )

            clinical = conn.execute(
                "SELECT length, position, feedback_item_id, pending_orient_deadline_at, "
                "pending_decide_deadline_at, status, updated_at "
                "FROM clinical_shift_sessions WHERE learner_id = ? "
                "AND (status = 'active' OR feedback_item_id IS NOT NULL) "
                "ORDER BY updated_at DESC, created_at DESC, session_id DESC LIMIT 1",
                (learner_id,),
            ).fetchone()
            if clinical:
                total = max(0, int(clinical["length"]))
                deadlines = (
                    clinical["pending_orient_deadline_at"],
                    clinical["pending_decide_deadline_at"],
                )
                has_running_deadline = clinical["status"] == "active" and any(
                    self._resume_timestamp(value) > snapshot_instant
                    for value in deadlines
                )
                has_feedback = clinical["feedback_item_id"] is not None
                candidates.append(
                    {
                        "mode": "clinical",
                        "phase": "deadline" if has_running_deadline else "feedback" if has_feedback else "in_progress",
                        "completed": max(0, min(int(clinical["position"]), total)),
                        "total": total,
                        "updatedAt": str(clinical["updated_at"]),
                        "destination": {"kind": "clinical"},
                        "_priority": 3 if has_running_deadline else 2 if has_feedback else 1,
                    }
                )

        candidates.sort(
            key=lambda item: (
                -int(item["_priority"]),
                -self._resume_timestamp(str(item["updatedAt"])),
                _RESUME_MODE_ORDER[str(item["mode"])],
            )
        )
        for candidate in candidates:
            candidate.pop("_priority", None)
        return {
            "version": "learning-resume-v1",
            "generatedAt": snapshot_at,
            "primary": candidates[0] if candidates else None,
            "additional": candidates[1:],
        }

    def upsert_pathway_progress(
        self,
        learner_id: str,
        items: list[dict[str, Any]],
        *,
        source: str = "server",
        merge: bool = True,
    ) -> list[dict[str, Any]]:
        """Idempotently persist per-scene/action pathway state.

        Merge mode is intentionally monotonic for completion and action receipts,
        which makes a one-time guest import safe to retry without downgrading work
        already completed on another device.
        """
        self.ensure_profile(learner_id)
        now = utc_now()
        keys: list[tuple[str, str, str]] = []
        with self.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            for item in items:
                key = (item["pathwayId"], item["moduleId"], item["sceneId"])
                keys.append(key)
                existing = conn.execute(
                    "SELECT * FROM pathway_progress WHERE learner_id = ? AND pathway_id = ? "
                    "AND module_id = ? AND scene_id = ?",
                    (learner_id, *key),
                ).fetchone()
                incoming_status = str(item["status"])
                incoming_actions = list(dict.fromkeys(item.get("completedActionIds") or []))
                incoming_state = dict(item.get("state") or {})
                incoming_index = int(item.get("activeInteractionIndex", 0))

                if existing and merge:
                    existing_status = str(existing["status"])
                    status = (
                        incoming_status
                        if _PATHWAY_STATUS_RANK[incoming_status] >= _PATHWAY_STATUS_RANK[existing_status]
                        else existing_status
                    )
                    actions = list(dict.fromkeys(
                        json.loads(existing["completed_action_ids_json"]) + incoming_actions
                    ))
                    state = {**json.loads(existing["state_json"]), **incoming_state}
                    active_index = max(int(existing["active_interaction_index"]), incoming_index)
                else:
                    status = incoming_status
                    actions = incoming_actions
                    state = incoming_state
                    active_index = incoming_index

                encoded_actions = json.dumps(actions, sort_keys=True)
                encoded_state = json.dumps(state, sort_keys=True)
                if existing:
                    unchanged = (
                        existing["status"] == status
                        and int(existing["active_interaction_index"]) == active_index
                        and existing["completed_action_ids_json"] == encoded_actions
                        and existing["state_json"] == encoded_state
                        and existing["source"] == source
                    )
                    if not unchanged:
                        conn.execute(
                            "UPDATE pathway_progress SET status = ?, active_interaction_index = ?, "
                            "completed_action_ids_json = ?, state_json = ?, source = ?, updated_at = ? "
                            "WHERE learner_id = ? AND pathway_id = ? AND module_id = ? AND scene_id = ?",
                            (
                                status, active_index, encoded_actions, encoded_state, source, now,
                                learner_id, *key,
                            ),
                        )
                else:
                    conn.execute(
                        "INSERT INTO pathway_progress (learner_id, pathway_id, module_id, scene_id, status, "
                        "active_interaction_index, completed_action_ids_json, state_json, source, created_at, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            learner_id, *key, status, active_index, encoded_actions,
                            encoded_state, source, now, now,
                        ),
                    )
            conn.execute(
                "UPDATE learner_profiles SET updated_at = ? WHERE learner_id = ?", (now, learner_id)
            )

            results: list[dict[str, Any]] = []
            for pathway_id, module_id, scene_id in keys:
                row = conn.execute(
                    "SELECT * FROM pathway_progress WHERE learner_id = ? AND pathway_id = ? "
                    "AND module_id = ? AND scene_id = ?",
                    (learner_id, pathway_id, module_id, scene_id),
                ).fetchone()
                if row:
                    results.append(self._pathway_progress_dict(row))
        return results

    def save_guided_learning_event(
        self,
        learner_id: str,
        event: dict[str, Any],
        *,
        occurred_at: datetime | str | None = None,
        _connection: sqlite3.Connection | None = None,
    ) -> dict[str, Any]:
        # Rapid finalization supplies its already-locked connection so the
        # guided event, retention receipt, answer ledger, generic attempt, and
        # round advance share one transaction. Other callers retain the public
        # self-contained transaction boundary.
        if _connection is None:
            self.ensure_profile(learner_id)
        event_time = parse_instant(occurred_at) or datetime.now(UTC)
        now = event_time.isoformat()
        event_key = str(event.get("eventKey") or "").strip()
        if not event_key:
            # A deterministic fallback protects older clients from network-retry
            # replay while still allowing a real subsequent attempt (whose attempt
            # count, response result, or assistance state will differ).
            idempotent_payload = {
                key: event.get(key)
                for key in (
                    "moduleId", "sceneId", "interactionId", "concept", "score", "correct",
                    "attempts", "assistance", "hintsUsed", "confidence", "evidenceLevel",
                    "trainingPhase", "evidenceSource", "caseId", "caseProvenance",
                    "caseEligible", "misconceptions",
                )
            }
            idempotent_payload["subskills"] = sorted(event.get("subskills") or [])
            event_key = hashlib.sha256(
                json.dumps(idempotent_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
        normalized_event_id = guided_interaction_event_id(learner_id, event_key)
        request_fingerprint = _guided_event_request_fingerprint(event)
        requested_level = str(event["evidenceLevel"])
        assistance = str(event["assistance"])
        provenance = str(event["caseProvenance"])
        case_eligible = bool(event["caseEligible"])
        server_verified_scoring = event.get("_serverVerifiedScoring") is True
        visual_subskills = {"recognize", "localize", "measure", "discriminate", "synthesize"}
        effective_level = requested_level
        if effective_level == "independent_transfer" and not server_verified_scoring:
            # Never turn a browser-asserted score/correct flag into independent
            # mastery. Only a mode-specific server grader may set the private
            # verification marker on its direct storage call.
            effective_level = "guided"
        definition = objective_definition(str(event["concept"]))
        if str(event["moduleId"]) == "train" and effective_level == "independent_transfer":
            # Training recognition and labeled build phases remain formative.
            # Independent transfer is limited to one exact, server-graded task
            # whose evidence source is appropriate for that subskill.
            training_subskills = list(event["subskills"])
            allowed_training_sources = {
                "localize": "trace_native",
                "measure": "trace_native",
                "discriminate": "labeled_contrast_task",
                "explain_mechanism": "curated_mechanism_task",
                "calibrate_confidence": "confidence_commit",
            }
            exact_server_task_transfer = (
                event.get("trainingPhase") == "transfer"
                and len(training_subskills) == 1
                and event.get("evidenceSource")
                == allowed_training_sources.get(training_subskills[0])
            )
            if not exact_server_task_transfer:
                effective_level = "guided"
        if effective_level == "independent_transfer" and definition:
            if any(
                str(subskill) not in definition.allowed_subskills
                for subskill in event.get("subskills") or []
            ):
                effective_level = "guided"
            source_unlocked = True
            if definition.id in DYNAMIC_SOURCE_UNAVAILABLE:
                packet = None
                case_id = str(event.get("caseId") or "")
                if self._case_packet_provider is not None and case_id:
                    try:
                        packet = self._case_packet_provider(case_id)
                    except Exception:
                        packet = None
                source_unlocked = audited_source_packet_supports_objective(packet, definition.id)
            if definition.unavailable_reason or not source_unlocked:
                effective_level = "guided"
        if assistance != "independent" and effective_level == "independent_transfer":
            effective_level = "guided"
        if (visual_subskills & set(event["subskills"])) and (provenance not in {"real_eligible", "real_reviewed"} or not case_eligible):
            if effective_level == "independent_transfer":
                effective_level = "guided"
        if "apply_in_context" in set(event["subskills"]) and (provenance != "real_reviewed" or not case_eligible):
            if effective_level == "independent_transfer":
                effective_level = "guided"

        score = float(event["score"])
        correct = bool(event["correct"])
        confidence = event.get("confidence")
        receipts: list[dict[str, Any]] = []
        with (self.connect() if _connection is None else nullcontext(_connection)) as conn:
            if _connection is None and not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT id, module_id, scene_id, interaction_id, concept, subskills_json, "
                "score, correct, attempts, assistance, hints_used, confidence, "
                "requested_evidence_level, effective_evidence_level, case_id, "
                "case_provenance, case_eligible, misconception_tags_json, "
                "request_fingerprint, receipt_json, registry_version "
                "FROM guided_learning_events WHERE learner_id = ? AND event_key = ?",
                (learner_id, event_key),
            ).fetchone()
            if existing:
                stored_fingerprint = existing["request_fingerprint"]
                replay_matches = (
                    hmac.compare_digest(str(stored_fingerprint), request_fingerprint)
                    if stored_fingerprint
                    else _legacy_guided_event_matches(
                        existing,
                        event,
                        requested_level=requested_level,
                        effective_level=effective_level,
                    )
                )
                if not replay_matches:
                    raise IdempotencyConflictError(
                        "event_key was already used for different Guided evidence"
                    )
                return {
                    "eventId": int(existing["id"]),
                    "eventKey": event_key,
                    "replay": True,
                    "requestedEvidenceLevel": existing["requested_evidence_level"],
                    "effectiveEvidenceLevel": existing["effective_evidence_level"],
                    "registryVersion": existing["registry_version"],
                    "receipts": json.loads(existing["receipt_json"] or "[]"),
                }
            cursor = conn.execute(
                """
                INSERT INTO guided_learning_events (
                    learner_id, module_id, scene_id, interaction_id, concept,
                    subskills_json, score, correct, attempts, assistance, hints_used,
                    confidence, requested_evidence_level, effective_evidence_level,
                    case_id, case_provenance, case_eligible, misconception_tags_json,
                    event_key, request_fingerprint, registry_version, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    learner_id, event["moduleId"], event["sceneId"], event["interactionId"], event["concept"],
                    json.dumps(event["subskills"]), score, 1 if correct else 0, int(event["attempts"]), assistance,
                    int(event.get("hintsUsed", 0)), confidence, requested_level, effective_level, event.get("caseId"),
                    provenance, 1 if case_eligible else 0, json.dumps(event.get("misconceptions", [])),
                    event_key, request_fingerprint, REGISTRY_VERSION, now,
                ),
            )
            for subskill in event["subskills"]:
                current = conn.execute(
                    """SELECT formative_score, independent_mastery, attempts, independent_attempts,
                              correct, high_confidence_wrong, next_due_at, stability_days,
                              lapses, spaced_retrievals, distinct_eligible_ecgs,
                              distinct_successful_ecgs, distinct_modes,
                              distinct_morphologies, last_independent_at,
                              last_independent_correct
                       FROM subskill_mastery
                       WHERE learner_id = ? AND concept = ? AND subskill = ?""",
                    (learner_id, event["concept"], subskill),
                ).fetchone()
                formative = float(current["formative_score"]) if current else 0.0
                independent = float(current["independent_mastery"]) if current else 0.15
                formative_delta = (0.04 + 0.04 * score) if correct else -0.04
                independent_delta = 0.0
                if effective_level == "independent_transfer":
                    independent_delta = (0.05 + 0.05 * score) if correct else -0.06
                next_formative = min(1.0, max(0.0, formative + formative_delta))
                next_independent = min(1.0, max(0.0, independent + independent_delta))
                high_conf_wrong = 1 if confidence is not None and int(confidence) >= 4 and not correct else 0
                retention_values = {
                    "independentAttempts": (
                        (int(current["independent_attempts"]) if current else 0)
                        + (1 if effective_level == "independent_transfer" else 0)
                    ),
                    "nextDueAt": current["next_due_at"] if current else None,
                    "stabilityDays": float(current["stability_days"]) if current else 0.0,
                    "lapses": int(current["lapses"]) if current else 0,
                    "spacedRetrievals": int(current["spaced_retrievals"]) if current else 0,
                    "distinctEligibleEcgs": int(current["distinct_eligible_ecgs"]) if current else 0,
                    "distinctSuccessfulEcgs": int(current["distinct_successful_ecgs"]) if current else 0,
                    "distinctModes": int(current["distinct_modes"]) if current else 0,
                    "distinctMorphologies": int(current["distinct_morphologies"]) if current else 0,
                    "lastIndependentAt": current["last_independent_at"] if current else None,
                    "lastIndependentCorrect": (
                        bool(current["last_independent_correct"])
                        if current and current["last_independent_correct"] is not None
                        else None
                    ),
                }
                retention_eligible = (
                    effective_level == "independent_transfer"
                    and bool(event.get("_retentionVerified"))
                    and bool(event.get("caseId"))
                )
                interval_expanded = False
                if retention_eligible:
                    update = update_retention(
                        retention_values,
                        correct=correct,
                        occurred_at=event_time,
                    )
                    retention_values.update({
                        "nextDueAt": update.next_due_at,
                        "stabilityDays": update.stability_days,
                        "lapses": update.lapses,
                        "spacedRetrievals": update.spaced_retrievals,
                        "lastIndependentAt": update.last_independent_at,
                        "lastIndependentCorrect": update.last_independent_correct,
                    })
                    interval_expanded = update.interval_expanded
                    conn.execute(
                        """
                        INSERT INTO subskill_retention_events (
                            guided_event_id, learner_id, concept, subskill, case_id,
                            mode, morphology_key, correct, registry_version, occurred_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            int(cursor.lastrowid), learner_id, event["concept"], subskill,
                            str(event["caseId"]), str(event["moduleId"]),
                            event.get("_retentionMorphologyKey"), 1 if correct else 0,
                            REGISTRY_VERSION, now,
                        ),
                    )
                    diversity = conn.execute(
                        """
                        SELECT COUNT(DISTINCT case_id) AS eligible_ecgs,
                               COUNT(DISTINCT CASE WHEN correct = 1 THEN case_id END) AS successful_ecgs,
                               COUNT(DISTINCT mode) AS modes,
                               COUNT(DISTINCT CASE
                                   WHEN morphology_key IS NOT NULL AND morphology_key != ''
                                   THEN morphology_key END) AS morphologies
                        FROM subskill_retention_events
                        WHERE learner_id = ? AND concept = ? AND subskill = ?
                        """,
                        (learner_id, event["concept"], subskill),
                    ).fetchone()
                    retention_values.update({
                        "distinctEligibleEcgs": int(diversity["eligible_ecgs"]),
                        "distinctSuccessfulEcgs": int(diversity["successful_ecgs"]),
                        "distinctModes": int(diversity["modes"]),
                        "distinctMorphologies": int(diversity["morphologies"]),
                    })
                if current:
                    conn.execute(
                        """
                        UPDATE subskill_mastery
                        SET formative_score = ?, independent_mastery = ?, attempts = attempts + 1,
                            independent_attempts = independent_attempts + ?, correct = correct + ?,
                            high_confidence_wrong = high_confidence_wrong + ?, last_practiced_at = ?,
                            next_due_at = ?, stability_days = ?, lapses = ?,
                            spaced_retrievals = ?, distinct_eligible_ecgs = ?,
                            distinct_successful_ecgs = ?, distinct_modes = ?,
                            distinct_morphologies = ?, last_independent_at = ?,
                            last_independent_correct = ?
                        WHERE learner_id = ? AND concept = ? AND subskill = ?
                        """,
                        (next_formative, next_independent, 1 if effective_level == "independent_transfer" else 0,
                         1 if correct else 0, high_conf_wrong, now,
                         retention_values["nextDueAt"], retention_values["stabilityDays"],
                         retention_values["lapses"], retention_values["spacedRetrievals"],
                         retention_values["distinctEligibleEcgs"], retention_values["distinctSuccessfulEcgs"],
                         retention_values["distinctModes"], retention_values["distinctMorphologies"],
                         retention_values["lastIndependentAt"],
                         (1 if retention_values["lastIndependentCorrect"] else 0)
                         if retention_values["lastIndependentCorrect"] is not None else None,
                         learner_id, event["concept"], subskill),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO subskill_mastery (
                            learner_id, concept, subskill, formative_score, independent_mastery,
                            attempts, independent_attempts, correct, high_confidence_wrong, last_practiced_at,
                            next_due_at, stability_days, lapses, spaced_retrievals,
                            distinct_eligible_ecgs, distinct_successful_ecgs, distinct_modes,
                            distinct_morphologies, last_independent_at, last_independent_correct
                        ) VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (learner_id, event["concept"], subskill, next_formative, next_independent,
                         1 if effective_level == "independent_transfer" else 0,
                         1 if correct else 0, high_conf_wrong, now,
                         retention_values["nextDueAt"], retention_values["stabilityDays"],
                         retention_values["lapses"], retention_values["spacedRetrievals"],
                         retention_values["distinctEligibleEcgs"], retention_values["distinctSuccessfulEcgs"],
                         retention_values["distinctModes"], retention_values["distinctMorphologies"],
                         retention_values["lastIndependentAt"],
                         (1 if retention_values["lastIndependentCorrect"] else 0)
                         if retention_values["lastIndependentCorrect"] is not None else None),
                    )
                due = due_snapshot(retention_values, as_of=event_time)
                receipts.append({
                    "registryVersion": REGISTRY_VERSION,
                    "concept": event["concept"],
                    "subskill": subskill,
                    "formativeScore": round(next_formative, 3),
                    "independentMastery": round(next_independent, 3),
                    "evidenceLevel": effective_level,
                    "retentionEligible": retention_eligible,
                    "nextDueAt": retention_values["nextDueAt"],
                    "stabilityDays": retention_values["stabilityDays"],
                    "lapses": retention_values["lapses"],
                    "spacedRetrievals": retention_values["spacedRetrievals"],
                    "distinctEligibleEcgs": retention_values["distinctEligibleEcgs"],
                    "distinctSuccessfulEcgs": retention_values["distinctSuccessfulEcgs"],
                    "distinctModes": retention_values["distinctModes"],
                    "distinctMorphologies": retention_values["distinctMorphologies"],
                    "dueState": due["dueState"],
                    "intervalExpanded": interval_expanded,
                })
            conn.execute(
                "UPDATE guided_learning_events SET receipt_json = ? WHERE id = ?",
                (json.dumps(receipts), cursor.lastrowid),
            )
            module_id = str(event["moduleId"])
            if module_id not in {"train", "rapid", "clinical"}:
                # Native Guided work has no assessment lease, but it belongs in
                # the same answer-free audit timeline. Training/Rapid/Clinical
                # append their lease-linked events inside their own atomic
                # answer transactions instead of duplicating them here.
                append_learner_event(
                    conn,
                    event_id=normalized_event_id,
                    owner_id=learner_id,
                    mode="guided",
                    session_id=f"{module_id}:{event['sceneId']}",
                    ecg_id=str(event.get("caseId") or "") or None,
                    event_type="interaction_committed",
                    evidence_level=(
                        "independent_transfer"
                        if effective_level == "independent_transfer"
                        else "guided"
                    ),
                    integrity_status="atomic_v2",
                    score=score,
                    competencies={
                        f"{event['concept']}:{subskill}": score
                        for subskill in event["subskills"]
                    },
                    occurred_at=now,
                )
            conn.execute("UPDATE learner_profiles SET updated_at = ? WHERE learner_id = ?", (now, learner_id))
            return {
                "eventId": int(cursor.lastrowid),
                "eventKey": event_key,
                "replay": False,
                "requestedEvidenceLevel": requested_level,
                "effectiveEvidenceLevel": effective_level,
                "registryVersion": REGISTRY_VERSION,
                "receipts": receipts,
            }

    def save_attempt(
        self,
        learner_id: str,
        case_id: str,
        mode: str,
        structured_answer: dict[str, Any],
        free_text_answer: str,
        confidence: int,
        hints_used: int,
        grade: dict[str, Any],
    ) -> int:
        self.ensure_profile(learner_id)
        now = utc_now()
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO attempts (
                    learner_id, case_id, mode, structured_answer_json, free_text_answer,
                    confidence, hints_used, score, correct_objectives_json,
                    missed_objectives_json, misconception_tags_json, feedback,
                    registry_version, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    learner_id,
                    case_id,
                    mode,
                    json.dumps(structured_answer),
                    free_text_answer,
                    confidence,
                    hints_used,
                    float(grade["score"]),
                    json.dumps(grade["correctObjectives"]),
                    json.dumps(grade["missedObjectives"]),
                    json.dumps(grade["misconceptions"]),
                    grade["feedback"],
                    REGISTRY_VERSION,
                    now,
                ),
            )
            # Training/Rapid use exact independent receipts. Clinical is also a
            # hard exclusion here because the currently served bank is formative
            # and pending named clinician sign-off. Even a forged/future-looking
            # grade marker must not bypass this persistence boundary; reviewed
            # Clinical evidence needs a dedicated server-authorized receipt path.
            mastery_delta = _legacy_mastery_deltas(mode, grade)
            for objective, delta in mastery_delta.items():
                current = conn.execute(
                    """
                    SELECT mastery, attempts, correct, high_confidence_wrong
                    FROM objective_mastery WHERE learner_id = ? AND objective = ?
                    """,
                    (learner_id, objective),
                ).fetchone()
                if current:
                    new_mastery = min(1.0, max(0.0, current["mastery"] + delta))
                    correct_increment = 1 if objective in grade["correctObjectives"] else 0
                    high_conf_wrong_increment = (
                        1 if confidence >= 4 and objective in grade["missedObjectives"] else 0
                    )
                    conn.execute(
                        """
                        UPDATE objective_mastery
                        SET mastery = ?, attempts = attempts + 1, correct = correct + ?,
                            high_confidence_wrong = high_confidence_wrong + ?,
                            last_practiced_at = ?
                        WHERE learner_id = ? AND objective = ?
                        """,
                        (
                            new_mastery,
                            correct_increment,
                            high_conf_wrong_increment,
                            now,
                            learner_id,
                            objective,
                        ),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO objective_mastery (
                            learner_id, objective, mastery, attempts, correct,
                            high_confidence_wrong, last_practiced_at
                        )
                        VALUES (?, ?, ?, 1, ?, ?, ?)
                        """,
                        (
                            learner_id,
                            objective,
                            min(1.0, max(0.0, 0.25 + delta)),
                            1 if objective in grade["correctObjectives"] else 0,
                            1 if confidence >= 4 and objective in grade["missedObjectives"] else 0,
                            now,
                        ),
                    )
            conn.execute(
                "UPDATE learner_profiles SET updated_at = ? WHERE learner_id = ?",
                (now, learner_id),
            )
            return int(cursor.lastrowid)

    def _save_attempt_in_transaction(
        self,
        conn: sqlite3.Connection,
        *,
        learner_id: str,
        case_id: str,
        mode: str,
        structured_answer: dict[str, Any],
        confidence: int,
        grade: dict[str, Any],
        now: str,
    ) -> int:
        """Write one attempt and its mastery deltas on an existing transaction.

        Clinical answers use this helper so the answer ledger, generic attempt,
        mastery mutation, and session advance either all commit or all roll back.
        """
        cursor = conn.execute(
            """
            INSERT INTO attempts (
                learner_id, case_id, mode, structured_answer_json, free_text_answer,
                confidence, hints_used, score, correct_objectives_json,
                missed_objectives_json, misconception_tags_json, feedback, registry_version, created_at
            ) VALUES (?, ?, ?, ?, '', ?, 0, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                learner_id,
                case_id,
                mode,
                json.dumps(structured_answer),
                confidence,
                float(grade["score"]),
                json.dumps(grade["correctObjectives"]),
                json.dumps(grade["missedObjectives"]),
                json.dumps(grade["misconceptions"]),
                grade["feedback"],
                REGISTRY_VERSION,
                now,
            ),
        )
        # Keep the transactional Clinical path fail-closed for legacy mastery.
        # Its exact observations are persisted immediately beforehand as
        # formative subskill receipts and remain available for reports/debrief.
        mastery_delta = _legacy_mastery_deltas(mode, grade)
        for objective, delta in mastery_delta.items():
            current = conn.execute(
                """SELECT mastery, attempts, correct, high_confidence_wrong
                   FROM objective_mastery WHERE learner_id = ? AND objective = ?""",
                (learner_id, objective),
            ).fetchone()
            correct_increment = 1 if objective in grade["correctObjectives"] else 0
            high_conf_wrong_increment = (
                1 if confidence >= 4 and objective in grade["missedObjectives"] else 0
            )
            if current:
                conn.execute(
                    """
                    UPDATE objective_mastery
                    SET mastery = ?, attempts = attempts + 1, correct = correct + ?,
                        high_confidence_wrong = high_confidence_wrong + ?, last_practiced_at = ?
                    WHERE learner_id = ? AND objective = ?
                    """,
                    (
                        min(1.0, max(0.0, float(current["mastery"]) + float(delta))),
                        correct_increment,
                        high_conf_wrong_increment,
                        now,
                        learner_id,
                        objective,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO objective_mastery (
                        learner_id, objective, mastery, attempts, correct,
                        high_confidence_wrong, last_practiced_at
                    ) VALUES (?, ?, ?, 1, ?, ?, ?)
                    """,
                    (
                        learner_id,
                        objective,
                        min(1.0, max(0.0, 0.25 + float(delta))),
                        correct_increment,
                        high_conf_wrong_increment,
                        now,
                    ),
                )
        conn.execute(
            "UPDATE learner_profiles SET updated_at = ? WHERE learner_id = ?",
            (now, learner_id),
        )
        return int(cursor.lastrowid)

    def recent_case_ids(self, learner_id: str, limit: int = 12) -> list[str]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT case_id FROM attempts WHERE learner_id = ? ORDER BY id DESC LIMIT ?",
                (learner_id, limit),
            ).fetchall()
            return [row["case_id"] for row in rows]

    def protected_case_ids(
        self, learner_id: str, *, as_of: str | datetime | None = None
    ) -> list[str]:
        """Answer-free owner projection for assessment selection boundaries."""

        with self.connect() as conn:
            return list(owner_exposure_ids(conn, owner_id=learner_id, as_of=as_of))

    def has_committed_attempt(self, learner_id: str, case_id: str) -> bool:
        """Return whether this owner has crossed the durable answer boundary.

        A different learner may be reading the same corpus ECG concurrently.
        That must not erase this owner's already-earned post-commit debrief, while
        the other learner's own precommit surfaces remain blinded.
        """

        with self.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM attempts WHERE learner_id = ? AND case_id = ? LIMIT 1",
                (learner_id, case_id),
            ).fetchone()
        return row is not None

    def retention_case_ids(self, learner_id: str, concept: str, subskill: str) -> list[str]:
        """Real ECGs already used as independent retention evidence for a competency."""

        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT case_id
                FROM subskill_retention_events
                WHERE learner_id = ? AND concept = ? AND subskill = ?
                ORDER BY case_id
                """,
                (learner_id, concept, subskill),
            ).fetchall()
        return [str(row["case_id"]) for row in rows]

    # --- users & sessions (Phase 4 auth) ---------------------------------------

    def _insert_new_user_graph(
        self,
        conn: sqlite3.Connection,
        *,
        user_id: str,
        username: str,
        display_name: str,
        password_hash: str,
        email_normalized: str | None,
        account_origin: str,
        now: str,
    ) -> None:
        """Insert the complete minimum account graph on an existing transaction.

        Authentication owns the transaction boundary. Keeping the user, profile,
        and default competency rows together prevents a partially registered
        learner from becoming visible when a later write fails.
        """

        conn.execute(
            "INSERT INTO users "
            "(user_id, username, display_name, password_hash, email_normalized, "
            "account_origin, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                user_id,
                username,
                display_name,
                password_hash,
                email_normalized,
                account_origin,
                now,
            ),
        )
        conn.execute(
            "INSERT INTO learner_profiles "
            "(learner_id, display_name, created_at, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (user_id, display_name, now, now),
        )
        for objective, mastery in DEFAULT_MASTERY.items():
            conn.execute(
                "INSERT INTO objective_mastery "
                "(learner_id, objective, mastery) VALUES (?, ?, ?)",
                (user_id, objective, mastery),
            )

    def _insert_session(
        self,
        conn: sqlite3.Connection,
        *,
        token: str,
        user_id: str,
        expires_at: str,
        now: str,
    ) -> None:
        """Insert a hashed session credential on an existing transaction."""

        conn.execute(
            "INSERT INTO sessions (token, user_id, created_at, expires_at) "
            "VALUES (?, ?, ?, ?)",
            (self._session_key(token), user_id, now, expires_at),
        )

    def create_registered_user(
        self,
        *,
        user_id: str,
        username: str,
        display_name: str,
        password_hash: str,
        email_normalized: str | None,
        session_token: str | None,
        session_expires_at: str | None,
        account_origin: str = "established",
        _transaction_hook: Callable[[sqlite3.Connection, str], None] | None = None,
        _failure_hook: Callable[[sqlite3.Connection], None] | None = None,
    ) -> None:
        """Atomically create an account, its defaults, and its first session.

        ``_failure_hook`` is private test instrumentation used to prove that a
        failure after the last write still rolls back the entire account.
        """

        now = utc_now()
        with self.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            self._insert_new_user_graph(
                conn,
                user_id=user_id,
                username=username,
                display_name=display_name,
                password_hash=password_hash,
                email_normalized=email_normalized,
                account_origin=account_origin,
                now=now,
            )
            if _transaction_hook is not None:
                _transaction_hook(conn, now)
            if session_token is not None and session_expires_at is not None:
                self._insert_session(
                    conn,
                    token=session_token,
                    user_id=user_id,
                    expires_at=session_expires_at,
                    now=now,
                )
            if _failure_hook is not None:
                _failure_hook(conn)

    def create_user(self, user_id: str, username: str, display_name: str, password_hash: str) -> None:
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO users (user_id, username, display_name, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, username, display_name, password_hash, now),
            )

    def get_user_by_username(self, username: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT user_id, username, display_name, password_hash, email_normalized, "
                "email_verified_at, email_two_factor_enabled, registration_reservation, "
                "account_origin, created_at "
                "FROM users WHERE username = ?",
                (username,),
            ).fetchone()
        return dict(row) if row else None

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT user_id, username, display_name, email_normalized, "
                "email_verified_at, email_two_factor_enabled, account_origin, created_at "
                "FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_user_auth(self, user_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT user_id, username, display_name, password_hash, email_normalized, "
                "email_verified_at, email_two_factor_enabled, account_origin, created_at "
                "FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_user_by_email(self, email_normalized: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT user_id, username, display_name, password_hash, "
                "email_normalized, email_verified_at, email_two_factor_enabled, account_origin, created_at "
                "FROM users WHERE email_normalized = ?",
                (email_normalized,),
            ).fetchone()
        return dict(row) if row else None

    def password_hash_iteration_audit(
        self, *, current_iterations: int = 600_000
    ) -> dict[str, int]:
        """Return aggregate credential-migration counts without identities."""

        counts = {
            "total": 0,
            "current": 0,
            "legacy": 0,
            "future": 0,
            "invalid": 0,
        }
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT password_hash FROM users WHERE registration_reservation = 0"
            ).fetchall()
        for row in rows:
            counts["total"] += 1
            try:
                algorithm, iterations_text, salt, digest = str(
                    row["password_hash"]
                ).split("$")
                iterations = int(iterations_text)
                valid = (
                    algorithm == "pbkdf2_sha256"
                    and 100_000 <= iterations <= 2_000_000
                    and len(salt) == 32
                    and len(bytes.fromhex(salt)) == 16
                    and len(digest) == 64
                    and len(bytes.fromhex(digest)) == 32
                )
            except (TypeError, ValueError):
                valid = False
                iterations = 0
            if not valid:
                counts["invalid"] += 1
            elif iterations < current_iterations:
                counts["legacy"] += 1
            elif iterations == current_iterations:
                counts["current"] += 1
            else:
                counts["future"] += 1
        return counts

    def _insert_auth_challenge(
        self,
        conn: sqlite3.Connection,
        *,
        challenge_id: str,
        user_id: str,
        purpose: str,
        secret_hash: str,
        expires_at: str,
        max_attempts: int,
        now: str,
        credential_fingerprint: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Insert one hashed, purpose-bound authentication challenge."""

        conn.execute(
            "UPDATE auth_challenges SET consumed_at = ? "
            "WHERE user_id = ? AND purpose = ? AND consumed_at IS NULL",
            (now, user_id, purpose),
        )
        conn.execute(
            "INSERT INTO auth_challenges "
            "(challenge_id, user_id, purpose, secret_hash, credential_fingerprint, "
            "context_json, created_at, expires_at, consumed_at, attempt_count, "
            "max_attempts, last_sent_at, send_count) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, 0, ?, ?, 1)",
            (
                challenge_id,
                user_id,
                purpose,
                secret_hash,
                credential_fingerprint,
                json.dumps(context or {}, sort_keys=True, separators=(",", ":")),
                now,
                expires_at,
                max_attempts,
                now,
            ),
        )

    def create_auth_challenge(
        self,
        *,
        challenge_id: str,
        user_id: str,
        purpose: str,
        secret_hash: str,
        expires_at: str,
        max_attempts: int,
        credential_fingerprint: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        now = utc_now()
        with self.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            self._insert_auth_challenge(
                conn,
                challenge_id=challenge_id,
                user_id=user_id,
                purpose=purpose,
                secret_hash=secret_hash,
                expires_at=expires_at,
                max_attempts=max_attempts,
                now=now,
                credential_fingerprint=credential_fingerprint,
                context=context,
            )

    def reserve_auth_challenge_issue(
        self,
        *,
        challenge_id: str,
        user_id: str,
        purpose: str,
        secret_hash: str,
        expires_at: str,
        max_attempts: int,
        max_sends: int,
        restart_exhausted: bool,
        credential_fingerprint: str | None = None,
        context: dict[str, Any] | None = None,
        reservation_user_id: str | None = None,
        reservation_username: str | None = None,
        reservation_password_hash: str | None = None,
    ) -> tuple[str, dict[str, Any] | None]:
        """Atomically select the single challenge that may be delivered.

        Challenge lookup followed by creation in separate transactions lets
        concurrent requests each invalidate and email the other's proof.  This
        writer transaction serializes reuse, replacement, delivery ceilings,
        and the optional public-username reservation.  A caller sends mail only
        for ``created``; ``existing`` and ``send_limit`` never own a new secret.

        Context supplied by the caller is a compatibility contract. Existing
        extra keys are retained (for example, an earlier guest migration
        intent), while a changed destination or different explicit value
        creates one replacement. Concurrent identical requests then observe
        that replacement and reuse it.
        """

        now_dt = datetime.now(UTC)
        now = now_dt.isoformat()
        requested_context = dict(context or {})
        with self.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")

            active_row = conn.execute(
                "SELECT c.*, u.email_normalized FROM auth_challenges c "
                "JOIN users u ON u.user_id = c.user_id "
                "WHERE c.user_id = ? AND c.purpose = ? AND c.consumed_at IS NULL "
                "ORDER BY c.created_at DESC LIMIT 1",
                (user_id, purpose),
            ).fetchone()
            active = dict(active_row) if active_row else None
            active_valid = bool(
                active
                and not self._challenge_expired(str(active["expires_at"]), now_dt)
                and int(active["attempt_count"]) < int(active["max_attempts"])
            )
            fingerprint_matches = bool(
                active_valid
                and (
                    credential_fingerprint is None
                    or (
                        active.get("credential_fingerprint")
                        and hmac.compare_digest(
                            str(active["credential_fingerprint"]),
                            credential_fingerprint,
                        )
                    )
                )
            )
            existing_context: dict[str, Any] = {}
            if active:
                try:
                    decoded_context = json.loads(
                        str(active.get("context_json") or "{}")
                    )
                    if isinstance(decoded_context, dict):
                        existing_context = decoded_context
                except json.JSONDecodeError:
                    existing_context = {}
            context_matches = all(
                existing_context.get(key) == value
                for key, value in requested_context.items()
            )

            if reservation_username is not None:
                if not (
                    reservation_user_id
                    and reservation_password_hash
                    and self._insert_registration_username_reservation(
                        conn,
                        reservation_user_id=reservation_user_id,
                        username=reservation_username,
                        password_hash=reservation_password_hash,
                        now=now,
                    )
                ):
                    return "reservation_conflict", None

            if active_valid and fingerprint_matches and context_matches:
                if int(active["send_count"]) < max_sends:
                    return "existing", active
                if not restart_exhausted:
                    return "send_limit", active

            self._insert_auth_challenge(
                conn,
                challenge_id=challenge_id,
                user_id=user_id,
                purpose=purpose,
                secret_hash=secret_hash,
                expires_at=expires_at,
                max_attempts=max_attempts,
                now=now,
                credential_fingerprint=credential_fingerprint,
                context=requested_context,
            )
            created = conn.execute(
                "SELECT c.*, u.email_normalized FROM auth_challenges c "
                "JOIN users u ON u.user_id = c.user_id "
                "WHERE c.challenge_id = ?",
                (challenge_id,),
            ).fetchone()
        return "created", dict(created) if created else None

    def auth_challenge_is_active(self, challenge_id: str) -> bool:
        """Best-effort final delivery guard after the issue reservation commits."""

        with self.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM auth_challenges WHERE challenge_id = ? "
                "AND consumed_at IS NULL AND expires_at > ?",
                (challenge_id, utc_now()),
            ).fetchone()
        return row is not None

    @staticmethod
    def _insert_registration_username_reservation(
        conn: sqlite3.Connection,
        *,
        reservation_user_id: str,
        username: str,
        password_hash: str,
        now: str,
    ) -> bool:
        """Reserve a public username using the same unique users boundary.

        A reservation has no email, profile, session, or learning graph and its
        credential hash has no known plaintext. It exists solely so the first
        and repeated registration state transitions are identical whether the
        supplied email was new or already owned.
        """

        try:
            conn.execute(
                "INSERT INTO users "
                "(user_id, username, display_name, password_hash, email_normalized, "
                "email_verified_at, email_two_factor_enabled, registration_reservation, "
                "account_origin, created_at) "
                "VALUES (?, ?, 'Registration reservation', ?, NULL, NULL, 0, 1, "
                "'registration_reservation', ?)",
                (reservation_user_id, username, password_hash, now),
            )
        except sqlite3.IntegrityError:
            return False
        return True

    def reserve_registration_username(
        self,
        *,
        reservation_user_id: str,
        username: str,
        password_hash: str,
    ) -> bool:
        now = utc_now()
        with self.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            return self._insert_registration_username_reservation(
                conn,
                reservation_user_id=reservation_user_id,
                username=username,
                password_hash=password_hash,
                now=now,
            )

    def create_auth_challenge_with_registration_reservation(
        self,
        *,
        reservation_user_id: str,
        reservation_username: str,
        reservation_password_hash: str,
        challenge_id: str,
        user_id: str,
        purpose: str,
        secret_hash: str,
        expires_at: str,
        max_attempts: int,
        credential_fingerprint: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> bool:
        """Atomically reserve the username and create the owner email proof."""

        now = utc_now()
        with self.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            if not self._insert_registration_username_reservation(
                conn,
                reservation_user_id=reservation_user_id,
                username=reservation_username,
                password_hash=reservation_password_hash,
                now=now,
            ):
                return False
            self._insert_auth_challenge(
                conn,
                challenge_id=challenge_id,
                user_id=user_id,
                purpose=purpose,
                secret_hash=secret_hash,
                expires_at=expires_at,
                max_attempts=max_attempts,
                now=now,
                credential_fingerprint=credential_fingerprint,
                context=context,
            )
        return True

    def get_auth_challenge(self, challenge_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT c.*, u.username, u.display_name, u.password_hash, "
                "u.email_normalized, u.email_verified_at, u.email_two_factor_enabled, u.account_origin "
                "FROM auth_challenges c JOIN users u ON u.user_id = c.user_id "
                "WHERE c.challenge_id = ?",
                (challenge_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_active_auth_challenge(
        self, user_id: str, purpose: str
    ) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT c.*, u.email_normalized FROM auth_challenges c "
                "JOIN users u ON u.user_id = c.user_id "
                "WHERE c.user_id = ? AND c.purpose = ? AND c.consumed_at IS NULL "
                "ORDER BY c.created_at DESC LIMIT 1",
                (user_id, purpose),
            ).fetchone()
        if not row:
            return None
        value = dict(row)
        if self._challenge_expired(str(value["expires_at"]), datetime.now(UTC)):
            return None
        if int(value["attempt_count"]) >= int(value["max_attempts"]):
            return None
        return value

    def get_pending_auth_challenge(
        self, user_id: str, purpose: str
    ) -> dict[str, Any] | None:
        """Return the unconsumed CAS row even when its proof is no longer usable."""

        with self.connect() as conn:
            row = conn.execute(
                "SELECT c.*, u.email_normalized FROM auth_challenges c "
                "JOIN users u ON u.user_id = c.user_id "
                "WHERE c.user_id = ? AND c.purpose = ? AND c.consumed_at IS NULL "
                "ORDER BY c.created_at DESC LIMIT 1",
                (user_id, purpose),
            ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def _challenge_expired(expires_at: str, now: datetime) -> bool:
        try:
            expiry = datetime.fromisoformat(expires_at)
        except (TypeError, ValueError):
            return True
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=UTC)
        return expiry <= now

    @staticmethod
    def _verification_budget_contract(
        record: dict[str, Any],
    ) -> tuple[str, str, int, int] | None:
        try:
            context = json.loads(str(record.get("context_json") or "{}"))
        except json.JSONDecodeError:
            return None
        if not isinstance(context, dict):
            return None
        key_hash = str(context.get("verificationBudgetKey") or "")
        purpose_group = str(context.get("verificationBudgetGroup") or "")
        try:
            max_failures = int(context.get("verificationBudgetMaxFailures") or 0)
            window_seconds = int(context.get("verificationBudgetWindowSeconds") or 0)
        except (TypeError, ValueError):
            return None
        if (
            not re.fullmatch(r"[0-9a-f]{64}", key_hash)
            or not re.fullmatch(r"[a-z0-9_-]{3,64}", purpose_group)
            or not 1 <= max_failures <= 20
            or not 60 <= window_seconds <= 86_400
        ):
            return None
        return key_hash, purpose_group, max_failures, window_seconds

    @staticmethod
    def _verification_budget_exhausted(
        conn: sqlite3.Connection,
        contract: tuple[str, str, int, int] | None,
        now_dt: datetime,
    ) -> bool:
        if contract is None:
            return False
        key_hash, purpose_group, max_failures, _window_seconds = contract
        row = conn.execute(
            "SELECT failure_count, window_expires_at FROM auth_verification_budgets "
            "WHERE key_hash = ? AND purpose_group = ?",
            (key_hash, purpose_group),
        ).fetchone()
        if not row:
            return False
        expiry = parse_instant(str(row["window_expires_at"]))
        return bool(
            expiry
            and expiry > now_dt
            and int(row["failure_count"]) >= max_failures
        )

    @staticmethod
    def _record_verification_budget_failure(
        conn: sqlite3.Connection,
        contract: tuple[str, str, int, int] | None,
        now_dt: datetime,
        now: str,
    ) -> bool:
        """Increment one rolling failure budget under the challenge writer lock."""

        if contract is None:
            return False
        key_hash, purpose_group, max_failures, window_seconds = contract
        row = conn.execute(
            "SELECT failure_count, window_expires_at FROM auth_verification_budgets "
            "WHERE key_hash = ? AND purpose_group = ?",
            (key_hash, purpose_group),
        ).fetchone()
        expiry = parse_instant(str(row["window_expires_at"])) if row else None
        if not row or not expiry or expiry <= now_dt:
            next_count = 1
            window_expires_at = (
                now_dt + timedelta(seconds=window_seconds)
            ).isoformat()
            conn.execute(
                "INSERT INTO auth_verification_budgets "
                "(key_hash, purpose_group, window_started_at, window_expires_at, "
                "failure_count, updated_at) VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(key_hash, purpose_group) DO UPDATE SET "
                "window_started_at = excluded.window_started_at, "
                "window_expires_at = excluded.window_expires_at, "
                "failure_count = excluded.failure_count, updated_at = excluded.updated_at",
                (
                    key_hash,
                    purpose_group,
                    now,
                    window_expires_at,
                    next_count,
                    now,
                ),
            )
        else:
            next_count = int(row["failure_count"]) + 1
            conn.execute(
                "UPDATE auth_verification_budgets SET failure_count = ?, updated_at = ? "
                "WHERE key_hash = ? AND purpose_group = ?",
                (next_count, now, key_hash, purpose_group),
            )
        return next_count >= max_failures

    def verify_auth_challenge(
        self,
        *,
        challenge_id: str,
        purpose: str,
        presented_secret_hash: str,
        user_id: str | None = None,
        on_success: Callable[[sqlite3.Connection, dict[str, Any], str], Any] | None = None,
    ) -> tuple[str, Any | None]:
        """Attempt and consume a challenge under one transaction.

        The caller computes a purpose/challenge-bound HMAC. Incorrect secrets
        consume a durable attempt; the optional success callback performs the
        account/session mutation before the one-time challenge is consumed.
        """

        now_dt = datetime.now(UTC)
        now = now_dt.isoformat()
        with self.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT c.*, u.username, u.display_name, u.password_hash, "
                "u.email_normalized, u.email_verified_at, u.email_two_factor_enabled, u.account_origin "
                "FROM auth_challenges c JOIN users u ON u.user_id = c.user_id "
                "WHERE c.challenge_id = ?",
                (challenge_id,),
            ).fetchone()
            if not row or str(row["purpose"]) != purpose:
                return "invalid", None
            record = dict(row)
            if user_id is not None and str(row["user_id"]) != user_id:
                return "invalid", None
            if row["consumed_at"]:
                return "consumed", None
            if self._challenge_expired(str(row["expires_at"]), now_dt):
                return "expired", None
            if int(row["attempt_count"]) >= int(row["max_attempts"]):
                return "attempts_exhausted", None
            budget_contract = self._verification_budget_contract(record)
            if self._verification_budget_exhausted(
                conn, budget_contract, now_dt
            ):
                return "attempts_exhausted", None
            if not hmac.compare_digest(
                str(row["secret_hash"]), presented_secret_hash
            ):
                next_attempt = int(row["attempt_count"]) + 1
                conn.execute(
                    "UPDATE auth_challenges SET attempt_count = ? "
                    "WHERE challenge_id = ?",
                    (next_attempt, challenge_id),
                )
                budget_exhausted = self._record_verification_budget_failure(
                    conn, budget_contract, now_dt, now
                )
                return (
                    "attempts_exhausted"
                    if next_attempt >= int(row["max_attempts"])
                    or budget_exhausted
                    else "incorrect",
                    None,
                )
            result = on_success(conn, record, now) if on_success else record
            consumed = conn.execute(
                "UPDATE auth_challenges SET consumed_at = ? "
                "WHERE challenge_id = ? AND consumed_at IS NULL",
                (now, challenge_id),
            )
            if int(consumed.rowcount) != 1:
                raise RuntimeError("Authentication challenge lost one-time ownership")
            if budget_contract is not None:
                conn.execute(
                    "DELETE FROM auth_verification_budgets "
                    "WHERE key_hash = ? AND purpose_group = ?",
                    (budget_contract[0], budget_contract[1]),
                )
        return "verified", result

    def resend_auth_challenge(
        self,
        *,
        challenge_id: str,
        purpose: str,
        replacement_secret_hash: str,
        replacement_expires_at: str,
        cooldown_seconds: int,
        max_sends: int,
    ) -> tuple[str, dict[str, Any] | None]:
        """Rotate a challenge secret after a durable resend cooldown."""

        now_dt = datetime.now(UTC)
        now = now_dt.isoformat()
        with self.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT c.*, u.email_normalized FROM auth_challenges c "
                "JOIN users u ON u.user_id = c.user_id WHERE c.challenge_id = ?",
                (challenge_id,),
            ).fetchone()
            if not row or str(row["purpose"]) != purpose or row["consumed_at"]:
                return "invalid", None
            if int(row["send_count"]) >= max_sends:
                return "send_limit", dict(row)
            try:
                last_sent = datetime.fromisoformat(str(row["last_sent_at"]))
                if last_sent.tzinfo is None:
                    last_sent = last_sent.replace(tzinfo=UTC)
            except ValueError:
                last_sent = now_dt
            if last_sent + timedelta(seconds=cooldown_seconds) > now_dt:
                return "cooldown", dict(row)
            conn.execute(
                "UPDATE auth_challenges SET secret_hash = ?, expires_at = ?, "
                "attempt_count = 0, last_sent_at = ?, send_count = send_count + 1 "
                "WHERE challenge_id = ? AND consumed_at IS NULL",
                (replacement_secret_hash, replacement_expires_at, now, challenge_id),
            )
            result = dict(row)
            result["expires_at"] = replacement_expires_at
            result["last_sent_at"] = now
            result["send_count"] = int(row["send_count"]) + 1
        return "resent", result

    def allow_auth_challenge_resend_now(self, challenge_id: str) -> None:
        """Release only the cooldown after transport failed post-rotation.

        The undelivered secret remains irrecoverable and hashed. A retry always
        rotates to another independent secret before attempting delivery.
        """

        with self.connect() as conn:
            conn.execute(
                "UPDATE auth_challenges SET last_sent_at = ? "
                "WHERE challenge_id = ? AND consumed_at IS NULL",
                ("1970-01-01T00:00:00+00:00", challenge_id),
            )

    def set_unverified_email(
        self,
        *,
        user_id: str,
        expected_password_hash: str,
        email_normalized: str,
        challenge_id: str,
        secret_hash: str,
        expires_at: str,
        max_attempts: int,
        context: dict[str, Any] | None = None,
    ) -> bool:
        """Attach a legacy account email and its verification challenge atomically."""

        now = utc_now()
        with self.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            current = conn.execute(
                "SELECT password_hash, email_normalized FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if (
                not current
                or current["email_normalized"] is not None
                or not hmac.compare_digest(
                    str(current["password_hash"]), expected_password_hash
                )
            ):
                return False
            conn.execute(
                "UPDATE users SET email_normalized = ?, email_verified_at = NULL, "
                "email_two_factor_enabled = 0 WHERE user_id = ?",
                (email_normalized, user_id),
            )
            self._insert_auth_challenge(
                conn,
                challenge_id=challenge_id,
                user_id=user_id,
                purpose="email_verification",
                secret_hash=secret_hash,
                expires_at=expires_at,
                max_attempts=max_attempts,
                now=now,
                credential_fingerprint=self._password_fingerprint(
                    expected_password_hash
                ),
                context=context,
            )
        return True

    def replace_unverified_email(
        self,
        *,
        user_id: str,
        expected_password_hash: str,
        expected_account_origin: str,
        expected_email_normalized: str,
        expected_challenge_id: str | None,
        email_normalized: str,
        challenge_id: str,
        secret_hash: str,
        expires_at: str,
        max_attempts: int,
        context: dict[str, Any] | None = None,
    ) -> bool:
        """Replace a never-verified address and every proof in one transaction.

        The expected address and active verification proof form a compare-and-
        swap boundary. Two concurrent corrections cannot both commit, and an
        old link can never verify the replacement destination.
        """

        now = utc_now()
        with self.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            current = conn.execute(
                "SELECT password_hash, email_normalized, email_verified_at, "
                "account_origin, registration_reservation FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if (
                not current
                or bool(current["registration_reservation"])
                or current["email_verified_at"] is not None
                or str(current["account_origin"]) != expected_account_origin
                or str(current["email_normalized"] or "")
                != expected_email_normalized
                or not hmac.compare_digest(
                    str(current["password_hash"]), expected_password_hash
                )
            ):
                return False
            active = conn.execute(
                "SELECT challenge_id FROM auth_challenges WHERE user_id = ? "
                "AND purpose = 'email_verification' AND consumed_at IS NULL "
                "ORDER BY created_at DESC LIMIT 1",
                (user_id,),
            ).fetchone()
            active_id = str(active["challenge_id"]) if active else None
            if active_id != expected_challenge_id:
                return False
            updated = conn.execute(
                "UPDATE users SET email_normalized = ?, email_verified_at = NULL, "
                "email_two_factor_enabled = 0 WHERE user_id = ? "
                "AND password_hash = ? AND email_verified_at IS NULL "
                "AND account_origin = ? AND email_normalized = ?",
                (
                    email_normalized,
                    user_id,
                    expected_password_hash,
                    expected_account_origin,
                    expected_email_normalized,
                ),
            )
            if int(updated.rowcount) != 1:
                return False
            conn.execute(
                "UPDATE auth_challenges SET consumed_at = ? "
                "WHERE user_id = ? AND consumed_at IS NULL",
                (now, user_id),
            )
            self._insert_auth_challenge(
                conn,
                challenge_id=challenge_id,
                user_id=user_id,
                purpose="email_verification",
                secret_hash=secret_hash,
                expires_at=expires_at,
                max_attempts=max_attempts,
                now=now,
                credential_fingerprint=self._password_fingerprint(
                    expected_password_hash
                ),
                context=context,
            )
        return True

    def cancel_unverified_email(
        self,
        *,
        user_id: str,
        expected_password_hash: str,
        expected_account_origin: str,
        expected_email_normalized: str,
        expected_challenge_id: str | None,
    ) -> str | None:
        """Cancel a typo safely: delete pending shells or detach legacy email."""

        now = utc_now()
        with self.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            current = conn.execute(
                "SELECT password_hash, email_normalized, email_verified_at, "
                "account_origin, registration_reservation FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if (
                not current
                or bool(current["registration_reservation"])
                or current["email_verified_at"] is not None
                or str(current["account_origin"]) != expected_account_origin
                or str(current["email_normalized"] or "")
                != expected_email_normalized
                or not hmac.compare_digest(
                    str(current["password_hash"]), expected_password_hash
                )
            ):
                return None
            active = conn.execute(
                "SELECT challenge_id FROM auth_challenges WHERE user_id = ? "
                "AND purpose = 'email_verification' AND consumed_at IS NULL "
                "ORDER BY created_at DESC LIMIT 1",
                (user_id,),
            ).fetchone()
            active_id = str(active["challenge_id"]) if active else None
            if active_id != expected_challenge_id:
                return None
            if expected_account_origin not in {
                "pending_registration",
                "established",
            }:
                return None
            if expected_account_origin == "pending_registration" and conn.execute(
                "SELECT 1 FROM sessions WHERE user_id = ? LIMIT 1", (user_id,)
            ).fetchone():
                return None
            conn.execute(
                "UPDATE auth_challenges SET consumed_at = ? "
                "WHERE user_id = ? AND consumed_at IS NULL",
                (now, user_id),
            )
            if expected_account_origin == "pending_registration":
                self._retire_account_generation(
                    conn,
                    user_id,
                    reason="pending_registration_cancelled",
                    retired_at=now,
                )
                self._delete_guest_owner_rows(conn, user_id)
                conn.execute("DELETE FROM auth_challenges WHERE user_id = ?", (user_id,))
                deleted = conn.execute(
                    "DELETE FROM users WHERE user_id = ? "
                    "AND account_origin = 'pending_registration' "
                    "AND email_verified_at IS NULL",
                    (user_id,),
                )
                return "account_cancelled" if int(deleted.rowcount) == 1 else None
            detached = conn.execute(
                "UPDATE users SET email_normalized = NULL, email_verified_at = NULL, "
                "email_two_factor_enabled = 0 WHERE user_id = ? "
                "AND account_origin = 'established' AND email_verified_at IS NULL",
                (user_id,),
            )
            return "email_removed" if int(detached.rowcount) == 1 else None

    def consume_owner_auth_challenge(
        self, *, user_id: str, challenge_id: str, purpose: str
    ) -> bool:
        """Owner-bound cancellation for a pending account-security proof."""

        now = utc_now()
        with self.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            consumed = conn.execute(
                "UPDATE auth_challenges SET consumed_at = ? WHERE challenge_id = ? "
                "AND user_id = ? AND purpose = ? AND consumed_at IS NULL",
                (now, challenge_id, user_id, purpose),
            )
        return int(consumed.rowcount) == 1

    def disable_email_two_factor(
        self,
        *,
        user_id: str,
        expected_password_hash: str,
    ) -> bool:
        """Disable email 2FA only while the reauthenticated password is current.

        Password verification is deliberately performed by ``AuthService``
        before this call so PBKDF2 work does not hold a database writer lock.
        The exact hash that was verified is then compared under the same writer
        transaction that disables 2FA and consumes outstanding 2FA proofs. A
        concurrent password rotation makes this operation fail closed.
        """

        now = utc_now()
        with self.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            current = conn.execute(
                "SELECT password_hash FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if not current or not hmac.compare_digest(
                str(current["password_hash"]), expected_password_hash
            ):
                return False
            updated = conn.execute(
                "UPDATE users SET email_two_factor_enabled = 0 "
                "WHERE user_id = ? AND password_hash = ?",
                (user_id, expected_password_hash),
            )
            if int(updated.rowcount) != 1:
                return False
            conn.execute(
                "UPDATE auth_challenges SET consumed_at = ? "
                "WHERE user_id = ? "
                "AND purpose IN ('two_factor_login', 'two_factor_enable') "
                "AND consumed_at IS NULL",
                (now, user_id),
            )
        return True

    def update_user_password(self, user_id: str, password_hash: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE users SET password_hash = ? WHERE user_id = ?",
                (password_hash, user_id),
            )
            if self._table_exists(conn, "export_authorizations"):
                conn.execute(
                    "DELETE FROM export_authorizations WHERE user_id = ?", (user_id,)
                )

    def rotate_password_and_sessions(
        self,
        *,
        user_id: str,
        expected_password_hash: str,
        new_password_hash: str,
        new_session_token: str,
        new_session_expires_at: str,
        _failure_hook: Callable[[sqlite3.Connection], None] | None = None,
    ) -> bool:
        """Atomically change credentials and replace every login session.

        Fresh password verification happens before this call, so the expected
        hash is rechecked under the same writer transaction that updates the
        password, revokes all old sessions/export grants, and creates the one
        replacement session. A concurrent credential change returns ``False``;
        any database failure rolls the entire rotation back.

        ``_failure_hook`` is private test instrumentation and is never exposed
        through an HTTP request.
        """

        now = utc_now()
        session_key = self._session_key(new_session_token)
        with self.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            current = conn.execute(
                "SELECT password_hash FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if not current or not hmac.compare_digest(
                str(current["password_hash"]), expected_password_hash
            ):
                return False
            updated = conn.execute(
                "UPDATE users SET password_hash = ? "
                "WHERE user_id = ? AND password_hash = ?",
                (new_password_hash, user_id, expected_password_hash),
            )
            if int(updated.rowcount) != 1:
                return False
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            if self._table_exists(conn, "export_authorizations"):
                conn.execute(
                    "DELETE FROM export_authorizations WHERE user_id = ?",
                    (user_id,),
                )
            if self._table_exists(conn, "auth_challenges"):
                conn.execute(
                    "UPDATE auth_challenges SET consumed_at = ? "
                    "WHERE user_id = ? AND consumed_at IS NULL",
                    (now, user_id),
                )
            conn.execute(
                "INSERT INTO sessions (token, user_id, created_at, expires_at) "
                "VALUES (?, ?, ?, ?)",
                (session_key, user_id, now, new_session_expires_at),
            )
            if _failure_hook is not None:
                _failure_hook(conn)
        return True

    @staticmethod
    def _session_key(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _export_authorization_key(token: str) -> str:
        return hashlib.sha256(
            _EXPORT_AUTH_KEY_DOMAIN + token.encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _password_fingerprint(password_hash: str) -> str:
        return hashlib.sha256(
            _PASSWORD_FINGERPRINT_DOMAIN + password_hash.encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _session_public_id(session_key: str) -> str:
        """Return a non-credential identifier derived from a stored digest.

        Session lookup digests are deliberately never returned to clients. The
        domain-separated second hash gives Account UI a stable opaque handle
        that cannot be replayed as either the browser token or its lookup key.
        """

        public_digest = hashlib.sha256(
            _SESSION_PUBLIC_ID_DOMAIN + session_key.encode("ascii")
        ).hexdigest()
        return f"ses_{public_digest}"

    def create_session(self, token: str, user_id: str, expires_at: str) -> None:
        with self.connect() as conn:
            self._insert_session(
                conn,
                token=token,
                user_id=user_id,
                expires_at=expires_at,
                now=utc_now(),
            )

    def create_session_if_password_current(
        self,
        *,
        user_id: str,
        expected_password_hash: str,
        token: str,
        expires_at: str,
        replacement_password_hash: str | None = None,
        _failure_hook: Callable[[sqlite3.Connection], None] | None = None,
    ) -> bool:
        """Mint a session only while the verified password hash is still current.

        Password verification is intentionally expensive and occurs before this
        call. The hash is compared again under the same writer transaction as
        session insertion, closing the password-change/login race. Older valid
        PBKDF2 hashes may be upgraded in that transaction without invalidating
        other sessions.
        """

        now = utc_now()
        with self.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            current = conn.execute(
                "SELECT password_hash FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if not current or not hmac.compare_digest(
                str(current["password_hash"]), expected_password_hash
            ):
                return False
            if replacement_password_hash is not None:
                updated = conn.execute(
                    "UPDATE users SET password_hash = ? "
                    "WHERE user_id = ? AND password_hash = ?",
                    (replacement_password_hash, user_id, expected_password_hash),
                )
                if int(updated.rowcount) != 1:
                    return False
                if self._table_exists(conn, "export_authorizations"):
                    conn.execute(
                        "DELETE FROM export_authorizations WHERE user_id = ?",
                        (user_id,),
                    )
            self._insert_session(
                conn,
                token=token,
                user_id=user_id,
                expires_at=expires_at,
                now=now,
            )
            if _failure_hook is not None:
                _failure_hook(conn)
        return True

    def get_session_user(self, token: str) -> str | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT user_id, expires_at FROM sessions WHERE token = ?",
                (self._session_key(token),),
            ).fetchone()
        if not row:
            return None
        if row["expires_at"] < utc_now():
            self.delete_session(token)
            return None
        return row["user_id"]

    def delete_session(self, token: str) -> None:
        session_key = self._session_key(token)
        with self.connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token = ?", (session_key,))
            if self._table_exists(conn, "export_authorizations"):
                conn.execute(
                    "DELETE FROM export_authorizations WHERE session_hash = ?",
                    (session_key,),
                )

    def delete_user_sessions(self, user_id: str) -> int:
        now = utc_now()
        with self.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            cursor = conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
            if self._table_exists(conn, "export_authorizations"):
                conn.execute(
                    "DELETE FROM export_authorizations WHERE user_id = ?", (user_id,)
                )
            if self._table_exists(conn, "auth_challenges"):
                # "Sign out all" is an account-wide security boundary: no
                # previously issued reset, email-change, verification, or 2FA
                # proof may mutate credentials or mint a later session.
                conn.execute(
                    "UPDATE auth_challenges SET consumed_at = ? "
                    "WHERE user_id = ? AND consumed_at IS NULL",
                    (now, user_id),
                )
        return int(cursor.rowcount)

    def delete_other_user_sessions(self, user_id: str, current_token: str) -> int:
        """Revoke every session for ``user_id`` except the presented credential."""

        current_key = self._session_key(current_token)
        with self.connect() as conn:
            cursor = conn.execute(
                "DELETE FROM sessions WHERE user_id = ? AND token != ?",
                (user_id, current_key),
            )
            if self._table_exists(conn, "export_authorizations"):
                conn.execute(
                    "DELETE FROM export_authorizations "
                    "WHERE user_id = ? AND session_hash != ?",
                    (user_id, current_key),
                )
        return int(cursor.rowcount)

    def list_user_sessions(
        self, user_id: str, current_token: str
    ) -> list[dict[str, Any]]:
        """List this owner's active sessions without exposing credentials."""

        current_key = self._session_key(current_token)
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                "DELETE FROM sessions WHERE user_id = ? AND expires_at <= ?",
                (user_id, now),
            )
            rows = conn.execute(
                "SELECT token, created_at, expires_at FROM sessions "
                "WHERE user_id = ? ORDER BY created_at DESC, token ASC",
                (user_id,),
            ).fetchall()
        sessions = [
            {
                "sessionId": self._session_public_id(str(row["token"])),
                "createdAt": str(row["created_at"]),
                "expiresAt": str(row["expires_at"]),
                "current": hmac.compare_digest(str(row["token"]), current_key),
            }
            for row in rows
        ]
        # Keep the presented session easy to find without inventing device data.
        return sorted(sessions, key=lambda session: not bool(session["current"]))

    def delete_owned_session_by_public_id(
        self, user_id: str, current_token: str, session_id: str
    ) -> str:
        """Revoke one non-current owned session.

        Returns a bounded status so callers can distinguish the current-session
        guard from the same not-found result used for foreign and absent IDs.
        """

        current_key = self._session_key(current_token)
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                "DELETE FROM sessions WHERE user_id = ? AND expires_at <= ?",
                (user_id, now),
            )
            rows = conn.execute(
                "SELECT token FROM sessions WHERE user_id = ?",
                (user_id,),
            ).fetchall()
            target_key = next(
                (
                    str(row["token"])
                    for row in rows
                    if hmac.compare_digest(
                        self._session_public_id(str(row["token"])), session_id
                    )
                ),
                None,
            )
            if target_key is None:
                return "not_found"
            if hmac.compare_digest(target_key, current_key):
                return "current"
            cursor = conn.execute(
                "DELETE FROM sessions WHERE user_id = ? AND token = ? AND token != ?",
                (user_id, target_key, current_key),
            )
            if int(cursor.rowcount) == 1 and self._table_exists(
                conn, "export_authorizations"
            ):
                conn.execute(
                    "DELETE FROM export_authorizations WHERE session_hash = ?",
                    (target_key,),
                )
        return "revoked" if int(cursor.rowcount) == 1 else "not_found"

    def create_export_authorization(
        self,
        *,
        token: str,
        user_id: str,
        current_session_token: str,
        expected_password_hash: str,
        expires_at: str,
    ) -> bool:
        """Persist one opaque, session-bound export capability by digest only."""

        session_key = self._session_key(current_session_token)
        now = utc_now()
        with self.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "DELETE FROM export_authorizations WHERE expires_at <= ?", (now,)
            )
            user = conn.execute(
                "SELECT password_hash FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
            session = conn.execute(
                "SELECT 1 FROM sessions "
                "WHERE token = ? AND user_id = ? AND expires_at > ?",
                (session_key, user_id, now),
            ).fetchone()
            if (
                not user
                or not session
                or not hmac.compare_digest(
                    str(user["password_hash"]), expected_password_hash
                )
            ):
                return False
            # At most one unused export grant is active for one login session.
            conn.execute(
                "DELETE FROM export_authorizations "
                "WHERE user_id = ? AND session_hash = ?",
                (user_id, session_key),
            )
            conn.execute(
                "INSERT INTO export_authorizations "
                "(token_hash, user_id, session_hash, password_fingerprint, created_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    self._export_authorization_key(token),
                    user_id,
                    session_key,
                    self._password_fingerprint(expected_password_hash),
                    now,
                    expires_at,
                ),
            )
        return True

    def delete_export_authorization_for_session(
        self, user_id: str, current_session_token: str
    ) -> None:
        """Invalidate any unused export grant for one exact login session."""

        with self.connect() as conn:
            conn.execute(
                "DELETE FROM export_authorizations "
                "WHERE user_id = ? AND session_hash = ?",
                (user_id, self._session_key(current_session_token)),
            )

    def consume_export_authorization(
        self,
        *,
        token: str | None,
        user_id: str,
        current_session_token: str,
    ) -> str:
        """Atomically consume one export capability and return a bounded status."""

        if not token:
            return "missing"
        token_key = self._export_authorization_key(token)
        session_key = self._session_key(current_session_token)
        now = utc_now()
        with self.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT user_id, session_hash, password_fingerprint, expires_at "
                "FROM export_authorizations WHERE token_hash = ?",
                (token_key,),
            ).fetchone()
            if not row:
                return "missing"
            # Deleting before validation makes replay impossible even when a
            # copied grant is presented from the wrong owner or session.
            conn.execute(
                "DELETE FROM export_authorizations WHERE token_hash = ?", (token_key,)
            )
            if str(row["expires_at"]) <= now:
                return "expired"
            if not hmac.compare_digest(str(row["user_id"]), user_id) or not hmac.compare_digest(
                str(row["session_hash"]), session_key
            ):
                return "invalid"
            session = conn.execute(
                "SELECT 1 FROM sessions "
                "WHERE token = ? AND user_id = ? AND expires_at > ?",
                (session_key, user_id, now),
            ).fetchone()
            user = conn.execute(
                "SELECT password_hash FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
            if not session or not user:
                return "invalid"
            if not hmac.compare_digest(
                str(row["password_fingerprint"]),
                self._password_fingerprint(str(user["password_hash"])),
            ):
                return "credentials_changed"
        return "authorized"

    @staticmethod
    def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ).fetchone()
        return row is not None

    @staticmethod
    def ensure_account_write_guards(conn: sqlite3.Connection) -> None:
        """Install guards for owner tables introduced after core initialization."""

        ensure_account_boundary_schema(conn)

    @staticmethod
    def _retire_account_generation(
        conn: sqlite3.Connection,
        user_id: str,
        *,
        reason: str,
        retired_at: str | None = None,
    ) -> None:
        retire_account_generation(
            conn,
            user_id,
            retired_at=retired_at or utc_now(),
            reason=reason,
        )

    @staticmethod
    def _maintenance_token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def claim_maintenance_lease(
        self,
        *,
        job_name: str,
        token: str,
        now: datetime | str,
        lease_seconds: int,
    ) -> bool:
        """Claim one due maintenance job without exposing a worker identity.

        The opaque token is stored only as a digest. ``BEGIN IMMEDIATE`` makes
        the due check and lease acquisition one writer boundary across app
        workers; an expired lease can be replaced after a crashed worker.
        """

        current = parse_instant(now)
        if current is None:
            raise ValueError("Maintenance lease time must be a valid instant")
        if lease_seconds < 1:
            raise ValueError("Maintenance lease duration must be positive")
        now_iso = current.isoformat()
        token_hash = self._maintenance_token_hash(token)
        expires_at = (current + timedelta(seconds=lease_seconds)).isoformat()
        with self.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            state = conn.execute(
                "SELECT next_run_at FROM maintenance_job_state WHERE job_name = ?",
                (job_name,),
            ).fetchone()
            next_run = parse_instant(state["next_run_at"]) if state else None
            if next_run is not None and next_run > current:
                return False
            lease = conn.execute(
                "SELECT expires_at FROM maintenance_leases WHERE lease_name = ?",
                (job_name,),
            ).fetchone()
            lease_expiry = parse_instant(lease["expires_at"]) if lease else None
            if lease is not None and lease_expiry is not None and lease_expiry > current:
                return False
            conn.execute(
                "INSERT INTO maintenance_leases "
                "(lease_name, token_hash, acquired_at, expires_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(lease_name) DO UPDATE SET "
                "token_hash = excluded.token_hash, acquired_at = excluded.acquired_at, "
                "expires_at = excluded.expires_at",
                (job_name, token_hash, now_iso, expires_at),
            )
        return True

    def complete_maintenance_lease(
        self,
        *,
        job_name: str,
        token: str,
        completed_at: datetime | str,
        interval_seconds: int,
    ) -> bool:
        """Release an owned lease and durably schedule its next run."""

        completed = parse_instant(completed_at)
        if completed is None:
            raise ValueError("Maintenance completion time must be a valid instant")
        if interval_seconds < 1:
            raise ValueError("Maintenance interval must be positive")
        completed_iso = completed.isoformat()
        next_run_at = (completed + timedelta(seconds=interval_seconds)).isoformat()
        with self.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            released = conn.execute(
                "DELETE FROM maintenance_leases WHERE lease_name = ? AND token_hash = ?",
                (job_name, self._maintenance_token_hash(token)),
            )
            if int(released.rowcount) != 1:
                return False
            conn.execute(
                "INSERT INTO maintenance_job_state "
                "(job_name, next_run_at, last_completed_at) VALUES (?, ?, ?) "
                "ON CONFLICT(job_name) DO UPDATE SET "
                "next_run_at = excluded.next_run_at, "
                "last_completed_at = excluded.last_completed_at",
                (job_name, next_run_at, completed_iso),
            )
        return True

    def release_maintenance_lease(self, *, job_name: str, token: str) -> bool:
        """Best-effort failure release; a stale worker cannot release a successor."""

        with self.connect() as conn:
            released = conn.execute(
                "DELETE FROM maintenance_leases WHERE lease_name = ? AND token_hash = ?",
                (job_name, self._maintenance_token_hash(token)),
            )
        return int(released.rowcount) == 1

    def _delete_guest_owner_rows(
        self, conn: sqlite3.Connection, guest_id: str
    ) -> int:
        """Delete one anonymous owner's complete learning graph in this transaction."""

        deleted_records = 0
        for table_name, predicate in _GUEST_CHILD_DELETE_SPECS:
            if self._table_exists(conn, table_name):
                cursor = conn.execute(
                    f"DELETE FROM {table_name} WHERE {predicate}",
                    (guest_id,),
                )
                deleted_records += int(cursor.rowcount)
        for table_name in _GUEST_DIRECT_DELETE_TABLES:
            if self._table_exists(conn, table_name):
                owner_column = (
                    "owner_id"
                    if table_name in {"learner_events", "assessment_leases"}
                    else "learner_id"
                )
                cursor = conn.execute(
                    f"DELETE FROM {table_name} WHERE {owner_column} = ?",
                    (guest_id,),
                )
                deleted_records += int(cursor.rowcount)
        return deleted_records

    def _inactive_guest_candidates(
        self,
        conn: sqlite3.Connection,
        *,
        cutoff: str,
        batch_size: int,
    ) -> list[str]:
        """Return only anonymous owners with no activity at/after ``cutoff``.

        A row whose activity is exactly the cutoff is retained.  Every child
        ledger participates so a recent tutor message or mode answer preserves
        an otherwise old profile.  A matching account or guest-claim receipt is
        an absolute preservation guard.
        """

        conditions = [
            "lp.updated_at < ?",
            "(lp.learner_id = 'demo' OR lp.learner_id GLOB 'g_*')",
            "NOT EXISTS (SELECT 1 FROM users u WHERE u.user_id = lp.learner_id)",
        ]
        params: list[Any] = [cutoff]
        if self._table_exists(conn, "guest_progress_claims"):
            conditions.append(
                "NOT EXISTS (SELECT 1 FROM guest_progress_claims gpc "
                "WHERE gpc.guest_learner_id = lp.learner_id)"
            )

        activity_predicates = (
            (
                "learner_preferences",
                "prefs.updated_at >= ?",
                "learner_preferences prefs",
                "prefs.learner_id",
            ),
            (
                "objective_mastery",
                "om.last_practiced_at >= ?",
                "objective_mastery om",
                "om.learner_id",
            ),
            (
                "subskill_retention_events",
                "sre.occurred_at >= ?",
                "subskill_retention_events sre",
                "sre.learner_id",
            ),
            (
                "guided_learning_events",
                "gle.created_at >= ?",
                "guided_learning_events gle",
                "gle.learner_id",
            ),
            (
                "learner_events",
                "le.occurred_at >= ?",
                "learner_events le",
                "le.owner_id",
            ),
            (
                "subskill_mastery",
                "(sm.last_practiced_at >= ? OR sm.last_independent_at >= ?)",
                "subskill_mastery sm",
                "sm.learner_id",
            ),
            ("attempts", "a.created_at >= ?", "attempts a", "a.learner_id"),
            (
                "pathway_progress",
                "pp.updated_at >= ?",
                "pathway_progress pp",
                "pp.learner_id",
            ),
            ("tutor_threads", "tt.updated_at >= ?", "tutor_threads tt", "tt.learner_id"),
            (
                "review_sessions",
                "rs.updated_at >= ?",
                "review_sessions rs",
                "rs.learner_id",
            ),
            ("rapid_rounds", "rr.updated_at >= ?", "rapid_rounds rr", "rr.learner_id"),
            (
                "clinical_shift_sessions",
                "css.updated_at >= ?",
                "clinical_shift_sessions css",
                "css.learner_id",
            ),
            (
                "training_campaigns",
                "tc.updated_at >= ?",
                "training_campaigns tc",
                "tc.learner_id",
            ),
        )
        for table_name, activity, source, owner_column in activity_predicates:
            if not self._table_exists(conn, table_name):
                continue
            conditions.append(
                f"NOT EXISTS (SELECT 1 FROM {source} "
                f"WHERE {owner_column} = lp.learner_id AND {activity})"
            )
            params.extend(
                [cutoff, cutoff]
                if table_name == "subskill_mastery"
                else [cutoff]
            )

        child_activity = (
            (
                "tutor_messages",
                "tutor_threads",
                "SELECT 1 FROM tutor_messages tm JOIN tutor_threads tt "
                "ON tt.thread_id = tm.thread_id WHERE tt.learner_id = lp.learner_id "
                "AND tm.created_at >= ?",
            ),
            (
                "rapid_round_answers",
                "rapid_rounds",
                "SELECT 1 FROM rapid_round_answers rra JOIN rapid_rounds rr "
                "ON rr.round_id = rra.round_id WHERE rr.learner_id = lp.learner_id "
                "AND rra.created_at >= ?",
            ),
            (
                "clinical_shift_answers",
                "clinical_shift_sessions",
                "SELECT 1 FROM clinical_shift_answers csa JOIN clinical_shift_sessions css "
                "ON css.session_id = csa.session_id WHERE css.learner_id = lp.learner_id "
                "AND csa.created_at >= ?",
            ),
            (
                "training_campaign_answers",
                "training_campaigns",
                "SELECT 1 FROM training_campaign_answers tca JOIN training_campaigns tc "
                "ON tc.campaign_id = tca.campaign_id WHERE tc.learner_id = lp.learner_id "
                "AND tca.created_at >= ?",
            ),
            (
                "training_campaign_slots",
                "training_campaigns",
                "SELECT 1 FROM training_campaign_slots tcs JOIN training_campaigns tc "
                "ON tc.campaign_id = tcs.campaign_id WHERE tc.learner_id = lp.learner_id "
                "AND (tcs.served_at >= ? OR tcs.answered_at >= ?)",
            ),
        )
        for child_table, parent_table, query in child_activity:
            if not (
                self._table_exists(conn, child_table)
                and self._table_exists(conn, parent_table)
            ):
                continue
            conditions.append(f"NOT EXISTS ({query})")
            params.extend(
                [cutoff, cutoff]
                if child_table == "training_campaign_slots"
                else [cutoff]
            )

        rows = conn.execute(
            "SELECT lp.learner_id FROM learner_profiles lp WHERE "
            + " AND ".join(conditions)
            + " ORDER BY lp.updated_at, lp.learner_id LIMIT ?",
            (*params, int(batch_size)),
        ).fetchall()
        return [str(row["learner_id"]) for row in rows]

    def _inactive_unverified_account_candidates(
        self,
        conn: sqlite3.Connection,
        *,
        cutoff: str,
        batch_size: int,
    ) -> list[str]:
        """Return never-verified account shells with no session or learning work."""

        conditions = [
            "((u.account_origin = 'pending_registration' "
            "AND u.email_normalized IS NOT NULL AND u.email_verified_at IS NULL) "
            "OR u.registration_reservation = 1)",
            "u.created_at < ?",
            "NOT EXISTS (SELECT 1 FROM sessions s WHERE s.user_id = u.user_id)",
        ]
        params: list[Any] = [cutoff]
        activity_specs = (
            ("learner_preferences", "learner_id", None),
            ("subskill_retention_events", "learner_id", None),
            ("guided_learning_events", "learner_id", None),
            ("learner_events", "owner_id", None),
            ("attempts", "learner_id", None),
            ("pathway_progress", "learner_id", None),
            ("tutor_threads", "learner_id", None),
            ("review_sessions", "learner_id", None),
            ("rapid_rounds", "learner_id", None),
            ("clinical_shift_sessions", "learner_id", None),
            ("training_campaigns", "learner_id", None),
            ("assessment_leases", "owner_id", None),
            ("objective_mastery", "learner_id", "attempts > 0"),
            ("subskill_mastery", "learner_id", "attempts > 0"),
        )
        for table, owner_column, extra in activity_specs:
            if not self._table_exists(conn, table):
                continue
            extra_clause = f" AND {extra}" if extra else ""
            conditions.append(
                f"NOT EXISTS (SELECT 1 FROM {table} activity "
                f"WHERE activity.{owner_column} = u.user_id{extra_clause})"
            )
        if self._table_exists(conn, "guest_progress_claims"):
            conditions.append(
                "NOT EXISTS (SELECT 1 FROM guest_progress_claims gpc "
                "WHERE gpc.user_id = u.user_id)"
            )
        rows = conn.execute(
            "SELECT u.user_id FROM users u WHERE "
            + " AND ".join(conditions)
            + " ORDER BY u.created_at, u.user_id LIMIT ?",
            (*params, int(batch_size)),
        ).fetchall()
        return [str(row["user_id"]) for row in rows]

    def cleanup_retention(
        self,
        *,
        now: datetime | str,
        guest_inactivity_days: int,
        batch_size: int,
        unverified_account_expiry_days: int = 7,
        _failure_hook: Callable[[sqlite3.Connection], None] | None = None,
    ) -> dict[str, int]:
        """Run one bounded, atomic privacy-retention batch.

        Expiry uses an inclusive boundary (``expires_at <= now``). Anonymous
        inactivity is strict (last activity ``< cutoff``), preserving records
        exactly on the configured boundary. Authenticated learner records are
        never candidates, even if their profile happens to use a guest-shaped
        identifier.
        """

        current = parse_instant(now)
        if current is None:
            raise ValueError("Retention cleanup time must be a valid instant")
        if guest_inactivity_days < 1:
            raise ValueError("Guest inactivity window must be at least one day")
        if batch_size < 1:
            raise ValueError("Retention cleanup batch size must be positive")
        if unverified_account_expiry_days < 1:
            raise ValueError("Unverified account expiry must be at least one day")
        now_iso = current.isoformat()
        cutoff = (current - timedelta(days=guest_inactivity_days)).isoformat()
        unverified_cutoff = (
            current - timedelta(days=unverified_account_expiry_days)
        ).isoformat()
        counts = {
            "expiredSessions": 0,
            "expiredExportAuthorizations": 0,
            "expiredAuthChallenges": 0,
            "expiredAuthVerificationBudgets": 0,
            "expiredMaintenanceLeases": 0,
            "inactiveGuestOwners": 0,
            "inactiveGuestRecords": 0,
            "expiredUnverifiedAccounts": 0,
        }

        def delete_expired(
            conn: sqlite3.Connection,
            *,
            table_name: str,
            key_column: str,
            count_key: str,
        ) -> None:
            if not self._table_exists(conn, table_name):
                return
            rows = conn.execute(
                f"SELECT {key_column} FROM {table_name} WHERE expires_at <= ? "
                f"ORDER BY expires_at, {key_column} LIMIT ?",
                (now_iso, int(batch_size)),
            ).fetchall()
            keys = [str(row[key_column]) for row in rows]
            if not keys:
                return
            placeholders = ",".join("?" for _ in keys)
            cursor = conn.execute(
                f"DELETE FROM {table_name} WHERE {key_column} IN ({placeholders}) "
                "AND expires_at <= ?",
                (*keys, now_iso),
            )
            counts[count_key] = int(cursor.rowcount)

        with self.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            delete_expired(
                conn,
                table_name="sessions",
                key_column="token",
                count_key="expiredSessions",
            )
            delete_expired(
                conn,
                table_name="export_authorizations",
                key_column="token_hash",
                count_key="expiredExportAuthorizations",
            )
            delete_expired(
                conn,
                table_name="auth_challenges",
                key_column="challenge_id",
                count_key="expiredAuthChallenges",
            )
            if self._table_exists(conn, "auth_verification_budgets"):
                expired_budgets = conn.execute(
                    "SELECT key_hash, purpose_group FROM auth_verification_budgets "
                    "WHERE window_expires_at <= ? ORDER BY window_expires_at, key_hash LIMIT ?",
                    (now_iso, int(batch_size)),
                ).fetchall()
                for budget in expired_budgets:
                    deleted_budget = conn.execute(
                        "DELETE FROM auth_verification_budgets WHERE key_hash = ? "
                        "AND purpose_group = ? AND window_expires_at <= ?",
                        (budget["key_hash"], budget["purpose_group"], now_iso),
                    )
                    counts["expiredAuthVerificationBudgets"] += int(
                        deleted_budget.rowcount
                    )
            delete_expired(
                conn,
                table_name="maintenance_leases",
                key_column="lease_name",
                count_key="expiredMaintenanceLeases",
            )

            guest_ids = self._inactive_guest_candidates(
                conn, cutoff=cutoff, batch_size=batch_size
            )
            for guest_id in guest_ids:
                # Reassert the account guard inside the same writer transaction
                # before cascading through owned child ledgers.
                if conn.execute(
                    "SELECT 1 FROM users WHERE user_id = ?", (guest_id,)
                ).fetchone():
                    continue
                counts["inactiveGuestRecords"] += self._delete_guest_owner_rows(
                    conn, guest_id
                )
                counts["inactiveGuestOwners"] += 1

            unverified_ids = self._inactive_unverified_account_candidates(
                conn,
                cutoff=unverified_cutoff,
                batch_size=batch_size,
            )
            for user_id in unverified_ids:
                self._retire_account_generation(
                    conn,
                    user_id,
                    reason="unverified_registration_expired",
                    retired_at=now_iso,
                )
                self._delete_guest_owner_rows(conn, user_id)
                if self._table_exists(conn, "auth_challenges"):
                    conn.execute(
                        "DELETE FROM auth_challenges WHERE user_id = ?", (user_id,)
                    )
                if self._table_exists(conn, "export_authorizations"):
                    conn.execute(
                        "DELETE FROM export_authorizations WHERE user_id = ?",
                        (user_id,),
                    )
                deleted = conn.execute(
                    "DELETE FROM users WHERE user_id = ? "
                    "AND ((account_origin = 'pending_registration' "
                    "AND email_verified_at IS NULL) OR registration_reservation = 1)",
                    (user_id,),
                )
                counts["expiredUnverifiedAccounts"] += int(deleted.rowcount)

            if _failure_hook is not None:
                _failure_hook(conn)
        return counts

    @staticmethod
    def _account_export_rows(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
        """Return readable JSON records while retaining unknown future columns.

        Persisted JSON fields are decoded under the same name without the
        ``_json`` suffix. Malformed legacy values remain strings instead of
        making a learner's entire export unavailable.
        """

        exported: list[dict[str, Any]] = []
        for row in rows:
            record: dict[str, Any] = {}
            for column in row.keys():
                value = row[column]
                key = column[:-5] if column.endswith("_json") else column
                if column.endswith("_json") and isinstance(value, str):
                    try:
                        value = json.loads(value)
                    except json.JSONDecodeError:
                        pass
                record[key] = value
            exported.append(record)
        return exported

    def _learning_record_ecg_reference(self, owner_id: str, value: object) -> object:
        """Pseudonymize a corpus key without making it a live waveform credential."""

        if value in (None, "") or is_ecg_capability(value):
            return value
        return issue_ecg_capability(
            self._public_reference_secret,
            owner_id,
            "learning-record",
            "history",
            str(value),
        )

    def _learning_record_internal_reference(self, owner_id: str, value: object) -> object:
        """Return a stable owner-scoped alias for an internal scenario identifier."""

        if value in (None, ""):
            return value
        normalized = str(value)
        if normalized.startswith("lr_"):
            return normalized
        material = bytearray(_LEARNING_RECORD_REFERENCE_DOMAIN)
        for field in (owner_id, normalized):
            encoded = str(field).encode("utf-8")
            material.extend(len(encoded).to_bytes(4, "big"))
            material.extend(encoded)
        digest = hmac.new(
            self._public_reference_secret.encode("utf-8"),
            bytes(material),
            hashlib.sha256,
        ).digest()
        token = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
        return f"lr_{token}"

    def _sanitize_learning_record_tree(self, owner_id: str, value: Any) -> Any:
        """Remove canonical ECG and authored-item identifiers from nested records."""

        if isinstance(value, list):
            return [self._sanitize_learning_record_tree(owner_id, item) for item in value]
        if not isinstance(value, dict):
            return value

        sanitized: dict[str, Any] = {}
        for key, child in value.items():
            if key in _LEARNING_RECORD_ECG_KEYS:
                if isinstance(child, list):
                    sanitized[key] = [
                        self._learning_record_ecg_reference(owner_id, item)
                        for item in child
                    ]
                else:
                    sanitized[key] = self._learning_record_ecg_reference(owner_id, child)
            elif key in _LEARNING_RECORD_ITEM_KEYS:
                if isinstance(child, list):
                    sanitized[key] = [
                        self._learning_record_internal_reference(owner_id, item)
                        for item in child
                    ]
                else:
                    sanitized[key] = self._learning_record_internal_reference(owner_id, child)
            elif key in _LEARNING_RECORD_DISPLAY_KEYS:
                reference = self._learning_record_ecg_reference(owner_id, child)
                sanitized[key] = (
                    f"ECG {str(reference)[-8:]}" if reference not in (None, "") else reference
                )
            elif key in _LEARNING_RECORD_EVENT_KEYS:
                sanitized[key] = self._learning_record_internal_reference(owner_id, child)
            else:
                sanitized[key] = self._sanitize_learning_record_tree(owner_id, child)
        return sanitized

    def _sanitize_account_export_identifiers(
        self,
        owner_id: str,
        records: dict[str, list[dict[str, Any]]],
    ) -> dict[str, list[dict[str, Any]]]:
        """Keep progress portable while withholding corpus lookup credentials."""

        sanitized = self._sanitize_learning_record_tree(owner_id, records)

        # These legacy list fields have no element-level key. Their meaning is
        # fixed by the owning table, so transform them explicitly after the
        # general keyed walk.
        for record_name in ("reviewSessions", "rapidRounds"):
            for row in sanitized.get(record_name, []):
                for field in ("served", "exclusions"):
                    if isinstance(row.get(field), list):
                        row[field] = [
                            self._learning_record_ecg_reference(owner_id, item)
                            for item in row[field]
                        ]
        for row in sanitized.get("clinicalShiftSessions", []):
            if isinstance(row.get("served"), list):
                row["served"] = [
                    self._learning_record_internal_reference(owner_id, item)
                    for item in row["served"]
                ]
        return sanitized

    def learning_record_integrity(self) -> tuple[bool, str]:
        """Validate semantic invariants that a writable SQLite probe misses."""

        try:
            with self.connect() as conn:
                physical = conn.execute("PRAGMA integrity_check").fetchone()
                if not physical or str(physical[0]).lower() != "ok":
                    return False, "sqlite_integrity_failed"
                if conn.execute("PRAGMA foreign_key_check").fetchone() is not None:
                    return False, "foreign_key_integrity_failed"
                if self._table_exists(conn, "subskill_mastery"):
                    cells = conn.execute(
                        "SELECT DISTINCT concept, subskill FROM subskill_mastery"
                    ).fetchall()
                    if any(
                        not validate_objective_subskill(str(row["concept"]), str(row["subskill"]))
                        for row in cells
                    ):
                        return False, "unknown_objective_registry_cell"
                if self._table_exists(conn, "rapid_round_answers"):
                    rows = conn.execute(
                        "SELECT receipts_json, integrity_status FROM rapid_round_answers"
                    ).fetchall()
                    for row in rows:
                        if str(row["integrity_status"]) == "legacy_incomplete":
                            continue
                        try:
                            receipts = json.loads(row["receipts_json"] or "[]")
                        except (TypeError, json.JSONDecodeError):
                            return False, "rapid_receipt_json_invalid"
                        if not isinstance(receipts, list) or not receipts:
                            return False, "rapid_answer_receipts_incomplete"
        except Exception:
            return False, "learning_record_integrity_query_failed"
        return True, "ready"

    def export_user_progress(self, user_id: str) -> dict[str, Any] | None:
        """Build a portable, owner-scoped account/progress document.

        The allowlist intentionally excludes password hashes, reusable session
        material, rate-limit buckets, and corpus answer keys. Child ledgers are
        selected only through a session/thread owned by ``user_id``.
        """

        with self.connect() as conn:
            user = conn.execute(
                "SELECT user_id, username, display_name, created_at "
                "FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if not user:
                return None

            # An export is a learning record, not a second assessment API.
            # Freeze an explicit column allowlist so newly added server-owned
            # answer contracts can never leak through a future ``SELECT *``.
            direct_specs = (
                ("learnerProfiles", "learner_profiles", "learner_id, display_name, created_at, updated_at", "created_at"),
                ("learnerPreferences", "learner_preferences", "learner_id, training_stage, primary_goal, default_session_length, rapid_pace, guidance_level, reduce_motion, large_controls, created_at, updated_at", "created_at"),
                ("objectiveMastery", "objective_mastery", "learner_id, objective, mastery, attempts, correct, high_confidence_wrong, last_practiced_at", "objective"),
                ("subskillMastery", "subskill_mastery", "learner_id, concept, subskill, formative_score, independent_mastery, attempts, independent_attempts, correct, high_confidence_wrong, last_practiced_at, next_due_at, stability_days, lapses, spaced_retrievals, distinct_eligible_ecgs, distinct_successful_ecgs, distinct_modes, distinct_morphologies, last_independent_at, last_independent_correct", "concept, subskill"),
                ("retentionEvents", "subskill_retention_events", "id, guided_event_id, learner_id, concept, subskill, case_id, mode, morphology_key, correct, registry_version, occurred_at", "id"),
                ("attempts", "attempts", "id, learner_id, case_id, mode, structured_answer_json, free_text_answer, confidence, hints_used, score, correct_objectives_json, missed_objectives_json, misconception_tags_json, feedback, registry_version, created_at", "id"),
                ("guidedLearningEvents", "guided_learning_events", "id, learner_id, module_id, scene_id, interaction_id, concept, subskills_json, score, correct, attempts, assistance, hints_used, confidence, requested_evidence_level, effective_evidence_level, case_id, case_provenance, case_eligible, misconception_tags_json, event_key, receipt_json, registry_version, created_at", "id"),
                ("pathwayProgress", "pathway_progress", "learner_id, pathway_id, module_id, scene_id, status, active_interaction_index, completed_action_ids_json, state_json, source, created_at, updated_at", "updated_at"),
                ("reviewSessions", "review_sessions", "session_id, learner_id, label, objectives_json, target_mastery, max_cases, served_json, status, created_at, updated_at", "created_at"),
                # Deliberately omit pending_manifest_json: it is the current
                # Rapid answer contract and must remain server-only precommit.
                ("rapidRounds", "rapid_rounds", "round_id, learner_id, pace, length, assessment_scope, focus_concept, focus_subskill, context_key, exclusions_json, served_json, pending_case_id, feedback_case_id, pending_started_at, pending_deadline_at, deadline_seconds, position, status, created_at, updated_at", "created_at"),
                ("clinicalShiftSessions", "clinical_shift_sessions", "session_id, learner_id, lane, tier, focus_objective, focus_subskill, length, requested_length, available_length, length_reason, served_json, served_ecgs_json, calibration_json, pending_item_id, feedback_item_id, pending_context_revealed, pending_first_look_json, pending_step_answers_json, pending_orient_started_at, pending_orient_deadline_at, pending_decide_started_at, pending_decide_deadline_at, pending_decide_submitted_at, position, status, created_at, updated_at", "created_at"),
            )
            records: dict[str, list[dict[str, Any]]] = {}
            for export_name, table_name, columns, order_by in direct_specs:
                if not self._table_exists(conn, table_name):
                    records[export_name] = []
                    continue
                rows = conn.execute(
                    f"SELECT {columns} FROM {table_name} WHERE learner_id = ? ORDER BY {order_by}",
                    (user_id,),
                ).fetchall()
                records[export_name] = self._account_export_rows(rows)

            # The normalized event ledger is deliberately answer-free. Export
            # its provenance and competency evidence, but never lease claim
            # hashes or ECG exposure rows for a still-pending assessment.
            if self._table_exists(conn, "learner_events"):
                event_rows = conn.execute(
                    "SELECT event_id, owner_id, mode, session_id, lease_id, ecg_id, "
                    "event_type, evidence_level, integrity_status, score, occurred_at, created_at "
                    "FROM learner_events WHERE owner_id = ? ORDER BY occurred_at, event_id",
                    (user_id,),
                ).fetchall()
                records["learnerEvents"] = self._account_export_rows(event_rows)
            else:
                records["learnerEvents"] = []
            if (
                self._table_exists(conn, "learner_event_competencies")
                and self._table_exists(conn, "learner_events")
            ):
                competency_rows = conn.execute(
                    "SELECT lec.event_id, lec.competency_id, lec.competency_score "
                    "FROM learner_event_competencies lec JOIN learner_events le "
                    "ON le.event_id = lec.event_id WHERE le.owner_id = ? "
                    "ORDER BY lec.event_id, lec.competency_id",
                    (user_id,),
                ).fetchall()
                records["learnerEventCompetencies"] = self._account_export_rows(competency_rows)
            else:
                records["learnerEventCompetencies"] = []
            if self._table_exists(conn, "assessment_leases"):
                lease_rows = conn.execute(
                    "SELECT lease_id, owner_id, mode, session_id, state, integrity_status, "
                    "expires_at, created_at, updated_at, claimed_at, terminal_at "
                    "FROM assessment_leases WHERE owner_id = ? ORDER BY created_at, lease_id",
                    (user_id,),
                ).fetchall()
                records["assessmentLeases"] = self._account_export_rows(lease_rows)
            else:
                records["assessmentLeases"] = []
            if (
                self._table_exists(conn, "assessment_lease_cases")
                and self._table_exists(conn, "assessment_leases")
            ):
                exposure_rows = conn.execute(
                    "SELECT alc.lease_id, alc.ecg_id, alc.ordinal "
                    "FROM assessment_lease_cases alc JOIN assessment_leases al "
                    "ON al.lease_id = alc.lease_id WHERE al.owner_id = ? "
                    "AND al.state NOT IN ('active', 'submitting') "
                    "ORDER BY alc.lease_id, alc.ordinal",
                    (user_id,),
                ).fetchall()
                records["assessmentLeaseCases"] = self._account_export_rows(exposure_rows)
            else:
                records["assessmentLeaseCases"] = []

            pending_ids: set[str] = set()
            if self._table_exists(conn, "training_campaigns"):
                pending_ids.update(
                    str(row["pending_case_id"])
                    for row in conn.execute(
                        "SELECT pending_case_id FROM training_campaigns "
                        "WHERE learner_id = ? AND status = 'active' AND pending_case_id IS NOT NULL",
                        (user_id,),
                    ).fetchall()
                )
            if self._table_exists(conn, "rapid_rounds"):
                pending_ids.update(
                    str(row["pending_case_id"])
                    for row in conn.execute(
                        "SELECT pending_case_id FROM rapid_rounds "
                        "WHERE learner_id = ? AND status = 'active' AND pending_case_id IS NOT NULL",
                        (user_id,),
                    ).fetchall()
                )
            pending_clinical_items: set[str] = set()
            if self._table_exists(conn, "clinical_shift_sessions"):
                pending_clinical_items.update(
                    str(row["pending_item_id"])
                    for row in conn.execute(
                        "SELECT pending_item_id FROM clinical_shift_sessions "
                        "WHERE learner_id = ? AND status = 'active' AND pending_item_id IS NOT NULL",
                        (user_id,),
                    ).fetchall()
                )

            # Historic answer-bearing rows for an ECG being reassessed are
            # temporarily withheld. Otherwise an export could bypass the same
            # pending-assessment guard enforced by the tutor/history APIs.
            if pending_ids:
                for export_name in ("retentionEvents", "attempts", "guidedLearningEvents"):
                    records[export_name] = [
                        row for row in records[export_name]
                        if str(row.get("case_id") or "") not in pending_ids
                    ]

            tutor_rows: list[sqlite3.Row] = []
            if self._table_exists(conn, "tutor_threads"):
                tutor_rows = conn.execute(
                    "SELECT thread_id, learner_id, mode, lesson_id, case_id, scope_key, title, created_at, updated_at "
                    "FROM tutor_threads WHERE learner_id = ? ORDER BY created_at",
                    (user_id,),
                ).fetchall()
                tutor_rows = [
                    row for row in tutor_rows
                    if str(row["case_id"] or "") not in pending_ids | pending_clinical_items
                ]
            records["tutorThreads"] = self._account_export_rows(tutor_rows)

            child_specs = (
                (
                    "rapidRoundAnswers",
                    "rapid_round_answers",
                    "id, round_id, case_id, response_json, grade_json, tutor_json, result_json, trace_grade_json, tested_manifest_json, receipts_json, integrity_status, attempt_id, created_at",
                    "round_id IN (SELECT round_id FROM rapid_rounds WHERE learner_id = ?)",
                    "id",
                ),
                (
                    "clinicalShiftAnswers",
                    "clinical_shift_answers",
                    "id, session_id, item_id, ecg_id, response_json, grade_json, receipts_json, score, correct, answer_time_ms, calibration_event_json, attempt_id, created_at",
                    "session_id IN (SELECT session_id FROM clinical_shift_sessions WHERE learner_id = ?)",
                    "id",
                ),
            )
            for export_name, table_name, columns, owner_predicate, order_by in child_specs:
                if not self._table_exists(conn, table_name):
                    records[export_name] = []
                    continue
                rows = conn.execute(
                    f"SELECT {columns} FROM {table_name} WHERE {owner_predicate} ORDER BY {order_by}",
                    (user_id,),
                ).fetchall()
                if export_name == "rapidRoundAnswers" and pending_ids:
                    rows = [row for row in rows if str(row["case_id"]) not in pending_ids]
                if export_name == "clinicalShiftAnswers" and pending_clinical_items:
                    rows = [row for row in rows if str(row["item_id"]) not in pending_clinical_items]
                records[export_name] = self._account_export_rows(rows)

            allowed_thread_ids = [str(row["thread_id"]) for row in tutor_rows]
            if self._table_exists(conn, "tutor_messages") and allowed_thread_ids:
                placeholders = ",".join("?" for _ in allowed_thread_ids)
                message_rows = conn.execute(
                    "SELECT id, thread_id, role, content, actions_json, meta_json, created_at "
                    f"FROM tutor_messages WHERE thread_id IN ({placeholders}) ORDER BY id",
                    allowed_thread_ids,
                ).fetchall()
                records["tutorMessages"] = self._account_export_rows(message_rows)
            else:
                records["tutorMessages"] = []

            if self._table_exists(conn, "guest_progress_claims"):
                claim_rows = conn.execute(
                    "SELECT guest_learner_id, user_id, claimed_at, summary_json "
                    "FROM guest_progress_claims WHERE user_id = ? ORDER BY claimed_at",
                    (user_id,),
                ).fetchall()
                records["guestProgressClaims"] = self._account_export_rows(claim_rows)
            else:
                records["guestProgressClaims"] = []

            if self._table_exists(conn, "training_campaigns"):
                campaign_rows = conn.execute(
                    "SELECT campaign_id, learner_id, concept_id, subskill, requested_length, length, "
                    "pool_count, phases_json, phase_counts_json, position, pending_case_id, feedback_case_id, "
                    "status, context_key, roster_policy_json, created_at, updated_at, abandoned_at "
                    "FROM training_campaigns WHERE learner_id = ? ORDER BY created_at",
                    (user_id,),
                ).fetchall()
                records["trainingCampaigns"] = self._account_export_rows(campaign_rows)
                # Only answered slots are part of the learner's record. Queued
                # and pending slots contain target_present/case_focus—the
                # answer key for current and future practice ECGs.
                slot_rows = conn.execute(
                    "SELECT campaign_id, ordinal, phase, case_id, case_focus, target_present, "
                    "selection_reason, status, served_at, answered_at "
                    "FROM training_campaign_slots WHERE status = 'answered' AND campaign_id IN "
                    "(SELECT campaign_id FROM training_campaigns WHERE learner_id = ?) "
                    "ORDER BY campaign_id, ordinal",
                    (user_id,),
                ).fetchall()
                if pending_ids:
                    slot_rows = [row for row in slot_rows if str(row["case_id"]) not in pending_ids]
                records["trainingCampaignSlots"] = self._account_export_rows(slot_rows)
                answer_rows = conn.execute(
                    "SELECT id, campaign_id, ordinal, case_id, response_json, grade_json, tutor_json, "
                    "receipt_json, summary_json, integrity_status, attempt_id, created_at "
                    "FROM training_campaign_answers WHERE campaign_id IN "
                    "(SELECT campaign_id FROM training_campaigns WHERE learner_id = ?) "
                    "ORDER BY id",
                    (user_id,),
                ).fetchall()
                if pending_ids:
                    answer_rows = [row for row in answer_rows if str(row["case_id"]) not in pending_ids]
                records["trainingCampaignAnswers"] = self._account_export_rows(answer_rows)
            else:
                records["trainingCampaigns"] = []
                records["trainingCampaignSlots"] = []
                records["trainingCampaignAnswers"] = []

        records = self._sanitize_account_export_identifiers(user_id, records)
        public_user = dict(user)
        return {
            "schemaVersion": "ecg-student-progress-v2",
            "exportedAt": utc_now(),
            "assessmentPrivacy": {
                "pendingAndFutureAnswerContractsOmitted": True,
                "corpusIdentifiersPseudonymized": True,
                "note": "Finish or leave an active ECG before expecting its prior answer-bearing history in an export.",
            },
            "account": {
                "userId": public_user["user_id"],
                "username": public_user["username"],
                "displayName": public_user["display_name"],
                "createdAt": public_user["created_at"],
            },
            "recordCounts": {name: len(items) for name, items in records.items()},
            "records": records,
        }

    def delete_guest_learning_record(
        self,
        guest_id: str,
        *,
        _failure_hook: Callable[[sqlite3.Connection], None] | None = None,
    ) -> int:
        """Delete one guest owner's complete learning record atomically.

        Child ledgers are removed through their owned session/thread parent.
        The optional private hook exists only for transaction rollback tests and
        is never reachable from an HTTP request.
        """

        with self.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            # A caller bug must never turn guest erasure into account deletion.
            if conn.execute(
                "SELECT 1 FROM users WHERE user_id = ?", (guest_id,)
            ).fetchone():
                raise ValueError("Authenticated account owners cannot be deleted as guests")
            deleted_records = self._delete_guest_owner_rows(conn, guest_id)

            if _failure_hook is not None:
                _failure_hook(conn)
        return deleted_records

    def delete_user_account(self, user_id: str, expected_password_hash: str) -> bool:
        """Delete one account and every directly or transitively owned record.

        The password-hash equality check closes the gap between the slow
        password verification and this immediate transaction. Tables without a
        direct learner id are deleted only through an owned parent id.
        """

        with self.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            user = conn.execute(
                "SELECT password_hash FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if not user or not hmac.compare_digest(
                str(user["password_hash"]), expected_password_hash
            ):
                return False

            self._retire_account_generation(
                conn,
                user_id,
                reason="owner_deleted",
            )

            child_deletes = (
                (
                    "learner_event_competencies",
                    "event_id IN (SELECT event_id FROM learner_events WHERE owner_id = ?)",
                ),
                (
                    "assessment_lease_cases",
                    "lease_id IN (SELECT lease_id FROM assessment_leases WHERE owner_id = ?)",
                ),
                (
                    "tutor_messages",
                    "thread_id IN (SELECT thread_id FROM tutor_threads WHERE learner_id = ?)",
                ),
                (
                    "rapid_round_answers",
                    "round_id IN (SELECT round_id FROM rapid_rounds WHERE learner_id = ?)",
                ),
                (
                    "clinical_shift_answers",
                    "session_id IN (SELECT session_id FROM clinical_shift_sessions WHERE learner_id = ?)",
                ),
                (
                    "training_campaign_answers",
                    "campaign_id IN (SELECT campaign_id FROM training_campaigns WHERE learner_id = ?)",
                ),
                (
                    "training_campaign_slots",
                    "campaign_id IN (SELECT campaign_id FROM training_campaigns WHERE learner_id = ?)",
                ),
            )
            for table_name, predicate in child_deletes:
                if self._table_exists(conn, table_name):
                    conn.execute(
                        f"DELETE FROM {table_name} WHERE {predicate}",
                        (user_id,),
                    )

            direct_tables = (
                "learner_events",
                "assessment_leases",
                "learner_preferences",
                "subskill_retention_events",
                "guided_learning_events",
                "objective_mastery",
                "subskill_mastery",
                "attempts",
                "pathway_progress",
                "tutor_threads",
                "review_sessions",
                "rapid_rounds",
                "clinical_shift_sessions",
                "training_campaigns",
                "learner_profiles",
                "sessions",
                "auth_challenges",
            )
            for table_name in direct_tables:
                if self._table_exists(conn, table_name):
                    owner_column = (
                        "user_id"
                        if table_name in {"sessions", "auth_challenges"}
                        else "owner_id"
                        if table_name in {"learner_events", "assessment_leases"}
                        else "learner_id"
                    )
                    conn.execute(
                        f"DELETE FROM {table_name} WHERE {owner_column} = ?",
                        (user_id,),
                    )
            if self._table_exists(conn, "guest_progress_claims"):
                conn.execute(
                    "DELETE FROM guest_progress_claims WHERE user_id = ?",
                    (user_id,),
                )
            if self._table_exists(conn, "export_authorizations"):
                conn.execute(
                    "DELETE FROM export_authorizations WHERE user_id = ?",
                    (user_id,),
                )
            deleted = conn.execute(
                "DELETE FROM users WHERE user_id = ? AND password_hash = ?",
                (user_id, expected_password_hash),
            )
            if deleted.rowcount != 1:
                raise RuntimeError("Account deletion lost ownership during transaction")
        return True

    def _consume_auth_hash_reservation(
        self,
        *,
        table_name: str,
        buckets: tuple[tuple[str, str, int], ...],
        window_minutes: int,
        block_minutes: int,
    ) -> bool:
        """Atomically reserve one expensive auth hash across nested buckets.

        Buckets must be ordered from narrowest to broadest.  Only a request
        admitted by every bucket increments counters; when a bucket rejects,
        just that bucket records the block.  This keeps the counters equal to
        actual password-hash work and prevents a narrowly blocked caller from
        cheaply exhausting broader classroom-IP or deployment capacity.
        """

        if table_name not in {"auth_registration_throttle", "auth_login_throttle"}:
            raise ValueError("Unsupported authentication throttle table")
        now_dt = datetime.now(UTC)
        now = now_dt.isoformat()
        cutoff = now_dt - timedelta(hours=24)
        with self.connect() as conn:
            try:
                if not conn.in_transaction:
                    conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    f"DELETE FROM {table_name} WHERE updated_at < ?",
                    (cutoff.isoformat(),),
                )
                states: list[dict[str, Any]] = []
                for scope, key_hash, ceiling in buckets:
                    row = conn.execute(
                        "SELECT attempt_count, window_started_at, blocked_until "
                        f"FROM {table_name} WHERE scope = ? AND key_hash = ?",
                        (scope, key_hash),
                    ).fetchone()
                    count = 0
                    window_start = now_dt
                    active_block_until: str | None = None
                    if row:
                        try:
                            stored_window_start = datetime.fromisoformat(
                                row["window_started_at"]
                            )
                        except ValueError:
                            stored_window_start = now_dt
                        try:
                            stored_block = (
                                datetime.fromisoformat(row["blocked_until"])
                                if row["blocked_until"]
                                else None
                            )
                        except ValueError:
                            stored_block = None
                        if stored_block and stored_block > now_dt:
                            active_block_until = row["blocked_until"]
                        if stored_window_start >= now_dt - timedelta(
                            minutes=window_minutes
                        ):
                            window_start = stored_window_start
                            count = int(row["attempt_count"])
                    states.append(
                        {
                            "scope": scope,
                            "key_hash": key_hash,
                            "ceiling": max(0, int(ceiling)),
                            "count": count,
                            "window_start": window_start,
                            "active_block_until": active_block_until,
                        }
                    )

                blocked_state = next(
                    (
                        state
                        for state in states
                        if state["active_block_until"]
                        or state["count"] >= state["ceiling"]
                    ),
                    None,
                )
                for state in [blocked_state] if blocked_state else states:
                    assert state is not None
                    count = int(state["count"])
                    blocked_until = None
                    if blocked_state:
                        blocked_until = state["active_block_until"] or (
                            now_dt + timedelta(minutes=block_minutes)
                        ).isoformat()
                    else:
                        count += 1
                    conn.execute(
                        f"INSERT INTO {table_name} "
                        "(scope, key_hash, attempt_count, window_started_at, blocked_until, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, ?) "
                        "ON CONFLICT(scope, key_hash) DO UPDATE SET "
                        "attempt_count = excluded.attempt_count, "
                        "window_started_at = excluded.window_started_at, "
                        "blocked_until = excluded.blocked_until, updated_at = excluded.updated_at",
                        (
                            state["scope"],
                            state["key_hash"],
                            count,
                            state["window_start"].isoformat(),
                            blocked_until,
                            now,
                        ),
                    )
                # Pair keys are username-controlled.  Aggregate buckets remain
                # while the least-recently-updated high-cardinality rows prune.
                conn.execute(
                    f"DELETE FROM {table_name} WHERE rowid IN ("
                    f"SELECT rowid FROM {table_name} "
                    "ORDER BY updated_at DESC LIMIT -1 OFFSET 50000)"
                )
            except Exception:
                conn.rollback()
                raise
        return blocked_state is not None

    def consume_registration_attempt(
        self,
        *,
        pair_key_hash: str,
        ip_key_hash: str,
        global_key_hash: str,
        max_pair_attempts: int,
        max_ip_attempts: int,
        max_global_attempts: int,
        window_minutes: int,
        block_minutes: int,
    ) -> bool:
        """Reserve registration hashing without persisting raw identifiers."""

        return self._consume_auth_hash_reservation(
            table_name="auth_registration_throttle",
            buckets=(
                ("pair", pair_key_hash, max_pair_attempts),
                ("ip", ip_key_hash, max_ip_attempts),
                ("global", global_key_hash, max_global_attempts),
            ),
            window_minutes=window_minutes,
            block_minutes=block_minutes,
        )

    def consume_login_attempt(
        self,
        *,
        pair_key_hash: str,
        ip_key_hash: str,
        global_key_hash: str,
        max_pair_attempts: int,
        max_ip_attempts: int,
        max_global_attempts: int,
        window_minutes: int,
        block_minutes: int,
    ) -> bool:
        """Reserve a login hash attempt before any expensive password work.

        All identifiers arrive as domain-separated HMAC digests.  Pair limits
        prevent focused guessing without making a username globally lockable;
        IP and deployment-wide limits bound random-username and distributed
        CPU exhaustion.  Every admitted request consumes capacity, including a
        successful one, because the slow hash has been reserved; rejected work
        never drains a broader bucket.
        """

        return self._consume_auth_hash_reservation(
            table_name="auth_login_throttle",
            buckets=(
                ("pair", pair_key_hash, max_pair_attempts),
                ("ip", ip_key_hash, max_ip_attempts),
                ("global", global_key_hash, max_global_attempts),
            ),
            window_minutes=window_minutes,
            block_minutes=block_minutes,
        )

    def clear_login_pair_attempts(self, pair_key_hash: str) -> None:
        """Let a verified learner recover from typos without erasing CPU limits."""

        with self.connect() as conn:
            conn.execute(
                "DELETE FROM auth_login_throttle WHERE scope = 'pair' AND key_hash = ?",
                (pair_key_hash,),
            )

    # --- remote tutor quotas ---------------------------------------------------

    def consume_remote_tutor_quota(
        self,
        *,
        learner_id: str,
        client_ip: str,
        hash_secret: str,
        authenticated: bool,
        authenticated_daily_limit: int,
        guest_daily_limit: int,
        ip_hourly_limit: int,
        global_daily_limit: int,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Atomically reserve one remote-model call across durable limits.

        The database stores only domain-separated HMAC digests, never a learner
        id or IP address. A reservation is consumed before the network call and
        remains consumed if the provider fails; this prevents retry storms from
        bypassing the spend boundary. Deterministic tutor fallbacks do not call
        this method and therefore remain available after a limit is reached.
        """

        instant = now or datetime.now(UTC)
        if instant.tzinfo is None:
            instant = instant.replace(tzinfo=UTC)
        instant = instant.astimezone(UTC)
        day_start = instant.replace(hour=0, minute=0, second=0, microsecond=0)
        hour_start = instant.replace(minute=0, second=0, microsecond=0)
        learner_limit = (
            int(authenticated_daily_limit) if authenticated else int(guest_daily_limit)
        )
        limits = {
            "learnerDaily": learner_limit,
            "ipHourly": int(ip_hourly_limit),
            "globalDaily": int(global_daily_limit),
        }
        if not hash_secret or any(value <= 0 for value in limits.values()):
            raise ValueError("Remote tutor quota configuration must use a secret and positive limits")

        secret = hash_secret.encode("utf-8")

        def digest(scope: str, value: str) -> str:
            return hmac.new(
                secret,
                f"ecg-remote-tutor-quota-v1\0{scope}\0{value}".encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()

        buckets = [
            {
                "scope": "learner_day",
                "key": digest("learner", learner_id),
                "window": day_start,
                "limit": learner_limit,
                "reason": "learner_daily",
                "remainingKey": "learnerDaily",
                "reset": day_start + timedelta(days=1),
            },
            {
                "scope": "ip_hour",
                "key": digest("ip", client_ip or "unknown"),
                "window": hour_start,
                "limit": int(ip_hourly_limit),
                "reason": "ip_hourly",
                "remainingKey": "ipHourly",
                "reset": hour_start + timedelta(hours=1),
            },
            {
                "scope": "global_day",
                "key": digest("global", "all"),
                "window": day_start,
                "limit": int(global_daily_limit),
                "reason": "global_daily",
                "remainingKey": "globalDaily",
                "reset": day_start + timedelta(days=1),
            },
        ]

        with self.connect() as conn:
            # A single writer reservation closes the select/increment race both
            # for the file-backed production DB and concurrent FastAPI workers.
            conn.execute("BEGIN IMMEDIATE")
            counts: dict[str, int] = {}
            for bucket in buckets:
                row = conn.execute(
                    "SELECT request_count FROM remote_tutor_quota_buckets "
                    "WHERE scope = ? AND key_hash = ? AND window_start = ?",
                    (
                        bucket["scope"],
                        bucket["key"],
                        bucket["window"].isoformat(),
                    ),
                ).fetchone()
                counts[bucket["remainingKey"]] = int(row["request_count"]) if row else 0

            blocked = next(
                (
                    bucket
                    for bucket in buckets
                    if counts[bucket["remainingKey"]] >= int(bucket["limit"])
                ),
                None,
            )
            if blocked is None:
                stamp = instant.isoformat()
                for bucket in buckets:
                    conn.execute(
                        "INSERT INTO remote_tutor_quota_buckets "
                        "(scope, key_hash, window_start, request_count, updated_at) "
                        "VALUES (?, ?, ?, 1, ?) "
                        "ON CONFLICT(scope, key_hash, window_start) DO UPDATE SET "
                        "request_count = request_count + 1, updated_at = excluded.updated_at",
                        (
                            bucket["scope"],
                            bucket["key"],
                            bucket["window"].isoformat(),
                            stamp,
                        ),
                    )
                    counts[bucket["remainingKey"]] += 1
                # Bound telemetry cardinality without touching current windows.
                conn.execute(
                    "DELETE FROM remote_tutor_quota_buckets WHERE updated_at < ?",
                    ((day_start - timedelta(days=8)).isoformat(),),
                )

        remaining = {
            key: max(0, limits[key] - count)
            for key, count in counts.items()
        }
        return {
            "allowed": blocked is None,
            "reason": blocked["reason"] if blocked else None,
            "resetAt": blocked["reset"].isoformat() if blocked else None,
            "remaining": remaining,
            "limits": limits,
        }

    # --- tutor conversation threads --------------------------------------------

    def ensure_thread(
        self,
        learner_id: str,
        thread_id: str | None = None,
        mode: str = "freeform",
        lesson_id: str | None = None,
        case_id: str | None = None,
        scope_key: str | None = None,
        title: str | None = None,
    ) -> str:
        import uuid

        now = utc_now()
        with self.connect() as conn:
            if thread_id:
                existing = conn.execute(
                    "SELECT thread_id FROM tutor_threads WHERE thread_id = ?", (thread_id,)
                ).fetchone()
                if existing:
                    conn.execute(
                        "UPDATE tutor_threads SET updated_at = ?, mode = ?, "
                        "lesson_id = COALESCE(?, lesson_id), case_id = COALESCE(?, case_id), "
                        "scope_key = COALESCE(?, scope_key) WHERE thread_id = ?",
                        (now, mode, lesson_id, case_id, scope_key, thread_id),
                    )
                    return thread_id
            new_id = thread_id or f"th_{uuid.uuid4().hex[:16]}"
            conn.execute(
                "INSERT INTO tutor_threads (thread_id, learner_id, mode, lesson_id, case_id, scope_key, title, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (new_id, learner_id, mode, lesson_id, case_id, scope_key, title or "ECG tutor session", now, now),
            )
            return new_id

    def append_tutor_message(
        self,
        thread_id: str,
        role: str,
        content: str,
        actions: list[Any] | None = None,
        meta: dict[str, Any] | None = None,
    ) -> int:
        now = utc_now()
        with self.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO tutor_messages (thread_id, role, content, actions_json, meta_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (thread_id, role, content, json.dumps(actions or []), json.dumps(meta or {}), now),
            )
            conn.execute("UPDATE tutor_threads SET updated_at = ? WHERE thread_id = ?", (now, thread_id))
            return int(cursor.lastrowid)

    def thread_history(self, thread_id: str, limit: int = 40) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT role, content, actions_json, meta_json, created_at FROM ("
                "SELECT id, role, content, actions_json, meta_json, created_at FROM tutor_messages "
                "WHERE thread_id = ? ORDER BY id DESC LIMIT ?) recent ORDER BY id ASC",
                (thread_id, limit),
            ).fetchall()
        return [
            {
                "role": row["role"],
                "content": row["content"],
                "viewerActions": json.loads(row["actions_json"]),
                "meta": json.loads(row["meta_json"]),
                "createdAt": row["created_at"],
            }
            for row in rows
        ]

    def get_thread(self, thread_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT thread_id, learner_id, mode, lesson_id, case_id, scope_key, title, created_at, updated_at "
                "FROM tutor_threads WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "threadId": row["thread_id"],
            "learnerId": row["learner_id"],
            "mode": row["mode"],
            "lessonId": row["lesson_id"],
            "caseId": row["case_id"],
            "scopeKey": row["scope_key"],
            "title": row["title"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
            "messages": self.thread_history(row["thread_id"]),
        }

    def list_threads(
        self,
        learner_id: str,
        *,
        mode: str | None = None,
        lesson_id: str | None = None,
        case_id: str | None = None,
        scope_key: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        sql = (
            "SELECT thread_id, learner_id, mode, lesson_id, case_id, scope_key, title, created_at, updated_at "
            "FROM tutor_threads WHERE learner_id = ?"
        )
        params: list[Any] = [learner_id]
        if mode is not None:
            sql += " AND mode = ?"
            params.append(mode)
        if lesson_id is not None:
            sql += " AND lesson_id = ?"
            params.append(lesson_id)
        if case_id is not None:
            sql += " AND case_id = ?"
            params.append(case_id)
        if scope_key is not None:
            sql += " AND scope_key = ?"
            params.append(scope_key)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(max(1, min(100, int(limit))))
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [
            {
                "threadId": row["thread_id"],
                "learnerId": row["learner_id"],
                "mode": row["mode"],
                "lessonId": row["lesson_id"],
                "caseId": row["case_id"],
                "scopeKey": row["scope_key"],
                "title": row["title"],
                "createdAt": row["created_at"],
                "updatedAt": row["updated_at"],
            }
            for row in rows
        ]

    # --- server-owned Rapid rounds ---------------------------------------------

    @staticmethod
    def _rapid_round_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "roundId": row["round_id"],
            "learnerId": row["learner_id"],
            "pace": row["pace"],
            "length": int(row["length"]),
            "assessmentScope": row["assessment_scope"],
            "focusConcept": row["focus_concept"],
            "focusSubskill": row["focus_subskill"],
            "contextKey": row["context_key"],
            "exclusions": json.loads(row["exclusions_json"] or "[]"),
            "served": json.loads(row["served_json"] or "[]"),
            "pendingCaseId": row["pending_case_id"],
            "pendingTestedObjectiveManifest": json.loads(
                row["pending_manifest_json"] or "{}"
            ),
            "feedbackCaseId": row["feedback_case_id"],
            "pendingStartedAt": row["pending_started_at"],
            "pendingDeadlineAt": row["pending_deadline_at"],
            "deadlineSeconds": row["deadline_seconds"],
            "position": int(row["position"]),
            "status": row["status"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    @staticmethod
    def _rapid_answer_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "answerId": int(row["id"]),
            "roundId": row["round_id"],
            "caseId": row["case_id"],
            "response": json.loads(row["response_json"]),
            "grade": json.loads(row["grade_json"]),
            "tutor": json.loads(row["tutor_json"] or "null"),
            "result": json.loads(row["result_json"]),
            "traceGrade": json.loads(row["trace_grade_json"]) if row["trace_grade_json"] else None,
            "testedObjectiveManifest": json.loads(row["tested_manifest_json"] or "{}"),
            "receipts": json.loads(row["receipts_json"] or "[]"),
            "integrityStatus": row["integrity_status"],
            "attemptId": int(row["attempt_id"]),
            "createdAt": row["created_at"],
        }

    def create_rapid_round(
        self,
        learner_id: str,
        pace: str,
        length: int,
        assessment_scope: str,
        deadline_seconds: int | None,
        *,
        focus_concept: str | None = None,
        focus_subskill: str | None = None,
        context_key: str = "",
        exclusions: list[str] | None = None,
    ) -> dict[str, Any]:
        import uuid

        self.ensure_profile(learner_id)
        now = utc_now()
        round_id = f"rr_{uuid.uuid4().hex[:16]}"
        with self.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            # Starting a new round is an explicit replacement of any unfinished
            # round for the same learner; stale rounds cannot later win discovery.
            conn.execute(
                "UPDATE rapid_rounds SET status = 'abandoned', feedback_case_id = NULL, "
                "pending_manifest_json = '{}', updated_at = ? "
                "WHERE learner_id = ? AND (status = 'active' OR feedback_case_id IS NOT NULL)",
                (now, learner_id),
            )
            conn.execute(
                """
                INSERT INTO rapid_rounds (
                    round_id, learner_id, pace, length, assessment_scope, focus_concept,
                    focus_subskill, context_key, exclusions_json, served_json,
                    deadline_seconds, position, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '[]', ?, 0, 'active', ?, ?)
                """,
                (
                    round_id, learner_id, pace, length, assessment_scope, focus_concept,
                    focus_subskill, context_key, json.dumps(exclusions or []),
                    deadline_seconds, now, now,
                ),
            )
        return self.get_rapid_round(round_id)  # type: ignore[return-value]

    def get_rapid_round(self, round_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM rapid_rounds WHERE round_id = ?", (round_id,)).fetchone()
        return self._rapid_round_dict(row) if row else None

    def is_rapid_case_pending(self, case_id: str) -> bool:
        """Whether any active Rapid round has this ECG awaiting commitment."""

        with self.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM rapid_rounds WHERE pending_case_id = ? "
                "AND status = 'active' LIMIT 1",
                (case_id,),
            ).fetchone()
        return row is not None

    def is_rapid_case_pending_for_learner(self, case_id: str, learner_id: str) -> bool:
        """Whether this learner currently owns an uncommitted Rapid ECG."""

        with self.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM rapid_rounds WHERE learner_id = ? "
                "AND pending_case_id = ? AND status = 'active' LIMIT 1",
                (learner_id, case_id),
            ).fetchone()
        return row is not None

    def get_resumable_rapid_round(self, learner_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM rapid_rounds WHERE learner_id = ? "
                "AND (status = 'active' OR feedback_case_id IS NOT NULL) "
                "ORDER BY updated_at DESC LIMIT 1",
                (learner_id,),
            ).fetchone()
        return self._rapid_round_dict(row) if row else None

    def abandon_rapid_round(self, round_id: str) -> dict[str, Any] | None:
        """Atomically retire an unfinished Rapid round.

        The conditional update is intentionally idempotent: a retry after a
        successful transition does not rewrite ``updated_at``. Clearing the
        pending case and its timer in the same statement also closes the
        submit/activation boundary; either an in-flight submission commits
        first, or the abandon transition wins and that case can no longer be
        graded.
        """
        now = utc_now()
        with self.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "UPDATE rapid_rounds SET status = 'abandoned', pending_case_id = NULL, "
                "feedback_case_id = NULL, pending_started_at = NULL, "
                "pending_deadline_at = NULL, pending_manifest_json = '{}', updated_at = ? "
                "WHERE round_id = ? AND status = 'active'",
                (now, round_id),
            )
        return self.get_rapid_round(round_id)

    def get_rapid_answers(
        self, round_id: str, *, limit: int | None = None, offset: int = 0
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM rapid_round_answers WHERE round_id = ? ORDER BY id"
        params: list[Any] = [round_id]
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([int(limit), int(offset)])
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._rapid_answer_dict(row) for row in rows]

    def get_recent_rapid_answers(self, round_id: str, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM (SELECT * FROM rapid_round_answers WHERE round_id = ? "
                "ORDER BY id DESC LIMIT ?) ORDER BY id",
                (round_id, int(limit)),
            ).fetchall()
        return [self._rapid_answer_dict(row) for row in rows]

    def rapid_answer_count(self, round_id: str) -> int:
        with self.connect() as conn:
            return int(
                conn.execute(
                    "SELECT COUNT(*) FROM rapid_round_answers WHERE round_id = ?", (round_id,)
                ).fetchone()[0]
            )

    def get_rapid_answer(self, round_id: str, case_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM rapid_round_answers WHERE round_id = ? AND case_id = ?",
                (round_id, case_id),
            ).fetchone()
        return self._rapid_answer_dict(row) if row else None

    def acknowledge_rapid_feedback(self, round_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE rapid_rounds SET feedback_case_id = NULL, updated_at = ? WHERE round_id = ?",
                (utc_now(), round_id),
            )
        return self.get_rapid_round(round_id)

    def set_rapid_pending(
        self,
        round_id: str,
        case_id: str,
        tested_objective_manifest: dict[str, Any],
    ) -> dict[str, Any] | None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE rapid_rounds SET pending_case_id = ?, pending_started_at = NULL, "
                "pending_deadline_at = NULL, pending_manifest_json = ?, updated_at = ? "
                "WHERE round_id = ? "
                "AND status = 'active' AND pending_case_id IS NULL AND feedback_case_id IS NULL "
                "AND position < length",
                (case_id, json.dumps(tested_objective_manifest), utc_now(), round_id),
            )
        return self.get_rapid_round(round_id)

    def ensure_rapid_pending_manifest(
        self,
        round_id: str,
        case_id: str,
        tested_objective_manifest: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Backfill a pre-migration pending item without replacing a frozen manifest."""

        with self.connect() as conn:
            conn.execute(
                "UPDATE rapid_rounds SET pending_manifest_json = ?, updated_at = ? "
                "WHERE round_id = ? AND pending_case_id = ? AND status = 'active' "
                "AND (pending_manifest_json IS NULL OR pending_manifest_json = '' "
                "OR pending_manifest_json = '{}')",
                (
                    json.dumps(tested_objective_manifest),
                    utc_now(),
                    round_id,
                    case_id,
                ),
            )
        return self.get_rapid_round(round_id)

    def activate_rapid_pending(self, round_id: str) -> dict[str, Any] | None:
        session = self.get_rapid_round(round_id)
        if not session or not session.get("pendingCaseId"):
            return session
        if session.get("pendingStartedAt"):
            return session
        now_dt = datetime.now(UTC)
        now = now_dt.isoformat()
        duration = session.get("deadlineSeconds")
        deadline = (now_dt + timedelta(seconds=int(duration))).isoformat() if duration is not None else None
        with self.connect() as conn:
            conn.execute(
                "UPDATE rapid_rounds SET pending_started_at = ?, pending_deadline_at = ?, updated_at = ? "
                "WHERE round_id = ? AND pending_case_id IS NOT NULL AND pending_started_at IS NULL",
                (now, deadline, now, round_id),
            )
        return self.get_rapid_round(round_id)

    def _rapid_finalization_checkpoint(self, label: str) -> None:
        """Private failure-injection seam for transaction-boundary tests."""

        hook = getattr(self, "_rapid_finalization_failure_hook", None)
        if callable(hook):
            hook(label)

    def finalize_rapid_answer(
        self,
        *,
        round_id: str,
        case_id: str,
        response: dict[str, Any],
        grade: dict[str, Any],
        tutor: dict[str, Any] | None,
        trace_grade: dict[str, Any] | None,
        tested_objective_manifest: dict[str, Any],
        confidence: int,
        result: dict[str, Any],
        receipts: list[dict[str, Any]],
        receipt_events: dict[int, dict[str, Any]],
        submitted_at: datetime | str,
        planned_timed_out: bool,
    ) -> dict[str, Any]:
        """Commit every durable effect of one Rapid answer exactly once.

        The answer row is deliberately inserted as ``finalizing`` while this
        transaction is private, then promoted to ``atomic_v1`` only after every
        guided event and retention receipt has been written. Any exception at
        any boundary rolls back the generic attempt, answer, mastery changes,
        receipts, and round advance together.
        """

        submitted_dt = parse_instant(submitted_at)
        if submitted_dt is None:
            raise ValueError("Rapid submission time must be a server-owned instant")
        submitted_iso = submitted_dt.isoformat()
        with self.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT * FROM rapid_round_answers WHERE round_id = ? AND case_id = ?",
                (round_id, case_id),
            ).fetchone()
            if existing:
                answer = self._rapid_answer_dict(existing)
                if (
                    answer["integrityStatus"] in {"legacy_incomplete", "finalizing"}
                    or not answer["receipts"]
                ):
                    # Old two-phase submissions with an empty receipt ledger are
                    # ambiguous: repair could double-apply mastery. Keep the row
                    # auditable and fail closed instead of guessing.
                    return {"status": "legacy_incomplete", "answer": answer}
                return {"status": "replay", "answer": answer}
            session = conn.execute(
                "SELECT * FROM rapid_rounds WHERE round_id = ?", (round_id,)
            ).fetchone()
            if not session:
                return {"status": "missing"}
            if session["pending_case_id"] != case_id or session["status"] != "active":
                return {"status": "not_pending", "pendingCaseId": session["pending_case_id"]}

            frozen_manifest = json.loads(session["pending_manifest_json"] or "{}")
            frozen_keys = (
                "version",
                "caseId",
                "assessmentScope",
                "taskKind",
                "objectives",
                "allowSelectedExtras",
                "overcallPolicy",
            )
            if not frozen_manifest or any(
                frozen_manifest.get(key) != tested_objective_manifest.get(key)
                for key in frozen_keys
            ):
                return {"status": "manifest_mismatch"}

            started_at = session["pending_started_at"]
            deadline_at = session["pending_deadline_at"]
            if not started_at:
                started_at = submitted_iso
                duration = session["deadline_seconds"]
                deadline_at = (
                    (submitted_dt + timedelta(seconds=int(duration))).isoformat()
                    if duration is not None else None
                )
            started_dt = datetime.fromisoformat(str(started_at))
            try:
                deadline_dt = datetime.fromisoformat(str(deadline_at)) if deadline_at else None
            except ValueError:
                # A malformed server deadline is never allowed to open a
                # positive-evidence path.
                deadline_dt = submitted_dt
            response_ms = max(0, int((submitted_dt - started_dt).total_seconds() * 1000))
            timed_out = bool(deadline_dt and submitted_dt >= deadline_dt)
            if timed_out != bool(planned_timed_out):
                return {"status": "deadline_state_mismatch"}
            durable_result = {
                **result,
                "timedOut": timed_out,
                "responseMs": response_ms,
                "pace": session["pace"],
                "assessmentScope": session["assessment_scope"],
                "startedAt": started_at,
                "deadlineAt": deadline_at,
                "submittedAt": submitted_iso,
            }
            durable_response = {
                **response,
                "pace": session["pace"],
                "assessmentScope": session["assessment_scope"],
                "serverStartedAt": started_at,
                "serverDeadlineAt": deadline_at,
            }
            tested_manifest = tested_objective_manifest
            attempt_id = self._save_attempt_in_transaction(
                conn,
                learner_id=session["learner_id"],
                case_id=case_id,
                mode="rapid_practice",
                structured_answer=response.get("structuredAnswer") or {},
                confidence=confidence,
                grade=grade,
                now=submitted_iso,
            )
            self._rapid_finalization_checkpoint("after_attempt")
            cursor = conn.execute(
                """
                INSERT INTO rapid_round_answers (
                    round_id, case_id, response_json, grade_json, tutor_json,
                    result_json, trace_grade_json, tested_manifest_json,
                    receipts_json, integrity_status, attempt_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, '[]', 'finalizing', ?, ?)
                """,
                (
                    round_id, case_id, json.dumps(durable_response), json.dumps(grade),
                    json.dumps(tutor), json.dumps(durable_result),
                    json.dumps(trace_grade) if trace_grade is not None else None,
                    json.dumps(tested_manifest), attempt_id, submitted_iso,
                ),
            )
            answer_id = int(cursor.lastrowid)
            self._rapid_finalization_checkpoint("after_answer")

            if not receipts:
                raise ValueError("A verified Rapid answer requires an explicit receipt ledger")
            event_indexes = set(receipt_events)
            if any(not isinstance(index, int) or index < 0 or index >= len(receipts) for index in event_indexes):
                raise ValueError("Rapid receipt event index is outside the receipt ledger")
            durable_receipts: list[dict[str, Any]] = []
            for index, source_receipt in enumerate(receipts):
                receipt = dict(source_receipt)
                event = receipt_events.get(index)
                if event is not None:
                    event_result = self.save_guided_learning_event(
                        str(session["learner_id"]),
                        event,
                        occurred_at=submitted_dt,
                        _connection=conn,
                    )
                    if event_result.get("replay"):
                        raise RuntimeError(
                            "A Rapid receipt event already exists without a complete atomic answer"
                        )
                    receipt["evidenceLevel"] = event_result["effectiveEvidenceLevel"]
                durable_receipts.append(receipt)
                self._rapid_finalization_checkpoint(f"after_receipt:{index}")

            conn.execute(
                "UPDATE rapid_round_answers SET receipts_json = ?, integrity_status = 'atomic_v1' "
                "WHERE id = ? AND integrity_status = 'finalizing'",
                (json.dumps(durable_receipts), answer_id),
            )
            self._rapid_finalization_checkpoint("after_receipts_persisted")

            served = json.loads(session["served_json"] or "[]")
            if case_id not in served:
                served.append(case_id)
            position = int(
                conn.execute(
                    "SELECT COUNT(*) AS n FROM rapid_round_answers WHERE round_id = ?", (round_id,)
                ).fetchone()["n"]
            )
            status = "complete" if position >= int(session["length"]) else "active"
            advanced = conn.execute(
                "UPDATE rapid_rounds SET served_json = ?, pending_case_id = NULL, "
                "feedback_case_id = ?, pending_started_at = NULL, pending_deadline_at = NULL, "
                "pending_manifest_json = '{}', position = ?, status = ?, updated_at = ? "
                "WHERE round_id = ? AND pending_case_id = ? AND status = 'active'",
                (
                    json.dumps(served), case_id, position, status,
                    submitted_iso, round_id, case_id,
                ),
            )
            if advanced.rowcount != 1:
                raise RuntimeError("Rapid round advance lost its pending-item boundary")
            self._rapid_finalization_checkpoint("after_round_advance")
            answer_row = conn.execute(
                "SELECT * FROM rapid_round_answers WHERE id = ?", (answer_id,)
            ).fetchone()
        return {"status": "recorded", "answer": self._rapid_answer_dict(answer_row)}

    # --- adaptive rapid-review sessions ----------------------------------------

    def create_review_session(
        self,
        learner_id: str,
        objectives: list[str],
        label: str,
        target_mastery: float = 0.8,
        max_cases: int = 30,
    ) -> str:
        import uuid

        now = utc_now()
        session_id = f"rs_{uuid.uuid4().hex[:16]}"
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO review_sessions (session_id, learner_id, label, objectives_json, target_mastery, "
                "max_cases, served_json, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, '[]', 'active', ?, ?)",
                (session_id, learner_id, label, json.dumps(objectives), target_mastery, max_cases, now, now),
            )
        return session_id

    def get_review_session(self, session_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT session_id, learner_id, label, objectives_json, target_mastery, max_cases, served_json, "
                "status, created_at, updated_at FROM review_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "sessionId": row["session_id"],
            "learnerId": row["learner_id"],
            "label": row["label"],
            "objectives": json.loads(row["objectives_json"]),
            "targetMastery": row["target_mastery"],
            "maxCases": row["max_cases"],
            "served": json.loads(row["served_json"]),
            "status": row["status"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    def record_review_served(self, session_id: str, case_id: str, status: str | None = None) -> None:
        session = self.get_review_session(session_id)
        if not session:
            return
        served = session["served"]
        if case_id not in served:
            served.append(case_id)
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                "UPDATE review_sessions SET served_json = ?, status = COALESCE(?, status), updated_at = ? "
                "WHERE session_id = ?",
                (json.dumps(served), status, now, session_id),
            )

    def set_review_status(self, session_id: str, status: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE review_sessions SET status = ?, updated_at = ? WHERE session_id = ?",
                (status, utc_now(), session_id),
            )

    # --- clinical shift sessions (Clinical Decisions mode) ---------------------

    def create_shift_session(
        self,
        learner_id: str,
        lane: str,
        tier: str,
        length: int = 5,
        focus_objective: str | None = None,
        focus_subskill: str | None = None,
        requested_length: int | None = None,
        available_length: int | None = None,
        length_reason: str | None = None,
    ) -> str:
        import uuid

        self.ensure_profile(learner_id)
        now = utc_now()
        session_id = f"cs_{uuid.uuid4().hex[:16]}"
        requested = int(length if requested_length is None else requested_length)
        available = int(length if available_length is None else available_length)
        with self.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            # A deliberate new shift replaces any unfinished presentation for this
            # learner, making active-session discovery deterministic.
            conn.execute(
                "UPDATE clinical_shift_sessions SET status = 'abandoned', pending_item_id = NULL, "
                "feedback_item_id = NULL, pending_context_revealed = 0, "
                "pending_first_look_json = NULL, pending_step_answers_json = '[]', pending_orient_started_at = NULL, "
                "pending_orient_deadline_at = NULL, pending_decide_started_at = NULL, "
                "pending_decide_deadline_at = NULL, pending_decide_submitted_at = NULL, "
                "updated_at = ? WHERE learner_id = ? AND status = 'active'",
                (now, learner_id),
            )
            # A completed final answer remains completed evidence. Starting a new
            # shift merely dismisses its unacknowledged feedback presentation.
            conn.execute(
                "UPDATE clinical_shift_sessions SET feedback_item_id = NULL, updated_at = ? "
                "WHERE learner_id = ? AND status = 'complete' AND feedback_item_id IS NOT NULL",
                (now, learner_id),
            )
            conn.execute(
                "INSERT INTO clinical_shift_sessions (session_id, learner_id, lane, tier, focus_objective, focus_subskill, "
                "length, requested_length, available_length, length_reason, served_json, served_ecgs_json, "
                "calibration_json, pending_item_id, feedback_item_id, position, status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '[]', '[]', '[]', NULL, NULL, 0, ?, ?, ?)",
                (
                    session_id,
                    learner_id,
                    lane,
                    tier,
                    focus_objective,
                    focus_subskill,
                    int(length),
                    requested,
                    available,
                    length_reason,
                    "complete" if int(length) == 0 else "active",
                    now,
                    now,
                ),
            )
        return session_id

    def get_shift_session(self, session_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT session_id, learner_id, lane, tier, focus_objective, focus_subskill, length, requested_length, "
                "available_length, length_reason, served_json, served_ecgs_json, calibration_json, "
                "pending_item_id, feedback_item_id, pending_context_revealed, pending_first_look_json, "
                "pending_step_answers_json, "
                "pending_orient_started_at, pending_orient_deadline_at, pending_decide_started_at, "
                "pending_decide_deadline_at, pending_decide_submitted_at, position, status, "
                "created_at, updated_at "
                "FROM clinical_shift_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "sessionId": row["session_id"],
            "learnerId": row["learner_id"],
            "lane": row["lane"],
            "tier": row["tier"],
            "focusObjective": row["focus_objective"],
            "focusSubskill": row["focus_subskill"],
            "length": row["length"],
            "requestedLength": row["requested_length"],
            "availableDistinctEcgs": row["available_length"],
            "lengthReason": row["length_reason"],
            "served": json.loads(row["served_json"]),
            "servedEcgs": json.loads(row["served_ecgs_json"]),
            "calibration": json.loads(row["calibration_json"]),
            "pendingItemId": row["pending_item_id"],
            "feedbackItemId": row["feedback_item_id"],
            "contextRevealed": bool(row["pending_context_revealed"]),
            "firstLook": (
                json.loads(row["pending_first_look_json"])
                if row["pending_first_look_json"] is not None
                else None
            ),
            "stepAnswers": json.loads(row["pending_step_answers_json"] or "[]"),
            "orientStartedAt": row["pending_orient_started_at"],
            "orientDeadlineAt": row["pending_orient_deadline_at"],
            "decideStartedAt": row["pending_decide_started_at"],
            "decideDeadlineAt": row["pending_decide_deadline_at"],
            "decideSubmittedAt": row["pending_decide_submitted_at"],
            "position": row["position"],
            "status": row["status"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    def pending_clinical_item_ids(self, learner_id: str | None = None) -> list[str]:
        """Auth-agnostic pending item ids used by the global secrecy guard."""

        with self.connect() as conn:
            if learner_id is None:
                rows = conn.execute(
                    "SELECT DISTINCT pending_item_id FROM clinical_shift_sessions "
                    "WHERE status = 'active' AND pending_item_id IS NOT NULL"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT DISTINCT pending_item_id FROM clinical_shift_sessions "
                    "WHERE learner_id = ? AND status = 'active' AND pending_item_id IS NOT NULL",
                    (learner_id,),
                ).fetchall()
        return [str(row["pending_item_id"]) for row in rows]

    def set_shift_pending(self, session_id: str, item_id: str) -> dict[str, Any] | None:
        """Persist the current item once; concurrent/repeated `next` calls keep it stable."""
        with self.connect() as conn:
            conn.execute(
                "UPDATE clinical_shift_sessions SET pending_item_id = ?, pending_context_revealed = 0, "
                "pending_first_look_json = NULL, pending_step_answers_json = '[]', pending_orient_started_at = NULL, "
                "pending_orient_deadline_at = NULL, pending_decide_started_at = NULL, "
                "pending_decide_deadline_at = NULL, pending_decide_submitted_at = NULL, updated_at = ? "
                "WHERE session_id = ? AND pending_item_id IS NULL AND feedback_item_id IS NULL "
                "AND status = 'active'",
                (item_id, utc_now(), session_id),
            )
        return self.get_shift_session(session_id)

    def get_resumable_shift_session(self, learner_id: str) -> dict[str, Any] | None:
        """Return the learner's one durable Clinical presentation.

        Active work and unacknowledged feedback win.  If neither exists, the most
        recent completed report remains discoverable across refresh/devices.
        """
        with self.connect() as conn:
            row = conn.execute(
                "SELECT session_id FROM clinical_shift_sessions WHERE learner_id = ? "
                "AND (status = 'active' OR feedback_item_id IS NOT NULL) "
                "ORDER BY updated_at DESC LIMIT 1",
                (learner_id,),
            ).fetchone()
            if row:
                session_id = row["session_id"]
            else:
                # An explicit abandon is a durable dismissal boundary. Do not
                # unexpectedly resurrect an older completed report after the
                # learner chose to return to setup; a subsequently completed
                # shift naturally becomes the newest presentation again.
                latest = conn.execute(
                    "SELECT session_id, status FROM clinical_shift_sessions WHERE learner_id = ? "
                    "AND status IN ('complete', 'abandoned') "
                    "ORDER BY updated_at DESC, rowid DESC LIMIT 1",
                    (learner_id,),
                ).fetchone()
                session_id = (
                    latest["session_id"]
                    if latest and latest["status"] == "complete"
                    else None
                )
        return self.get_shift_session(session_id) if session_id else None

    def abandon_shift_session(self, session_id: str) -> dict[str, Any] | None:
        """Atomically retire an active Clinical shift and its pending presentation.

        Completed answer, attempt, calibration, and competency ledgers are append-only
        and intentionally untouched. The single conditional update closes the race
        with phase activation and answer recording: either that transaction commits
        first, or abandonment clears every unsubmitted item/context/clock field.
        Repeating this call after a successful transition is read-only/idempotent.
        """
        now = utc_now()
        with self.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "UPDATE clinical_shift_sessions SET status = 'abandoned', "
                "pending_item_id = NULL, feedback_item_id = NULL, "
                "pending_context_revealed = 0, pending_first_look_json = NULL, pending_step_answers_json = '[]', "
                "pending_orient_started_at = NULL, pending_orient_deadline_at = NULL, "
                "pending_decide_started_at = NULL, pending_decide_deadline_at = NULL, "
                "pending_decide_submitted_at = NULL, updated_at = ? "
                "WHERE session_id = ? AND status = 'active'",
                (now, session_id),
            )
        return self.get_shift_session(session_id)

    def acknowledge_shift_feedback(self, session_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE clinical_shift_sessions SET feedback_item_id = NULL, updated_at = ? "
                "WHERE session_id = ?",
                (utc_now(), session_id),
            )
        return self.get_shift_session(session_id)

    def activate_shift_phase(
        self,
        session_id: str,
        item_id: str,
        phase: str,
        duration_seconds: int | None,
    ) -> dict[str, Any]:
        """Activate one server-owned phase clock exactly once.

        The route derives ``duration_seconds`` from the persisted item/tier; no
        client duration participates in this write boundary.
        """
        if phase not in {"orient", "decide"}:
            return {"status": "invalid_phase"}
        now_dt = datetime.now(UTC)
        now = now_dt.isoformat()
        deadline = (
            (now_dt + timedelta(seconds=int(duration_seconds))).isoformat()
            if duration_seconds is not None
            else None
        )
        started_column = f"pending_{phase}_started_at"
        deadline_column = f"pending_{phase}_deadline_at"
        with self.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT pending_item_id, pending_context_revealed, status, "
                f"{started_column} AS started_at FROM clinical_shift_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if not row:
                return {"status": "missing"}
            if row["pending_item_id"] != item_id or row["status"] != "active":
                return {"status": "not_pending", "pendingItemId": row["pending_item_id"]}
            phase_ready = (phase == "orient" and not row["pending_context_revealed"]) or (
                phase == "decide" and bool(row["pending_context_revealed"])
            )
            if not phase_ready:
                return {"status": "phase_not_ready"}
            if row["started_at"]:
                return {"status": "replay"}
            conn.execute(
                f"UPDATE clinical_shift_sessions SET {started_column} = ?, {deadline_column} = ?, "
                "updated_at = ? WHERE session_id = ? AND pending_item_id = ? "
                f"AND {started_column} IS NULL",
                (now, deadline, now, session_id, item_id),
            )
        return {"status": "activated"}

    def reveal_shift_context(
        self,
        session_id: str,
        item_id: str,
        first_look: dict[str, Any],
        decide_duration_seconds: int | None = None,
    ) -> dict[str, Any]:
        """Persist the ECG-only commitment before authored context is served.

        The first commitment wins. A repeated reveal request replays that value,
        which makes refresh/resume safe without letting the pre-context answer be
        silently revised.
        """
        now_dt = datetime.now(UTC)
        now = now_dt.isoformat()
        decide_deadline = (
            (now_dt + timedelta(seconds=int(decide_duration_seconds))).isoformat()
            if decide_duration_seconds is not None
            else None
        )
        with self.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT pending_item_id, pending_context_revealed, pending_first_look_json, tier, "
                "pending_orient_started_at, pending_orient_deadline_at, pending_decide_started_at "
                "FROM clinical_shift_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if not row:
                return {"status": "missing"}
            if row["pending_item_id"] != item_id:
                return {"status": "not_pending", "pendingItemId": row["pending_item_id"]}
            if row["pending_context_revealed"]:
                return {
                    "status": "replay",
                    "firstLook": json.loads(row["pending_first_look_json"] or "{}"),
                }
            if row["tier"] == "shift" and not row["pending_orient_started_at"]:
                # A timed first look cannot begin at page/request time. The viewer
                # readiness activation endpoint is the only clock start boundary.
                return {"status": "phase_not_activated"}
            orient_started = (
                datetime.fromisoformat(str(row["pending_orient_started_at"]))
                if row["pending_orient_started_at"]
                else now_dt
            )
            orient_deadline = (
                datetime.fromisoformat(str(row["pending_orient_deadline_at"]))
                if row["pending_orient_deadline_at"]
                else None
            )
            durable_first_look = {
                **first_look,
                "orientAnswerTimeMs": max(0, int((now_dt - orient_started).total_seconds() * 1000)),
                "orientTimedOut": bool(orient_deadline and now_dt >= orient_deadline),
                "orientStartedAt": row["pending_orient_started_at"] or now,
                "orientDeadlineAt": row["pending_orient_deadline_at"],
            }
            conn.execute(
                "UPDATE clinical_shift_sessions SET pending_context_revealed = 1, "
                "pending_first_look_json = ?, pending_decide_started_at = ?, "
                "pending_decide_deadline_at = ?, updated_at = ? WHERE session_id = ? "
                "AND pending_context_revealed = 0",
                (json.dumps(durable_first_look), now, decide_deadline, now, session_id),
            )
            return {"status": "recorded", "firstLook": durable_first_look}

    def commit_shift_step(
        self,
        session_id: str,
        item_id: str,
        step_index: int,
        answer_index: int,
        *,
        step_count: int,
        option_count: int,
    ) -> dict[str, Any]:
        """Commit one Clinical step in order; prior commitments are immutable."""

        if step_index < 0 or step_index >= step_count or answer_index < 0 or answer_index >= option_count:
            return {"status": "invalid_step"}
        now = utc_now()
        with self.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT pending_item_id, pending_context_revealed, pending_step_answers_json, status "
                "FROM clinical_shift_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if not row:
                return {"status": "missing"}
            if row["pending_item_id"] != item_id or row["status"] != "active":
                return {"status": "not_pending", "pendingItemId": row["pending_item_id"]}
            if not row["pending_context_revealed"]:
                return {"status": "context_not_revealed"}
            committed = json.loads(row["pending_step_answers_json"] or "[]")
            if step_index < len(committed):
                return {
                    "status": "replay" if int(committed[step_index]) == answer_index else "step_locked",
                    "stepAnswers": committed,
                }
            if step_index != len(committed):
                return {"status": "step_out_of_order", "nextStepIndex": len(committed)}
            committed.append(answer_index)
            conn.execute(
                "UPDATE clinical_shift_sessions SET pending_step_answers_json = ?, updated_at = ? "
                "WHERE session_id = ? AND pending_item_id = ?",
                (json.dumps(committed), now, session_id, item_id),
            )
            return {"status": "recorded", "stepAnswers": committed}

    def claim_shift_submission_timing(self, session_id: str, item_id: str) -> dict[str, Any]:
        """Freeze one authoritative decision submission timestamp.

        Freezing before grading keeps the timeout decision and response time stable
        across retries and concurrent submissions. Client timing fields are never
        read at this boundary.
        """
        now_dt = datetime.now(UTC)
        now = now_dt.isoformat()
        with self.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT pending_item_id, pending_context_revealed, pending_decide_started_at, "
                "pending_decide_deadline_at, pending_decide_submitted_at, status "
                "FROM clinical_shift_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if not row:
                return {"status": "missing"}
            if row["pending_item_id"] != item_id or row["status"] != "active":
                return {"status": "not_pending", "pendingItemId": row["pending_item_id"]}
            if not row["pending_context_revealed"]:
                return {"status": "context_not_revealed", "pendingItemId": item_id}
            started_at = row["pending_decide_started_at"] or now
            submitted_at = row["pending_decide_submitted_at"] or now
            if not row["pending_decide_started_at"] or not row["pending_decide_submitted_at"]:
                conn.execute(
                    "UPDATE clinical_shift_sessions SET pending_decide_started_at = COALESCE(pending_decide_started_at, ?), "
                    "pending_decide_submitted_at = COALESCE(pending_decide_submitted_at, ?), updated_at = ? "
                    "WHERE session_id = ? AND pending_item_id = ?",
                    (started_at, submitted_at, now, session_id, item_id),
                )
            started_dt = datetime.fromisoformat(str(started_at))
            submitted_dt = datetime.fromisoformat(str(submitted_at))
            deadline_at = row["pending_decide_deadline_at"]
            deadline_dt = datetime.fromisoformat(str(deadline_at)) if deadline_at else None
            return {
                "status": "claimed" if not row["pending_decide_submitted_at"] else "replay",
                "startedAt": started_at,
                "deadlineAt": deadline_at,
                "submittedAt": submitted_at,
                "answerTimeMs": max(0, int((submitted_dt - started_dt).total_seconds() * 1000)),
                "timedOut": bool(deadline_dt and submitted_dt >= deadline_dt),
            }

    def _record_formative_subskill_receipts_in_transaction(
        self,
        conn: sqlite3.Connection,
        *,
        learner_id: str,
        events: list[dict[str, Any]],
        now: str,
    ) -> list[dict[str, Any]]:
        """Apply server-authored Clinical evidence on the answer transaction.

        Clinical content is automated-screened and pending named clinician
        sign-off, so this path can update formative evidence only.  It never
        increments independent attempts, creates retention events, or schedules
        a due date.  The enclosing unique Clinical answer row is the exactly-once
        idempotency boundary.
        """

        receipts: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for event in events:
            concept = str(event.get("concept") or "").strip()
            subskill = str(event.get("subskill") or "").strip()
            key = (concept, subskill)
            if not concept or not subskill or key in seen:
                continue
            seen.add(key)
            definition = objective_definition(concept)
            if definition is None or subskill not in definition.allowed_subskills:
                raise ValueError(
                    f"Clinical competency event targets unavailable cell {concept} x {subskill}."
                )
            score = max(0.0, min(1.0, float(event.get("score", 0.0))))
            correct = bool(event.get("correct"))
            confidence = event.get("confidence")
            high_conf_wrong = 1 if confidence is not None and int(confidence) >= 4 and not correct else 0
            current = conn.execute(
                """
                SELECT formative_score, independent_mastery, attempts,
                       independent_attempts, correct, high_confidence_wrong,
                       next_due_at, stability_days, lapses, spaced_retrievals,
                       distinct_eligible_ecgs, distinct_successful_ecgs,
                       distinct_modes, distinct_morphologies,
                       last_independent_at, last_independent_correct
                FROM subskill_mastery
                WHERE learner_id = ? AND concept = ? AND subskill = ?
                """,
                (learner_id, concept, subskill),
            ).fetchone()
            formative = float(current["formative_score"]) if current else 0.0
            formative_delta = (0.04 + 0.04 * score) if correct else -0.04
            next_formative = min(1.0, max(0.0, formative + formative_delta))
            if current:
                conn.execute(
                    """
                    UPDATE subskill_mastery
                    SET formative_score = ?, attempts = attempts + 1,
                        correct = correct + ?,
                        high_confidence_wrong = high_confidence_wrong + ?,
                        last_practiced_at = ?
                    WHERE learner_id = ? AND concept = ? AND subskill = ?
                    """,
                    (
                        next_formative,
                        1 if correct else 0,
                        high_conf_wrong,
                        now,
                        learner_id,
                        concept,
                        subskill,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO subskill_mastery (
                        learner_id, concept, subskill, formative_score,
                        independent_mastery, attempts, independent_attempts,
                        correct, high_confidence_wrong, last_practiced_at
                    ) VALUES (?, ?, ?, ?, 0.15, 1, 0, ?, ?, ?)
                    """,
                    (
                        learner_id,
                        concept,
                        subskill,
                        next_formative,
                        1 if correct else 0,
                        high_conf_wrong,
                        now,
                    ),
                )
            retention_values = {
                "nextDueAt": current["next_due_at"] if current else None,
                "stabilityDays": float(current["stability_days"]) if current else 0.0,
                "lapses": int(current["lapses"]) if current else 0,
                "spacedRetrievals": int(current["spaced_retrievals"]) if current else 0,
                "distinctEligibleEcgs": int(current["distinct_eligible_ecgs"]) if current else 0,
                "distinctSuccessfulEcgs": int(current["distinct_successful_ecgs"]) if current else 0,
                "distinctModes": int(current["distinct_modes"]) if current else 0,
                "distinctMorphologies": int(current["distinct_morphologies"]) if current else 0,
                "lastIndependentAt": current["last_independent_at"] if current else None,
                "lastIndependentCorrect": (
                    bool(current["last_independent_correct"])
                    if current and current["last_independent_correct"] is not None
                    else None
                ),
            }
            due = due_snapshot(retention_values, as_of=datetime.fromisoformat(now))
            receipts.append({
                "registryVersion": REGISTRY_VERSION,
                "concept": concept,
                "subskill": subskill,
                "score": round(score, 3),
                "correct": correct,
                "formativeScore": round(next_formative, 3),
                "independentMastery": round(
                    float(current["independent_mastery"]) if current else 0.15,
                    3,
                ),
                "evidenceLevel": "guided",
                "formativeOnly": True,
                "retentionEligible": False,
                "nextDueAt": retention_values["nextDueAt"],
                "stabilityDays": retention_values["stabilityDays"],
                "lapses": retention_values["lapses"],
                "spacedRetrievals": retention_values["spacedRetrievals"],
                "distinctEligibleEcgs": retention_values["distinctEligibleEcgs"],
                "distinctSuccessfulEcgs": retention_values["distinctSuccessfulEcgs"],
                "distinctModes": retention_values["distinctModes"],
                "distinctMorphologies": retention_values["distinctMorphologies"],
                "dueState": due["dueState"],
                "intervalExpanded": False,
                "evidenceSource": str(event.get("evidenceSource") or "clinical_server_grade"),
                "mode": "clinical",
                "caseId": str(event.get("caseId") or ""),
                "itemId": str(event.get("itemId") or ""),
            })
        return receipts

    @staticmethod
    def _shift_answer_dict(row: sqlite3.Row) -> dict[str, Any]:
        receipts = json.loads(row["receipts_json"] or "[]") if "receipts_json" in row.keys() else []
        return {
            "answerId": int(row["id"]),
            "sessionId": row["session_id"],
            "itemId": row["item_id"],
            "ecgId": row["ecg_id"],
            "response": json.loads(row["response_json"]),
            "grade": json.loads(row["grade_json"]),
            "receipts": receipts,
            "score": float(row["score"]),
            "correct": bool(row["correct"]),
            "answerTimeMs": row["answer_time_ms"],
            "calibrationEvent": (
                json.loads(row["calibration_event_json"])
                if row["calibration_event_json"] is not None
                else None
            ),
            "attemptId": int(row["attempt_id"]),
            "createdAt": row["created_at"],
        }

    def get_shift_answer(self, session_id: str, item_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM clinical_shift_answers WHERE session_id = ? AND item_id = ?",
                (session_id, item_id),
            ).fetchone()
        return self._shift_answer_dict(row) if row else None

    def get_shift_answers(self, session_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM clinical_shift_answers WHERE session_id = ? ORDER BY id",
                (session_id,),
            ).fetchall()
        return [self._shift_answer_dict(row) for row in rows]

    def record_shift_answer(
        self,
        *,
        session_id: str,
        item_id: str,
        ecg_id: str,
        response: dict[str, Any],
        grade: dict[str, Any],
        correct: bool,
        confidence: int,
        calibration_event: dict[str, Any] | None,
        competency_events: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Exactly-once Clinical write boundary.

        A replay returns the first stored grade. A first submission is accepted only
        for the persisted pending item, and advances attempts/mastery/position once.
        """
        now = utc_now()
        with self.connect() as conn:
            # Serialize file-backed writers before checking the uniqueness/pending gates.
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT * FROM clinical_shift_answers WHERE session_id = ? AND item_id = ?",
                (session_id, item_id),
            ).fetchone()
            if existing:
                return {"status": "replay", "answer": self._shift_answer_dict(existing)}

            session = conn.execute(
                "SELECT learner_id, tier, length, served_json, served_ecgs_json, calibration_json, "
                "pending_item_id, pending_context_revealed, pending_first_look_json, "
                "pending_decide_submitted_at "
                "FROM clinical_shift_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if not session:
                return {"status": "missing"}
            if session["pending_item_id"] != item_id:
                return {"status": "not_pending", "pendingItemId": session["pending_item_id"]}
            if not session["pending_context_revealed"]:
                return {"status": "context_not_revealed", "pendingItemId": session["pending_item_id"]}
            if not session["pending_decide_submitted_at"]:
                return {"status": "timing_not_claimed", "pendingItemId": session["pending_item_id"]}

            receipts = self._record_formative_subskill_receipts_in_transaction(
                conn,
                learner_id=session["learner_id"],
                events=competency_events or [],
                now=now,
            )
            stored_grade = {**grade, "competencyReceipts": receipts}
            attempt_id = self._save_attempt_in_transaction(
                conn,
                learner_id=session["learner_id"],
                case_id=ecg_id,
                mode="clinical_decision",
                structured_answer=response,
                confidence=confidence,
                grade=stored_grade,
                now=now,
            )
            cursor = conn.execute(
                """
                INSERT INTO clinical_shift_answers (
                    session_id, item_id, ecg_id, response_json, grade_json,
                    receipts_json, score, correct, answer_time_ms,
                    calibration_event_json, attempt_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    item_id,
                    ecg_id,
                    json.dumps(response),
                    json.dumps(stored_grade),
                    json.dumps(receipts),
                    float(stored_grade["score"]),
                    1 if correct else 0,
                    response.get("answer_time_ms", response.get("answerTimeMs")),
                    json.dumps(calibration_event) if calibration_event is not None else None,
                    attempt_id,
                    now,
                ),
            )
            served = json.loads(session["served_json"])
            if item_id not in served:
                served.append(item_id)
            served_ecgs = json.loads(session["served_ecgs_json"])
            if ecg_id not in served_ecgs:
                served_ecgs.append(ecg_id)
            calibration = json.loads(session["calibration_json"])
            if calibration_event is not None:
                calibration.append(calibration_event)
            position = int(
                conn.execute(
                    "SELECT COUNT(*) AS n FROM clinical_shift_answers WHERE session_id = ?",
                    (session_id,),
                ).fetchone()["n"]
            )
            status = "complete" if position >= int(session["length"]) else "active"
            conn.execute(
                "UPDATE clinical_shift_sessions SET served_json = ?, served_ecgs_json = ?, "
                "calibration_json = ?, pending_item_id = NULL, pending_context_revealed = 0, "
                "pending_first_look_json = NULL, pending_step_answers_json = '[]', pending_orient_started_at = NULL, "
                "pending_orient_deadline_at = NULL, pending_decide_started_at = NULL, "
                "pending_decide_deadline_at = NULL, pending_decide_submitted_at = NULL, "
                "feedback_item_id = ?, position = ?, status = ?, updated_at = ? "
                "WHERE session_id = ?",
                (
                    json.dumps(served),
                    json.dumps(served_ecgs),
                    json.dumps(calibration),
                    item_id,
                    position,
                    status,
                    now,
                    session_id,
                ),
            )
            answer_row = conn.execute(
                "SELECT * FROM clinical_shift_answers WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
            return {"status": "created", "answer": self._shift_answer_dict(answer_row)}

    def record_shift_served(
        self, session_id: str, item_id: str, calibration_event: dict[str, Any] | None = None
    ) -> None:
        session = self.get_shift_session(session_id)
        if not session:
            return
        served = session["served"]
        if item_id not in served:
            served.append(item_id)
        calibration = session["calibration"]
        if calibration_event is not None:
            calibration.append(calibration_event)
        position = session["position"] + 1
        status = "complete" if position >= session["length"] else "active"
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                "UPDATE clinical_shift_sessions SET served_json = ?, calibration_json = ?, position = ?, "
                "status = ?, updated_at = ? WHERE session_id = ?",
                (json.dumps(served), json.dumps(calibration), position, status, now, session_id),
            )

    def set_shift_status(self, session_id: str, status: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE clinical_shift_sessions SET status = ?, updated_at = ? WHERE session_id = ?",
                (status, utc_now(), session_id),
            )

    def _misconception_counts(self, conn: sqlite3.Connection, learner_id: str) -> list[dict[str, Any]]:
        rows = conn.execute(
            "SELECT misconception_tags_json FROM attempts WHERE learner_id = ? ORDER BY id DESC LIMIT 50",
            (learner_id,),
        ).fetchall()
        counts: dict[str, int] = {}
        for row in rows:
            for tag in json.loads(row["misconception_tags_json"]):
                counts[tag] = counts.get(tag, 0) + 1
        return [
            {"tag": tag, "count": count}
            for tag, count in sorted(counts.items(), key=lambda item: item[1], reverse=True)
        ]
