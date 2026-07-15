"""Cookie sessions, credential compatibility, and learner-data ownership."""

from __future__ import annotations

import hashlib
import os
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import Cookie, FastAPI, Response
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("ECG_CORPUS_ROOT", "data/ecg_corpus_smoke")

from app import auth as auth_module  # noqa: E402
from app.auth import LOGIN_BLOCK_MINUTES, PASSWORD_ITERATIONS, hash_password, verify_password  # noqa: E402
from app import main as main_module  # noqa: E402
from app.main import app, auth_service, store  # noqa: E402
from app.storage import LearningStore  # noqa: E402

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


def _authorize_export(client: TestClient, password: str = _PASSWORD):
    return client.post(
        "/auth/export/authorize", json={"currentPassword": password}
    )


def test_password_hash_roundtrip_and_legacy_iteration_compatibility() -> None:
    current = hash_password("hunter2-long")
    assert current.startswith(f"pbkdf2_sha256${PASSWORD_ITERATIONS}$")
    assert verify_password("hunter2-long", current)
    assert not verify_password("wrong", current)

    legacy = hash_password("hunter2-long", iterations=200_000)
    assert verify_password("hunter2-long", legacy)
    assert not verify_password("hunter2-long", legacy.replace("pbkdf2_sha256$", "unknown$", 1))
    assert not verify_password(
        "hunter2-long",
        legacy.replace("pbkdf2_sha256$200000$", "pbkdf2_sha256$1$", 1),
    )
    with pytest.raises(ValueError, match="iterations"):
        hash_password("hunter2-long", iterations=1)


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
        for weak_password in ("password123", "aaaaaaaaaa", "          "):
            weak = client.post(
                "/auth/register",
                json={"username": _username("weak"), "password": weak_password},
            )
            assert weak.status_code == 400
            assert weak.json()["detail"]["field"] == "password"
            assert weak.json()["detail"]["code"] == "password_too_common"
        username_password = "samepassword"
        same_as_username = client.post(
            "/auth/register",
            json={"username": username_password, "password": username_password},
        )
        assert same_as_username.status_code == 400
        assert same_as_username.json()["detail"]["code"] == "password_too_common"
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


def test_profile_defaults_are_neutral_and_authenticated_get_syncs_canonical_name(tmp_path) -> None:
    isolated = LearningStore(tmp_path / "neutral-profile.sqlite3")
    assert isolated.ensure_profile(f"g_{'n' * 24}")["displayName"] == "Guest learner"
    assert isolated.ensure_profile("local-learner")["displayName"] == "Learner"

    with TestClient(app) as owner, TestClient(app) as other:
        owner_user = _register(owner, "profile_owner", "Canonical Owner")
        other_user = _register(other, "profile_other", "Canonical Other")

        # Simulate a stale prototype name from an earlier profile row. The URL
        # requests another learner, but the signed-in account remains both the
        # owner and the canonical display-name source.
        store.ensure_profile(owner_user["userId"], "Demo Learner")
        response = owner.get(f"/learners/{other_user['userId']}")
        assert response.status_code == 200
        assert response.json()["learnerId"] == owner_user["userId"]
        assert response.json()["displayName"] == "Canonical Owner"
        assert store.get_profile(other_user["userId"])["displayName"] == "Canonical Other"

        missing_name = owner.put(f"/learners/{other_user['userId']}", json={})
        assert missing_name.status_code == 422
        blank_name = owner.put(
            f"/learners/{other_user['userId']}", json={"displayName": "   "}
        )
        assert blank_name.status_code == 422

        updated = owner.put(
            f"/learners/{other_user['userId']}",
            json={"displayName": "Explicit study name"},
        )
        assert updated.status_code == 200
        assert updated.json()["learnerId"] == owner_user["userId"]
        assert updated.json()["displayName"] == "Explicit study name"
        assert store.get_profile(other_user["userId"])["displayName"] == "Canonical Other"

        resynced = owner.get("/learners/untrusted-request-id")
        assert resynced.json()["displayName"] == "Canonical Owner"


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


def test_registration_replaces_and_revokes_a_presented_account_session() -> None:
    with TestClient(app) as client:
        first = _register(client, "register_switch", "First Account")
        first_cookie = client.cookies.get("ecg_session")
        assert first_cookie and auth_service.resolve(first_cookie) == first["userId"]

        second_username = _username("register_replacement")
        replacement = client.post(
            "/auth/register",
            json={
                "username": second_username,
                "password": _PASSWORD,
                "displayName": "Replacement Account",
            },
        )
        assert replacement.status_code == 200, replacement.text
        second = replacement.json()["user"]
        assert second["userId"] != first["userId"]
        assert auth_service.resolve(first_cookie) is None
        assert client.get("/auth/me").json()["user"]["userId"] == second["userId"]
        with store.connect() as conn:
            assert conn.execute(
                "SELECT COUNT(*) FROM sessions WHERE user_id = ?", (first["userId"],)
            ).fetchone()[0] == 0


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
        with store.connect() as conn:
            sessions = conn.execute(
                "SELECT token FROM sessions WHERE user_id = ?", (user["userId"],)
            ).fetchall()
        assert len(sessions) == 1
        assert auth_service.resolve(first.cookies.get("ecg_session")) == user["userId"]

        first.post("/auth/logout")
        old_password = first.post(
            "/auth/login", json={"username": user["username"], "password": _PASSWORD}
        )
        assert old_password.status_code == 401
        new_password = first.post(
            "/auth/login", json={"username": user["username"], "password": replacement}
        )
        assert new_password.status_code == 200


