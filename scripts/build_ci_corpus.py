#!/usr/bin/env python3
"""Build the deterministic, real-PTB corpus used by clean CI runners.

The asset contains every distinct PTB-XL ECG bound to the authored Clinical
bank, its authenticated longitudinal priors, and the governed Foundations
contrast pools. It is a source-test dependency, not the production corpus or a
substitute for the exhaustive release audit.
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

from app.clinical.real_items import (  # noqa: E402
    AUTHENTIC_LONGITUDINAL_PRIOR_BY_CURRENT,
    REAL_ECGS_BY_SCENARIO,
    vetted_real_items,
)
from app.foundations_case_pools import preferred_foundations_case_ids  # noqa: E402
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

FOUNDATIONS_CI_POOL_SLOTS = (
    "foundations:S5:component",
    "foundations:S10:modeled",
    "foundations:S11:guided",
    "foundations:S12:integration",
    "foundations:equivalent-retry",
)


def sanitized_packet(
    packet: dict,
    *,
    longitudinal_metadata: dict[str, str] | None = None,
) -> dict:
    cleaned = deepcopy(packet)
    identity = cleaned.get("record_identity") or {}
    for key in ("patientId", "recordingDate", "recordedAt"):
        identity.pop(key, None)
    provenance = cleaned.get("source_provenance") or {}
    for key in ("patientId", "recordingDate", "recordedAt"):
        provenance.pop(key, None)
    ptbxl = cleaned.get("ptbxl") or {}
    metadata = ptbxl.get("metadata") or {}
    ptbxl["metadata"] = {
        key: value for key, value in metadata.items() if key not in PRIVATE_METADATA_KEYS
    }
    nested_provenance = ptbxl.get("source_provenance") or {}
    for key in ("patientId", "recordingDate", "recordedAt"):
        nested_provenance.pop(key, None)
    if longitudinal_metadata is not None:
        # Clean CI must exercise the same fail-closed pair checks as production,
        # without committing a source patient id or acquisition date. These
        # fixture-scoped handles and timestamps encode only same-pair membership
        # and prior/current order; they are not derived from either source value.
        identity.update(longitudinal_metadata)
        provenance.update(longitudinal_metadata)
    return cleaned


def ci_longitudinal_metadata() -> dict[str, dict[str, str]]:
    members: dict[str, dict[str, str]] = {}
    for index, (current_id, prior_id) in enumerate(
        sorted(
            AUTHENTIC_LONGITUDINAL_PRIOR_BY_CURRENT.items(),
            key=lambda pair: int(pair[0]),
        ),
        start=1,
    ):
        pair_handle = f"ci-longitudinal-pair-{index:02d}"
        members[prior_id] = {
            "patientId": pair_handle,
            "recordedAt": f"2000-{index:02d}-01T00:00:00Z",
        }
        members[current_id] = {
            "patientId": pair_handle,
            "recordedAt": f"2000-{index:02d}-02T00:00:00Z",
        }
    return members


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
    clinical_case_ids = {
        case_id for values in REAL_ECGS_BY_SCENARIO.values() for case_id in values
    }
    comparison_case_ids = set(AUTHENTIC_LONGITUDINAL_PRIOR_BY_CURRENT.values())
    if clinical_case_ids & comparison_case_ids:
        raise RuntimeError("longitudinal prior ECGs must be distinct from served Clinical ECGs")
    foundations_case_ids = {
        case_id
        for slot in FOUNDATIONS_CI_POOL_SLOTS
        for case_id in (
            preferred_foundations_case_ids(
                slot,
                learner_id="ci-foundations-pool-audit",
                secret="ci-foundations-pool-audit",
            )
            or ()
        )
    }
    if len(foundations_case_ids) != 24:
        raise RuntimeError("CI subset must cover all 24 governed Foundations ECGs")
    case_ids = sorted(
        clinical_case_ids | comparison_case_ids | foundations_case_ids,
        key=int,
    )
    longitudinal_metadata = ci_longitudinal_metadata()
    if set(longitudinal_metadata) != (
        set(AUTHENTIC_LONGITUDINAL_PRIOR_BY_CURRENT) | comparison_case_ids
    ):
        raise RuntimeError("CI longitudinal metadata does not cover every pair member")

    with tempfile.TemporaryDirectory(prefix="ecg-ci-corpus-") as temporary:
        corpus = Path(temporary)
        target_store = CaseStore(corpus / "corpus.db")
        target_waveforms = LocalWaveformStore(corpus / "waveforms")
        for case_id in case_ids:
            packet = source_store.get_packet(case_id)
            signal = source_waveforms.read(case_id)
            if packet is None or len(signal) != 12:
                raise RuntimeError(f"complete source packet/waveform missing for Clinical ECG {case_id}")
            target_store.upsert_case(
                sanitized_packet(
                    packet,
                    longitudinal_metadata=longitudinal_metadata.get(case_id),
                )
            )
            target_waveforms.write(case_id, signal)

        clinical = vetted_real_items(target_store.get_packet)
        if len(clinical) != len(clinical_case_ids):
            raise RuntimeError("CI subset no longer satisfies the complete Clinical bank contract")
        longitudinal_pairs = {
            str(item.ecg_id): str(item.prior_ecg_id)
            for item in clinical
            if item.prior_ecg_id
        }
        if longitudinal_pairs != AUTHENTIC_LONGITUDINAL_PRIOR_BY_CURRENT:
            raise RuntimeError("CI subset no longer satisfies the longitudinal pair contract")
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
                "comparisonEcgCount": len(comparison_case_ids),
                "foundationsCaseCount": len(foundations_case_ids),
                "distinctRealEcgCount": len(case_ids),
                "longitudinalLinkage": "fixture-scoped opaque pair handles and synthetic order only",
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
