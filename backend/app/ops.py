"""Operational liveness and readiness probes."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import tempfile
import time
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse


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


def readiness_report(settings: Any, repo: Any, store: Any, clinical_store: Any) -> dict[str, Any]:
    corpus_ok, corpus_state = _corpus_check(settings, repo)
    database_ok, database_state = _database_check(settings, store)
    backup_ok, backup_state = _backup_check(settings)
    ai_ok, ai_state = _ai_tutor_check(settings)
    clinical_ok, clinical_state = _clinical_check(settings, clinical_store)
    ai_required = bool(getattr(settings, "llm_required", False))
    return {
        "ok": corpus_ok and database_ok and backup_ok and clinical_ok and (ai_ok or not ai_required),
        "checks": {
            "corpus": {"ok": corpus_ok, "state": corpus_state},
            "learnerDatabase": {"ok": database_ok, "state": database_state},
            "learnerBackup": {"ok": backup_ok, "state": backup_state},
            "clinicalBank": {"ok": clinical_ok, "state": clinical_state},
            "aiTutor": {"ok": ai_ok, "state": ai_state, "required": ai_required},
        },
    }


def build_ops_router(settings: Any, repo: Any, store: Any, clinical_store: Any) -> APIRouter:
    router = APIRouter(tags=["operations"])

    @router.get("/livez", include_in_schema=False)
    def livez() -> dict[str, bool]:
        return {"ok": True}

    @router.get("/readyz", include_in_schema=False)
    def readyz() -> JSONResponse:
        report = readiness_report(settings, repo, store, clinical_store)
        return JSONResponse({"ok": report["ok"]}, status_code=200 if report["ok"] else 503)

    return router