def test_password_rotation_rolls_back_credentials_sessions_and_export_grants(
    tmp_path,
) -> None:
    isolated = LearningStore(tmp_path / "password-rotation.sqlite3")
    user_id = "u_atomic_password"
    old_hash = hash_password(_PASSWORD)
    new_hash = hash_password("N3w-Private-Password!")
    future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    isolated.create_user(user_id, "atomic-password", "Atomic Password", old_hash)
    isolated.create_session("old-current-token", user_id, future)
    isolated.create_session("old-other-token", user_id, future)
    with isolated.connect() as conn:
        conn.execute(
            "INSERT INTO export_authorizations "
            "(token_hash, user_id, session_hash, password_fingerprint, created_at, expires_at) "
            "VALUES ('existing-export', ?, 'existing-session', 'existing-password', ?, ?)",
            (user_id, datetime.now(UTC).isoformat(), future),
        )

    def fail_after_rotation(_conn) -> None:
        raise RuntimeError("injected password rotation failure")

    with pytest.raises(RuntimeError, match="injected password rotation failure"):
        isolated.rotate_password_and_sessions(
            user_id=user_id,
            expected_password_hash=old_hash,
            new_password_hash=new_hash,
            new_session_token="replacement-token",
            new_session_expires_at=future,
            _failure_hook=fail_after_rotation,
        )

    assert isolated.get_user_auth(user_id)["password_hash"] == old_hash
    assert isolated.get_session_user("old-current-token") == user_id
    assert isolated.get_session_user("old-other-token") == user_id
    assert isolated.get_session_user("replacement-token") is None
    with isolated.connect() as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM export_authorizations WHERE user_id = ?", (user_id,)
        ).fetchone()[0] == 1


def test_password_rotation_rejects_stale_verified_hash_without_mutation(tmp_path) -> None:
    isolated = LearningStore(tmp_path / "password-cas.sqlite3")
    user_id = "u_password_cas"
    current_hash = hash_password(_PASSWORD)
    future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    isolated.create_user(user_id, "password-cas", "Password CAS", current_hash)
    isolated.create_session("existing-token", user_id, future)

    assert isolated.rotate_password_and_sessions(
        user_id=user_id,
        expected_password_hash=hash_password("stale-password"),
        new_password_hash=hash_password("N3w-Private-Password!"),
        new_session_token="replacement-token",
        new_session_expires_at=future,
    ) is False

    assert isolated.get_user_auth(user_id)["password_hash"] == current_hash
    assert isolated.get_session_user("existing-token") == user_id
    assert isolated.get_session_user("replacement-token") is None


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


def test_logout_others_preserves_the_presented_session() -> None:
    with TestClient(app) as current, TestClient(app) as other:
        user = _register(current, "logout_others")
        assert other.post(
            "/auth/login", json={"username": user["username"], "password": _PASSWORD}
        ).status_code == 200
        other_cookie = other.cookies.get("ecg_session")

        revoked = current.post("/auth/logout-others")
        assert revoked.status_code == 200
        assert revoked.json() == {"ok": True, "revokedOtherSessions": 1}
        assert current.get("/auth/me").json()["authenticated"] is True
        assert auth_service.resolve(other_cookie) is None
        assert other.get(f"/learners/{user['userId']}").status_code == 401

        replay = current.post("/auth/logout-others")
        assert replay.json() == {"ok": True, "revokedOtherSessions": 0}


def test_session_inventory_is_owner_scoped_and_exposes_no_credentials() -> None:
    with TestClient(app) as current, TestClient(app) as other, TestClient(app) as stranger:
        user = _register(current, "session_inventory")
        current_cookie = current.cookies.get("ecg_session")
        assert current_cookie
        assert other.post(
            "/auth/login",
            json={"username": user["username"], "password": _PASSWORD},
        ).status_code == 200
        other_cookie = other.cookies.get("ecg_session")
        assert other_cookie
        stranger_user = _register(stranger, "inventory_other")

        response = current.get("/auth/sessions")
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "no-store"
        sessions = response.json()["sessions"]
        assert len(sessions) == 2
        assert sum(bool(session["current"]) for session in sessions) == 1
        assert sessions[0]["current"] is True
        assert all(
            set(session) == {"sessionId", "createdAt", "expiresAt", "current"}
            for session in sessions
        )
        assert all(
            len(session["sessionId"]) == 68
            and session["sessionId"].startswith("ses_")
            for session in sessions
        )

        with store.connect() as conn:
            stored_digests = {
                str(row["token"])
                for row in conn.execute(
                    "SELECT token FROM sessions WHERE user_id = ?", (user["userId"],)
                ).fetchall()
            }
        serialized = response.text
        assert current_cookie not in serialized
        assert other_cookie not in serialized
        assert all(digest not in serialized for digest in stored_digests)
        assert all(
            session["sessionId"] not in stored_digests
            and auth_service.resolve(session["sessionId"]) is None
            for session in sessions
        )
        assert hashlib.sha256(current_cookie.encode("utf-8")).hexdigest() in stored_digests

        stranger_sessions = stranger.get("/auth/sessions").json()["sessions"]
        assert len(stranger_sessions) == 1
        assert stranger_sessions[0]["current"] is True
        assert stranger_sessions[0]["sessionId"] not in {
            session["sessionId"] for session in sessions
        }
        assert stranger_user["userId"] not in serialized

    with TestClient(app) as guest:
        assert guest.get("/auth/sessions").status_code == 401
        assert guest.delete(f"/auth/sessions/ses_{'0' * 64}").status_code == 401


