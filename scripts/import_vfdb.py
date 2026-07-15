"""Inventory/import real VFDB rhythm windows into a dedicated gated store.

Dry-run inventory is the default.  ``--apply`` plus an explicit ``--out`` is
required for mutation.  This importer never writes the serving 12-lead corpus
and does not unlock Clinical/ACLS routes.

Examples:
  python scripts/import_vfdb.py --source-root data/raw/vfdb/1.0.0
  python scripts/import_vfdb.py --source-root data/raw/vfdb/1.0.0 --rhythm ventricular_fibrillation
  python scripts/import_vfdb.py --source-root data/raw/vfdb/1.0.0 --apply --out data/rhythm_streams/vfdb --limit 25
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.ingest.source_contract import source_catalog_entry  # noqa: E402
from app.ingest.vfdb import (  # noqa: E402
    DEFAULT_BOUNDARY_GUARD_SECONDS,
    DEFAULT_STRIDE_SECONDS,
    DESCRIPTOR,
    EXPECTED_RECORDS,
    EXTRACTION_VERSION,
    FUTURE_MODE_ID,
    RHYTHM_LABELS,
    SOURCE_ID,
    build_window_packet,
    inventory_source,
    read_window,
    select_windows,
)
from app.store.rhythm_stream_store import RhythmStreamStore  # noqa: E402
from app.store.waveform_store import LocalWaveformStore  # noqa: E402


DEFAULT_SOURCE_ROOT = os.getenv("VFDB_DATA_ROOT") or "data/raw/vfdb/1.0.0"
STATE_FILE = ".vfdb-import-state.json"


def _resolve(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)


def _begin_gated_import(output: Path, selection: dict[str, Any]) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    manifest_path = output / "manifest.json"
    state_path = output / STATE_FILE
    manifest = _read_json(manifest_path)
    state = _read_json(state_path)
    if manifest and (
        manifest.get("sourceId") != SOURCE_ID
        or manifest.get("sourceVersion") != DESCRIPTOR.version
    ):
        raise RuntimeError("output manifest belongs to another source/version")
    if (output / "rhythm_streams.db").exists() and not manifest and not state:
        raise RuntimeError(
            "output has a rhythm database but no manifest/import state; refusing to assume ownership"
        )
    if state and state.get("sourceId") not in {None, SOURCE_ID}:
        raise RuntimeError("output import state belongs to another source")
    if state.get("status") == "in_progress" and state.get("selection") != selection:
        raise RuntimeError("an interrupted import has a different selection; resume it before changing scope")
    started = {
        "status": "in_progress",
        "sourceId": SOURCE_ID,
        "sourceVersion": DESCRIPTOR.version,
        "extractionVersion": EXTRACTION_VERSION,
        "startedAt": state.get("startedAt") or datetime.now(UTC).isoformat(),
        "selection": selection,
        "priorManifest": manifest,
    }
    _atomic_json(state_path, started)
    if manifest_path.exists():
        manifest_path.unlink()
    return started


def _publish_manifest(
    output: Path,
    store: RhythmStreamStore,
    state: dict[str, Any],
    inventory_payload: dict[str, Any],
    run: dict[str, int],
    *,
    full_source_selection: bool,
) -> None:
    completed_at = datetime.now(UTC).isoformat()
    source_catalog = {
        **source_catalog_entry(SOURCE_ID),
        "eligibleModes": [FUTURE_MODE_ID],
        "eligibleSubskills": ["recognize", "discriminate"],
        "currentRuntimeConnected": False,
        "clinicalCaseEligible": False,
        "clinicalManagementEligible": False,
        "pulseOrPerfusionClaimsEligible": False,
        "treatmentOrActionSequenceEligible": False,
        "extractionVersion": EXTRACTION_VERSION,
    }
    manifest = {
        "formatVersion": 1,
        "sourceId": SOURCE_ID,
        "sourceVersion": DESCRIPTOR.version,
        "complete": True,
        "selectionComplete": True,
        "fullDatasetImported": bool(full_source_selection and store.count() == inventory_payload["eligibleWindowCount"]),
        "runtimeStatus": "foundation_only_not_connected",
        "database": "rhythm_streams.db",
        "waveformRoot": "waveforms",
        "totalWindows": store.count(),
        "sourceCounts": store.source_counts(),
        "canonicalRhythmCounts": store.rhythm_counts(),
        "sourceCatalog": {SOURCE_ID: source_catalog},
        "inventory": inventory_payload,
        "lastRun": run,
        "completedAt": completed_at,
        "requiredBeforeStudentUse": [
            "explicit reviewed Clinical resuscitation-rhythm route",
            "separate supplied pulse/perfusion/arrest-state context for any action question",
            "named clinician review of rhythm prompts and current algorithm content",
            "no action/mastery claim derived from this waveform source alone",
        ],
    }
    ready_state = {
        **state,
        "status": "ready_to_publish",
        "completedAt": completed_at,
        "run": run,
    }
    _atomic_json(output / STATE_FILE, ready_state)
    # Readiness gate is the final write.
    _atomic_json(output / "manifest.json", manifest)


def _parser() -> argparse.ArgumentParser:
    rhythms = sorted(
        {
            contract.canonical_rhythm_id
            for contract in RHYTHM_LABELS.values()
            if contract.canonical_rhythm_id
        }
    )
    parser = argparse.ArgumentParser(
        description="Dry-run inventory or import checksum-verified VFDB rhythm windows."
    )
    parser.add_argument("--source-root", default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--out", help="Dedicated rhythm-store directory; required with --apply")
    parser.add_argument("--record", action="append", help="Restrict to a source record (repeatable)")
    parser.add_argument(
        "--rhythm",
        action="append",
        choices=rhythms,
        help="Restrict to a canonical source rhythm (repeatable)",
    )
    parser.add_argument("--limit", type=int, default=0, help="Maximum windows; 0 = all")
    parser.add_argument(
        "--max-per-rhythm", type=int, default=0,
        help="Deterministic cap per canonical rhythm; 0 = no cap",
    )
    parser.add_argument("--stride-seconds", type=float, default=DEFAULT_STRIDE_SECONDS)
    parser.add_argument(
        "--boundary-guard-seconds", type=float, default=DEFAULT_BOUNDARY_GUARD_SECONDS
    )
    parser.add_argument("--progress-every", type=int, default=100)
    parser.add_argument(
        "--apply", action="store_true",
        help="Write the dedicated store. Without this flag the command is read-only.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.limit < 0 or args.max_per_rhythm < 0:
        print("ERROR: --limit and --max-per-rhythm may not be negative", file=sys.stderr)
        return 2
    if args.progress_every <= 0:
        print("ERROR: --progress-every must be positive", file=sys.stderr)
        return 2
    if args.apply and not args.out:
        print("ERROR: --out is required with --apply", file=sys.stderr)
        return 2

    source_root = _resolve(args.source_root)
    try:
        inventory = inventory_source(
            source_root,
            record_names=args.record,
            stride_seconds=args.stride_seconds,
            boundary_guard_seconds=args.boundary_guard_seconds,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    selected = select_windows(
        inventory.windows,
        canonical_rhythm_ids=set(args.rhythm or []) or None,
        limit=args.limit,
        max_per_rhythm=args.max_per_rhythm,
    )
    payload = inventory.as_dict()
    payload["selectedWindowCount"] = len(selected)
    payload["selectedCanonicalRhythmCounts"] = dict(
        sorted(Counter(item.canonical_rhythm_id for item in selected).items())
    )
    missing_selected = sorted(
        {item.record_name for item in selected} & set(inventory.missing_waveform_records), key=int
    )
    payload["selectedMissingWaveformRecords"] = missing_selected
    payload["parameters"] = {
        "records": args.record or "all",
        "rhythms": args.rhythm or "all eligible",
        "limit": args.limit,
        "maxPerRhythm": args.max_per_rhythm,
        "windowSeconds": 10.0,
        "strideSeconds": args.stride_seconds,
        "boundaryGuardSeconds": args.boundary_guard_seconds,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))

    if inventory.errors:
        print("ERROR: source inventory has failures; no writes attempted", file=sys.stderr)
        return 2
    if not args.apply:
        print("[vfdb] DRY RUN complete — no files were created or modified.")
        return 0
    if not selected:
        print("ERROR: no windows matched the selection; output was not modified", file=sys.stderr)
        return 2
    if missing_selected:
        print(
            "ERROR: selected records are missing checksum-listed .dat files: "
            + ", ".join(missing_selected),
            file=sys.stderr,
        )
        return 2

    output = _resolve(args.out)
    selection_state = {
        "sourceRoot": str(source_root),
        "selectedWindowIds": [item.case_id for item in selected],
        "parameters": payload["parameters"],
    }
    try:
        state = _begin_gated_import(output, selection_state)
    except Exception as exc:
        print(f"ERROR: cannot begin gated import: {exc}", file=sys.stderr)
        return 2

    store = RhythmStreamStore(output / "rhythm_streams.db")
    waveforms = LocalWaveformStore(output / "waveforms", leads=("ECG1", "ECG2"))
    run = {
        "selected": len(selected),
        "imported": 0,
        "skippedExisting": 0,
        "skippedDuplicate": 0,
        "errors": 0,
    }
    started = time.time()
    for index, spec in enumerate(selected, start=1):
        if store.exists(spec.case_id) and waveforms.exists(spec.case_id):
            run["skippedExisting"] += 1
            continue
        try:
            signal = read_window(source_root, spec)
            packet = build_window_packet(
                spec,
                signal,
                artifact_checksums=inventory.checksums_by_record[spec.record_name],
            )
            duplicate = store.find_by_fingerprint(packet["signal_fingerprint"])
            if duplicate and duplicate != spec.case_id:
                run["skippedDuplicate"] += 1
                print(f"[vfdb] duplicate waveform {spec.case_id} matches {duplicate}; not admitted")
                continue
            # Waveform first, metadata second. A partial write is rebuilt on resume.
            waveforms.write(spec.case_id, signal)
            store.upsert(packet)
            run["imported"] += 1
        except Exception as exc:
            run["errors"] += 1
            print(f"[vfdb] ERROR {spec.case_id}: {exc}", file=sys.stderr)
        if index % args.progress_every == 0:
            rate = index / max(1e-6, time.time() - started)
            print(
                f"[vfdb] processed={index}/{len(selected)} imported={run['imported']} "
                f"errors={run['errors']} ({rate:.1f}/s)"
            )
    if run["errors"]:
        print(
            f"ERROR: {run['errors']} window(s) failed. manifest.json remains absent; rerun to resume.",
            file=sys.stderr,
        )
        return 3

    full_selection = bool(
        not args.record
        and not args.rhythm
        and args.limit == 0
        and args.max_per_rhythm == 0
        and inventory.records_scanned == len(EXPECTED_RECORDS)
    )
    _publish_manifest(
        output,
        store,
        state,
        payload,
        run,
        full_source_selection=full_selection,
    )
    print(
        f"[vfdb] DONE imported={run['imported']} existing={run['skippedExisting']} "
        f"duplicates={run['skippedDuplicate']} total={store.count()} "
        f"manifest written last -> {output / 'manifest.json'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
