"""Deployment-ready storage layer for the ECG corpus.

Separates concerns so the same code runs locally (cheap/free) and deploys cleanly:
- :class:`CaseStore` — case metadata + grounded packets in SQLite (Postgres-ready
  SQL behind a narrow interface), with concept/tier indexes for fast adaptive queries.
- :class:`WaveformStore` — compact per-record signal store (int16 microvolts),
  behind an interface that a future S3/GCS backend can implement without touching
  callers. No serve-time WFDB or Google Drive dependency.
"""

from .waveform_store import WaveformStore, LocalWaveformStore, waveform_fingerprint
from .case_store import CaseStore

__all__ = ["WaveformStore", "LocalWaveformStore", "waveform_fingerprint", "CaseStore"]