def test_single_session_revoke_enforces_owner_and_current_session_guards() -> None:
    with TestClient(app) as current, TestClient(app) as other, TestClient(app) as stranger:
        user = _register(current, "session_revoke")
        assert other.post(
            "/auth/login",
            json={"username": user["username"], "password": _PASSWORD},
        ).status_code == 200
        other_cookie = other.cookies.get("ecg_session")
        assert other_cookie
        _register(stranger, "revoke_other")

        owner_sessions = current.get("/auth/sessions").json()["sessions"]
        current_id = next(
            session["sessionId"] for session in owner_sessions if session["current"]
        )
        other_id = next(
            session["sessionId"] for session in owner_sessions if not session["current"]
        )
        stranger_id = stranger.get("/auth/sessions").json()["sessions"][0]["sessionId"]

        foreign = current.delete(f"/auth/sessions/{stranger_id}")
        assert foreign.status_code == 404
        assert foreign.json()["detail"]["code"] == "session_not_found"
        assert stranger.get("/auth/me").json()["authenticated"] is True

        current_attempt = current.delete(f"/auth/sessions/{current_id}")
        assert current_attempt.status_code == 409
        assert current_attempt.json()["detail"]["code"] == "current_session"
        assert current.get("/auth/me").json()["authenticated"] is True

        revoked = current.delete(f"/auth/sessions/{other_id}")
        assert revoked.status_code == 200, revoked.text
        assert revoked.json() == {"ok": True, "revokedSessionId": other_id}
        assert auth_service.resolve(other_cookie) is None
        assert other.get(f"/learners/{user['userId']}").status_code == 401

        remaining = current.get("/auth/sessions").json()["sessions"]
        assert len(remaining) == 1
        assert remaining[0]["sessionId"] == current_id
        assert remaining[0]["current"] is True
        assert current.delete(f"/auth/sessions/{other_id}").status_code == 404


def test_progress_export_is_owner_scoped_and_contains_no_auth_secrets() -> None:
    with TestClient(app) as owner, TestClient(app) as other, TestClient(app) as guest:
        owner_user = _register(owner, "export_owner", "Export Owner")
        other_user = _register(other, "export_other", "Export Other")
        owner_thread = store.ensure_thread(owner_user["userId"], mode="freeform")
        store.append_tutor_message(owner_thread, "user", "OWNER-ONLY-EXPORT-MARKER")
        other_thread = store.ensure_thread(other_user["userId"], mode="freeform")
        store.append_tutor_message(other_thread, "user", "OTHER-PRIVATE-MARKER")

        unauthorized = owner.post("/auth/export")
        assert unauthorized.status_code == 403
        assert unauthorized.json()["detail"]["code"] == "export_authorization_required"
        assert owner.get("/auth/export").status_code == 405

        authorized = _authorize_export(owner)
        assert authorized.status_code == 200, authorized.text
        assert set(authorized.json()) == {"ok", "expiresAt"}
        response = owner.post("/auth/export")
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["content-disposition"].endswith(
            f'ecg-progress-{owner_user["username"]}.json"'
        )
        exported = response.json()
        assert set(exported) == {
            "schemaVersion",
            "exportedAt",
            "assessmentPrivacy",
            "account",
            "recordCounts",
            "records",
        }
        assert exported["schemaVersion"] == "ecg-student-progress-v2"
        assert exported["assessmentPrivacy"]["pendingAndFutureAnswerContractsOmitted"] is True
        assert exported["account"] == {
            "userId": owner_user["userId"],
            "username": owner_user["username"],
            "displayName": "Export Owner",
            "createdAt": exported["account"]["createdAt"],
        }
        assert exported["recordCounts"]["tutorMessages"] == 1
        serialized = response.text
        assert "OWNER-ONLY-EXPORT-MARKER" in serialized
        assert "OTHER-PRIVATE-MARKER" not in serialized
        assert "password_hash" not in serialized
        assert "ecg_session" not in serialized
        assert "auth_login_throttle" not in serialized
        assert owner.post("/auth/export").status_code == 403
        assert guest.post("/auth/export/authorize", json={"currentPassword": _PASSWORD}).status_code == 401
        assert guest.post("/auth/export").status_code == 401


