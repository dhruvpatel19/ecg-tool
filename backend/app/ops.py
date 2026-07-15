"""Operational liveness and readiness probes."""

from __future__ import annotations

from datetime import UTC, datetime
import logging
import os
from pathlib import Path
import secrets
import shutil
import tempfile
import threading
import time
from typing import Any, Callable

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from .auth_mailer import build_auth_mailer


logger = logging.getLogger(__name__)
_RETENTION_JOB_NAME = "privacy-retention-v1"
_RETENTION_BACKLOG_INTERVAL_SECONDS = 60
_READINESS_CACHE_TTL_SECONDS = 15.0


def _corpus_check(settings: Any, repo: Any) -> tuple[bool, str]:
    if not getattr(settings, "require_real_data", True):
        return True, "fixture_mode_explicitly_allowed"
    status = getattr(repo, "status", {}) or {}
    if status.get("active_source") != "corpus" or status.get("fixture_fallback"):
        return False, "real_corpus_not_active"
    manifest = status.get("manifest") or {}
    if manifest.get("complete") is not True:
        return False, "corpus_manifest_incomplete"
    try:
        case_count = int(repo.store.count())
        student_count = int(repo.store.student_facing_count())
    except Exception:
        return False, "corpus_query_failed"
    if case_count <= 0 or student_count <= 0:
        return False, "corpus_empty"
    root = Path(getattr(repo, "root", ""))
    if not (root / "corpus.db").is_file() or not (root / "waveforms").is_dir():
        return False, "corpus_mount_missing"
    deployment_readiness = getattr(repo, "deployment_readiness", None)
    if not callable(deployment_readiness):
        return False, "corpus_capability_audit_missing"
    try:
        capability_ok, capability_state = deployment_readiness()
    except Exception:
        return False, "corpus_capability_audit_failed"
    if not capability_ok:
        return False, str(capability_state or "corpus_capability_audit_failed")
    return True, "ready"


def _database_check(settings: Any, store: Any) -> tuple[bool, str]:
    probe_fd: int | None = None
    probe_path: str | None = None
    try:
        db_path = Path(settings.sqlite_path)
        parent = db_path.parent
        if not parent.is_dir() or not os.access(parent, os.W_OK):
            return False, "state_mount_not_writable"
        if db_path.exists() and not os.access(db_path, os.W_OK):
            return False, "learner_database_not_writable"
        minimum_free = int(getattr(settings, "min_state_free_bytes", 268435456))
        if shutil.disk_usage(parent).free < minimum_free:
            return False, "state_mount_low_space"
        probe_fd, probe_path = tempfile.mkstemp(prefix=".readiness-", dir=parent)
        os.write(probe_fd, b"ok")
        os.fsync(probe_fd)
        os.close(probe_fd)
        probe_fd = None
        os.unlink(probe_path)
        probe_path = None
        with store.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("SELECT 1").fetchone()
            conn.rollback()
    except Exception:
        return False, "learner_database_query_failed"
    finally:
        if probe_fd is not None:
            try:
                os.close(probe_fd)
            except OSError:
                pass
        if probe_path is not None:
            try:
                os.unlink(probe_path)
            except OSError:
                pass
    return True, "ready"


def _learning_record_check(store: Any) -> tuple[bool, str]:
    check = getattr(store, "learning_record_integrity", None)
    if not callable(check):
        return False, "learning_record_integrity_check_missing"
    try:
        return check()
    except Exception:
        return False, "learning_record_integrity_check_failed"


def _password_hash_check(
    store: Any,
) -> tuple[bool, str, dict[str, int]]:
    """Audit only aggregate credential work factors for operator readiness."""

    audit = getattr(store, "password_hash_iteration_audit", None)
    if not callable(audit):
        return False, "password_hash_audit_missing", {}
    try:
        counts = {
            str(key): int(value)
            for key, value in dict(audit()).items()
            if key in {"total", "current", "legacy", "future", "invalid"}
        }
    except Exception:
        return False, "password_hash_audit_failed", {}
    if counts.get("invalid", 0) > 0:
        return False, "invalid_password_hashes_present", counts
    if counts.get("legacy", 0) > 0:
        return True, "legacy_password_hash_migration_pending", counts
    return True, "ready", counts


