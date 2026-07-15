from __future__ import annotations

import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app import auth as auth_module
from app import main as main_module
from app.auth import (
    AuthError,
    AuthService,
    VERIFICATION_FAILURE_BUDGET_MAX,
    hash_password,
    verify_password_with_current_work,
)
from app.auth_mailer import MemoryAuthMailer
from app.guest_progress import GuestProgressService
from app.ops import _password_hash_check
from app.storage import LearningStore
from app.main import app


PASSWORD = "correct horse battery staple"
NEW_PASSWORD = "a replacement passphrase for security testing"


def _services(tmp_path, monkeypatch, name: str = "security"):
    store = LearningStore(tmp_path / f"{name}.db")
    guests = GuestProgressService(store)
    mailer = MemoryAuthMailer()
    auth = AuthService(store, guests, "auth-security-test-secret", mailer=mailer)
    fast_hash = hash_password(PASSWORD, iterations=100_000)
    monkeypatch.setattr(auth_module, "hash_password", lambda _password: fast_hash)
    return store, mailer, auth


def _register_and_verify(auth: AuthService, mailer: MemoryAuthMailer, suffix: str):
    pending = auth.register_with_email(
        f"student_{suffix}", PASSWORD, f"student.{suffix}@example.edu"
    )
    proof = next(
        message
        for message in reversed(mailer.messages(purpose="email_verification"))
        if message.challenge_id == pending["challengeId"]
    )
    session = auth.confirm_email_verification(
        proof.challenge_id, proof.secret, PASSWORD
    )
    return pending, session


def _enable_two_factor(
    auth: AuthService, mailer: MemoryAuthMailer, suffix: str
) -> dict:
    _pending, session = _register_and_verify(auth, mailer, suffix)
    user_id = session["user"]["userId"]
    auth.request_email_two_factor_enable(user_id, PASSWORD)
    proof = mailer.messages(purpose="two_factor_enable")[-1]
    auth.confirm_email_two_factor_enable(
        user_id, proof.challenge_id, proof.secret, session["token"]
    )
    auth.logout(session["token"])
    return session


def _wrong_hash() -> str:
    return "f" * 64


def test_repeat_registration_has_same_public_username_transition_for_new_and_existing_email(
    tmp_path, monkeypatch
) -> None:
    store, mailer, auth = _services(tmp_path, monkeypatch, "registration-oracle")
    _pending, _verified = _register_and_verify(auth, mailer, "oracle_owner")
    mailer.clear()

    auth.register_with_email("new_probe", PASSWORD, "new-probe@example.edu")
    with pytest.raises(AuthError) as repeated_new:
        auth.register_with_email("new_probe", PASSWORD, "new-probe@example.edu")

    existing = auth.register_with_email(
        "existing_probe", PASSWORD, "student.oracle_owner@example.edu"
    )
    with pytest.raises(AuthError) as repeated_existing:
        auth.register_with_email(
            "existing_probe", PASSWORD, "student.oracle_owner@example.edu"
        )

    assert repeated_new.value.code == repeated_existing.value.code == "username_taken"
    assert len(mailer.messages(purpose="registration_resolution")) == 1
    with store.connect() as conn:
        reservation = conn.execute(
            "SELECT registration_reservation, email_normalized FROM users "
            "WHERE username = 'existing_probe'"
        ).fetchone()
        assert reservation["registration_reservation"] == 1
        assert reservation["email_normalized"] is None
        assert conn.execute(
            "SELECT 1 FROM learner_profiles WHERE learner_id = ("
            "SELECT user_id FROM users WHERE username = 'existing_probe')"
        ).fetchone() is None
    with pytest.raises(AuthError) as placeholder_login:
        auth.login("existing_probe", PASSWORD, client_ip="203.0.113.10")
    assert placeholder_login.value.code == "invalid"
    assert existing["verificationRequired"] is True


