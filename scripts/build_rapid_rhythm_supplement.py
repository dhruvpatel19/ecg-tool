#!/usr/bin/env python3
"""Build the optional high-risk ventricular-rhythm supplement for Rapid.

The command is dry-run by default.  ``--apply`` writes a fresh, self-contained
supplement under an existing complete corpus and adds one checksum-pinned
reference to the corpus manifest as the final atomic step.  Raw Drive/source
files are read only and are never copied into the release.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.ingest.dangerous_arrhythmia import (  # noqa: E402
    DESCRIPTOR,
    EXTRACTION_VERSION,
    SOURCE_ID,
    build_fragment_packet,
    build_release_manifest,
    inventory_source,
    read_fragment,
    select_fragments,
)
from app.rapid_rhythm_supplement import (  # noqa: E402
    RUNTIME_MANIFEST_NAME,
    RUNTIME_MAPPING_VERSION,
    RUNTIME_TARGETS,
    RapidRhythmSupplement,
    SUPPLEMENT_DIRECTORY,
    build_runtime_manifest,
)
from app.store.rhythm_stream_store import RhythmStreamStore  # noqa: E402
from app.store.waveform_store import LocalWaveformStore  # noqa: E402


DEFAULT_SOURCE_ROOT = os.getenv("DANGEROUS_ARRHYTHMIA_DATA_ROOT") or (
    "data/external/ecg-fragment-high-risk-label-1.0.0/raw/"
    "ecg-fragment-database-for-the-exploration-of-dangerous-arrhythmia-1.0.0"
)
DEFAULT_CORPUS_ROOT = os.getenv("ECG_CORPUS_ROOT") or "data/ecg_corpus"


def _resolve(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _load_complete_corpus_manifest(corpus_root: Path) -> dict[str, Any]:
    manifest_path = corpus_root / "manifest.json"
    if not (corpus_root / "corpus.db").is_file() or not (corpus_root / "waveforms").is_dir():
        raise ValueError("corpus root must contain corpus.db and waveforms/")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("corpus manifest is unreadable") from exc
    if not isinstance(manifest, dict) or manifest.get("complete") is not True:
        raise ValueError("corpus manifest is not complete")
    if any(key in manifest for key in ("ptbxlDataRoot", "ptbxlPlusDataRoot", "sourceRoot")):
        raise ValueError("corpus manifest contains a private local source path")
    return manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a manifest-gated high-risk ventricular-rhythm supplement for Rapid."
    )
    parser.add_argument("--source-root", default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--corpus-root", default=DEFAULT_CORPUS_ROOT)
    parser.add_argument(
        "--max-per-source-label",
        type=int,
        default=0,
        help="Optional deterministic per-label cap; 0 retains every approved fragment.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write a fresh supplement and update the complete corpus manifest.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.max_per_source_label < 0:
        print("ERROR: --max-per-source-label may not be negative", file=sys.stderr)
        return 2
    source_root = _resolve(args.source_root)
    corpus_root = _resolve(args.corpus_root)
    try:
        corpus_manifest = _load_complete_corpus_manifest(corpus_root)
        inventory = inventory_source(source_root)
        selected = select_fragments(
            inventory.fragments,
            rhythm_codes=set(RUNTIME_TARGETS),
            max_per_rhythm=args.max_per_source_label,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if inventory.errors:
        print(
            json.dumps(
                {**inventory.as_dict(), "selectedFragmentCount": 0},
                indent=2,
                sort_keys=True,
            )
        )
        print("ERROR: source validation errors block the supplement", file=sys.stderr)
        return 1
    if not selected:
        print("ERROR: no reviewed high-risk ventricular rhythm fragments were selected", file=sys.stderr)
        return 1

    preview = {
        "sourceId": SOURCE_ID,
        "sourceVersion": DESCRIPTOR.version,
        "sourceExtractionVersion": EXTRACTION_VERSION,
        "mappingVersion": RUNTIME_MAPPING_VERSION,
        "selectedFragmentCount": len(selected),
        "selectedSourceLabelCounts": dict(
            sorted(Counter(spec.rhythm_code for spec in selected).items())
        ),
        "runtimeTargets": {
            code: target.objective_id for code, target in sorted(RUNTIME_TARGETS.items())
        },
        "clinicalManagementEligible": False,
        "shockabilityClassificationEligible": False,
        "actionQuestionsRequireSeparateAuthoredContext": True,
        "actionQuestionsFormativeOnly": True,
        "output": str(corpus_root / SUPPLEMENT_DIRECTORY),
    }
    print(json.dumps(preview, indent=2, sort_keys=True))
    if not args.apply:
        return 0

    output = corpus_root / SUPPLEMENT_DIRECTORY
    if output.exists() and any(output.iterdir()):
        print(
            "ERROR: supplement output must be absent or empty; publish a new corpus tree instead of mutating an active supplement",
            file=sys.stderr,
        )
        return 2
    output.mkdir(parents=True, exist_ok=True)
    state_path = output / ".build-state.json"
    _atomic_json(
        state_path,
        {
            "status": "in_progress",
            "sourceId": SOURCE_ID,
            "mappingVersion": RUNTIME_MAPPING_VERSION,
            "selectedFragmentCount": len(selected),
        },
    )
    store = RhythmStreamStore(output / "rhythm_streams.db")
    waveforms = LocalWaveformStore(output / "waveforms", leads=("MLII",))
    packets: list[dict[str, Any]] = []
    try:
        for spec in selected:
            values, header = read_fragment(source_root, spec)
            packet = build_fragment_packet(spec, values, header)
            serialized = json.dumps(packet, sort_keys=True)
            if spec.relative_record_path in serialized or spec.source_parent_record in serialized:
                raise RuntimeError("raw dangerous-arrhythmia source identity leaked into packet")
            duplicate = store.find_by_fingerprint(str(packet["signal_fingerprint"]))
            if duplicate and duplicate != packet["stream_window_id"]:
                continue
            store.upsert(packet)
            waveforms.write(packet["stream_window_id"], {"MLII": values})
            packets.append(packet)

        source_manifest = build_release_manifest(packets)
        source_manifest_path = output / "manifest.json"
        _atomic_json(source_manifest_path, source_manifest)
        runtime_manifest = build_runtime_manifest(
            source_manifest_path=source_manifest_path,
            packets=packets,
        )
        runtime_manifest_path = output / RUNTIME_MANIFEST_NAME
        _atomic_json(runtime_manifest_path, runtime_manifest)
        # Reopen through the exact production reader before advertising the
        # supplement from the parent manifest.
        verified = RapidRhythmSupplement(output)
        if verified.count != len(packets):
            raise RuntimeError("runtime verification count changed")
        supplement_reference = {
            "schemaVersion": 1,
            "path": SUPPLEMENT_DIRECTORY,
            "sourceId": SOURCE_ID,
            "runtimeScope": "rapid_emergency_rhythm",
            "mappingVersion": RUNTIME_MAPPING_VERSION,
            "fragmentCount": verified.count,
            "learnerTargetCounts": verified.target_counts,
            "runtimeManifestSha256": _sha256(runtime_manifest_path),
        }
        # Manifest update is last: an interrupted build is never selectable.
        updated_corpus_manifest = dict(corpus_manifest)
        updated_corpus_manifest["rapidRhythmSupplement"] = supplement_reference
        _atomic_json(corpus_root / "manifest.json", updated_corpus_manifest)
        if state_path.exists():
            state_path.unlink()
    except Exception as exc:
        _atomic_json(
            state_path,
            {
                "status": "failed",
                "sourceId": SOURCE_ID,
                "mappingVersion": RUNTIME_MAPPING_VERSION,
                "completedFragmentCount": len(packets),
                "errorType": type(exc).__name__,
            },
        )
        print(f"ERROR: {exc}; parent corpus manifest was not promoted", file=sys.stderr)
        return 1

    print(
        f"Built and promoted {len(packets)} Rapid emergency-rhythm fragments -> {output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
