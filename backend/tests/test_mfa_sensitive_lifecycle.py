from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app import auth as auth_module
from app import main as main_module
from app.auth import (
    AuthError,
    AuthService,
    VERIFICATION_FAILURE_BUDGET_MAX,
    hash_password,
)
from app.auth_mailer import MemoryAuthMailer
from app.guest_progress import GuestProgressService
from app.main import app
from app.storage import LearningStore


PASSWORD = "correct horse battery staple"


def _services(tmp_path, monkeypatch, suffix: str):
    store = LearningStore(tmp_path / f"mfa-{suffix}-{uuid.uuid4().hex}.db")
    guests = GuestProgressService(store)
    mailer = MemoryAuthMailer()
    auth = AuthService(store, guests, "mfa-sensitive-test-secret", mailer=mailer)
    fast_hash = hash_password(PASSWORD, iterations=100_000)
    monkeypatch.setattr(auth_module, "hash_password", lambda _password: fast_hash)
    return store, guests, mailer, auth


def _register(auth: AuthService, mailer: MemoryAuthMailer, suffix: str):
    pending = auth.register_with_email(
        f"student_{suffix}", PASSWORD, f"student.{suffix}@example.edu"
    )
    proof = next(
        item
        for item in reversed(mailer.messages(purpose="email_verification"))
        if item.challenge_id == pending["challengeId"]
    )
    return auth.confirm_email_verification(
        proof.challenge_id, proof.secret, PASSWORD
    )


def _enable(
    auth: AuthService,
    mailer: MemoryAuthMailer,
    session: dict,
) -> str:
    user_id = session["user"]["userId"]
    auth.request_email_two_factor_enable(user_id, PASSWORD)
    proof = mailer.messages(purpose="two_factor_enable")[-1]
    enabled = auth.confirm_email_two_factor_enable(
        user_id, proof.challenge_id, proof.secret, session["token"]
    )
    assert enabled["emailTwoFactorEnabled"] is True
    return str(enabled["_sessionToken"])


def _mfa_login(auth: AuthService, mailer: MemoryAuthMailer, username: str) -> str:
    pending = auth.login(username, PASSWORD)
    assert pending["twoFactorRequired"] is True
    proof = mailer.messages(purpose="two_factor_login")[-1]
    return str(auth.verify_email_two_factor(proof.challenge_id, proof.secret)["token"])


def test_disable_requires_password_and_current_email_otp_then_rotates_every_session(
    tmp_path, monkeypatch
) -> None:
    store, _guests, mailer, auth = _services(tmp_path, monkeypatch, "disable")
    original = _register(auth, mailer, "disable")
    user_id = original["user"]["userId"]
    enabled_token = _enable(auth, mailer, original)
    proving_token = _mfa_login(auth, mailer, "student_disable")
    export = auth.authorize_export(user_id, proving_token, PASSWORD)

    with pytest.raises(AuthError) as bad_password:
        auth.request_email_two_factor_disable(user_id, "wrong password")
    assert bad_password.value.code == "invalid_current_password"

    requested = auth.request_email_two_factor_disable(user_id, PASSWORD)
    assert requested["challengeId"]
    assert "code" not in requested and "token" not in requested
    proof = mailer.messages(purpose="two_factor_disable")[-1]
    assert proof.recipient == "student.disable@example.edu"
    wrong = "000000" if proof.secret != "000000" else "000001"
    with pytest.raises(AuthError) as incorrect:
        auth.confirm_email_two_factor_disable(
            user_id, proof.challenge_id, wrong, proving_token
        )
    assert incorrect.value.code == "challenge_incorrect"

    disabled = auth.confirm_email_two_factor_disable(
        user_id, proof.challenge_id, proof.secret, proving_token
    )
    replacement = str(disabled["_sessionToken"])
    assert disabled["emailTwoFactorEnabled"] is False
    assert replacement not in {enabled_token, proving_token}
    assert auth.resolve(replacement) == user_id
    assert auth.resolve(enabled_token) is None
    assert auth.resolve(proving_token) is None
    assert store.get_user_auth(user_id)["email_two_factor_enabled"] == 0
    with store.connect() as conn:
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM export_authorizations WHERE user_id = ?",
            (user_id,),
        ).fetchone()["n"] == 0
    with pytest.raises(AuthError) as revoked_export:
        auth.export_progress(user_id, proving_token, export["token"])
    assert revoked_export.value.code == "export_authorization_required"
    assert len(mailer.messages(purpose="two_factor_disabled")) == 1
    with pytest.raises(AuthError) as replay:
        auth.confirm_email_two_factor_disable(
            user_id, proof.challenge_id, proof.secret, replacement
        )
    assert replay.value.code == "challenge_used"