def test_registration_verification_and_resolution_share_rolling_email_budget(
    tmp_path, monkeypatch
) -> None:
    store, mailer, auth = _services(tmp_path, monkeypatch, "registration-budget")
    pending = auth.register_with_email(
        "budget_pending", PASSWORD, "budget-owner@example.edu"
    )
    for _ in range(3):
        status, _ = store.verify_auth_challenge(
            challenge_id=pending["challengeId"],
            purpose="email_verification",
            presented_secret_hash=_wrong_hash(),
        )
        assert status == "incorrect"

    resolution = auth.register_with_email(
        "budget_resolution", PASSWORD, "budget-owner@example.edu"
    )
    first, _ = store.verify_auth_challenge(
        challenge_id=resolution["challengeId"],
        purpose="registration_resolution",
        presented_secret_hash=_wrong_hash(),
    )
    second, _ = store.verify_auth_challenge(
        challenge_id=resolution["challengeId"],
        purpose="registration_resolution",
        presented_secret_hash=_wrong_hash(),
    )
    assert first == "incorrect"
    assert second == "attempts_exhausted"

    proof = mailer.messages(purpose="registration_resolution")[-1]
    correct_after_ceiling, _ = store.verify_auth_challenge(
        challenge_id=proof.challenge_id,
        purpose="registration_resolution",
        presented_secret_hash=auth._challenge_hash(
            "registration_resolution", proof.challenge_id, proof.secret
        ),
    )
    assert correct_after_ceiling == "attempts_exhausted"


def test_two_factor_budget_survives_resend_expiry_and_correct_password_reissue(
    tmp_path, monkeypatch
) -> None:
    store, mailer, auth = _services(tmp_path, monkeypatch, "two-factor-budget")
    _enable_two_factor(auth, mailer, "budget_2fa")
    mailer.clear()
    login = auth.login("student_budget_2fa", PASSWORD, client_ip="203.0.113.20")
    challenge_id = login["challengeId"]

    for _ in range(VERIFICATION_FAILURE_BUDGET_MAX - 2):
        status, _ = store.verify_auth_challenge(
            challenge_id=challenge_id,
            purpose="two_factor_login",
            presented_secret_hash=_wrong_hash(),
        )
        assert status == "incorrect"
    store.allow_auth_challenge_resend_now(challenge_id)
    auth.resend_email_challenge(challenge_id, purpose="two_factor_login")
    resent = mailer.messages(purpose="two_factor_login")[-1]
    assert store.verify_auth_challenge(
        challenge_id=challenge_id,
        purpose="two_factor_login",
        presented_secret_hash=_wrong_hash(),
    )[0] == "incorrect"
    assert store.verify_auth_challenge(
        challenge_id=challenge_id,
        purpose="two_factor_login",
        presented_secret_hash=_wrong_hash(),
    )[0] == "attempts_exhausted"
    with pytest.raises(AuthError) as blocked_correct:
        auth.verify_email_two_factor(challenge_id, resent.secret)
    assert blocked_correct.value.code == "challenge_attempts_exhausted"

    with store.connect() as conn:
        conn.execute(
            "UPDATE auth_challenges SET expires_at = ? WHERE challenge_id = ?",
            ((datetime.now(UTC) - timedelta(seconds=1)).isoformat(), challenge_id),
        )
    reissued = auth.login(
        "student_budget_2fa", PASSWORD, client_ip="203.0.113.21"
    )
    assert reissued["challengeId"] != challenge_id
    new_proof = mailer.messages(purpose="two_factor_login")[-1]
    with pytest.raises(AuthError) as blocked_reissue:
        auth.verify_email_two_factor(new_proof.challenge_id, new_proof.secret)
    assert blocked_reissue.value.code == "challenge_attempts_exhausted"


