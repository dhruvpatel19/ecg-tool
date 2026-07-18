from __future__ import annotations

import hashlib
import json
import uuid

from fastapi.testclient import TestClient
import pytest

from app import rapid_routes
from app.ingest.dangerous_arrhythmia import (
    FragmentSpec,
    HeaderSummary,
    SOURCE_ID,
    SOURCE_FS,
    build_fragment_packet,
    build_release_manifest,
)
from app.main import app, repo, store
from app.ontology import concept_label
from app.rapid_rhythm_supplement import (
    RUNTIME_LEAD,
    RUNTIME_MANIFEST_NAME,
    RapidRhythmSupplement,
    build_runtime_manifest,
    project_runtime_packet,
)
from app.objectives import (
    OBJECTIVES,
    audited_source_packet_supports_objective,
    objective_runtime_availability,
)
from app.source_policy import packet_allows_learning_evidence, packet_mode_policy
from app.store.rhythm_stream_store import RhythmStreamStore
from app.store.waveform_store import LocalWaveformStore


def _packet(code: str, suffix: str) -> tuple[dict, list[float]]:
    data_sha = hashlib.sha256(f"data-{suffix}".encode()).hexdigest()
    spec = FragmentSpec(
        relative_record_path=f"1_Dangerous_VFL_VF/frag/418_C_{code}_277s_frag",
        source_parent_record="418_C",
        source_offset_text="277",
        source_class="1_Dangerous_VFL_VF",
        rhythm_code=code,
        header_sha256=hashlib.sha256(f"header-{suffix}".encode()).hexdigest(),
        data_sha256=data_sha,
    )
    header = HeaderSummary(SOURCE_FS, 500, "1")
    offset = (int(hashlib.sha256(suffix.encode()).hexdigest()[:4], 16) % 17) / 1000
    values = [((index % 31) - 15) / 100 + offset for index in range(header.sample_count)]
    return build_fragment_packet(spec, values, header), values


def _supplement(tmp_path, codes: tuple[str, ...] = ("VF", "VTHR", "VTTdP")):
    root = tmp_path / "rapid_rhythm_supplement"
    store = RhythmStreamStore(root / "rhythm_streams.db")
    waveforms = LocalWaveformStore(root / "waveforms", leads=(RUNTIME_LEAD,))
    packets = []
    for index, code in enumerate(codes):
        packet, values = _packet(code, str(index))
        store.upsert(packet)
        waveforms.write(packet["case_id"], {RUNTIME_LEAD: values})
        packets.append(packet)
    source_manifest_path = root / "manifest.json"
    source_manifest_path.write_text(
        json.dumps(build_release_manifest(packets), sort_keys=True),
        encoding="utf-8",
    )
    runtime_manifest = build_runtime_manifest(
        source_manifest_path=source_manifest_path,
        packets=packets,
    )
    runtime_manifest_path = root / RUNTIME_MANIFEST_NAME
    runtime_manifest_path.write_text(
        json.dumps(runtime_manifest, sort_keys=True),
        encoding="utf-8",
    )
    return root, packets, runtime_manifest


def test_runtime_projection_is_rapid_only_and_never_mints_management_evidence() -> None:
    packet, _ = _packet("VF", "vf")
    assert packet_mode_policy(packet, "rapid").allowed is False

    projected = project_runtime_packet(packet)
    assert packet_mode_policy(projected, "rapid").allowed is True
    assert packet_mode_policy(projected, "training").allowed is False
    assert projected["waveform"]["leads"] == [RUNTIME_LEAD]
    assert projected["supported_objectives"] == ["ventricular_fibrillation"]
    eligibility = projected["educational_eligibility"]
    assert eligibility["masteryEvidenceEligible"] is True
    assert eligibility["clinicalManagementEligible"] is False
    assert eligibility["shockabilityClassificationEligible"] is False
    assert eligibility["treatmentOrActionSequenceEligible"] is False
    assert packet_allows_learning_evidence(
        projected, "rapid", "ventricular_fibrillation", "recognize"
    ).allowed is True
    assert packet_allows_learning_evidence(
        projected, "rapid", "ventricular_fibrillation", "apply_in_context"
    ).allowed is False


