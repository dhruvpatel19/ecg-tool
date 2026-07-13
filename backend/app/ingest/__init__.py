"""PTB-XL / PTB-XL+ ingestion building blocks.

This package converts the raw PTB-XL and PTB-XL+ source files into the grounded
case-packet shape consumed by curation, grading, the tutor, and the frontend.

Design goals (driven by the V1 audit):
- Real PTB-XL+ measurements (QT, QTc, PR, axis, voltage, per-lead ST) are mapped
  from their actual ``*_Global`` / ``*_<lead>`` column names, not guessed aliases.
- Statements are rendered to human-readable teaching prose, never raw repr tuples.
- Fiducial ``.atr`` annotations are parsed into real lead-level ROIs so click-to-grade
  and grounded tutor highlighting actually work.
- Signal quality is derived from PTB-XL's real noise fields.

The same building blocks are reused by the corpus build script and by any
runtime raw-data loader, so the served data and the build pipeline never drift.
"""

from .measurements import extract_measurements, derive_signal_quality
from .statements import readable_statements, scp_descriptions, load_scp_reference
from .fiducials import parse_fiducials_to_rois

__all__ = [
    "extract_measurements",
    "derive_signal_quality",
    "readable_statements",
    "scp_descriptions",
    "load_scp_reference",
    "parse_fiducials_to_rois",
]