def test_password_reset_confirm_throttles_random_ids_before_hashing(
    tmp_path, monkeypatch
) -> None:
    _store, _mailer, auth = _services(tmp_path, monkeypatch, "reset-cpu")
    hashes: list[str] = []
    precomputed = hash_password(NEW_PASSWORD, iterations=100_000)

    def tracked_hash(password: str) -> str:
        hashes.append(password)
        return precomputed

    monkeypatch.setattr(auth_module, "hash_password", tracked_hash)
    monkeypatch.setattr(auth_module, "RECOVERY_CONFIRM_PAIR_MAX_ATTEMPTS", 20)
    monkeypatch.setattr(auth_module, "RECOVERY_CONFIRM_IP_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(auth_module, "RECOVERY_CONFIRM_GLOBAL_MAX_ATTEMPTS", 20)

    for index in range(2):
        with pytest.raises(AuthError) as invalid:
            auth.confirm_password_reset(
                f"ach_random_reset_identifier_{index:02d}",
                "not-a-real-proof",
                NEW_PASSWORD,
                client_ip="198.51.100.45",
            )
        assert invalid.value.code == "challenge_invalid"
    with pytest.raises(AuthError) as throttled:
        auth.confirm_password_reset(
            "ach_random_reset_identifier_99",
            "not-a-real-proof",
            NEW_PASSWORD,
            client_ip="198.51.100.45",
        )
    assert throttled.value.code == "recovery_confirm_throttled"
    assert hashes == [NEW_PASSWORD, NEW_PASSWORD]


def test_established_legacy_unverified_email_cannot_reset_or_take_over_identity(
    tmp_path, monkeypatch
) -> None:
    store, mailer, auth = _services(tmp_path, monkeypatch, "legacy-takeover")
    legacy = auth.register("legacy_owner", PASSWORD, "Original Learner")
    user_id = legacy["user"]["userId"]
    with store.connect() as conn:
        conn.execute(
            "INSERT INTO attempts (learner_id, case_id, mode, structured_answer_json, "
            "free_text_answer, confidence, hints_used, score, correct_objectives_json, "
            "missed_objectives_json, misconception_tags_json, feedback, created_at) "
            "VALUES (?, 'legacy-progress', 'rapid', '{}', '', 3, 0, 1, '[]', '[]', '[]', '', ?)",
            (user_id, datetime.now(UTC).isoformat()),
        )
    auth.request_legacy_email_upgrade(
        user_id, "mistyped-legacy@example.edu", PASSWORD
    )
    mailer.clear()
    auth.request_password_reset(
        "mistyped-legacy@example.edu", client_ip="203.0.113.31"
    )
    assert not mailer.messages(purpose="password_reset")

    user = store.get_user_auth(user_id)
    reset = auth._new_challenge(
        "password_reset", ttl=timedelta(minutes=30), otp=False
    )
    store.create_auth_challenge(
        challenge_id=reset["challengeId"],
        user_id=user_id,
        purpose="password_reset",
        secret_hash=reset["secretHash"],
        expires_at=reset["expiresAt"],
        max_attempts=8,
        credential_fingerprint=store._password_fingerprint(user["password_hash"]),
    )
    with pytest.raises(AuthError) as stale:
        auth.confirm_password_reset(
            reset["challengeId"],
            reset["secret"],
            NEW_PASSWORD,
            recovery_username="attacker_identity",
            recovery_display_name="Attacker",
            client_ip="203.0.113.32",
        )
    assert stale.value.code == "challenge_stale"
    unchanged = store.get_user_auth(user_id)
    assert unchanged["username"] == "legacy_owner"
    assert unchanged["display_name"] == "Original Learner"
    assert unchanged["email_verified_at"] is None
    with store.connect() as conn:
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM attempts WHERE learner_id = ?", (user_id,)
        ).fetchone()["n"] == 1


def test_legacy_hash_wrong_password_work_matches_unknown_dummy_path(
    monkeypatch,
) -> None:
    legacy = hash_password(PASSWORD, iterations=200_000)
    original = auth_module.hashlib.pbkdf2_hmac
    calls: list[int] = []

    def tracked(name, password, salt, iterations):
        calls.append(iterations)
        return original(name, password, salt, iterations)

    monkeypatch.setattr(auth_module.hashlib, "pbkdf2_hmac", tracked)
    assert verify_password_with_current_work("wrong password", legacy) is False
    legacy_calls = list(calls)
    calls.clear()
    assert (
        verify_password_with_current_work(
            "wrong password", auth_module._DUMMY_PASSWORD_HASH
        )
        is False
    )
    unknown_calls = list(calls)
    assert legacy_calls == [200_000, 400_000]
    assert unknown_calls == [600_000]
    assert sum(legacy_calls) == sum(unknown_calls)


def test_password_hash_audit_is_aggregate_and_fails_readiness_only_for_invalid_rows(
    tmp_path,
) -> None:
    store = LearningStore(tmp_path / "password-audit.db")
    store.create_user("u_current", "current_hash", "Current", hash_password(PASSWORD))
    store.create_user(
        "u_legacy", "legacy_hash", "Legacy", hash_password(PASSWORD, iterations=200_000)
    )
    store.create_user("u_invalid", "invalid_hash", "Invalid", "not-a-password-hash")

    audit = store.password_hash_iteration_audit()
    assert audit == {
        "total": 3,
        "current": 1,
        "legacy": 1,
        "future": 0,
        "invalid": 1,
    }
    assert not any("u_" in str(value) for value in audit.values())
    ok, state, counts = _password_hash_check(store)
    assert ok is False
    assert state == "invalid_password_hashes_present"
    assert counts == audit

    store.update_user_password("u_invalid", hash_password(PASSWORD))
    ok, state, counts = _password_hash_check(store)
    assert ok is True
    assert state == "legacy_password_hash_migration_pending"
    assert counts["legacy"] == 1


