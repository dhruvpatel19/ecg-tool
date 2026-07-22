from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient

from app import main as main_module
from app.auth import AuthService
from app.guest_progress import GuestProgressService
from app.main import app, store
from app.storage import LearningStore
from app.study_calendar import _launch_href


_PASSWORD = "Calendar-Test-Password!"


def _register(client: TestClient, prefix: str, *, claim_guest: bool = False) -> dict:
    response = client.post(
        "/auth/register",
        json={
            "username": f"{prefix}_{uuid.uuid4().hex[:10]}",
            "password": _PASSWORD,
            "claimGuestProgress": claim_guest,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _window(center: date | None = None) -> tuple[str, str]:
    today = center or datetime.now(UTC).date()
    return today.isoformat(), (today + timedelta(days=6)).isoformat()


def _calendar(client: TestClient, *, time_zone: str = "UTC"):
    start, end = _window()
    return client.get(
        "/learning/calendar",
        params={"startDate": start, "endDate": end, "timeZone": time_zone},
    )


def _first_runnable_cell(client: TestClient, learner_id: str) -> tuple[str, str]:
    registry = client.get(f"/learners/{learner_id}/competencies")
    assert registry.status_code == 200, registry.text
    for objective in registry.json()["objectives"]:
        for cell in objective["subskills"]:
            if cell["independentReceipt"] is not None:
                return objective["objectiveId"], cell["subskill"]
    raise AssertionError("The checked test corpus has no independent competency route")


def test_emergency_rhythm_calendar_receipt_uses_the_isolated_practice_mode() -> None:
    href = _launch_href(
        {
            "mode": "rapid",
            "caseConcept": "ventricular_fibrillation",
            "receiptConcept": "ventricular_fibrillation",
            "subskill": "recognize",
        },
        scheduled_date="2026-07-17",
    )
    assert href is not None
    assert "focus=ventricular_fibrillation" in href
    assert "practiceMode=emergency" in href
    assert "returnTo=%2Fhome%3Fpanel%3Dcalendar%26date%3D2026-07-17" in href


def test_dashboard_and_calendar_share_the_exact_focused_pool_gate(monkeypatch) -> None:
    definition = main_module.OBJECTIVES["right_bundle_branch_block"]
    runtime = main_module.objective_runtime_availability(definition, main_module.repo)
    counts = main_module.repo.concept_ab_counts()
    monkeypatch.setattr(
        main_module,
        "_training_pool_receipt_available",
        lambda _concept, _subskill: False,
    )

    assert main_module._independent_receipt_contract(
        definition, runtime, counts, "localize"
    ) is None
    assert main_module._calendar_receipt_contracts()[
        ("right_bundle_branch_block", "localize")
    ] is None
    assert main_module._independent_receipt_contract(
        definition, runtime, counts, "recognize"
    ) == {
        "mode": "rapid",
        "caseConcept": "right_bundle_branch_block",
        "receiptConcept": "right_bundle_branch_block",
        "subskill": "recognize",
    }


def test_calendar_manual_crud_is_owner_bound_idempotent_and_revision_safe() -> None:
    with TestClient(app) as owner, TestClient(app) as other:
        owner_registration = _register(owner, "calendar_owner")
        _register(other, "calendar_other")
        start, _ = _window()

        initial = _calendar(owner, time_zone="America/New_York")
        assert initial.status_code == 200, initial.text
        assert initial.headers["cache-control"] == "no-store, private"
        assert initial.json()["settings"] == {
            "timeZone": "America/New_York",
            "weekStartsOn": 0,
            "saved": False,
            "updatedAt": None,
        }
        assert owner.put(
            "/learning/calendar/settings",
            json={"timeZone": "Not/AZone", "weekStartsOn": 0},
        ).status_code == 422
        saved_settings = owner.put(
            "/learning/calendar/settings",
            json={"timeZone": "America/New_York", "weekStartsOn": 1},
        )
        assert saved_settings.status_code == 200
        assert saved_settings.json()["saved"] is True
        saved_projection = _calendar(owner, time_zone="Asia/Tokyo")
        assert saved_projection.status_code == 200
        assert saved_projection.json()["settings"]["timeZone"] == "America/New_York"
        assert saved_projection.json()["settings"]["saved"] is True
        competency_projection = owner.get(
            f"/learners/{owner_registration['user']['userId']}/competencies",
            headers={"X-ECG-Time-Zone": "Asia/Tokyo"},
        )
        assert competency_projection.status_code == 200
        assert competency_projection.json()["calendarProjection"] == {
            "timeZone": "America/New_York",
            "today": saved_projection.json()["today"],
            "reviewDays": [],
        }

        request_id = f"manual-{uuid.uuid4()}"
        payload = {
            "title": "  Review ECG notes  ",
            "notes": "  Bring calipers  ",
            "scheduledDate": start,
            "startMinute": 19 * 60,
            "durationMinutes": 25,
            "clientRequestId": request_id,
        }
        created = owner.post("/learning/calendar/items", json=payload)
        replay = owner.post("/learning/calendar/items", json=payload)
        assert created.status_code == replay.status_code == 201
        assert created.json() == replay.json()
        item = created.json()
        assert item["source"] == "manual"
        assert item["title"] == "Review ECG notes"
        assert item["notes"] == "Bring calipers"
        assert item["competency"] is None
        assert item["revision"] == 1
        exported = store.export_user_progress(owner_registration["user"]["userId"])
        assert exported is not None
        assert exported["recordCounts"]["learnerCalendarSettings"] == 1
        assert exported["recordCounts"]["studyCalendarItems"] == 1
        assert exported["records"]["studyCalendarItems"][0]["title"] == "Review ECG notes"

        conflict = owner.post(
            "/learning/calendar/items",
            json={**payload, "title": "Different"},
        )
        assert conflict.status_code == 409
        assert conflict.json()["detail"]["code"] == "calendar_request_conflict"
        assert _calendar(other).json()["items"] == []
        foreign = other.patch(
            f"/learning/calendar/items/{item['itemId']}",
            json={"revision": 1, "title": "No"},
        )
        assert foreign.status_code == 404

        edited = owner.patch(
            f"/learning/calendar/items/{item['itemId']}",
            json={"revision": 1, "title": "Focused ECG review", "startMinute": None},
        )
        assert edited.status_code == 200, edited.text
        assert edited.json()["startMinute"] is None
        assert edited.json()["revision"] == 2
        stale = owner.patch(
            f"/learning/calendar/items/{item['itemId']}",
            json={"revision": 1, "title": "Stale edit"},
        )
        assert stale.status_code == 409
        assert stale.json()["detail"]["current"]["revision"] == 2

        completed = owner.put(
            f"/learning/calendar/items/{item['itemId']}/completion",
            json={"revision": 2},
        )
        assert completed.status_code == 200
        assert completed.json()["status"] == "completed"
        assert completed.json()["completionSource"] == "manual"
        # Same desired state is an idempotent replay even when the caller still
        # holds the pre-completion revision.
        repeated = owner.put(
            f"/learning/calendar/items/{item['itemId']}/completion",
            json={"revision": 2},
        )
        assert repeated.status_code == 200
        assert repeated.json() == completed.json()

        reopened = owner.delete(
            f"/learning/calendar/items/{item['itemId']}/completion",
            params={"revision": completed.json()["revision"]},
        )
        assert reopened.status_code == 200
        assert reopened.json()["status"] == "scheduled"
        removed = owner.delete(
            f"/learning/calendar/items/{item['itemId']}",
            params={"revision": reopened.json()["revision"]},
        )
        assert removed.json() == {"deleted": True, "itemId": item["itemId"]}
        assert _calendar(owner).json()["items"] == []


def test_mode_aware_manual_blocks_and_current_plan_actions_are_server_routed() -> None:
    with TestClient(app) as client:
        registration = _register(client, "calendar_plan")
        learner_id = registration["user"]["userId"]
        today, _ = _window()

        manual = client.post(
            "/learning/calendar/items",
            json={
                "title": "Clinical handoff practice",
                "scheduledDate": today,
                "mode": "clinical",
                "clientRequestId": f"manual-mode-{uuid.uuid4()}",
            },
        )
        assert manual.status_code == 201, manual.text
        assert manual.json()["activity"] == {
            "kind": "manual_mode",
            "mode": "clinical",
            "objectiveId": None,
            "objectiveLabel": None,
            "subskill": None,
            "caseConcept": None,
            "sourceCurrent": None,
            "launchHref": (
                f"/practice?returnTo=%2Fhome%3Fpanel%3Dcalendar%26date%3D{today}"
            ),
        }
        arbitrary_route = client.post(
            "/learning/calendar/items",
            json={
                "title": "Unsafe route",
                "scheduledDate": today,
                "mode": "rapid",
                "launchHref": "https://example.com",
                "clientRequestId": f"manual-unsafe-{uuid.uuid4()}",
            },
        )
        assert arbitrary_route.status_code == 422

        plan_response = client.get("/adaptive/plan")
        assert plan_response.status_code == 200, plan_response.text
        action = plan_response.json()["calendarAction"]
        assert action is not None
        assert action["mode"] in {"train", "rapid"}
        assert action["objectiveId"] and action["subskill"] and action["caseConcept"]

        request_id = f"plan-{uuid.uuid4()}"
        payload = {
            "expectedActionKey": action["actionKey"],
            "scheduledDate": today,
            "startMinute": 9 * 60,
            "durationMinutes": 30,
            "notes": "Confirm after rounds",
            "clientRequestId": request_id,
        }
        scheduled = client.post("/learning/calendar/items/from-plan", json=payload)
        assert scheduled.status_code == 201, scheduled.text
        item = scheduled.json()
        assert item["source"] == "study_plan"
        assert item["competency"] is None
        assert item["activity"]["kind"] == "study_plan"
        assert item["activity"]["mode"] == action["mode"]
        assert item["activity"]["objectiveId"] == action["objectiveId"]
        assert item["activity"]["subskill"] == action["subskill"]
        assert item["activity"]["sourceCurrent"] is True
        assert item["activity"]["launchHref"].startswith(f"/{action['mode']}?")
        assert "%2Fhome%3Fpanel%3Dcalendar%26date%3D" in item["activity"]["launchHref"]

        replay = client.post("/learning/calendar/items/from-plan", json=payload)
        assert replay.status_code == 201
        assert replay.json()["itemId"] == item["itemId"]
        assert replay.json()["activity"]["sourceCurrent"] is True
        assert _calendar(client).json()["today"] == datetime.now(UTC).date().isoformat()

        stale = client.post(
            "/learning/calendar/items/from-plan",
            json={**payload, "expectedActionKey": "0" * 64, "clientRequestId": f"stale-{uuid.uuid4()}"},
        )
        assert stale.status_code == 409
        assert stale.json()["detail"]["code"] == "calendar_plan_changed"

        with store.connect() as conn:
            persisted = conn.execute(
                "SELECT source, target_objective, target_subskill, target_mode, "
                "target_launch_href, source_plan_key FROM study_calendar_items "
                "WHERE learner_id = ? AND item_id = ?",
                (learner_id, item["itemId"]),
            ).fetchone()
        assert dict(persisted) == {
            "source": "study_plan",
            "target_objective": action["objectiveId"],
            "target_subskill": action["subskill"],
            "target_mode": action["mode"],
            "target_launch_href": item["activity"]["launchHref"],
            "source_plan_key": action["actionKey"],
        }


def test_live_due_projection_and_exact_schedule_never_mutate_retention() -> None:
    with TestClient(app) as client:
        registration = _register(client, "calendar_due")
        learner_id = registration["user"]["userId"]
        objective_id, subskill = _first_runnable_cell(client, learner_id)
        due_at = (datetime.now(UTC) - timedelta(days=2)).isoformat()
        now = datetime.now(UTC).isoformat()
        with store.connect() as conn:
            conn.execute(
                "INSERT INTO subskill_mastery ("
                "learner_id, concept, subskill, formative_score, independent_mastery, "
                "attempts, independent_attempts, correct, last_practiced_at, "
                "next_due_at, stability_days, last_independent_at, "
                "last_independent_correct"
                ") VALUES (?, ?, ?, 0.8, 0.75, 1, 1, 1, ?, ?, 3.0, ?, 1)",
                (learner_id, objective_id, subskill, now, due_at, now),
            )

        snapshot = _calendar(client).json()
        today = datetime.now(UTC).date().isoformat()
        review_day = next(day for day in snapshot["reviewDays"] if day["date"] == today)
        review = next(
            item
            for item in review_day["items"]
            if item["objectiveId"] == objective_id and item["subskill"] == subskill
        )
        assert review["dueState"] == "overdue"
        assert review["launchHref"].startswith(("/train?", "/rapid?"))
        assert review["plannedFor"] is None
        plan = client.get("/adaptive/plan").json()
        expected_priority = next(
            (
                index
                for index, priority in enumerate(plan["priorities"], start=1)
                if priority["objectiveId"] == objective_id
                and priority["subskill"] == subskill
            ),
            None,
        )
        assert review["planPriority"] == expected_priority

        stale = client.post(
            "/learning/calendar/items/from-competency",
            json={
                "objectiveId": objective_id,
                "subskill": subskill,
                "expectedNextDueAt": (datetime.now(UTC) - timedelta(days=3)).isoformat(),
                "scheduledDate": today,
                "clientRequestId": f"review-stale-{uuid.uuid4()}",
            },
        )
        assert stale.status_code == 409
        assert stale.json()["detail"]["code"] == "calendar_source_changed"
        assert stale.json()["detail"]["currentNextDueAt"] == due_at

        scheduled = client.post(
            "/learning/calendar/items/from-competency",
            json={
                "objectiveId": objective_id,
                "subskill": subskill,
                "expectedNextDueAt": due_at,
                "scheduledDate": today,
                "durationMinutes": 20,
                "clientRequestId": f"review-{uuid.uuid4()}",
            },
        )
        assert scheduled.status_code == 201, scheduled.text
        item = scheduled.json()
        assert item["source"] == "retention_review"
        assert item["competency"]["sourceCurrent"] is True
        assert item["competency"]["currentDueAt"] == due_at
        assert item["competency"]["launchHref"].startswith(("/train?", "/rapid?"))

        planned_snapshot = _calendar(client).json()
        planned_review = next(
            review
            for day in planned_snapshot["reviewDays"]
            for review in day["items"]
            if review["objectiveId"] == objective_id and review["subskill"] == subskill
        )
        assert planned_review["plannedFor"] == today
        assert planned_review["scheduledItemId"] == item["itemId"]

        completed = client.put(
            f"/learning/calendar/items/{item['itemId']}/completion",
            json={"revision": item["revision"]},
        )
        assert completed.status_code == 200
        with store.connect() as conn:
            persisted = conn.execute(
                "SELECT next_due_at, independent_attempts FROM subskill_mastery "
                "WHERE learner_id = ? AND concept = ? AND subskill = ?",
                (learner_id, objective_id, subskill),
            ).fetchone()
        assert persisted["next_due_at"] == due_at
        assert int(persisted["independent_attempts"]) == 1
        after_completion = _calendar(client).json()
        assert any(
            review["objectiveId"] == objective_id
            and review["subskill"] == subskill
            and review["plannedFor"] is None
            for day in after_completion["reviewDays"]
            for review in day["items"]
        )


def test_guest_calendar_claim_preserves_items_and_account_settings_win(
    tmp_path, monkeypatch
) -> None:
    # Test mode maps anonymous requests to the shared deterministic ``demo``
    # owner. Keep this one-time claim contract independent from the preference
    # and resume claim tests that exercise the same namespace.
    isolated_store = LearningStore(
        tmp_path / f"calendar-claim-{uuid.uuid4().hex}.db"
    )
    isolated_claims = GuestProgressService(isolated_store)
    isolated_auth = AuthService(isolated_store, isolated_claims)
    monkeypatch.setattr(main_module, "store", isolated_store)
    monkeypatch.setattr(main_module, "guest_progress_service", isolated_claims)
    monkeypatch.setattr(main_module, "auth_service", isolated_auth)

    with TestClient(app) as client:
        today, _ = _window()
        assert client.put(
            "/learning/calendar/settings",
            json={"timeZone": "America/Chicago", "weekStartsOn": 1},
        ).status_code == 200
        guest_item = client.post(
            "/learning/calendar/items",
            json={
                "title": "Guest study block",
                "scheduledDate": today,
                "clientRequestId": f"guest-{uuid.uuid4()}",
            },
        )
        assert guest_item.status_code == 201

        registration = _register(client, "calendar_claim", claim_guest=True)
        summary = registration["guestClaim"]["guestProgress"]
        assert summary["calendarSettings"] == 1
        assert summary["calendarItems"] == 1
        claimed = _calendar(client, time_zone="America/Chicago").json()
        assert claimed["settings"]["timeZone"] == "America/Chicago"
        assert claimed["settings"]["saved"] is True
        assert [item["title"] for item in claimed["items"]] == ["Guest study block"]


def test_schema_v8_installs_calendar_tables_indexes_and_owner_guards() -> None:
    with store.connect() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 8
        tables = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        assert {"learner_calendar_settings", "study_calendar_items"} <= tables
        triggers = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'trigger'"
            ).fetchall()
        }
        assert {
            "account_generation_guard_learner_calendar_settings_insert",
            "account_generation_guard_study_calendar_items_insert",
        } <= triggers
        indexes = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index' "
                "AND tbl_name = 'study_calendar_items'"
            ).fetchall()
        }
        assert {
            "idx_study_calendar_owner_date",
            "idx_study_calendar_owner_target",
        } <= indexes
