from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from app.corpus_repository import CorpusRepository
from app.ingest.dangerous_arrhythmia import (
    FragmentSpec,
    HeaderSummary,
    SOURCE_FS,
    build_fragment_packet,
    build_release_manifest,
)
from app.rapid_rhythm_supplement import (
    RUNTIME_LEAD,
    RUNTIME_MANIFEST_NAME,
    RUNTIME_MAPPING_VERSION,
    RUNTIME_SCOPE,
    RapidRhythmSupplement,
    build_runtime_manifest,
)
from app.store.rhythm_stream_store import RhythmStreamStore
from app.store.waveform_store import LocalWaveformStore


_AUDIT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "audit_release_corpus.py"
_AUDIT_SPEC = importlib.util.spec_from_file_location("release_corpus_audit", _AUDIT_PATH)
assert _AUDIT_SPEC is not None and _AUDIT_SPEC.loader is not None
_AUDIT_MODULE = importlib.util.module_from_spec(_AUDIT_SPEC)
_AUDIT_SPEC.loader.exec_module(_AUDIT_MODULE)
_audit_rapid_rhythm_supplement = _AUDIT_MODULE._audit_rapid_rhythm_supplement


TWELVE_LEADS = [
    "I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"
]


def _packet(code: str, suffix: str) -> tuple[dict, list[float]]:
    spec = FragmentSpec(
        relative_record_path=f"1_Dangerous_VFL_VF/frag/418_C_{code}_277s_frag",
        source_parent_record="418_C",
        source_offset_text="277",
        source_class="1_Dangerous_VFL_VF",
        rhythm_code=code,
        header_sha256=hashlib.sha256(f"header-{suffix}".encode()).hexdigest(),
        data_sha256=hashlib.sha256(f"data-{suffix}".encode()).hexdigest(),
    )
    header = HeaderSummary(SOURCE_FS, 500, "1")
    offset = (int(hashlib.sha256(suffix.encode()).hexdigest()[:4], 16) % 17) / 1000
    values = [((index % 31) - 15) / 100 + offset for index in range(header.sample_count)]
    return build_fragment_packet(spec, values, header), values


def _build_supplement(tmp_path, codes: tuple[str, ...] = ("VF", "VTHR", "VTTdP")):
    root = tmp_path / "rapid_rhythm_supplement"
    store = RhythmStreamStore(root / "rhythm_streams.db")
    waveforms = LocalWaveformStore(root / "waveforms", leads=(RUNTIME_LEAD,))
    packets: list[dict] = []
    for index, code in enumerate(codes):
        packet, values = _packet(code, str(index))
        store.upsert(packet)
        waveforms.write(packet["case_id"], {RUNTIME_LEAD: values})
        packets.append(packet)
    source_manifest_path = root / "manifest.json"
    source_manifest_path.write_text(
        json.dumps(build_release_manifest(packets), sort_keys=True), encoding="utf-8"
    )
    runtime_manifest = build_runtime_manifest(
        source_manifest_path=source_manifest_path,
        packets=packets,
    )
    runtime_path = root / RUNTIME_MANIFEST_NAME
    runtime_path.write_text(json.dumps(runtime_manifest, sort_keys=True), encoding="utf-8")
    reader = RapidRhythmSupplement(root)
    reference = {
        "schemaVersion": 1,
        "path": "rapid_rhythm_supplement",
        "sourceId": "ecg-fragment-dangerous-arrhythmia",
        "runtimeScope": RUNTIME_SCOPE,
        "mappingVersion": RUNTIME_MAPPING_VERSION,
        "fragmentCount": reader.count,
        "learnerTargetCounts": reader.target_counts,
        "runtimeManifestSha256": hashlib.sha256(runtime_path.read_bytes()).hexdigest(),
    }
    return root, packets, reference, reader


def test_release_audit_exhaustively_pins_supplement_without_raw_identity(tmp_path) -> None:
    _, _, reference, _ = _build_supplement(tmp_path)

    result = _audit_rapid_rhythm_supplement(tmp_path, reference)

    assert result["complete"] is True
    assert result["fragmentCount"] == 3
    assert result["waveforms"] == {
        "complete": True,
        "caseFilesChecked": 3,
        "npyFilesFound": 3,
        "expectedColumns": 1,
        "lead": "MLII",
        "dtype": "int16",
        "filesSha256": result["waveforms"]["filesSha256"],
    }
    assert len(result["waveforms"]["filesSha256"]) == 64
    serialized = json.dumps(result, sort_keys=True)
    assert "418_C" not in serialized
    assert "1_Dangerous_VFL_VF" not in serialized