def test_export_authorization_expires_and_is_bound_to_owner_session_and_password() -> None:
    new_password = "N3w-Export-Password!"
    with (
        TestClient(app) as owner,
        TestClient(app) as second_session,
        TestClient(app) as stranger,
    ):
        owner_user = _register(owner, "export_grant_owner", "Grant Owner")
        assert second_session.post(
            "/auth/login",
            json={"username": owner_user["username"], "password": _PASSWORD},
        ).status_code == 200
        _register(stranger, "export_grant_stranger", "Grant Stranger")

        wrong = _authorize_export(owner, "not-the-password")
        assert wrong.status_code == 400
        assert wrong.json()["detail"]["code"] == "invalid_current_password"
        assert owner.cookies.get("ecg_export_auth") is None

        authorized = _authorize_export(owner)
        assert authorized.status_code == 200, authorized.text
        capability = owner.cookies.get("ecg_export_auth")
        assert capability
        set_cookie = authorized.headers["set-cookie"].lower()
        assert "httponly" in set_cookie
        assert "samesite=strict" in set_cookie
        assert "max-age=300" in set_cookie
        assert capability not in authorized.text
        with store.connect() as conn:
            stored = conn.execute(
                "SELECT token_hash, session_hash, password_fingerprint "
                "FROM export_authorizations WHERE user_id = ?",
                (owner_user["userId"],),
            ).fetchone()
        assert stored is not None
        assert capability not in {str(stored[column]) for column in stored.keys()}

        second_session.cookies.set(
            "ecg_export_auth",
            capability,
            domain="testserver.local",
            path="/",
        )
        cross_session = second_session.post("/auth/export")
        assert cross_session.status_code == 403
        assert cross_session.json()["detail"]["code"] == "export_authorization_invalid"
        # A copied capability is burned on misuse and cannot then be replayed
        # from the session that originally obtained it.
        replay_after_copy = owner.post("/auth/export")
        assert replay_after_copy.status_code == 403
        assert replay_after_copy.json()["detail"]["code"] == "export_authorization_required"

        assert _authorize_export(owner).status_code == 200
        cross_owner_capability = owner.cookies.get("ecg_export_auth")
        assert cross_owner_capability
        stranger.cookies.set(
            "ecg_export_auth",
            cross_owner_capability,
            domain="testserver.local",
            path="/",
        )
        cross_owner = stranger.post("/auth/export")
        assert cross_owner.status_code == 403
        assert cross_owner.json()["detail"]["code"] == "export_authorization_invalid"

        assert _authorize_export(owner).status_code == 200
        with store.connect() as conn:
            conn.execute(
                "UPDATE export_authorizations SET expires_at = '2000-01-01T00:00:00+00:00' "
                "WHERE user_id = ?",
                (owner_user["userId"],),
            )
        expired = owner.post("/auth/export")
        assert expired.status_code == 403
        assert expired.json()["detail"]["code"] == "export_authorization_expired"

        assert _authorize_export(owner).status_code == 200
        stale_capability = owner.cookies.get("ecg_export_auth")
        assert stale_capability
        changed = owner.post(
            "/auth/change-password",
            json={"currentPassword": _PASSWORD, "newPassword": new_password},
        )
        assert changed.status_code == 200, changed.text
        owner.cookies.set(
            "ecg_export_auth",
            stale_capability,
            domain="testserver.local",
            path="/",
        )
        stale = owner.post("/auth/export")
        assert stale.status_code == 403
        assert stale.json()["detail"]["code"] == "export_authorization_required"
        with store.connect() as conn:
            assert conn.execute(
                "SELECT COUNT(*) FROM export_authorizations WHERE user_id = ?",
                (owner_user["userId"],),
            ).fetchone()[0] == 0


def test_profile_history_uses_owner_scoped_ecg_references() -> None:
    with TestClient(app) as client:
        user = _register(client, "profile_ecg_refs", "Profile References")
        raw_case_id = f"ptbxl-private-{uuid.uuid4().hex[:10]}"
        with store.connect() as conn:
            conn.execute(
                "INSERT INTO attempts "
                "(learner_id, case_id, mode, structured_answer_json, free_text_answer, "
                "confidence, hints_used, score, correct_objectives_json, missed_objectives_json, "
                "misconception_tags_json, feedback, created_at) "
                "VALUES (?, ?, 'rapid', '{}', '', 3, 0, 1, '[]', '[]', '[]', '', ?)",
                (user["userId"], raw_case_id, "2026-07-14T12:00:00+00:00"),
            )

        response = client.get(f"/learners/{user['userId']}")
        assert response.status_code == 200, response.text
        attempt = response.json()["recentAttempts"][0]
        assert attempt["caseId"].startswith("ec_")
        assert raw_case_id not in response.text


def test_progress_export_omits_pending_and_future_assessment_answer_material() -> None:
    with TestClient(app) as owner:
        user = _register(owner, "export_assessment", "Assessment Export")
        learner_id = user["userId"]
        suffix = uuid.uuid4().hex[:10]
        now = "2026-07-13T12:00:00+00:00"
        pending_case = f"pending-{suffix}"
        future_case = f"future-{suffix}"
        answered_case = f"answered-{suffix}"
        round_id = f"rapid-{suffix}"
        campaign_id = f"training-{suffix}"

        pending_thread = store.ensure_thread(
            learner_id,
            mode="practice",
            case_id=pending_case,
        )
        store.append_tutor_message(
            pending_thread,
            "tutor",
            "PENDING-HISTORIC-TUTOR-ANSWER-SECRET",
        )

        with store.connect() as conn:
            conn.execute(
                "INSERT INTO rapid_rounds "
                "(round_id, learner_id, pace, length, assessment_scope, pending_case_id, "
                "pending_manifest_json, status, created_at, updated_at) "
                "VALUES (?, ?, 'ward', 3, 'mixed', ?, ?, 'active', ?, ?)",
                (
                    round_id,
                    learner_id,
                    pending_case,
                    '{"answerKey":"RAPID-PENDING-MANIFEST-SECRET"}',
                    now,
                    now,
                ),
            )
            conn.execute(
                "INSERT INTO rapid_round_answers "
                "(round_id, case_id, response_json, grade_json, result_json, "
                "tested_manifest_json, receipts_json, integrity_status, attempt_id, created_at) "
                "VALUES (?, ?, '{}', ?, '{}', '{}', '[]', 'legacy_incomplete', 991001, ?)",
                (round_id, pending_case, '{"answer":"RAPID-HISTORIC-GRADE-SECRET"}', now),
            )
            conn.execute(
                "INSERT INTO attempts "
                "(learner_id, case_id, mode, structured_answer_json, free_text_answer, "
                "confidence, hints_used, score, correct_objectives_json, missed_objectives_json, "
                "misconception_tags_json, feedback, created_at) "
                "VALUES (?, ?, 'rapid', '{}', ?, 4, 0, 1, '[]', '[]', '[]', '', ?)",
                (learner_id, pending_case, "PRIOR-ATTEMPT-ANSWER-SECRET", now),
            )
            conn.execute(
                "INSERT INTO training_campaigns "
                "(campaign_id, learner_id, concept_id, subskill, requested_length, length, "
                "pool_count, phases_json, phase_counts_json, position, pending_case_id, status, "
                "context_key, created_at, updated_at) "
                "VALUES (?, ?, 'sinus_rhythm', 'recognize', 3, 3, 3, '[\"build\"]', "
                "'{\"build\":3}', 0, ?, 'active', '', ?, ?)",
                (campaign_id, learner_id, pending_case, now, now),
            )
            conn.executemany(
                "INSERT INTO training_campaign_slots "
                "(campaign_id, ordinal, phase, case_id, case_focus, target_present, status, served_at, answered_at) "
                "VALUES (?, ?, 'build', ?, ?, ?, ?, ?, ?)",
                (
                    (campaign_id, 0, pending_case, "TRAINING-PENDING-FOCUS-SECRET", 1, "served", now, None),
                    (campaign_id, 1, future_case, "TRAINING-FUTURE-FOCUS-SECRET", 0, "queued", None, None),
                    (campaign_id, 2, answered_case, "normal_ecg", 1, "answered", now, now),
                ),
            )
            conn.execute(
                "INSERT INTO training_campaign_answers "
                "(campaign_id, ordinal, case_id, response_json, grade_json, tutor_json, "
                "receipt_json, summary_json, attempt_id, created_at) "
                "VALUES (?, 2, ?, '{}', '{}', '{}', '[]', '{}', 991002, ?)",
                (campaign_id, answered_case, now),
            )

        authorized = _authorize_export(owner)
        assert authorized.status_code == 200, authorized.text
        response = owner.post("/auth/export")
        assert response.status_code == 200, response.text
        exported = response.json()
        serialized = response.text
        assert exported["schemaVersion"] == "ecg-student-progress-v2"
        assert exported["records"]["trainingCampaigns"][0]["roster_policy"] == {}
        assert exported["records"]["trainingCampaignAnswers"][0]["integrity_status"] == "legacy_two_phase"
        assert all("pending_manifest" not in row for row in exported["records"]["rapidRounds"])
        exported_slot_ids = [
            row["case_id"]
            for row in exported["records"]["trainingCampaignSlots"]
        ]
        assert len(exported_slot_ids) == 1
        assert exported_slot_ids[0].startswith("ec_")
        assert "RAPID-PENDING-MANIFEST-SECRET" not in serialized
        assert "RAPID-HISTORIC-GRADE-SECRET" not in serialized
        assert "PRIOR-ATTEMPT-ANSWER-SECRET" not in serialized
        assert "PENDING-HISTORIC-TUTOR-ANSWER-SECRET" not in serialized
        assert "TRAINING-PENDING-FOCUS-SECRET" not in serialized
        assert "TRAINING-FUTURE-FOCUS-SECRET" not in serialized
        assert future_case not in serialized
        assert pending_case not in serialized
        assert answered_case not in serialized


