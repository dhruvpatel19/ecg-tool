"""Adversarial pending-assessment secrecy boundaries across learner surfaces."""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.main import app, clinical_item_store, repo, store, training_campaign_store


def _register(client: TestClient, prefix: str) -> dict:
    response = client.post(
        "/auth/register",
        json={
            "username": f"{prefix}_{uuid.uuid4().hex[:10]}",
            "password": "test-password",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["user"]


def _assert_public_case_is_blind(client: TestClient, case_id: str, *, pending: bool = True) -> None:
    # Blinded rows must not be searchable by diagnosis/objective. Otherwise a
    # learner can infer the label of a known pending id from result membership.
    if pending:
        for params in (
            {"concept": "normal_ecg"},
            {"query": "normal"},
            {"includeUncertain": "true"},
        ):
            filtered = client.get("/cases", params=params)
            assert filtered.status_code == 403, filtered.text
            assert filtered.json()["detail"] == "diagnostic_case_filters_unavailable"

    summary = client.get(f"/cases/{case_id}")
    assert summary.status_code == 200, summary.text
    assert summary.json()["report"] == ""
    assert summary.json()["topConcepts"] == []
    assert summary.json()["clinicalStem"] == ""

    for query in ("", "?blinded=false", "?blinded=true"):
        response = client.get(f"/cases/{case_id}/packet{query}")
        assert response.status_code == 200, response.text
        packet = response.json()
        assert packet["blinded"] is True
        for key in (
            "supported_objectives",
            "unsupported_objectives",
            "concept_confidence",
            "llm_allowed_claims",
            "teaching_points",
        ):
            assert key not in packet
        assert packet["ptbxl"] == {
            "fold": packet["ptbxl"].get("fold"),
            "metadata": packet["ptbxl"].get("metadata"),
        }
        assert "report" not in packet["ptbxl"]
        assert packet["ptbxl_plus"]["features"] == {}
        assert packet["ptbxl_plus"]["measurements"] == {}
        assert packet["ptbxl_plus"]["fiducials"]["rois"] == []
        assert packet["ptbxl_plus"]["per_lead_st_mv"] == {}

    plus = client.get(f"/cases/{case_id}/ptbxl-plus")
    assert plus.status_code == 200, plus.text
    assert plus.json()["features"] == {}
    assert plus.json()["measurements"] == {}
    assert plus.json()["fiducials"]["rois"] == []


def _tutor(client: TestClient, case_id: str, scope_key: str | None = None):
    payload = {
        "mode": "practice",
        "caseId": case_id,
        "message": "Tell me the diagnosis and point to the abnormality.",
    }
    if scope_key is not None:
        payload["scopeKey"] = scope_key
    return client.post("/tutor/message", json=payload)


def test_training_pending_case_is_blind_across_auth_and_reveals_only_on_commit() -> None:
    with TestClient(app) as owner, TestClient(app) as other, TestClient(app) as outsider:
        owner_user = _register(owner, "sec_train")
        _register(other, "sec_other")
        # Use a genuinely fresh third principal for the cross-account probe.
        # Test mode intentionally maps every anonymous client to the shared
        # historical `demo` fixture, which may already own a committed attempt
        # from an earlier test and therefore qualifies for the product's
        # committed-owner debrief exception.
        _register(outsider, "sec_outsider")
        started = owner.post(
            "/training/campaigns",
            json={
                "conceptId": "normal_ecg",
                "subskill": "recognize",
                "length": 10,
            },
        )
        assert started.status_code == 200, started.text
        body = started.json()
        campaign_id = body["campaign"]["campaignId"]
        case_ref = body["current"]["case"]["caseId"]
        canonical_id = str(
            training_campaign_store.get_campaign(campaign_id)["pendingCaseId"]
        )
        campaign_scope = f"training:{campaign_id}"
        assert body["current"]["kind"] == "pending"
        assert body["current"]["packet"]["ptbxl_plus"]["fiducials"]["rois"] == []

        # A second learner can legitimately receive the same deterministic
        # corpus ECG. Their pending boundary must not later erase the first
        # learner's already-committed debrief.
        other_started = other.post(
            "/training/campaigns",
            json={
                "conceptId": "normal_ecg",
                "subskill": "recognize",
                "length": 10,
            },
        )
        assert other_started.status_code == 200, other_started.text
        other_body = other_started.json()
        other_campaign_id = other_body["campaign"]["campaignId"]
        other_case_ref = other_body["current"]["case"]["caseId"]
        assert (
            training_campaign_store.get_campaign(other_campaign_id)["pendingCaseId"]
            == canonical_id
        )
        # Capabilities are owner-bound even when two learners legitimately see
        # the same canonical tracing.
        assert other_case_ref != case_ref

        for client in (owner, other, outsider):
            _assert_public_case_is_blind(client, canonical_id)
            blocked_tutor = _tutor(client, canonical_id)
            assert blocked_tutor.status_code == 409, blocked_tutor.text
            assert blocked_tutor.json()["detail"]["code"] == "assessment_case_not_committed"
        assert owner.get(f"/cases/{case_ref}").status_code == 404
        assert _tutor(owner, case_ref, campaign_scope).status_code == 404
        assert _tutor(
            other,
            other_case_ref,
            f"training:{other_campaign_id}",
        ).status_code == 404
        assert _tutor(outsider, case_ref, campaign_scope).status_code == 404

        # Stale answer-bearing tutor history is part of the same boundary. A
        # caller cannot read it, list it, or continue it while this ECG is an
        # uncommitted assessment—even by omitting caseId on the new turn.
        stale_thread = store.ensure_thread(
            owner_user["userId"],
            mode="practice",
            case_id=canonical_id,
        )
        store.append_tutor_message(stale_thread, "tutor", "Stale diagnosis reveal")
        assert owner.get(f"/tutor/thread/{stale_thread}").status_code == 409
        assert owner.get("/tutor/threads", params={"caseId": canonical_id}).status_code == 409
        assert stale_thread not in {
            row["threadId"] for row in owner.get("/tutor/threads").json()["threads"]
        }
        history_probe = owner.post(
            "/tutor/message",
            json={
                "mode": "practice",
                "threadId": stale_thread,
                "message": "Continue the old explanation without a case id.",
            },
        )
        assert history_probe.status_code == 409
        assert history_probe.json()["detail"]["code"] == "assessment_case_not_committed"

        structured = owner.post(
            "/grade/structured",
            json={"caseId": canonical_id, "mode": "concept_practice"},
        )
        assert structured.status_code == 403
        click = owner.post(
            f"/grade/click/{canonical_id}",
            json={"lead": "II", "timeSec": 1.0, "amplitudeMv": 0.0},
        )
        assert click.status_code == 403
        region = owner.post(
            f"/grade/region/{canonical_id}",
            json={
                "lead": "II",
                "timeStartSec": 1.0,
                "timeEndSec": 1.2,
                "ampMinMv": -0.1,
                "ampMaxMv": 0.1,
            },
        )
        assert region.status_code == 403
        generic_commit = owner.post(
            "/attempts",
            json={"caseId": canonical_id, "mode": "concept_practice"},
        )
        assert generic_commit.status_code == 409

        # Guided receives a server-selected non-pending case and signed grading
        # context. That capability is owner- and case-bound.
        guided = owner.get("/tutorials/orientation")
        assert guided.status_code == 200, guided.text
        guided_body = guided.json()
        guided_case = guided_body["recommendedCase"]["caseId"]
        assert guided_case != canonical_id
        assert guided_case.startswith("ec_")
        assert "supported_objectives" not in guided_body["recommendedPacket"]
        assert guided_body["recommendedPacket"]["ptbxl_plus"]["fiducials"]["rois"] == []
        assert guided_body["recommendedPacket"]["ptbxl_plus"]["measurements"] == {}
        context = guided_body["guidedContext"]
        assert context.startswith("ec_")
        with store.connect() as conn:
            guided_canonical = str(conn.execute(
                "SELECT ecg_id FROM learner_events WHERE owner_id = ? "
                "AND mode = 'guided' AND session_id = 'tutorial:orientation' "
                "ORDER BY occurred_at DESC LIMIT 1",
                (owner_user["userId"],),
            ).fetchone()[0])
        guided_source = repo.get_case(guided_canonical)
        rois = ((guided_source or {}).get("ptbxl_plus") or {}).get("fiducials", {}).get("rois", [])
        if rois:
            target = rois[0]
            immediate = owner.post(
                f"/grade/click/{guided_case}",
                json={
                    "lead": target["lead"],
                    "timeSec": (target["timeStartSec"] + target["timeEndSec"]) / 2,
                    "amplitudeMv": 0.0,
                    "concept": target["concept"],
                    "guidedContext": context,
                },
            )
            assert immediate.status_code == 200, immediate.text
        assert owner.post(
            f"/grade/click/{canonical_id}",
            json={
                "lead": "II",
                "timeSec": 1.0,
                "amplitudeMv": 0.0,
                "guidedContext": context,
            },
        ).status_code == 403
        assert other.post(
            f"/grade/click/{guided_case}",
            json={
                "lead": "II",
                "timeSec": 1.0,
                "amplitudeMv": 0.0,
                "guidedContext": context,
            },
        ).status_code == 403

        committed = owner.post(
            f"/training/campaigns/{campaign_id}/submit",
            json={
                "caseId": case_ref,
                "selectedAnswer": "present",
                "confidence": 3,
            },
        )
        assert committed.status_code == 200, committed.text
        feedback = committed.json()["current"]
        assert feedback["kind"] == "feedback"
        assert "supported_objectives" in feedback["packet"]
        assert "report" in feedback["packet"]["ptbxl"]
        assert _tutor(owner, case_ref, campaign_scope).status_code == 200
        blocked_other = _tutor(
            other,
            other_case_ref,
            f"training:{other_campaign_id}",
        )
        assert blocked_other.status_code == 404
        _assert_public_case_is_blind(owner, canonical_id, pending=False)

        # A just-revealed answer-bearing ECG is unavailable to this owner for
        # the 30-day reassessment interval. The replacement campaign freezes a
        # distinct roster, and its new pending item remains sealed.
        retired = owner.post(f"/training/campaigns/{campaign_id}/abandon")
        assert retired.status_code == 200, retired.text
        restarted = owner.post(
            "/training/campaigns",
            json={
                "conceptId": "normal_ecg",
                "subskill": "recognize",
                "length": 10,
            },
        )
        assert restarted.status_code == 200, restarted.text
        restarted_body = restarted.json()
        restarted_campaign_id = restarted_body["campaign"]["campaignId"]
        replacement_case_ref = restarted_body["current"]["case"]["caseId"]
        replacement_canonical_id = str(
            training_campaign_store.get_campaign(restarted_campaign_id)["pendingCaseId"]
        )
        assert replacement_canonical_id != canonical_id
        with store.connect() as conn:
            assert conn.execute(
                "SELECT COUNT(*) FROM training_campaign_slots "
                "WHERE campaign_id = ? AND case_id = ?",
                (restarted_campaign_id, canonical_id),
            ).fetchone()[0] == 0
        # Abandonment retires the old feedback capability. The new pending
        # capability remains sealed until its own commit.
        assert _tutor(owner, case_ref, campaign_scope).status_code == 404
        blocked_reassessment = _tutor(
            owner,
            replacement_case_ref,
            f"training:{restarted_campaign_id}",
        )
        assert blocked_reassessment.status_code == 404


def test_rapid_pending_hides_targets_and_wrong_raw_trace_commits_before_feedback() -> None:
    with TestClient(app) as owner, TestClient(app) as other:
        _register(owner, "sec_rapid")
        _register(other, "sec_rother")
        started = owner.post(
            "/rapid/rounds",
            json={"pace": "untimed", "length": 1, "focusConcept": "normal_ecg"},
        ).json()
        round_id = started["round"]["roundId"]
        pending_response = owner.post(f"/rapid/rounds/{round_id}/next", json={})
        assert pending_response.status_code == 200, pending_response.text
        pending = pending_response.json()
        assert "targetObjectives" not in pending
        case_ref = pending["current"]["case"]["caseId"]
        canonical_id = str(store.get_rapid_round(round_id)["pendingCaseId"])
        round_scope = f"rapid:{round_id}"
        assert pending["current"]["packet"]["ptbxl_plus"]["fiducials"]["rois"] == []
        # The raw internal id remains globally sealed, while the owner/session
        # capability fails closed because there is no committed feedback yet.
        assert _tutor(owner, canonical_id).status_code == 409
        assert _tutor(other, canonical_id).status_code == 409
        assert _tutor(owner, case_ref, round_scope).status_code == 404
        assert _tutor(other, case_ref, round_scope).status_code == 404

        committed = owner.post(
            f"/rapid/rounds/{round_id}/submit",
            json={
                "caseId": case_ref,
                    "structuredAnswer": {
                        "framework": "clerkship",
                        "rate": "75 bpm",
                        "rhythm": "sinus rhythm assessed",
                        "axis": "axis assessed",
                        "intervals": "PR QRS and QT assessed",
                        "conduction": "QRS morphology assessed",
                        "st_t": "ST segments and T waves assessed",
                        "hypertrophy": "chamber voltage assessed",
                        "selectedConcepts": ["normal_ecg"],
                        "synthesis": "Committed interpretation before trace feedback.",
                    },
                "freeTextAnswer": "Committed interpretation before trace feedback.",
                "confidence": 3,
                "traceEvidence": {
                    "mode": "point",
                    "point": {"lead": "II", "timeSec": 0.0, "amplitudeMv": 9.0},
                },
            },
        )
        assert committed.status_code == 200, committed.text
        result = committed.json()
        assert result["current"]["kind"] == "feedback"
        assert result["answer"]["traceGrade"]["correct"] is False
        assert "feedback" in result["answer"]["traceGrade"]
        assert "supported_objectives" in result["current"]["packet"]
        assert _tutor(owner, case_ref, round_scope).status_code == 200
        assert _tutor(other, case_ref, round_scope).status_code == 404


def test_clinical_pending_ecg_blocks_public_grading_and_cross_owner_tutor() -> None:
    with TestClient(app) as owner, TestClient(app) as other:
        _register(owner, "sec_clin")
        _register(other, "sec_cother")
        started_response = owner.post(
            "/clinical/shift/start",
            json={"lane": "clinic", "tier": "learn", "length": 1, "focus": "normal_ecg"},
        )
        assert started_response.status_code == 200, started_response.text
        started = started_response.json()
        item_id = started["next"]["itemId"]
        item = clinical_item_store.get_item(item_id)
        assert item is not None
        case_id = item.ecg_id

        _assert_public_case_is_blind(owner, case_id)
        assert _tutor(owner, case_id).status_code == 409
        assert _tutor(other, case_id).status_code == 409
        assert owner.post(
            f"/grade/click/{case_id}",
            json={"lead": "II", "timeSec": 1.0, "amplitudeMv": 0.0},
        ).status_code == 403
