"""Inventory or import stable Leipzig expert-rhythm windows into a corpus.

Dry-run inventory is the default and performs no corpus writes.  ``--apply`` is
required to mutate a specified corpus.  A complete manifest is removed before
the first corpus mutation and rewritten atomically only after every selected
window succeeds, so runtime selection remains fail-closed during an interrupted
or partial import.

Examples:
  python scripts/import_leipzig.py
  python scripts/import_leipzig.py --record x100 --concept wide_complex_tachycardia
  python scripts/import_leipzig.py --apply --corpus data/ecg_corpus --limit 25
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

from app.ingest.leipzig import (  # noqa: E402
    DEFAULT_BOUNDARY_GUARD_SECONDS,
    DEFAULT_STRIDE_SECONDS,
    DESCRIPTOR,
    EXTRACTION_VERSION,
    RHYTHM_TO_CONCEPT,
    SOURCE_ID,
    build_window_packet,
    inventory_source,
    load_subject_metadata,
    read_surface_window,
    select_windows,
)
from app.ingest.source_contract import source_catalog_entry  # noqa: E402
from app.store import CaseStore, LocalWaveformStore  # noqa: E402


DEFAULT_SOURCE_ROOT = os.getenv("LEIPZIG_ECG_DATA_ROOT") or "data/raw/leipzig-heart-center-ecg/1.0.0"
STATE_FILE = ".leipzig-import-state.json"


def _resolve(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else ROOT / path


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temp, path)


def _begin_gated_import(corpus: Path, selection: dict[str, Any]) -> dict[str, Any]:
    """Persist resumability state, then remove the runtime readiness gate."""

    corpus.mkdir(parents=True, exist_ok=True)
    manifest_path = corpus / "manifest.json"
    state_path = corpus / STATE_FILE
    current_manifest = _read_json(manifest_path)
    prior_state = _read_json(state_path)
    if current_manifest and not current_manifest.get("complete"):
        raise RuntimeError("target corpus manifest is incomplete; finish that build before importing Leipzig")
    if (corpus / "corpus.db").exists() and not current_manifest and not prior_state:
        raise RuntimeError(
            "target corpus has a database but no complete manifest or Leipzig resume state; refusing to assume ownership"
        )
    if prior_state and prior_state.get("sourceId") not in {None, SOURCE_ID}:
        raise RuntimeError("target corpus has an in-progress state owned by another source importer")
    base_manifest = current_manifest or (prior_state.get("baseManifest") if isinstance(prior_state.get("baseManifest"), dict) else {})
    state = {
        "status": "in_progress",
        "sourceId": SOURCE_ID,
        "sourceVersion": DESCRIPTOR.version,
        "extractionVersion": EXTRACTION_VERSION,
        "startedAt": datetime.now(UTC).isoformat(),
        "selection": selection,
        "baseManifest": base_manifest,
    }
    _atomic_json(state_path, state)
    if manifest_path.exists():
        manifest_path.unlink()
    return state


def _source_counts(store: CaseStore) -> dict[str, int]:
    with store.connect() as conn:
        rows = conn.execute("SELECT source, COUNT(*) AS count FROM cases GROUP BY source ORDER BY source").fetchall()
    return {str(row["source"]): int(row["count"]) for row in rows}


def _duplicate_case_id(store: CaseStore, fingerprint: str, case_id: str) -> str | None:
    with store.connect() as conn:
        row = conn.execute(
            "SELECT ecg_id FROM cases WHERE signal_fingerprint = ? AND ecg_id <> ? LIMIT 1",
            (fingerprint, case_id),
        ).fetchone()
    return str(row["ecg_id"]) if row else None


def _publish_manifest(
    corpus: Path,
    store: CaseStore,
    state: dict[str, Any],
    inventory_payload: dict[str, Any],
    run_stats: dict[str, int],
) -> None:
    """Write build state, then the complete runtime manifest as the final write."""

    base = dict(state.get("baseManifest") or {})
    # Runtime provenance must be portable and safe to publish. Local Drive,
    # mount, and staging paths belong only in the ignored resumability state.
    for private_key in ("ptbxlDataRoot", "ptbxlPlusDataRoot", "sourceRoot", "stagingRoot"):
        base.pop(private_key, None)
    catalog = dict(base.get("sourceCatalog") or {}) if isinstance(base.get("sourceCatalog"), dict) else {}
    source_counts = base.get("sourceCounts") if isinstance(base.get("sourceCounts"), dict) else {}
    has_ptbxl = bool(
        "ptbxl" in catalog
        or int((source_counts or {}).get("ptbxl") or 0) > 0
    )
    if has_ptbxl:
        # Overwrite legacy catalog rows as well as missing rows: manifests built
        # before license-contract v2 incorrectly labelled PTB-XL as ODC-By.
        catalog["ptbxl"] = source_catalog_entry("ptbxl")
        catalog["ptbxl-plus"] = source_catalog_entry("ptbxl-plus")
    catalog[SOURCE_ID] = {
        **source_catalog_entry(SOURCE_ID),
        "eligibleModes": ["training", "rapid"],
        "clinicalCaseEligible": False,
        "clinicalManagementEligible": False,
        "extractionVersion": EXTRACTION_VERSION,
    }

    completed_at = datetime.now(UTC).isoformat()
    manifest = {
        **base,
        "version": max(5, int(base.get("version") or 0)),
        "licenseContractVersion": 2,
        "source": "multi_source_ecg_corpus",
        "complete": True,
        "totalCases": store.count(),
        "studentFacing": store.student_facing_count(),
        "tierDistribution": store.tier_counts(),
        "conceptABCounts": dict(sorted(store.concept_ab_counts().items(), key=lambda item: -item[1])),
        "samplingFrequency": 100,
        "sourceCounts": _source_counts(store),
        "sourceCatalog": catalog,
        "lastImport": {
            "sourceId": SOURCE_ID,
            "sourceVersion": DESCRIPTOR.version,
            "extractionVersion": EXTRACTION_VERSION,
            "completedAt": completed_at,
            "inventory": inventory_payload,
            "run": run_stats,
        },
    }
    state_path = corpus / STATE_FILE
    ready_state = {
        **state,
        "status": "ready_to_publish",
        "completedAt": completed_at,
        "run": run_stats,
    }
    _atomic_json(state_path, ready_state)
    # Runtime readiness is the final corpus mutation.
    _atomic_json(corpus / "manifest.json", manifest)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Dry-run inventory (default) or import stable Leipzig expert-rhythm windows."
    )
    parser.add_argument("--source-root", default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--corpus", help="Target corpus directory; required with --apply")
    parser.add_argument("--record", action="append", help="Restrict to a WFDB record (repeatable)")
    parser.add_argument(
        "--concept",
        action="append",
        choices=sorted(set(RHYTHM_TO_CONCEPT.values())),
        help="Restrict to one canonical concept (repeatable)",
    )
    parser.add_argument("--limit", type=int, default=0, help="Maximum selected windows; 0 = all")
    parser.add_argument(
        "--max-per-concept", type=int, default=0,
        help="Deterministic cap per concept; 0 = no cap",
    )
    parser.add_argument("--stride-seconds", type=float, default=DEFAULT_STRIDE_SECONDS)
    parser.add_argument("--boundary-guard-seconds", type=float, default=DEFAULT_BOUNDARY_GUARD_SECONDS)
    parser.add_argument("--progress-every", type=int, default=100)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write the specified corpus. Without this flag the command is read-only.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.limit < 0 or args.max_per_concept < 0:
        print("ERROR: --limit and --max-per-concept may not be negative", file=sys.stderr)
        return 2
    if args.progress_every <= 0:
        print("ERROR: --progress-every must be positive", file=sys.stderr)
        return 2
    if args.apply and not args.corpus:
        print("ERROR: --corpus is required with --apply", file=sys.stderr)
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
        concept_ids=set(args.concept or []) or None,
        limit=args.limit,
        max_per_concept=args.max_per_concept,
    )
    payload = inventory.as_dict()
    payload["selectedWindowCount"] = len(selected)
    payload["selectedConceptCounts"] = dict(sorted(Counter(item.concept_id for item in selected).items()))
    missing_selected_records = sorted(
        {item.record_name for item in selected} & set(inventory.missing_waveform_records)
    )
    payload["selectedMissingWaveformRecords"] = missing_selected_records
    payload["selectedLocallyReadableWindowCount"] = sum(
        item.record_name not in set(inventory.missing_waveform_records) for item in selected
    )
    payload["parameters"] = {
        "records": args.record or "all",
        "concepts": args.concept or "all eligible",
        "limit": args.limit,
        "maxPerConcept": args.max_per_concept,
        "windowSeconds": 10.0,
        "strideSeconds": args.stride_seconds,
        "boundaryGuardSeconds": args.boundary_guard_seconds,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))

    if inventory.errors:
        print("ERROR: inventory has record failures; no corpus writes were attempted", file=sys.stderr)
        return 2
    if not args.apply:
        print("[leipzig] DRY RUN complete — no corpus files were created or modified.")
        return 0
    if not selected:
        print("ERROR: no windows matched the import selection; corpus was not modified", file=sys.stderr)
        return 2
    if missing_selected_records:
        print(
            "ERROR: selected records are missing local .dat waveform files: "
            + ", ".join(missing_selected_records)
            + ". Hydrate/sync those source files or narrow --record before applying. Corpus was not modified.",
            file=sys.stderr,
        )
        return 2

    corpus = _resolve(args.corpus)
    selection_state = {
        "sourceRoot": str(source_root),
        "selectedWindowCount": len(selected),
        "parameters": payload["parameters"],
    }
    try:
        state = _begin_gated_import(corpus, selection_state)
    except Exception as exc:
        print(f"ERROR: cannot begin gated import: {exc}", file=sys.stderr)
        return 2
    store = CaseStore(corpus / "corpus.db")
    waveforms = LocalWaveformStore(corpus / "waveforms")
    subject_metadata = load_subject_metadata(source_root)
    stats = {"selected": len(selected), "imported": 0, "skippedExisting": 0, "skippedDuplicate": 0, "errors": 0}
    started = time.time()

    for index, spec in enumerate(selected, start=1):
        if store.exists(spec.case_id) and waveforms.exists(spec.case_id):
            stats["skippedExisting"] += 1
            continue
        try:
            signal = read_surface_window(source_root, spec)
            packet = build_window_packet(
                spec,
                signal,
                source_subject_metadata=subject_metadata.get(spec.record_name),
            )
            duplicate = _duplicate_case_id(store, packet["signal_fingerprint"], spec.case_id)
            if duplicate:
                stats["skippedDuplicate"] += 1
                print(f"[leipzig] duplicate waveform {spec.case_id} matches {duplicate}; not admitted")
                continue
            # Waveform first, metadata second.  If interrupted between them, the
            # missing CaseStore row is rebuilt on the next resumable run.
            waveforms.write(spec.case_id, signal)
            store.upsert_case(packet)
            stats["imported"] += 1
        except Exception as exc:
            stats["errors"] += 1
            print(f"[leipzig] ERROR {spec.case_id}: {exc}", file=sys.stderr)
        if index % args.progress_every == 0:
            rate = index / max(1e-6, time.time() - started)
            print(f"[leipzig] processed={index}/{len(selected)} imported={stats['imported']} errors={stats['errors']} ({rate:.1f}/s)")

    if stats["errors"]:
        print(
            f"ERROR: import stopped with {stats['errors']} failed window(s). manifest.json remains absent; rerun to resume.",
            file=sys.stderr,
        )
        return 3

    _publish_manifest(corpus, store, state, payload, stats)
    print(
        f"[leipzig] DONE imported={stats['imported']} existing={stats['skippedExisting']} "
        f"duplicates={stats['skippedDuplicate']} total={store.count()} manifest written last -> {corpus / 'manifest.json'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