def test_account_deletion_requires_recent_password_and_removes_owned_ledgers() -> None:
    now = "2026-07-13T12:00:00+00:00"
    with TestClient(app) as owner, TestClient(app) as second_device, TestClient(app) as other:
        owner_user = _register(owner, "delete_owner", "Delete Owner")
        other_user = _register(other, "delete_other", "Delete Other")
        assert second_device.post(
            "/auth/login",
            json={"username": owner_user["username"], "password": _PASSWORD},
        ).status_code == 200

        owner_thread = store.ensure_thread(owner_user["userId"], mode="freeform")
        store.append_tutor_message(owner_thread, "user", "delete this conversation")
        with store.connect() as conn:
            conn.execute(
                "INSERT INTO review_sessions (session_id, learner_id, created_at, updated_at) "
                "VALUES ('delete-review', ?, ?, ?)",
                (owner_user["userId"], now, now),
            )
            conn.execute(
                "INSERT INTO rapid_rounds "
                "(round_id, learner_id, pace, length, assessment_scope, created_at, updated_at) "
                "VALUES ('delete-rapid', ?, 'ward', 5, 'mixed', ?, ?)",
                (owner_user["userId"], now, now),
            )
            conn.execute(
                "INSERT INTO rapid_round_answers "
                "(round_id, case_id, response_json, grade_json, result_json, "
                "integrity_status, attempt_id, created_at) "
                "VALUES ('delete-rapid', 'case-r', '{}', '{}', '{}', "
                "'legacy_incomplete', 0, ?)",
                (now,),
            )
            conn.execute(
                "INSERT INTO clinical_shift_sessions "
                "(session_id, learner_id, lane, tier, created_at, updated_at) "
                "VALUES ('delete-clinical', ?, 'ward', 'learn', ?, ?)",
                (owner_user["userId"], now, now),
            )
            conn.execute(
                "INSERT INTO clinical_shift_answers "
                "(session_id, item_id, ecg_id, response_json, grade_json, score, correct, attempt_id, created_at) "
                "VALUES ('delete-clinical', 'item-c', 'case-c', '{}', '{}', 0, 0, 0, ?)",
                (now,),
            )
            conn.execute(
                "INSERT INTO training_campaigns "
                "(campaign_id, learner_id, concept_id, subskill, requested_length, length, "
                "pool_count, phases_json, phase_counts_json, created_at, updated_at) "
                "VALUES ('delete-training', ?, 'sinus_rhythm', 'recognize', 10, 1, 1, '[]', '{}', ?, ?)",
                (owner_user["userId"], now, now),
            )
            conn.execute(
                "INSERT INTO training_campaign_slots "
                "(campaign_id, ordinal, phase, case_id, case_focus, target_present) "
                "VALUES ('delete-training', 0, 'target', 'case-t', 'target', 1)"
            )
            conn.execute(
                "INSERT INTO training_campaign_answers "
                "(campaign_id, ordinal, case_id, response_json, grade_json, tutor_json, "
                "receipt_json, summary_json, attempt_id, created_at) "
                "VALUES ('delete-training', 0, 'case-t', '{}', '{}', '{}', '{}', '{}', 0, ?)",
                (now,),
            )
            conn.execute(
                "INSERT INTO guest_progress_claims "
                "(guest_learner_id, user_id, claimed_at, summary_json) VALUES (?, ?, ?, '{}')",
                (f"g_delete_{uuid.uuid4().hex}", owner_user["userId"], now),
            )

        wrong_password = owner.request(
            "DELETE",
            "/auth/account",
            json={"currentPassword": "not-the-password", "confirmation": owner_user["username"]},
        )
        assert wrong_password.status_code == 400
        assert wrong_password.json()["detail"]["code"] == "invalid_current_password"
        assert owner.get("/auth/me").json()["authenticated"] is True

        wrong_confirmation = owner.request(
            "DELETE",
            "/auth/account",
            json={"currentPassword": _PASSWORD, "confirmation": "wrong-username"},
        )
        assert wrong_confirmation.status_code == 400
        assert wrong_confirmation.json()["detail"]["code"] == "confirmation_mismatch"

        wrong_case = owner.request(
            "DELETE",
            "/auth/account",
            json={
                "currentPassword": _PASSWORD,
                "confirmation": owner_user["username"].upper(),
            },
        )
        assert wrong_case.status_code == 400
        assert wrong_case.json()["detail"]["code"] == "confirmation_mismatch"

        deleted = owner.request(
            "DELETE",
            "/auth/account",
            json={"currentPassword": _PASSWORD, "confirmation": owner_user["username"]},
        )
        assert deleted.status_code == 200, deleted.text
        assert deleted.json() == {"ok": True}
        assert owner.cookies.get("ecg_session") is None
        assert owner.get("/auth/me").json() == {"authenticated": False, "user": None}
        assert second_device.get(f"/learners/{owner_user['userId']}").status_code == 401

        with store.connect() as conn:
            for table, column in (
                ("users", "user_id"),
                ("sessions", "user_id"),
                ("learner_profiles", "learner_id"),
                ("objective_mastery", "learner_id"),
                ("tutor_threads", "learner_id"),
                ("review_sessions", "learner_id"),
                ("rapid_rounds", "learner_id"),
                ("clinical_shift_sessions", "learner_id"),
                ("training_campaigns", "learner_id"),
                ("guest_progress_claims", "user_id"),
                ("export_authorizations", "user_id"),
            ):
                assert conn.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE {column} = ?",
                    (owner_user["userId"],),
                ).fetchone()[0] == 0
            assert conn.execute(
                "SELECT COUNT(*) FROM tutor_messages WHERE thread_id = ?", (owner_thread,)
            ).fetchone()[0] == 0
            assert conn.execute(
                "SELECT COUNT(*) FROM rapid_round_answers WHERE round_id = 'delete-rapid'"
            ).fetchone()[0] == 0
            assert conn.execute(
                "SELECT COUNT(*) FROM clinical_shift_answers WHERE session_id = 'delete-clinical'"
            ).fetchone()[0] == 0
            assert conn.execute(
                "SELECT COUNT(*) FROM training_campaign_slots WHERE campaign_id = 'delete-training'"
            ).fetchone()[0] == 0
            assert conn.execute(
                "SELECT COUNT(*) FROM training_campaign_answers WHERE campaign_id = 'delete-training'"
            ).fetchone()[0] == 0
            assert conn.execute(
                "SELECT COUNT(*) FROM users WHERE user_id = ?", (other_user["userId"],)
            ).fetchone()[0] == 1


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


