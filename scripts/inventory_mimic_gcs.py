"""Audit MIMIC-ECG-EXT <-> private GCS waveform coverage without downloading signals.

Requires Application Default Credentials authorized for the named project and
bucket. Output is aggregate only; subject/study identifiers are never printed.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.ingest.mimic_gcs import iter_ext_joins  # noqa: E402


def _bucket_parts(prefix: str) -> tuple[str, str]:
    if not prefix.startswith("gs://"):
        raise ValueError("GCS prefix must start with gs://")
    bucket, _, path = prefix[5:].partition("/")
    return bucket, path.rstrip("/")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=os.getenv("MIMIC_ECG_GCS_PROJECT", ""))
    parser.add_argument("--prefix", default=os.getenv("MIMIC_ECG_GCS_PREFIX", ""))
    parser.add_argument("--labels", default=os.getenv("MIMIC_ECG_EXT_LABELS_CSV", ""))
    parser.add_argument("--limit", type=int, default=100, help="metadata joins to HEAD; 0 scans every label row")
    args = parser.parse_args()
    if not args.project or not args.prefix or not args.labels:
        parser.error("--project, --prefix, and --labels (or matching environment variables) are required")

    try:
        from google.cloud import storage
    except ImportError:
        print("Install backend/requirements-data.txt and configure Application Default Credentials.", file=sys.stderr)
        return 2

    bucket_name, base = _bucket_parts(args.prefix)
    client = storage.Client(project=args.project)
    bucket = client.bucket(bucket_name)
    checked = waveform_pairs = labels_with_icd = 0
    for join in iter_ext_joins(args.labels, args.prefix):
        if args.limit and checked >= args.limit:
            break
        checked += 1
        relative_header = join.gcs_header_uri.split(f"gs://{bucket_name}/", 1)[1]
        relative_signal = join.gcs_signal_uri.split(f"gs://{bucket_name}/", 1)[1]
        if bucket.blob(relative_header).exists(client) and bucket.blob(relative_signal).exists(client):
            waveform_pairs += 1
        if join.icd10_codes:
            labels_with_icd += 1

    print({
        "checked": checked,
        "waveformPairsPresent": waveform_pairs,
        "rowsWithEncounterIcd10": labels_with_icd,
        "morphologyEligible": 0,
        "learnerFacingEligible": 0,
        "project": args.project,
        "bucket": bucket_name,
        "prefixConfigured": bool(base),
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