def test_source_torsades_label_projects_to_polymorphic_vt_with_qt_limit() -> None:
    packet, _ = _packet("VTTdP", "tdp")
    projected = project_runtime_packet(packet)
    assert projected["supported_objectives"] == [
        "polymorphic_ventricular_tachycardia"
    ]
    report = projected["ptbxl"]["report"].casefold()
    assert "preceding long-qt evidence" in report
    assert projected["source_labels"]["rhythm"]["sourceCanonicalRhythmId"] == (
        "torsades_de_pointes"
    )


def test_manifest_gated_reader_indexes_only_reviewed_targets_and_mlII(tmp_path) -> None:
    root, packets, runtime_manifest = _supplement(tmp_path)
    reader = RapidRhythmSupplement(root)
    assert reader.count == 3
    assert reader.target_counts == {
        "polymorphic_ventricular_tachycardia": 1,
        "ventricular_fibrillation": 1,
        "ventricular_tachycardia": 1,
    }
    case = reader.get_case(packets[0]["case_id"])
    assert case is not None
    waveform = reader.get_waveform_window(case["case_id"], max_points=100)
    assert waveform is not None
    assert [row["lead"] for row in waveform["leads"]] == [RUNTIME_LEAD]
    assert len(waveform["leads"][0]["points"]) <= 101
    assert reader.get_waveform_window(case["case_id"], leads=["II"]) is None
    assert runtime_manifest["actionQuestionsRequireSeparateAuthoredContext"] is True
    assert runtime_manifest["actionQuestionsFormativeOnly"] is True


def test_parent_manifest_reference_is_checksum_and_count_pinned(tmp_path) -> None:
    root, _, runtime_manifest = _supplement(tmp_path)
    runtime_path = root / RUNTIME_MANIFEST_NAME
    expected = {
        "path": "rapid_rhythm_supplement",
        "sourceId": "ecg-fragment-dangerous-arrhythmia",
        "fragmentCount": runtime_manifest["fragmentCount"],
        "runtimeManifestSha256": hashlib.sha256(runtime_path.read_bytes()).hexdigest(),
    }
    assert RapidRhythmSupplement(root, expected=expected).count == 3

    forged = dict(expected)
    forged["runtimeManifestSha256"] = "0" * 64
    with pytest.raises(ValueError, match="do not match"):
        RapidRhythmSupplement(root, expected=forged)


def test_reader_fails_closed_if_any_waveform_is_missing(tmp_path) -> None:
    root, packets, _ = _supplement(tmp_path, ("VF",))
    waveforms = LocalWaveformStore(root / "waveforms", leads=(RUNTIME_LEAD,))
    waveforms.path_for(packets[0]["case_id"]).unlink()
    with pytest.raises(ValueError, match="unreadable"):
        RapidRhythmSupplement(root)


def test_runtime_objective_unlocks_only_from_the_manifest_promoted_fragment() -> None:
    data_sha = hashlib.sha256(b"objective-data").hexdigest()
    spec = FragmentSpec(
        relative_record_path="1_Dangerous_VFL_VF/frag/418_C_VF_277s_frag",
        source_parent_record="418_C",
        source_offset_text="277",
        source_class="1_Dangerous_VFL_VF",
        rhythm_code="VF",
        header_sha256=hashlib.sha256(b"objective-header").hexdigest(),
        data_sha256=data_sha,
    )
    header = HeaderSummary(SOURCE_FS, SOURCE_FS * 2, "1")
    values = [((index % 31) - 15) / 100 for index in range(header.sample_count)]
    projected = project_runtime_packet(build_fragment_packet(spec, values, header))
    objective_id = "ventricular_fibrillation"

    class Repo:
        def candidates(self, concept_id=None):
            return []

        def rapid_rhythm_candidates(self, concept_id=None):
            return (
                [{"case_id": projected["case_id"], "source": projected["source"]}]
                if concept_id == objective_id
                else []
            )

        def get_case(self, case_id):
            return projected if case_id == projected["case_id"] else None

    assert audited_source_packet_supports_objective(projected, objective_id) is True
    available = objective_runtime_availability(OBJECTIVES[objective_id], Repo())
    assert available.evidence_ceiling == "eligible_real_case"
    assert available.eligible_case_ids == (projected["case_id"],)
    assert available.eligible_subskills == ("recognize", "discriminate")

    projected["educational_eligibility"]["clinicalManagementEligible"] = True
    assert audited_source_packet_supports_objective(projected, objective_id) is False


