#!/usr/bin/env python3
"""Exhaustively audit a corpus before it becomes a release artifact.

This intentionally opens every case's canonical NPY file. Runtime readiness
verifies the resulting audit inside the checksum-pinned archive and performs
representative decodes; publication is where the slower all-file proof belongs.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.clinical.real_items import MINIMUM_CLINICAL_BANK_SIZE, vetted_real_items  # noqa: E402
from app.ingest.dangerous_arrhythmia import SOURCE_ID as RHYTHM_SOURCE_ID  # noqa: E402
from app.rapid_rhythm_supplement import (  # noqa: E402
    RUNTIME_LEAD,
    RUNTIME_MANIFEST_NAME,
    RUNTIME_MAPPING_VERSION,
    RUNTIME_SCOPE,
    RapidRhythmSupplement,
    SUPPLEMENT_DIRECTORY,
)
from app.source_policy import NEVER_LEARNER_SERVE_SOURCES, packet_mode_policy  # noqa: E402
from app.store import CaseStore, LocalWaveformStore  # noqa: E402


DEPLOYABLE_SOURCES = frozenset({"ptbxl", "prepared_bundle", "leipzig-heart-center"})
PRIVATE_MANIFEST_PATH_KEYS = frozenset(
    {"ptbxlDataRoot", "ptbxlPlusDataRoot", "sourceRoot", "stagingRoot"}
)
RHYTHM_REFERENCE_KEYS = frozenset(
    {
        "schemaVersion",
        "path",
        "sourceId",
        "runtimeScope",
        "mappingVersion",
        "fragmentCount",
        "learnerTargetCounts",
        "runtimeManifestSha256",
    }
)
OPAQUE_RHYTHM_RECORD = re.compile(r"fragment-[0-9a-f]{20}")
OPAQUE_RHYTHM_PARENT = re.compile(r"source-group-[0-9a-f]{20}")


def fail(message: str) -> None:
    raise SystemExit(f"release corpus audit failed: {message}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _rapid_rhythm_fingerprint(values: np.ndarray) -> str:
    """Recompute the source packet fingerprint from the packaged int16 file."""

    normalized = np.asarray(values, dtype="<i2")
    digest = hashlib.sha256()
    digest.update(RUNTIME_LEAD.encode("ascii"))
    digest.update(len(normalized).to_bytes(8, "little"))
    digest.update(normalized.tobytes())
    return digest.hexdigest()


def _audit_rapid_rhythm_supplement(root: Path, reference: object) -> dict:
    """Exhaustively prove the optional single-lead release and its boundaries."""

    if not isinstance(reference, dict):
        fail("rapid rhythm supplement reference is not an object")
    if set(reference) != RHYTHM_REFERENCE_KEYS:
        fail("rapid rhythm supplement reference has an unexpected schema")
    try:
        expected_count = int(reference.get("fragmentCount") or 0)
        expected_targets = {
            str(target): int(count)
            for target, count in (reference.get("learnerTargetCounts") or {}).items()
        }
    except (AttributeError, TypeError, ValueError):
        fail("rapid rhythm supplement reference counts are invalid")
    if (
        reference.get("schemaVersion") != 1
        or reference.get("path") != SUPPLEMENT_DIRECTORY
        or reference.get("sourceId") != RHYTHM_SOURCE_ID
        or reference.get("runtimeScope") != RUNTIME_SCOPE
        or reference.get("mappingVersion") != RUNTIME_MAPPING_VERSION
        or expected_count <= 0
        or not expected_targets
        or sum(expected_targets.values()) != expected_count
        or not re.fullmatch(r"[0-9a-f]{64}", str(reference.get("runtimeManifestSha256") or ""))
    ):
        fail("rapid rhythm supplement reference violates the reviewed release contract")

    supplement_root = (root / SUPPLEMENT_DIRECTORY).resolve()
    if root.resolve() not in supplement_root.parents or not supplement_root.is_dir():
        fail("referenced rapid rhythm supplement directory is missing")
    if any(path.is_symlink() for path in supplement_root.rglob("*")):
        fail("rapid rhythm supplement may not contain symlinks")
    allowed_top_level = {
        "manifest.json",
        RUNTIME_MANIFEST_NAME,
        "rhythm_streams.db",
        "waveforms",
    }
    actual_top_level = {path.name for path in supplement_root.iterdir()}
    if actual_top_level != allowed_top_level:
        fail("rapid rhythm supplement contains an unexpected or incomplete top-level artifact")

    runtime_path = supplement_root / RUNTIME_MANIFEST_NAME
    source_manifest_path = supplement_root / "manifest.json"
    database_path = supplement_root / "rhythm_streams.db"
    waveform_root = supplement_root / "waveforms"
    try:
        reader = RapidRhythmSupplement(supplement_root, expected=reference)
    except (OSError, TypeError, ValueError) as exc:
        fail(
            "rapid rhythm supplement production reader rejected the release: "
            f"{type(exc).__name__}"
        )

    source_manifest = reader.source_manifest
    runtime_manifest = reader.runtime_manifest
    if (
        source_manifest.get("rawPatientIdentifiersIncluded") is not False
        or source_manifest.get("rawRecordIdentifiersIncluded") is not False
        or source_manifest.get("clinicalManagementEligible") is not False
        or source_manifest.get("shockabilityClassificationEligible") is not False
        or source_manifest.get("currentRuntimeConnected") is not False
        or runtime_manifest.get("clinicalCaseEligible") is not False
        or runtime_manifest.get("hemodynamicContextAvailable") is not False
        or runtime_manifest.get("stabilityInferenceEligible") is not False
        or runtime_manifest.get("cardiacArrestInferenceEligible") is not False
        or runtime_manifest.get("shockabilityClassificationEligible") is not False
        or runtime_manifest.get("clinicalManagementEligible") is not False
        or runtime_manifest.get("treatmentOrActionSequenceEligible") is not False
        or runtime_manifest.get("actionQuestionsRequireSeparateAuthoredContext") is not True
        or runtime_manifest.get("actionQuestionsFormativeOnly") is not True
    ):
        fail("rapid rhythm supplement exceeds its recognition/discrimination evidence boundary")
    if (
        sha256(runtime_path) != reference["runtimeManifestSha256"]
        or runtime_manifest.get("sourceManifestSha256") != sha256(source_manifest_path)
        or int(source_manifest.get("fragmentCount") or 0) != expected_count
        or int(runtime_manifest.get("fragmentCount") or 0) != expected_count
        or reader.count != expected_count
        or reader.target_counts != expected_targets
        or runtime_manifest.get("learnerTargetCounts") != expected_targets
    ):
        fail("rapid rhythm supplement manifest hashes or counts do not reconcile")

    with sqlite3.connect(database_path.as_uri() + "?mode=ro&immutable=1", uri=True) as conn:
        integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        database_count = int(conn.execute("SELECT COUNT(*) FROM rhythm_windows").fetchone()[0])
    if integrity != "ok" or database_count != expected_count:
        fail("rapid rhythm supplement database integrity/count check failed")

    expected_paths: set[Path] = set()
    runtime_index_entries: list[str] = []
    source_index_rows: list[tuple[str, str]] = []
    source_rhythm_counts: Counter[str] = Counter()
    target_counts: Counter[str] = Counter()
    for packet in reader.store.iter_packets():
        identity = packet.get("record_identity") or {}
        provenance = packet.get("source_provenance") or {}
        labels = packet.get("source_labels") or {}
        rhythm = labels.get("rhythm") if isinstance(labels, dict) else {}
        waveform = packet.get("waveform") or {}
        case_id = str(packet.get("case_id") or "")
        record_id = str(identity.get("sourceRecordId") or "")
        parent_id = str(identity.get("parentRecordId") or "")
        fingerprint = str(packet.get("signal_fingerprint") or "")
        if (
            not isinstance(identity, dict)
            or not isinstance(provenance, dict)
            or not isinstance(rhythm, dict)
            or not isinstance(waveform, dict)
            or not OPAQUE_RHYTHM_RECORD.fullmatch(record_id)
            or not OPAQUE_RHYTHM_PARENT.fullmatch(parent_id)
            or case_id != f"{RHYTHM_SOURCE_ID}:{record_id}"
            or str(identity.get("patientId") or "")
            or str(provenance.get("patientId") or "")
            or provenance.get("rawPatientIdentifiersIncluded") is not False
            or provenance.get("rawRecordIdentifiersIncluded") is not False
            or not re.fullmatch(r"[0-9a-f]{64}", fingerprint)
        ):
            fail("rapid rhythm packet contains non-opaque or private source identity")
        try:
            frequency = float(waveform.get("sampling_frequency"))
            duration = float(waveform.get("duration_sec"))
            expected_samples = int(round(frequency * duration))
        except (TypeError, ValueError):
            fail("rapid rhythm packet has invalid waveform dimensions")
        path = reader.waveforms.path_for(case_id).resolve()
        if waveform_root.resolve() not in path.parents:
            fail("rapid rhythm waveform path escapes its release directory")
        expected_paths.add(path)
        try:
            array = np.load(path, mmap_mode="r", allow_pickle=False)
        except (OSError, ValueError) as exc:
            fail(f"rapid rhythm waveform is unreadable: {type(exc).__name__}")
        if array.shape != (expected_samples, 1) or array.dtype != np.dtype("int16"):
            fail("rapid rhythm waveform has an unexpected shape or dtype")
        if _rapid_rhythm_fingerprint(array[:, 0]) != fingerprint:
            fail("rapid rhythm waveform does not match its packet fingerprint")
        projected = reader.get_case(case_id)
        objective = str(((projected or {}).get("supported_objectives") or [""])[0])
        source_code = str(rhythm.get("rhythmCode") or "")
        if not objective:
            fail("rapid rhythm packet has no reviewed learner target")
        runtime_index_entries.append(
            "\0".join((case_id, fingerprint, source_code, objective))
        )
        source_index_rows.append((case_id, fingerprint))
        source_rhythm_counts[str(rhythm.get("canonicalRhythmId") or "")] += 1
        target_counts[objective] += 1

    actual_paths = {path.resolve() for path in waveform_root.rglob("*.npy") if path.is_file()}
    non_npy_files = [
        path for path in waveform_root.rglob("*") if path.is_file() and path.suffix != ".npy"
    ]
    if (
        non_npy_files
        or expected_paths != actual_paths
        or len(expected_paths) != expected_count
    ):
        fail("rapid rhythm database/waveform file mapping is not one-to-one")

    source_digest = hashlib.sha256()
    for case_id, fingerprint in sorted(source_index_rows):
        source_digest.update(case_id.encode("ascii"))
        source_digest.update(fingerprint.encode("ascii"))
    runtime_digest = hashlib.sha256()
    for entry in sorted(runtime_index_entries):
        runtime_digest.update(entry.encode("utf-8"))
    if (
        source_digest.hexdigest() != source_manifest.get("contentIndexSha256")
        or dict(sorted(source_rhythm_counts.items()))
        != source_manifest.get("canonicalRhythmCounts")
        or runtime_digest.hexdigest() != runtime_manifest.get("contentIndexSha256")
        or dict(sorted(target_counts.items())) != expected_targets
    ):
        fail("rapid rhythm supplement content indexes do not match the packaged data")

    waveform_files_digest = hashlib.sha256()
    for path in sorted(
        actual_paths,
        key=lambda value: value.relative_to(supplement_root).as_posix(),
    ):
        relative = path.relative_to(supplement_root).as_posix()
        waveform_files_digest.update(f"{sha256(path)}  {relative}\n".encode("ascii"))

    return {
        "present": True,
        "complete": True,
        "schemaVersion": 1,
        "sourceId": RHYTHM_SOURCE_ID,
        "path": SUPPLEMENT_DIRECTORY,
        "fragmentCount": expected_count,
        "learnerTargetCounts": expected_targets,
        "runtimeManifestSha256": sha256(runtime_path),
        "sourceManifestSha256": sha256(source_manifest_path),
        "databaseSha256": sha256(database_path),
        "contentIndexSha256": runtime_digest.hexdigest(),
        "waveforms": {
            "complete": True,
            "caseFilesChecked": len(expected_paths),
            "npyFilesFound": len(actual_paths),
            "expectedColumns": 1,
            "lead": RUNTIME_LEAD,
            "dtype": "int16",
            "filesSha256": waveform_files_digest.hexdigest(),
        },
        "identity": {
            "opaqueOnly": True,
            "rawPatientIdentifiersIncluded": False,
            "rawRecordIdentifiersIncluded": False,
        },
        "clinicalManagementEligible": False,
        "shockabilityClassificationEligible": False,
        "actionQuestionsFormativeOnly": True,
    }


def audit(root: Path) -> dict:
    root = root.resolve(strict=True)
    manifest_path = root / "manifest.json"
    database_path = root / "corpus.db"
    waveform_root = root / "waveforms"
    if not manifest_path.is_file() or not database_path.is_file() or not waveform_root.is_dir():
        fail("manifest.json, corpus.db, and waveforms/ are required")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"manifest is unreadable: {exc}")
    if manifest.get("complete") is not True:
        fail("manifest is not complete")
    leaked_path_keys = sorted(PRIVATE_MANIFEST_PATH_KEYS.intersection(manifest))
    if leaked_path_keys:
        fail(
            "manifest contains local source paths that cannot enter a release artifact: "
            + ", ".join(leaked_path_keys)
        )

    store = CaseStore(database_path, read_only=True)
    waveforms = LocalWaveformStore(waveform_root)
    total = store.count()
    source_counts = store.source_counts()
    student_count = store.student_facing_count()
    manifest_sources = {
        str(source): int(count)
        for source, count in (manifest.get("sourceCounts") or {}).items()
    }
    if total != int(manifest.get("totalCases") or 0):
        fail("database total does not match manifest")
    if source_counts != manifest_sources:
        fail("database source counts do not match manifest")
    if student_count != int(manifest.get("studentFacing") or 0):
        fail("database Tier A/B count does not match manifest")
    if not source_counts or not set(source_counts) <= DEPLOYABLE_SOURCES:
        fail(f"unapproved deployable source set: {sorted(source_counts)}")
    if set(source_counts) & NEVER_LEARNER_SERVE_SOURCES:
        fail("research-only source is present in the release corpus")

    eligible = {"training": 0, "rapid": 0}
    eligible_by_source: dict[str, dict[str, int]] = {
        source: {"training": 0, "rapid": 0} for source in source_counts
    }
    expected_paths: set[Path] = set()
    malformed: list[str] = []
    with sqlite3.connect(database_path.as_uri() + "?mode=ro&immutable=1", uri=True) as conn:
        rows = conn.execute(
            "SELECT ecg_id, teaching_tier, source, packet_json FROM cases ORDER BY source, ecg_id"
        )
        for case_id, teaching_tier, source, packet_json in rows:
            try:
                packet = json.loads(packet_json)
                waveform = packet.get("waveform") or {}
                frequency = float(waveform.get("sampling_frequency"))
                duration = float(waveform.get("duration_sec"))
                expected_samples = int(round(frequency * duration))
                path = waveforms.path_for(case_id).resolve()
                if waveform_root.resolve() not in path.parents:
                    fail(f"waveform path escapes corpus root for {case_id}")
                expected_paths.add(path)
                array = np.load(path, mmap_mode="r", allow_pickle=False)
                if array.shape != (expected_samples, 12) or array.dtype != np.dtype("int16"):
                    malformed.append(str(case_id))
                if teaching_tier in {"A", "B"}:
                    for mode in ("training", "rapid"):
                        if packet_mode_policy(packet, mode).allowed:
                            eligible[mode] += 1
                            eligible_by_source[str(source)][mode] += 1
            except Exception as exc:
                fail(f"case/waveform {case_id!r} is unreadable: {type(exc).__name__}")
    if malformed:
        fail(f"unexpected waveform shape/dtype for {len(malformed)} case(s): {malformed[:5]}")

    actual_paths = {path.resolve() for path in waveform_root.rglob("*.npy") if path.is_file()}
    missing = expected_paths - actual_paths
    extras = actual_paths - expected_paths
    if missing or extras or len(expected_paths) != total:
        fail(
            f"case/file mapping mismatch (expected={len(expected_paths)}, actual={len(actual_paths)}, "
            f"missing={len(missing)}, extra={len(extras)})"
        )
    if min(eligible.values(), default=0) < 5000:
        fail(f"Training/Rapid eligible pools are below 5,000: {eligible}")
    student_sources = {source for source, count in store.student_source_counts().items() if count > 0}
    if any(eligible_by_source[source][mode] == 0 for source in student_sources for mode in eligible):
        fail("a Tier A/B source has no eligible Training or Rapid packets")

    clinical_items = vetted_real_items(store.get_packet)
    clinical_ecgs: set[str] = set()
    expected_clinical_ecgs = 0
    for item in clinical_items:
        clinical_ecgs.add(str(item.ecg_id))
        expected_clinical_ecgs += 1
        if item.prior_ecg_id is not None:
            clinical_ecgs.add(str(item.prior_ecg_id))
            expected_clinical_ecgs += 1
    if (
        len(clinical_items) < MINIMUM_CLINICAL_BANK_SIZE
        or len(clinical_ecgs) != expected_clinical_ecgs
    ):
        fail("Clinical bank did not preserve 100+ distinct real ECGs")

    supplement_reference = manifest.get("rapidRhythmSupplement")
    rhythm_audit = (
        _audit_rapid_rhythm_supplement(root, supplement_reference)
        if supplement_reference is not None
        else {"present": False}
    )

    return {
        "schemaVersion": 1,
        "manifestSha256": sha256(manifest_path),
        "totalCases": total,
        "studentFacingCases": student_count,
        "sourceCounts": source_counts,
        "eligibleCaseCounts": eligible,
        "eligibleCaseCountsBySource": eligible_by_source,
        "waveforms": {
            "complete": True,
            "caseFilesChecked": len(expected_paths),
            "npyFilesFound": len(actual_paths),
            "expectedColumns": 12,
            "dtype": "int16",
        },
        "clinical": {
            "harnessPassed": True,
            "items": len(clinical_items),
            "distinctRealEcgs": len(clinical_ecgs),
        },
        "rapidRhythmSupplement": rhythm_audit,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus-root", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or args.corpus_root / "release-audit.json"
    result = audit(args.corpus_root)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"release corpus audit passed: {result['totalCases']} cases, "
        f"{result['waveforms']['caseFilesChecked']} waveforms, "
        f"{result['clinical']['items']} clinical items"
    )


if __name__ == "__main__":
    main()