def test_current_password_reauthentication_is_pre_hash_throttled(monkeypatch) -> None:
    monkeypatch.setattr(auth_module, "ACCOUNT_REAUTH_PAIR_MAX_ATTEMPTS", 1)
    monkeypatch.setattr(auth_module, "ACCOUNT_REAUTH_IP_MAX_ATTEMPTS", 1_000_000)
    monkeypatch.setattr(auth_module, "ACCOUNT_REAUTH_GLOBAL_MAX_ATTEMPTS", 1_000_000)
    with TestClient(app) as client:
        _register(client, "reauth_throttle")
        first = client.post(
            "/auth/change-password",
            json={"currentPassword": "wrong-password", "newPassword": "N3w-Private-Password!"},
        )
        assert first.status_code == 400
        assert first.json()["detail"]["code"] == "invalid_current_password"

        blocked = client.post(
            "/auth/change-password",
            json={"currentPassword": "wrong-password", "newPassword": "N3w-Private-Password!"},
        )
        assert blocked.status_code == 429
        assert blocked.json()["detail"]["code"] == "reauth_throttled"
        assert blocked.headers["retry-after"] == str(
            auth_module.ACCOUNT_REAUTH_BLOCK_MINUTES * 60
        )


def test_export_password_confirmation_is_pre_hash_throttled(monkeypatch) -> None:
    monkeypatch.setattr(auth_module, "ACCOUNT_REAUTH_PAIR_MAX_ATTEMPTS", 1)
    monkeypatch.setattr(auth_module, "ACCOUNT_REAUTH_IP_MAX_ATTEMPTS", 1_000_000)
    monkeypatch.setattr(auth_module, "ACCOUNT_REAUTH_GLOBAL_MAX_ATTEMPTS", 1_000_000)
    with TestClient(app) as client:
        _register(client, "export_throttle")
        first = _authorize_export(client, "wrong-password")
        assert first.status_code == 400
        assert first.json()["detail"]["code"] == "invalid_current_password"

        blocked = _authorize_export(client, "wrong-password")
        assert blocked.status_code == 429
        assert blocked.json()["detail"]["code"] == "reauth_throttled"
        assert blocked.headers["retry-after"] == str(
            auth_module.ACCOUNT_REAUTH_BLOCK_MINUTES * 60
        )


