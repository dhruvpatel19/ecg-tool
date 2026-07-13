from __future__ import annotations

import json

from app.config import Settings
from app.llm import MockProvider, TutorService, _detect_concepts, _flag_unsupported_diagnoses, _profile_summary, _roi_for_concept
from app.schemas import TutorResponse, ViewerAction, validate_tutor_response


def _packet_with_rois() -> dict:
    return {
        "waveform": {"duration_sec": 10.0, "leads": ["I", "II", "V2", "V5"]},
        "supported_objectives": ["sinus_rhythm"],
        "ptbxl_plus": {
            "features": {},
            "fiducials": {
                "rois": [
                    {"concept": "p_wave", "lead": "II", "label": "P wave",
                     "timeStartSec": 0.10, "timeEndSec": 0.20, "ampMinMv": -0.1, "ampMaxMv": 0.2},
                    {"concept": "qrs_complex", "lead": "II", "label": "QRS complex",
                     "timeStartSec": 0.30, "timeEndSec": 0.40, "ampMinMv": -0.5, "ampMaxMv": 1.0},
                ]
            },
        },
    }


def _axis_packet() -> dict:
    packet = _packet_with_rois()
    packet["supported_objectives"] = ["axis_normal"]
    packet["ptbxl_plus"]["features"] = {"axis_deg": -12}
    packet["ptbxl_plus"]["fiducials"]["rois"] = [
        {"concept": "p_wave", "lead": "II", "label": "P wave",
         "timeStartSec": 0.10, "timeEndSec": 0.20, "ampMinMv": -0.1, "ampMaxMv": 0.2},
        {"concept": "qrs_complex", "lead": "I", "label": "QRS complex I",
         "timeStartSec": 0.30, "timeEndSec": 0.40, "ampMinMv": -0.5, "ampMaxMv": 1.0},
        {"concept": "qrs_complex", "lead": "aVF", "label": "QRS complex aVF",
         "timeStartSec": 0.31, "timeEndSec": 0.41, "ampMinMv": -0.5, "ampMaxMv": 1.0},
    ]
    return packet


def test_mock_neutral_anatomy_highlights_requested_component_without_warning() -> None:
    # "Show me the QRS complex" must point at the QRS ROI (not the P wave) and must NOT
    # warn about an unsupported finding (V1 audit regression).
    raw = MockProvider().generate(
        [{"role": "user", "content": "Show me the QRS complex"}],
        {"casePacket": _packet_with_rois(), "mode": "practice"},
    )
    data = json.loads(raw)
    highlights = [a for a in data["viewerActions"] if a["type"] == "highlightROI"]
    assert highlights and highlights[0]["label"] == "QRS complex"
    assert data["uncertaintyWarnings"] == []


def test_adaptive_plan_coach_explains_verified_queue_without_scoring_or_viewer_actions() -> None:
    raw = MockProvider().generate(
        [{"role": "user", "content": "Why is this first, and what evidence would make it durable?"}],
        {
            "casePacket": None,
            "mode": "freeform",
            "viewerState": {
                "activity": "adaptive_mastery_plan",
                "authority": "verified_scheduler_only",
                "explanation": "Due retrievals are ranked before unseen cells.",
                "primary": {
                    "concept": "atrial_fibrillation",
                    "label": "Atrial fibrillation",
                    "subskill": "recognize",
                    "reason": "Atrial fibrillation recognition is overdue for retrieval by 3 days.",
                },
                "prescribedStages": [{"title": "Build atrial fibrillation recognition"}],
            },
        },
    )
    data = json.loads(raw)

    assert "atrial fibrillation" in data["tutorMessage"].lower()
    assert "overdue" in data["tutorMessage"].lower()
    assert data["objectiveUpdates"] == []
    assert data["viewerActions"] == []
    assert "cannot score" in " ".join(data["uncertaintyWarnings"]).lower()


def test_tutor_profile_prefers_exact_subskill_and_retention_evidence() -> None:
    summary = _profile_summary({
        "learnerId": "learner",
        "weakObjectives": ["atrial_fibrillation", "normal_ecg"],
        "subskillMastery": [{
            "concept": "atrial_fibrillation",
            "subskill": "recognize",
            "attempts": 5,
            "independentAttempts": 5,
            "independentMastery": 0.82,
            "dueState": "scheduled",
            "isDue": False,
            "distinctSuccessfulEcgs": 5,
            "distinctMorphologies": 4,
            "stabilityDays": 7,
            "lapses": 0,
            "spacedRetrievals": 3,
            "highConfidenceWrong": 0,
        }],
        "misconceptions": [],
    })
    assert summary["competencySource"] == "exact_subskill_receipts"
    assert summary["priorityCompetencies"][0]["objectiveId"] == "atrial_fibrillation"
    assert summary["priorityCompetencies"][0]["distinctSuccessfulEcgs"] == 5
    assert "atrial_fibrillation" not in summary["weakObjectives"]
    assert summary["weakObjectives"] == ["normal_ecg"]


