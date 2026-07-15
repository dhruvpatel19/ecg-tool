from __future__ import annotations

import json

from app.assessment_presentation import (
    assessment_display_id,
    public_assessment_record,
    public_case_packet,
    public_case_summary,
    public_waveform,
)


REFERENCE = "ec_" + "a" * 43


def test_public_packet_deeply_removes_corpus_identity_without_mutating_source() -> None:
    packet = {
        "case_id": "ptbxl-01234",
        "display_id": "PTB-XL 01234",
        "source": "ptbxl",
        "waveform": {
            "path": "records500/01000/01234_hr",
            "filename_hr": "records500/01000/01234_hr",
            "samplingFrequency": 500,
        },
        "ptbxl": {
            "metadata": {
                "ecg_id": "ptbxl-01234",
                "patient_id": 987,
                "age": 64,
            }
        },
        "record_identity": {
            "sourceRecordId": "01234",
            "patientId": 987,
        },
        "source_provenance": {
            "recordName": "s01234_0001",
            "annotationFile": "s01234_0001.atr",
            "windowStartSample": 12000,
        },
        "signal_fingerprint": "sha256:external-matchable-signal",
        "nested": [{"caseId": "ptbxl-01234", "recordId": "01234"}],
    }

    public = public_case_packet(
        packet,
        case_reference=REFERENCE,
        display_id="Training ECG 0001",
    )
    encoded = json.dumps(public, sort_keys=True)

    assert packet["case_id"] == "ptbxl-01234"
    assert packet["waveform"]["path"] == "records500/01000/01234_hr"
    assert public["case_id"] == REFERENCE
    assert public["display_id"] == "Training ECG 0001"
    assert public["ptbxl"]["metadata"]["ecg_id"] == REFERENCE
    assert public["ptbxl"]["metadata"]["age"] == 64
    assert "record_identity" not in public
    assert "source_provenance" not in public
    for forbidden in (
        "ptbxl-01234",
        "PTB-XL 01234",
        "records500/01000/01234_hr",
        "patient_id",
        "recordId",
        "sourceRecordId",
        "external-matchable-signal",
        "s01234_0001",
    ):
        assert forbidden not in encoded


def test_all_public_helpers_preserve_only_the_opaque_reference() -> None:
    summary = public_case_summary(
        {"caseId": "raw-case", "displayId": "Raw display", "source": "ptbxl"},
        case_reference=REFERENCE,
        display_id="Rapid ECG 0007",
    )
    record = public_assessment_record(
        {
            "caseId": "raw-case",
            "grade": {"testedObjectiveManifest": {"caseId": "raw-case"}},
        },
        case_reference=REFERENCE,
        display_id="Rapid ECG 0007",
    )
    waveform = public_waveform(
        {"caseId": "raw-case", "samplingFrequency": 100, "leads": []},
        case_reference=REFERENCE,
    )

    assert summary["caseId"] == REFERENCE
    assert summary["displayId"] == "Rapid ECG 0007"
    assert record["caseId"] == REFERENCE
    assert record["grade"]["testedObjectiveManifest"]["caseId"] == REFERENCE
    assert waveform["caseId"] == REFERENCE
    assert "raw-case" not in json.dumps((summary, record, waveform))


def test_assessment_display_labels_are_source_neutral() -> None:
    assert assessment_display_id("training", 1) == "Training ECG 0001"
    assert assessment_display_id("rapid", 27) == "Rapid ECG 0027"
    assert "PTB" not in assessment_display_id("rapid", 27)