def test_reader_fails_closed_if_waveform_bytes_do_not_match_packet_fingerprint(
    tmp_path,
) -> None:
    root, packets, _ = _supplement(tmp_path, ("VF",))
    waveforms = LocalWaveformStore(root / "waveforms", leads=(RUNTIME_LEAD,))
    values = waveforms.read(packets[0]["case_id"], (RUNTIME_LEAD,))[RUNTIME_LEAD]
    values[0] += 0.01
    waveforms.write(packets[0]["case_id"], {RUNTIME_LEAD: values})
    with pytest.raises(ValueError, match="unreadable"):
        RapidRhythmSupplement(root)


def test_reader_fails_closed_if_same_target_source_codes_are_swapped(tmp_path) -> None:
    """VTHR/VTLR share a learner target, so counts alone cannot detect a swap."""

    root, packets, _ = _supplement(tmp_path, ("VTHR", "VTLR"))
    rhythm_store = RhythmStreamStore(root / "rhythm_streams.db")
    first = dict(packets[0])
    second = dict(packets[1])
    first["source_labels"] = json.loads(json.dumps(first["source_labels"]))
    second["source_labels"] = json.loads(json.dumps(second["source_labels"]))
    first["source_labels"]["rhythm"]["rhythmCode"] = "VTLR"
    second["source_labels"]["rhythm"]["rhythmCode"] = "VTHR"
    rhythm_store.upsert(first)
    rhythm_store.upsert(second)
    with pytest.raises(ValueError, match="content index"):
        RapidRhythmSupplement(root)


PASSWORD = "Sup3r-Secret-Pw!"


