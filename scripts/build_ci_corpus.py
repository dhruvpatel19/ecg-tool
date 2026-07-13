#!/usr/bin/env python3
"""Build the deterministic, real-PTB corpus used by clean CI runners.

The asset contains exactly the distinct PTB-XL ECGs bound to the authored
Clinical bank. It is a source-test dependency, not the production corpus or a
substitute for the exhaustive 22,497-case release audit.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import gzip
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import sys
import tarfile
import tempfile


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.clinical.real_items import REAL_ECGS_BY_SCENARIO, vetted_real_items  # noqa: E402
from app.store import CaseStore, LocalWaveformStore  # noqa: E402


PRIVATE_METADATA_KEYS = {
    "patient_id",
    "recording_date",
    "filename_lr",
    "filename_hr",
    "nurse",
    "site",
    "device",
    "validated_by",
}


def sanitized_packet(packet: dict) -> dict:
    cleaned = deepcopy(packet)
    identity = cleaned.get("record_identity") or {}
    identity.pop("patientId", None)
    provenance = cleaned.get("source_provenance") or {}
    provenance.pop("patientId", None)
    ptbxl = cleaned.get("ptbxl") or {}
    metadata = ptbxl.get("metadata") or {}
    ptbxl["metadata"] = {
        key: value for key, value in metadata.items() if key not in PRIVATE_METADATA_KEYS
    }
    nested_provenance = ptbxl.get("source_provenance") or {}
    nested_provenance.pop("patientId", None)
    return cleaned


def write_deterministic_archive(corpus_root: Path, destination: Path) -> None:
    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w", format=tarfile.PAX_FORMAT) as archive:
        paths = sorted(
            [corpus_root / "manifest.json", corpus_root / "corpus.db"]
            + [path for path in (corpus_root / "waveforms").rglob("*")],
            key=lambda path: path.relative_to(corpus_root).as_posix(),
        )
        for path in paths:
            relative = path.relative_to(corpus_root).as_posix()
            info = archive.gettarinfo(str(path), arcname=relative)
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            info.mtime = 0
            if path.is_file():
                with path.open("rb") as handle:
                    archive.addfile(info, handle)
            else:
                archive.addfile(info)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as output:
        with gzip.GzipFile(filename="", mode="wb", fileobj=output, mtime=0, compresslevel=9) as zipped:
            zipped.write(tar_buffer.getvalue())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=REPO_ROOT / "data" / "ecg_corpus")
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "backend" / "tests" / "assets" / "ptb_ci_corpus.tar.gz",
    )
    args = parser.parse_args()
    source = args.source.resolve(strict=True)
    source_store = CaseStore(source / "corpus.db", read_only=True)
    source_waveforms = LocalWaveformStore(source / "waveforms")
    source_manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    case_ids = sorted(
        {case_id for values in REAL_ECGS_BY_SCENARIO.values() for case_id in values},
        key=int,
    )

    with tempfile.TemporaryDirectory(prefix="ecg-ci-corpus-") as temporary:
        corpus = Path(temporary)
        target_store = CaseStore(corpus / "corpus.db")
        target_waveforms = LocalWaveformStore(corpus / "waveforms")
        for case_id in case_ids:
            packet = source_store.get_packet(case_id)
            signal = source_waveforms.read(case_id)
            if packet is None or len(signal) != 12:
                raise RuntimeError(f"complete source packet/waveform missing for Clinical ECG {case_id}")
            target_store.upsert_case(sanitized_packet(packet))
            target_waveforms.write(case_id, signal)

        clinical = vetted_real_items(target_store.get_packet)
        if len(clinical) != len(case_ids):
            raise RuntimeError("CI subset no longer satisfies the complete Clinical bank contract")
        with target_store.connect() as conn:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.execute("VACUUM")
        for suffix in ("-wal", "-shm"):
            Path(f"{target_store.db_path}{suffix}").unlink(missing_ok=True)

        manifest = {
            "version": source_manifest.get("version"),
            "licenseContractVersion": source_manifest.get("licenseContractVersion"),
            "complete": True,
            "source": "ptbxl_clinical_ci_subset",
            "samplingFrequency": source_manifest.get("samplingFrequency", 100),
            "totalCases": len(case_ids),
            "built": len(case_ids),
            "studentFacing": target_store.student_facing_count(),
            "sourceCounts": target_store.source_counts(),
            "tierDistribution": target_store.tier_counts(),
            "conceptABCounts": target_store.concept_ab_counts(),
            "sourceCatalog": {
                key: value
                for key, value in (source_manifest.get("sourceCatalog") or {}).items()
                if key in {"ptbxl", "ptbxl-plus"}
            },
            "ciFixture": {
                "purpose": "clean-runner source tests only",
                "clinicalCaseCount": len(clinical),
                "patientIdentifiersRemoved": True,
                "productionCorpus": False,
            },
        }
        (corpus / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        write_deterministic_archive(corpus, args.output)

    digest = hashlib.sha256(args.output.read_bytes()).hexdigest()
    args.output.with_suffix(args.output.suffix + ".sha256").write_text(
        f"{digest}  {args.output.name}\n", encoding="ascii"
    )
    print(f"wrote {args.output} ({args.output.stat().st_size} bytes, {len(case_ids)} real ECGs)")


if __name__ == "__main__":
    main()