def test_concurrent_password_reset_issue_sends_only_atomic_winner(
    tmp_path, monkeypatch
) -> None:
    store, mailer, auth = _services(tmp_path, monkeypatch, "reset-concurrency")
    _pending, _verified = _register_and_verify(auth, mailer, "reset_race")
    mailer.clear()
    original = store.get_active_auth_challenge
    barrier = threading.Barrier(2)

    def synchronized_lookup(user_id: str, purpose: str):
        result = original(user_id, purpose)
        if purpose == "password_reset" and result is None:
            barrier.wait(timeout=5)
        return result

    monkeypatch.setattr(store, "get_active_auth_challenge", synchronized_lookup)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(auth._dispatch_password_reset, "student.reset_race@example.edu")
            for _ in range(2)
        ]
        for future in futures:
            future.result(timeout=10)

    messages = mailer.messages(purpose="password_reset")
    assert len(messages) == 1
    active = original(_verified["user"]["userId"], "password_reset")
    assert active["challenge_id"] == messages[0].challenge_id


def test_concurrent_two_factor_logins_reuse_one_challenge_and_one_email(
    tmp_path, monkeypatch
) -> None:
    store, mailer, auth = _services(tmp_path, monkeypatch, "two-factor-concurrency")
    _enable_two_factor(auth, mailer, "login_race")
    mailer.clear()
    monkeypatch.setattr(
        auth_module, "verify_password_with_current_work", lambda _password, _stored: True
    )
    original = store.reserve_auth_challenge_issue
    barrier = threading.Barrier(2)

    def synchronized_reservation(**kwargs):
        barrier.wait(timeout=5)
        return original(**kwargs)

    monkeypatch.setattr(store, "reserve_auth_challenge_issue", synchronized_reservation)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda ip: auth.login(
                    "student_login_race", PASSWORD, client_ip=ip
                ),
                ("198.51.100.50", "198.51.100.51"),
            )
        )
    assert {result["challengeId"] for result in results} == {
        mailer.messages(purpose="two_factor_login")[0].challenge_id
    }
    assert len(mailer.messages(purpose="two_factor_login")) == 1


def test_pending_registration_can_atomically_replace_and_cancel_unverified_email(
    tmp_path, monkeypatch
) -> None:
    store, mailer, auth = _services(tmp_path, monkeypatch, "pending-email-correction")
    pending = auth.register_with_email(
        "mistyped_pending", PASSWORD, "mistyped-pending@example.edu"
    )
    old_proof = mailer.messages(purpose="email_verification")[-1]
    replacement = auth.replace_unverified_email(
        user_id=None,
        challenge_id=pending["challengeId"],
        current_password=PASSWORD,
        new_email="correct-pending@example.edu",
        client_ip="203.0.113.60",
    )
    assert replacement["verificationRequired"] is True
    assert store.get_user_by_email("mistyped-pending@example.edu") is None
    corrected = store.get_user_by_email("correct-pending@example.edu")
    assert corrected["account_origin"] == "pending_registration"
    with pytest.raises(AuthError) as old_link:
        auth.confirm_email_verification(
            old_proof.challenge_id, old_proof.secret, PASSWORD
        )
    assert old_link.value.code == "challenge_used"

    new_proof = mailer.messages(purpose="email_verification")[-1]
    verified = auth.confirm_email_verification(
        new_proof.challenge_id, new_proof.secret, PASSWORD
    )
    assert verified["accountStatus"] == "verified"
    assert store.get_user_auth(corrected["user_id"])["account_origin"] == "registered"

    cancellable = auth.register_with_email(
        "cancel_pending", PASSWORD, "cancel-pending@example.edu"
    )
    cancelled = auth.cancel_unverified_email(
        user_id=None,
        challenge_id=cancellable["challengeId"],
        current_password=PASSWORD,
        client_ip="203.0.113.61",
    )
    assert cancelled == {"ok": True, "accountCancelled": True}
    assert store.get_user_by_email("cancel-pending@example.edu") is None
    restarted = auth.register_with_email(
        "cancel_pending", PASSWORD, "cancel-pending@example.edu"
    )
    assert restarted["verificationRequired"] is True


