from __future__ import annotations

import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

from app.ops import readiness_report


class FakeCaseStore:
    def __init__(self, cases: int = 100, students: int = 90):
        self.cases = cases
        self.students = students

    def count(self) -> int:
        return self.cases

    def student_facing_count(self) -> int:
        return self.students


class FakeLearningStore:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def learning_record_integrity(self) -> tuple[bool, str]:
        return True, "ready"

    def password_hash_iteration_audit(self) -> dict[str, int]:
        return {"total": 0, "current": 0, "legacy": 0, "future": 0, "invalid": 0}


class FakeClinicalStore:
    def __init__(self, verdict: tuple[bool, str] = (True, "ready")):
        self.verdict = verdict

    def release_readiness(self, minimum_cases: int) -> tuple[bool, str]:
        return self.verdict


CLINICAL = FakeClinicalStore()


def configured(tmp_path: Path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "corpus.db").touch()
    (corpus / "waveforms").mkdir()
    db_path = tmp_path / "state" / "learning.db"
    db_path.parent.mkdir()
    settings = SimpleNamespace(
        require_real_data=True,
        sqlite_path=db_path,
        learner_backup_marker_path=Path(f"{db_path}.last-backup-success"),
        auth_email_delivery_mode="smtp",
        auth_smtp_host="smtp.example.edu",
        auth_smtp_port=587,
        auth_smtp_username="mailer",
        auth_smtp_password="test-only-secret",
        auth_smtp_starttls=True,
        auth_smtp_timeout_seconds=10,
        auth_email_from_address="ECG Learning <no-reply@example.edu>",
        auth_email_reply_to="TRACE support <support@example.edu>",
        auth_public_app_url="https://learn.example.edu",
    )
    repo = SimpleNamespace(
        root=corpus,
        store=FakeCaseStore(),
        deployment_readiness=lambda: (True, "ready"),
        status={
            "active_source": "corpus",
            "fixture_fallback": False,
            "manifest": {"complete": True},
        },
    )
    return settings, repo, FakeLearningStore(db_path)


def test_readiness_fails_closed_without_release_capability_audit(tmp_path: Path):
    settings, repo, store = configured(tmp_path)
    del repo.deployment_readiness

    report = readiness_report(settings, repo, store, CLINICAL)

    assert report["ok"] is False
    assert report["checks"]["corpus"]["state"] == "corpus_capability_audit_missing"


def test_readiness_propagates_release_capability_failure_without_paths(tmp_path: Path):
    settings, repo, store = configured(tmp_path)
    repo.deployment_readiness = lambda: (False, "representative_waveform_unreadable")

    report = readiness_report(settings, repo, store, CLINICAL)

    assert report["ok"] is False
    assert report["checks"]["corpus"]["state"] == "representative_waveform_unreadable"


def test_readiness_requires_complete_validated_clinical_bank(tmp_path: Path):
    settings, repo, store = configured(tmp_path)
    clinical = FakeClinicalStore((False, "clinical_bank_below_release_minimum"))

    report = readiness_report(settings, repo, store, clinical)

    assert report["ok"] is False
    assert report["checks"]["clinicalBank"] == {
        "ok": False,
        "state": "clinical_bank_below_release_minimum",
    }


def test_readiness_requires_real_corpus_and_writable_database(tmp_path: Path):
    settings, repo, store = configured(tmp_path)

    report = readiness_report(settings, repo, store, CLINICAL)

    assert report["ok"] is True
    assert report["checks"]["corpus"]["state"] == "ready"
    assert report["checks"]["learnerDatabase"]["state"] == "ready"
    assert report["checks"]["learningRecord"] == {"ok": True, "state": "ready"}


def test_readiness_fails_closed_when_state_mount_is_low_on_space(
    tmp_path: Path, monkeypatch
):
    settings, repo, store = configured(tmp_path)
    settings.min_state_free_bytes = 2 * 1024 * 1024 * 1024
    monkeypatch.setattr(
        "app.ops.shutil.disk_usage",
        lambda _path: SimpleNamespace(total=10, used=9, free=1),
    )

    report = readiness_report(settings, repo, store, CLINICAL)

    assert report["ok"] is False
    assert report["checks"]["learnerDatabase"] == {
        "ok": False,
        "state": "state_mount_low_space",
    }


def test_readiness_fails_closed_when_manifest_is_incomplete(tmp_path: Path):
    settings, repo, store = configured(tmp_path)
    repo.status["manifest"]["complete"] = False

    report = readiness_report(settings, repo, store, CLINICAL)

    assert report["ok"] is False
    assert report["checks"]["corpus"]["state"] == "corpus_manifest_incomplete"


def test_readiness_never_exposes_host_paths(tmp_path: Path):
    settings, repo, store = configured(tmp_path)
    (repo.root / "corpus.db").unlink()

    report = readiness_report(settings, repo, store, CLINICAL)

    assert str(tmp_path) not in str(report)
    assert report["checks"]["corpus"]["state"] == "corpus_mount_missing"


def test_readiness_requires_a_recent_successful_backup_when_configured(tmp_path: Path):
    settings, repo, store = configured(tmp_path)
    settings.require_recent_backup = True
    settings.backup_max_age_seconds = 3600
    marker = Path(f"{settings.sqlite_path}.last-backup-success")
    stale_time = time.time() - 3601
    marker.touch()
    marker.chmod(0o640)
    os.utime(marker, (stale_time, stale_time))

    report = readiness_report(settings, repo, store, CLINICAL)

    assert report["ok"] is False
    assert report["checks"]["learnerBackup"] == {"ok": False, "state": "backup_stale"}


