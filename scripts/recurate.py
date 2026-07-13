"""Re-curate an already-built corpus.db in place from the stored packets.

The full packet (raw SCP codes, PTB-XL+ features, per-lead ST, statements, fiducials,
signal quality) is persisted in `cases.packet_json`, so curation can be re-run WITHOUT
re-reading WFDB from Drive — a minutes-long pass instead of a multi-hour rebuild. Used
when only `backend/app/curation.py` / `ontology.py` change.

    python scripts/recurate.py data/ecg_corpus
    python scripts/recurate.py data/ecg_corpus --sync-manifest-only
"""

from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.curation import curate_case  # noqa: E402
from app.store.case_store import STUDENT_TIERS  # noqa: E402


def _ab_counts(conn: sqlite3.Connection) -> Counter:
    rows = conn.execute(
        "SELECT concept_id, COUNT(*) c FROM case_concepts WHERE tier IN ('A','B') GROUP BY concept_id"
    ).fetchall()
    return Counter({r[0]: r[1] for r in rows})


def _sync_manifest(db_file: Path, conn: sqlite3.Connection) -> None:
    manifest_path = db_file.parent / "manifest.json"
    if not manifest_path.exists():
        return
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    tier_counts = dict(conn.execute("SELECT teaching_tier, COUNT(*) FROM cases GROUP BY teaching_tier").fetchall())
    total = int(conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0])
    concept_counts = dict(_ab_counts(conn))
    manifest.update(
        {
            "totalCases": total,
            "tierDistribution": tier_counts,
            "studentFacing": sum(int(tier_counts.get(tier, 0)) for tier in STUDENT_TIERS),
            "conceptABCounts": concept_counts,
            "lastRecuratedAt": datetime.now(UTC).isoformat(),
        }
    )
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"synchronized {manifest_path}")


def main(db_path: str, manifest_only: bool = False) -> None:
    target = Path(db_path)
    db_file = target / "corpus.db" if target.is_dir() else target
    conn = sqlite3.connect(db_file, timeout=30.0)
    conn.execute("PRAGMA busy_timeout=30000")
    if manifest_only:
        _sync_manifest(db_file, conn)
        conn.close()
        return
    before = _ab_counts(conn)
    before_tiers = Counter(dict(conn.execute("SELECT teaching_tier, COUNT(*) FROM cases GROUP BY teaching_tier").fetchall()))

    rows = conn.execute("SELECT ecg_id, packet_json FROM cases").fetchall()
    print(f"re-curating {len(rows)} cases in {db_file} ...")
    n = 0
    for ecg_id, pj in rows:
        packet = json.loads(pj)
        packet.update(curate_case(packet))
        cc = packet.get("concept_confidence", {}) or {}
        supported = packet.get("supported_objectives", []) or []
        top = sorted(
            ({"id": cid, "tier": c.get("tier"), "score": c.get("score", 0)}
             for cid, c in cc.items() if c.get("tier") in STUDENT_TIERS),
            key=lambda i: i["score"], reverse=True,
        )[:6]
        conn.execute(
            "UPDATE cases SET teaching_tier=?, signal_status=?, supported_json=?, top_concepts_json=?, packet_json=? WHERE ecg_id=?",
            (
                packet.get("teaching_tier", "C"),
                (packet.get("signal_quality", {}) or {}).get("status", "acceptable"),
                json.dumps(supported),
                json.dumps(top),
                json.dumps(packet),
                ecg_id,
            ),
        )
        conn.execute("DELETE FROM case_concepts WHERE ecg_id=?", (ecg_id,))
        conn.executemany(
            "INSERT INTO case_concepts (ecg_id, concept_id, tier, score) VALUES (?,?,?,?)",
            [(ecg_id, cid, c.get("tier", "D"), float(c.get("score", 0))) for cid, c in cc.items()],
        )
        n += 1
        if n % 5000 == 0:
            print(f"  ...{n}")
    conn.commit()
    after = _ab_counts(conn)
    after_tiers = Counter(dict(conn.execute("SELECT teaching_tier, COUNT(*) FROM cases GROUP BY teaching_tier").fetchall()))
    _sync_manifest(db_file, conn)
    conn.close()

    print(f"\nteaching_tier: before={dict(before_tiers)}  ->  after={dict(after_tiers)}")
    concepts = sorted(set(before) | set(after))
    print(f"\n{'concept':42}{'before':>8}{'after':>8}{'delta':>8}")
    for c in concepts:
        b, a = before.get(c, 0), after.get(c, 0)
        flag = "  <-- NEW" if b == 0 and a > 0 else ("  (lost)" if b > 0 and a == 0 else "")
        print(f"{c:42}{b:>8}{a:>8}{a-b:>+8}{flag}")


if __name__ == "__main__":
    args = [arg for arg in sys.argv[1:] if arg != "--sync-manifest-only"]
    main(args[0] if args else "data/ecg_corpus", manifest_only="--sync-manifest-only" in sys.argv)