def _backup_check(settings: Any, *, now: float | None = None) -> tuple[bool, str]:
    if not getattr(settings, "require_recent_backup", False):
        return True, "not_required"
    current = time.time() if now is None else now
    max_age = int(getattr(settings, "backup_max_age_seconds", 50400))
    marker = Path(
        getattr(settings, "learner_backup_marker_path", None)
        or f"{settings.sqlite_path}.last-backup-success"
    )
    if marker.is_file():
        try:
            age = current - marker.stat().st_mtime
        except OSError:
            return False, "backup_marker_unreadable"
        return (True, "ready") if age <= max_age else (False, "backup_stale")
    return False, "backup_never_succeeded"


def _ai_tutor_check(settings: Any) -> tuple[bool, str]:
    provider = str(getattr(settings, "llm_provider", "mock") or "mock").lower()
    if provider == "openai-compatible":
        return (True, "ready") if getattr(settings, "llm_api_key", None) else (False, "api_key_missing")
    if provider in {"", "mock"}:
        return False, "mock_provider"
    return False, "unsupported_provider"


def _clinical_check(settings: Any, clinical_store: Any) -> tuple[bool, str]:
    readiness = getattr(clinical_store, "release_readiness", None)
    if not callable(readiness):
        return False, "clinical_capability_audit_missing"
    try:
        return readiness(int(getattr(settings, "min_clinical_cases", 1)))
    except Exception:
        return False, "clinical_capability_audit_failed"


def _retention_automation_check(settings: Any) -> tuple[bool, str]:
    enabled = bool(getattr(settings, "retention_cleanup_enabled", True))
    production = str(getattr(settings, "app_env", "development")).lower() in {
        "production",
        "prod",
    }
    if enabled:
        return True, "ready"
    if production:
        return False, "automatic_retention_cleanup_disabled"
    return True, "disabled_outside_production"


def _authenticated_retention_policy_check(settings: Any) -> tuple[bool, str]:
    """Require an external account-retention decision before production readiness.

    This is deliberately only an acknowledgement contract. The application does
    not infer a legal/product duration and never auto-deletes an account.
    """

    production = str(getattr(settings, "app_env", "development")).lower() in {
        "production",
        "prod",
    }
    if not production:
        return True, "not_required_outside_production"
    if not bool(
        getattr(settings, "authenticated_retention_policy_acknowledged", False)
    ):
        return False, "authenticated_retention_policy_unacknowledged"
    reference = str(
        getattr(settings, "authenticated_retention_policy_reference", "") or ""
    ).strip()
    if not reference:
        return False, "authenticated_retention_policy_reference_missing"
    return True, "ready"


def _auth_email_delivery_check(settings: Any) -> tuple[bool, str]:
    """Fail production readiness when verified-account mail cannot be sent."""

    production = str(getattr(settings, "app_env", "development")).lower() in {
        "production",
        "prod",
    }
    if not production:
        return True, "not_required_outside_production"
    mailer = build_auth_mailer(
        app_env=str(getattr(settings, "app_env", "production")),
        mode=str(getattr(settings, "auth_email_delivery_mode", "disabled")),
        smtp_host=getattr(settings, "auth_smtp_host", None),
        smtp_port=int(getattr(settings, "auth_smtp_port", 587)),
        smtp_username=getattr(settings, "auth_smtp_username", None),
        smtp_password=getattr(settings, "auth_smtp_password", None),
        from_address=getattr(settings, "auth_email_from_address", None),
        reply_to=getattr(settings, "auth_email_reply_to", None),
        public_app_url=getattr(settings, "auth_public_app_url", None),
        smtp_starttls=bool(getattr(settings, "auth_smtp_starttls", True)),
        smtp_timeout_seconds=int(
            getattr(settings, "auth_smtp_timeout_seconds", 10)
        ),
    )
    if mailer.ready:
        return True, "ready"
    # The public probe serializes only {"ok": false}. This internal report is
    # used by tests and operator-side diagnostics, so environment variable names
    # are useful while credential values and provider responses remain absent.
    errors = tuple(getattr(mailer, "readiness_errors", ()))
    suffix = ",".join(errors) if errors else "transport_disabled"
    return False, f"authentication_email_configuration_invalid:{suffix}"