def test_session_cookie_is_secure_in_production(monkeypatch) -> None:
    monkeypatch.setattr(main_module, "settings", SimpleNamespace(app_env="production"))
    response = Response()
    main_module._set_session_cookie(response, "opaque-test-token")
    headers = [
        value.decode("latin-1")
        for name, value in response.raw_headers
        if name.lower() == b"set-cookie"
    ]
    host_header = next(
        header for header in headers if header.startswith("__Host-ecg_session=")
    ).lower()
    legacy_clear = next(
        header
        for header in headers
        if header.startswith("ecg_session=") and "Max-Age=0" in header
    ).lower()
    assert "secure" in host_header
    assert "httponly" in host_header
    assert "samesite=lax" in host_header
    assert "path=/" in host_header
    assert "domain=" not in host_header
    assert "secure" in legacy_clear

    cleared = Response()
    main_module._clear_session_cookie(cleared)
    cleared_headers = [
        value.decode("latin-1")
        for name, value in cleared.raw_headers
        if name.lower() == b"set-cookie"
    ]
    assert {header.split("=", 1)[0] for header in cleared_headers} == {
        "__Host-ecg_session",
        "ecg_session",
    }
    assert all("Max-Age=0" in header for header in cleared_headers)

    export_response = Response()
    main_module._set_export_auth_cookie(export_response, "single-use-export-token")
    export_header = export_response.headers["set-cookie"].lower()
    assert "secure" in export_header
    assert "httponly" in export_header
    assert "samesite=strict" in export_header
    assert "max-age=300" in export_header


def test_production_legacy_session_cookie_migrates_once_and_host_cookie_wins() -> None:
    migration_app = FastAPI()

    @migration_app.get("/session")
    def current_session(
        token: str | None = Cookie(
            default=None, alias=auth_module.PRODUCTION_SESSION_COOKIE_NAME
        ),
    ) -> dict[str, str | None]:
        return {"token": token}

    @migration_app.post("/rotate")
    def rotate_session(response: Response) -> dict[str, bool]:
        response.set_cookie(
            key=auth_module.PRODUCTION_SESSION_COOKIE_NAME,
            value="newly-proved-session",
            secure=True,
            httponly=True,
            samesite="lax",
            path="/",
        )
        return {"ok": True}

    migration_app.add_middleware(
        main_module.SessionCookieMigrationMiddleware,
        app_env="production",
        resolver=lambda token: "u_owner" if token == "legacy-valid" else None,
    )
    with TestClient(migration_app, base_url="https://learn.example.edu") as client:
        migrated = client.get(
            "/session", headers={"Cookie": "ecg_session=legacy-valid"}
        )
        assert migrated.status_code == 200
        assert migrated.json() == {"token": "legacy-valid"}
        migrated_headers = migrated.headers.get_list("set-cookie")
        assert any(
            header.startswith("__Host-ecg_session=legacy-valid")
            and "Secure" in header
            and "Path=/" in header
            and "Domain=" not in header
            for header in migrated_headers
        )
        assert any(
            header.startswith("ecg_session=") and "Max-Age=0" in header
            for header in migrated_headers
        )

        client.cookies.clear()
        precedence = client.get(
            "/session",
            headers={
                "Cookie": "__Host-ecg_session=host-wins; ecg_session=legacy-valid"
            },
        )
        assert precedence.json() == {"token": "host-wins"}
        assert not any(
            header.startswith("__Host-ecg_session=legacy-valid")
            for header in precedence.headers.get_list("set-cookie")
        )

        client.cookies.clear()
        invalid = client.get(
            "/session", headers={"Cookie": "ecg_session=legacy-invalid"}
        )
        assert invalid.json() == {"token": None}
        invalid_headers = invalid.headers.get_list("set-cookie")
        assert any(
            header.startswith("ecg_session=") and "Max-Age=0" in header
            for header in invalid_headers
        )
        assert not any(
            header.startswith("__Host-ecg_session=") for header in invalid_headers
        )

        client.cookies.clear()
        rotated = client.post(
            "/rotate", headers={"Cookie": "ecg_session=legacy-valid"}
        )
        active_headers = [
            header
            for header in rotated.headers.get_list("set-cookie")
            if header.startswith("__Host-ecg_session=")
        ]
        assert len(active_headers) == 1
        assert active_headers[0].startswith(
            "__Host-ecg_session=newly-proved-session"
        )


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


