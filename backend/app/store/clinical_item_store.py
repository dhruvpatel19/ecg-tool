"""SQLite-backed store for Clinical Decisions items (the item bank).

Separate table from ``cases`` (the immutable grounding layer): items are an authored/
generated, many-per-ECG layer with their own validation lifecycle. Mirrors the
connection/`:memory:` handling of :class:`app.store.case_store.CaseStore`.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable

from ..clinical.item_reference import is_public_item_reference, public_item_reference
from ..clinical.schemas import ClinicalCaseItem


class ClinicalItemStore:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._memory_conn = (
            sqlite3.connect(":memory:", check_same_thread=False) if self.db_path == ":memory:" else None
        )
        if self._memory_conn is not None:
            self._memory_conn.row_factory = sqlite3.Row
        self.init_db()

    @contextmanager
    def connect(self):
        if self._memory_conn is not None:
            yield self._memory_conn
            self._memory_conn.commit()
            return
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

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS clinical_case_items (
                    item_id TEXT PRIMARY KEY,
                    ecg_id TEXT NOT NULL,
                    prior_ecg_id TEXT,
                    situation TEXT NOT NULL,
                    question_type TEXT NOT NULL,
                    acuity_tier TEXT NOT NULL,
                    tested_scope TEXT NOT NULL,
                    provenance TEXT NOT NULL,
                    validation_status TEXT NOT NULL DEFAULT 'draft',
                    item_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_cci_serve
                    ON clinical_case_items(situation, question_type, validation_status);
                CREATE INDEX IF NOT EXISTS idx_cci_ecg ON clinical_case_items(ecg_id);
                """
            )

    def upsert_item(self, item: ClinicalCaseItem) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO clinical_case_items (item_id, ecg_id, prior_ecg_id, situation,
                    question_type, acuity_tier, tested_scope, provenance, validation_status, item_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(item_id) DO UPDATE SET
                    ecg_id=excluded.ecg_id, prior_ecg_id=excluded.prior_ecg_id,
                    situation=excluded.situation, question_type=excluded.question_type,
                    acuity_tier=excluded.acuity_tier, tested_scope=excluded.tested_scope,
                    provenance=excluded.provenance, validation_status=excluded.validation_status,
                    item_json=excluded.item_json
                """,
                (
                    item.item_id, item.ecg_id, item.prior_ecg_id, item.situation,
                    item.question_type, item.acuity_tier, item.tested_scope,
                    item.provenance, item.validation_status, item.model_dump_json(),
                ),
            )

    def replace_items_atomically(self, items: Iterable[ClinicalCaseItem]) -> None:
        """Publish one complete code-defined bank in a single transaction.

        Readers keep seeing the prior committed bank until the swap commits;
        concurrent app workers serialize on ``BEGIN IMMEDIATE`` and can never
        expose the old clear-then-refill partial-bank window.
        """
        rows = list(items)
        ids = [item.item_id for item in rows]
        if len(ids) != len(set(ids)):
            raise ValueError("clinical replacement bank contains duplicate item ids")
        values = [
            (
                item.item_id, item.ecg_id, item.prior_ecg_id, item.situation,
                item.question_type, item.acuity_tier, item.tested_scope,
                item.provenance, item.validation_status, item.model_dump_json(),
            )
            for item in rows
        ]
        with self.connect() as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN IMMEDIATE")
            conn.executemany(
                """
                INSERT INTO clinical_case_items (item_id, ecg_id, prior_ecg_id, situation,
                    question_type, acuity_tier, tested_scope, provenance, validation_status, item_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(item_id) DO UPDATE SET
                    ecg_id=excluded.ecg_id, prior_ecg_id=excluded.prior_ecg_id,
                    situation=excluded.situation, question_type=excluded.question_type,
                    acuity_tier=excluded.acuity_tier, tested_scope=excluded.tested_scope,
                    provenance=excluded.provenance, validation_status=excluded.validation_status,
                    item_json=excluded.item_json
                """,
                values,
            )
            if ids:
                placeholders = ",".join("?" for _ in ids)
                conn.execute(
                    f"DELETE FROM clinical_case_items WHERE item_id NOT IN ({placeholders})",
                    ids,
                )
            else:
                conn.execute("DELETE FROM clinical_case_items")

    def get_item(self, item_id: str) -> ClinicalCaseItem | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT item_json FROM clinical_case_items WHERE item_id = ?", (item_id,)
            ).fetchone()
            if row is None and is_public_item_reference(item_id):
                # Public Clinical handles are keyed, one-way aliases.  Resolve
                # across the small reviewed bank without ever transporting the
                # diagnosis-bearing authoring id back to the learner.
                candidates = conn.execute(
                    "SELECT item_id, item_json FROM clinical_case_items"
                ).fetchall()
                row = next(
                    (
                        candidate
                        for candidate in candidates
                        if public_item_reference(str(candidate["item_id"])) == item_id
                    ),
                    None,
                )
        return ClinicalCaseItem.model_validate_json(row["item_json"]) if row else None

    def list_for_serving(
        self, situation: str | None = None, question_type: str | None = None, status: str = "harness_pass"
    ) -> list[ClinicalCaseItem]:
        sql = "SELECT item_json FROM clinical_case_items WHERE validation_status = ?"
        params: list = [status]
        if situation:
            sql += " AND situation = ?"
            params.append(situation)
        if question_type:
            sql += " AND question_type = ?"
            params.append(question_type)
        sql += " ORDER BY item_id"
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [ClinicalCaseItem.model_validate_json(r["item_json"]) for r in rows]

    def clear(self) -> None:
        """Drop all items (used to re-seed the code-defined v0 bank deterministically on boot)."""
        with self.connect() as conn:
            conn.execute("DELETE FROM clinical_case_items")

    def set_status(self, item_id: str, status: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE clinical_case_items SET validation_status = ? WHERE item_id = ?",
                (status, item_id),
            )

    def count_by_status(self) -> dict[str, int]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT validation_status, COUNT(*) c FROM clinical_case_items GROUP BY validation_status"
            ).fetchall()
        return {r["validation_status"]: r["c"] for r in rows}

    def coverage(self, status: str = "harness_pass") -> dict[str, dict[str, int]]:
        """Per-concept pool depth for the adaptive loop: how many items target each concept,
        and across how many DISTINCT ECGs (the real diversity ceiling — a struggling student
        should not see the same tracing twice). Concepts with thin coverage can't sustain repetition."""
        from collections import defaultdict

        agg: dict[str, dict] = defaultdict(lambda: {"items": 0, "ecgs": set()})
        for item in self.list_for_serving(status=status):
            for objective in {c.objective_id for c in item.evidence_manifest.ecg_supports}:
                agg[objective]["items"] += 1
                agg[objective]["ecgs"].add(item.ecg_id)
        return {k: {"items": v["items"], "distinctEcgs": len(v["ecgs"])} for k, v in sorted(agg.items())}

    def application_coverage(
        self, status: str = "harness_pass"
    ) -> dict[str, dict[str, dict[str, int]]]:
        """Exact formative application capacity by objective and Clinical lane.

        Generic ECG support is not enough for an ``apply_in_context`` handoff:
        the authored item must explicitly grade that objective's decision in the
        requested setting. Keeping this server-derived prevents links from
        advertising a globally present concept that the selected lane cannot serve.
        """
        from collections import defaultdict

        agg: dict[str, dict[str, dict]] = defaultdict(
            lambda: defaultdict(lambda: {"items": 0, "ecgs": set()})
        )
        for item in self.list_for_serving(status=status):
            for objective in set(item.application_objectives):
                agg[objective][item.situation]["items"] += 1
                agg[objective][item.situation]["ecgs"].add(item.ecg_id)
        return {
            objective: {
                lane: {
                    "items": values["items"],
                    "distinctEcgs": len(values["ecgs"]),
                }
                for lane, values in sorted(lanes.items())
            }
            for objective, lanes in sorted(agg.items())
        }

    def iter_items(self) -> Iterable[ClinicalCaseItem]:
        with self.connect() as conn:
            rows = conn.execute("SELECT item_json FROM clinical_case_items ORDER BY item_id").fetchall()
        for r in rows:
            yield ClinicalCaseItem.model_validate_json(r["item_json"])

    def release_readiness(self, minimum_cases: int) -> tuple[bool, str]:
        """Check that the atomically published learner bank remains complete.

        The authored bank's full provenance and deterministic harness run at
        application startup. This inexpensive probe detects later deletion,
        partial publication, duplicate ECG binding, invalid status, or synthetic
        identifier leakage in the durable learner database.
        """
        items = list(self.iter_items())
        if len(items) < int(minimum_cases):
            return False, "clinical_bank_below_release_minimum"
        if any(item.validation_status != "harness_pass" for item in items):
            return False, "clinical_bank_contains_unvalidated_item"
        ecg_ids = [str(item.ecg_id) for item in items]
        if len(ecg_ids) != len(set(ecg_ids)):
            return False, "clinical_bank_reuses_ecg"
        identifiers = [
            str(value).casefold()
            for item in items
            for value in (item.item_id, item.ecg_id, item.prior_ecg_id)
            if value
        ]
        if any(value.startswith(("fixture-", "seed-")) for value in identifiers):
            return False, "clinical_bank_contains_synthetic_identifier"
        return True, "ready"