def test_recent_backup_marker_satisfies_readiness(tmp_path: Path):
    settings, repo, store = configured(tmp_path)
    settings.require_recent_backup = True
    settings.backup_max_age_seconds = 3600
    Path(f"{settings.sqlite_path}.last-backup-success").touch()

    report = readiness_report(settings, repo, store, CLINICAL)

    assert report["ok"] is True
    assert report["checks"]["learnerBackup"] == {"ok": True, "state": "ready"}


def test_missing_backup_fails_closed_immediately_when_required(tmp_path: Path):
    settings, repo, store = configured(tmp_path)
    settings.require_recent_backup = True
    report = readiness_report(settings, repo, store, CLINICAL)

    assert report["ok"] is False
    assert report["checks"]["learnerBackup"] == {
        "ok": False,
        "state": "backup_never_succeeded",
    }


def test_required_ai_tutor_blocks_readiness_when_provider_is_mock(tmp_path: Path):
    settings, repo, store = configured(tmp_path)
    settings.llm_required = True
    settings.llm_provider = "mock"

    report = readiness_report(settings, repo, store, CLINICAL)

    assert report["ok"] is False
    assert report["checks"]["aiTutor"] == {
        "ok": False,
        "state": "mock_provider",
        "required": True,
    }


def test_optional_ai_tutor_is_reported_without_blocking_core_readiness(tmp_path: Path):
    settings, repo, store = configured(tmp_path)
    settings.llm_required = False
    settings.llm_provider = "mock"

    report = readiness_report(settings, repo, store, CLINICAL)

    assert report["ok"] is True
    assert report["checks"]["aiTutor"]["ok"] is False
    assert report["checks"]["aiTutor"]["required"] is False


def test_production_readiness_requires_external_authenticated_retention_policy(
    tmp_path: Path,
):
    settings, repo, store = configured(tmp_path)
    settings.app_env = "production"
    settings.retention_cleanup_enabled = True
    settings.authenticated_retention_policy_acknowledged = False
    settings.authenticated_retention_policy_reference = None

    report = readiness_report(settings, repo, store, CLINICAL)

    assert report["ok"] is False
    assert report["checks"]["authenticatedRetentionPolicy"] == {
        "ok": False,
        "state": "authenticated_retention_policy_unacknowledged",
    }

    settings.authenticated_retention_policy_acknowledged = True
    report = readiness_report(settings, repo, store, CLINICAL)
    assert report["checks"]["authenticatedRetentionPolicy"]["state"] == (
        "authenticated_retention_policy_reference_missing"
    )


def test_documented_retention_policy_and_automation_satisfy_production_gate(
    tmp_path: Path,
):
    settings, repo, store = configured(tmp_path)
    settings.app_env = "production"
    settings.retention_cleanup_enabled = True
    settings.authenticated_retention_policy_acknowledged = True
    settings.authenticated_retention_policy_reference = "policy:learner-records-v1"

    report = readiness_report(settings, repo, store, CLINICAL)

    assert report["ok"] is True
    assert report["checks"]["authenticatedRetentionPolicy"] == {
        "ok": True,
        "state": "ready",
    }
    assert report["checks"]["retentionAutomation"] == {
        "ok": True,
        "state": "ready",
    }
    assert settings.authenticated_retention_policy_reference not in str(report)


def test_production_readiness_rejects_disabled_retention_automation(tmp_path: Path):
    settings, repo, store = configured(tmp_path)
    settings.app_env = "production"
    settings.retention_cleanup_enabled = False
    settings.authenticated_retention_policy_acknowledged = True
    settings.authenticated_retention_policy_reference = "policy:learner-records-v1"

    report = readiness_report(settings, repo, store, CLINICAL)

    assert report["ok"] is False
    assert report["checks"]["retentionAutomation"] == {
        "ok": False,
        "state": "automatic_retention_cleanup_disabled",
    }


def test_production_readiness_requires_complete_smtp_auth_email_config(tmp_path: Path):
    settings, repo, store = configured(tmp_path)
    settings.app_env = "production"
    settings.retention_cleanup_enabled = True
    settings.authenticated_retention_policy_acknowledged = True
    settings.authenticated_retention_policy_reference = "policy:learner-records-v1"
    settings.auth_smtp_host = None

    report = readiness_report(settings, repo, store, CLINICAL)

    assert report["ok"] is False
    assert report["checks"]["authenticationEmail"] == {
        "ok": False,
        "state": "authentication_email_configuration_invalid:AUTH_SMTP_HOST",
    }


def test_production_readiness_requires_monitored_auth_reply_to(tmp_path: Path):
    settings, repo, store = configured(tmp_path)
    settings.app_env = "production"
    settings.retention_cleanup_enabled = True
    settings.authenticated_retention_policy_acknowledged = True
    settings.authenticated_retention_policy_reference = "policy:learner-records-v1"
    settings.auth_email_reply_to = None

    report = readiness_report(settings, repo, store, CLINICAL)

    assert report["ok"] is False
    assert report["checks"]["authenticationEmail"] == {
        "ok": False,
        "state": "authentication_email_configuration_invalid:AUTH_EMAIL_REPLY_TO_REQUIRED",
    }
