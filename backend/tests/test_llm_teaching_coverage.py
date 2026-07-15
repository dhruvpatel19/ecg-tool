from __future__ import annotations

import re

from app.config import Settings
from app.llm import (
    _CONCEPT_CUES,
    _GENERAL_TEACHING,
    _detect_concepts,
    curated_general_teaching,
    TutorService,
)
from app.ontology import CONCEPTS


def _neutral_packet() -> dict:
    return {
        "waveform": {"duration_sec": 10.0, "leads": ["I", "II", "aVF", "V1"]},
        "supported_objectives": ["sinus_rhythm"],
        "ptbxl_plus": {"features": {}, "fiducials": {"rois": []}},
    }


def test_reviewed_guidance_and_precise_cues_cover_every_canonical_concept() -> None:
    canonical = {concept.id for concept in CONCEPTS}

    assert canonical <= set(_GENERAL_TEACHING)
    assert canonical <= set(_CONCEPT_CUES)
    assert all(curated_general_teaching(concept) for concept in canonical)
    assert all(concept in _detect_concepts(f"Explain {_CONCEPT_CUES[concept][0]} in general.") for concept in canonical)


def test_ambiguous_words_do_not_infer_a_specific_pathology() -> None:
    assert _detect_concepts("What is the normal PR interval?") == ["pr_ms"]
    assert "inferior_mi" not in _detect_concepts("How do inferior leads view the heart?")
    assert "anterior_mi" not in _detect_concepts("How does the anterior fascicle conduct?")
    assert "av_block_first_degree" not in _detect_concepts("What is a heart block?")
    assert "sinus_rhythm" not in _detect_concepts("What does atrial activity mean?")


def test_every_canonical_general_question_uses_reviewed_local_teaching() -> None:
    class ExplodingProvider:
        def generate(self, messages: list[dict], context: dict) -> str:
            raise AssertionError("reviewed general teaching must bypass the remote provider")

    service = TutorService(Settings(llm_provider="openai-compatible", llm_api_key="unused"))
    service.provider = ExplodingProvider()
    axis_concepts = {"axis_normal", "left_axis_deviation", "right_axis_deviation"}

    for concept in (item.id for item in CONCEPTS):
        result = service.converse(
            f"Explain {_CONCEPT_CUES[concept][0]} in general.",
            _neutral_packet(),
            {},
            [],
            mode="tutorial",
            lesson={"objectives": [concept]},
            viewer_state={"pausedWaypoint": "Return to checkpoint"},
        )

        assert result["provider"] == "grounded-fallback", concept
        assert result["remoteCall"]["attempted"] is False, concept
        assert result["viewerActions"] == [], concept
        assert result["objectiveUpdates"] == [], concept
        assert result["claimCheck"]["unsupportedDiagnosisClaims"] == [], concept
        if concept in axis_concepts:
            assert "qrs" in result["tutorMessage"].lower(), concept
            assert "cannot substantiate" in result["tutorMessage"].lower(), concept
        else:
            assert "not a claim that the current tracing" in result["feedback"].lower(), concept
            assert result["suggestedNextStep"] == "Return to checkpoint", concept


def test_reviewed_teaching_contains_no_management_directives() -> None:
    directive = re.compile(
        r"\b(?:administer|prescribe|treat|cardiovert|defibrillate|anticoagulate|ablate|admit|discharge)\b",
        re.IGNORECASE,
    )

    for concept in (item.id for item in CONCEPTS):
        teaching = curated_general_teaching(concept)
        assert teaching is not None
        assert directive.search(teaching) is None, concept