class RetentionCleanupCoordinator:
    """Run bounded retention cleanup once on startup and then when due.

    ``/readyz`` is the periodic scheduler trigger used by production health
    probes. A durable database schedule plus an opaque expiring lease prevents
    duplicate app workers from running the same pass concurrently. Only
    aggregate counts are logged.
    """

    def __init__(self, settings: Any, store: Any):
        self.settings = settings
        self.store = store
        self._lock = threading.Lock()
        self._last_run_ok: bool | None = None
        self._last_counts: dict[str, int] | None = None

    @property
    def healthy(self) -> bool:
        return self._last_run_ok is not False

    @property
    def last_counts(self) -> dict[str, int] | None:
        return dict(self._last_counts) if self._last_counts is not None else None

    def maybe_run(self, *, now: datetime | None = None) -> dict[str, int] | None:
        if not bool(getattr(self.settings, "retention_cleanup_enabled", True)):
            return None
        if not self._lock.acquire(blocking=False):
            return None
        current = (now or datetime.now(UTC)).astimezone(UTC)
        token = secrets.token_urlsafe(24)
        try:
            claimed = self.store.claim_maintenance_lease(
                job_name=_RETENTION_JOB_NAME,
                token=token,
                now=current,
                lease_seconds=int(
                    getattr(self.settings, "retention_cleanup_lease_seconds", 300)
                ),
            )
            if not claimed:
                return None
            try:
                counts = self.store.cleanup_retention(
                    now=current,
                    guest_inactivity_days=int(
                        getattr(self.settings, "guest_inactivity_days", 30)
                    ),
                    unverified_account_expiry_days=int(
                        getattr(
                            self.settings,
                            "unverified_account_expiry_days",
                            7,
                        )
                    ),
                    batch_size=int(
                        getattr(self.settings, "retention_cleanup_batch_size", 100)
                    ),
                )
                batch_size = int(
                    getattr(self.settings, "retention_cleanup_batch_size", 100)
                )
                normal_interval = int(
                    getattr(
                        self.settings,
                        "retention_cleanup_interval_seconds",
                        21600,
                    )
                )
                # A count equal to the query limit means more expired rows may
                # remain. Keep each transaction bounded but drain that backlog
                # on the next minute-level probe instead of waiting six hours.
                saturated = any(
                    int(counts.get(key, 0)) >= batch_size
                    for key in (
                        "expiredSessions",
                        "expiredExportAuthorizations",
                        "expiredMaintenanceLeases",
                        "inactiveGuestOwners",
                    )
                )
                completed = self.store.complete_maintenance_lease(
                    job_name=_RETENTION_JOB_NAME,
                    token=token,
                    completed_at=current,
                    interval_seconds=(
                        min(normal_interval, _RETENTION_BACKLOG_INTERVAL_SECONDS)
                        if saturated
                        else normal_interval
                    ),
                )
                self._last_counts = {key: int(value) for key, value in counts.items()}
                self._last_run_ok = True
                if completed:
                    logger.info("retention_cleanup_complete counts=%s", self._last_counts)
                else:
                    logger.warning(
                        "retention_cleanup_complete_schedule_lease_changed counts=%s",
                        self._last_counts,
                    )
                return dict(self._last_counts)
            except Exception:
                self.store.release_maintenance_lease(
                    job_name=_RETENTION_JOB_NAME, token=token
                )
                self._last_run_ok = False
                logger.exception("retention_cleanup_failed")
                return None
        except Exception:
            self._last_run_ok = False
            logger.exception("retention_cleanup_coordination_failed")
            return None
        finally:
            self._lock.release()


