from __future__ import annotations

import hashlib
import io
import json
import zipfile

from app.ingest.source_contract import KNOWN_SOURCES
from app.ingest.staff_iii import (
    CHECKSUM_MANIFEST_SHA256,
    FRAME_SECONDS,
    HeaderSummary,
    InflationProtocol,
    METADATA_XLSX_SHA256,
    PatientProtocol,
    RECORDS_SHA256,
    SOURCE_FS,
    TARGET_FS,
    artifact_contains_raw_record_identity,
    build_episode_artifact,
    build_episode_specs,
    build_release_manifest,
    parse_checksum_manifest,
    parse_header,
    parse_protocol_workbook,
)
from app.store.waveform_store import LEADS


def _workbook(values: dict[str, str]) -> bytes:
    shared = list(values.values())
    cells = "".join(
        f'<c r="{reference}" t="s"><v>{index}</v></c>'
        for index, reference in enumerate(values)
    )
    strings = "".join(f"<si><t>{value}</t></si>" for value in shared)
    namespace = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "xl/sharedStrings.xml",
            f'<sst xmlns="{namespace}" count="{len(shared)}" uniqueCount="{len(shared)}">'
            f"{strings}</sst>",
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            f'<worksheet xmlns="{namespace}"><sheetData><row r="11">{cells}</row>'
            "</sheetData></worksheet>",
        )
    return buffer.getvalue()


def _signals(scale: float = 1.0) -> dict[str, list[float]]:
    points = int(FRAME_SECONDS * TARGET_FS)
    return {
        lead: [scale * (index % 19) / 1000 for index in range(points)] for lead in LEADS
    }


def test_source_descriptor_is_open_protocol_timed_and_not_a_management_source() -> None:
    descriptor = KNOWN_SOURCES["staff-iii"]
    assert descriptor.version == "1.0.0"
    assert descriptor.license_id == "ODC-BY-1.0"
    assert descriptor.educational_uses == ("acute_serial",)
    assert "PTCA" in descriptor.label_authority
    assert descriptor.source_url.endswith("/staffiii/1.0.0/")
    assert len(CHECKSUM_MANIFEST_SHA256) == 64


def test_checksum_manifest_must_be_caller_pinned_before_rows_are_trusted() -> None:
    raw = (
        f"{RECORDS_SHA256} RECORDS\n"
        f"{METADATA_XLSX_SHA256} STAFF-III-Database-Annotations.xlsx\n"
    ).encode("ascii")
    expected = hashlib.sha256(raw).hexdigest()
    parsed = parse_checksum_manifest(raw, expected_manifest_sha256=expected)
    assert parsed["RECORDS"] == RECORDS_SHA256
    try:
        parse_checksum_manifest(raw + b"0", expected_manifest_sha256=expected)
    except ValueError as exc:
        assert "pinned" in str(exc)
    else:  # pragma: no cover - makes the intended fail-closed contract explicit
        raise AssertionError("mutated checksum manifest was accepted")


def test_workbook_parser_reads_protocol_records_but_drops_patient_attributes() -> None:
    raw = _workbook(
        {
            "A11": "17",
            "B11": "83",
            "C11": "f",
            "E11": "17b",
            "G11": "17c",
            "H11": "mid LAD",
            "I11": "60;185;20",
            "J11": "238",
            "Y11": "17d",
            "AC11": "anterior",
        }
    )
    protocols = parse_protocol_workbook(raw)
    assert len(protocols) == 1
    protocol = protocols[0]
    assert protocol.baseline_record == "017b"
    assert protocol.recovery_record == "017d"
    assert protocol.inflations[0].record_name == "017c"
    assert protocol.inflations[0].documented_injection_seconds == (238.0,)
    assert not hasattr(protocol, "age")
    assert not hasattr(protocol, "sex")
    assert not hasattr(protocol, "prior_mi")


