"""SQLite-backed case store (Postgres-portable behind this narrow interface).

Holds one grounded case packet per ECG plus a ``case_concepts`` index so adaptive
selection and concept availability are index lookups, not full-corpus scans of
in-memory packets. The packet JSON excludes the raw signal (that lives in the
:class:`WaveformStore`), keeping rows small.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator

from ..source_text import repair_packet_source_text, repair_utf8_mojibake

STUDENT_TIERS = ("A", "B")


class CaseStore:
    def __init__(self, db_path: str | Path, *, read_only: bool = False):
        self.db_path = str(db_path)
        self.read_only = bool(read_only)
        if self.read_only and self.db_path == ":memory:":
            raise ValueError("A read-only case store requires a filesystem database")
        if self.db_path != ":memory:":
            if self.read_only:
                if not Path(self.db_path).is_file():
                    raise FileNotFoundError(self.db_path)
            else:
                Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._memory_conn = (
            sqlite3.connect(":memory:", check_same_thread=False) if self.db_path == ":memory:" else None
        )
        if self._memory_conn is not None:
            self._memory_conn.row_factory = sqlite3.Row
        if self.read_only:
            self.validate_db()
        else:
            self.init_db()

    @contextmanager
    def connect(self):
        if self._memory_conn is not None:
            yield self._memory_conn
            self._memory_conn.commit()
            return
        if self.read_only:
            # Immutable mode avoids SQLite sidecar/WAL writes and is appropriate
            # because a deployed corpus is versioned and replaced atomically,
            # never edited in place by the learner service.
            uri = Path(self.db_path).resolve().as_uri() + "?mode=ro&immutable=1"
            conn = sqlite3.connect(uri, uri=True, timeout=10.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA query_only=ON")
            try:
                yield conn
            finally:
                conn.close()
            return
        # busy_timeout so a build's writes and the app's reads of the same corpus.db
        # wait instead of raising "database is locked" (V1 audit fix).
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=10000")
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            pass
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def validate_db(self) -> None:
        """Fail closed if a mounted read-only corpus lacks its required schema."""
        with self.connect() as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' "
                    "AND name IN ('cases', 'case_concepts')"
                ).fetchall()
            }
            if tables != {"cases", "case_concepts"}:
                raise ValueError("Read-only corpus database is missing required tables")
            required = {"ecg_id", "packet_json", "teaching_tier", "source"}
            columns = {row[1] for row in conn.execute("PRAGMA table_info(cases)").fetchall()}
            if not required.issubset(columns):
                raise ValueError("Read-only corpus database is missing required case columns")

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS cases (
                    ecg_id TEXT PRIMARY KEY,
                    display_id TEXT,
                    source TEXT,
                    teaching_tier TEXT,
                    fold INTEGER,
                    report TEXT,
                    clinical_stem TEXT,
                    signal_status TEXT,
                    source_record_id TEXT,
                    patient_id TEXT,
                    source_version TEXT,
                    license_id TEXT,
                    signal_fingerprint TEXT,
                    supported_json TEXT NOT NULL DEFAULT '[]',
                    top_concepts_json TEXT NOT NULL DEFAULT '[]',
                    packet_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_cases_tier ON cases(teaching_tier);
                CREATE INDEX IF NOT EXISTS idx_cases_fold ON cases(fold);
                CREATE TABLE IF NOT EXISTS case_concepts (
                    ecg_id TEXT NOT NULL,
                    concept_id TEXT NOT NULL,
                    tier TEXT NOT NULL,
                    score REAL NOT NULL,
                    PRIMARY KEY (ecg_id, concept_id)
                );
                CREATE INDEX IF NOT EXISTS idx_concept_tier ON case_concepts(concept_id, tier);
                """
            )
            columns = {row[1] for row in conn.execute("PRAGMA table_info(cases)").fetchall()}
            for name in ("source_record_id", "patient_id", "source_version", "license_id", "signal_fingerprint"):
                if name not in columns:
                    conn.execute(f"ALTER TABLE cases ADD COLUMN {name} TEXT")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_cases_source_record ON cases(source, source_record_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_cases_patient ON cases(source, patient_id)")
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_cases_signal_fingerprint "
                "ON cases(signal_fingerprint) WHERE signal_fingerprint IS NOT NULL"
            )

    # --- writes -----------------------------------------------------------------

    def upsert_case(self, packet: dict[str, Any]) -> None:
        ecg_id = str(packet["case_id"])
        concept_confidence = packet.get("concept_confidence", {}) or {}
        supported = packet.get("supported_objectives", []) or []
        top = sorted(
            (
                {"id": cid, "tier": c.get("tier"), "score": c.get("score", 0)}
                for cid, c in concept_confidence.items()
                if c.get("tier") in STUDENT_TIERS
            ),
            key=lambda item: item["score"],
            reverse=True,
        )[:6]
        identity = packet.get("record_identity", {}) or {}
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO cases (ecg_id, display_id, source, teaching_tier, fold, report,
                    clinical_stem, signal_status, source_record_id, patient_id, source_version,
                    license_id, signal_fingerprint, supported_json, top_concepts_json, packet_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ecg_id) DO UPDATE SET
                    display_id=excluded.display_id, source=excluded.source,
                    teaching_tier=excluded.teaching_tier, fold=excluded.fold, report=excluded.report,
                    clinical_stem=excluded.clinical_stem, signal_status=excluded.signal_status,
                    source_record_id=excluded.source_record_id, patient_id=excluded.patient_id,
                    source_version=excluded.source_version, license_id=excluded.license_id,
                    signal_fingerprint=excluded.signal_fingerprint,
                    supported_json=excluded.supported_json, top_concepts_json=excluded.top_concepts_json,
                    packet_json=excluded.packet_json
                """,
                (
                    ecg_id,
                    packet.get("display_id", f"PTB-XL {ecg_id}"),
                    packet.get("source", "ptbxl"),
                    packet.get("teaching_tier", "C"),
                    int((packet.get("ptbxl", {}) or {}).get("fold") or 0),
                    (packet.get("ptbxl", {}) or {}).get("report", ""),
                    packet.get("clinical_stem", ""),
                    (packet.get("signal_quality", {}) or {}).get("status", "acceptable"),
                    identity.get("sourceRecordId", ecg_id),
                    identity.get("patientId"),
                    identity.get("sourceVersion"),
                    identity.get("licenseId"),
                    packet.get("signal_fingerprint"),
                    json.dumps(supported),
                    json.dumps(top),
                    json.dumps(packet),
                ),
            )
            conn.execute("DELETE FROM case_concepts WHERE ecg_id = ?", (ecg_id,))
            conn.executemany(
                "INSERT INTO case_concepts (ecg_id, concept_id, tier, score) VALUES (?, ?, ?, ?)",
                [
                    (ecg_id, cid, c.get("tier", "D"), float(c.get("score", 0)))
                    for cid, c in concept_confidence.items()
                ],
            )

    # --- reads ------------------------------------------------------------------

    def exists(self, ecg_id: str | int) -> bool:
        with self.connect() as conn:
            return conn.execute("SELECT 1 FROM cases WHERE ecg_id = ?", (str(ecg_id),)).fetchone() is not None

    def count(self) -> int:
        with self.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0])

    def tier_counts(self) -> dict[str, int]:
        with self.connect() as conn:
            rows = conn.execute("SELECT teaching_tier, COUNT(*) c FROM cases GROUP BY teaching_tier").fetchall()
        return {row["teaching_tier"]: row["c"] for row in rows}

    def student_facing_count(self) -> int:
        with self.connect() as conn:
            return int(
                conn.execute(
                    "SELECT COUNT(*) FROM cases WHERE teaching_tier IN ('A','B')"
                ).fetchone()[0]
            )

    def source_counts(self) -> dict[str, int]:
        """Exact case counts by source for release-manifest reconciliation."""
        with self.connect() as conn:
            rows = conn.execute("SELECT source, COUNT(*) c FROM cases GROUP BY source").fetchall()
        return {str(row["source"]): int(row["c"]) for row in rows}

    def student_source_counts(self) -> dict[str, int]:
        """Tier A/B counts by source, before the stricter packet-policy audit."""
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT source, COUNT(*) c FROM cases "
                "WHERE teaching_tier IN ('A','B') GROUP BY source"
            ).fetchall()
        return {str(row["source"]): int(row["c"]) for row in rows}

    def iter_student_packets(self) -> Iterator[dict[str, Any]]:
        """Stream every Tier A/B packet for the one-time deployment audit.

        The release corpus is immutable, so holding a read-only cursor during
        startup is safe and avoids materializing the full 22k-packet corpus in
        memory. Source-policy checks happen in the repository layer.
        """
        with self.connect() as conn:
            cursor = conn.execute(
                "SELECT packet_json FROM cases WHERE teaching_tier IN ('A','B')"
            )
            for row in cursor:
                yield json.loads(row["packet_json"])

    def get_packet(self, ecg_id: str | int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT packet_json FROM cases WHERE ecg_id = ?", (str(ecg_id),)).fetchone()
        return repair_packet_source_text(json.loads(row["packet_json"])) if row else None

    def concept_ab_counts(self) -> dict[str, int]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT concept_id, COUNT(*) c FROM case_concepts WHERE tier IN ('A','B') GROUP BY concept_id"
            ).fetchall()
        return {row["concept_id"]: row["c"] for row in rows}

    def distinct_case_count(self, concept_ids: list[str]) -> int:
        """Number of student-facing cases that are Tier A/B for ANY of these concepts."""
        if not concept_ids:
            return 0
        placeholders = ",".join("?" for _ in concept_ids)
        with self.connect() as conn:
            row = conn.execute(
                f"SELECT COUNT(DISTINCT ecg_id) FROM case_concepts "
                f"WHERE tier IN ('A','B') AND concept_id IN ({placeholders})",
                concept_ids,
            ).fetchone()
        return int(row[0])

    def candidates(self, concept_id: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
        """Lightweight rows for adaptive selection (no full-packet parse)."""
        sql = (
            "SELECT c.ecg_id, c.teaching_tier, c.source, c.report, c.supported_json"
            + (", cc.tier AS concept_tier, cc.score AS concept_score" if concept_id else "")
            + " FROM cases c"
        )
        params: list[Any] = []
        if concept_id:
            sql += " JOIN case_concepts cc ON cc.ecg_id = c.ecg_id AND cc.concept_id = ? AND cc.tier IN ('A','B')"
            params.append(concept_id)
        sql += " WHERE c.teaching_tier IN ('A','B')"
        if limit:
            sql += " LIMIT ?"
            params.append(limit)
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        out = []
        for row in rows:
            report = str(row["report"] or "").casefold()
            if concept_id == "right_bundle_branch_block" and (
                "linksschenkelblock" in report or "left bundle branch block" in report
            ):
                continue
            if concept_id == "left_bundle_branch_block" and (
                "rechtsschenkelblock" in report or "right bundle branch block" in report
            ):
                continue
            item = {
                "case_id": row["ecg_id"],
                "teaching_tier": row["teaching_tier"],
                "source": row["source"],
                "supported_objectives": json.loads(row["supported_json"]),
            }
            if concept_id:
                item["concept_tier"] = row["concept_tier"]
            out.append(item)
        return out

    def training_candidates(
        self,
        *,
        segment: str | None = None,
        leads: list[str] | None = None,
        measurement_key: str | None = None,
        truth_key: str | None = None,
    ) -> list[dict[str, Any]]:
        """Indexed Training rows without deserializing every full packet.

        SQLite's JSON engine evaluates the coordinate/measurement admission
        predicates in-process. Returning compact rows keeps a first visit to a
        21k-record corpus responsive; non-legacy source contracts are still
        checked from their full packets by the Training router.
        """
        for key in (measurement_key, truth_key):
            if key and not key.replace("_", "").isalnum():
                raise ValueError("Unsafe Training measurement key")
        leads = [str(lead) for lead in (leads or [])]

        def value_expr(key: str) -> str:
            return (
                f"COALESCE(json_extract(c.packet_json, '$.ptbxl_plus.measurements.{key}'), "
                f"json_extract(c.packet_json, '$.ptbxl_plus.features.{key}'))"
            )

        select = "SELECT c.ecg_id, c.teaching_tier, c.source, c.supported_json"
        select += f", {value_expr(truth_key)} AS training_truth_value" if truth_key else ", NULL AS training_truth_value"
        sql = select + " FROM cases c WHERE c.teaching_tier IN ('A','B') AND json_array_length(c.supported_json) > 0"
        params: list[Any] = []
        if measurement_key:
            sql += f" AND typeof({value_expr(measurement_key)}) IN ('integer','real')"
        if truth_key and truth_key != measurement_key:
            sql += f" AND typeof({value_expr(truth_key)}) IN ('integer','real')"
        if segment:
            sql += (
                " AND EXISTS (SELECT 1 FROM json_each(c.packet_json, '$.ptbxl_plus.fiducials.rois') r "
                "WHERE json_extract(r.value, '$.concept') = ?"
            )
            params.append(segment)
            if leads:
                sql += " AND json_extract(r.value, '$.lead') IN (" + ",".join("?" for _ in leads) + ")"
                params.extend(leads)
            sql += ")"
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [
            {
                "case_id": row["ecg_id"],
                "teaching_tier": row["teaching_tier"],
                "source": row["source"],
                "supported_objectives": json.loads(row["supported_json"]),
                "training_truth_value": row["training_truth_value"],
                "training_indexed": True,
            }
            for row in rows
        ]

    def summaries(
        self,
        concept: str | None = None,
        include_uncertain: bool = False,
        query: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        sql = "SELECT c.ecg_id, c.display_id, c.source, c.teaching_tier, c.clinical_stem, c.report, c.top_concepts_json FROM cases c"
        params: list[Any] = []
        where: list[str] = []
        if concept:
            sql += " JOIN case_concepts cc ON cc.ecg_id = c.ecg_id AND cc.concept_id = ? AND cc.tier IN ('A','B')"
            params.append(concept)
            if concept == "right_bundle_branch_block":
                where.append("LOWER(COALESCE(c.report, '')) NOT LIKE '%linksschenkelblock%' AND LOWER(COALESCE(c.report, '')) NOT LIKE '%left bundle branch block%'")
            elif concept == "left_bundle_branch_block":
                where.append("LOWER(COALESCE(c.report, '')) NOT LIKE '%rechtsschenkelblock%' AND LOWER(COALESCE(c.report, '')) NOT LIKE '%right bundle branch block%'")
        if not include_uncertain:
            where.append("c.teaching_tier IN ('A','B')")
        if query:
            where.append("(c.ecg_id LIKE ? OR LOWER(c.report) LIKE ?)")
            params.extend([f"%{query}%", f"%{query.lower()}%"])
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY CASE WHEN c.ecg_id GLOB '[0-9]*' THEN 0 ELSE 1 END, CAST(c.ecg_id AS INTEGER), c.ecg_id LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [
            {
                "caseId": row["ecg_id"],
                "displayId": row["display_id"],
                "source": row["source"],
                "teachingTier": row["teaching_tier"],
                "clinicalStem": row["clinical_stem"],
                "report": repair_utf8_mojibake(str(row["report"] or "")),
                "topConcepts": json.loads(row["top_concepts_json"]),
                "studentFacing": row["teaching_tier"] in STUDENT_TIERS,
            }
            for row in rows
        ]

    def iter_ids(self) -> Iterable[str]:
        with self.connect() as conn:
            for row in conn.execute("SELECT ecg_id FROM cases ORDER BY CAST(ecg_id AS INTEGER)").fetchall():
                yield row["ecg_id"]