def test_tutor_thread_history_is_partitioned_by_exact_learning_waypoint() -> None:
    with TestClient(app) as client:
        _register(client, "scope", "Scoped Learner")
        suffix = uuid.uuid4().hex
        first_scope = f"guided-rate:scene-a:{suffix}"
        second_scope = f"guided-rate:scene-b:{suffix}"

        first = client.post(
            "/tutor/message",
            json={
                "mode": "freeform",
                "scopeKey": first_scope,
                "message": "Help me reason through this first scene.",
            },
        )
        assert first.status_code == 200, first.text
        first_thread = first.json()["threadId"]

        second = client.post(
            "/tutor/message",
            json={
                "mode": "freeform",
                "scopeKey": second_scope,
                "message": "Help me reason through this second scene.",
            },
        )
        assert second.status_code == 200, second.text
        assert second.json()["threadId"] != first_thread

        first_scene_threads = client.get(
            "/tutor/threads",
            params={"mode": "freeform", "scopeKey": first_scope},
        )
        assert first_scene_threads.status_code == 200
        assert [row["threadId"] for row in first_scene_threads.json()["threads"]] == [first_thread]

        cross_scene = client.post(
            "/tutor/message",
            json={
                "mode": "freeform",
                "scopeKey": second_scope,
                "threadId": first_thread,
                "message": "Continue the earlier scene here.",
            },
        )
        assert cross_scene.status_code == 404


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
    monkeypatch.setattr(
        main_module.repo,
        "get_case",
        lambda case_id: {
            "case_id": case_id,
            "display_id": case_id,
            "clinical_stem": "",
            "source": "ptbxl",
            "waveform": {"sampling_frequency": 100, "duration_sec": 10, "leads": ["II"]},
            "ptbxl": {},
            "ptbxl_plus": {"median_beats": {}},
            "signal_quality": {},
            "concept_confidence": {},
            "supported_objectives": [],
            "unsupported_objectives": [],
            "teaching_tier": "A",
            "inclusion_reasons": [],
            "exclusion_reasons": [],
            "llm_allowed_claims": [],
            "llm_forbidden_claims": [],
        },
    )
    with TestClient(app) as first, TestClient(app) as second:
        first_user = _register(first, "tutorial_first")
        second_user = _register(second, "tutorial_second")
        first_response = first.get("/tutorials/rate")
        first_retry = first.get("/tutorials/rate")
        second_response = second.get("/tutorials/rate")
        assert first_response.status_code == first_retry.status_code == second_response.status_code == 200
        assert first_response.headers["cache-control"] == "no-store, private"
        first_ref = first_response.json()["recommendedCase"]["caseId"]
        second_ref = second_response.json()["recommendedCase"]["caseId"]
        assert first_ref.startswith("ec_")
        assert first_retry.json()["recommendedCase"]["caseId"] == first_ref
        assert second_ref.startswith("ec_")
        assert second_ref != first_ref
        for response, canonical in (
            (first_response, f"case-for-{first_user['userId']}"),
            (first_retry, f"case-for-{first_user['userId']}"),
            (second_response, f"case-for-{second_user['userId']}"),
        ):
            assert canonical not in response.text
            assert response.json()["assessmentPrivacy"]["opaqueEcgReference"] is True
        assert selected_for == [first_user["userId"], first_user["userId"], second_user["userId"]]
        with store.connect() as conn:
            first_events = conn.execute(
                "SELECT mode, session_id, ecg_id, event_type, score "
                "FROM learner_events WHERE owner_id = ? AND event_type = 'item_presented'",
                (first_user["userId"],),
            ).fetchall()
            second_events = conn.execute(
                "SELECT mode, session_id, ecg_id, event_type, score "
                "FROM learner_events WHERE owner_id = ? AND event_type = 'item_presented'",
                (second_user["userId"],),
            ).fetchall()
        assert [tuple(row) for row in first_events] == [
            ("guided", "tutorial:rate", f"case-for-{first_user['userId']}", "item_presented", None)
        ]
        assert [tuple(row) for row in second_events] == [
            ("guided", "tutorial:rate", f"case-for-{second_user['userId']}", "item_presented", None)
        ]


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


def test_legacy_review_is_owner_read_only_and_never_advances_without_assessment() -> None:
    with TestClient(app) as owner, TestClient(app) as other, TestClient(app) as guest:
        owner_user = _register(owner, "review_owner")
        _register(other, "review_other")
        with store.connect() as conn:
            sessions_before = int(
                conn.execute(
                    "SELECT COUNT(*) FROM review_sessions WHERE learner_id = ?",
                    (owner_user["userId"],),
                ).fetchone()[0]
            )
        rejected_start = owner.post(
            "/review/start",
            json={"conceptId": "anterior_mi", "targetMastery": 0.8, "maxCases": 3},
        )
        assert rejected_start.status_code == 410
        assert rejected_start.json()["detail"] == {
            "code": "legacy_review_deprecated",
            "message": (
                "Legacy Review cannot safely associate its separately submitted answers "
                "with the case it served. Open the adaptive plan for evidence-tracked "
                "Training, Rapid, and Clinical recommendations."
            ),
            "replacement": {"method": "GET", "path": "/adaptive/plan"},
        }
        replacement = owner.get("/adaptive/plan")
        assert replacement.status_code == 200
        assert replacement.json()["learnerId"] == owner_user["userId"]
        with store.connect() as conn:
            assert int(
                conn.execute(
                    "SELECT COUNT(*) FROM review_sessions WHERE learner_id = ?",
                    (owner_user["userId"],),
                ).fetchone()[0]
            ) == sessions_before

        # Ownership is independent of corpus availability; constructing the
        # persisted session directly makes this a focused authorization test.
        session_id = store.create_review_session(
            owner_user["userId"], ["anterior_mi"], "Anterior MI", target_mastery=0.8, max_cases=3
        )
        stored_before = store.get_review_session(session_id)

        historical = owner.get(f"/review/{session_id}")
        assert historical.status_code == 200
        assert historical.json()["deprecated"] is True
        assert historical.json()["readOnly"] is True
        assert historical.json()["case"] is None
        assert "progress" not in historical.json()
        assert historical.json()["session"]["status"] == "deprecated"
        assert historical.json()["session"]["legacyStatus"] == "active"
        assert other.get(f"/review/{session_id}").status_code == 404
        assert guest.get(f"/review/{session_id}").status_code == 404

        rejected_next = owner.post(f"/review/{session_id}/next")
        assert rejected_next.status_code == 410
        assert rejected_next.json()["detail"]["code"] == "legacy_review_deprecated"
        assert rejected_next.json()["detail"]["replacement"] == {
            "method": "GET",
            "path": "/adaptive/plan",
        }
        assert other.post(f"/review/{session_id}/next").status_code == 404
        assert guest.post(f"/review/{session_id}/next").status_code == 404
        assert store.get_review_session(session_id) == stored_before
