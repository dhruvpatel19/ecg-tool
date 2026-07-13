"""Ingestion tests against the REAL PTB-XL+ column names and behaviors.

These replace the prior normalization test that passed on fabricated column names
while the real normalizer extracted nothing (V1 audit finding).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.grading import _concepts_from_answer, _match_concepts
from app.schemas import StructuredInterpretation
from app.ingest.measurements import derive_signal_quality, extract_measurements
from app.ingest.statements import is_readable, readable_statements
from app.source_text import repair_utf8_mojibake
from app.store import CaseStore


def test_real_ptbxl_plus_columns_map_to_canonical_measurements() -> None:
    # Exact PTB-XL+ 12SL column names (the ones the old alias map missed).
    raw = {
        "QT_Int_Global": 400.0,
        "QT_IntCorr_Global": 431.0,  # QTc
        "PR_Int_Global": 162.0,
        "QRS_Dur_Global": 92.0,
        "HR_Ventr_Global": 68.0,
        "R_AxisFrontal_Global": 45.0,
        "R_Amp_V5": 2.4,
        "S_Amp_V1": -1.4,
        "R_Amp_aVL": 0.6,
        "S_Amp_V3": -1.5,
        "ST_Elev_V2": 0.2,
    }
    values = extract_measurements(raw)["values"]
    assert values["qtc_ms"] == 431.0
    assert values["qt_ms"] == 400.0
    assert values["pr_ms"] == 162.0
    assert values["qrs_ms"] == 92.0
    assert values["heart_rate"] == 68.0
    assert values["axis_deg"] == 45.0
    # Sokolow-Lyon = |S_V1| + max(R_V5,R_V6) in mV (amplitudes already mV).
    assert abs(values["sokolow_lyon_mv"] - 3.8) < 1e-6
    assert extract_measurements(raw)["per_lead_st_mv"]["V2"] == 0.2


def test_signal_quality_uses_real_noise_fields_not_validation_metadata() -> None:
    assert derive_signal_quality({"static_noise": " , I-V1,  "})["status"] == "borderline"
    assert derive_signal_quality({"burst_noise": "V2"})["status"] == "poor"
    assert derive_signal_quality({"electrodes_problems": "alles"})["status"] == "poor"
    assert derive_signal_quality({})["status"] == "acceptable"
    # Lack of a second opinion must NOT degrade signal quality (the audited bug).
    assert derive_signal_quality({"second_opinion": False, "validated_by_human": True})["status"] == "acceptable"


def test_teaching_points_are_readable_prose_not_repr_tuples() -> None:
    points = readable_statements({"NORM": 100.0, "LVOLT": 100.0, "SR": 100.0}, "sinus rhythm", {})
    assert points and all(is_readable(p) for p in points)
    assert not any(p.startswith("[(") for p in points)


def test_ptbxl_utf8_report_mojibake_is_repaired_without_hiding_source_text(tmp_path: Path) -> None:
    broken = "qt-verlÃ„ngerung nach Kardioversion"
    repaired = "qt-verlÄngerung nach Kardioversion"
    assert repair_utf8_mojibake(broken) == repaired
    assert repair_utf8_mojibake(repaired) == repaired
    assert readable_statements({}, broken, {}) == [f"PTB-XL report: {repaired}"]

    store = CaseStore(tmp_path / "source-text.sqlite3")
    store.upsert_case({
        "case_id": "encoding-1",
        "display_id": "PTB-XL encoding-1",
        "source": "ptbxl",
        "teaching_tier": "A",
        "supported_objectives": ["normal_ecg"],
        "concept_confidence": {"normal_ecg": {"tier": "A", "score": 0.9}},
        "ptbxl": {"report": broken, "fold": 1},
        "ptbxl_plus": {},
        "signal_quality": {"status": "acceptable"},
        "clinical_stem": "Encoding regression",
        "teaching_points": [f"PTB-XL report: {broken}"],
    })
    packet = store.get_packet("encoding-1")
    assert packet is not None
    assert packet["ptbxl"]["report"] == repaired
    assert packet["teaching_points"] == [f"PTB-XL report: {repaired}"]
    assert store.summaries("normal_ecg")[0]["report"] == repaired


def test_grading_word_boundary_and_negation() -> None:
    assert "myocardial_infarction" in _match_concepts("anterior MI present", None)
    # word boundary: must not fire on substrings of other words
    assert "myocardial_infarction" not in _match_concepts("examine the mild changes", None)
    # negation guard
    assert "myocardial_infarction" not in _match_concepts("no MI, otherwise normal", None)
    assert "st_elevation" not in _match_concepts("no ST elevation seen", None)
    assert "st_elevation" in _match_concepts("clear ST elevation in V2-V4", None)


def test_grading_is_field_aware() -> None:
    # "normal" in the RATE field must not register normal_ecg (the audited overcall)
    answer = StructuredInterpretation(rate="normal rate", rhythm="sinus")
    hits = _concepts_from_answer(answer, "")
    assert "normal_ecg" not in hits
    assert "sinus_rhythm" in hits
    # but "normal ECG" in synthesis legitimately registers it
    assert "normal_ecg" in _concepts_from_answer(StructuredInterpretation(synthesis="normal ecg"), "")


SMOKE_DB = Path("data/ecg_corpus_smoke/corpus.db")


@pytest.mark.skipif(not SMOKE_DB.exists(), reason="smoke corpus not built")
def test_corpus_packets_are_grounded_and_clean() -> None:
    from app.store import CaseStore

    store = CaseStore(str(SMOKE_DB))
    assert store.count() > 0
    checked_measurement = checked_roi = checked_median = checked_statement = False
    for ecg_id in list(store.iter_ids())[:60]:
        packet = store.get_packet(ecg_id)
        plus = packet["ptbxl_plus"]
        # teaching points never contain raw repr tuples
        assert all(is_readable(p) for p in packet.get("teaching_points", []))
        # PTB-XL+ statements are readable (independent 12SL/SNOMED source)
        assert all(is_readable(s) for s in plus.get("statements", []))
        if plus.get("statements"):
            checked_statement = True
        features = plus["features"]
        if "qtc_ms" in features:
            checked_measurement = True
            assert features["qtc_ms"] > 0
        rois = plus["fiducials"]["rois"]
        if rois:
            checked_roi = True
            # ROIs now span more than the old 3-lead set (territory coverage)
            assert len({r["lead"] for r in rois}) >= 6
        median = plus.get("median_beats", {})
        if median.get("available"):
            checked_median = True
            assert len(median["leads"]) == 12 and len(median["beats"]["II"]) > 0
    assert checked_measurement, "expected a corpus case with a QTc measurement"
    assert checked_roi, "expected a corpus case with parsed fiducial ROIs"
    assert checked_median, "expected a corpus case with a computed median beat"
    assert checked_statement, "expected a corpus case with readable PTB-XL+ statements"