def test_axis_challenge_uses_numeric_axis_and_qrs_never_p_wave_evidence() -> None:
    raw = MockProvider().generate(
        [{"role": "user", "content": "Why is a P wave evidence for axis? Show me the correct trace evidence."}],
        {"casePacket": _axis_packet(), "mode": "practice"},
    )
    data = json.loads(raw)

    assert "-12" in data["tutorMessage"]
    assert "does not support" in data["tutorMessage"]
    assert "qrs" in data["tutorMessage"].lower()
    highlights = [action for action in data["viewerActions"] if action["type"] == "highlightROI"]
    assert {action["lead"] for action in highlights} == {"I", "aVF"}
    assert all("qrs" in action["label"].lower() for action in highlights)
    assert all("p wave" not in evidence.lower() for evidence in data["citedEvidence"])


def test_axis_evidence_boundary_bypasses_remote_provider() -> None:
    class ExplodingProvider:
        def generate(self, messages: list[dict], context: dict) -> str:
            raise AssertionError("axis evidence must use the curated QRS/measurement path")

    service = TutorService(Settings(llm_provider="openai-compatible", llm_api_key="unused"))
    service.provider = ExplodingProvider()
    result = service.converse(
        "Show the evidence for the axis on this tracing.",
        _axis_packet(),
        {},
        [],
        mode="practice",
    )

    assert "-12" in result["tutorMessage"]
    assert result["viewerActions"]
    assert all("QRS" in (action.get("label") or "") for action in result["viewerActions"])


def test_diagnosis_claim_check_flags_assertions_but_not_refusals() -> None:
    case = {"supported_objectives": ["sinus_rhythm"]}
    asserted = TutorResponse(
        tutorMessage="This tracing shows an anterior STEMI with marked ST elevation in V2-V4.", feedback=""
    )
    assert _flag_unsupported_diagnoses(asserted, case), "an asserted unsupported finding must be flagged"

    refused = TutorResponse(
        tutorMessage="I don't have grounded evidence for ST elevation here, so I won't claim it.", feedback=""
    )
    assert _flag_unsupported_diagnoses(refused, case) == [], "a refusal must not be flagged"


def test_validate_tutor_response_accepts_grounded_json() -> None:
    response, error = validate_tutor_response(
        {
            "tutorMessage": "Look at V2.",
            "feedback": "Grounded feedback.",
            "viewerActions": [
                {"type": "highlightLead", "lead": "V2"},
                {"type": "drawCaliper", "lead": "II", "timeStart": 1.0, "timeEnd": 1.16, "label": "PR"},
            ],
            "objectiveUpdates": [],
            "misconceptions": [],
            "uncertaintyWarnings": [],
            "suggestedNextStep": "Submit.",
        }
    )

    assert error is None
    assert all(isinstance(action, ViewerAction) for action in response.viewerActions)


def test_validate_tutor_response_falls_back_on_invalid_json() -> None:
    response, error = validate_tutor_response("not json")

    assert error is not None
    assert response.viewerActions == []
    assert response.uncertaintyWarnings


def test_concept_detection_does_not_find_mi_inside_terminal() -> None:
    concepts = _detect_concepts("Does a terminal S wave in lead I support RBBB?")
    assert "right_bundle_branch_block" in concepts
    assert "myocardial_infarction" not in concepts


def test_mock_answers_general_tangent_and_preserves_exact_waypoint() -> None:
    raw = MockProvider().generate(
        [{"role": "user", "content": "How do I distinguish wide-complex tachycardia from VT?"}],
        {
            "casePacket": _packet_with_rois(),
            "mode": "tutorial",
            "lesson": {"objectives": ["sinus_rhythm"]},
            "viewerState": {"pausedWaypoint": "Vectors · S2 polarity checkpoint"},
        },
    )
    data = json.loads(raw)

    assert "wide-complex tachycardia" in data["tutorMessage"].lower()
    assert data["viewerActions"] == []
    assert data["suggestedNextStep"] == "Vectors · S2 polarity checkpoint"
    assert data["onLessonTopic"] is False
    assert "current tracing" in data["feedback"].lower()


