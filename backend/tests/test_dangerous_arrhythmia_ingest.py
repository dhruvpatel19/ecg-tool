from __future__ import annotations

import hashlib
import json

from app.ingest.dangerous_arrhythmia import (
    CHECKSUM_MANIFEST_SHA256,
    DESCRIPTOR,
    FragmentSpec,
    HeaderSummary,
    RECORDS_SHA256,
    RHYTHM_LABELS,
    SOURCE_FS,
    build_fragment_packet,
    build_release_manifest,
    parse_checksum_manifest,
    parse_header,
    select_fragments,
)
from app.store.rhythm_stream_store import RhythmStreamStore


def _spec(code: str = "VF", suffix: str = "a") -> FragmentSpec:
    checksum = hashlib.sha256(f"waveform-{suffix}".encode()).hexdigest()
    return FragmentSpec(
        relative_record_path=f"1_Dangerous_VFL_VF/frag/418_C_{code}_277s_frag",
        source_parent_record="418_C",
        source_offset_text="277",
        source_class="1_Dangerous_VFL_VF",
        rhythm_code=code,
        header_sha256=hashlib.sha256(f"header-{suffix}".encode()).hexdigest(),
        data_sha256=checksum,
    )


def test_source_contract_is_precise_single_lead_recognition_only() -> None:
    assert DESCRIPTOR.version == "1.0.0"
    assert DESCRIPTOR.license_id == "ODC-BY-1.0"
    assert DESCRIPTOR.educational_uses == ("rhythm_stream",)
    assert DESCRIPTOR.patient_ids_available is False
    assert DESCRIPTOR.source_url.endswith("/ecg-fragment-high-risk-label/1.0.0/")
    assert len(CHECKSUM_MANIFEST_SHA256) == 64
    assert set(RHYTHM_LABELS) == {
        "VFL", "VF", "VTTdP", "VTHR", "VTLR", "B", "HGEA", "VER",
        "AFIB", "SVTA", "SBR", "BI", "NOD", "BBB", "N", "Ne",
    }
    assert all(item.eligible_subskills == ("recognize", "discriminate") for item in RHYTHM_LABELS.values())


def test_checksum_manifest_must_be_pinned_and_include_the_real_records_hash() -> None:
    raw = f"{RECORDS_SHA256} RECORDS\n".encode("ascii")
    expected = hashlib.sha256(raw).hexdigest()
    assert parse_checksum_manifest(raw, expected_manifest_sha256=expected)["RECORDS"] == RECORDS_SHA256
    try:
        parse_checksum_manifest(raw.replace(b"b5d4", b"a5d4"), expected_manifest_sha256=expected)
    except ValueError as exc:
        assert "pinned" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("mutated checksum manifest was accepted")


def test_header_is_one_250_hz_signal_and_packet_hides_source_identity(tmp_path) -> None:
    header = parse_header(
        "418_C_VF_277s_frag 1 250 721\n"
        "418_C_VF_277s_frag.dat 16 200 16 0 -191 5627 0 col 1\n",
        "418_C_VF_277s_frag",
    )
    assert header == HeaderSummary(SOURCE_FS, 721, "1")
    spec = _spec()
    values = [((index % 17) - 8) / 1000 for index in range(header.sample_count)]
    packet = build_fragment_packet(spec, values, header)
    serialized = json.dumps(packet, sort_keys=True)
    assert spec.relative_record_path not in serialized
    assert spec.source_parent_record not in serialized
    assert packet["stream_window_id"].startswith("ecg-fragment-dangerous-arrhythmia:fragment-")
    assert packet["record_identity"]["patientId"] == ""
    assert packet["waveform"]["isTwelveLead"] is False
    assert packet["waveform"]["isSingleModifiedLimbLeadII"] is True
    assert packet["source_labels"]["rhythm"]["canonicalRhythmId"] == "ventricular_fibrillation"

    eligibility = packet["educational_eligibility"]
    assert eligibility["eligibleSubskills"] == {
        "ventricular_fibrillation": ["recognize", "discriminate"]
    }
    assert eligibility["clinicalCaseEligible"] is False
    assert eligibility["clinicalManagementEligible"] is False
    assert eligibility["treatmentOrActionSequenceEligible"] is False
    assert eligibility["shockabilityClassificationEligible"] is False
    assert eligibility["masteryEvidenceEligible"] is False
    forbidden = " ".join(packet["llm_forbidden_claims"]).casefold()
    for term in ("pulse", "stability", "cardiac arrest", "shockability", "treatment", "management"):
        assert term in forbidden

    store = RhythmStreamStore(tmp_path / "rhythm.db")
    store.upsert(packet)
    assert store.count() == 1
    stored = store.get(packet["stream_window_id"])
    assert stored is not None
    assert stored["signal_fingerprint"] == packet["signal_fingerprint"]

    manifest = build_release_manifest((packet,))
    assert manifest["fragmentCount"] == 1
    assert manifest["canonicalRhythmCounts"] == {"ventricular_fibrillation": 1}
    assert manifest["clinicalManagementEligible"] is False
    assert manifest["currentRuntimeConnected"] is False


def test_selection_is_deterministic_bounded_and_label_scoped() -> None:
    fragments = (_spec("VF", "b"), _spec("VF", "a"), _spec("VFL", "c"))
    selected = select_fragments(
        fragments,
        rhythm_codes={"VF"},
        max_per_rhythm=1,
    )
    assert len(selected) == 1
    assert selected[0].rhythm_code == "VF"
