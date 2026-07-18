"""Inventory or build a gated STAFF III comparison-candidate release.

Dry-run inventory is the default. ``--apply`` writes a dedicated, offline
authoring artifact; it never mutates the runtime ECG corpus and never reads
Google Drive or PhysioNet at serve time.
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

from app.ingest.staff_iii import (  # noqa: E402
    DESCRIPTOR,
    EXTRACTION_VERSION,
    SOURCE_ID,
    SourceFrameQualityError,
    artifact_contains_raw_record_identity,
    build_episode_artifact,
    build_release_manifest,
    inventory_source,
    load_checksum_manifest,
    read_frame,
    select_episodes,
    source_record_names,
)
from app.store.waveform_store import LocalWaveformStore  # noqa: E402


DEFAULT_SOURCE_ROOT = os.getenv("STAFF_III_DATA_ROOT") or "data/raw/staffiii/1.0.0"


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
        description="Inventory STAFF III or build a review-required comparison artifact."
    )
    parser.add_argument("--source-root", default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--out", help="Dedicated output directory; required with --apply")
    parser.add_argument("--limit", type=int, default=0, help="Episode limit; 0 = all")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the dedicated candidate artifact. Default is read-only inventory.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.limit < 0:
        print("ERROR: --limit may not be negative", file=sys.stderr)
        return 2
    if args.apply and not args.out:
        print("ERROR: --out is required with --apply", file=sys.stderr)
        return 2

    source_root = _resolve(args.source_root)
    try:
        # A bounded selection needs only enough complete source protocols to
        # produce that bound. Full inventory (limit 0) still validates every
        # metadata-referenced header.
        inventory = inventory_source(
            source_root,
            # A small buffer covers source-declared lead-configuration
            # exclusions and patients with no complete triple.
            protocol_limit=(args.limit + 10 if args.limit else 0),
        )
        selected = select_episodes(inventory.episodes, limit=args.limit)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    payload = inventory.as_dict()
    payload["selectedEpisodeCount"] = len(selected)
    payload["selectedFrameCount"] = len(selected) * 3
    print(json.dumps(payload, indent=2, sort_keys=True))
    if not args.apply:
        return 0 if not inventory.errors else 1
    if inventory.errors:
        print("ERROR: source inventory has validation errors; no output written", file=sys.stderr)
        return 1
    if not selected:
        print("ERROR: no complete STAFF III episodes selected", file=sys.stderr)
        return 1

    output = _resolve(args.out)
    if output.exists() and any(output.iterdir()):
        print(
            "ERROR: output must be absent or empty; use a fresh staging directory",
            file=sys.stderr,
        )
        return 2
    output.mkdir(parents=True, exist_ok=True)
    state_path = output / ".staff-iii-import-state.json"
    _atomic_json(
        state_path,
        {
            "status": "in_progress",
            "sourceId": SOURCE_ID,
            "sourceVersion": DESCRIPTOR.version,
            "extractionVersion": EXTRACTION_VERSION,
            "selectedEpisodeCount": len(selected),
        },
    )

    checksums = load_checksum_manifest(source_root)
    waveforms = LocalWaveformStore(output / "waveforms")
    artifacts: list[dict[str, Any]] = []
    quality_exclusions: Counter[str] = Counter()
    try:
        for spec in selected:
            try:
                signals = {
                    frame.role: read_frame(source_root, frame, checksums)
                    for frame in spec.frames
                }
            except SourceFrameQualityError as exc:
                quality_exclusions[exc.reason] += 1
                continue
            artifact = build_episode_artifact(spec, signals)
            if artifact_contains_raw_record_identity(
                artifact, source_record_names(spec)
            ):
                raise RuntimeError("raw STAFF III record identity leaked into the public artifact")
            for frame in spec.frames:
                frame_id = f"{spec.episode_id}:{frame.role}"
                waveforms.write(frame_id, signals[frame.role])
            artifacts.append(artifact)
    except Exception as exc:
        _atomic_json(
            state_path,
            {
                "status": "failed",
                "sourceId": SOURCE_ID,
                "sourceVersion": DESCRIPTOR.version,
                "selectedEpisodeCount": len(selected),
                "completedEpisodeCount": len(artifacts),
                "errorType": type(exc).__name__,
            },
        )
        print(f"ERROR: {exc}; manifest.json remains absent", file=sys.stderr)
        return 1

    if not artifacts:
        _atomic_json(
            state_path,
            {
                "status": "failed",
                "sourceId": SOURCE_ID,
                "sourceVersion": DESCRIPTOR.version,
                "selectedEpisodeCount": len(selected),
                "completedEpisodeCount": 0,
                "qualityExclusionCounts": dict(quality_exclusions),
                "errorType": "NoUsableEpisodes",
            },
        )
        print("ERROR: every selected STAFF III episode failed waveform quality checks", file=sys.stderr)
        return 1

    _atomic_json(output / "comparison-episodes.json", {"episodes": artifacts})
    manifest = build_release_manifest(
        artifacts,
        source_candidate_episode_count=len(selected),
        quality_exclusion_counts=quality_exclusions,
    )
    _atomic_json(state_path, {**manifest, "status": "ready_to_publish"})
    # Readiness is written last. An interrupted build cannot look complete.
    _atomic_json(output / "manifest.json", manifest)
    print(
        f"Built {len(artifacts)} review-required STAFF III comparison episodes "
        f"({sum(quality_exclusions.values())} source-quality exclusions) -> {output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
