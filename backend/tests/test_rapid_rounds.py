from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import json
from threading import Barrier
import uuid

from fastapi.testclient import TestClient
import pytest

from app import rapid_routes
from app.assessment_ledger import create_lease, record_guided_packet_exposure
from app.main import app, repo, store
from app.rapid_assessment import RapidAssessmentStore
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


def _canonical_pending(round_id: str) -> str:
    session = store.get_rapid_round(round_id)
    assert session and session["pendingCaseId"]
    return str(session["pendingCaseId"])


def _point_from_packet(packet: dict, canonical_id: str | None = None) -> dict:
    # Pending learner packets intentionally contain no reviewed ROI geometry.
    # Backend contract tests may resolve the server-owned source packet directly.
    packet = repo.get_case(
        canonical_id or str(packet.get("case_id") or packet.get("caseId"))
    ) or packet
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


def _rapid_atomic_snapshot(round_id: str, learner_id: str, case_id: str) -> dict:
    """Read every ledger mutated by one Rapid finalization."""

    with store.connect() as conn:
        round_row = conn.execute(
            "SELECT pending_case_id, feedback_case_id, served_json, position, status, updated_at "
            "FROM rapid_rounds WHERE round_id = ?",
            (round_id,),
        ).fetchone()
        return {
            "round": tuple(round_row) if round_row else None,
            "answers": int(conn.execute(
                "SELECT COUNT(*) FROM rapid_round_answers WHERE round_id = ?",
                (round_id,),
            ).fetchone()[0]),
            "attempts": int(conn.execute(
                "SELECT COUNT(*) FROM attempts WHERE learner_id = ? AND case_id = ? "
                "AND mode = 'rapid_practice'",
                (learner_id, case_id),
            ).fetchone()[0]),
            "events": int(conn.execute(
                "SELECT COUNT(*) FROM guided_learning_events WHERE learner_id = ? "
                "AND event_key LIKE ?",
                (learner_id, f"rapid:{round_id}:{case_id}:%"),
            ).fetchone()[0]),
            "retention": int(conn.execute(
                "SELECT COUNT(*) FROM subskill_retention_events WHERE learner_id = ? "
                "AND case_id = ? AND mode = 'rapid'",
                (learner_id, case_id),
            ).fetchone()[0]),
            "subskills": int(conn.execute(
                "SELECT COUNT(*) FROM subskill_mastery WHERE learner_id = ?",
                (learner_id,),
            ).fetchone()[0]),
            "assessmentLeases": [tuple(row) for row in conn.execute(
                "SELECT state, integrity_status, submission_key_hash, claimed_at, terminal_at "
                "FROM assessment_leases WHERE owner_id = ? AND mode = 'rapid' "
                "AND session_id = ? ORDER BY lease_id",
                (learner_id, round_id),
            ).fetchall()],
            "learnerEvents": [tuple(row) for row in conn.execute(
                "SELECT event_type, score, integrity_status FROM learner_events "
                "WHERE owner_id = ? AND mode = 'rapid' AND session_id = ? "
                "ORDER BY event_type, event_id",
                (learner_id, round_id),
            ).fetchall()],
            "competencyEvidence": [tuple(row) for row in conn.execute(
                "SELECT c.competency_id, c.competency_score "
                "FROM learner_event_competencies AS c "
                "JOIN learner_events AS e ON e.event_id = c.event_id "
                "WHERE e.owner_id = ? AND e.mode = 'rapid' AND e.session_id = ? "
                "ORDER BY c.competency_id",
                (learner_id, round_id),
            ).fetchall()],
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


def test_ward_read_uses_the_two_minute_server_owned_deadline() -> None:
    with TestClient(app) as client:
        _register(client, "rapid_ward_clock")
        started = _start(client, pace="ward", length=5)
        assert started["round"]["pace"] == "ward"
        assert started["round"]["deadlineSeconds"] == 120


def test_integration_launch_contract_rejects_unsafe_or_unfreezable_requests() -> None:
    with TestClient(app) as client:
        _register(client, "rapid_int_bad")
        base = {
            "learnerId": "demo",
            "pace": "untimed",
            "length": 10,
            "focusConcept": "normal_ecg",
            "secondaryConcept": "atrial_fibrillation",
            "focusSubskill": "synthesize",
            "contextKey": (
                "?focus=normal_ecg&secondaryConcept=atrial_fibrillation"
                "&receiptConcept=normal_ecg&subskill=synthesize"
            ),
            "exclusions": [],
        }

        mismatch = client.post(
            "/rapid/rounds",
            json={**base, "secondaryConcept": "rate"},
        )
        assert mismatch.status_code == 422
        assert mismatch.json()["detail"]["code"] == "rapid_secondary_concept_mismatch"

        duplicate = client.post(
            "/rapid/rounds",
            json={
                **base,
                "contextKey": (
                    base["contextKey"]
                    + "&secondaryConcept=rate"
                ),
            },
        )
        assert duplicate.status_code == 422
        assert duplicate.json()["detail"]["code"] == "rapid_secondary_concept_invalid"

        injected = client.post(
            "/rapid/rounds",
            json={**base, "contextKey": base["contextKey"] + "&__integrationRoster=learner-owned"},
        )
        assert injected.status_code == 422
        assert injected.json()["detail"]["code"] == "rapid_integration_roster_client_owned"

        too_short = client.post(
            "/rapid/rounds",
            json={**base, "length": 1},
        )
        assert too_short.status_code == 422
        assert too_short.json()["detail"]["code"] == "rapid_integration_length_too_short"


def test_integration_round_freezes_two_concepts_but_keeps_synthesis_formative() -> None:
    with TestClient(app) as client:
        user = _register(client, "rapid_integration")
        response = client.post(
            "/rapid/rounds",
            json={
                "learnerId": "demo",
                "pace": "untimed",
                "length": 2,
                "focusConcept": "normal_ecg",
                "secondaryConcept": "atrial_fibrillation",
                "focusSubskill": "synthesize",
                "contextKey": (
                    "?focus=normal_ecg&secondaryConcept=atrial_fibrillation"
                    "&receiptConcept=normal_ecg&subskill=synthesize"
                ),
                "exclusions": [],
            },
        )
        assert response.status_code == 200, response.text
        round_id = response.json()["round"]["roundId"]

        first_pending = client.post(f"/rapid/rounds/{round_id}/next", json={})
        assert first_pending.status_code == 200, first_pending.text
        first_ref = first_pending.json()["current"]["case"]["caseId"]
        first_id = _canonical_pending(round_id)
        first_case = repo.get_case(first_id) or {}
        assert "normal_ecg" in (first_case.get("supported_objectives") or [])

        first_submit = client.post(
            f"/rapid/rounds/{round_id}/submit",
            json={
                "caseId": first_ref,
                "structuredAnswer": _complete_sweep(first_case, ["normal_ecg"]),
                "freeTextAnswer": "Evidence-limited complete read: normal ECG.",
                "confidence": 4,
                "traceEvidence": {
                    "mode": "point",
                    "point": _point_from_packet(
                        first_pending.json()["current"]["packet"], first_id
                    ),
                },
            },
        )
        assert first_submit.status_code == 200, first_submit.text
        synthesis_receipt = next(
            row for row in first_submit.json()["receipts"]
            if row["concept"] == "normal_ecg" and row["subskill"] == "synthesize"
        )
        assert synthesis_receipt["accepted"] is False
        assert synthesis_receipt["evidenceLevel"] == "none"
        assert "deterministic per-domain" in synthesis_receipt["reason"]

        second_pending = client.post(f"/rapid/rounds/{round_id}/next", json={})
        assert second_pending.status_code == 200, second_pending.text
        second_ref = second_pending.json()["current"]["case"]["caseId"]
        second_id = _canonical_pending(round_id)
        second_case = repo.get_case(second_id) or {}
        assert second_id != first_id
        assert "atrial_fibrillation" in (
            second_case.get("supported_objectives") or []
        )

        second_submit = client.post(
            f"/rapid/rounds/{round_id}/submit",
            json={
                "caseId": second_ref,
                "structuredAnswer": _complete_sweep(
                    second_case, ["atrial_fibrillation"]
                ),
                "freeTextAnswer": "Evidence-limited complete read: atrial fibrillation.",
                "confidence": 4,
                "traceEvidence": {
                    "mode": "point",
                    "point": _point_from_packet(
                        second_pending.json()["current"]["packet"], second_id
                    ),
                },
            },
        )
        assert second_submit.status_code == 200, second_submit.text

        session = store.get_rapid_round(round_id)
        assert session is not None
        assert session["served"][:2] == [first_id, second_id]
        profile = client.get(f"/learners/{user['userId']}").json()
        assert [
            row for row in profile["subskillMastery"]
            if row["subskill"] == "synthesize"
        ] == []


def test_owner_can_idempotently_abandon_5000_round_and_restart_with_new_setup() -> None:
    with TestClient(app) as owner, TestClient(app) as other:
        user = _register(owner, "rapid_abandon_owner")
        _register(other, "rapid_abandon_other")
        started = _start(owner, pace="untimed", length=5000)
        round_id = started["round"]["roundId"]
        pending = owner.post(f"/rapid/rounds/{round_id}/next", json={})
        assert pending.status_code == 200, pending.text
        case_id = pending.json()["current"]["case"]["caseId"]
        activated = owner.post(
            f"/rapid/rounds/{round_id}/next", json={"activate": True}
        )
        assert activated.status_code == 200, activated.text
        assert activated.json()["round"]["pendingStartedAt"] is not None

        # Round identity is private; a different authenticated learner cannot
        # infer or mutate it through the new lifecycle endpoint.
        assert other.post(f"/rapid/rounds/{round_id}/abandon").status_code == 404

        abandoned = owner.post(f"/rapid/rounds/{round_id}/abandon")
        assert abandoned.status_code == 200, abandoned.text
        retired = abandoned.json()
        assert retired["round"]["status"] == "abandoned"
        assert retired["round"]["length"] == 5000
        assert retired["round"]["pendingCaseId"] is None
        assert retired["round"]["pendingStartedAt"] is None
        assert retired["round"]["pendingDeadlineAt"] is None
        assert retired["current"] is None
        transitioned_at = retired["round"]["updatedAt"]

        # Retrying the same command is a no-op, while every case-serving or
        # grading path remains closed after the atomic transition.
        replay = owner.post(f"/rapid/rounds/{round_id}/abandon")
        assert replay.status_code == 200, replay.text
        assert replay.json()["round"]["updatedAt"] == transitioned_at
        with store.connect() as conn:
            leases = conn.execute(
                "SELECT state FROM assessment_leases WHERE owner_id = ? "
                "AND mode = 'rapid' AND session_id = ?",
                (user["userId"], round_id),
            ).fetchall()
            assert [row["state"] for row in leases] == ["abandoned"]
            terminal_events = conn.execute(
                "SELECT event_type FROM learner_events WHERE owner_id = ? "
                "AND mode = 'rapid' AND session_id = ? "
                "AND event_type = 'item_abandoned'",
                (user["userId"], round_id),
            ).fetchall()
            assert len(terminal_events) == 1
        assert owner.get("/rapid/rounds/active").json()["round"] is None
        blocked_next = owner.post(f"/rapid/rounds/{round_id}/next", json={})
        assert blocked_next.status_code == 409
        assert blocked_next.json()["detail"]["code"] == "rapid_round_abandoned"
        blocked_submit = owner.post(
            f"/rapid/rounds/{round_id}/submit", json={"caseId": case_id}
        )
        assert blocked_submit.status_code == 409

        replacement = _start(owner, pace="emergency", length=5, contextKey="")
        assert replacement["round"]["roundId"] != round_id
        assert replacement["round"]["pace"] == "emergency"
        assert replacement["round"]["length"] == 5
        assert replacement["round"]["status"] == "active"


def test_expired_idle_rapid_lease_is_audited_once_and_rotated_for_same_frozen_ecg() -> None:
    with TestClient(app) as client:
        user = _register(client, "rapid_expiry")
        started = _start(client, pace="untimed", length=5)
        round_id = started["round"]["roundId"]
        pending = client.post(f"/rapid/rounds/{round_id}/next", json={})
        assert pending.status_code == 200, pending.text
        case_id = pending.json()["current"]["case"]["caseId"]
        with store.connect() as conn:
            old_lease_id = str(conn.execute(
                "SELECT lease_id FROM assessment_leases WHERE owner_id = ? "
                "AND mode = 'rapid' AND session_id = ? AND state = 'active'",
                (user["userId"], round_id),
            ).fetchone()[0])
            conn.execute(
                "UPDATE assessment_leases SET expires_at = '2000-01-01T00:00:00+00:00' "
                "WHERE lease_id = ?",
                (old_lease_id,),
            )

        first_resume = client.get(f"/rapid/rounds/{round_id}")
        second_resume = client.get(f"/rapid/rounds/{round_id}")
        assert first_resume.status_code == second_resume.status_code == 200
        assert first_resume.json()["current"]["case"]["caseId"] == case_id
        with store.connect() as conn:
            leases = conn.execute(
                "SELECT lease_id, state FROM assessment_leases WHERE owner_id = ? "
                "AND mode = 'rapid' AND session_id = ? ORDER BY created_at, lease_id",
                (user["userId"], round_id),
            ).fetchall()
            assert {(row["lease_id"], row["state"]) for row in leases} == {
                (old_lease_id, "expired"),
                next(
                    (str(row["lease_id"]), "active")
                    for row in leases
                    if str(row["lease_id"]) != old_lease_id
                ),
            }
            assert conn.execute(
                "SELECT COUNT(*) FROM learner_events WHERE owner_id = ? "
                "AND mode = 'rapid' AND session_id = ? "
                "AND event_type = 'item_expired'",
                (user["userId"], round_id),
            ).fetchone()[0] == 1


def test_grading_failure_releases_exact_rapid_reservation_without_partial_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with TestClient(app) as client:
        user = _register(client, "rapid_grade_release")
        started = _start(client, pace="untimed", length=5)
        round_id = started["round"]["roundId"]
        pending = client.post(f"/rapid/rounds/{round_id}/next", json={}).json()
        case_ref = pending["current"]["case"]["caseId"]
        case_id = _canonical_pending(round_id)
        packet = pending["current"]["packet"]
        case = repo.get_case(case_id) or {}
        target = case["supported_objectives"][0]

        def fail_grade(*_args, **_kwargs):
            raise RuntimeError("injected deterministic grader failure")

        monkeypatch.setattr(rapid_routes, "grade_attempt", fail_grade)
        with pytest.raises(RuntimeError, match="injected deterministic grader failure"):
            client.post(
                f"/rapid/rounds/{round_id}/submit",
                json={
                    "caseId": case_ref,
                    "structuredAnswer": _complete_sweep(case, [target]),
                    "confidence": 3,
                    "traceEvidence": {
                        "mode": "point",
                        "point": _point_from_packet(packet, case_id),
                    },
                },
            )

        with store.connect() as conn:
            lease = conn.execute(
                "SELECT state, submission_key_hash, claimed_at, terminal_at "
                "FROM assessment_leases WHERE owner_id = ? AND mode = 'rapid' "
                "AND session_id = ?",
                (user["userId"], round_id),
            ).fetchone()
            assert tuple(lease) == ("active", None, None, None)
            assert conn.execute(
                "SELECT COUNT(*) FROM rapid_round_answers WHERE round_id = ?",
                (round_id,),
            ).fetchone()[0] == 0
            assert conn.execute(
                "SELECT COUNT(*) FROM attempts WHERE learner_id = ? AND case_id = ? "
                "AND mode = 'rapid_practice'",
                (user["userId"], case_id),
            ).fetchone()[0] == 0
            assert conn.execute(
                "SELECT COUNT(*) FROM learner_events WHERE owner_id = ? "
                "AND mode = 'rapid' AND session_id = ? "
                "AND event_type = 'answer_committed'",
                (user["userId"], round_id),
            ).fetchone()[0] == 0


def test_concurrent_same_item_claims_share_one_exact_reservation_generation() -> None:
    """Two browser retries cannot create parallel grading generations."""

    with TestClient(app) as client:
        user = _register(client, "rapid_claim_race")
        started = _start(client, pace="untimed", length=5)
        round_id = started["round"]["roundId"]
        pending = client.post(f"/rapid/rounds/{round_id}/next", json={})
        assert pending.status_code == 200, pending.text
        case_id = _canonical_pending(round_id)
        coordinator = RapidAssessmentStore(store)
        ready = Barrier(2)

        def claim() -> dict:
            ready.wait(timeout=5)
            return coordinator.claim_answer_submission(
                round_id=round_id,
                case_id=case_id,
                learner_id=user["userId"],
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            first_future = executor.submit(claim)
            second_future = executor.submit(claim)
            claims = [first_future.result(timeout=10), second_future.result(timeout=10)]

        assert {claim["status"] for claim in claims} == {"claimed"}
        assert sorted(claim["replayed"] for claim in claims) == [False, True]
        assert len({claim["leaseId"] for claim in claims}) == 1
        assert len({claim["submissionKey"] for claim in claims}) == 1
        assert len({claim["position"] for claim in claims}) == 1

        winning_claim = claims[0]
        with store.connect() as conn:
            lease = conn.execute(
                "SELECT state, submission_key_hash, claimed_at, terminal_at "
                "FROM assessment_leases WHERE lease_id = ? AND owner_id = ?",
                (winning_claim["leaseId"], user["userId"]),
            ).fetchone()
            assert lease["state"] == "submitting"
            assert lease["submission_key_hash"]
            assert lease["claimed_at"]
            assert lease["terminal_at"] is None
            assert conn.execute(
                "SELECT COUNT(*) FROM rapid_round_answers WHERE round_id = ?",
                (round_id,),
            ).fetchone()[0] == 0

        assert coordinator.release_answer_submission(
            round_id=round_id,
            learner_id=user["userId"],
            lease_id=winning_claim["leaseId"],
            submission_key=winning_claim["submissionKey"],
        ) is True
        assert coordinator.release_answer_submission(
            round_id=round_id,
            learner_id=user["userId"],
            lease_id=winning_claim["leaseId"],
            submission_key=winning_claim["submissionKey"],
        ) is False
        with store.connect() as conn:
            released = conn.execute(
                "SELECT state, submission_key_hash, claimed_at, terminal_at "
                "FROM assessment_leases WHERE lease_id = ?",
                (winning_claim["leaseId"],),
            ).fetchone()
            assert tuple(released) == ("active", None, None, None)


def test_focused_selector_hard_excludes_an_owner_waveform_live_in_another_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with TestClient(app) as client:
        user = _register(client, "rapid_cross_mode")
        candidates = repo.candidates("normal_ecg")
        exposed_case = str(candidates[0]["case_id"])
        guided_case = str(candidates[1]["case_id"])
        now = datetime.now(UTC)
        with store.connect() as conn:
            create_lease(
                conn,
                lease_id=f"cross-mode-{uuid.uuid4().hex}",
                owner_id=user["userId"],
                mode="training",
                session_id=f"training-cross-mode-{uuid.uuid4().hex}",
                ecg_ids=(exposed_case,),
                created_at=now,
                expires_at=now + timedelta(hours=1),
            )
            record_guided_packet_exposure(
                conn,
                owner_id=user["userId"],
                lesson_id="rapid-cross-mode",
                ecg_id=guided_case,
                occurred_at=now,
            )

        original = rapid_routes._focused_corpus_selection
        observed: list[set[str]] = []

        def capture_exclusions(*args, **kwargs):
            excluded = set(args[3] if len(args) > 3 else kwargs["excluded"])
            observed.append(excluded)
            return original(*args, **kwargs)

        monkeypatch.setattr(rapid_routes, "_focused_corpus_selection", capture_exclusions)
        started = _start(
            client,
            pace="untimed",
            length=5,
            focusConcept="normal_ecg",
        )
        selected = client.post(
            f"/rapid/rounds/{started['round']['roundId']}/next", json={}
        )
        assert selected.status_code == 200, selected.text
        assert observed and {exposed_case, guided_case}.issubset(observed[-1])
        assert selected.json()["current"]["case"]["caseId"] not in {
            exposed_case,
            guided_case,
        }


def test_public_round_metadata_bounds_the_5000_case_served_ledger() -> None:
    served = [f"ptbxl:{index:05d}" for index in range(5000)]
    session = {"roundId": "rr_scale", "position": 5000, "served": served}

    public = _public_round(
        session, case_reference=lambda canonical_id: f"opaque:{canonical_id}"
    )

    assert "served" not in public
    assert public["servedCount"] == 5000
    assert public["recentServed"] == [
        f"opaque:{canonical_id}" for canonical_id in served[-25:]
    ]
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
        assert "exclusions" not in activated["round"]
        assert store.get_rapid_round(round_id)["exclusions"] == ["never-serve-me"]
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
        case_ref = pending["current"]["case"]["caseId"]
        case_id = _canonical_pending(round_id)
        packet = pending["current"]["packet"]
        client.post(f"/rapid/rounds/{round_id}/next", json={"activate": True})
        target = (repo.get_case(case_id) or {})["supported_objectives"][0]
        body = {
            "caseId": case_ref,
            "structuredAnswer": _complete_sweep(repo.get_case(case_id) or {}, [target]),
            "freeTextAnswer": target.replace("_", " "),
            "confidence": 4,
            "traceEvidence": {
                "mode": "point",
                "point": _point_from_packet(packet, case_id),
            },
        }
        first = client.post(f"/rapid/rounds/{round_id}/submit", json=body)
        # A retry cannot replace the committed answer even if its body differs
        # and would fail the original completion gates.
        second = client.post(
            f"/rapid/rounds/{round_id}/submit",
            json={"caseId": case_ref, "confidence": 1},
        )
        assert first.status_code == second.status_code == 200
        assert first.json()["replay"] is False
        assert second.json()["replay"] is True
        assert first.json()["answer"]["attemptId"] == second.json()["answer"]["attemptId"]
        assert second.json()["answer"] == first.json()["answer"]
        assert first.json()["answer"]["integrityStatus"] == "atomic_v2"
        with store.connect() as conn:
            lease = conn.execute(
                "SELECT state, integrity_status, submission_key_hash, claimed_at, terminal_at "
                "FROM assessment_leases WHERE owner_id = ? AND mode = 'rapid' "
                "AND session_id = ?",
                (user["userId"], round_id),
            ).fetchone()
            assert lease is not None
            assert tuple(lease)[:2] == ("submitted", "atomic_v2")
            assert all(value for value in tuple(lease)[2:])
            events = conn.execute(
                "SELECT event_type, score, integrity_status FROM learner_events "
                "WHERE owner_id = ? AND mode = 'rapid' AND session_id = ? "
                "ORDER BY event_type",
                (user["userId"], round_id),
            ).fetchall()
            assert [row["event_type"] for row in events] == [
                "answer_committed",
                "item_presented",
            ]
            assert events[0]["score"] == first.json()["answer"]["result"]["score"]
            assert events[0]["integrity_status"] == "atomic_v2"
            assert conn.execute(
                "SELECT COUNT(*) FROM learner_event_competencies AS c "
                "JOIN learner_events AS e ON e.event_id = c.event_id "
                "WHERE e.owner_id = ? AND e.mode = 'rapid' AND e.session_id = ?",
                (user["userId"], round_id),
            ).fetchone()[0] >= 1
            event_columns = {
                str(row["name"])
                for row in conn.execute("PRAGMA table_info(learner_events)").fetchall()
            }
            assert not event_columns.intersection(
                {"response_json", "answer_json", "grade_json", "feedback_json"}
            )
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
        with store.connect() as conn:
            assert conn.execute(
                "SELECT COUNT(*) FROM attempts WHERE id = ?",
                (first.json()["answer"]["attemptId"],),
            ).fetchone()[0] == 1
            assert conn.execute(
                "SELECT COUNT(*) FROM guided_learning_events WHERE event_key LIKE ?",
                (f"rapid:{round_id}:{case_id}:%",),
            ).fetchone()[0] == len(accepted)
            assert conn.execute(
                "SELECT COUNT(*) FROM subskill_retention_events WHERE learner_id = ? "
                "AND case_id = ? AND mode = 'rapid'",
                (user["userId"], case_id),
            ).fetchone()[0] == len(accepted)
        ledger = client.get(f"/rapid/rounds/{round_id}/results?offset=0&limit=5000")
        assert ledger.status_code == 200
        assert ledger.json()["total"] == 1
        assert ledger.json()["results"][0]["caseId"] == case_ref


def test_rapid_finalization_rolls_back_every_receipt_and_advance_boundary() -> None:
    with TestClient(app) as client:
        user = _register(client, "rapid_atomic")
        started = _start(client, pace="untimed", length=5, focusConcept="normal_ecg")
        round_id = started["round"]["roundId"]
        pending = client.post(f"/rapid/rounds/{round_id}/next", json={}).json()
        case_ref = pending["current"]["case"]["caseId"]
        case_id = _canonical_pending(round_id)
        packet = pending["current"]["packet"]
        activated = client.post(
            f"/rapid/rounds/{round_id}/next", json={"activate": True}
        )
        assert activated.status_code == 200, activated.text
        case = repo.get_case(case_id) or {}
        target = case["supported_objectives"][0]
        body = {
            "caseId": case_ref,
            "structuredAnswer": _complete_sweep(case, [target]),
            "freeTextAnswer": target.replace("_", " "),
            "confidence": 4,
            "traceEvidence": {
                "mode": "point",
                "point": _point_from_packet(packet, case_id),
            },
        }
        baseline = _rapid_atomic_snapshot(round_id, user["userId"], case_id)

        # First discover the complete checkpoint sequence while failing after
        # the round UPDATE but before COMMIT. This itself proves the furthest
        # boundary rolls back, and prevents the test from assuming how many
        # frozen objective receipts a future manifest may contain.
        checkpoints: list[str] = []

        def fail_after_advance(label: str) -> None:
            checkpoints.append(label)
            if label == "after_round_advance":
                raise RuntimeError("injected:after_round_advance")

        setattr(store, "_rapid_finalization_failure_hook", fail_after_advance)
        try:
            with pytest.raises(RuntimeError, match="injected:after_round_advance"):
                client.post(f"/rapid/rounds/{round_id}/submit", json=body)
        finally:
            delattr(store, "_rapid_finalization_failure_hook")
        assert checkpoints[-1] == "after_round_advance"
        assert any(label.startswith("after_receipt:") for label in checkpoints)
        assert _rapid_atomic_snapshot(round_id, user["userId"], case_id) == baseline

        # Fail independently at every earlier write boundary, including every
        # individual static/event receipt and the receipt-ledger promotion.
        for checkpoint in checkpoints[:-1]:
            seen: list[str] = []

            def fail_at_boundary(label: str, *, target: str = checkpoint) -> None:
                seen.append(label)
                if label == target:
                    raise RuntimeError(f"injected:{target}")

            setattr(store, "_rapid_finalization_failure_hook", fail_at_boundary)
            try:
                with pytest.raises(RuntimeError, match=f"injected:{checkpoint}"):
                    client.post(f"/rapid/rounds/{round_id}/submit", json=body)
            finally:
                delattr(store, "_rapid_finalization_failure_hook")
            assert checkpoint in seen
            assert _rapid_atomic_snapshot(round_id, user["userId"], case_id) == baseline

        committed = client.post(f"/rapid/rounds/{round_id}/submit", json=body)
        assert committed.status_code == 200, committed.text
        assert committed.json()["replay"] is False
        assert committed.json()["answer"]["integrityStatus"] == "atomic_v2"
        durable = _rapid_atomic_snapshot(round_id, user["userId"], case_id)
        assert durable["answers"] == durable["attempts"] == 1
        assert durable["events"] == durable["retention"]
        assert durable["events"] >= 1
        assert durable["round"][0] is None
        assert durable["round"][1] == case_id
        assert durable["round"][3] == 1

        replay = client.post(
            f"/rapid/rounds/{round_id}/submit",
            json={"caseId": case_ref, "confidence": 1},
        )
        assert replay.status_code == 200, replay.text
        assert replay.json()["replay"] is True
        assert replay.json()["answer"] == committed.json()["answer"]
        assert _rapid_atomic_snapshot(round_id, user["userId"], case_id) == durable


def test_legacy_incomplete_rapid_answer_is_quarantined_without_repair() -> None:
    with TestClient(app) as client:
        user = _register(client, "rapid_quarantine")
        started = _start(client, pace="untimed", length=5, focusConcept="normal_ecg")
        round_id = started["round"]["roundId"]
        pending = client.post(f"/rapid/rounds/{round_id}/next", json={}).json()
        case_ref = pending["current"]["case"]["caseId"]
        case_id = _canonical_pending(round_id)
        session = store.get_rapid_round(round_id)
        assert session is not None
        with store.connect() as conn:
            conn.execute(
                """
                INSERT INTO rapid_round_answers (
                    round_id, case_id, response_json, grade_json, tutor_json,
                    result_json, trace_grade_json, tested_manifest_json,
                    receipts_json, integrity_status, attempt_id, created_at
                ) VALUES (?, ?, '{}', '{}', 'null', '{}', NULL, ?, '[]',
                          'legacy_incomplete', 0, ?)
                """,
                (
                    round_id,
                    case_id,
                    json.dumps(session["pendingTestedObjectiveManifest"]),
                    session["updatedAt"],
                ),
            )

        before = _rapid_atomic_snapshot(round_id, user["userId"], case_id)
        response = client.post(
            f"/rapid/rounds/{round_id}/submit",
            json={"caseId": case_ref, "confidence": 5},
        )
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "rapid_legacy_answer_quarantined"
        assert _rapid_atomic_snapshot(round_id, user["userId"], case_id) == before
        assert store.learning_record_integrity() == (True, "ready")


def test_axis_text_or_unsupported_explicit_axis_cannot_create_axis_mastery() -> None:
    with TestClient(app) as client:
        user = _register(client, "rapid_axis")
        started = _start(client, pace="untimed", length=5, focusConcept="normal_ecg")
        round_id = started["round"]["roundId"]
        pending = client.post(f"/rapid/rounds/{round_id}/next", json={}).json()
        case_ref = pending["current"]["case"]["caseId"]
        case_id = _canonical_pending(round_id)
        point = _point_from_packet(pending["current"]["packet"], case_id)
        response = client.post(
            f"/rapid/rounds/{round_id}/submit",
            json={
                "caseId": case_ref,
                "structuredAnswer": {
                    **_complete_sweep(repo.get_case(case_id) or {}, ["right_axis_deviation"]),
                    "axis": "definite right axis deviation",
                    "synthesis": "Evidence-limited complete read: right axis deviation.",
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
        case_ref = pending["current"]["case"]["caseId"]
        case_id = _canonical_pending(round_id)
        point = _point_from_packet(pending["current"]["packet"], case_id)
        response = client.post(
            f"/rapid/rounds/{round_id}/submit",
            json={
                "caseId": case_ref,
                "structuredAnswer": _complete_sweep(
                    repo.get_case(case_id) or {},
                    ["uncertain"],
                ),
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


def test_complete_sweep_filler_creates_no_synthesis_mastery_evidence() -> None:
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
        case_ref = pending["current"]["case"]["caseId"]
        case_id = _canonical_pending(round_id)
        packet = pending["current"]["packet"]
        case = repo.get_case(case_id)
        selected = ["normal_ecg"]
        filler_sweep = {
            key: "placeholder text"
            for key in (
                "rate", "rhythm", "axis", "intervals", "conduction", "st_t",
                "hypertrophy", "synthesis",
            )
        }
        response = client.post(
            f"/rapid/rounds/{round_id}/submit",
            json={
                "caseId": case_ref,
                "structuredAnswer": {
                    "framework": "clerkship",
                    **filler_sweep,
                    "selectedConcepts": selected,
                },
                "freeTextAnswer": "placeholder text",
                "confidence": 4,
                "traceEvidence": {
                    "mode": "point",
                    "point": _point_from_packet(packet, case_id),
                },
            },
        )
        assert response.status_code == 200, response.text
        manifest = response.json()["answer"]["testedObjectiveManifest"]
        assert manifest["taskKind"] == "focused_handoff"
        assert manifest["selectedSupportedExtras"] == []
        assert [
            (entry["objectiveId"], entry["subskill"])
            for entry in manifest["objectives"]
        ] == []
        receipt = next(
            row for row in response.json()["receipts"]
            if row["concept"] == "integrated_interpretation"
            and row["subskill"] == "synthesize"
        )
        assert receipt["accepted"] is False
        assert receipt["evidenceLevel"] == "none"
        assert "deterministic per-domain" in receipt["reason"]
        profile = client.get(f"/learners/{user['userId']}").json()
        synthesis_rows = [
            item for item in profile["subskillMastery"]
            if item["subskill"] == "synthesize"
        ]
        assert synthesis_rows == []


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
        case_ref = pending["current"]["case"]["caseId"]
        case_id = _canonical_pending(round_id)
        response = client.post(
            f"/rapid/rounds/{round_id}/submit",
            json={
                "caseId": case_ref,
                "structuredAnswer": {
                    "framework": "clerkship",
                    "selectedConcepts": ["normal_ecg"],
                    "synthesis": "A long confident free-text synthesis without the structured sweep.",
                },
                "freeTextAnswer": "A long confident free-text synthesis without the structured sweep.",
                "confidence": 5,
                "traceEvidence": {
                    "mode": "point",
                    "point": _point_from_packet(
                        pending["current"]["packet"], case_id
                    ),
                },
            },
        )
        assert response.status_code == 422, response.text
        assert response.json()["detail"]["code"] == "rapid_systematic_sweep_required"


def test_proxy_case_cannot_launder_an_unreviewed_alias_synthesis_receipt() -> None:
    with TestClient(app) as client:
        _register(client, "synth_alias_guard")
        started = _start(
            client,
            pace="untimed",
            length=1,
            focusConcept="normal_ecg",
            focusSubskill="synthesize",
            contextKey=(
                "?focus=normal_ecg&receiptConcept=integrated_capstone"
                "&subskill=synthesize"
            ),
        )
        round_id = started["round"]["roundId"]
        pending = client.post(f"/rapid/rounds/{round_id}/next", json={}).json()
        case_ref = pending["current"]["case"]["caseId"]
        case_id = _canonical_pending(round_id)
        case = repo.get_case(case_id)
        selected = list(dict.fromkeys(case.get("supported_objectives") or []))
        response = client.post(
            f"/rapid/rounds/{round_id}/submit",
            json={
                "caseId": case_ref,
                "structuredAnswer": _complete_sweep(case, selected),
                "freeTextAnswer": "A complete sweep cannot substitute for an unreviewed capstone contract.",
                "confidence": 4,
                "traceEvidence": {
                    "mode": "point",
                    "point": _point_from_packet(
                        pending["current"]["packet"], case_id
                    ),
                },
            },
        )
        assert response.status_code == 200, response.text
        receipt = next(
            row for row in response.json()["receipts"]
            if row["concept"] == "integrated_capstone"
            and row["subskill"] == "synthesize"
        )
        assert receipt["accepted"] is False
        assert receipt["evidenceLevel"] == "none"
        assert "deterministic per-domain" in receipt["reason"]