def test_disable_resend_does_not_reset_the_durable_factor_failure_budget(
    tmp_path, monkeypatch
) -> None:
    store, _guests, mailer, auth = _services(tmp_path, monkeypatch, "budget")
    original = _register(auth, mailer, "budget")
    user_id = original["user"]["userId"]
    current = _enable(auth, mailer, original)
    auth.request_email_two_factor_disable(user_id, PASSWORD)
    proof = mailer.messages(purpose="two_factor_disable")[-1]

    for index in range(VERIFICATION_FAILURE_BUDGET_MAX - 1):
        wrong = f"{index:06d}"
        if wrong == proof.secret:
            wrong = "999999"
        with pytest.raises(AuthError) as failed:
            auth.confirm_email_two_factor_disable(
                user_id, proof.challenge_id, wrong, current
            )
        assert failed.value.code == "challenge_incorrect"

    store.allow_auth_challenge_resend_now(proof.challenge_id)
    auth.resend_email_challenge(
        proof.challenge_id, purpose="two_factor_disable", user_id=user_id
    )
    rotated = mailer.messages(purpose="two_factor_disable")[-1]
    wrong = "000000" if rotated.secret != "000000" else "000001"
    with pytest.raises(AuthError) as exhausted:
        auth.confirm_email_two_factor_disable(
            user_id, rotated.challenge_id, wrong, current
        )
    assert exhausted.value.code == "challenge_attempts_exhausted"
    assert store.get_user_auth(user_id)["email_two_factor_enabled"] == 1


def test_mfa_email_change_proves_current_then_new_destination_and_rotates_session(
    tmp_path, monkeypatch
) -> None:
    store, _guests, mailer, auth = _services(tmp_path, monkeypatch, "change")
    original = _register(auth, mailer, "change")
    user_id = original["user"]["userId"]
    first_token = _enable(auth, mailer, original)
    proving_token = _mfa_login(auth, mailer, "student_change")
    mailer.clear()

    requested = auth.request_email_change(
        user_id, "new-destination@example.edu", PASSWORD
    )
    assert requested["currentEmailFactorRequired"] is True
    assert mailer.messages(purpose="email_change") == ()
    current_factor = mailer.messages(purpose="email_change_current_factor")[-1]
    assert current_factor.recipient == "student.change@example.edu"
    with store.connect() as conn:
        stored = conn.execute(
            "SELECT secret_hash, context_json FROM auth_challenges WHERE challenge_id = ?",
            (current_factor.challenge_id,),
        ).fetchone()
        assert stored["secret_hash"] != current_factor.secret
        assert "new-destination@example.edu" in stored["context_json"]

    next_stage = auth.confirm_email_change_current_factor(
        user_id,
        current_factor.challenge_id,
        current_factor.secret,
        proving_token,
    )
    assert next_stage["emailChangeVerificationRequired"] is True
    destination = mailer.messages(purpose="email_change")[-1]
    assert destination.recipient == "new-destination@example.edu"
    with pytest.raises(AuthError) as factor_replay:
        auth.confirm_email_change_current_factor(
            user_id,
            current_factor.challenge_id,
            current_factor.secret,
            proving_token,
        )
    assert factor_replay.value.code == "challenge_used"

    changed = auth.confirm_email_change(
        user_id,
        destination.challenge_id,
        destination.secret,
        proving_token,
    )
    replacement = str(changed["_sessionToken"])
    assert changed["user"]["emailMasked"] == "n***@e***.edu"
    assert auth.resolve(replacement) == user_id
    assert auth.resolve(proving_token) is None
    assert auth.resolve(first_token) is None
    assert store.get_user_by_email("student.change@example.edu") is None
    assert store.get_user_by_email("new-destination@example.edu")["user_id"] == user_id
    changed_notice = mailer.messages(purpose="email_changed")
    assert len(changed_notice) == 1
    assert changed_notice[0].recipient == "student.change@example.edu"


def test_mfa_rejects_an_email_change_link_not_derived_from_current_factor(
    tmp_path, monkeypatch
) -> None:
    _store, _guests, mailer, auth = _services(tmp_path, monkeypatch, "bypass")
    original = _register(auth, mailer, "bypass")
    user_id = original["user"]["userId"]
    current = _enable(auth, mailer, original)
    user = auth.store.get_user_auth(user_id)
    bypass = auth._issue_email_challenge(
        user=user,
        purpose="email_change",
        ttl=timedelta(minutes=10),
        otp=False,
        max_attempts=8,
        context={"destinationEmail": "bypass@example.edu"},
        reuse_active=False,
        credential_bound=True,
        destination_email="bypass@example.edu",
    )
    link = mailer.messages(purpose="email_change")[-1]
    assert bypass["challengeId"] == link.challenge_id
    with pytest.raises(AuthError) as rejected:
        auth.confirm_email_change(
            user_id, link.challenge_id, link.secret, current
        )
    assert rejected.value.code == "current_email_factor_required"


