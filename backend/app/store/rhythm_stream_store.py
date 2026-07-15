"""Dedicated metadata store for source-verified long-form rhythm windows.

Rhythm-stream packets are deliberately separated from the 12-lead ``CaseStore``
so merely importing a telemetry/ambulatory source cannot make it selectable by
Training, Rapid, or Clinical routes.  A future reviewed lane must opt into this
store and re-check each packet's exact mode/subskill contract.
"""

from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Iterator

from ..ingest.source_contract import KNOWN_SOURCES


class RhythmStreamStore:
    def __init__(self, db_path: str | Path, *, read_only: bool = False):
        self.db_path = str(db_path)
        self.read_only = bool(read_only)
        if self.db_path == ":memory:" and self.read_only:
            raise ValueError("a read-only rhythm store requires a filesystem database")
        if self.db_path != ":memory:":
            path = Path(self.db_path)
            if self.read_only and not path.is_file():
                raise FileNotFoundError(path)
            if not self.read_only:
                path.parent.mkdir(parents=True, exist_ok=True)
        self._memory = (
            sqlite3.connect(":memory:", check_same_thread=False)
            if self.db_path == ":memory:"
            else None
        )
        if self._memory is not None:
            self._memory.row_factory = sqlite3.Row
        if self.read_only:
            self.validate_db()
        else:
            self.init_db()

    @contextmanager
    def connect(self):
        if self._memory is not None:
            yield self._memory
            self._memory.commit()
            return
        if self.read_only:
            uri = Path(self.db_path).resolve().as_uri() + "?mode=ro&immutable=1"
            conn = sqlite3.connect(uri, uri=True, timeout=10.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA query_only=ON")
            try:
                yield conn
            finally:
                conn.close()
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
                CREATE TABLE IF NOT EXISTS rhythm_windows (
                    window_id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    source_record_id TEXT NOT NULL,
                    parent_record_id TEXT NOT NULL,
                    patient_id TEXT NOT NULL,
                    source_version TEXT NOT NULL,
                    license_id TEXT NOT NULL,
                    rhythm_code TEXT NOT NULL,
                    canonical_rhythm_id TEXT NOT NULL,
                    start_sample INTEGER NOT NULL,
                    end_sample INTEGER NOT NULL,
                    sampling_frequency INTEGER NOT NULL,
                    signal_fingerprint TEXT NOT NULL UNIQUE,
                    packet_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_rhythm_source_record
                    ON rhythm_windows(source, parent_record_id, start_sample);
                CREATE INDEX IF NOT EXISTS idx_rhythm_canonical
                    ON rhythm_windows(canonical_rhythm_id, source);
                CREATE INDEX IF NOT EXISTS idx_rhythm_patient
                    ON rhythm_windows(source, patient_id);
                """
            )

    def validate_db(self) -> None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='rhythm_windows'"
            ).fetchone()
            if not row:
                raise ValueError("read-only rhythm database is missing rhythm_windows")
            columns = {
                value[1] for value in conn.execute("PRAGMA table_info(rhythm_windows)").fetchall()
            }
            required = {
                "window_id", "source", "source_record_id", "patient_id", "rhythm_code",
                "canonical_rhythm_id", "signal_fingerprint", "packet_json",
            }
            if not required.issubset(columns):
                raise ValueError("read-only rhythm database is missing required columns")

    def upsert(self, packet: dict[str, Any]) -> None:
        identity = packet.get("record_identity") or {}
        labels = packet.get("source_labels") or {}
        rhythm = labels.get("rhythm") if isinstance(labels, dict) else {}
        provenance = packet.get("source_provenance") or {}
        eligibility = packet.get("educational_eligibility") or {}
        waveform = packet.get("waveform") or {}
        source = str(packet.get("source") or "")
        descriptor = KNOWN_SOURCES.get(source)
        fingerprint = str(packet.get("signal_fingerprint") or "")
        if (
            not descriptor
            or descriptor.access != "open"
            or "rhythm_stream" not in descriptor.educational_uses
            or not all(
                isinstance(value, dict)
                for value in (identity, provenance, eligibility, waveform, rhythm)
            )
            or identity.get("sourceId") != source
            or provenance.get("sourceId") != source
            or str(identity.get("sourceVersion") or "") != descriptor.version
            or str(provenance.get("sourceVersion") or "") != descriptor.version
            or str(identity.get("licenseId") or "") != descriptor.license_id
            or str(provenance.get("licenseId") or "") != descriptor.license_id
            or str(provenance.get("labelAuthority") or "") != descriptor.label_authority
            or str(identity.get("patientId") or "") != str(provenance.get("patientId") or "")
            or str(packet.get("stream_window_id") or "")
            != f"{source}:{identity.get('sourceRecordId') or ''}"
            or str(eligibility.get("educationalUse") or "") != "rhythm_stream"
            or not re.fullmatch(r"[0-9a-f]{64}", fingerprint)
            or packet.get("current_student_serving_eligible") is not False
            or eligibility.get("currentRuntimeModeConnected") is not False
            or eligibility.get("clinicalManagementEligible") is not False
        ):
            raise ValueError(
                "rhythm packet must preserve its audited identity and remain disconnected/non-management"
            )
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO rhythm_windows (
                    window_id, source, source_record_id, parent_record_id, patient_id,
                    source_version, license_id, rhythm_code, canonical_rhythm_id,
                    start_sample, end_sample, sampling_frequency, signal_fingerprint, packet_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(window_id) DO UPDATE SET
                    source=excluded.source,
                    source_record_id=excluded.source_record_id,
                    parent_record_id=excluded.parent_record_id,
                    patient_id=excluded.patient_id,
                    source_version=excluded.source_version,
                    license_id=excluded.license_id,
                    rhythm_code=excluded.rhythm_code,
                    canonical_rhythm_id=excluded.canonical_rhythm_id,
                    start_sample=excluded.start_sample,
                    end_sample=excluded.end_sample,
                    sampling_frequency=excluded.sampling_frequency,
                    signal_fingerprint=excluded.signal_fingerprint,
                    packet_json=excluded.packet_json
                """,
                (
                    str(packet["stream_window_id"]),
                    source,
                    str(identity["sourceRecordId"]),
                    str(identity["parentRecordId"]),
                    str(identity["patientId"]),
                    str(identity["sourceVersion"]),
                    str(identity["licenseId"]),
                    str(rhythm["rhythmCode"]),
                    str(rhythm["canonicalRhythmId"]),
                    int(provenance["windowStartSample"]),
                    int(provenance["windowEndSample"]),
                    int(waveform["sampling_frequency"]),
                    fingerprint,
                    json.dumps(packet, sort_keys=True, separators=(",", ":")),
                ),
            )

    def exists(self, window_id: str) -> bool:
        with self.connect() as conn:
            return conn.execute(
                "SELECT 1 FROM rhythm_windows WHERE window_id=?", (window_id,)
            ).fetchone() is not None

    def get(self, window_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT packet_json FROM rhythm_windows WHERE window_id=?", (window_id,)
            ).fetchone()
        return json.loads(row["packet_json"]) if row else None

    def find_by_fingerprint(self, fingerprint: str) -> str | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT window_id FROM rhythm_windows WHERE signal_fingerprint=?", (fingerprint,)
            ).fetchone()
        return str(row["window_id"]) if row else None

    def count(self) -> int:
        with self.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM rhythm_windows").fetchone()[0])

    def rhythm_counts(self) -> dict[str, int]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT canonical_rhythm_id, COUNT(*) AS count FROM rhythm_windows "
                "GROUP BY canonical_rhythm_id ORDER BY canonical_rhythm_id"
            ).fetchall()
        return {str(row["canonical_rhythm_id"]): int(row["count"]) for row in rows}

    def source_counts(self) -> dict[str, int]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT source, COUNT(*) AS count FROM rhythm_windows GROUP BY source ORDER BY source"
            ).fetchall()
        return {str(row["source"]): int(row["count"]) for row in rows}

    def iter_packets(self) -> Iterator[dict[str, Any]]:
        with self.connect() as conn:
            cursor = conn.execute(
                "SELECT packet_json FROM rhythm_windows ORDER BY source, parent_record_id, start_sample"
            )
            for row in cursor:
                yield json.loads(row["packet_json"])
