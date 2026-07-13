"""End-to-end Clinical Decisions shift flow + blinding + calibration label."""

from __future__ import annotations

import json
import uuid

from fastapi.testclient import TestClient

from app.clinical import grounding, shift
from app.clinical.clinical_grading import grade_clinical_answer
from app.clinical.schemas import ClinicalAnswer
from app.clinical.shift import calibration_label
from app.main import app, clinical_item_store, clinical_packet, store

client = TestClient(app)


def _answer(
    session_id: str,
    item_id: str,
    *,
    answer_time_ms: int = 4200,
    headers=None,
    test_client: TestClient = client,
):
    test_client.post(
        f"/clinical/shift/{session_id}/phase",
        json={"itemId": item_id, "phase": "orient"},
        headers=headers or {},
    )
    test_client.post(
        f"/clinical/shift/{session_id}/context",
        json={
            "itemId": item_id,
            "answer": {"firstLookFinding": "uncertain", "firstLookConfidence": 3},
        },
        headers=headers or {},
    )
    return test_client.post(
        f"/clinical/shift/{session_id}/answer",
        json={
            "itemId": item_id,
            "answer": {"confidence": 3, "answerTimeMs": answer_time_ms},
        },
        headers=headers or {},
    )


def _set_mastery(learner_id: str, values: dict[str, float]) -> None:
    store.ensure_profile(learner_id)
    with store.connect() as conn:
        for objective, mastery in values.items():
            conn.execute(
                "INSERT OR REPLACE INTO objective_mastery (learner_id, objective, mastery, attempts, "
                "correct, high_confidence_wrong, last_practiced_at) VALUES (?, ?, ?, 3, 2, 0, ?)",
                (learner_id, objective, mastery, "2026-06-29T00:00:00+00:00"),
            )


def test_bank_seeded_with_automated_screened_items():
    status = client.get("/clinical/bank/status").json()
    assert status["counts"].get("harness_pass", 0) >= 100  # automated checks, not clinician review
    assert status["distinctRealEcgs"] >= 100
    assert status["distinctScenarioSignatures"] >= 100
    assert len(status["authoredClinicalFamilies"]) >= 8
    assert status["counts"].get("vetted", 0) == 0
    assert status["tracingSources"] == ["ptbxl"]
    assert status["tracingSourceCounts"] == {
        "ptbxl": status["counts"]["harness_pass"]
    }
    assert status["tracingLabel"] == "real de-identified ECG"
    assert status["vignetteProvenance"] == "authored simulation"
    assert status["learningEvidence"] == "formative_only"
    assert status["reviewStatus"] == "pending_named_clinician_signoff"


def test_shift_flow_serves_grades_and_reports():
    start = client.post("/clinical/shift/start", json={"lane": "clinic", "tier": "shift", "length": 2}).json()
    session_id = start["session"]["sessionId"]
    first = start["next"]
    assert first["done"] is False

    served_ids = []
    current = first
    guard = 0
    while not current["done"] and guard < 10:
        guard += 1
        item = current["item"]
        item_id = current["itemId"]
        served_ids.append(item_id)
        # Blinding: the answer key must not leak.
        assert "evidence_manifest" not in item
        assert "application_objectives" not in item
        assert "acuity_tier" not in item
        for opt in item.get("options", []):
            assert "answer_class" not in opt
        assert "stem" not in item and "options" not in item
        activated = client.post(
            f"/clinical/shift/{session_id}/phase",
            json={"itemId": item_id, "phase": "orient"},
        )
        assert activated.status_code == 200
        revealed = client.post(
            f"/clinical/shift/{session_id}/context",
            json={"itemId": item_id, "answer": {"firstLookFinding": "uncertain", "firstLookConfidence": 3}},
        ).json()
        item = revealed["item"]
        # Answer with the first available option (correctness is irrelevant here).
        option_id = item["options"][0]["id"] if item.get("options") else None
        answer = {"selectedOptionId": option_id, "confidence": 3, "answerTimeMs": 4200}
        graded = client.post(
            f"/clinical/shift/{session_id}/answer", json={"itemId": item_id, "answer": answer}
        ).json()
        assert "grade" in graded and "score" in graded["grade"]
        current = client.post(f"/clinical/shift/{session_id}/next").json()

    assert len(served_ids) == len(set(served_ids))  # no-repeat
    report = client.get(f"/clinical/shift/{session_id}/report").json()
    assert report["answered"] >= 1
    assert "calibrationLabel" in report


