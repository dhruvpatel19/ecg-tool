"""Atomically add the corrected v2 source/license envelope to an existing corpus.

This is a metadata-only migration for a corpus whose waveforms, labels,
measurements, curation, and signal fingerprints have already been built. It
copies ``corpus.db`` side by side, updates only PTB provenance fields, validates
the copy, and swaps the database plus manifest only after every gate passes.
The original database and manifest are retained as ``*.pre-license-v2`` unless
``--remove-backup`` is supplied.

Dry-run is the default. Serving processes must be stopped for ``--apply`` so the
atomic swap cannot race an open Windows/SQLite handle.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.ingest.source_contract import source_catalog_entry  # noqa: E402


PTB_SOURCE = "ptbxl"
PTB_LICENSE = "CC-BY-4.0"
PTB_VERSION = "1.0.3"
LEIPZIG_SOURCE = "leipzig-heart-center"
LEIPZIG_LICENSE = "ODC-BY-1.0"


def _source_counts(conn: sqlite3.Connection) -> dict[str, int]:
    return {str(row[0]): int(row[1]) for row in conn.execute(
        "SELECT source, COUNT(*) FROM cases GROUP BY source ORDER BY source"
    )}


def audit_database(db_path: Path) -> dict[str, Any]:
    conn = sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        counts = _source_counts(conn)
        ptb_count = counts.get(PTB_SOURCE, 0)
        compliant = int(conn.execute(
            """
            SELECT COUNT(*) FROM cases
            WHERE source = ?
              AND source_version = ?
              AND license_id = ?
              AND json_extract(packet_json, '$.record_identity.sourceId') = ?
              AND json_extract(packet_json, '$.record_identity.sourceVersion') = ?
              AND json_extract(packet_json, '$.record_identity.licenseId') = ?
              AND json_extract(packet_json, '$.source_provenance.licenseId') = ?
              AND json_extract(packet_json, '$.ptbxl.source_provenance.licenseId') = ?
              AND json_extract(packet_json, '$.ptbxl_plus.source_provenance.licenseId') = ?
            """,
            (
                PTB_SOURCE, PTB_VERSION, PTB_LICENSE, PTB_SOURCE, PTB_VERSION,
                PTB_LICENSE, PTB_LICENSE, PTB_LICENSE, PTB_LICENSE,
            ),
        ).fetchone()[0])
        leipzig_invalid = int(conn.execute(
            "SELECT COUNT(*) FROM cases WHERE source = ? AND COALESCE(license_id, '') != ?",
            (LEIPZIG_SOURCE, LEIPZIG_LICENSE),
        ).fetchone()[0])
        integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        return {
            "sourceCounts": counts,
            "ptbCount": ptb_count,
            "ptbCompliant": compliant,
            "leipzigInvalid": leipzig_invalid,
            "integrity": integrity,
            "ready": ptb_count > 0 and compliant == ptb_count and leipzig_invalid == 0 and integrity == "ok",
        }
    finally:
        conn.close()


def _migrate_copy(source_db: Path, destination_db: Path) -> dict[str, Any]:
    shutil.copy2(source_db, destination_db)
    conn = sqlite3.connect(destination_db)
    try:
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute("BEGIN IMMEDIATE")
        ptb = source_catalog_entry("ptbxl")
        plus = source_catalog_entry("ptbxl-plus")
        top = {**ptb, "derivedEvidenceSources": [plus]}
        patient = (
            "CASE WHEN json_extract(packet_json, '$.ptbxl.metadata.patient_id') IS NULL "
            "THEN NULL ELSE CAST(json_extract(packet_json, '$.ptbxl.metadata.patient_id') AS TEXT) END"
        )
        conn.execute(
            f"""
            UPDATE cases
               SET source_record_id = ecg_id,
                   patient_id = {patient},
                   source_version = ?,
                   license_id = ?,
                   packet_json = json_set(
                       packet_json,
                       '$.ptbxl.source_provenance', json(?),
                       '$.ptbxl_plus.source_provenance', json(?),
                       '$.record_identity', json_object(
                           'sourceId', ?,
                           'sourceRecordId', ecg_id,
                           'patientId', {patient},
                           'sourceVersion', ?,
                           'licenseId', ?
                       ),
                       '$.source_provenance', json_set(json(?), '$.patientId', {patient})
                   )
             WHERE source = ?
            """,
            (
                PTB_VERSION,
                PTB_LICENSE,
                json.dumps(ptb, separators=(",", ":")),
                json.dumps(plus, separators=(",", ":")),
                PTB_SOURCE,
                PTB_VERSION,
                PTB_LICENSE,
                json.dumps(top, separators=(",", ":")),
                PTB_SOURCE,
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    result = audit_database(destination_db)
    if not result["ready"]:
        raise RuntimeError(f"Migrated database failed verification: {result}")
    return result


def _updated_manifest(original: dict[str, Any], audit: dict[str, Any]) -> dict[str, Any]:
    manifest = dict(original)
    manifest["version"] = max(5, int(manifest.get("version") or 0))
    manifest["licenseContractVersion"] = 2
    manifest["source"] = "multi_source_ecg_corpus"
    manifest["sourceCounts"] = audit["sourceCounts"]
    manifest["totalCases"] = sum(audit["sourceCounts"].values())
    catalog = dict(manifest.get("sourceCatalog") or {})
    catalog["ptbxl"] = source_catalog_entry("ptbxl")
    catalog["ptbxl-plus"] = source_catalog_entry("ptbxl-plus")
    if audit["sourceCounts"].get(LEIPZIG_SOURCE):
        existing_leipzig = dict(catalog.get(LEIPZIG_SOURCE) or {})
        catalog[LEIPZIG_SOURCE] = {
            **source_catalog_entry(LEIPZIG_SOURCE),
            **{
                key: value
                for key, value in existing_leipzig.items()
                if key in {"eligibleModes", "clinicalCaseEligible", "clinicalManagementEligible", "extractionVersion"}
            },
        }
    manifest["sourceCatalog"] = catalog
    manifest["complete"] = True
    return manifest


def migrate_corpus(corpus: Path, *, keep_backup: bool = True) -> dict[str, Any]:
    corpus = corpus.resolve()
    db = corpus / "corpus.db"
    manifest_path = corpus / "manifest.json"
    if not db.is_file() or not manifest_path.is_file():
        raise FileNotFoundError("Corpus requires corpus.db and manifest.json")
    original_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not original_manifest.get("complete"):
        raise ValueError("Refusing to migrate an incomplete corpus")

    before = audit_database(db)
    if before["ready"] and int(original_manifest.get("licenseContractVersion") or 0) >= 2:
        return {"status": "already_compliant", "audit": before}

    db_part = corpus / "corpus.db.license-v2.part"
    manifest_part = corpus / "manifest.json.license-v2.part"
    db_backup = corpus / "corpus.db.pre-license-v2"
    manifest_backup = corpus / "manifest.json.pre-license-v2"
    for path in (db_part, manifest_part, db_backup, manifest_backup):
        if path.exists():
            raise FileExistsError(f"Remove or archive stale migration artifact first: {path}")

    try:
        after = _migrate_copy(db, db_part)
        manifest_part.write_text(
            json.dumps(_updated_manifest(original_manifest, after), indent=2) + "\n",
            encoding="utf-8",
        )
        # Remove the completeness gate before replacing either authoritative file.
        os.replace(manifest_path, manifest_backup)
        os.replace(db, db_backup)
        os.replace(db_part, db)
        os.replace(manifest_part, manifest_path)
    except Exception:
        if not db.exists() and db_backup.exists():
            os.replace(db_backup, db)
        if not manifest_path.exists() and manifest_backup.exists():
            os.replace(manifest_backup, manifest_path)
        db_part.unlink(missing_ok=True)
        manifest_part.unlink(missing_ok=True)
        raise

    final = audit_database(db)
    if not final["ready"]:
        raise RuntimeError(f"Authoritative corpus failed post-swap verification: {final}")
    if not keep_backup:
        db_backup.unlink(missing_ok=True)
        manifest_backup.unlink(missing_ok=True)
    return {
        "status": "migrated",
        "before": before,
        "after": final,
        "backupDatabase": str(db_backup) if keep_backup else None,
        "backupManifest": str(manifest_backup) if keep_backup else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", default="data/ecg_corpus")
    parser.add_argument("--apply", action="store_true", help="perform the atomic side-by-side migration")
    parser.add_argument("--remove-backup", action="store_true", help="delete pre-v2 files after verification")
    args = parser.parse_args()
    corpus = Path(args.corpus)
    if not corpus.is_absolute():
        corpus = ROOT / corpus
    if not args.apply:
        db = corpus / "corpus.db"
        print(json.dumps({"status": "dry_run", "audit": audit_database(db)}, indent=2))
        return 0
    result = migrate_corpus(corpus, keep_backup=not args.remove_backup)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