def _register(client: TestClient, prefix: str) -> dict:
    response = client.post(
        "/auth/register",
        json={
            "username": f"{prefix[:18]}_{uuid.uuid4().hex[:10]}",
            "password": PASSWORD,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["user"]


def _start_emergency(client: TestClient, **overrides) -> dict:
    body = {
        "learnerId": "demo",
        "pace": "emergency",
        "length": 1,
        "contextKey": "",
        "exclusions": [],
        "contractVersion": "mixed-v2",
        "practiceMode": "emergency",
        "questionDepth": "focused",
    }
    body.update(overrides)
    response = client.post("/rapid/rounds", json=body)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize(
    ("depth", "expected_count"),
    (("quick", 1), ("focused", 2), ("complete", 3)),
)
def test_emergency_depths_keep_the_strip_to_bounded_rapid_tasks(
    tmp_path, depth: str, expected_count: int
) -> None:
    root, packets, _ = _supplement(tmp_path, ("VF",))
    case = RapidRhythmSupplement(root).get_case(packets[0]["case_id"])
    assert case is not None
    session = {
        "roundId": f"depth-{depth}",
        "position": 0,
        "deadlineSeconds": 75,
        "contextKey": rapid_routes._with_round_contract(
            "",
            contract_version="mixed-v2",
            practice_mode="emergency",
            question_depth=depth,
        ),
    }
    packet = rapid_routes._build_mixed_task_packet(
        case,
        session,
        focus_concept="ventricular_fibrillation",
    )
    assert packet["display"] == {"kind": "rhythm_strip", "leads": [RUNTIME_LEAD]}
    assert len(packet["tasks"]) == expected_count
    assert packet["tasks"][0]["type"] == "short_answer"
    assert all(task["type"] != "full_interpretation" for task in packet["tasks"])
    if expected_count > 1:
        assert [
            bool((task.get("grading") or {}).get("formativeOnly"))
            for task in packet["tasks"]
        ] == ([False, True] if expected_count == 2 else [False, True, True])


def test_ordinary_mixed_round_never_queries_or_selects_rhythm_supplement(
    tmp_path, monkeypatch
) -> None:
    root, _, _ = _supplement(tmp_path, ("VF", "VTHR", "VTTdP"))
    reader = RapidRhythmSupplement(root)
    candidate_calls: list[str | None] = []
    original_candidates = reader.candidates

    def tracked_candidates(objective_id: str | None = None):
        candidate_calls.append(objective_id)
        return original_candidates(objective_id)

    monkeypatch.setattr(reader, "candidates", tracked_candidates)
    monkeypatch.setattr(repo, "rapid_rhythm_supplement", reader)
    supplement_ids = {row["case_id"] for row in original_candidates()}

    with TestClient(app) as client:
        _register(client, "rapid_ordinary_no_supplement")
        response = client.post(
            "/rapid/rounds",
            json={
                "learnerId": "demo",
                "pace": "untimed",
                "length": 1,
                "contextKey": "",
                "exclusions": [],
                "contractVersion": "mixed-v2",
                "practiceMode": "mixed",
                "questionDepth": "quick",
            },
        )
        assert response.status_code == 200, response.text
        round_id = response.json()["round"]["roundId"]
        served = client.post(f"/rapid/rounds/{round_id}/next", json={})
        assert served.status_code == 200, served.text
        durable = store.get_rapid_round(round_id)
        assert durable is not None
        assert durable["pendingCaseId"] not in supplement_ids
        assert candidate_calls == []
        assert client.post(f"/rapid/rounds/{round_id}/abandon").status_code == 200


def test_emergency_round_is_blinded_waveform_bound_and_mastery_scoped(
    tmp_path, monkeypatch
) -> None:
    root, _, _ = _supplement(tmp_path, ("VF", "VTHR", "VTTdP"))
    reader = RapidRhythmSupplement(root)
    monkeypatch.setattr(repo, "rapid_rhythm_supplement", reader)

    with TestClient(app) as client:
        _register(client, "rapid_emergency_contract")
        started = _start_emergency(client, questionDepth="complete")
        supplement_status = started["rhythmSupplement"]
        assert supplement_status["available"] is True
        assert supplement_status["count"] == reader.count
        assert supplement_status["targetCounts"] == reader.target_counts
        assert supplement_status["runtimeScope"] == "rapid_emergency_rhythm"
        assert supplement_status["singleLead"] == RUNTIME_LEAD
        assert supplement_status["managementQuestionsFormativeOnly"] is True
        round_id = started["round"]["roundId"]

        served_response = client.post(f"/rapid/rounds/{round_id}/next", json={})
        assert served_response.status_code == 200, served_response.text
        served = served_response.json()
        current = served["current"]
        public_ref = current["case"]["caseId"]
        durable = store.get_rapid_round(round_id)
        assert durable is not None
        canonical_id = str(durable["pendingCaseId"])
        private_case = reader.get_case(canonical_id)
        assert private_case is not None
        objective = str(private_case["supported_objectives"][0])

        assert current["case"]["source"] == "audited_rhythm_stream"
        assert current["packet"]["source"] == "audited_rhythm_stream"
        assert current["taskPacket"]["display"] == {
            "kind": "rhythm_strip",
            "leads": [RUNTIME_LEAD],
        }
        assert len(current["taskPacket"]["tasks"]) == 3
        pending_json = json.dumps(current, sort_keys=True)
        for secret_value in (
            canonical_id,
            SOURCE_ID,
            "record_identity",
            "source_provenance",
            "rhythmCode",
            '"grading"',
            "correctOptionId",
        ):
            assert secret_value not in pending_json

        waveform = client.get(
            f"/rapid/rounds/{round_id}/waveform/{public_ref}",
            params={"leads": RUNTIME_LEAD, "start": 0, "end": 2, "maxPoints": 250},
        )
        assert waveform.status_code == 200, waveform.text
        waveform_body = waveform.json()
        assert waveform_body["caseId"] == public_ref
        assert [row["lead"] for row in waveform_body["leads"]] == [RUNTIME_LEAD]
        assert canonical_id not in json.dumps(waveform_body)
        assert client.get(
            f"/rapid/rounds/{round_id}/waveform/{public_ref}",
            params={"leads": "II"},
        ).status_code == 404

        private_packet = durable["pendingTestedObjectiveManifest"]["taskPacket"]
        responses: dict[str, str] = {}
        made_formative_error = False
        for task in private_packet["tasks"]:
            grading = task["grading"]
            if task["type"] == "short_answer":
                responses[task["id"]] = concept_label(str(grading["objectiveId"]))
            elif grading.get("formativeOnly") and not made_formative_error:
                responses[task["id"]] = next(
                    option["id"]
                    for option in task["options"]
                    if option["id"] != grading["correctOptionId"]
                )
                made_formative_error = True
            else:
                responses[task["id"]] = str(grading["correctOptionId"])
        activated = client.post(
            f"/rapid/rounds/{round_id}/next", json={"activate": True}
        )
        assert activated.status_code == 200, activated.text
        submitted = client.post(
            f"/rapid/rounds/{round_id}/submit",
            json={"caseId": public_ref, "taskResponses": responses},
        )
        assert submitted.status_code == 200, submitted.text
        answer = submitted.json()["answer"]
        feedback = answer["grade"]["taskFeedback"]
        assert len(feedback) == 3
        assert [row["correct"] for row in feedback] == [True, False, True]
        assert [row["formativeOnly"] for row in feedback] == [False, True, True]
        assert all(row.get("referenceLabel") for row in feedback[1:])
        assert answer["grade"]["score"] == 1.0
        assert answer["result"]["score"] == 1.0

        receipts = submitted.json()["receipts"]
        recognition = [
            row
            for row in receipts
            if row["concept"] == objective and row["subskill"] == "recognize"
        ]
        assert len(recognition) == 1
        assert recognition[0]["accepted"] is True
        assert recognition[0]["evidenceLevel"] == "independent_transfer"
        assert recognition[0]["registryVersion"]
        formative = [
            row
            for row in receipts
            if row["concept"] == "resuscitation_source_boundary"
        ]
        assert {(row["subskill"], row["accepted"], row["evidenceLevel"]) for row in formative} == {
            ("apply_in_context", False, "none"),
            ("calibrate_confidence", False, "none"),
        }
        outcomes = answer["result"]["competencyOutcomes"]
        assert [row["formativeOnly"] for row in outcomes] == [False, True, True]
        feedback_json = json.dumps(submitted.json()["current"], sort_keys=True)
        assert canonical_id not in feedback_json
        assert SOURCE_ID not in feedback_json
        assert submitted.json()["current"]["packet"]["source"] == "audited_rhythm_stream"

        finished = client.post(f"/rapid/rounds/{round_id}/next", json={})
        assert finished.status_code == 200, finished.text
        assert finished.json()["round"]["status"] == "complete"

        sessions = client.get("/learning/sessions")
        assert sessions.status_code == 200, sessions.text
        rapid_session = next(
            item for item in sessions.json()["items"] if item["mode"] == "rapid"
        )
        replay = client.get(
            f"/learning/sessions/{rapid_session['sessionRef']}/attempts/1/replay"
        )
        assert replay.status_code == 200, replay.text
        replay_body = replay.json()
        assert replay_body["waveformPresentation"] == {
            "kind": "rhythm_strip",
            "leads": [RUNTIME_LEAD],
        }
        assert canonical_id not in json.dumps(replay_body)
        replay_waveform = client.get(
            f"/learning/sessions/{rapid_session['sessionRef']}/attempts/1/"
            f"waveform/{replay_body['ecgRef']}",
            params={"leads": RUNTIME_LEAD, "start": 0, "end": 2, "maxPoints": 250},
        )
        assert replay_waveform.status_code == 200, replay_waveform.text
        assert [row["lead"] for row in replay_waveform.json()["leads"]] == [
            RUNTIME_LEAD
        ]
        assert canonical_id not in json.dumps(replay_waveform.json())


def test_emergency_focused_handoff_filters_the_first_strip_to_exact_target(
    tmp_path, monkeypatch
) -> None:
    root, _, _ = _supplement(tmp_path, ("VF", "VTHR", "VTTdP"))
    reader = RapidRhythmSupplement(root)
    monkeypatch.setattr(repo, "rapid_rhythm_supplement", reader)
    target = "polymorphic_ventricular_tachycardia"

    with TestClient(app) as client:
        _register(client, "rapid_emergency_focus")
        started = _start_emergency(
            client,
            focusConcept=target,
            focusSubskill="recognize",
            questionDepth="quick",
        )
        round_id = started["round"]["roundId"]
        served = client.post(f"/rapid/rounds/{round_id}/next", json={})
        assert served.status_code == 200, served.text
        durable = store.get_rapid_round(round_id)
        assert durable is not None
        selected = reader.get_case(str(durable["pendingCaseId"]))
        assert selected is not None
        assert selected["supported_objectives"] == [target]
        task = durable["pendingTestedObjectiveManifest"]["taskPacket"]["tasks"][0]
        assert task["grading"] == {
            "kind": "concept_text",
            "objectiveId": target,
            "subskill": "recognize",
        }
        assert client.post(f"/rapid/rounds/{round_id}/abandon").status_code == 200


def test_emergency_start_fails_closed_without_current_contract_or_supplement(
    tmp_path, monkeypatch
) -> None:
    root, _, _ = _supplement(tmp_path, ("VF",))
    reader = RapidRhythmSupplement(root)
    monkeypatch.setattr(repo, "rapid_rhythm_supplement", reader)

    with TestClient(app) as client:
        _register(client, "rapid_emergency_guard")
        legacy = client.post(
            "/rapid/rounds",
            json={
                "learnerId": "demo",
                "pace": "emergency",
                "length": 1,
                "contractVersion": "legacy-v1",
                "practiceMode": "emergency",
                "questionDepth": "quick",
            },
        )
        assert legacy.status_code == 422
        assert legacy.json()["detail"]["code"] == "rapid_emergency_contract_required"

        wrong_focus = client.post(
            "/rapid/rounds",
            json={
                "learnerId": "demo",
                "pace": "emergency",
                "length": 1,
                "contractVersion": "mixed-v2",
                "practiceMode": "emergency",
                "questionDepth": "quick",
                "focusConcept": "atrial_fibrillation",
                "focusSubskill": "recognize",
            },
        )
        assert wrong_focus.status_code == 422
        assert wrong_focus.json()["detail"]["code"] == (
            "rapid_emergency_handoff_conflict"
        )

        monkeypatch.setattr(repo, "rapid_rhythm_supplement", None)
        unavailable = client.post(
            "/rapid/rounds",
            json={
                "learnerId": "demo",
                "pace": "emergency",
                "length": 1,
                "contractVersion": "mixed-v2",
                "practiceMode": "emergency",
                "questionDepth": "quick",
            },
        )
        assert unavailable.status_code == 409
        assert unavailable.json()["detail"]["code"] == (
            "rapid_emergency_rhythm_unavailable"
        )