def test_release_audit_rejects_parent_hash_drift(tmp_path) -> None:
    _, _, reference, _ = _build_supplement(tmp_path, ("VF",))
    reference["runtimeManifestSha256"] = "0" * 64

    with pytest.raises(SystemExit, match="production reader rejected"):
        _audit_rapid_rhythm_supplement(tmp_path, reference)


def test_release_audit_rejects_waveform_content_drift_and_extra_files(tmp_path) -> None:
    root, packets, reference, _ = _build_supplement(tmp_path, ("VF",))
    waveforms = LocalWaveformStore(root / "waveforms", leads=(RUNTIME_LEAD,))
    path = waveforms.path_for(packets[0]["case_id"])
    values = np.load(path, allow_pickle=False)
    values[0, 0] += 1
    np.save(path, values, allow_pickle=False)

    with pytest.raises(SystemExit, match="production reader rejected"):
        _audit_rapid_rhythm_supplement(tmp_path, reference)

    # Restore the reviewed file, then prove that an unindexed NPY also fails.
    _, original_values = _packet("VF", "0")
    waveforms.write(packets[0]["case_id"], {RUNTIME_LEAD: original_values})
    extra = root / "waveforms" / "extra.npy"
    np.save(extra, np.zeros((500, 1), dtype=np.int16), allow_pickle=False)
    with pytest.raises(SystemExit, match="one-to-one"):
        _audit_rapid_rhythm_supplement(tmp_path, reference)


class _MainStore:
    def __init__(self, packet: dict):
        self.packet = packet

    def count(self) -> int:
        return 1

    def source_counts(self) -> dict[str, int]:
        return {"ptbxl": 1}

    def student_source_counts(self) -> dict[str, int]:
        return {"ptbxl": 1}

    def student_facing_count(self) -> int:
        return 1

    def iter_student_packets(self):
        yield self.packet


class _MainWaveforms:
    def read(self, case_id: str, leads: list[str]):
        return {"II": [0.0, 0.1, -0.1]}


def test_runtime_readiness_requires_matching_supplement_release_audit(tmp_path) -> None:
    _, _, reference, reader = _build_supplement(tmp_path, ("VF",))
    main_packet = {
        "case_id": "1",
        "source": "ptbxl",
        "teaching_tier": "A",
        "waveform": {
            "leads": TWELVE_LEADS,
            "sampling_frequency": 100,
            "duration_sec": 10,
        },
    }
    manifest = {
        "complete": True,
        "totalCases": 1,
        "sourceCounts": {"ptbxl": 1},
        "studentFacing": 1,
        "rapidRhythmSupplement": reference,
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    rhythm_audit = _audit_rapid_rhythm_supplement(tmp_path, reference)
    release_audit = {
        "schemaVersion": 1,
        "manifestSha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "totalCases": 1,
        "sourceCounts": {"ptbxl": 1},
        "waveforms": {"complete": True, "caseFilesChecked": 1, "npyFilesFound": 1},
        "clinical": {"harnessPassed": True, "distinctRealEcgs": 1},
        "rapidRhythmSupplement": rhythm_audit,
    }
    audit_path = tmp_path / "release-audit.json"
    audit_path.write_text(json.dumps(release_audit, sort_keys=True), encoding="utf-8")

    repository = CorpusRepository.__new__(CorpusRepository)
    repository.root = tmp_path
    repository.settings = SimpleNamespace(
        min_corpus_cases=1,
        min_ptbxl_cases=1,
        min_practice_cases=1,
        min_clinical_cases=1,
        require_release_audit=True,
    )
    repository.store = _MainStore(main_packet)
    repository.waveforms = _MainWaveforms()
    repository.manifest = manifest
    repository.rapid_rhythm_supplement = reader
    repository.rapid_rhythm_supplement_error = None

    assert repository._build_deployment_check() == (True, "ready")

    release_audit["rapidRhythmSupplement"]["databaseSha256"] = "0" * 64
    audit_path.write_text(json.dumps(release_audit, sort_keys=True), encoding="utf-8")
    assert repository._build_deployment_check() == (
        False,
        "rapid_rhythm_release_audit_mismatch",
    )
