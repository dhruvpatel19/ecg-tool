from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path

from app.store.case_store import CaseStore


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "migrate_corpus_license_contract_v2",
    ROOT / "scripts" / "migrate_corpus_license_contract_v2.py",
)
assert SPEC and SPEC.loader
MIGRATION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MIGRATION)


def test_license_migration_is_atomic_scoped_and_idempotent(tmp_path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    store = CaseStore(corpus / "corpus.db")
    store.upsert_case(
        {
            "case_id": "1",
            "source": "ptbxl",
            "teaching_tier": "A",
            "ptbxl": {"metadata": {"patient_id": 42.0}},
            "ptbxl_plus": {},
            "concept_confidence": {"rate": {"tier": "A", "score": 1.0}},
            "supported_objectives": ["rate"],
            "signal_quality": {"status": "acceptable"},
        }
    )
    store.upsert_case(
        {
            "case_id": "leipzig-heart-center:x@1-2",
            "source": "leipzig-heart-center",
            "teaching_tier": "A",
            "record_identity": {
                "sourceId": "leipzig-heart-center",
                "sourceRecordId": "x@1-2",
                "patientId": "x",
                "sourceVersion": "1.0.0",
                "licenseId": "ODC-BY-1.0",
            },
            "source_provenance": {
                "sourceId": "leipzig-heart-center",
                "sourceVersion": "1.0.0",
                "licenseId": "ODC-BY-1.0",
            },
            "concept_confidence": {"sinus_rhythm": {"tier": "A", "score": 1.0}},
            "supported_objectives": ["sinus_rhythm"],
            "signal_quality": {"status": "acceptable"},
        }
    )
    (corpus / "manifest.json").write_text(
        json.dumps(
            {
                "version": 4,
                "complete": True,
                "sourceCatalog": {
                    "ptbxl": {"licenseId": "ODC-BY-1.0"},
                    "leipzig-heart-center": {"licenseId": "ODC-BY-1.0", "eligibleModes": ["training"]},
                },
            }
        ),
        encoding="utf-8",
    )

    result = MIGRATION.migrate_corpus(corpus, keep_backup=False)
    assert result["status"] == "migrated"
    assert result["after"]["sourceCounts"] == {"leipzig-heart-center": 1, "ptbxl": 1}

    conn = sqlite3.connect(corpus / "corpus.db")
    conn.row_factory = sqlite3.Row
    ptb = conn.execute("SELECT * FROM cases WHERE source = 'ptbxl'").fetchone()
    packet = json.loads(ptb["packet_json"])
    assert ptb["license_id"] == "CC-BY-4.0"
    assert ptb["patient_id"] == "42.0"
    assert packet["record_identity"]["licenseId"] == "CC-BY-4.0"
    assert packet["ptbxl"]["source_provenance"]["sourceVersion"] == "1.0.3"
    assert packet["ptbxl_plus"]["source_provenance"]["sourceVersion"] == "1.0.1"
    leipzig = conn.execute(
        "SELECT license_id, packet_json FROM cases WHERE source = 'leipzig-heart-center'"
    ).fetchone()
    assert leipzig["license_id"] == "ODC-BY-1.0"
    assert json.loads(leipzig["packet_json"])["record_identity"]["licenseId"] == "ODC-BY-1.0"
    conn.close()

    manifest = json.loads((corpus / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["licenseContractVersion"] == 2
    assert manifest["sourceCatalog"]["ptbxl"]["licenseId"] == "CC-BY-4.0"
    assert manifest["sourceCatalog"]["ptbxl-plus"]["licenseId"] == "CC-BY-4.0"
    assert manifest["sourceCatalog"]["leipzig-heart-center"]["licenseId"] == "ODC-BY-1.0"
    assert manifest["sourceCatalog"]["leipzig-heart-center"]["eligibleModes"] == ["training"]

    second = MIGRATION.migrate_corpus(corpus, keep_backup=False)
    assert second["status"] == "already_compliant"
