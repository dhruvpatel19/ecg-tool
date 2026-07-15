from __future__ import annotations

import copy
import hashlib

import pytest

from app.ingest.source_contract import KNOWN_SOURCES, source_catalog_entry
from app.ingest.vfdb import (
    CHANNELS,
    CHECKSUM_MANIFEST_SHA256,
    FUTURE_MODE_ID,
    RHYTHM_LABELS,
    RhythmEpisode,
    WindowSpec,
    build_window_packet,
    parse_checksum_manifest,
    rhythm_waveform_fingerprint,
    segment_rhythm_episodes,
    stable_windows,
    validate_vfdb_header,
)
from app.store.rhythm_stream_store import RhythmStreamStore


# Byte-for-byte official PhysioNet VFDB 1.0.0 record 418 header.  Its checksum
# is published in that version's pinned SHA256SUMS.txt.  The decoded annotation
# rows below are the first five entries of the checksum-pinned 418.atr artifact
# (official SHA-256 55391c70...).  No source waveform is copied into the test
# suite and no test packet is connected to a learner route.
REAL_418_HEADER = (
    b"418 2 250 525000\r\n"
    b"418.dat 212 200 12 0 -128 1830 0 ECG\r\n"
    b"418.dat 212 200 12 0 -14 -5967 0 ECG\r\n"
)
REAL_418_HEADER_SHA256 = "339bca584735e83f1ce6ac555d8ba5d6489e39a915cdbf13b58c5329f5527a86"
REAL_418_ANNOTATION_SHA256 = "55391c70f16caa201b8e675ebdf4bc0405c03a4d861019f7a4cf4cc7f5d2a399"
REAL_418_SAMPLES = [18, 99_624, 101_499, 133_092, 134_038]
REAL_418_SYMBOLS = ["+", "+", "+", "+", "+"]
REAL_418_AUX = ["(N\x00", "(VFL\x00", "(N\x00", "(VFL\x00", "(N\x00"]

REAL_424_CHECKSUMS = {
    "424.hea": "f5877ea2f4f53087acf3e9cb2fd8bf0ad4a3aad3d45d544fbf3a04feed73c544",
    "424.atr": "60976184325ca61944d84b5c7bf75bec624a4f41543fa74fa2e41278b0a75a67",
    "424.dat": "b9b0dbeb0a7c939246a4884c955e74625422c55c39aacfd8d93f8ec9278470e9",
}


def _vfib_spec() -> WindowSpec:
    # Derived from the real 424.atr VFIB episode [314749, 341173).  The window
    # starts after the adapter's 0.5 s / 125-sample boundary guard.
    return WindowSpec(
        record_name="424",
        patient_id="424",
        sampling_frequency=250,
        start_sample=314_874,
        end_sample=317_374,
        episode_start_sample=314_749,
        episode_end_sample=341_173,
        annotation_index=1,
        raw_rhythm_aux="(VFIB\x00",
        rhythm_code="VFIB",
        canonical_rhythm_id="ventricular_fibrillation",
    )


def _shape_only_signal(scale: float = 1.0) -> dict[str, list[float]]:
    # Unit-test input for packet/storage shape and fingerprint determinism only.
    # Importable learner artifacts can be created only by the checksum-gated
    # offline importer reading a real .dat source file.
    return {
        "ECG1": [0.0] * 2_500,
        "ECG2": [round(((index % 7) - 3) * 0.001 * scale, 4) for index in range(2_500)],
    }


def test_real_418_header_and_annotation_fixture_preserve_source_boundaries(tmp_path) -> None:
    wfdb = pytest.importorskip("wfdb")
    header_path = tmp_path / "418.hea"
    header_path.write_bytes(REAL_418_HEADER)

    assert hashlib.sha256(REAL_418_HEADER).hexdigest() == REAL_418_HEADER_SHA256
    header = wfdb.rdheader(str(tmp_path / "418"))
    validate_vfdb_header(header, "418")

    episodes = segment_rhythm_episodes(
        REAL_418_SAMPLES,
        REAL_418_SYMBOLS,
        REAL_418_AUX,
        525_000,
    )
    assert [(item.rhythm_code, item.start_sample, item.end_sample) for item in episodes[:4]] == [
        ("N", 18, 99_624),
        ("VFL", 99_624, 101_499),
        ("N", 101_499, 133_092),
        ("VFL", 133_092, 134_038),
    ]
    assert episodes[1].raw_aux == "(VFL\x00"
    assert len(stable_windows(episodes[0], 250)) == 39
    # The first real VFL burst is only 7.5 seconds, so it is retained in source
    # inventory but cannot be padded/invented into a ten-second learner window.
    assert stable_windows(episodes[1], 250) == []
    assert len(REAL_418_ANNOTATION_SHA256) == 64


def test_exact_vfdb_label_dictionary_and_mode_subskill_ceiling() -> None:
    assert set(RHYTHM_LABELS) == {
        "AFIB", "ASYS", "B", "BI", "HGEA", "N", "NOD", "NOISE", "NSR",
        "PM", "SBR", "SVTA", "VER", "VF", "VFIB", "VFL", "VT",
    }
    assert RHYTHM_LABELS["VF"].canonical_rhythm_id == "ventricular_fibrillation"
    assert RHYTHM_LABELS["VFIB"].canonical_rhythm_id == "ventricular_fibrillation"
    assert RHYTHM_LABELS["N"].canonical_rhythm_id == "sinus_rhythm"
    assert RHYTHM_LABELS["NSR"].canonical_rhythm_id == "sinus_rhythm"
    assert RHYTHM_LABELS["NOISE"].learner_window_eligible is False
    for code, contract in RHYTHM_LABELS.items():
        if code == "NOISE":
            continue
        assert contract.eligible_modes == (FUTURE_MODE_ID,)
        assert contract.eligible_subskills == ("recognize", "discriminate")
        assert "apply_in_context" not in contract.eligible_subskills