def test_established_legacy_account_can_replace_or_detach_typo_without_identity_loss(
    tmp_path, monkeypatch
) -> None:
    store, mailer, auth = _services(tmp_path, monkeypatch, "legacy-email-correction")
    session = auth.register("legacy_typo", PASSWORD, "Legacy Student")
    user_id = session["user"]["userId"]
    auth.request_legacy_email_upgrade(user_id, "legacy-typo@example.edu", PASSWORD)
    old_proof = mailer.messages(purpose="email_verification")[-1]

    replaced = auth.replace_unverified_email(
        user_id=user_id,
        challenge_id=None,
        current_password=PASSWORD,
        new_email="legacy-correct@example.edu",
        client_ip="203.0.113.70",
    )
    assert replaced["verificationRequired"] is True
    assert store.get_auth_challenge(old_proof.challenge_id)["consumed_at"] is not None
    cancelled = auth.cancel_unverified_email(
        user_id=user_id,
        challenge_id=None,
        current_password=PASSWORD,
        client_ip="203.0.113.70",
    )
    assert cancelled == {
        "ok": True,
        "emailRemoved": True,
        "accountStatus": "email_upgrade_required",
    }
    user = store.get_user_auth(user_id)
    assert user["username"] == "legacy_typo"
    assert user["display_name"] == "Legacy Student"
    assert user["email_normalized"] is None
    assert auth.resolve(session["token"]) == user_id


def test_unverified_email_replacement_duplicate_and_race_fail_without_partial_mutation(
    tmp_path, monkeypatch
) -> None:
    store, mailer, auth = _services(tmp_path, monkeypatch, "email-replace-race")
    _target_pending, _target = _register_and_verify(auth, mailer, "occupied_email")
    pending = auth.register_with_email(
        "replace_racer", PASSWORD, "replace-racer@example.edu"
    )
    with pytest.raises(AuthError) as duplicate:
        auth.replace_unverified_email(
            user_id=None,
            challenge_id=pending["challengeId"],
            current_password=PASSWORD,
            new_email="student.occupied_email@example.edu",
            client_ip="203.0.113.80",
        )
    assert duplicate.value.code == "unverified_email_change_unavailable"
    assert store.get_user_by_email("replace-racer@example.edu") is not None

    original = store.replace_unverified_email
    barrier = threading.Barrier(2)

    def synchronized_replace(**kwargs):
        barrier.wait(timeout=5)
        return original(**kwargs)

    monkeypatch.setattr(store, "replace_unverified_email", synchronized_replace)
    mailer.clear()
    outcomes = []

    def replace(destination: str):
        try:
            return auth.replace_unverified_email(
                user_id=None,
                challenge_id=pending["challengeId"],
                current_password=PASSWORD,
                new_email=destination,
                client_ip="203.0.113.81",
            )
        except AuthError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(
            pool.map(
                replace,
                ("race-winner-a@example.edu", "race-winner-b@example.edu"),
            )
        )
    assert sum(isinstance(value, dict) for value in outcomes) == 1
    assert outcomes.count("unverified_email_change_unavailable") == 1
    assert len(mailer.messages(purpose="email_verification")) == 1
    present = [
        email
        for email in ("race-winner-a@example.edu", "race-winner-b@example.edu")
        if store.get_user_by_email(email)
    ]
    assert len(present) == 1


def test_retention_never_deletes_established_account_with_unverified_upgrade(
    tmp_path, monkeypatch
) -> None:
    store, _mailer, auth = _services(tmp_path, monkeypatch, "legacy-retention")
    session = auth.register("legacy_retained", PASSWORD)
    user_id = session["user"]["userId"]
    auth.request_legacy_email_upgrade(
        user_id, "legacy-retained@example.edu", PASSWORD
    )
    now = datetime.now(UTC)
    with store.connect() as conn:
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        conn.execute(
            "UPDATE users SET created_at = ? WHERE user_id = ?",
            ((now - timedelta(days=30)).isoformat(), user_id),
        )
    counts = store.cleanup_retention(
        now=now,
        guest_inactivity_days=30,
        unverified_account_expiry_days=7,
        batch_size=50,
    )
    assert counts["expiredUnverifiedAccounts"] == 0
    assert store.get_user_auth(user_id)["account_origin"] == "established"