def test_learn_tier_is_untimed():
    start = client.post("/clinical/shift/start", json={"lane": "clinic", "tier": "learn", "length": 1}).json()
    assert start["next"]["clock"]["untimed"] is True


def test_ed_lane_rejects_outpatient_context_even_when_mislabeled_ed():
    valid = next(
        item
        for item in clinical_item_store.list_for_serving(situation="ed")
        if shift._lane_compatible(item, "ed")
    )
    mislabeled = valid.model_copy(
        update={"stem": "Stable patient attending a routine pre-operative clearance clinic visit."}
    )
    assert shift._lane_compatible(mislabeled, "ed") is False

    # Exercise the real serving boundary as well as the predicate.
    start = client.post(
        "/clinical/shift/start", json={"lane": "ed", "tier": "learn", "length": 10}
    ).json()
    session_id = start["session"]["sessionId"]
    current = start["next"]
    served: set[str] = set()
    while not current["done"]:
        item_id = current["itemId"]
        served.add(item_id)
        assert not item_id.startswith(("seed-", "fixture-", "fx-"))
        revealed = client.post(
            f"/clinical/shift/{session_id}/context",
            json={
                "itemId": item_id,
                "answer": {"firstLookFinding": "uncertain", "firstLookConfidence": 3},
            },
        ).json()
        stem = revealed["item"]["stem"].lower()
        assert not any(cue in stem for cue in shift._ED_OUTPATIENT_CONTEXT_CUES)
        options = revealed["item"].get("options") or []
        option_id = options[0].get("id") if options else None
        graded = client.post(
            f"/clinical/shift/{session_id}/answer",
            json={
                "itemId": item_id,
                "answer": {"selectedOptionId": option_id, "confidence": 3, "answerTimeMs": 1000},
            },
        )
        assert graded.status_code == 200
        current = client.post(f"/clinical/shift/{session_id}/next").json()

    assert served
    assert start["session"]["length"] == len(served)
    assert start["session"]["availableDistinctEcgs"] >= len(served)


def test_revealed_click_item_exposes_neutral_viewer_roi_not_pathology_key():
    item = next(
        item
        for item in clinical_item_store.list_for_serving(status="harness_pass")
        if item.question_type in {"click", "spoterror"} and item.roi_target is not None
    )
    payload = shift._serve_payload(
        item,
        clinical_packet,
        {
            "contextRevealed": True,
            "position": 0,
            "length": 1,
            "tier": "learn",
            "firstLook": {"firstLookFinding": "uncertain", "firstLookConfidence": 3},
        },
    )
    served = payload["item"]

    assert "roi_target" not in served
    assert served["click_roi_concept"] in {
        "p_wave", "pr_interval", "qrs_complex", "st_segment", "t_wave", "qt_segment"
    }
    assert served["click_roi_concept"] != item.roi_target.concept


def test_authored_stepwise_simulation_reveals_after_first_look_and_grades_once():
    start = client.post(
        "/clinical/shift/start",
        json={"lane": "ward", "tier": "learn", "length": 1, "focus": "av_block_third_degree"},
    ).json()
    session_id = start["session"]["sessionId"]
    first = start["next"]
    selected = clinical_item_store.get_item(first["itemId"])
    assert selected is not None
    assert "av_block_third_degree" in {
        support.objective_id for support in selected.evidence_manifest.ecg_supports
    }
    assert first["contextRevealed"] is False
    assert "stem" not in first["item"] and "steps" not in first["item"]
    assert first["item"]["learning_evidence"] == "formative_only"
    assert "real de-identified ECG" in first["item"]["content_label"]
    assert first["item"]["tracing_provenance"] == "real_deidentified_ecg"
    assert first["item"]["context_provenance"] == "authored_simulation"
    waveform = client.get(f"/cases/{selected.ecg_id}/waveform?leads=II&maxPoints=300")
    assert waveform.status_code == 200
    assert waveform.json()["caseId"] == selected.ecg_id
    assert "syntheticTeachingWaveform" not in waveform.json()

    revealed = client.post(
        f"/clinical/shift/{session_id}/context",
        json={
            "itemId": first["itemId"],
            "answer": {"firstLookFinding": "conduction_or_interval", "firstLookConfidence": 3},
        },
    ).json()
    assert revealed["contextRevealed"] is True
    assert len(revealed["item"]["steps"]) == 2
    assert all("correct" not in option for step in revealed["item"]["steps"] for option in step["options"])

    payload = {
        "itemId": first["itemId"],
        "answer": {"selectedOptionId": "chb_bedside", "stepAnswers": [0, 0], "answerTimeMs": 3400},
    }
    graded = client.post(f"/clinical/shift/{session_id}/answer", json=payload)
    assert graded.status_code == 200
    body = graded.json()
    assert body["replay"] is False
    assert body["grade"]["stepResults"] == [True, True]
    assert body["grade"]["clinicalApplicationEvidence"] == "formative_only"

    replay = client.post(
        f"/clinical/shift/{session_id}/answer",
        json={**payload, "answer": {"selectedOptionId": "chb_home", "stepAnswers": [1, 1]}},
    ).json()
    assert replay["replay"] is True
    assert replay["answerId"] == body["answerId"]
    assert replay["grade"] == body["grade"]


