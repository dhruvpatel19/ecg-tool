"""Inventory/import reviewed dangerous-arrhythmia fragments into a gated store.

The output is intentionally disconnected from learner routes. It is a source
foundation for short MLII recognition/discrimination only, never an ACLS
management or treatment-answer source.
"""

from __future__ import annotations

import argparse
from collections import Counter
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
    RHYTHM_LABELS,
    SOURCE_ID,
    build_fragment_packet,
    build_release_manifest,
    inventory_source,
    read_fragment,
    select_fragments,
)
from app.store.rhythm_stream_store import RhythmStreamStore  # noqa: E402
from app.store.waveform_store import LocalWaveformStore  # noqa: E402


DEFAULT_SOURCE_ROOT = os.getenv("DANGEROUS_ARRHYTHMIA_DATA_ROOT") or (
    "data/external/ecg-fragment-high-risk-label-1.0.0/raw/"
    "ecg-fragment-database-for-the-exploration-of-dangerous-arrhythmia-1.0.0"
)


def _resolve(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inventory or stage reviewed single-lead dangerous-arrhythmia fragments."
    )
    parser.add_argument("--source-root", default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--out", help="Dedicated output directory; required with --apply")
    parser.add_argument(
        "--rhythm", action="append", choices=sorted(RHYTHM_LABELS), help="Repeatable source label"
    )
    parser.add_argument("--limit", type=int, default=0, help="Total fragment limit; 0 = all")
    parser.add_argument(
        "--max-per-rhythm", type=int, default=0, help="Per-label cap; 0 = no cap"
    )
    parser.add_argument(
        "--apply", action="store_true", help="Write a gated store. Default is read-only inventory."
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.limit < 0 or args.max_per_rhythm < 0:
        print("ERROR: limits may not be negative", file=sys.stderr)
        return 2
    if args.apply and not args.out:
        print("ERROR: --out is required with --apply", file=sys.stderr)
        return 2
    source_root = _resolve(args.source_root)
    try:
        inventory = inventory_source(source_root)
        selected = select_fragments(
            inventory.fragments,
            rhythm_codes=set(args.rhythm or ()) or None,
            limit=args.limit,
            max_per_rhythm=args.max_per_rhythm,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    payload = inventory.as_dict()
    payload["selectedFragmentCount"] = len(selected)
    payload["selectedRawLabelCounts"] = dict(
        sorted(Counter(item.rhythm_code for item in selected).items())
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    if not args.apply:
        return 0 if not inventory.errors else 1
    if inventory.errors:
        print("ERROR: source inventory has validation errors; no output written", file=sys.stderr)
        return 1
    if not selected:
        print("ERROR: no dangerous-arrhythmia fragments selected", file=sys.stderr)
        return 1

    output = _resolve(args.out)
    if output.exists() and any(output.iterdir()):
        print("ERROR: output must be absent or empty", file=sys.stderr)
        return 2
    output.mkdir(parents=True, exist_ok=True)
    state_path = output / ".dangerous-arrhythmia-import-state.json"
    _atomic_json(
        state_path,
        {
            "status": "in_progress",
            "sourceId": SOURCE_ID,
            "sourceVersion": DESCRIPTOR.version,
            "extractionVersion": EXTRACTION_VERSION,
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
            duplicate = store.find_by_fingerprint(packet["signal_fingerprint"])
            if duplicate and duplicate != packet["stream_window_id"]:
                continue
            store.upsert(packet)
            waveforms.write(packet["stream_window_id"], {"MLII": values})
            packets.append(packet)
    except Exception as exc:
        _atomic_json(
            state_path,
            {
                "status": "failed",
                "sourceId": SOURCE_ID,
                "sourceVersion": DESCRIPTOR.version,
                "completedFragmentCount": len(packets),
                "errorType": type(exc).__name__,
            },
        )
        print(f"ERROR: {exc}; manifest.json remains absent", file=sys.stderr)
        return 1

    manifest = build_release_manifest(packets)
    _atomic_json(state_path, {**manifest, "status": "ready_to_publish"})
    _atomic_json(output / "manifest.json", manifest)
    print(
        f"Built {manifest['fragmentCount']} gated rhythm-recognition fragments -> {output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