def test_retention_releases_registration_reservations_and_expired_otp_budgets(
    tmp_path, monkeypatch
) -> None:
    store, _mailer, auth = _services(tmp_path, monkeypatch, "auth-retention")
    _pending, verified = _register_and_verify(auth, _mailer, "retention_owner")
    auth.register_with_email(
        "reserved_until_cleanup",
        PASSWORD,
        "student.retention_owner@example.edu",
    )
    owner_id = verified["user"]["userId"]
    active = store.get_active_auth_challenge(owner_id, "registration_resolution")
    assert store.verify_auth_challenge(
        challenge_id=active["challenge_id"],
        purpose="registration_resolution",
        presented_secret_hash=_wrong_hash(),
    )[0] == "incorrect"
    now = datetime.now(UTC)
    with store.connect() as conn:
        conn.execute(
            "UPDATE users SET created_at = ? WHERE username = 'reserved_until_cleanup'",
            ((now - timedelta(days=8)).isoformat(),),
        )
        conn.execute(
            "UPDATE auth_verification_budgets SET window_expires_at = ?",
            ((now - timedelta(seconds=1)).isoformat(),),
        )
    counts = store.cleanup_retention(
        now=now,
        guest_inactivity_days=30,
        unverified_account_expiry_days=7,
        batch_size=50,
    )
    assert counts["expiredUnverifiedAccounts"] == 1
    assert counts["expiredAuthVerificationBudgets"] == 1
    assert store.get_user_auth(owner_id) is not None
    restarted = auth.register_with_email(
        "reserved_until_cleanup", PASSWORD, "released-name@example.edu"
    )
    assert restarted["verificationRequired"] is True


def test_owner_can_cancel_pending_email_change_and_old_link_is_unusable(
    tmp_path, monkeypatch
) -> None:
    _store, mailer, auth = _services(tmp_path, monkeypatch, "email-change-cancel")
    _pending, session = _register_and_verify(auth, mailer, "change_cancel")
    user_id = session["user"]["userId"]
    auth.request_email_change(user_id, "new-cancelled@example.edu", PASSWORD)
    proof = mailer.messages(purpose="email_change")[-1]
    assert auth.cancel_email_change(user_id, proof.challenge_id) == {"ok": True}
    with pytest.raises(AuthError) as cancelled:
        auth.confirm_email_change(
            user_id, proof.challenge_id, proof.secret, session["token"]
        )
    assert cancelled.value.code == "challenge_used"


def test_unverified_email_correction_http_contract_supports_public_pending_and_session_legacy(
    tmp_path, monkeypatch
) -> None:
    store, mailer, auth = _services(tmp_path, monkeypatch, "email-correction-api")
    monkeypatch.setattr(main_module, "auth_service", auth)
    client = TestClient(app)

    pending = auth.register_with_email(
        "api_pending_typo", PASSWORD, "api-pending-typo@example.edu"
    )
    replaced = client.post(
        "/auth/email/unverified/replace",
        json={
            "challengeId": pending["challengeId"],
            "currentPassword": PASSWORD,
            "newEmail": "api-pending-correct@example.edu",
        },
    )
    assert replaced.status_code == 200
    assert set(replaced.json()) == {
        "verificationRequired",
        "challengeId",
        "maskedEmail",
        "expiresAt",
        "deliveryFailed",
        "retryAfterSeconds",
    }
    assert store.get_user_by_email("api-pending-correct@example.edu") is not None

    legacy = auth.register("api_legacy_typo", PASSWORD)
    user_id = legacy["user"]["userId"]
    auth.request_legacy_email_upgrade(
        user_id, "api-legacy-typo@example.edu", PASSWORD
    )
    detached = client.post(
        "/auth/email/unverified/cancel",
        headers={"Authorization": f"Bearer {legacy['token']}"},
        json={"currentPassword": PASSWORD},
    )
    assert detached.status_code == 200
    assert detached.json() == {
        "ok": True,
        "emailRemoved": True,
        "accountStatus": "email_upgrade_required",
    }
    assert store.get_user_auth(user_id)["email_normalized"] is None
