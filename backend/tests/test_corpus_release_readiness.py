from __future__ import annotations

from types import SimpleNamespace

from app.corpus_repository import CorpusRepository


LEADS = ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]


def packet(*, source: str = "ptbxl", case_id: str = "1") -> dict:
    return {
        "case_id": case_id,
        "source": source,
        "teaching_tier": "A",
        "waveform": {"leads": LEADS, "sampling_frequency": 100, "duration_sec": 10},
    }


class AuditStore:
    def __init__(self, packets: list[dict]):
        self.packets = packets

    def count(self) -> int:
        return len(self.packets)

    def source_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in self.packets:
            counts[row["source"]] = counts.get(row["source"], 0) + 1
        return counts

    def student_source_counts(self) -> dict[str, int]:
        return self.source_counts()

    def student_facing_count(self) -> int:
        return len(self.packets)

    def iter_student_packets(self):
        yield from self.packets


class AuditWaveforms:
    def __init__(self, readable: bool = True):
        self.readable = readable

    def read(self, case_id: str, leads: list[str]):
        return {"II": [0.0, 0.1, -0.1]} if self.readable else {}


def repository(packets: list[dict], *, readable: bool = True) -> CorpusRepository:
    repo = CorpusRepository.__new__(CorpusRepository)
    repo.settings = SimpleNamespace(
        min_corpus_cases=1,
        min_ptbxl_cases=1,
        min_practice_cases=1,
    )
    repo.store = AuditStore(packets)
    repo.waveforms = AuditWaveforms(readable)
    source_counts = repo.store.source_counts()
    repo.manifest = {
        "totalCases": len(packets),
        "sourceCounts": source_counts,
        "studentFacing": len(packets),
    }
    return repo


def test_release_audit_requires_policy_eligible_packets_and_readable_waveforms():
    repo = repository([packet()])

    assert repo._build_deployment_check() == (True, "ready")

    repo.waveforms = AuditWaveforms(False)
    assert repo._build_deployment_check() == (False, "representative_waveform_unreadable")


def test_release_audit_rejects_manifest_database_count_drift():
    repo = repository([packet()])
    repo.manifest["sourceCounts"] = {"ptbxl": 2}

    assert repo._build_deployment_check() == (False, "corpus_manifest_counts_mismatch")


def test_release_audit_rejects_research_only_or_unknown_corpus_sources():
    mimic = repository(
        [packet(), packet(source="mimic-iv-ecg", case_id="mimic-iv-ecg:1")]
    )
    unknown = repository([packet(), packet(source="unreviewed", case_id="unreviewed:1")])

    assert mimic._build_deployment_check() == (False, "corpus_contains_unapproved_source")
    assert unknown._build_deployment_check() == (False, "corpus_contains_unapproved_source")


def test_release_audit_enforces_complete_ptb_and_practice_minima():
    repo = repository([packet()])
    repo.settings.min_ptbxl_cases = 2
    assert repo._build_deployment_check() == (False, "ptbxl_release_incomplete")

    repo.settings.min_ptbxl_cases = 1
    repo.settings.min_practice_cases = 2
    assert repo._build_deployment_check() == (False, "practice_pool_below_release_minimum")