def test_postcommit_tutor_resolves_real_clinical_packet_and_synthetic_ids_404():
    response = client.post(
        "/tutor/message",
        json={
            "mode": "practice",
            "caseId": "8911",
            "message": "Point out the P wave on this tracing.",
            "viewerState": {"committed": True, "activity": "clinical_case_debrief"},
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["schemaError"] is None
    assert body["viewerActions"]
    assert all(action.get("lead") in {"II"} for action in body["viewerActions"] if action.get("lead"))

    unknown = client.post(
        "/tutor/message",
        json={"mode": "practice", "caseId": "seed-chb-001", "message": "Show the P wave."},
    )
    assert unknown.status_code == 404


def test_shift_prioritizes_weak_concept():
    """The mastery loop: a student weak at QTc should be served a QTc case first."""
    from app.ontology import CONCEPT_BY_ID

    learner = "t-weak-qtc"
    mastery = {c: 0.95 for c in CONCEPT_BY_ID}  # everything mastered + recent...
    mastery["qtc_prolongation"] = 0.05          # ...except QTc → it must surface
    _set_mastery(learner, mastery)
    session_id = store.create_shift_session(learner, "clinic", "shift", 3)
    nxt = shift.next_shift_item(store, clinical_item_store, clinical_packet, session_id)
    item = clinical_item_store.get_item(nxt["itemId"])
    targets = [c.objective_id for c in item.evidence_manifest.ecg_supports]
    assert "qtc_prolongation" in targets, f"expected a QTc-targeting case, got {nxt['itemId']} ({targets})"


def test_guided_handoff_focus_selects_a_compatible_first_clinical_item():
    start = client.post(
        "/clinical/shift/start",
        json={"lane": "clinic", "tier": "learn", "length": 2, "focus": "qtc_prolongation"},
    ).json()

    assert start["session"]["focusObjective"] == "qtc_prolongation"
    first = clinical_item_store.get_item(start["next"]["itemId"])
    targets = [support.objective_id for support in first.evidence_manifest.ecg_supports]
    assert "qtc_prolongation" in targets


def test_guided_handoff_subskill_selects_only_an_exact_server_graded_cell():
    application = client.post(
        "/clinical/shift/start",
        json={
            "lane": "clinic",
            "tier": "learn",
            "length": 2,
            "focus": "qtc_prolongation",
            "subskill": "apply_in_context",
        },
    ).json()
    application_item = clinical_item_store.get_item(application["next"]["itemId"])
    assert application["session"]["focusSubskill"] == "apply_in_context"
    assert "qtc_prolongation" in application_item.application_objectives
    assert application_item.question_type == "mcq"

    localization = client.post(
        "/clinical/shift/start",
        json={
            "lane": "clinic",
            "tier": "learn",
            "length": 2,
            "focus": "qtc_prolongation",
            "subskill": "localize",
        },
    ).json()
    localization_item = clinical_item_store.get_item(localization["next"]["itemId"])
    assert localization_item.question_type == "click"
    assert localization_item.roi_target.concept == "qtc_prolongation"

    unsupported = client.post(
        "/clinical/shift/start",
        json={
            "lane": "clinic",
            "tier": "learn",
            "length": 2,
            "focus": "qtc_prolongation",
            "subskill": "recognize",
        },
    ).json()
    assert unsupported["next"]["item"] is None
    assert "qtc prolongation x recognize" in unsupported["next"]["reason"]
    assert "No substitute case" in unsupported["next"]["reason"]


def test_guided_handoff_with_no_compatible_item_fails_closed():
    start = client.post(
        "/clinical/shift/start",
        json={"lane": "ward", "tier": "learn", "length": 2, "focus": "premature_ventricular_complex"},
    ).json()

    assert start["next"]["item"] is None
    assert start["next"]["done"] is True
    assert "No substitute case" in start["next"]["reason"]


def test_bank_coverage_reports_per_concept_depth():
    response = client.get("/clinical/bank/coverage").json()
    assert response["tracingSources"] == ["ptbxl"]
    assert response["tracingSourceCounts"]["ptbxl"] >= 100
    cov = response["coverage"]
    assert cov  # non-empty
    qtc = cov.get("qtc_prolongation")
    assert qtc and qtc["items"] >= 1 and qtc["distinctEcgs"] >= 1


def test_calibration_label_thresholds():
    # round-3: small samples show counts, not a label (a 5-case label flips on one item).
    assert calibration_label([{"overTriage": True, "correct": False}] * 4).startswith("early signal")
    # With enough cases (>=8), the labels apply.
    over = [{"overTriage": True, "correct": False}] * 8
    assert calibration_label(over) == "cautious over-caller"
    under = [{"underTriage": True, "correct": False}] * 8
    assert calibration_label(under) == "risky under-caller"
    brittle = [{"highConfidenceWrong": True, "correct": False}] * 8
    assert calibration_label(brittle) == "confident-but-brittle"
    assert calibration_label([{"correct": True}] * 8) == "well-calibrated"


def test_pending_item_is_stable_across_refresh_and_resume():
    start = client.post(
        "/clinical/shift/start", json={"lane": "clinic", "tier": "learn", "length": 2}
    ).json()
    session_id = start["session"]["sessionId"]
    first_id = start["next"]["itemId"]

    again = client.post(f"/clinical/shift/{session_id}/next").json()
    assert again["itemId"] == first_id
    assert again["index"] == 0
    fetched = client.get(f"/clinical/shift/{session_id}").json()
    assert fetched["pendingItemId"] == first_id
    assert fetched["position"] == 0


def test_duplicate_answer_is_exactly_once_and_replays_stored_grade():
    start = client.post(
        "/clinical/shift/start", json={"lane": "clinic", "tier": "shift", "length": 2}
    ).json()
    session_id = start["session"]["sessionId"]
    item_id = start["next"]["itemId"]
    ecg_id = clinical_item_store.get_item(item_id).ecg_id

    first = _answer(session_id, item_id, answer_time_ms=3210)
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["replay"] is False
    after_first = store.get_shift_session(session_id)
    with store.connect() as conn:
        # answerId and attemptId are separate sequences; use the ledger's explicit link.
        ledger = conn.execute(
            "SELECT attempt_id FROM clinical_shift_answers WHERE session_id = ? AND item_id = ?",
            (session_id, item_id),
        ).fetchone()
        attempt = conn.execute(
            "SELECT case_id FROM attempts WHERE id = ?", (ledger["attempt_id"],)
        ).fetchone()
        attempt_count = conn.execute(
            "SELECT COUNT(*) n FROM attempts WHERE learner_id = 'demo' AND mode = 'clinical_decision'"
        ).fetchone()["n"]
        mastery_attempts = conn.execute(
            "SELECT COALESCE(SUM(attempts), 0) n FROM objective_mastery WHERE learner_id = 'demo'"
        ).fetchone()["n"]
    assert attempt["case_id"] == ecg_id  # actual tracing id, never the authored item id

    replay = _answer(session_id, item_id, answer_time_ms=99999)
    assert replay.status_code == 200
    replay_body = replay.json()
    assert replay_body["replay"] is True
    assert replay_body["answerId"] == first_body["answerId"]
    assert replay_body["grade"] == first_body["grade"]

    after_replay = store.get_shift_session(session_id)
    with store.connect() as conn:
        assert conn.execute(
            "SELECT COUNT(*) n FROM attempts WHERE learner_id = 'demo' AND mode = 'clinical_decision'"
        ).fetchone()["n"] == attempt_count
        assert conn.execute(
            "SELECT COALESCE(SUM(attempts), 0) n FROM objective_mastery WHERE learner_id = 'demo'"
        ).fetchone()["n"] == mastery_attempts
        assert conn.execute(
            "SELECT COUNT(*) n FROM clinical_shift_answers WHERE session_id = ?", (session_id,)
        ).fetchone()["n"] == 1
    assert after_replay["position"] == after_first["position"] == 1
    assert after_replay["calibration"] == after_first["calibration"]


def test_clinical_application_receipt_is_exact_formative_and_exactly_once():
    suffix = uuid.uuid4().hex[:10]
    with TestClient(app) as student:
        registered = student.post(
            "/auth/register",
            json={"username": f"clinical_apply_{suffix}", "password": "test-password"},
        ).json()
        learner_id = registered["user"]["userId"]
        started = student.post(
            "/clinical/shift/start",
            json={"lane": "clinic", "tier": "learn", "length": 1, "focus": "normal_ecg"},
        ).json()
        session_id = started["session"]["sessionId"]
        item_id = started["next"]["itemId"]
        item = clinical_item_store.get_item(item_id)
        assert item is not None and item.application_objectives == ["normal_ecg"]
        ideal = next(option for option in item.options if option.answer_class == "ideal")

        assert student.post(
            f"/clinical/shift/{session_id}/phase",
            json={"itemId": item_id, "phase": "orient"},
        ).status_code == 200
        assert student.post(
            f"/clinical/shift/{session_id}/context",
            json={
                "itemId": item_id,
                "answer": {
                    "firstLookFinding": "normal_or_no_dominant_abnormality",
                    "firstLookConfidence": 5,
                },
            },
        ).status_code == 200
        payload = {
            "itemId": item_id,
            "answer": {"selectedOptionId": ideal.id, "confidence": 5},
        }
        first = student.post(f"/clinical/shift/{session_id}/answer", json=payload).json()
        receipts = first["grade"]["competencyReceipts"]
        assert first["replay"] is False
        assert len(receipts) == 1
        receipt = receipts[0]
        assert (receipt["concept"], receipt["subskill"]) == ("normal_ecg", "apply_in_context")
        assert receipt["correct"] is True
        assert receipt["formativeOnly"] is True
        assert receipt["evidenceLevel"] == "guided"
        assert receipt["independentMastery"] == 0.15
        assert receipt["retentionEligible"] is False
        assert receipt["nextDueAt"] is None
        assert receipt["evidenceSource"] == "clinical_action_server_grade"

        replay = student.post(
            f"/clinical/shift/{session_id}/answer",
            json={
                "itemId": item_id,
                "answer": {"selectedOptionId": "normal_emergency", "confidence": 5},
            },
        ).json()
        assert replay["replay"] is True
        assert replay["answerId"] == first["answerId"]
        assert replay["grade"] == first["grade"]
        with store.connect() as conn:
            row = conn.execute(
                "SELECT attempts, independent_attempts, next_due_at FROM subskill_mastery "
                "WHERE learner_id = ? AND concept = 'normal_ecg' AND subskill = 'apply_in_context'",
                (learner_id,),
            ).fetchone()
            answer_row = conn.execute(
                "SELECT receipts_json FROM clinical_shift_answers "
                "WHERE session_id = ? AND item_id = ?",
                (session_id, item_id),
            ).fetchone()
        assert row is not None
        assert row["attempts"] == 1
        assert row["independent_attempts"] == 0
        assert row["next_due_at"] is None
        assert len(json.loads(answer_row["receipts_json"])) == 1


def test_server_matched_clinical_click_records_localize_but_not_application():
    suffix = uuid.uuid4().hex[:10]
    with TestClient(app) as student:
        registered = student.post(
            "/auth/register",
            json={"username": f"clinical_click_{suffix}", "password": "test-password"},
        ).json()
        learner_id = registered["user"]["userId"]
        started = student.post(
            "/clinical/shift/start",
            json={
                "lane": "clinic",
                "tier": "learn",
                "length": 1,
                "focus": "av_block_first_degree",
            },
        ).json()
        session_id = started["session"]["sessionId"]
        item_id = started["next"]["itemId"]
        item = clinical_item_store.get_item(item_id)
        assert item is not None and item.question_type == "click"
        assert item.application_objectives == []
        packet = clinical_packet(item.ecg_id)
        acceptable = grounding.acceptable_roi_concepts(item.roi_target.concept)
        roi = next(
            region
            for region in grounding.rois(packet)
            if region.get("concept") in acceptable
            and region.get("lead") in set(item.roi_target.leads)
        )
        click = {
            "lead": roi["lead"],
            "timeSec": (float(roi["timeStartSec"]) + float(roi["timeEndSec"])) / 2,
            "amplitudeMv": 0.0,
        }

        student.post(
            f"/clinical/shift/{session_id}/phase",
            json={"itemId": item_id, "phase": "orient"},
        )
        student.post(
            f"/clinical/shift/{session_id}/context",
            json={
                "itemId": item_id,
                "answer": {
                    "firstLookFinding": "conduction_or_interval",
                    "firstLookConfidence": 5,
                },
            },
        )
        graded = student.post(
            f"/clinical/shift/{session_id}/answer",
            json={"itemId": item_id, "answer": {"click": click, "confidence": 5}},
        ).json()
        receipts = graded["grade"]["competencyReceipts"]
        assert len(receipts) == 1
        assert (receipts[0]["concept"], receipts[0]["subskill"]) == (
            "av_block_first_degree",
            "localize",
        )
        assert receipts[0]["correct"] is True
        assert receipts[0]["formativeOnly"] is True
        assert receipts[0]["retentionEligible"] is False
        with store.connect() as conn:
            rows = conn.execute(
                "SELECT concept, subskill, attempts, independent_attempts FROM subskill_mastery "
                "WHERE learner_id = ?",
                (learner_id,),
            ).fetchall()
        assert [(row["concept"], row["subskill"]) for row in rows] == [
            ("av_block_first_degree", "localize")
        ]
        assert rows[0]["attempts"] == 1
        assert rows[0]["independent_attempts"] == 0


def test_stepwise_application_success_requires_the_ecg_sequence_and_action():
    item = next(
        candidate
        for candidate in clinical_item_store.list_for_serving(status="harness_pass")
        if candidate.question_type == "stepwise" and candidate.application_objectives
    )
    packet = clinical_packet(item.ecg_id)
    ideal = next(option for option in item.options if option.answer_class == "ideal")
    wrong_steps = [
        next(index for index, option in enumerate(step.options) if not option.correct)
        for step in item.steps
    ]
    answer = ClinicalAnswer(
        selected_option_id=ideal.id,
        step_answers=wrong_steps,
        confidence=5,
    )
    grade = grade_clinical_answer(item, packet, answer)
    events = shift._clinical_competency_events(item, packet, grade, answer)
    application = next(event for event in events if event["subskill"] == "apply_in_context")

    assert grade["answerClass"] == "ideal"
    assert not all(grade["stepResults"])
    assert application["correct"] is False
    assert application["score"] == 0.0


def test_first_look_category_is_formative_persisted_and_replay_stable():
    start = client.post(
        "/clinical/shift/start", json={"lane": "clinic", "tier": "learn", "length": 1}
    ).json()
    session_id = start["session"]["sessionId"]
    item_id = start["next"]["itemId"]
    payload = {
        "itemId": item_id,
        "answer": {
            "firstLookFinding": "uncertain",
            "firstLookConfidence": 3,
            "confidence": 3,
            "answerTimeMs": 2100,
        },
    }
    reveal = client.post(
        f"/clinical/shift/{session_id}/context",
        json={
            "itemId": item_id,
            "answer": {"firstLookFinding": "uncertain", "firstLookConfidence": 3},
        },
    )
    assert reveal.status_code == 200
    first = client.post(f"/clinical/shift/{session_id}/answer", json=payload)
    assert first.status_code == 200, first.text
    assessment = first.json()["grade"]["firstLookAssessment"]
    assert assessment["submittedCategory"] == "uncertain"
    assert assessment["confidence"] == 3
    assert assessment["formativeOnly"] is True
    assert assessment["exactPathologyMasterySuppressed"] is True

    stored = store.get_shift_answer(session_id, item_id)
    assert stored["response"]["first_look_finding"] == "uncertain"
    assert stored["response"]["first_look_confidence"] == 3

    replay_payload = {
        **payload,
        "answer": {
            **payload["answer"],
            "firstLookFinding": "normal_or_no_dominant_abnormality",
            "firstLookConfidence": 5,
        },
    }
    replay = client.post(f"/clinical/shift/{session_id}/answer", json=replay_payload)
    assert replay.status_code == 200
    assert replay.json()["replay"] is True
    assert replay.json()["grade"] == first.json()["grade"]
    assert store.get_shift_answer(session_id, item_id)["response"] == stored["response"]


def test_only_the_current_pending_item_can_be_answered():
    start = client.post(
        "/clinical/shift/start", json={"lane": "clinic", "tier": "learn", "length": 2}
    ).json()
    session_id = start["session"]["sessionId"]
    pending_id = start["next"]["itemId"]
    other = next(
        item for item in clinical_item_store.list_for_serving(situation="clinic", status="harness_pass")
        if item.item_id != pending_id
    )
    response = _answer(session_id, other.item_id)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "clinical_item_not_pending"
    assert store.get_shift_session(session_id)["position"] == 0
    assert store.get_shift_answers(session_id) == []


def test_learn_report_counts_answers_without_calibration_events():
    start = client.post(
        "/clinical/shift/start", json={"lane": "clinic", "tier": "learn", "length": 3}
    ).json()
    session_id = start["session"]["sessionId"]
    current = start["next"]
    times = [1000, 2000, 6000]
    for answer_time in times:
        assert current["done"] is False
        response = _answer(session_id, current["itemId"], answer_time_ms=answer_time)
        assert response.status_code == 200, response.text
        current = client.post(f"/clinical/shift/{session_id}/next").json()

    report = client.get(f"/clinical/shift/{session_id}/report").json()
    assert report["answered"] == 3
    # Request timing is untrusted; the report is derived from durable server clocks.
    assert report["avgDecideMs"] is not None
    assert report["avgDecideMs"] >= 0
    assert report["avgDecideMs"] != 3000
    assert 0.0 <= report["accuracy"] <= 1.0
    assert 0 <= report["bestStreak"] <= 3
    assert report["calibrationLabel"] == "calibration off (Learn)"
    assert store.get_shift_session(session_id)["calibration"] == []


def test_requested_length_is_capped_to_distinct_lane_ecgs_and_never_repeats_ecg():
    available = len({
        item.ecg_id
        for item in clinical_item_store.list_for_serving(situation="clinic", status="harness_pass")
        if clinical_packet(item.ecg_id) is not None
    })
    start = client.post(
        "/clinical/shift/start", json={"lane": "clinic", "tier": "learn", "length": 50}
    ).json()
    session = start["session"]
    assert session["requestedLength"] == 50
    assert session["availableDistinctEcgs"] == available
    assert session["length"] == available
    assert "Requested 50" in session["lengthReason"]
    assert f"{available} distinct" in session["lengthReason"]

    ecgs = []
    current = start["next"]
    while not current["done"]:
        item = clinical_item_store.get_item(current["itemId"])
        ecgs.append(item.ecg_id)
        response = _answer(session["sessionId"], item.item_id)
        assert response.status_code == 200, response.text
        current = client.post(f"/clinical/shift/{session['sessionId']}/next").json()
    assert len(ecgs) == available
    assert len(ecgs) == len(set(ecgs))
    assert current["requested"] == 50
    assert current["available"] == available


def test_shift_routes_always_enforce_effective_learner_ownership():
    suffix = uuid.uuid4().hex[:10]
    with TestClient(app) as owner_client, TestClient(app) as other_client, TestClient(app) as guest_client:
        a = owner_client.post(
            "/auth/register",
            json={"username": f"owner_{suffix}", "password": "test-password"},
        ).json()
        b = other_client.post(
            "/auth/register",
            json={"username": f"other_{suffix}", "password": "test-password"},
        ).json()
        started = owner_client.post(
            "/clinical/shift/start",
            json={"learnerId": "demo", "lane": "clinic", "tier": "learn", "length": 1},
        ).json()
        session_id = started["session"]["sessionId"]
        item_id = started["next"]["itemId"]
        assert started["session"]["learnerId"] == a["user"]["userId"]
        assert a["user"]["userId"] != b["user"]["userId"]

        for caller in (guest_client, other_client):
            assert caller.get(f"/clinical/shift/{session_id}").status_code == 404
            assert caller.post(f"/clinical/shift/{session_id}/next").status_code == 404
            assert caller.get(f"/clinical/shift/{session_id}/report").status_code == 404
            assert _answer(session_id, item_id, test_client=caller).status_code == 404

        # Sending a `u_…` learner id without authentication never creates an owned session.
        guest = guest_client.post(
            "/clinical/shift/start",
            json={
                "learnerId": a["user"]["userId"],
                "lane": "clinic",
                "tier": "learn",
                "length": 1,
            },
        ).json()
        assert guest["session"]["learnerId"] == "demo"
