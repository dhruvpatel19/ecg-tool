"""Assemble a grounded case packet for one ECG from PTB-XL / PTB-XL+ sources.

Keeps the established packet shape (so curation, grading, the tutor, and the
frontend are unchanged) while fixing the *inputs*: real canonical measurements,
readable statements, noise-based signal quality, and parsed fiducial ROIs.
"""

from __future__ import annotations

import ast
import math
from typing import Any, Mapping, Sequence

from ..curation import curate_case
from ..source_text import repair_utf8_mojibake
from .fiducials import DEFAULT_FIDUCIAL_LEADS, parse_fiducials_to_rois
from .measurements import LEADS, derive_signal_quality, extract_measurements
from .source_contract import KNOWN_SOURCES, source_catalog_entry
from .statements import ptbxl_plus_statements, readable_statements, statement_texts


def _clean(value: Any) -> Any:
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def _parse_scp(value: Any) -> dict[str, float]:
    if isinstance(value, dict):
        return {str(k): float(v) for k, v in value.items()}
    if isinstance(value, str):
        try:
            parsed = ast.literal_eval(value)
            if isinstance(parsed, dict):
                return {str(k): float(v) for k, v in parsed.items()}
        except (ValueError, SyntaxError):
            return {}
    return {}


def _classes(scp_codes: Mapping[str, float], scp_ref: Mapping[str, dict[str, str]], field: str) -> list[str]:
    values = {
        scp_ref.get(code, {}).get(field, "")
        for code in scp_codes
    }
    return sorted(v for v in values if v)


def build_case_packet(
    ecg_id: str | int,
    db_row: Mapping[str, Any],
    scp_ref: Mapping[str, dict[str, str]],
    raw_12sl: Mapping[str, Any] | None,
    raw_ecgdeli: Mapping[str, Any] | None,
    signal_by_lead: Mapping[str, Sequence[float]] | None,
    plus_root: str | None,
    fiducial_leads: Sequence[str] = DEFAULT_FIDUCIAL_LEADS,
    plus_statements_snomed: str | None = None,
    snomed_map: Mapping[int, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    ecg_id = str(ecg_id)
    scp_codes = _parse_scp(db_row.get("scp_codes"))
    merged_raw: dict[str, Any] = {**(raw_ecgdeli or {}), **(raw_12sl or {})}
    meas = extract_measurements(merged_raw)

    features: dict[str, Any] = dict(meas["values"])
    for lead, st in meas["per_lead_st_mv"].items():
        features[f"st_elev_{lead}_mv"] = st

    # Independent PTB-XL+ (12SL) algorithmic statements, readable + provenance-tagged.
    plus_statements_detailed = ptbxl_plus_statements(plus_statements_snomed, snomed_map or {})
    plus_statements = statement_texts(plus_statements_detailed)
    # Student-facing teaching summary from PTB-XL SCP labels + report (kept separate).
    source_report = repair_utf8_mojibake(str(db_row.get("report") or "").strip())
    teaching_points = readable_statements(scp_codes, source_report, scp_ref)
    signal_quality = derive_signal_quality(db_row)

    fiducials = {"rois": [], "fiducials_by_lead": {}, "median": {}}
    if plus_root:
        fiducials = parse_fiducials_to_rois(
            plus_root, ecg_id, fiducial_leads, signal_by_lead, 100, meas["per_lead_st_mv"]
        )
    median = fiducials.get("median") or {}
    median_beats = (
        {
            "available": True,
            "samplingFrequency": 100,
            "durationMs": (len(next(iter(median.values()))) * 10) if median else 0,
            "leads": list(median.keys()),
            "beats": median,
            "source": "computed_from_waveform_at_fiducial_r_peaks",
        }
        if median
        else {"available": False}
    )

    metadata = {k: _clean(v) for k, v in db_row.items() if k not in {"scp_codes", "report"}}
    patient_id_value = _clean(db_row.get("patient_id"))
    patient_id = str(patient_id_value) if patient_id_value is not None else None
    ptbxl_descriptor = KNOWN_SOURCES["ptbxl"]
    ptbxl_provenance = source_catalog_entry("ptbxl")
    ptbxl_plus_provenance = source_catalog_entry("ptbxl-plus")

    packet: dict[str, Any] = {
        "case_id": ecg_id,
        "display_id": f"PTB-XL {ecg_id}",
        "clinical_stem": "PTB-XL educational ECG. Not for clinical diagnosis.",
        "waveform": {
            "path": None,
            "sampling_frequency": 100,
            "duration_sec": 10,
            "leads": list(LEADS),
            "source": "corpus_store",
        },
        "ptbxl": {
            "scp_codes": scp_codes,
            "diagnostic_superclass": _classes(scp_codes, scp_ref, "diagnostic_class"),
            "diagnostic_subclass": _classes(scp_codes, scp_ref, "diagnostic_subclass"),
            "report": source_report,
            "fold": int(_clean(db_row.get("strat_fold")) or 0),
            "metadata": metadata,
            "source_provenance": ptbxl_provenance,
        },
        "ptbxl_plus": {
            "statements": plus_statements,
            "statements_detailed": plus_statements_detailed,
            "statement_source": "ptbxl_plus_12sl_snomed",
            "features": features,
            "measurements": features,
            "fiducials": {
                "rois": fiducials.get("rois", []),
                "fiducials_by_lead": fiducials.get("fiducials_by_lead", {}),
            },
            "median_beats": median_beats,
            "feature_sources": meas["sources"],
            "per_lead_st_mv": meas["per_lead_st_mv"],
            "source_provenance": ptbxl_plus_provenance,
        },
        "record_identity": {
            "sourceId": "ptbxl",
            "sourceRecordId": ecg_id,
            "patientId": patient_id,
            "sourceVersion": ptbxl_descriptor.version,
            "licenseId": ptbxl_descriptor.license_id,
        },
        "source_provenance": {
            **ptbxl_provenance,
            "patientId": patient_id,
            "derivedEvidenceSources": [ptbxl_plus_provenance],
        },
        "signal_quality": signal_quality,
        "teaching_points": teaching_points,
        "source": "ptbxl",
    }
    packet.update(curate_case(packet))
    return packet
