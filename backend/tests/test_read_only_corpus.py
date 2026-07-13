from __future__ import annotations

import sqlite3

import pytest

from app.store.case_store import CaseStore


def _packet(case_id: str = "1") -> dict:
    return {
        "case_id": case_id,
        "source": "ptbxl",
        "teaching_tier": "A",
        "supported_objectives": ["rate"],
        "concept_confidence": {"rate": {"tier": "A", "score": 1.0}},
        "record_identity": {
            "sourceRecordId": case_id,
            "sourceVersion": "1.0.3",
            "licenseId": "CC-BY-4.0",
        },
        "signal_quality": {"status": "acceptable"},
    }


def test_read_only_case_store_serves_without_sqlite_sidecars(tmp_path) -> None:
    db = tmp_path / "corpus.db"
    writable = CaseStore(db)
    writable.upsert_case(_packet())

    read_only = CaseStore(db, read_only=True)
    assert read_only.count() == 1
    assert read_only.get_packet("1")["record_identity"]["licenseId"] == "CC-BY-4.0"
    assert not (tmp_path / "corpus.db-wal").exists()
    assert not (tmp_path / "corpus.db-shm").exists()

    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        read_only.upsert_case(_packet("2"))


def test_read_only_case_store_fails_closed_on_missing_schema(tmp_path) -> None:
    db = tmp_path / "empty.db"
    sqlite3.connect(db).close()
    with pytest.raises(ValueError, match="required tables"):
        CaseStore(db, read_only=True)