def readiness_report(settings: Any, repo: Any, store: Any, clinical_store: Any) -> dict[str, Any]:
    corpus_ok, corpus_state = _corpus_check(settings, repo)
    database_ok, database_state = _database_check(settings, store)
    record_ok, record_state = _learning_record_check(store)
    password_hash_ok, password_hash_state, password_hash_counts = (
        _password_hash_check(store)
    )
    backup_ok, backup_state = _backup_check(settings)
    ai_ok, ai_state = _ai_tutor_check(settings)
    clinical_ok, clinical_state = _clinical_check(settings, clinical_store)
    retention_ok, retention_state = _retention_automation_check(settings)
    account_policy_ok, account_policy_state = _authenticated_retention_policy_check(
        settings
    )
    auth_email_ok, auth_email_state = _auth_email_delivery_check(settings)
    ai_required = bool(getattr(settings, "llm_required", False))
    return {
        "ok": (
            corpus_ok
            and database_ok
            and record_ok
            and password_hash_ok
            and backup_ok
            and clinical_ok
            and retention_ok
            and account_policy_ok
            and auth_email_ok
            and (ai_ok or not ai_required)
        ),
        "checks": {
            "corpus": {"ok": corpus_ok, "state": corpus_state},
            "learnerDatabase": {"ok": database_ok, "state": database_state},
            "learningRecord": {"ok": record_ok, "state": record_state},
            "passwordHashes": {
                "ok": password_hash_ok,
                "state": password_hash_state,
                "counts": password_hash_counts,
            },
            "learnerBackup": {"ok": backup_ok, "state": backup_state},
            "clinicalBank": {"ok": clinical_ok, "state": clinical_state},
            "retentionAutomation": {"ok": retention_ok, "state": retention_state},
            "authenticatedRetentionPolicy": {
                "ok": account_policy_ok,
                "state": account_policy_state,
            },
            "authenticationEmail": {
                "ok": auth_email_ok,
                "state": auth_email_state,
            },
            "aiTutor": {"ok": ai_ok, "state": ai_state, "required": ai_required},
        },
    }


class ReadinessProbeCoordinator:
    """Single-flight, briefly cached evaluation for the public readiness probe.

    The dependency audit includes an fsync/write-lock probe, SQLite integrity
    checks, corpus capability checks, and retention coordination. Running that
    work for every unauthenticated request would turn a required public health
    endpoint into I/O amplification. Both healthy and unhealthy outcomes are
    cached for the same short window; only the final boolean is retained.
    """

    def __init__(
        self,
        settings: Any,
        repo: Any,
        store: Any,
        clinical_store: Any,
        retention_cleanup: RetentionCleanupCoordinator,
        *,
        cache_ttl_seconds: float = _READINESS_CACHE_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        reporter: Callable[[Any, Any, Any, Any], dict[str, Any]] = readiness_report,
    ):
        self.settings = settings
        self.repo = repo
        self.store = store
        self.clinical_store = clinical_store
        self.retention_cleanup = retention_cleanup
        self.cache_ttl_seconds = max(0.0, float(cache_ttl_seconds))
        self.clock = clock
        self.reporter = reporter
        self._lock = threading.Lock()
        self._cached_ready: bool | None = None
        self._cached_at: float | None = None

    def ready(self) -> bool:
        with self._lock:
            now = self.clock()
            if (
                self._cached_ready is not None
                and self._cached_at is not None
                and now - self._cached_at < self.cache_ttl_seconds
            ):
                return self._cached_ready
            try:
                self.retention_cleanup.maybe_run()
                report = self.reporter(
                    self.settings,
                    self.repo,
                    self.store,
                    self.clinical_store,
                )
                ready = bool(report.get("ok") and self.retention_cleanup.healthy)
            except Exception as exc:
                # Probes fail closed without serializing exception text, paths,
                # or dependency configuration into the learner-facing response.
                logger.warning(
                    "readiness_evaluation_failed type=%s", type(exc).__name__
                )
                ready = False
            self._cached_ready = ready
            self._cached_at = self.clock()
            return ready


def build_ops_router(settings: Any, repo: Any, store: Any, clinical_store: Any) -> APIRouter:
    router = APIRouter(tags=["operations"])
    retention_cleanup = RetentionCleanupCoordinator(settings, store)
    # App construction is the worker startup boundary. The durable due check
    # makes this safe when several workers import the application together.
    retention_cleanup.maybe_run()
    readiness_probe = ReadinessProbeCoordinator(
        settings, repo, store, clinical_store, retention_cleanup
    )

    @router.get("/livez", include_in_schema=False)
    def livez() -> dict[str, bool]:
        return {"ok": True}

    @router.get("/readyz", include_in_schema=False)
    def readyz() -> JSONResponse:
        ready = readiness_probe.ready()
        return JSONResponse({"ok": ready}, status_code=200 if ready else 503)

    return router
