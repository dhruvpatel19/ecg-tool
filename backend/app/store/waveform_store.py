"""Compact, object-store-ready waveform storage.

Each record's 12-lead signal is stored as int16 microvolts (≈24 KB per 100 Hz /
10 s record), sharded by id like PTB-XL (``waveforms/01000/01234.npy``). The
``WaveformStore`` interface lets a future S3/GCS backend drop in without changing
the API layer; the local backend is used for development and cheap deployments.
"""

from __future__ import annotations

from pathlib import Path
import hashlib
import re
from typing import Mapping, Protocol, Sequence

import numpy as np

LEADS = ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]
_UV_PER_MV = 1000.0
_INT16_MAX = 32767


class WaveformStore(Protocol):
    def exists(self, ecg_id: str | int) -> bool: ...
    def write(self, ecg_id: str | int, signal_by_lead: Mapping[str, Sequence[float]]) -> None: ...
    def read(
        self, ecg_id: str | int, leads: Sequence[str] | None = None
    ) -> dict[str, list[float]]: ...


def _bucket(ecg_id: str | int) -> str:
    digits = "".join(ch for ch in str(ecg_id) if ch.isdigit())
    if not digits:
        return "00000"
    return f"{(int(digits) // 1000) * 1000:05d}"


def _padded(ecg_id: str | int) -> str:
    digits = "".join(ch for ch in str(ecg_id) if ch.isdigit())
    return f"{int(digits):05d}" if digits else str(ecg_id)


def waveform_fingerprint(signal_by_lead: Mapping[str, Sequence[float]]) -> str:
    """Stable content fingerprint for cross-dataset tracing deduplication."""
    digest = hashlib.sha256()
    for lead in LEADS:
        digest.update(lead.encode("ascii"))
        values = signal_by_lead.get(lead) or []
        arr = np.asarray(values, dtype=np.float64) * _UV_PER_MV
        normalized = np.clip(np.round(arr), -_INT16_MAX, _INT16_MAX).astype("<i2")
        digest.update(len(normalized).to_bytes(8, "little"))
        digest.update(normalized.tobytes())
    return digest.hexdigest()


def _namespaced_path(root: Path, ecg_id: str | int) -> Path:
    raw = str(ecg_id)
    # Preserve every existing PTB numeric path. New sources must use a namespaced
    # id such as ``mimic-iv-ecg:record`` and are stored collision-free.
    if raw.isdigit():
        return root / _bucket(raw) / f"{_padded(raw)}.npy"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    readable = re.sub(r"[^A-Za-z0-9._-]+", "_", raw).strip("._-")[:72] or "record"
    return root / f"ns-{digest[:2]}" / f"{readable}-{digest[:12]}.npy"


class LocalWaveformStore:
    """Local filesystem backend storing int16-microvolt ``.npy`` files."""

    def __init__(self, root: str | Path, leads: Sequence[str] = LEADS):
        self.root = Path(root)
        self.leads = list(leads)

    def _path(self, ecg_id: str | int) -> Path:
        return _namespaced_path(self.root, ecg_id)

    def path_for(self, ecg_id: str | int) -> Path:
        """Return the canonical on-disk path for release integrity tooling."""
        return self._path(ecg_id)

    def exists(self, ecg_id: str | int) -> bool:
        return self._path(ecg_id).exists()

    def write(self, ecg_id: str | int, signal_by_lead: Mapping[str, Sequence[float]]) -> None:
        lengths = [len(signal_by_lead.get(lead, [])) for lead in self.leads]
        n = max(lengths) if lengths else 0
        if n == 0:
            return
        matrix = np.zeros((n, len(self.leads)), dtype=np.int16)
        for col, lead in enumerate(self.leads):
            values = signal_by_lead.get(lead) or []
            arr = np.asarray(values, dtype=np.float64)[:n] * _UV_PER_MV
            arr = np.clip(np.round(arr), -_INT16_MAX, _INT16_MAX).astype(np.int16)
            matrix[: len(arr), col] = arr
        path = self._path(ecg_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        np.save(path, matrix, allow_pickle=False)

    def read(
        self, ecg_id: str | int, leads: Sequence[str] | None = None
    ) -> dict[str, list[float]]:
        path = self._path(ecg_id)
        if not path.exists():
            return {}
        matrix = np.load(path, allow_pickle=False)
        wanted = [lead for lead in (leads or self.leads) if lead in self.leads]
        out: dict[str, list[float]] = {}
        for lead in wanted:
            col = self.leads.index(lead)
            out[lead] = (matrix[:, col].astype(np.float64) / _UV_PER_MV).round(4).tolist()
        return out
