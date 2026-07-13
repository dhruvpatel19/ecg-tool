from __future__ import annotations

from copy import deepcopy

from app.ingest.leipzig import SURFACE_LEADS, WindowSpec, build_window_packet
from app.objectives import (
    OBJECTIVES,
    audited_source_packet_supports_objective,
    objective_runtime_availability,
)
from app.storage import LearningStore


def _wct_packet() -> dict:
    spec = WindowSpec(
        record_name="x109",
        patient_id="109",
        sampling_frequency=1_000,
        start_sample=10_000,
        end_sample=20_000,
        episode_start_sample=9_500,
        episode_end_sample=20_500,
        raw_rhythm_aux="(VT",
        rhythm_code="VT",
        concept_id="wide_complex_tachycardia",
        beat_samples=tuple(range(10_300, 20_000, 300)),
    )
    signal = {
        lead: [((index % 25) - 12) / 100 for index in range(1_000)]
        for lead in SURFACE_LEADS
    }
    return build_window_packet(spec, signal)


class _Repo:
    def __init__(self, packet: dict | None):
        self.packet = packet

    def candidates(self, concept_id: str | None = None) -> list[dict]:
        if not self.packet or concept_id != "wide_complex_tachycardia":
            return []
        return [{"case_id": self.packet["case_id"], "source": self.packet["source"]}]

    def get_case(self, case_id: str) -> dict | None:
        return self.packet if self.packet and case_id == self.packet["case_id"] else None


def _event(packet: dict, key: str) -> dict:
    return {
        "eventKey": key,
        "moduleId": "rapid",
        "sceneId": "rhythm-stream",
        "interactionId": "wct-recognition",
        "concept": "wide_complex_tachycardia",
        "subskills": ["recognize"],
        "score": 1.0,
        "correct": True,
        "attempts": 1,
        "assistance": "independent",
        "hintsUsed": 0,
        "confidence": 4,
        "evidenceLevel": "independent_transfer",
        "caseId": packet["case_id"],
        "caseProvenance": "real_eligible",
        "caseEligible": True,
        "misconceptions": [],
        "_retentionVerified": True,
        "_retentionMorphologyKey": "leipzig:VT",
        "_serverVerifiedScoring": True,
    }


def test_wct_unlocks_only_for_complete_audited_expert_rhythm_packet() -> None:
    packet = _wct_packet()
    definition = OBJECTIVES["wide_complex_tachycardia"]

    assert audited_source_packet_supports_objective(packet, definition.id) is True
    available = objective_runtime_availability(definition, _Repo(packet))
    assert available.evidence_ceiling == "eligible_real_case"
    assert available.unavailable_reason is None
    assert available.eligible_case_ids == (packet["case_id"],)
    assert available.eligible_subskills == ("recognize", "discriminate")

    tamper_cases = []
    for path, value in (
        (("record_identity", "licenseId"), "wrong-license"),
        (("source_provenance", "sourceVersion"), "0.0.0"),
        (("educational_eligibility", "eligibleModes"), ["clinical"]),
        (("source_labels", "rhythm", "canonicalConceptId"), "sinus_rhythm"),
        (("signal_quality", "status"), "poor"),
    ):
        changed = deepcopy(packet)
        cursor = changed
        for key in path[:-1]:
            cursor = cursor[key]
        cursor[path[-1]] = value
        tamper_cases.append(changed)

    for changed in tamper_cases:
        assert audited_source_packet_supports_objective(changed, definition.id) is False
        locked = objective_runtime_availability(definition, _Repo(changed))
        assert locked.evidence_ceiling == "formative_or_simulation"
        assert locked.unavailable_reason


def test_learning_store_keeps_wct_guided_without_exact_audited_case_packet() -> None:
    packet = _wct_packet()

    unbound = LearningStore(":memory:")
    receipt = unbound.save_guided_learning_event("learner-unbound", _event(packet, "wct-unbound"))
    assert receipt["requestedEvidenceLevel"] == "independent_transfer"
    assert receipt["effectiveEvidenceLevel"] == "guided"

    invalid = deepcopy(packet)
    invalid["source_provenance"]["licenseId"] = "wrong-license"
    invalid_store = LearningStore(":memory:")
    invalid_store.set_case_packet_provider(_Repo(invalid).get_case)
    receipt = invalid_store.save_guided_learning_event("learner-invalid", _event(invalid, "wct-invalid"))
    assert receipt["effectiveEvidenceLevel"] == "guided"

    eligible_store = LearningStore(":memory:")
    eligible_store.set_case_packet_provider(_Repo(packet).get_case)
    receipt = eligible_store.save_guided_learning_event("learner-valid", _event(packet, "wct-valid"))
    assert receipt["effectiveEvidenceLevel"] == "independent_transfer"
