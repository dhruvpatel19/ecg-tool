"""Cookie sessions, credential compatibility, and learner-data ownership."""

from __future__ import annotations

import os
import uuid
from types import SimpleNamespace

from fastapi import Response
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("ECG_CORPUS_ROOT", "data/ecg_corpus_smoke")

from app import auth as auth_module  # noqa: E402
from app.auth import LOGIN_BLOCK_MINUTES, PASSWORD_ITERATIONS, hash_password, verify_password  # noqa: E402
from app import main as main_module  # noqa: E402
from app.main import app, auth_service, store  # noqa: E402

_PASSWORD = "Sup3r-Secret-Pw!"


def _username(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def _register(client: TestClient, prefix: str, display_name: str | None = None) -> dict:
    username = _username(prefix)
    response = client.post(
        "/auth/register",
        json={"username": username, "password": _PASSWORD, "displayName": display_name},
    )
    assert response.status_code == 200, response.text
    return response.json()["user"]


def test_password_hash_roundtrip_and_legacy_iteration_compatibility() -> None:
    current = hash_password("hunter2-long")
    assert current.startswith(f"pbkdf2_sha256${PASSWORD_ITERATIONS}$")
    assert verify_password("hunter2-long", current)
    assert not verify_password("wrong", current)

    legacy = hash_password("hunter2-long", iterations=200_000)
    assert verify_password("hunter2-long", legacy)


def test_register_validation_and_case_insensitive_login() -> None:
    with TestClient(app) as client:
        username = _username("CaseUser")
        reg = client.post(
            "/auth/register",
            json={"username": username.upper(), "password": _PASSWORD, "displayName": "Case User"},
        )
        assert reg.status_code == 200
        assert "token" not in reg.json()
        assert reg.json()["user"]["username"] == username.lower()

        duplicate = client.post(
            "/auth/register",
            json={"username": username.swapcase(), "password": _PASSWORD},
        )
        assert duplicate.status_code == 400
        assert duplicate.json()["detail"]["field"] == "username"
        assert duplicate.json()["detail"]["code"] == "username_taken"

        short = client.post(
            "/auth/register",
            json={"username": _username("short"), "password": "123456789"},
        )
        assert short.status_code == 400
        assert short.json()["detail"] == {
            "field": "password",
            "code": "password_too_short",
            "message": "Password must be at least 10 characters.",
        }
        reserved = client.post("/auth/register", json={"username": "demo", "password": _PASSWORD})
        assert reserved.status_code == 400
        assert reserved.json()["detail"]["field"] == "username"

        oversized = client.post(
            "/auth/register",
            json={"username": "x" * 65, "password": "p" * 257, "displayName": "d" * 81},
        )
        assert oversized.status_code == 422

        client.post("/auth/logout")
        login = client.post("/auth/login", json={"username": username.upper(), "password": _PASSWORD})
        assert login.status_code == 200
        assert "token" not in login.json()
        assert login.json()["user"]["username"] == username.lower()

        missing = client.post("/auth/login", json={"username": _username("missing"), "password": "wrong-password"})
        wrong = client.post("/auth/login", json={"username": username, "password": "wrong-password"})
        assert missing.status_code == wrong.status_code == 401
        assert missing.json() == wrong.json() == {"detail": {"message": "Invalid username or password."}}


def test_cookie_hydration_and_logout_revocation() -> None:
    with TestClient(app) as client:
        user = _register(client, "cookie", "Cookie Learner")
        cookie = client.cookies.get("ecg_session")
        assert cookie
        with store.connect() as conn:
            stored = conn.execute(
                "SELECT token FROM sessions WHERE user_id = ?", (user["userId"],)
            ).fetchone()["token"]
        assert stored != cookie
        assert len(stored) == 64
        assert all(character in "0123456789abcdef" for character in stored)

        set_cookie = client.post(
            "/auth/login",
            json={"username": user["username"], "password": _PASSWORD},
        ).headers["set-cookie"].lower()
        assert "httponly" in set_cookie
        assert "samesite=lax" in set_cookie
        assert "path=/" in set_cookie
        rotated_cookie = client.cookies.get("ecg_session")
        assert rotated_cookie and rotated_cookie != cookie
        assert auth_service.resolve(cookie) is None
        assert auth_service.resolve(rotated_cookie) == user["userId"]

        me = client.get("/auth/me").json()
        assert me["authenticated"] is True
        assert me["user"]["userId"] == user["userId"]

        logout = client.post("/auth/logout")
        assert logout.status_code == 200
        assert "max-age=0" in logout.headers["set-cookie"].lower()
        assert client.get("/auth/me").json() == {"authenticated": False, "user": None}


def test_password_change_rotates_this_device_and_revokes_other_devices() -> None:
    replacement = "N3w-Private-Password!"
    with TestClient(app) as first, TestClient(app) as second:
        user = _register(first, "password_change", "Password Learner")
        login = second.post(
            "/auth/login", json={"username": user["username"], "password": _PASSWORD}
        )
        assert login.status_code == 200
        second_cookie = second.cookies.get("ecg_session")

        changed = first.post(
            "/auth/change-password",
            json={"currentPassword": _PASSWORD, "newPassword": replacement},
        )
        assert changed.status_code == 200, changed.text
        assert changed.json()["revokedOtherSessions"] is True
        assert first.get("/auth/me").json()["authenticated"] is True
        assert second.get(f"/learners/{user['userId']}").status_code == 401
        assert auth_service.resolve(second_cookie) is None

        first.post("/auth/logout")
        old_password = first.post(
            "/auth/login", json={"username": user["username"], "password": _PASSWORD}
        )
        assert old_password.status_code == 401
        new_password = first.post(
            "/auth/login", json={"username": user["username"], "password": replacement}
        )
        assert new_password.status_code == 200


def test_logout_all_revokes_every_device() -> None:
    with TestClient(app) as first, TestClient(app) as second:
        user = _register(first, "logout_all")
        assert second.post(
            "/auth/login", json={"username": user["username"], "password": _PASSWORD}
        ).status_code == 200
        revoked = first.post("/auth/logout-all")
        assert revoked.status_code == 200
        assert revoked.json()["revokedSessions"] == 2
        assert first.cookies.get("ecg_session") is None
        assert second.get(f"/learners/{user['userId']}").status_code == 401


def test_expired_presented_cookie_cannot_silently_write_to_guest() -> None:
    with TestClient(app) as client:
        user = _register(client, "expired", "Expired Session Learner")
        token = client.cookies.get("ecg_session")
        assert token
        auth_service.logout(token)

        rejected = client.put(
            "/learners/demo",
            json={"displayName": "Must not become guest data"},
        )
        assert rejected.status_code == 401
        assert rejected.json()["detail"] == "Invalid or expired session"
        assert store.ensure_profile("demo")["displayName"] != "Must not become guest data"

        # Hydration may confirm expiry, clears the stale browser credential, and
        # only then allows the UI to enter its isolated guest preview.
        me = client.get("/auth/me")
        assert me.status_code == 200
        assert me.json() == {"authenticated": False, "user": None}
        assert client.cookies.get("ecg_session") is None


def test_invalid_bearer_is_not_hidden_by_a_valid_cookie() -> None:
    with TestClient(app) as client:
        _register(client, "bearer_precedence")
        response = client.get("/learners/demo", headers={"Authorization": "Bearer not-a-session"})
        assert response.status_code == 401


def test_failed_login_is_bounded_without_changing_the_generic_error(monkeypatch) -> None:
    monkeypatch.setattr(auth_module, "LOGIN_PAIR_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(auth_module, "LOGIN_IP_MAX_ATTEMPTS", 1_000_000)
    monkeypatch.setattr(auth_module, "LOGIN_GLOBAL_MAX_ATTEMPTS", 1_000_000)
    with TestClient(app) as client:
        user = _register(client, "throttle")
        client.post("/auth/logout")
        for _ in range(2):
            response = client.post(
                "/auth/login", json={"username": user["username"], "password": "wrong-password"}
            )
            assert response.status_code == 401
            assert response.json() == {"detail": {"message": "Invalid username or password."}}

        blocked = client.post(
            "/auth/login", json={"username": user["username"], "password": "wrong-password"}
        )
        assert blocked.status_code == 429
        assert blocked.json() == {"detail": {"message": "Invalid username or password."}}
        assert blocked.headers["retry-after"] == str(LOGIN_BLOCK_MINUTES * 60)

        still_blocked = client.post(
            "/auth/login", json={"username": user["username"], "password": _PASSWORD}
        )
        assert still_blocked.status_code == 429
        assert still_blocked.json() == blocked.json()


def test_session_cookie_is_secure_in_production(monkeypatch) -> None:
    monkeypatch.setattr(main_module, "settings", SimpleNamespace(app_env="production"))
    response = Response()
    main_module._set_session_cookie(response, "opaque-test-token")
    header = response.headers["set-cookie"].lower()
    assert "secure" in header
    assert "httponly" in header
    assert "samesite=lax" in header


def test_bearer_credential_remains_supported_for_non_browser_clients() -> None:
    username = _username("bearer")
    issued = auth_service.register(username, _PASSWORD)
    with TestClient(app) as client:
        me = client.get("/auth/me", headers={"Authorization": f"Bearer {issued['token']}"})
        assert me.status_code == 200
        assert me.json()["user"]["username"] == username.lower()


def test_profile_and_tutor_thread_ownership_with_cookie_and_guest() -> None:
    with TestClient(app) as owner, TestClient(app) as other, TestClient(app) as guest:
        owner_user = _register(owner, "owner", "Owner")
        other_user = _register(other, "other", "Other")

        # URL/body learner ids cannot override cookie identity. Anonymous callers
        # are confined to the shared demo profile.
        owner_view = owner.get(f"/learners/{other_user['userId']}").json()
        other_view = other.get(f"/learners/{owner_user['userId']}").json()
        guest_view = guest.get(f"/learners/{owner_user['userId']}").json()
        assert owner_view["learnerId"] == owner_user["userId"]
        assert other_view["learnerId"] == other_user["userId"]
        assert guest_view["learnerId"] == "demo"

        assert owner.get(f"/adaptive/plan?learnerId={other_user['userId']}").json()["learnerId"] == owner_user["userId"]
        assert other.get(f"/adaptive/plan?learnerId={owner_user['userId']}").json()["learnerId"] == other_user["userId"]

        created = owner.post(
            "/tutor/message",
            json={"learnerId": other_user["userId"], "mode": "freeform", "message": "Help me read systematically."},
        )
        assert created.status_code == 200, created.text
        thread_id = created.json()["threadId"]
        assert owner.get(f"/tutor/thread/{thread_id}").status_code == 200
        assert other.get(f"/tutor/thread/{thread_id}").status_code == 404
        assert guest.get(f"/tutor/thread/{thread_id}").status_code == 404

        owner_threads = owner.get("/tutor/threads?mode=freeform").json()["threads"]
        assert any(thread["threadId"] == thread_id for thread in owner_threads)
        assert all(thread["learnerId"] == owner_user["userId"] for thread in owner_threads)
        assert all(thread["threadId"] != thread_id for thread in other.get("/tutor/threads").json()["threads"])
        assert all(thread["threadId"] != thread_id for thread in guest.get("/tutor/threads").json()["threads"])


def test_guided_tutorial_selection_uses_the_authenticated_learner(monkeypatch) -> None:
    selected_for: list[str] = []

    def fake_next_case(repo, store, learner_id, concept_id=None, **kwargs):
        selected_for.append(learner_id)
        return {
            "case": {"caseId": f"case-for-{learner_id}", "displayId": "private selection"},
            "reason": "test selection",
            "targetObjectives": [concept_id] if concept_id else [],
        }

    monkeypatch.setattr(main_module, "next_case", fake_next_case)
    with TestClient(app) as first, TestClient(app) as second:
        first_user = _register(first, "tutorial_first")
        second_user = _register(second, "tutorial_second")
        first_response = first.get("/tutorials/rate")
        second_response = second.get("/tutorials/rate")
        assert first_response.status_code == second_response.status_code == 200
        assert first_response.json()["recommendedCase"]["caseId"] == f"case-for-{first_user['userId']}"
        assert second_response.json()["recommendedCase"]["caseId"] == f"case-for-{second_user['userId']}"
        assert selected_for == [first_user["userId"], second_user["userId"]]


def test_tutor_history_keeps_the_latest_window_in_chronological_order() -> None:
    learner = f"history_{uuid.uuid4().hex}"
    thread_id = store.ensure_thread(learner, mode="freeform")
    for index in range(50):
        store.append_tutor_message(
            thread_id,
            "tutor" if index % 2 else "user",
            f"message-{index:02d}",
            [{"type": "highlightLead", "lead": "II"}] if index == 49 else [],
        )
    history = store.thread_history(thread_id)
    assert len(history) == 40
    assert history[0]["content"] == "message-10"
    assert history[-1]["content"] == "message-49"
    assert history[-1]["viewerActions"] == [{"type": "highlightLead", "lead": "II"}]


def test_review_get_and_next_require_session_owner() -> None:
    with TestClient(app) as owner, TestClient(app) as other, TestClient(app) as guest:
        owner_user = _register(owner, "review_owner")
        _register(other, "review_other")
        # Ownership is independent of corpus availability; constructing the
        # persisted session directly makes this a focused authorization test.
        session_id = store.create_review_session(
            owner_user["userId"], ["anterior_mi"], "Anterior MI", target_mastery=0.8, max_cases=3
        )

        assert owner.get(f"/review/{session_id}").status_code == 200
        assert other.get(f"/review/{session_id}").status_code == 404
        assert guest.get(f"/review/{session_id}").status_code == 404
        assert other.post(f"/review/{session_id}/next").status_code == 404
        assert guest.post(f"/review/{session_id}/next").status_code == 404
