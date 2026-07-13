from __future__ import annotations

import math

from app.ingest.leipzig import (
    RHYTHM_TO_CONCEPT,
    SURFACE_LEADS,
    RhythmEpisode,
    WindowSpec,
    build_window_packet,
    downsample_surface_signals,
    map_rhythm_aux,
    segment_rhythm_episodes,
    signal_quality_intervals,
    stable_windows,
)


def test_episode_mapping_uses_all_rhythm_markers_as_hard_boundaries() -> None:
    samples = [0, 15_000, 30_000, 45_000, 60_000, 75_000, 90_000, 105_000]
    symbols = ["+"] * len(samples)
    aux = ["(N", "(AFL", "(AVNRT", "(AVRT", "(VT", "(AFIB", "(/A", "(/V"]

    episodes = segment_rhythm_episodes(samples, symbols, aux, 120_000)

    # AFL is not silently admitted, but its marker still terminates sinus rhythm.
    assert [(row.rhythm_code, row.start_sample, row.end_sample) for row in episodes] == [
        ("N", 0, 15_000),
        ("AVNRT", 30_000, 45_000),
        ("AVRT", 45_000, 60_000),
        ("VT", 60_000, 75_000),
        ("AFIB", 75_000, 90_000),
        ("/A", 90_000, 105_000),
        ("/V", 105_000, 120_000),
    ]
    assert map_rhythm_aux("(AVNRT") == "supraventricular_tachycardia"
    assert map_rhythm_aux("(AVRT") == "supraventricular_tachycardia"
    assert map_rhythm_aux("(VT") == "wide_complex_tachycardia"
    assert map_rhythm_aux("(AFIB") == "atrial_fibrillation"
    assert map_rhythm_aux("(/A") == "paced_rhythm"
    assert map_rhythm_aux("(/V") == "paced_rhythm"
    assert map_rhythm_aux("(N") == "sinus_rhythm"
    assert map_rhythm_aux("(AFL") is None
    assert "normal_ecg" not in RHYTHM_TO_CONCEPT.values()


def test_stable_windows_are_nonoverlapping_contained_and_quality_filtered() -> None:
    episode = RhythmEpisode("(N", "N", "sinus_rhythm", 0, 40_000)
    beats = list(range(500, 40_000, 1_000))
    quality = signal_quality_intervals([12_000, 18_000], ["~", "~"], 40_000)

    windows = stable_windows(
        episode,
        1_000,
        beats,
        quality,
        boundary_guard_seconds=0,
        duration_seconds=10,
        stride_seconds=10,
    )

    assert [(start, end) for start, end, _ in windows] == [
        (0, 10_000),
        (20_000, 30_000),
        (30_000, 40_000),
    ]
    assert all(episode.start_sample <= start < end <= episode.end_sample for start, end, _ in windows)
    assert all(end - start == 10_000 for start, end, _ in windows)


def test_downsample_normalizes_977_hz_surface_leads_to_exactly_100_hz() -> None:
    source = {
        lead: [math.sin(index / 40.0) + lead_index * 0.01 for index in range(9_770)]
        for lead_index, lead in enumerate(SURFACE_LEADS)
    }

    sampled = downsample_surface_signals(source, 977)

    assert list(sampled) == list(SURFACE_LEADS)
    assert {len(values) for values in sampled.values()} == {1_000}
    assert all(math.isfinite(value) for values in sampled.values() for value in values)


def test_packet_preserves_provenance_and_forbids_clinical_management() -> None:
    spec = WindowSpec(
        record_name="x001",
        patient_id="001",
        sampling_frequency=1_000,
        start_sample=10_000,
        end_sample=20_000,
        episode_start_sample=9_000,
        episode_end_sample=21_000,
        raw_rhythm_aux="(N",
        rhythm_code="N",
        concept_id="sinus_rhythm",
        beat_samples=tuple(range(10_500, 20_000, 1_000)),
    )
    signal = {
        lead: [round(math.sin(index / 12.0) * 0.5, 4) for index in range(1_000)]
        for lead in SURFACE_LEADS
    }

    packet = build_window_packet(
        spec,
        signal,
        source_subject_metadata={
            "subject_id": "001",
            "file_name": "x001",
            "age": "6.6",
            "gender": "M",
            "diagnosis": "AVRT",
            "invented_context": "must not survive",
        },
    )

    assert packet["case_id"].startswith("leipzig-heart-center:x001@")
    assert packet["record_identity"] == {
        "sourceId": "leipzig-heart-center",
        "sourceRecordId": spec.source_record_id,
        "patientId": "001",
        "sourceVersion": "1.0.0",
        "licenseId": "ODC-BY-1.0",
    }
    provenance = packet["source_provenance"]
    assert provenance["recordName"] == "x001"
    assert provenance["patientId"] == "001"
    assert provenance["sourceVersion"] == "1.0.0"
    assert provenance["licenseId"] == "ODC-BY-1.0"
    assert provenance["annotationFile"] == "x001.atr"
    assert "invented_context" not in provenance["subjectMetadata"]
    assert packet["source_labels"]["rhythm"]["canonicalConceptId"] == "sinus_rhythm"

    eligibility = packet["educational_eligibility"]
    assert eligibility["eligibleModes"] == ["training", "rapid"]
    assert eligibility["clinicalCaseEligible"] is False
    assert eligibility["clinicalManagementEligible"] is False
    assert "sinus_rhythm" in packet["supported_objectives"]
    assert "normal_ecg" not in packet["supported_objectives"]
    assert packet["concept_confidence"]["normal_ecg"]["tier"] == "D"
    assert any("Do not equate sinus rhythm with a normal ECG" in row for row in packet["llm_forbidden_claims"])
    assert any("management" in row.lower() for row in packet["llm_forbidden_claims"])

    assert packet["ptbxl_plus"]["features"]["heart_rate"] == 60.0
    rois = packet["ptbxl_plus"]["fiducials"]["rois"]
    assert rois
    assert {row["concept"] for row in rois} == {"qrs_complex"}
    assert {row["source"] for row in rois} == {"leipzig_expert_beat_timing"}
    assert all("rhythm" not in row and "annotationSymbol" not in row for row in rois)
    assert len(packet["signal_fingerprint"]) == 64