def test_sensitive_confirm_endpoints_rotate_cookie_and_never_serialize_credentials(
    tmp_path, monkeypatch
) -> None:
    _store, guests, mailer, auth = _services(tmp_path, monkeypatch, "api")
    original = _register(auth, mailer, "api")
    user_id = original["user"]["userId"]
    monkeypatch.setattr(main_module, "store", auth.store)
    monkeypatch.setattr(main_module, "guest_progress_service", guests)
    monkeypatch.setattr(main_module, "auth_service", auth)

    with TestClient(app) as client:
        client.cookies.set(
            "ecg_session",
            original["token"],
            domain="testserver.local",
            path="/",
        )
        enable_request = client.post(
            "/auth/2fa/email/enable/request",
            json={"currentPassword": PASSWORD},
        )
        assert enable_request.status_code == 200
        enable = mailer.messages(purpose="two_factor_enable")[-1]
        enabled = client.post(
            "/auth/2fa/email/enable/confirm",
            json={"challengeId": enable.challenge_id, "code": enable.secret},
        )
        assert enabled.status_code == 200
        assert enabled.headers["cache-control"] == "no-store"
        assert set(enabled.json()) == {"ok", "emailTwoFactorEnabled"}

        disable_request = client.post(
            "/auth/2fa/email/disable/request",
            json={"currentPassword": PASSWORD},
        )
        assert disable_request.status_code == 200
        disable = mailer.messages(purpose="two_factor_disable")[-1]
        disabled = client.post(
            "/auth/2fa/email/disable/confirm",
            json={"challengeId": disable.challenge_id, "code": disable.secret},
        )
        assert disabled.status_code == 200
        assert disabled.headers["cache-control"] == "no-store"
        assert set(disabled.json()) == {"ok", "emailTwoFactorEnabled"}

        change_request = client.post(
            "/auth/email/change/request",
            json={
                "email": "api-new@example.edu",
                "currentPassword": PASSWORD,
            },
        )
        assert change_request.status_code == 200
        change = mailer.messages(purpose="email_change")[-1]
        changed = client.post(
            "/auth/email/change/confirm",
            json={"challengeId": change.challenge_id, "token": change.secret},
        )
        assert changed.status_code == 200
        assert changed.headers["cache-control"] == "no-store"
        assert set(changed.json()) == {"ok", "user"}
        assert changed.json()["user"]["userId"] == user_id


def test_concurrent_disable_confirmation_has_one_transactional_winner(
    tmp_path, monkeypatch
) -> None:
    _store, _guests, mailer, auth = _services(tmp_path, monkeypatch, "concurrent")
    original = _register(auth, mailer, "concurrent")
    user_id = original["user"]["userId"]
    current = _enable(auth, mailer, original)
    auth.request_email_two_factor_disable(user_id, PASSWORD)
    proof = mailer.messages(purpose="two_factor_disable")[-1]

    def confirm():
        try:
            result = auth.confirm_email_two_factor_disable(
                user_id, proof.challenge_id, proof.secret, current
            )
            return "ok", result
        except AuthError as exc:
            return exc.code, None

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _index: confirm(), range(2)))
    assert [status for status, _result in outcomes].count("ok") == 1
    assert sorted(status for status, _result in outcomes) == ["challenge_used", "ok"]
    winner = next(result for status, result in outcomes if status == "ok")
    assert auth.resolve(winner["_sessionToken"]) == user_id


def test_production_login_host_cookie_authenticates_me_and_learning_boundary(
    tmp_path, monkeypatch
) -> None:
    store, guests, mailer, auth = _services(tmp_path, monkeypatch, "prod-cookie")
    session = _register(auth, mailer, "prod_cookie")
    user_id = session["user"]["userId"]
    monkeypatch.setattr(main_module, "store", store)
    monkeypatch.setattr(main_module, "guest_progress_service", guests)
    monkeypatch.setattr(main_module, "auth_service", auth)
    monkeypatch.setattr(
        main_module,
        "settings",
        replace(main_module.settings, app_env="production"),
    )
    production_app = main_module.SessionCookieMigrationMiddleware(
        app,
        app_env="production",
        resolver=auth.resolve,
    )

    with TestClient(
        production_app, base_url="https://learn.example.edu"
    ) as client:
        login = client.post(
            "/auth/login",
            json={"username": "student_prod_cookie", "password": PASSWORD},
        )
        assert login.status_code == 200, login.text
        assert "token" not in login.json()
        host_headers = [
            value
            for value in login.headers.get_list("set-cookie")
            if value.startswith("__Host-ecg_session=")
        ]
        assert len(host_headers) == 1
        host_token = host_headers[0].split(";", 1)[0].split("=", 1)[1]
        assert auth.resolve(host_token) == user_id

        # Exercise the deployed shape, not TestClient's accumulated migration
        # cookies: the browser sends only the secure host-prefixed credential.
        client.cookies.clear()
        client.cookies.set(
            "__Host-ecg_session",
            host_token,
            domain="learn.example.edu",
            path="/",
        )
        me = client.get("/auth/me")
        assert me.status_code == 200
        assert me.json()["user"]["userId"] == user_id
        access = client.get("/auth/learning-access")
        assert access.status_code == 204