def test_tutor_service_uses_curated_general_answer_before_remote_provider() -> None:
    class ExplodingProvider:
        def generate(self, messages: list[dict], context: dict) -> str:
            raise AssertionError("general teaching tangent should not call the remote provider")

    service = TutorService(Settings(llm_provider="openai-compatible", llm_api_key="unused"))
    service.provider = ExplodingProvider()
    result = service.converse(
        "How do I distinguish wide-complex tachycardia from VT?",
        _packet_with_rois(),
        {},
        [],
        mode="tutorial",
        lesson={"objectives": ["sinus_rhythm"]},
        viewer_state={"pausedWaypoint": "Vectors · S2 polarity checkpoint"},
    )

    assert "wide-complex tachycardia" in result["tutorMessage"].lower()
    assert result["suggestedNextStep"] == "Vectors · S2 polarity checkpoint"
    assert result["onLessonTopic"] is False

    paraphrase = service.converse(
        "Where in lead V1 would I look to distinguish RBBB from a normal rSr' pattern in general?",
        _packet_with_rois(),
        {},
        [],
        mode="tutorial",
        lesson={"objectives": ["axis_normal"]},
        viewer_state={"pausedWaypoint": "Vectors · S2 polarity checkpoint"},
    )
    assert "terminal" in paraphrase["tutorMessage"].lower()
    assert paraphrase["suggestedNextStep"] == "Vectors · S2 polarity checkpoint"


def test_novice_sequence_and_p_qrs_physiology_are_general_and_resume_waypoint() -> None:
    class ExplodingProvider:
        def generate(self, messages: list[dict], context: dict) -> str:
            raise AssertionError("curated novice teaching should not call the remote provider")

    service = TutorService(Settings(llm_provider="openai-compatible", llm_api_key="unused"))
    service.provider = ExplodingProvider()
    waypoint = "Foundations · rhythm checkpoint"

    rate = service.converse(
        "How does rate fit before rhythm in the systematic sequence?",
        _packet_with_rois(),
        {},
        [],
        mode="tutorial",
        lesson={"objectives": ["axis_normal"]},
        viewer_state={"pausedWaypoint": waypoint},
    )
    assert "rate before" in rate["tutorMessage"].lower()
    assert "regularity" in rate["tutorMessage"].lower()
    assert rate["viewerActions"] == []
    assert rate["suggestedNextStep"] == waypoint
    assert rate["onLessonTopic"] is False
    assert "not a claim about the current tracing" in rate["feedback"].lower()

    physiology = service.converse(
        "Why does atrial P activity precede the ventricular QRS physiologically?",
        _packet_with_rois(),
        {},
        [],
        mode="tutorial",
        lesson={"objectives": ["axis_normal"]},
        viewer_state={"pausedWaypoint": waypoint},
    )
    assert "av node" in physiology["tutorMessage"].lower()
    assert "qrs" in physiology["tutorMessage"].lower()
    assert physiology["viewerActions"] == []
    assert physiology["suggestedNextStep"] == waypoint
    assert physiology["onLessonTopic"] is False


def test_roi_selection_prefers_the_learners_selected_lead_and_nearest_beat() -> None:
    packet = _packet_with_rois()
    packet["ptbxl_plus"]["fiducials"]["rois"] = [
        {"concept": "qrs_complex", "lead": "II", "label": "QRS II early",
         "timeStartSec": 0.30, "timeEndSec": 0.40, "ampMinMv": -0.5, "ampMaxMv": 1.0},
        {"concept": "qrs_complex", "lead": "I", "label": "QRS I early",
         "timeStartSec": 0.32, "timeEndSec": 0.42, "ampMinMv": -0.5, "ampMaxMv": 1.0},
        {"concept": "qrs_complex", "lead": "I", "label": "QRS I selected beat",
         "timeStartSec": 4.32, "timeEndSec": 4.42, "ampMinMv": -0.5, "ampMaxMv": 1.0},
    ]

    roi = _roi_for_concept(
        packet,
        "right_bundle_branch_block",
        {"selectedPoint": {"lead": "I", "timeSec": 4.38}},
    )

    assert roi is not None
    assert roi["label"] == "QRS I selected beat"