def test_source_contract_is_open_versioned_odc_by_and_foundation_only() -> None:
    descriptor = KNOWN_SOURCES["mit-bih-vfdb"]
    assert descriptor.version == "1.0.0"
    assert descriptor.license_id == "ODC-BY-1.0"
    assert descriptor.access == "open"
    assert descriptor.educational_uses == ("rhythm_stream",)
    assert descriptor.patient_ids_available is True
    assert descriptor.published_uncompressed_size == "33.1 MB"
    catalog = source_catalog_entry("mit-bih-vfdb")
    assert catalog["sourceUrl"] == "https://physionet.org/content/vfdb/1.0.0/"
    assert catalog["doi"] == "https://doi.org/10.13026/C22P44"
    assert catalog["publishedUncompressedSize"] == "33.1 MB"


def test_checksum_manifest_fails_closed_before_trusting_rows() -> None:
    assert len(CHECKSUM_MANIFEST_SHA256) == 64
    with pytest.raises(ValueError, match="pinned PhysioNet"):
        parse_checksum_manifest(
            f"{REAL_418_HEADER_SHA256} 418.hea\n".encode("ascii")
        )


def test_packet_preserves_identity_checksums_and_forbids_patient_state() -> None:
    spec = _vfib_spec()
    packet = build_window_packet(
        spec,
        _shape_only_signal(),
        artifact_checksums=REAL_424_CHECKSUMS,
    )

    assert packet["case_id"] == (
        "mit-bih-vfdb:424@000314874-000317374"
    )
    assert packet["record_identity"] == {
        "sourceId": "mit-bih-vfdb",
        "sourceRecordId": "424@000314874-000317374",
        "parentRecordId": "424",
        "patientId": "424",
        "patientIdentityBasis": "source_record_identifier",
        "sourceVersion": "1.0.0",
        "licenseId": "ODC-BY-1.0",
    }
    provenance = packet["source_provenance"]
    assert provenance["recordName"] == "424"
    assert provenance["patientId"] == "424"
    assert provenance["windowStartSample"] == 314_874
    assert provenance["episodeStartSample"] == 314_749
    assert provenance["checksumManifest"]["sha256"] == CHECKSUM_MANIFEST_SHA256
    assert {
        name: row["sha256"] for name, row in provenance["sourceArtifacts"].items()
    } == REAL_424_CHECKSUMS
    assert packet["source_labels"]["rhythm"]["rhythmCode"] == "VFIB"
    assert packet["source_labels"]["rhythm"]["canonicalRhythmId"] == (
        "ventricular_fibrillation"
    )

    eligibility = packet["educational_eligibility"]
    assert eligibility["eligibleModes"] == [FUTURE_MODE_ID]
    assert eligibility["eligibleSubskills"] == {
        "ventricular_fibrillation": ["recognize", "discriminate"]
    }
    assert packet["current_student_serving_eligible"] is False
    assert eligibility["currentRuntimeModeConnected"] is False
    assert eligibility["scenarioWaveformEligibleAfterReview"] is True
    assert eligibility["clinicalCaseEligible"] is False
    assert eligibility["clinicalManagementEligible"] is False
    assert eligibility["pulseOrPerfusionClaimsEligible"] is False
    assert eligibility["cardiacArrestClaimEligible"] is False
    assert eligibility["shockableStatusClaimEligible"] is False
    assert eligibility["treatmentOrActionSequenceEligible"] is False
    assert packet["waveform"]["isTwelveLead"] is False
    assert packet["waveform"]["isMonitorOrDefibrillatorExport"] is False
    forbidden = " ".join(packet["llm_forbidden_claims"]).casefold()
    assert all(term in forbidden for term in ("pulse", "perfusion", "shock", "action", "12-lead"))
    assert not any("pulse" in row.casefold() for row in packet["llm_allowed_claims"])
    assert len(packet["signal_fingerprint"]) == 64


def test_fingerprint_is_ordered_content_and_dedicated_store_stays_disconnected(tmp_path) -> None:
    first_signal = _shape_only_signal()
    second_signal = _shape_only_signal(scale=2.0)
    assert rhythm_waveform_fingerprint(first_signal) == rhythm_waveform_fingerprint(first_signal)
    assert rhythm_waveform_fingerprint(first_signal) != rhythm_waveform_fingerprint(second_signal)
    with pytest.raises(ValueError, match="missing rhythm channel"):
        rhythm_waveform_fingerprint({"ECG1": first_signal["ECG1"]})

    packet = build_window_packet(
        _vfib_spec(), first_signal, artifact_checksums=REAL_424_CHECKSUMS
    )
    store = RhythmStreamStore(tmp_path / "rhythm.db")
    store.upsert(packet)
    assert store.count() == 1
    assert store.source_counts() == {"mit-bih-vfdb": 1}
    assert store.rhythm_counts() == {"ventricular_fibrillation": 1}
    assert store.get(packet["stream_window_id"])["record_identity"]["patientId"] == "424"
    assert list(store.iter_packets())[0]["signal_fingerprint"] == packet["signal_fingerprint"]

    connected = copy.deepcopy(packet)
    connected["educational_eligibility"]["currentRuntimeModeConnected"] = True
    with pytest.raises(ValueError, match="remain disconnected"):
        store.upsert(connected)


def test_noise_episode_never_yields_a_window() -> None:
    noise = RhythmEpisode("(NOISE\x00", "NOISE", 100, 100_000, 7)
    assert stable_windows(noise, 250) == []
