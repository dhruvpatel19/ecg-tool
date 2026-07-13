#!/usr/bin/env python3
"""Exhaustively audit a corpus before it becomes a release artifact.

This intentionally opens every case's canonical NPY file. Runtime readiness
verifies the resulting audit inside the checksum-pinned archive and performs
representative decodes; publication is where the slower all-file proof belongs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.clinical.real_items import MINIMUM_CLINICAL_BANK_SIZE, vetted_real_items  # noqa: E402
from app.source_policy import NEVER_LEARNER_SERVE_SOURCES, packet_mode_policy  # noqa: E402
from app.store import CaseStore, LocalWaveformStore  # noqa: E402


DEPLOYABLE_SOURCES = frozenset({"ptbxl", "prepared_bundle", "leipzig-heart-center"})


def fail(message: str) -> None:
    raise SystemExit(f"release corpus audit failed: {message}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
    clinical_ecgs = {str(item.ecg_id) for item in clinical_items}
    if len(clinical_items) < MINIMUM_CLINICAL_BANK_SIZE or len(clinical_ecgs) != len(clinical_items):
        fail("Clinical bank did not preserve 100+ distinct real ECGs")

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
