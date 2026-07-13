from __future__ import annotations

import pytest
import sqlite3

from app.ingest.pipeline import build_case_packet
from app.ingest.source_contract import (
    KNOWN_SOURCES,
    SourceRecord,
    namespaced_case_id,
    source_catalog_entry,
    validate_source_record,
)
from app.ingest.mimic_gcs import gcs_uris, iter_ext_joins
from app.store import CaseStore, LocalWaveformStore, waveform_fingerprint


def _signal(scale: float = 1.0) -> dict[str, list[float]]:
    return {"I": [0.0, 0.1 * scale, -0.2 * scale], "II": [0.0, 0.2 * scale, -0.1 * scale]}


def test_namespaced_waveforms_with_same_numeric_record_do_not_collide(tmp_path) -> None:
    store = LocalWaveformStore(tmp_path)
    first = namespaced_case_id("ptbxl", "123")
    second = namespaced_case_id("mimic-iv-ecg", "123")
    store.write(first, _signal(1.0))
    store.write(second, _signal(2.0))
    assert store.read(first, ["I"])["I"] != store.read(second, ["I"])["I"]
    assert len(list(tmp_path.rglob("*.npy"))) == 2


def test_waveform_fingerprint_is_content_not_source_identity() -> None:
    assert waveform_fingerprint(_signal()) == waveform_fingerprint(_signal())
    assert waveform_fingerprint(_signal()) != waveform_fingerprint(_signal(2.0))


def test_admission_requires_patient_label_and_signal_contract() -> None:
    descriptor = KNOWN_SOURCES["ptbxl"]
    with pytest.raises(ValueError, match="patient identity"):
        validate_source_record(descriptor, SourceRecord("1", None, _signal(), 100, ("NORM",), "SCP"))
    validate_source_record(
        descriptor,
        SourceRecord("1", "patient-1", _signal(), 100, ("NORM",), "cardiologist SCP statement"),
    )


def test_official_source_license_contracts_are_version_specific() -> None:
    ptbxl = KNOWN_SOURCES["ptbxl"]
    ptbxl_plus = KNOWN_SOURCES["ptbxl-plus"]
    leipzig = KNOWN_SOURCES["leipzig-heart-center"]

    assert (ptbxl.version, ptbxl.license_id) == ("1.0.3", "CC-BY-4.0")
    assert (ptbxl_plus.version, ptbxl_plus.license_id) == ("1.0.1", "CC-BY-4.0")
    assert (leipzig.version, leipzig.license_id) == ("1.0.0", "ODC-BY-1.0")

    ptbxl_catalog = source_catalog_entry("ptbxl")
    plus_catalog = source_catalog_entry("ptbxl-plus")
    assert ptbxl_catalog["sourceUrl"] == "https://physionet.org/content/ptb-xl/1.0.3/"
    assert ptbxl_catalog["doi"] == "https://doi.org/10.13026/kfzx-aw45"
    assert plus_catalog["sourceUrl"] == "https://physionet.org/content/ptb-xl-plus/1.0.1/"
    assert plus_catalog["doi"] == "https://doi.org/10.13026/g6h6-7g88"


def test_ptb_packet_keeps_waveform_and_derived_evidence_provenance_distinct() -> None:
    packet = build_case_packet(
        42,
        {"patient_id": 7, "scp_codes": "{}", "report": "", "strat_fold": 1},
        {},
        None,
        None,
        None,
        None,
    )

    assert packet["record_identity"] == {
        "sourceId": "ptbxl",
        "sourceRecordId": "42",
        "patientId": "7",
        "sourceVersion": "1.0.3",
        "licenseId": "CC-BY-4.0",
    }
    assert packet["ptbxl"]["source_provenance"]["licenseId"] == "CC-BY-4.0"
    assert packet["ptbxl_plus"]["source_provenance"] == source_catalog_entry("ptbxl-plus")
    assert packet["source_provenance"]["derivedEvidenceSources"] == [
        source_catalog_entry("ptbxl-plus")
    ]


def test_case_store_rejects_cross_source_duplicate_signal_fingerprint(tmp_path) -> None:
    store = CaseStore(tmp_path / "corpus.db")
    fingerprint = waveform_fingerprint(_signal())

    def packet(case_id: str, source: str) -> dict:
        return {
            "case_id": case_id,
            "display_id": case_id,
            "source": source,
            "teaching_tier": "A",
            "ptbxl": {"fold": 0, "report": "normal"},
            "signal_quality": {"status": "acceptable"},
            "concept_confidence": {},
            "supported_objectives": [],
            "record_identity": {
                "sourceRecordId": "123",
                "patientId": f"{source}-patient",
                "sourceVersion": "1",
                "licenseId": "test",
            },
            "signal_fingerprint": fingerprint,
        }

    store.upsert_case(packet("ptbxl:123", "ptbxl"))
    with pytest.raises(sqlite3.IntegrityError):
        store.upsert_case(packet("mimic-iv-ecg:123", "mimic-iv-ecg"))


def test_mimic_ext_join_builds_a_placeholder_gcs_path_but_never_morphology_truth(tmp_path) -> None:
    prefix = "gs://example-private-bucket/mimic-iv-ecg-1.0/physionet.org/files/mimic-iv-ecg/1.0/files"
    file_name = (
        "mimic-iv-ecg-diagnostic-electrocardiogram-matched-subset-1.0/files/"
        "p0000/p00000000/s00000000/00000000"
    )
    header, signal = gcs_uris(file_name, prefix)
    assert signal == (
        "gs://example-private-bucket/mimic-iv-ecg-1.0/physionet.org/files/mimic-iv-ecg/1.0/files/"
        "p0000/p00000000/s00000000/00000000.dat"
    )
    assert header.endswith("00000000.hea")

    csv_path = tmp_path / "labels.csv"
    csv_path.write_text(
        "file_name,study_id,subject_id,all_diag_all\n"
        f'"{file_name}",00000000,00000000,"[\'I48\', \'R07\']"\n',
        encoding="utf-8",
    )
    joined = next(iter_ext_joins(csv_path, prefix))
    assert joined.icd10_codes == ("I48", "R07")
    assert joined.morphology_eligible is False
    assert joined.learner_facing_eligible is False
