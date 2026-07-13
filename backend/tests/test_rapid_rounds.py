from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app import rapid_routes
from app.main import app, repo
from app.rapid_routes import _BroadRoundOrderCache, _broad_corpus_selection, _public_round


PASSWORD = "Sup3r-Secret-Pw!"


def _register(client: TestClient, prefix: str = "rapid") -> dict:
    username = f"{prefix}_{uuid.uuid4().hex[:10]}"
    response = client.post(
        "/auth/register", json={"username": username, "password": PASSWORD}
    )
    assert response.status_code == 200, response.text
    return {"username": username, **response.json()["user"]}


def _start(client: TestClient, **overrides) -> dict:
    body = {
        "learnerId": "demo",
        "pace": "ward",
        "length": 5,
        "contextKey": "?focus=normal_ecg",
        "exclusions": [],
    }
    body.update(overrides)
    response = client.post("/rapid/rounds", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def _point_from_packet(packet: dict) -> dict:
    roi = next(
        row for row in packet["ptbxl_plus"]["fiducials"]["rois"]
        if row["lead"] == "II" and row["concept"] == "qrs_complex"
    )
    return {
        "lead": "II",
        "timeSec": (roi["timeStartSec"] + roi["timeEndSec"]) / 2,
        "amplitudeMv": (roi["ampMinMv"] + roi["ampMaxMv"]) / 2,
    }


def _complete_sweep(case: dict, selected: list[str]) -> dict:
    features = {
        **((case.get("ptbxl_plus") or {}).get("features") or {}),
        **((case.get("ptbxl_plus") or {}).get("measurements") or {}),
    }
    rate = features.get("heart_rate")
    return {
        "framework": "clerkship",
        "rate": f"{round(float(rate))} bpm" if isinstance(rate, (int, float)) else "rate assessed",
        "rhythm": "rhythm assessed from atrial and ventricular timing",
        "axis": "axis assessed from limb-lead QRS polarity",
        "intervals": "PR, QRS, and QT intervals assessed",
        "conduction": "QRS width and terminal morphology assessed",
        "st_t": "ST segments and T waves assessed",
        "hypertrophy": "chamber voltage and morphology assessed",
        "synthesis": "Evidence-limited complete ECG synthesis with the supported findings selected.",
        "selectedConcepts": selected,
    }


def test_round_is_cookie_owned_and_hidden_from_another_user() -> None:
    with TestClient(app) as owner, TestClient(app) as other:
        _register(owner, "rapid_owner")
        _register(other, "rapid_other")
        started = _start(owner)
        round_id = started["round"]["roundId"]

        assert other.get(f"/rapid/rounds/{round_id}").status_code == 404
        assert other.get(f"/rapid/rounds/{round_id}/results").status_code == 404
        assert other.post(f"/rapid/rounds/{round_id}/next", json={}).status_code == 404
        assert other.get("/rapid/rounds/active").json()["round"] is None


def test_round_contract_supports_a_5000_unique_ecg_marathon() -> None:
    with TestClient(app) as client:
        _register(client, "rapid_marathon")
        started = _start(client, pace="untimed", length=5000)
        assert started["round"]["length"] == 5000
        assert started["round"]["servedCount"] == 0
        assert started["round"]["recentServed"] == []
        assert "served" not in started["round"]

        too_large = client.post(
            "/rapid/rounds",
            json={"pace": "untimed", "length": 5001, "exclusions": []},
        )
        assert too_large.status_code == 422


def test_public_round_metadata_bounds_the_5000_case_served_ledger() -> None:
    served = [f"ptbxl:{index:05d}" for index in range(5000)]
    session = {"roundId": "rr_scale", "position": 5000, "served": served}

    public = _public_round(session)

    assert "served" not in public
    assert public["servedCount"] == 5000
    assert public["recentServed"] == served[-25:]
    assert session["served"] == served


def test_broad_selector_can_reach_every_eligible_record_without_replacement() -> None:
    class Repo:
        def __init__(self) -> None:
            self.rows = [
                {"case_id": str(index), "teaching_tier": "A", "source": "ptbxl", "supported_objectives": ["rate"]}
                for index in range(20)
            ]

        def candidates(self, concept=None):
            assert concept is None
            return list(self.rows)

        def get_case(self, case_id):
            return {
                "case_id": case_id,
                "display_id": case_id,
                "source": "ptbxl",
                "teaching_tier": "A",
                    "supported_objectives": ["rate"],
                    "concept_confidence": {"rate": {"tier": "A", "score": 1.0}},
                    "waveform": {
                        "leads": [
                            "I", "II", "III", "aVR", "aVL", "aVF",
                            "V1", "V2", "V3", "V4", "V5", "V6",
                        ],
                        "sampling_frequency": 100,
                        "duration_sec": 10,
                    },
                    "clinical_stem": "",
                "ptbxl": {"report": ""},
            }

    repo = Repo()
    served: set[str] = set()
    for position in range(20):
        selection = _broad_corpus_selection(repo, served, f"round:{position}")
        case_id = selection["case"]["caseId"]
        assert case_id not in served
        served.add(case_id)
    assert served == {str(index) for index in range(20)}
    assert _broad_corpus_selection(repo, served, "exhausted")["case"] is None


def test_cached_preordered_path_does_not_requery_or_resort_and_rebuilds_deterministically(
    monkeypatch,
) -> None:
    class Repo:
        def __init__(self) -> None:
            self.query_count = 0
            self.packet_count = 0
            self.rows = [
                {"case_id": str(index), "unused_mutable_field": [index]}
                for index in range(257)
            ]

        def candidates(self, concept=None):
            assert concept is None
            self.query_count += 1
            return list(reversed(self.rows))

        def get_case(self, case_id):
            self.packet_count += 1
            return {
                "case_id": case_id,
                "display_id": case_id,
                "source": "ptbxl",
                "teaching_tier": "A",
                "supported_objectives": ["rate"],
                "concept_confidence": {"rate": {"tier": "A", "score": 1.0}},
                "waveform": {
                    "leads": [
                        "I", "II", "III", "aVR", "aVL", "aVF",
                        "V1", "V2", "V3", "V4", "V5", "V6",
                    ],
                    "sampling_frequency": 100,
                    "duration_sec": 10,
                },
                "clinical_stem": "",
                "ptbxl": {"report": ""},
            }

    repo = Repo()
    real_sort = rapid_routes._stable_round_order
    sort_count = 0

    def counted_sort(candidates, round_id):
        nonlocal sort_count
        sort_count += 1
        return real_sort(candidates, round_id)

    monkeypatch.setattr(rapid_routes, "_stable_round_order", counted_sort)
    cache = _BroadRoundOrderCache(repo, max_rounds=2)

    first_order, first_rejected = cache.get("rr_restart_stable")
    cached_order, cached_rejected = cache.get("rr_restart_stable")
    assert cached_order is first_order
    assert cached_rejected is first_rejected
    assert repo.query_count == 1
    assert sort_count == 1

    served: set[str] = set()
    first = _broad_corpus_selection(
        repo,
        served,
        "ignored-when-preordered",
        ordered_candidates=cached_order,
        rejected_candidates=cached_rejected,
    )
    served.add(first["case"]["caseId"])
    second = _broad_corpus_selection(
        repo,
        served,
        "ignored-when-preordered",
        ordered_candidates=cached_order,
        rejected_candidates=cached_rejected,
    )
    assert second["case"]["caseId"] != first["case"]["caseId"]
    assert repo.query_count == 1
    assert sort_count == 1
    assert repo.packet_count == 2

    # LRU release/restart may discard ephemeral rejections, but rebuilding from
    # the durable round id yields exactly the same permutation. The process-wide
    # lightweight index also remains cached.
    cache.release("rr_restart_stable")
    rebuilt_order, rebuilt_rejected = cache.get("rr_restart_stable")
    assert rebuilt_order is not first_order
    assert rebuilt_order == first_order
    assert rebuilt_rejected == set()
    assert repo.query_count == 1
    assert sort_count == 2

    # A fresh cache models an application restart. Even if the database returns
    # the candidate rows in the opposite physical order, the round-id hash order
    # and therefore the next durable-ledger choice remain identical.
    repo.rows.reverse()
    restarted_cache = _BroadRoundOrderCache(repo, max_rounds=2)
    restarted_order, _ = restarted_cache.get("rr_restart_stable")
    assert restarted_order == first_order
    assert repo.query_count == 2
    assert sort_count == 3


def test_pending_case_and_original_deadline_resume_across_login_and_replay() -> None:
    with TestClient(app) as first, TestClient(app) as second:
        user = _register(first, "rapid_resume")
        started = _start(first, pace="emergency", length=5, exclusions=["never-serve-me"])
        round_id = started["round"]["roundId"]
        first_case = first.post(f"/rapid/rounds/{round_id}/next", json={}).json()
        activated = first.post(
            f"/rapid/rounds/{round_id}/next", json={"activate": True}
        ).json()
        deadline = activated["round"]["pendingDeadlineAt"]
        case_id = activated["current"]["case"]["caseId"]
        assert activated["round"]["assessmentScope"] == "dominant_finding"
        assert activated["round"]["deadlineSeconds"] == 20
        assert activated["round"]["exclusions"] == ["never-serve-me"]
        assert first_case["current"]["case"]["caseId"] == case_id

        login = second.post(
            "/auth/login", json={"username": user["username"], "password": PASSWORD}
        )
        assert login.status_code == 200
        resumed = second.get("/rapid/rounds/active").json()
        assert resumed["round"]["roundId"] == round_id
        assert resumed["current"]["case"]["caseId"] == case_id
        assert resumed["round"]["pendingDeadlineAt"] == deadline
        replayed_next = second.post(f"/rapid/rounds/{round_id}/next", json={}).json()
        assert replayed_next["current"]["case"]["caseId"] == case_id
        assert replayed_next["round"]["pendingDeadlineAt"] == deadline


def test_submit_is_exactly_once_and_records_server_verified_context_and_receipts() -> None:
    with TestClient(app) as client:
        user = _register(client, "rapid_submit")
        started = _start(client, pace="untimed", length=5, focusConcept="normal_ecg")
        round_id = started["round"]["roundId"]
        pending = client.post(f"/rapid/rounds/{round_id}/next", json={}).json()
        case_id = pending["current"]["case"]["caseId"]
        packet = pending["current"]["packet"]
        client.post(f"/rapid/rounds/{round_id}/next", json={"activate": True})
        target = pending["targetObjectives"][0]
        body = {
            "caseId": case_id,
            "structuredAnswer": {
                "framework": "clerkship",
                "selectedConcepts": [target],
                "synthesis": target.replace("_", " "),
            },
            "freeTextAnswer": target.replace("_", " "),
            "confidence": 4,
            "traceEvidence": {"mode": "point", "point": _point_from_packet(packet)},
        }
        first = client.post(f"/rapid/rounds/{round_id}/submit", json=body)
        second = client.post(f"/rapid/rounds/{round_id}/submit", json=body)
        assert first.status_code == second.status_code == 200
        assert first.json()["replay"] is False
        assert second.json()["replay"] is True
        assert first.json()["answer"]["attemptId"] == second.json()["answer"]["attemptId"]
        assert first.json()["resultCount"] == 1
        assert first.json()["resultsTruncated"] is False
        assert first.json()["answer"]["result"]["pace"] == "untimed"
        assert first.json()["answer"]["result"]["assessmentScope"] == "full_read"
        assert first.json()["answer"]["result"]["startedAt"]
        assert first.json()["answer"]["result"]["deadlineAt"] is None
        assert first.json()["answer"]["grade"]["masteryDelta"] == {}
        assert first.json()["answer"]["grade"]["legacyObjectiveMasterySuppressed"] is True
        assert first.json()["answer"]["tutor"] is None

        accepted = [row for row in first.json()["receipts"] if row["accepted"]]
        assert any(row["concept"] == target and row["subskill"] == "recognize" for row in accepted)
        assert any(row["concept"] == "qrs_complex" and row["subskill"] == "localize" for row in accepted)
        profile = client.get(f"/learners/{user['userId']}").json()
        target_row = next(
            row for row in profile["subskillMastery"]
            if row["concept"] == target and row["subskill"] == "recognize"
        )
        assert target_row["independentAttempts"] == 1
        assert target_row["distinctSuccessfulEcgs"] == 1
        assert target_row["nextDueAt"] is not None
        assert profile["attemptCount"] == 1
        ledger = client.get(f"/rapid/rounds/{round_id}/results?offset=0&limit=5000")
        assert ledger.status_code == 200
        assert ledger.json()["total"] == 1
        assert ledger.json()["results"][0]["caseId"] == case_id


def test_axis_text_or_unsupported_explicit_axis_cannot_create_axis_mastery() -> None:
    with TestClient(app) as client:
        user = _register(client, "rapid_axis")
        started = _start(client, pace="untimed", length=5, focusConcept="normal_ecg")
        round_id = started["round"]["roundId"]
        pending = client.post(f"/rapid/rounds/{round_id}/next", json={}).json()
        case_id = pending["current"]["case"]["caseId"]
        point = _point_from_packet(pending["current"]["packet"])
        response = client.post(
            f"/rapid/rounds/{round_id}/submit",
            json={
                "caseId": case_id,
                "structuredAnswer": {
                    "framework": "clerkship",
                    "axis": "definite right axis deviation",
                    "synthesis": "right axis deviation",
                    "selectedConcepts": ["right_axis_deviation"],
                },
                "freeTextAnswer": "Definite right axis deviation.",
                "confidence": 5,
                "traceEvidence": {"mode": "point", "point": point},
            },
        )
        assert response.status_code == 200, response.text
        axis_receipt = next(
            row for row in response.json()["receipts"]
            if row["concept"] == "right_axis_deviation"
        )
        assert axis_receipt["accepted"] is False
        assert axis_receipt["evidenceLevel"] == "none"
        profile = client.get(f"/learners/{user['userId']}").json()
        assert not any(
            row["concept"] == "right_axis_deviation" and row["subskill"] == "recognize"
            for row in profile["subskillMastery"]
        )
        legacy_axis = next(row for row in profile["mastery"] if row["objective"] == "right_axis_deviation")
        assert legacy_axis["attempts"] == 0
        assert legacy_axis["mastery"] == 0.25


def test_missed_supported_focus_records_one_verified_retention_lapse() -> None:
    with TestClient(app) as client:
        user = _register(client, "rapid_lapse")
        started = _start(client, pace="untimed", length=1, focusConcept="normal_ecg")
        round_id = started["round"]["roundId"]
        pending = client.post(f"/rapid/rounds/{round_id}/next", json={}).json()
        case_id = pending["current"]["case"]["caseId"]
        point = _point_from_packet(pending["current"]["packet"])
        response = client.post(
            f"/rapid/rounds/{round_id}/submit",
            json={
                "caseId": case_id,
                "structuredAnswer": {
                    "framework": "clerkship",
                    "selectedConcepts": [],
                    "synthesis": "Unable to identify the dominant finding.",
                },
                "freeTextAnswer": "Unable to identify the dominant finding.",
                "confidence": 4,
                "traceEvidence": {"mode": "point", "point": point},
            },
        )
        assert response.status_code == 200, response.text
        lapse = next(
            receipt for receipt in response.json()["receipts"]
            if receipt["concept"] == "normal_ecg" and receipt.get("correct") is False
        )
        assert lapse["accepted"] is True
        assert lapse["evidenceLevel"] == "independent_transfer"

        profile = client.get(f"/learners/{user['userId']}").json()
        row = next(
            item for item in profile["subskillMastery"]
            if item["concept"] == "normal_ecg" and item["subskill"] == "recognize"
        )
        assert row["lapses"] == 1
        assert row["lastIndependentCorrect"] is False
        assert row["distinctEligibleEcgs"] == 1


def test_prescribed_complete_sweep_emits_exact_independent_synthesis_receipt() -> None:
    with TestClient(app) as client:
        user = _register(client, "rapid_synthesis")
        started = _start(
            client,
            pace="untimed",
            length=1,
            focusConcept="normal_ecg",
            focusSubskill="synthesize",
            contextKey=(
                "?focus=normal_ecg&receiptConcept=integrated_interpretation"
                "&subskill=synthesize&returnTo=%2Freview"
            ),
        )
        round_id = started["round"]["roundId"]
        pending = client.post(f"/rapid/rounds/{round_id}/next", json={}).json()
        case_id = pending["current"]["case"]["caseId"]
        packet = pending["current"]["packet"]
        case = repo.get_case(case_id)
        selected = list(dict.fromkeys(case.get("supported_objectives") or []))
        response = client.post(
            f"/rapid/rounds/{round_id}/submit",
            json={
                "caseId": case_id,
                "structuredAnswer": _complete_sweep(case, selected),
                "freeTextAnswer": "Evidence-limited complete ECG synthesis with supported findings.",
                "confidence": 4,
                "traceEvidence": {"mode": "point", "point": _point_from_packet(packet)},
            },
        )
        assert response.status_code == 200, response.text
        receipt = next(
            row for row in response.json()["receipts"]
            if row["concept"] == "integrated_interpretation"
            and row["subskill"] == "synthesize"
        )
        assert receipt["accepted"] is True
        assert receipt["correct"] is True
        assert receipt["evidenceLevel"] == "independent_transfer"
        profile = client.get(f"/learners/{user['userId']}").json()
        row = next(
            item for item in profile["subskillMastery"]
            if item["concept"] == "integrated_interpretation"
            and item["subskill"] == "synthesize"
        )
        assert row["independentAttempts"] == 1
        assert row["distinctSuccessfulEcgs"] == 1


def test_synthesis_free_text_without_complete_sweep_cannot_create_receipt() -> None:
    with TestClient(app) as client:
        _register(client, "rapid_synth_short")
        started = _start(
            client,
            pace="untimed",
            length=1,
            focusConcept="normal_ecg",
            focusSubskill="synthesize",
            contextKey=(
                "?focus=normal_ecg&receiptConcept=integrated_interpretation"
                "&subskill=synthesize"
            ),
        )
        round_id = started["round"]["roundId"]
        pending = client.post(f"/rapid/rounds/{round_id}/next", json={}).json()
        case_id = pending["current"]["case"]["caseId"]
        response = client.post(
            f"/rapid/rounds/{round_id}/submit",
            json={
                "caseId": case_id,
                "structuredAnswer": {
                    "framework": "clerkship",
                    "selectedConcepts": ["normal_ecg"],
                    "synthesis": "A long confident free-text synthesis without the structured sweep.",
                },
                "freeTextAnswer": "A long confident free-text synthesis without the structured sweep.",
                "confidence": 5,
                "traceEvidence": {
                    "mode": "point",
                    "point": _point_from_packet(pending["current"]["packet"]),
                },
            },
        )
        assert response.status_code == 200, response.text
        receipt = next(
            row for row in response.json()["receipts"]
            if row["concept"] == "integrated_interpretation"
            and row["subskill"] == "synthesize"
        )
        assert receipt["accepted"] is False
        assert receipt["evidenceLevel"] == "none"
