"""MIMIC waveform/ECG-EXT join helpers (inventory only, never learner truth).

Waveforms and labels are deliberately separate. The GCS bucket may contain a
larger waveform inventory than the Drive mirror, while ECG-EXT supplies
credentialed encounter-linked ICD codes. ICD codes are clinical-context labels,
not proof of a morphology on a particular ECG, so this module never promotes
them to scored ECG concepts.
"""

from __future__ import annotations

import ast
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


@dataclass(frozen=True)
class MimicExtJoin:
    study_id: str
    subject_id: str
    waveform_stem: str
    gcs_header_uri: str
    gcs_signal_uri: str
    icd10_codes: tuple[str, ...]
    morphology_eligible: bool = False
    learner_facing_eligible: bool = False


def gcs_uris(file_name: str, gcs_prefix: str) -> tuple[str, str]:
    normalized = file_name.replace("\\", "/").strip("/")
    marker = "/files/"
    if marker not in normalized:
        raise ValueError("MIMIC file_name does not contain the expected /files/ segment")
    relative = normalized.split(marker, 1)[1]
    stem = f"{gcs_prefix.rstrip('/')}/{relative}"
    return f"{stem}.hea", f"{stem}.dat"


def _codes(raw: str) -> tuple[str, ...]:
    if not raw:
        return ()
    try:
        value = ast.literal_eval(raw)
    except (SyntaxError, ValueError):
        return ()
    return tuple(sorted({str(item) for item in value if item})) if isinstance(value, list) else ()


def iter_ext_joins(labels_csv: str | Path, gcs_prefix: str) -> Iterator[MimicExtJoin]:
    """Stream the ~800k-row join without loading the CSV into memory."""
    with Path(labels_csv).open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            header_uri, signal_uri = gcs_uris(row["file_name"], gcs_prefix)
            yield MimicExtJoin(
                study_id=str(row["study_id"]),
                subject_id=str(row["subject_id"]),
                waveform_stem=row["file_name"],
                gcs_header_uri=header_uri,
                gcs_signal_uri=signal_uri,
                icd10_codes=_codes(row.get("all_diag_all", "")),
            )