def test_header_contract_requires_expected_nine_measured_source_leads() -> None:
    lead_rows = "\n".join(
        f"017b.dat 16+512 1600 12 0 0 0 0 {lead}"
        for lead in ("V1", "V2", "V3", "V4", "V5", "V6", "I", "II", "III")
    )
    header = parse_header(f"017b 9 1000 300000\n{lead_rows}\n# Age: 83\n", "017b")
    assert header.sampling_frequency == SOURCE_FS
    assert header.sample_count == 300000
    assert set(header.leads) == {"I", "II", "III", "V1", "V2", "V3", "V4", "V5", "V6"}


def test_comparison_artifact_is_complete_opaque_and_review_gated() -> None:
    protocol = PatientProtocol(
        source_patient_number=17,
        baseline_record="017b",
        baseline_kind="BC1",
        recovery_record="017d",
        recovery_kind="PC1",
        inflations=(
            InflationProtocol("017c", 1, "mid LAD", 60, 185, 20, (238.0,)),
        ),
    )
    headers = {
        "017b": HeaderSummary("017b", SOURCE_FS, 300000, ()),
        "017c": HeaderSummary("017c", SOURCE_FS, 265000, ()),
        "017d": HeaderSummary("017d", SOURCE_FS, 300000, ()),
    }
    specs = build_episode_specs((protocol,), headers)
    assert len(specs) == 1
    spec = specs[0]
    assert [frame.role for frame in spec.frames] == ["baseline", "occlusion", "recovery"]
    # The documented injection at 238 s is conservatively excluded from the
    # selected 10-second occlusion frame and its two-second guard.
    assert spec.occlusion.end_sample <= 236000

    artifact = build_episode_artifact(
        spec,
        {"baseline": _signals(1), "occlusion": _signals(2), "recovery": _signals(3)},
    )
    serialized = json.dumps(artifact, sort_keys=True)
    assert "017b" not in serialized
    assert "017c" not in serialized
    assert "017d" not in serialized
    assert artifact["comparisonTruth"]["protocolOrderVerified"] is True
    assert artifact["comparisonTruth"]["morphologyAnswerKeyReady"] is False
    eligibility = artifact["educationalEligibility"]
    assert eligibility["eligibleModes"] == []
    assert eligibility["clinicalManagementEligible"] is False
    assert eligibility["masteryEvidenceEligible"] is False
    assert artifact["currentStudentServingEligible"] is False
    assert all(frame["waveform"]["isTwelveLead"] for frame in artifact["frames"])

    # Raw STAFF names are short enough to appear inside a SHA-256 by chance.
    # The leak guard must reject record tokens and paths, not opaque digests.
    hash_collision_shape = dict(artifact)
    hash_collision_shape["opaqueDigest"] = "a" * 30 + "017b" + "c" * 30
    assert artifact_contains_raw_record_identity(
        hash_collision_shape, ("017b", "017c", "017d")
    ) is False
    leaked = dict(artifact)
    leaked["sourcePath"] = "data/017b"
    assert artifact_contains_raw_record_identity(
        leaked, ("017b", "017c", "017d")
    ) is True

    manifest = build_release_manifest((artifact,))
    assert manifest["complete"] is True
    assert manifest["episodeCount"] == 1
    assert manifest["sourceCandidateEpisodeCount"] == 1
    assert manifest["qualityExcludedEpisodeCount"] == 0
    assert manifest["qualityExclusionCounts"] == {}
    assert manifest["sequenceCounts"] == {"baseline->occlusion->recovery": 1}
    assert manifest["rawPatientIdentifiersIncluded"] is False
    json.dumps(manifest)

    manifest_with_exclusion = build_release_manifest(
        (artifact,),
        source_candidate_episode_count=2,
        quality_exclusion_counts={"non_finite_source_samples": 1},
    )
    assert manifest_with_exclusion["episodeCount"] == 1
    assert manifest_with_exclusion["qualityExcludedEpisodeCount"] == 1
