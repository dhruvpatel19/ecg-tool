"""Build the deployment-ready ECG corpus from PTB-XL + PTB-XL+.

Reads the full corpus (or a bounded subset), grounds each case packet with real
measurements / readable statements / parsed fiducial ROIs / noise-based signal
quality, runs autonomous curation, and writes:

  <out>/corpus.db          SQLite case store (metadata + grounded packets + concept index)
  <out>/waveforms/         compact int16-microvolt signal store (~24 KB/record)
  <out>/manifest.json      build provenance + tier/concept distribution

Resumable: re-running skips cases already present (unless --rebuild).

Examples:
  python scripts/build_corpus.py --limit 300 --out data/ecg_corpus_smoke  # diagnostic, never published complete
  python scripts/build_corpus.py --limit 0 --out data/ecg_corpus      # full corpus
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import pandas as pd  # noqa: E402

from app.ingest.fiducials import DEFAULT_FIDUCIAL_LEADS  # noqa: E402
from app.ingest.measurements import LEADS  # noqa: E402
from app.ingest.pipeline import build_case_packet  # noqa: E402
from app.ingest.source_contract import source_catalog_entry  # noqa: E402
from app.ingest.statements import load_scp_reference, load_snomed_descriptions  # noqa: E402
from app.store import CaseStore, LocalWaveformStore, waveform_fingerprint  # noqa: E402

DEFAULT_PTBXL = os.getenv("PTBXL_DATA_ROOT") or "data/raw/ptb-xl/1.0.3"
DEFAULT_PLUS = os.getenv("PTBXL_PLUS_DATA_ROOT") or "data/raw/ptb-xl-plus/1.0.1"

# Only the columns the pipeline consumes (keeps the feature CSV loads small/fast).
NEEDED_12SL = [
    "HR_Ventr_Global", "HR__Global", "HR_Atrial_Global", "RR_Mean_Global",
    "QRS_Dur_Global", "QT_Int_Global", "QT_IntCorr_Global", "QT_IntBazett_Global",
    "QT_IntFridericia_Global", "PR_Int_Global", "PQ_Int_Global",
    "R_AxisFrontal_Global", "QRS_AxisFront_Global", "P_AxisFront_Global", "T_AxisFront_Global",
    "R_Amp_V1", "S_Amp_V1", "R_Amp_V5", "R_Amp_V6", "R_Amp_aVL", "S_Amp_V3",
]

REQUIRED_PTBXL_FILES = (
    Path("ptbxl_database.csv"),
    Path("scp_statements.csv"),
)
REQUIRED_PTBXL_PLUS_FILES = (
    Path("features/12sl_features.csv"),
    Path("features/ecgdeli_features.csv"),
    Path("labels/12sl_statements.csv"),
    Path("labels/snomed_description.csv"),
)


def _missing_required_inputs(
    ptbxl_root: Path,
    plus_root: Path,
    *,
    require_fiducials: bool,
) -> list[Path]:
    """Return release-critical source paths absent from this build input."""

    required = [*(ptbxl_root / item for item in REQUIRED_PTBXL_FILES)]
    required.extend(plus_root / item for item in REQUIRED_PTBXL_PLUS_FILES)
    if require_fiducials:
        required.append(plus_root / "fiducial_points" / "ecgdeli")
    return [path for path in required if not path.exists()]


def _release_completion_blockers(
    *,
    limit: int,
    scan_rows: int,
    errors: int,
    skipped: int,
    expected_ptbxl_rows: int,
    stored_ptbxl_rows: int,
    fiducials_enabled: bool,
) -> list[str]:
    """Explain why a build must remain non-selectable by the runtime."""

    blockers: list[str] = []
    if limit > 0:
        blockers.append(f"bounded --limit={limit}")
    if scan_rows > 0:
        blockers.append(f"bounded --scan-rows={scan_rows}")
    if errors:
        blockers.append(f"{errors} record error(s)")
    if skipped:
        blockers.append(f"{skipped} record(s) skipped")
    if not fiducials_enabled:
        blockers.append("PTB-XL+ fiducial ingestion disabled")
    if stored_ptbxl_rows != expected_ptbxl_rows:
        blockers.append(
            "PTB-XL row coverage mismatch "
            f"(stored={stored_ptbxl_rows}, expected={expected_ptbxl_rows})"
        )
    return blockers


def _load_features(path: Path, needed: list[str] | None, nrows: int | None) -> dict[int, dict]:
    if not path.exists():
        return {}
    header = pd.read_csv(path, nrows=0).columns.tolist()
    if needed is not None:
        usecols = ["ecg_id"] + [c for c in needed if c in header]
        if "ecg_id" not in header:
            usecols = None  # fall back to all columns
    else:
        usecols = None
    df = pd.read_csv(path, usecols=usecols, nrows=nrows)
    id_col = "ecg_id" if "ecg_id" in df.columns else df.columns[0]
    df = df.set_index(id_col)
    return {int(idx): row.dropna().to_dict() for idx, row in df.iterrows()}


def _read_signal(ptbxl_root: Path, filename_lr: str):
    import wfdb

    signal, fields = wfdb.rdsamp(str(ptbxl_root / filename_lr))
    names = {str(n).lower(): i for i, n in enumerate(fields.get("sig_name", []))}
    out: dict[str, list[float]] = {}
    for lead in LEADS:
        idx = names.get(lead.lower())
        if idx is not None:
            out[lead] = [round(float(signal[k][idx]), 4) for k in range(len(signal))]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the grounded ECG corpus store.")
    ap.add_argument("--ptbxl-root", default=DEFAULT_PTBXL)
    ap.add_argument("--plus-root", default=DEFAULT_PLUS)
    ap.add_argument("--out", default="data/ecg_corpus")
    ap.add_argument("--limit", type=int, default=0, help="0 = full corpus")
    ap.add_argument("--scan-rows", type=int, default=0, help="0 = all database rows")
    ap.add_argument("--fiducial-leads", default=",".join(DEFAULT_FIDUCIAL_LEADS),
                    help="comma list, or empty to skip fiducial ROI parsing")
    ap.add_argument("--rebuild", action="store_true", help="rebuild cases even if already present")
    ap.add_argument("--progress-every", type=int, default=100)
    args = ap.parse_args()
    if args.limit < 0 or args.scan_rows < 0:
        ap.error("--limit and --scan-rows must be non-negative")
    if args.progress_every < 1:
        ap.error("--progress-every must be positive")

    ptbxl_root = Path(args.ptbxl_root)
    plus_root = Path(args.plus_root)
    out = (ROOT / args.out) if not Path(args.out).is_absolute() else Path(args.out)
    # Build in place but gate selection on the manifest: delete any existing
    # manifest first so the live app does NOT serve this directory while it is
    # mid-build (corpus_repository requires manifest.complete == true). The manifest
    # is rewritten last, on success. This is robust on Windows/OneDrive where dir
    # rename/delete fails when a reader (e.g. the app) holds the SQLite handle.
    out.mkdir(parents=True, exist_ok=True)
    manifest_path = out / "manifest.json"
    if manifest_path.exists():
        manifest_path.unlink()
    fiducial_leads = [s.strip() for s in args.fiducial_leads.split(",") if s.strip()]

    missing_inputs = _missing_required_inputs(
        ptbxl_root,
        plus_root,
        require_fiducials=bool(fiducial_leads),
    )
    if missing_inputs:
        print(
            "ERROR: required PTB-XL/PTB-XL+ build inputs are missing:\n  - "
            + "\n  - ".join(str(path) for path in missing_inputs),
            file=sys.stderr,
        )
        return 2

    print(f"[corpus] PTB-XL={ptbxl_root}\n[corpus] PTB-XL+={plus_root}\n[corpus] out={out}")
    scp_ref = load_scp_reference(ptbxl_root / "scp_statements.csv")
    snomed_map = load_snomed_descriptions(plus_root / "labels" / "snomed_description.csv")
    nrows = args.scan_rows or None
    print("[corpus] loading PTB-XL+ feature tables (12sl globals + ecgdeli ST)...")
    f12 = _load_features(plus_root / "features" / "12sl_features.csv", NEEDED_12SL, nrows)
    st_cols = [f"ST_Elev_{ld}" for ld in LEADS]
    fed = _load_features(plus_root / "features" / "ecgdeli_features.csv", st_cols, nrows)
    # Independent PTB-XL+ 12SL diagnostic statements (SNOMED-coded) for concordance.
    stmt12 = _load_features(plus_root / "labels" / "12sl_statements.csv", ["statements_ext_snomed"], nrows)
    print(f"[corpus] 12sl rows={len(f12)} ecgdeli rows={len(fed)} 12sl-statements={len(stmt12)} snomed={len(snomed_map)}")

    store = CaseStore(out / "corpus.db")
    waveforms = LocalWaveformStore(out / "waveforms")

    # PTB-XL publishes this CSV as UTF-8. Reading it as CP-1252 corrupts German
    # report characters (for example, ``Ä`` becomes ``Ã„``) in every packet.
    db = pd.read_csv(ptbxl_root / "ptbxl_database.csv", nrows=nrows, encoding="utf-8-sig")
    built = skipped = errors = 0
    start = time.time()
    for _, row in db.iterrows():
        if args.limit and built >= args.limit:
            break
        rowd = row.to_dict()
        eid = int(rowd["ecg_id"])
        if not args.rebuild and store.exists(eid) and waveforms.exists(eid):
            continue
        filename = rowd.get("filename_lr")
        if not filename:
            skipped += 1
            continue
        try:
            signal = _read_signal(ptbxl_root, str(filename))
            if not signal:
                skipped += 1
                continue
            packet = build_case_packet(
                eid, rowd, scp_ref, f12.get(eid), fed.get(eid), signal,
                str(plus_root) if fiducial_leads else None, fiducial_leads or DEFAULT_FIDUCIAL_LEADS,
                plus_statements_snomed=(stmt12.get(eid) or {}).get("statements_ext_snomed"),
                snomed_map=snomed_map,
            )
            packet["signal_fingerprint"] = waveform_fingerprint(signal)
            waveforms.write(eid, signal)
            store.upsert_case(packet)
            built += 1
            if built % args.progress_every == 0:
                rate = built / max(1e-6, time.time() - start)
                print(f"[corpus] built={built} skipped={skipped} errors={errors} ({rate:.1f}/s)")
        except Exception as exc:  # keep going on a single bad record
            errors += 1
            if errors <= 10:
                print(f"[corpus] error ecg {eid}: {exc}", file=sys.stderr)

    tiers = store.tier_counts()
    concepts = store.concept_ab_counts()
    total = store.count()
    source_counts = store.source_counts()
    completion_blockers = _release_completion_blockers(
        limit=args.limit,
        scan_rows=args.scan_rows,
        errors=errors,
        skipped=skipped,
        expected_ptbxl_rows=len(db),
        stored_ptbxl_rows=int(source_counts.get("ptbxl") or 0),
        fiducials_enabled=bool(fiducial_leads),
    )
    if completion_blockers:
        print(
            "[corpus] INCOMPLETE: no selectable manifest was written: "
            + "; ".join(completion_blockers),
            file=sys.stderr,
        )
        return 1
    manifest = {
        "version": 5,
        "licenseContractVersion": 2,
        "source": "ptbxl_ptbxl_plus_corpus",
        "complete": True,  # written LAST; gates auto-selection (see corpus_repository)
        "built": built,
        "skipped": skipped,
        "errors": errors,
        "totalCases": total,
        "tierDistribution": tiers,
        "studentFacing": store.student_facing_count(),
        "sourceCounts": source_counts,
        "sourceCatalog": {
            "ptbxl": source_catalog_entry("ptbxl"),
            "ptbxl-plus": source_catalog_entry("ptbxl-plus"),
        },
        "samplingFrequency": 100,
        "conceptABCounts": dict(sorted(concepts.items(), key=lambda kv: -kv[1])),
        "fiducialLeads": fiducial_leads,
        "elapsedSec": round(time.time() - start, 1),
    }
    # Write the manifest LAST — this is the signal that makes the corpus selectable.
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"[corpus] DONE built={built} total={total} tiers={tiers} elapsed={manifest['elapsedSec']}s")
    print(f"[corpus] manifest written -> {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
