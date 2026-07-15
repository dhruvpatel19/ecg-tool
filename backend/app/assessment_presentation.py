"""Learner-safe presentation helpers for owner-bound ECG assessments.

Canonical corpus identifiers stay in durable assessment rows and grading
events.  These helpers create response-only copies whose ECG identity is the
opaque capability issued by the owning route.  Source storage coordinates are
removed as well: a hidden canonical id is not useful if a packet still exposes
the corresponding WFDB filename or object path.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


_ECG_REFERENCE_KEYS = {
    "caseId",
    "case_id",
    "ecgId",
    "ecg_id",
    "pendingCaseId",
    "feedbackCaseId",
}
_DISPLAY_KEYS = {"displayId", "display_id"}
_SOURCE_IDENTITY_KEYS = {
    "record_identity",
    "source_provenance",
    "patientId",
    "patient_id",
    "subjectId",
    "subject_id",
    "recordId",
    "record_id",
    "sourceRecordId",
    "source_record_id",
    "parentRecordId",
    "parent_record_id",
    "studyId",
    "study_id",
    "filename",
    "filename_lr",
    "filename_hr",
    "path",
    "record_path",
    "file_path",
    "data_path",
    "uri",
    "url",
    "gcs_uri",
    "source_uri",
    "signalFingerprint",
    "signal_fingerprint",
}


def assessment_display_id(mode: str, ordinal: int) -> str:
    """Return a useful label that contains no dataset or record identity."""

    normalized = "Training" if mode == "training" else "Rapid"
    return f"{normalized} ECG {max(1, int(ordinal)):04d}"


def _sanitize_identity(
    value: Any,
    *,
    case_reference: str,
    display_id: str,
) -> Any:
    if isinstance(value, list):
        return [
            _sanitize_identity(
                item,
                case_reference=case_reference,
                display_id=display_id,
            )
            for item in value
        ]
    if not isinstance(value, dict):
        return deepcopy(value)

    sanitized: dict[str, Any] = {}
    for key, item in value.items():
        if key in _SOURCE_IDENTITY_KEYS:
            continue
        if key in _ECG_REFERENCE_KEYS:
            sanitized[key] = case_reference
        elif key in _DISPLAY_KEYS:
            sanitized[key] = display_id
        else:
            sanitized[key] = _sanitize_identity(
                item,
                case_reference=case_reference,
                display_id=display_id,
            )
    return sanitized


def public_case_summary(
    summary: dict[str, Any], *, case_reference: str, display_id: str
) -> dict[str, Any]:
    """Copy a case summary while replacing every ECG identity field."""

    public = _sanitize_identity(
        summary, case_reference=case_reference, display_id=display_id
    )
    public["caseId"] = case_reference
    public["displayId"] = display_id
    return public


def public_case_packet(
    packet: dict[str, Any], *, case_reference: str, display_id: str
) -> dict[str, Any]:
    """Copy a packet without corpus ids or backing-storage coordinates."""

    public = _sanitize_identity(
        packet, case_reference=case_reference, display_id=display_id
    )
    public["case_id"] = case_reference
    public["display_id"] = display_id
    return public


def public_assessment_record(
    record: dict[str, Any], *, case_reference: str, display_id: str
) -> dict[str, Any]:
    """Copy an answer/result/summary and replace nested ECG identity fields."""

    return _sanitize_identity(
        record, case_reference=case_reference, display_id=display_id
    )


def public_waveform(
    waveform: dict[str, Any], *, case_reference: str
) -> dict[str, Any]:
    """Copy a waveform window and bind its identity to the public reference."""

    public = deepcopy(waveform)
    public["caseId"] = case_reference
    return public


__all__ = [
    "assessment_display_id",
    "public_assessment_record",
    "public_case_packet",
    "public_case_summary",
    "public_waveform",
]
