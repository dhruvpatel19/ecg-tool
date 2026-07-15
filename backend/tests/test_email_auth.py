from __future__ import annotations

import sqlite3
import time
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import auth as auth_module
from app import main as main_module
from app.auth import (
    AuthError,
    AuthService,
    EMAIL_CHALLENGE_MAX_SENDS,
    PASSWORD_ITERATIONS,
    hash_password,
    password_hash_iterations,
)
from app.auth_mailer import (
    AuthEmail,
    AuthMailerUnavailable,
    BoundedAuthTaskDispatcher,
    MemoryAuthMailer,
)
from app.guest_progress import GuestProgressService
from app.main import app
from app.ontology import DEFAULT_MASTERY
from app.storage import LearningStore


PASSWORD = "correct horse battery staple"
NEW_PASSWORD = "replacement passphrase for recovery"


def _services(tmp_path):
    store = LearningStore(tmp_path / f"email-auth-{uuid.uuid4().hex}.db")
    guests = GuestProgressService(store)
    mailer = MemoryAuthMailer()
    auth = AuthService(store, guests, "email-auth-test-secret", mailer=mailer)
    return store, guests, mailer, auth


def _register_and_verify(auth: AuthService, mailer: MemoryAuthMailer, suffix: str):
    pending = auth.register_with_email(
        f"student_{suffix}",
        PASSWORD,
        f"Student.{suffix}@Example.edu",
    )
    message = next(
        item
        for item in reversed(mailer.messages(purpose="email_verification"))
        if item.challenge_id == pending["challengeId"]
    )
    session = auth.confirm_email_verification(
        message.challenge_id, message.secret, PASSWORD
    )
    return pending, session


def test_email_first_registration_needs_no_student_chosen_username(tmp_path) -> None:
    store, _guests, mailer, auth = _services(tmp_path)
    pending = auth.register_with_email(
        None,
        PASSWORD,
        "Email.First@Example.edu",
    )
    account = store.get_user_by_email("email.first@example.edu")

    assert pending["verificationRequired"] is True
    assert account is not None
    assert str(account["username"]).startswith("student_")
    assert account["display_name"] == "Student"

    proof = mailer.messages(purpose="email_verification")[-1]
    auth.confirm_email_verification(proof.challenge_id, proof.secret, PASSWORD)
    session = auth.login("EMAIL.FIRST@example.edu", PASSWORD)
    assert session["user"]["userId"] == account["user_id"]
    assert "twoFactorRequired" not in session


def test_retired_email_two_factor_migrates_an_early_pilot_account_on_login(
    tmp_path,
) -> None:
    store, guests, mailer, legacy_auth = _services(tmp_path)
    _pending, session = _register_and_verify(legacy_auth, mailer, "retired_2fa")
    user_id = str(session["user"]["userId"])
    legacy_auth.request_email_two_factor_enable(user_id, PASSWORD)
    proof = mailer.messages(purpose="two_factor_enable")[-1]
    legacy_auth.confirm_email_two_factor_enable(
        user_id,
        proof.challenge_id,
        proof.secret,
        str(session["token"]),
    )

    deployed_auth = AuthService(
        store,
        guests,
        "email-auth-test-secret",
        mailer=mailer,
        email_two_factor_enabled=False,
    )
    migrated = deployed_auth.login("student.retired_2fa@example.edu", PASSWORD)

    assert "twoFactorRequired" not in migrated
    assert store.get_user_auth(user_id)["email_two_factor_enabled"] == 0


def test_account_graph_and_first_session_are_independently_atomic(tmp_path) -> None:
    store = LearningStore(tmp_path / "atomic.db")
    user_id = "u_atomic"

    def fail(_conn: sqlite3.Connection) -> None:
        raise RuntimeError("injected post-session failure")

    with pytest.raises(RuntimeError, match="injected"):
        store.create_registered_user(
            user_id=user_id,
            username="atomic_user",
            display_name="Atomic User",
            password_hash=hash_password(PASSWORD),
            email_normalized="atomic@example.edu",
            session_token="raw-session-token",
            session_expires_at="2026-08-01T00:00:00+00:00",
            _failure_hook=fail,
        )

    with store.connect() as conn:
        assert conn.execute(
            "SELECT 1 FROM users WHERE user_id = ?", (user_id,)
        ).fetchone() is None
        assert conn.execute(
            "SELECT 1 FROM learner_profiles WHERE learner_id = ?", (user_id,)
        ).fetchone() is None
        assert conn.execute(
            "SELECT 1 FROM objective_mastery WHERE learner_id = ?", (user_id,)
        ).fetchone() is None
        assert conn.execute(
            "SELECT 1 FROM sessions WHERE user_id = ?", (user_id,)
        ).fetchone() is None


def test_verified_registration_stores_or_logs_no_plaintext_secret_and_is_one_time(
    tmp_path, caplog
) -> None:
    store, _guests, mailer, auth = _services(tmp_path)
    pending = auth.register_with_email(
        "email_student",
        PASSWORD,
        "Student@Example.EDU",
    )
    assert pending["verificationRequired"] is True
    assert pending["deliveryFailed"] is False
    message = mailer.messages(purpose="email_verification")[-1]

    with store.connect() as conn:
        user = conn.execute(
            "SELECT * FROM users WHERE username = 'email_student'"
        ).fetchone()
        assert user["email_normalized"] == "student@example.edu"
        assert user["email_verified_at"] is None
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM sessions WHERE user_id = ?",
            (user["user_id"],),
        ).fetchone()["n"] == 0
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM objective_mastery WHERE learner_id = ?",
            (user["user_id"],),
        ).fetchone()["n"] == len(DEFAULT_MASTERY)
        challenge = conn.execute(
            "SELECT secret_hash, attempt_count FROM auth_challenges "
            "WHERE challenge_id = ?",
            (message.challenge_id,),
        ).fetchone()
        assert challenge["secret_hash"] != message.secret
        assert message.secret not in str(tuple(challenge))
    assert message.secret not in caplog.text

    with pytest.raises(AuthError, match="invalid or expired"):
        auth.confirm_email_verification(
            message.challenge_id, "wrong-token", PASSWORD
        )
    session = auth.confirm_email_verification(
        message.challenge_id, message.secret, PASSWORD
    )
    assert auth.resolve(session["token"]) == session["user"]["userId"]
    with store.connect() as conn:
        stored = conn.execute(
            "SELECT token FROM sessions WHERE user_id = ?",
            (session["user"]["userId"],),
        ).fetchone()["token"]
        assert stored != session["token"]
    with pytest.raises(AuthError, match="invalid or expired"):
        auth.confirm_email_verification(
            message.challenge_id, message.secret, PASSWORD
        )

    by_email = auth.login("STUDENT@EXAMPLE.EDU", PASSWORD)
    assert by_email["user"]["username"] == "email_student"
    duplicate = auth.register_with_email(
        "different_username", PASSWORD, "student@example.edu"
    )
    assert set(duplicate) == set(pending)
    assert duplicate["verificationRequired"] is True
    resolution = mailer.messages(purpose="registration_resolution")[-1]
    resolved = auth.confirm_email_verification(
        resolution.challenge_id,
        resolution.secret,
        "a password that is intentionally irrelevant",
    )
    assert resolved == {
        "accountResolutionRequired": True,
        "suggestedAction": "sign_in_or_reset_password",
        "message": "This email is already connected to TRACE. Sign in or reset your password.",
    }
    assert "token" not in resolved


def test_email_proof_cannot_activate_an_attacker_chosen_registration_password(
    tmp_path,
) -> None:
    store, _guests, mailer, auth = _services(tmp_path)
    attacker_password = "attacker chose this registration password"
    pending = auth.register_with_email(
        "pre_registration_target",
        attacker_password,
        "target@example.edu",
    )
    message = mailer.messages(purpose="email_verification")[-1]

    with pytest.raises(AuthError) as missing_original_factor:
        auth.confirm_email_verification(
            message.challenge_id,
            message.secret,
            "email owner does not know attacker password",
            client_ip="203.0.113.10",
        )
    assert missing_original_factor.value.code == "invalid_verification_credentials"
    assert store.get_user_by_email("target@example.edu")["email_verified_at"] is None
    with store.connect() as conn:
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM sessions WHERE user_id = ?",
            (store.get_user_by_email("target@example.edu")["user_id"],),
        ).fetchone()["n"] == 0
        challenge = conn.execute(
            "SELECT credential_fingerprint, consumed_at FROM auth_challenges "
            "WHERE challenge_id = ?",
            (pending["challengeId"],),
        ).fetchone()
        assert challenge["credential_fingerprint"]
        assert challenge["consumed_at"] is None

    activated = auth.confirm_email_verification(
        message.challenge_id,
        message.secret,
        attacker_password,
        client_ip="203.0.113.10",
    )
    assert auth.resolve(activated["token"]) == activated["user"]["userId"]


def test_password_rotation_consumes_legacy_email_verification_session_proof(
    tmp_path,
) -> None:
    store, _guests, mailer, auth = _services(tmp_path)
    legacy = auth.register("legacy_verification_rotation", PASSWORD)
    user_id = legacy["user"]["userId"]
    auth.request_legacy_email_upgrade(
        user_id,
        "legacy-rotation@example.edu",
        PASSWORD,
    )
    old_proof = mailer.messages(purpose="email_verification")[-1]

    replacement = auth.change_password(user_id, PASSWORD, NEW_PASSWORD)
    assert auth.resolve(replacement["token"]) == user_id
    with pytest.raises(AuthError) as stale:
        auth.confirm_email_verification(
            old_proof.challenge_id,
            old_proof.secret,
            NEW_PASSWORD,
        )
    assert stale.value.code == "challenge_used"
    assert store.get_user(user_id)["email_verified_at"] is None


def test_login_compare_and_write_closes_stale_password_race_and_rehashes(tmp_path) -> None:
    store, _guests, _mailer, auth = _services(tmp_path)
    legacy_hash = hash_password(PASSWORD, iterations=200_000)
    store.create_user("u_legacy", "legacy_login", "Legacy", legacy_hash)
    store.ensure_profile("u_legacy", "Legacy")

    session = auth.login("legacy_login", PASSWORD)
    assert auth.resolve(session["token"]) == "u_legacy"
    upgraded = store.get_user_auth("u_legacy")
    assert password_hash_iterations(upgraded["password_hash"]) == PASSWORD_ITERATIONS

    stale_hash = upgraded["password_hash"]
    store.update_user_password("u_legacy", hash_password(NEW_PASSWORD))
    assert store.create_session_if_password_current(
        user_id="u_legacy",
        expected_password_hash=stale_hash,
        token="must-not-be-minted",
        expires_at="2026-08-01T00:00:00+00:00",
    ) is False
    assert store.get_session_user("must-not-be-minted") is None


class _FailingReadyMailer:
    ready = True
    mode = "smtp"

    def send(self, _message: AuthEmail) -> None:
        raise AuthMailerUnavailable("timeout")


def test_post_commit_delivery_failure_is_recoverable_and_does_not_reclaim_guest(tmp_path) -> None:
    store, guests, memory, _auth = _services(tmp_path)
    guest_id = f"g_{'f' * 24}"
    store.ensure_profile(guest_id, "Legacy")
    with store.connect() as conn:
        conn.execute(
            "INSERT INTO attempts (learner_id, case_id, mode, structured_answer_json, "
            "free_text_answer, confidence, hints_used, score, correct_objectives_json, "
            "missed_objectives_json, misconception_tags_json, feedback, created_at) "
            "VALUES (?, 'legacy-case', 'rapid', '{}', '', 3, 0, 1, '[]', '[]', '[]', '', ?)",
            (guest_id, "2026-07-01T00:00:00+00:00"),
        )
    failing = AuthService(
        store,
        guests,
        "email-auth-test-secret",
        mailer=_FailingReadyMailer(),
    )
    pending = failing.register_with_email(
        "delivery_failure",
        PASSWORD,
        "failure@example.edu",
        claim_guest_progress=True,
        guest_id=guest_id,
    )
    assert pending["verificationRequired"] is True
    assert pending["deliveryFailed"] is True
    assert pending["retryAfterSeconds"] == 0
    assert guests.summary(guest_id)["claimable"] is True
    assert store.get_user_by_email("failure@example.edu") is not None

    failing.mailer = memory
    resent = failing.resend_email_challenge(
        pending["challengeId"], purpose="email_verification"
    )
    assert resent["deliveryFailed"] is False
    message = memory.messages()[-1]
    verified = failing.confirm_email_verification(
        message.challenge_id, message.secret, PASSWORD
    )
    assert verified["guestClaim"]["claimed"] is True
    assert guests.summary(guest_id)["hasProgress"] is False


def test_expired_unverified_registration_releases_account_but_preserves_legacy_claim(
    tmp_path,
) -> None:
    store, guests, mailer, auth = _services(tmp_path)
    guest_id = f"g_{'p' * 24}"
    store.ensure_profile(guest_id, "Legacy")
    with store.connect() as conn:
        conn.execute(
            "INSERT INTO attempts (learner_id, case_id, mode, structured_answer_json, "
            "free_text_answer, confidence, hints_used, score, correct_objectives_json, "
            "missed_objectives_json, misconception_tags_json, feedback, created_at) "
            "VALUES (?, 'preserved-case', 'rapid', '{}', '', 3, 0, 1, '[]', '[]', '[]', '', ?)",
            (guest_id, datetime.now(UTC).isoformat()),
        )
    pending = auth.register_with_email(
        "expiring_pending",
        PASSWORD,
        "pending@example.edu",
        claim_guest_progress=True,
        guest_id=guest_id,
    )
    user = store.get_user_by_email("pending@example.edu")
    now = datetime.now(UTC)
    with store.connect() as conn:
        conn.execute(
            "UPDATE users SET created_at = ? WHERE user_id = ?",
            ((now - timedelta(days=8)).isoformat(), user["user_id"]),
        )

    counts = store.cleanup_retention(
        now=now,
        guest_inactivity_days=30,
        unverified_account_expiry_days=7,
        batch_size=20,
    )

    assert counts["expiredUnverifiedAccounts"] == 1
    assert store.get_user_by_email("pending@example.edu") is None
    assert store.get_auth_challenge(pending["challengeId"]) is None
    assert guests.summary(guest_id)["claimable"] is True
    assert guests.summary(guest_id)["attempts"] == 1


class _CapturingDispatcher:
    def __init__(self):
        self.tasks = []

    def submit(self, task):
        self.tasks.append(task)
        return True


def test_password_reset_response_path_never_looks_up_or_sends_by_account_existence(
    tmp_path, monkeypatch
) -> None:
    store, guests, mailer, base = _services(tmp_path)
    _pending, session = _register_and_verify(base, mailer, "reset")
    dispatcher = _CapturingDispatcher()
    auth = AuthService(
        store,
        guests,
        "email-auth-test-secret",
        mailer=mailer,
        recovery_dispatcher=dispatcher,
    )
    calls: list[str] = []
    original_lookup = store.get_user_by_email

    def tracked(email):
        calls.append(email)
        return original_lookup(email)

    monkeypatch.setattr(store, "get_user_by_email", tracked)
    existing = auth.request_password_reset("student.reset@example.edu")
    missing = auth.request_password_reset("missing@example.edu")
    assert existing == missing == {
        "ok": True,
        "message": "If the request is eligible, an email will be sent.",
    }
    assert calls == []
    assert len(dispatcher.tasks) == 2

    for task in dispatcher.tasks:
        task()
    assert set(calls) == {"student.reset@example.edu", "missing@example.edu"}
    reset_message = mailer.messages(purpose="password_reset")[-1]
    auth.confirm_password_reset(
        reset_message.challenge_id, reset_message.secret, NEW_PASSWORD
    )
    assert auth.resolve(session["token"]) is None
    with pytest.raises(AuthError):
        auth.login("student_reset", PASSWORD)
    assert auth.login("student_reset", NEW_PASSWORD)["user"]["username"] == "student_reset"


def test_email_owner_can_recover_an_attacker_reserved_pending_registration(
    tmp_path,
) -> None:
    store, _guests, mailer, auth = _services(tmp_path)
    attacker_password = "attacker reserved this pending account"
    pending = auth.register_with_email(
        "reserved_pending",
        attacker_password,
        "reserved@example.edu",
        "Attacker-controlled display name",
    )
    assert store.get_user_by_email("reserved@example.edu")["email_verified_at"] is None

    public = auth.request_password_reset(
        "reserved@example.edu", client_ip="203.0.113.30"
    )
    assert public == {
        "ok": True,
        "message": "If the request is eligible, an email will be sent.",
    }
    reset = mailer.messages(purpose="password_reset")[-1]
    result = auth.confirm_password_reset(
        reset.challenge_id, reset.secret, NEW_PASSWORD
    )
    assert result["ok"] is True
    assert result["identityRecovered"] is True
    assert result["username"].startswith("student_")
    assert result["username"] != "reserved_pending"
    assert result["displayName"] == "Student"
    recovered = store.get_user_by_email("reserved@example.edu")
    assert recovered["email_verified_at"] is not None
    assert recovered["username"] == result["username"]
    assert recovered["display_name"] == "Student"
    with store.connect() as conn:
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM sessions WHERE user_id = ?",
            (recovered["user_id"],),
        ).fetchone()["n"] == 0
        assert conn.execute(
            "SELECT consumed_at FROM auth_challenges WHERE challenge_id = ?",
            (pending["challengeId"],),
        ).fetchone()["consumed_at"] is not None
    with pytest.raises(AuthError):
        auth.login("reserved@example.edu", attacker_password)
    with pytest.raises(AuthError):
        auth.login("reserved_pending", NEW_PASSWORD)
    signed_in = auth.login("reserved@example.edu", NEW_PASSWORD)
    assert signed_in["user"]["userId"] == recovered["user_id"]
    assert len(mailer.messages(purpose="password_reset_complete")) == 1


def test_pending_identity_recovery_collision_rolls_back_then_allows_safe_retry(
    tmp_path,
) -> None:
    store, _guests, mailer, auth = _services(tmp_path)
    _registered, existing = _register_and_verify(auth, mailer, "identity_taken")
    occupied_username = existing["user"]["username"]
    pending = auth.register_with_email(
        "attacker_shell",
        "attacker selected this credential",
        "identity-owner@example.edu",
        "Attacker label",
    )
    auth.request_password_reset(
        "identity-owner@example.edu", client_ip="203.0.113.31"
    )
    reset = mailer.messages(purpose="password_reset")[-1]
    before = store.get_user_by_email("identity-owner@example.edu")

    with pytest.raises(AuthError) as collision:
        auth.confirm_password_reset(
            reset.challenge_id,
            reset.secret,
            NEW_PASSWORD,
            recovery_username=occupied_username,
            recovery_display_name="Intended Owner",
        )
    assert collision.value.code == "recovery_identity_unavailable"
    unchanged = store.get_user_by_email("identity-owner@example.edu")
    assert unchanged["username"] == "attacker_shell"
    assert unchanged["display_name"] == "Attacker label"
    assert unchanged["password_hash"] == before["password_hash"]
    assert unchanged["email_verified_at"] is None
    assert not mailer.messages(purpose="password_reset_complete")
    with store.connect() as conn:
        assert conn.execute(
            "SELECT consumed_at FROM auth_challenges WHERE challenge_id = ?",
            (reset.challenge_id,),
        ).fetchone()["consumed_at"] is None
        assert conn.execute(
            "SELECT consumed_at FROM auth_challenges WHERE challenge_id = ?",
            (pending["challengeId"],),
        ).fetchone()["consumed_at"] is None

    recovered = auth.confirm_password_reset(
        reset.challenge_id,
        reset.secret,
        NEW_PASSWORD,
        recovery_username="intended_owner",
        recovery_display_name="Intended Owner",
    )
    assert recovered == {
        "ok": True,
        "identityRecovered": True,
        "username": "intended_owner",
        "displayName": "Intended Owner",
    }
    user = store.get_user_by_email("identity-owner@example.edu")
    assert user["username"] == "intended_owner"
    assert user["display_name"] == "Intended Owner"
    assert user["email_verified_at"] is not None
    with store.connect() as conn:
        assert conn.execute(
            "SELECT display_name FROM learner_profiles WHERE learner_id = ?",
            (user["user_id"],),
        ).fetchone()["display_name"] == "Intended Owner"
    assert auth.login("identity-owner@example.edu", NEW_PASSWORD)["user"][
        "username"
    ] == "intended_owner"
    assert len(mailer.messages(purpose="password_reset_complete")) == 1


def test_password_reset_preproof_errors_do_not_reveal_pending_account_state(
    tmp_path,
) -> None:
    _store, _guests, mailer, auth = _services(tmp_path)
    auth.register_with_email(
        "pending_state_probe",
        PASSWORD,
        "pending-state@example.edu",
    )
    _verified_pending, _verified = _register_and_verify(
        auth, mailer, "verified_state_probe"
    )
    auth.request_password_reset(
        "pending-state@example.edu", client_ip="203.0.113.41"
    )
    pending_reset = mailer.messages(purpose="password_reset")[-1]
    auth.request_password_reset(
        "student.verified_state_probe@example.edu",
        client_ip="203.0.113.42",
    )
    verified_reset = mailer.messages(purpose="password_reset")[-1]

    invalid_identity_errors = []
    for reset in (pending_reset, verified_reset):
        with pytest.raises(AuthError) as raised:
            auth.confirm_password_reset(
                reset.challenge_id,
                "wrong-proof",
                NEW_PASSWORD,
                recovery_username="invalid username!",
            )
        invalid_identity_errors.append(
            (raised.value.code, raised.value.field, str(raised.value))
        )
    assert len(set(invalid_identity_errors)) == 1

    invalid_proof_errors = []
    for reset in (pending_reset, verified_reset):
        with pytest.raises(AuthError) as raised:
            auth.confirm_password_reset(
                reset.challenge_id,
                "wrong-proof",
                NEW_PASSWORD,
                recovery_username="valid_recovery_name",
                recovery_display_name="Recovered Student",
            )
        invalid_proof_errors.append((raised.value.code, str(raised.value)))
    assert len(set(invalid_proof_errors)) == 1
    assert invalid_proof_errors[0][0] == "challenge_incorrect"


def test_registration_hides_email_membership_but_keeps_username_availability_public(
    tmp_path,
    monkeypatch,
) -> None:
    store, _guests, mailer, auth = _services(tmp_path)
    original_pending, verified = _register_and_verify(auth, mailer, "membership")
    mailer.clear()

    # The unique insert is attempted before any email-owner lookup. Both new
    # and existing-email requests pay password-hash + write + delivery work;
    # the latter receives a real owner-only resolution code, not a fake dead
    # end. Only username availability remains intentionally public.
    events: list[str] = []
    atomic_insert = store.create_registered_user
    username_lookup = auth._user_by_username
    owner_lookup = store.get_user_by_email

    def record_insert(**kwargs):
        events.append("atomic_insert")
        return atomic_insert(**kwargs)

    def record_lookup(email):
        events.append("owner_lookup")
        return owner_lookup(email)

    def record_username_lookup(username):
        events.append("username_lookup")
        return username_lookup(username)

    monkeypatch.setattr(store, "create_registered_user", record_insert)
    monkeypatch.setattr(store, "get_user_by_email", record_lookup)
    monkeypatch.setattr(auth, "_user_by_username", record_username_lookup)
    existing_email = auth.register_with_email(
        "other_membership", PASSWORD, "student.membership@example.edu"
    )
    assert events[:3] == ["atomic_insert", "username_lookup", "owner_lookup"]
    assert set(existing_email) == set(original_pending)
    assert existing_email["verificationRequired"] is True
    resolution = mailer.messages(purpose="registration_resolution")[-1]
    assert resolution.recipient == "student.membership@example.edu"

    with pytest.raises(AuthError) as username_taken:
        auth.register_with_email(
            verified["user"]["username"],
            PASSWORD,
            "other-membership@example.edu",
        )
    assert username_taken.value.code == "username_taken"
    assert username_taken.value.field == "username"

    events.clear()
    with pytest.raises(AuthError) as both_taken:
        auth.register_with_email(
            verified["user"]["username"],
            PASSWORD,
            "student.membership@example.edu",
        )
    assert both_taken.value.code == "username_taken"
    assert both_taken.value.field == "username"
    assert events == ["atomic_insert", "username_lookup"]
    with store.connect() as conn:
        # Existing-email registration reserves the submitted public handle in
        # the same UNIQUE namespace, making a repeat indistinguishable from a
        # repeat against a genuinely new pending registration.
        assert conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"] == 2
        reservation = conn.execute(
            "SELECT registration_reservation, email_normalized FROM users "
            "WHERE username = 'other_membership'"
        ).fetchone()
        assert reservation["registration_reservation"] == 1
        assert reservation["email_normalized"] is None
        assert conn.execute(
            "SELECT COUNT(*) AS n FROM auth_challenges"
        ).fetchone()["n"] == 2


def test_registration_guest_claim_intent_cannot_reveal_existing_email(
    tmp_path,
) -> None:
    _store, _guests, mailer, auth = _services(tmp_path)
    _pending, _verified = _register_and_verify(auth, mailer, "claim_oracle")
    guest_id = f"g_{'c' * 24}"

    fresh = auth.register_with_email(
        "fresh_claim_oracle",
        PASSWORD,
        "fresh-claim-oracle@example.edu",
        claim_guest_progress=True,
        guest_id=guest_id,
    )
    existing = auth.register_with_email(
        "existing_claim_oracle",
        PASSWORD,
        "student.claim_oracle@example.edu",
        claim_guest_progress=True,
        guest_id=guest_id,
    )
    assert fresh["guestClaimPendingVerification"] is True
    assert existing["guestClaimPendingVerification"] is True
    assert set(fresh) == set(existing)
    # Resolution proves email ownership but cannot attach the submitted legacy
    # namespace or issue a session.
    resolution = mailer.messages(purpose="registration_resolution")[-1]
    resolved = auth.confirm_email_verification(
        resolution.challenge_id,
        resolution.secret,
        PASSWORD,
    )
    assert resolved["accountResolutionRequired"] is True
    assert "guestClaim" not in resolved
    assert "token" not in resolved


def test_registration_verification_and_resolution_share_password_work_path(
    tmp_path,
    monkeypatch,
) -> None:
    store, _guests, mailer, auth = _services(tmp_path)
    new_registration = auth.register_with_email(
        "password_work_new",
        PASSWORD,
        "password-work-new@example.edu",
    )
    _pending, _verified = _register_and_verify(auth, mailer, "password_work_existing")
    existing_registration = auth.register_with_email(
        "password_work_resolution",
        PASSWORD,
        "student.password_work_existing@example.edu",
    )
    existing_owner_hash = store.get_user_by_email(
        "student.password_work_existing@example.edu"
    )["password_hash"]

    original_verify = auth_module.verify_password
    calls: list[str] = []

    def record_verify(password, stored):
        calls.append(stored)
        return original_verify(password, stored)

    monkeypatch.setattr(auth_module, "verify_password", record_verify)
    observed: list[tuple[str, str]] = []
    for challenge in (new_registration, existing_registration):
        calls.clear()
        with pytest.raises(AuthError) as wrong:
            auth.confirm_email_verification(
                challenge["challengeId"],
                "not-the-owner-code",
                PASSWORD,
                client_ip="203.0.113.51",
            )
        assert len(calls) == 1
        observed.append((wrong.value.code, calls[0]))

    assert observed[0][0] == observed[1][0] == "challenge_incorrect"
    assert observed[0][1] != auth_module._DUMMY_PASSWORD_HASH
    assert observed[1][1] == auth_module._DUMMY_PASSWORD_HASH
    assert observed[1][1] != existing_owner_hash


def test_public_registration_and_recovery_cannot_reset_account_mail_ceiling(
    tmp_path,
    monkeypatch,
) -> None:
    store, _guests, mailer, auth = _services(tmp_path)
    _pending, _verified = _register_and_verify(auth, mailer, "mail_ceiling")
    email = "student.mail_ceiling@example.edu"
    mailer.clear()

    # Keep this abuse-boundary test fast while retaining the same valid stored
    # hash shape and atomic insert-collision path.
    precomputed_hash = hash_password(PASSWORD, iterations=100_000)
    monkeypatch.setattr(
        auth_module, "hash_password", lambda _password: precomputed_hash
    )
    first = auth.register_with_email("ceiling_probe_0", PASSWORD, email)
    resolution_id = first["challengeId"]
    for _ in range(EMAIL_CHALLENGE_MAX_SENDS - 1):
        store.allow_auth_challenge_resend_now(resolution_id)
        auth.resend_registration_email(resolution_id)
    assert len(mailer.messages(purpose="registration_resolution")) == EMAIL_CHALLENGE_MAX_SENDS

    returned_ids = set()
    for index in range(1, 13):
        result = auth.register_with_email(
            f"ceiling_probe_{index}", PASSWORD, email, client_ip=f"198.51.100.{index}"
        )
        returned_ids.add(result["challengeId"])
    assert returned_ids == {resolution_id}
    assert len(mailer.messages(purpose="registration_resolution")) == EMAIL_CHALLENGE_MAX_SENDS

    # Password reset has the same per-account/window ceiling even across
    # distributed request IPs. Exhaustion remains a generic public success.
    mailer.clear()
    auth.request_password_reset(email, client_ip="203.0.113.1")
    reset_id = mailer.messages(purpose="password_reset")[-1].challenge_id
    for index in range(2, EMAIL_CHALLENGE_MAX_SENDS + 1):
        store.allow_auth_challenge_resend_now(reset_id)
        auth.request_password_reset(email, client_ip=f"203.0.113.{index}")
    assert len(mailer.messages(purpose="password_reset")) == EMAIL_CHALLENGE_MAX_SENDS
    for index in range(20, 32):
        store.allow_auth_challenge_resend_now(reset_id)
        response = auth.request_password_reset(
            email, client_ip=f"203.0.113.{index}"
        )
        assert response["ok"] is True
    assert len(mailer.messages(purpose="password_reset")) == EMAIL_CHALLENGE_MAX_SENDS
    assert store.get_active_auth_challenge(
        _verified["user"]["userId"], "password_reset"
    )["challenge_id"] == reset_id


def test_email_2fa_attempts_are_hashed_one_time_and_credential_bound(tmp_path) -> None:
    store, _guests, mailer, auth = _services(tmp_path)
    _pending, session = _register_and_verify(auth, mailer, "twofactor")
    user_id = session["user"]["userId"]
    with pytest.raises(AuthError) as hijacked_session_only:
        auth.request_email_two_factor_enable(user_id, "wrong-password")
    assert hijacked_session_only.value.code == "invalid_current_password"
    enable = auth.request_email_two_factor_enable(user_id, PASSWORD)
    message = mailer.messages(purpose="two_factor_enable")[-1]
    with store.connect() as conn:
        assert conn.execute(
            "SELECT secret_hash FROM auth_challenges WHERE challenge_id = ?",
            (message.challenge_id,),
        ).fetchone()["secret_hash"] != message.secret
    wrong_code = "000000" if message.secret != "000000" else "000001"
    with pytest.raises(AuthError) as wrong:
        auth.confirm_email_two_factor_enable(
            user_id, message.challenge_id, wrong_code, session["token"]
        )
    assert wrong.value.code in {"challenge_incorrect", "challenge_attempts_exhausted"}
    assert auth.confirm_email_two_factor_enable(
        user_id, message.challenge_id, message.secret, session["token"]
    )["emailTwoFactorEnabled"] is True

    auth.logout(session["token"])
    challenge = auth.login("student_twofactor", PASSWORD)
    assert challenge["twoFactorRequired"] is True
    assert "token" not in challenge
    otp = mailer.messages(purpose="two_factor_login")[-1]
    completed = auth.verify_email_two_factor(otp.challenge_id, otp.secret)
    assert auth.resolve(completed["token"]) == user_id
    with pytest.raises(AuthError):
        auth.verify_email_two_factor(otp.challenge_id, otp.secret)


def test_email_2fa_disable_rejects_password_rotated_after_reauthentication(
    tmp_path,
) -> None:
    store, _guests, mailer, auth = _services(tmp_path)
    _pending, session = _register_and_verify(auth, mailer, "disable_race")
    user_id = session["user"]["userId"]
    auth.request_email_two_factor_enable(user_id, PASSWORD)
    enable = mailer.messages(purpose="two_factor_enable")[-1]
    enabled = auth.confirm_email_two_factor_enable(
        user_id, enable.challenge_id, enable.secret, session["token"]
    )
    current_token = enabled["_sessionToken"]
    assert store.get_user_auth(user_id)["email_two_factor_enabled"] == 1

    auth.request_email_two_factor_disable(user_id, PASSWORD)
    disable = mailer.messages(purpose="two_factor_disable")[-1]
    store.update_user_password(user_id, hash_password(NEW_PASSWORD))
    with pytest.raises(AuthError) as stale:
        auth.confirm_email_two_factor_disable(
            user_id, disable.challenge_id, disable.secret, current_token
        )

    assert stale.value.code == "challenge_stale"
    assert store.get_user_auth(user_id)["email_two_factor_enabled"] == 1


def test_enabling_email_two_factor_rotates_current_session_and_revokes_preexisting_sessions(
    tmp_path,
) -> None:
    store, _guests, mailer, auth = _services(tmp_path)
    _pending, current = _register_and_verify(auth, mailer, "enable_revoke")
    user_id = current["user"]["userId"]
    preexisting = auth.login("student_enable_revoke", PASSWORD)
    _other_pending, other_owner = _register_and_verify(
        auth, mailer, "enable_revoke_other"
    )

    auth.request_email_two_factor_enable(user_id, PASSWORD)
    proof = mailer.messages(purpose="two_factor_enable")[-1]
    with pytest.raises(AuthError) as foreign_session:
        auth.confirm_email_two_factor_enable(
            user_id,
            proof.challenge_id,
            proof.secret,
            other_owner["token"],
        )
    assert foreign_session.value.code == "challenge_stale"
    assert store.get_user_auth(user_id)["email_two_factor_enabled"] == 0
    assert store.get_auth_challenge(proof.challenge_id)["consumed_at"] is None

    enabled = auth.confirm_email_two_factor_enable(
        user_id,
        proof.challenge_id,
        proof.secret,
        current["token"],
    )
    assert enabled["emailTwoFactorEnabled"] is True
    assert enabled["_sessionToken"] != current["token"]
    assert auth.resolve(enabled["_sessionToken"]) == user_id
    assert auth.resolve(current["token"]) is None
    assert auth.resolve(preexisting["token"]) is None
    assert auth.resolve(other_owner["token"]) == other_owner["user"]["userId"]


def test_email_two_factor_enable_api_binds_revocation_to_presented_session(
    tmp_path, monkeypatch
) -> None:
    store, guests, mailer, auth = _services(tmp_path)
    _pending, current = _register_and_verify(auth, mailer, "enable_api_revoke")
    user_id = current["user"]["userId"]
    preexisting = auth.login("student_enable_api_revoke", PASSWORD)
    auth.request_email_two_factor_enable(user_id, PASSWORD)
    proof = mailer.messages(purpose="two_factor_enable")[-1]
    monkeypatch.setattr(main_module, "store", store)
    monkeypatch.setattr(main_module, "guest_progress_service", guests)
    monkeypatch.setattr(main_module, "auth_service", auth)

    with TestClient(app) as client:
        client.cookies.set("ecg_session", current["token"])
        response = client.post(
            "/auth/2fa/email/enable/confirm",
            json={"challengeId": proof.challenge_id, "code": proof.secret},
        )
        replacement_tokens = [
            cookie.value
            for cookie in client.cookies.jar
            if cookie.name == "ecg_session" and cookie.value != current["token"]
        ]
    assert response.status_code == 200, response.text
    assert response.json()["emailTwoFactorEnabled"] is True
    assert "token" not in response.json()
    assert "_sessionToken" not in response.json()
    assert len(replacement_tokens) == 1
    replacement_token = replacement_tokens[0]
    assert auth.resolve(replacement_token) == user_id
    assert auth.resolve(current["token"]) is None
    assert auth.resolve(preexisting["token"]) is None


def test_logout_all_consumes_pending_two_factor_session_proof(tmp_path) -> None:
    _store, _guests, mailer, auth = _services(tmp_path)
    _pending, session = _register_and_verify(auth, mailer, "logout_pending_2fa")
    user_id = session["user"]["userId"]
    auth.request_email_two_factor_enable(user_id, PASSWORD)
    enable = mailer.messages(purpose="two_factor_enable")[-1]
    auth.confirm_email_two_factor_enable(
        user_id, enable.challenge_id, enable.secret, session["token"]
    )

    pending_login = auth.login("student_logout_pending_2fa", PASSWORD)
    assert pending_login["twoFactorRequired"] is True
    login_code = mailer.messages(purpose="two_factor_login")[-1]
    auth.logout_all(user_id)

    with pytest.raises(AuthError) as stale:
        auth.verify_email_two_factor(login_code.challenge_id, login_code.secret)
    assert stale.value.code == "challenge_used"


def test_logout_all_consumes_pending_password_reset_proof(tmp_path) -> None:
    _store, _guests, mailer, auth = _services(tmp_path)
    _pending, session = _register_and_verify(auth, mailer, "logout_pending_reset")
    user_id = session["user"]["userId"]
    auth.request_password_reset(
        "student.logout_pending_reset@example.edu",
        client_ip="203.0.113.20",
    )
    reset = mailer.messages(purpose="password_reset")[-1]

    auth.logout_all(user_id)
    with pytest.raises(AuthError) as stale:
        auth.confirm_password_reset(
            reset.challenge_id, reset.secret, NEW_PASSWORD
        )
    assert stale.value.code == "challenge_used"
    assert auth.login("student_logout_pending_reset", PASSWORD)["user"][
        "userId"
    ] == user_id


def test_email_change_proves_new_destination_and_revokes_other_sessions_and_challenges(
    tmp_path,
) -> None:
    store, _guests, mailer, auth = _services(tmp_path)
    _pending, first = _register_and_verify(auth, mailer, "change")
    second = auth.login("student_change", PASSWORD)
    user_id = first["user"]["userId"]
    auth.request_email_two_factor_enable(user_id, PASSWORD)

    change = auth.request_email_change(
        user_id, "new-address@example.edu", PASSWORD
    )
    assert store.get_user_by_email("student.change@example.edu") is not None
    assert store.get_user_by_email("new-address@example.edu") is None
    message = mailer.messages(purpose="email_change")[-1]
    result = auth.confirm_email_change(
        user_id,
        message.challenge_id,
        message.secret,
        first["token"],
    )
    assert result["user"]["emailMasked"] == "n***@e***.edu"
    assert result["_sessionToken"] != first["token"]
    assert auth.resolve(result["_sessionToken"]) == user_id
    assert auth.resolve(first["token"]) is None
    assert auth.resolve(second["token"]) is None
    assert store.get_user_by_email("student.change@example.edu") is None
    assert store.get_user_by_email("new-address@example.edu")["user_id"] == user_id
    with store.connect() as conn:
        remaining = conn.execute(
            "SELECT COUNT(*) AS n FROM auth_challenges "
            "WHERE user_id = ? AND consumed_at IS NULL",
            (user_id,),
        ).fetchone()["n"]
        assert remaining == 0


def test_committed_security_changes_notify_the_protected_destination(
    tmp_path,
) -> None:
    store, _guests, mailer, auth = _services(tmp_path)
    _pending, session = _register_and_verify(auth, mailer, "security_notice")
    user_id = session["user"]["userId"]
    original_email = "student.security_notice@example.edu"
    mailer.clear()

    auth.request_email_two_factor_enable(user_id, PASSWORD)
    enable = mailer.messages(purpose="two_factor_enable")[-1]
    enabled = auth.confirm_email_two_factor_enable(
        user_id, enable.challenge_id, enable.secret, session["token"]
    )
    auth.request_email_two_factor_disable(user_id, PASSWORD)
    disable = mailer.messages(purpose="two_factor_disable")[-1]
    disabled = auth.confirm_email_two_factor_disable(
        user_id, disable.challenge_id, disable.secret, enabled["_sessionToken"]
    )
    assert disabled["emailTwoFactorEnabled"] is False

    replacement = auth.change_password(user_id, PASSWORD, NEW_PASSWORD)
    change = auth.request_email_change(
        user_id, "changed-security@example.edu", NEW_PASSWORD
    )
    change_message = mailer.messages(purpose="email_change")[-1]
    auth.confirm_email_change(
        user_id,
        change_message.challenge_id,
        change_message.secret,
        replacement["token"],
    )
    auth.delete_account(
        user_id,
        NEW_PASSWORD,
        session["user"]["username"],
    )

    expected = {
        "two_factor_enabled": original_email,
        "two_factor_disabled": original_email,
        "password_changed": original_email,
        "email_changed": original_email,
        "account_deleted": "changed-security@example.edu",
    }
    for purpose, recipient in expected.items():
        messages = mailer.messages(purpose=purpose)
        assert len(messages) == 1, purpose
        assert messages[0].recipient == recipient
    assert store.get_user(user_id) is None


def test_security_notification_failure_never_undoes_committed_password_change(
    tmp_path,
) -> None:
    store = LearningStore(tmp_path / "notification-failure.db")
    guests = GuestProgressService(store)

    class FailingSecurityMailer(MemoryAuthMailer):
        def send(self, message):
            if message.purpose == "password_changed":
                raise AuthMailerUnavailable("secondary notification unavailable")
            super().send(message)

    mailer = FailingSecurityMailer()
    auth = AuthService(
        store, guests, "notification-failure-secret", mailer=mailer
    )
    _pending, session = _register_and_verify(auth, mailer, "notify_failure")

    replacement = auth.change_password(
        session["user"]["userId"], PASSWORD, NEW_PASSWORD
    )
    assert auth.resolve(replacement["token"]) == session["user"]["userId"]
    with pytest.raises(AuthError):
        auth.login("student_notify_failure", PASSWORD)
    assert auth.login("student_notify_failure", NEW_PASSWORD)["user"][
        "userId"
    ] == session["user"]["userId"]
    assert not mailer.messages(purpose="password_changed")


def test_failed_password_rotation_emits_no_security_notification(
    tmp_path,
    monkeypatch,
) -> None:
    _store, _guests, mailer, auth = _services(tmp_path)
    _pending, session = _register_and_verify(auth, mailer, "no_false_notice")
    mailer.clear()
    monkeypatch.setattr(auth.store, "rotate_password_and_sessions", lambda **_kwargs: False)

    with pytest.raises(AuthError) as failed:
        auth.change_password(session["user"]["userId"], PASSWORD, NEW_PASSWORD)
    assert failed.value.code == "password_changed"
    assert not mailer.messages(purpose="password_changed")


def test_bounded_dispatcher_counts_security_notification_delivery_failure(
    tmp_path,
) -> None:
    store = LearningStore(tmp_path / "notification-telemetry.db")
    guests = GuestProgressService(store)

    class FailingSecurityMailer(MemoryAuthMailer):
        def send(self, message):
            if message.purpose == "password_changed":
                raise AuthMailerUnavailable("secret-free simulated failure")
            super().send(message)

    mailer = FailingSecurityMailer()
    dispatcher = BoundedAuthTaskDispatcher(workers=1, capacity=2)
    auth = AuthService(
        store,
        guests,
        "notification-telemetry-secret",
        mailer=mailer,
        recovery_dispatcher=dispatcher,
    )
    _pending, session = _register_and_verify(auth, mailer, "notify_telemetry")
    replacement = auth.change_password(
        session["user"]["userId"], PASSWORD, NEW_PASSWORD
    )
    assert auth.resolve(replacement["token"]) == session["user"]["userId"]

    deadline = time.monotonic() + 2
    while dispatcher.telemetry()["completed"] < 1 and time.monotonic() < deadline:
        time.sleep(0.01)
    telemetry = dispatcher.telemetry()
    assert telemetry["submitted"] == 1
    assert telemetry["completed"] == 1
    assert telemetry["failed"] == 1


def test_email_api_issues_no_cookie_before_verification(tmp_path, monkeypatch) -> None:
    store, guests, mailer, auth = _services(tmp_path)
    monkeypatch.setattr(main_module, "store", store)
    monkeypatch.setattr(main_module, "guest_progress_service", guests)
    monkeypatch.setattr(main_module, "auth_service", auth)

    with TestClient(app) as client:
        capabilities = client.get("/auth/capabilities")
        assert capabilities.status_code == 200
        assert capabilities.json() == {
            "verifiedEmailRequired": True,
            "emailTwoFactorAvailable": True,
            "passwordRecoveryAvailable": True,
        }
        assert "mode" not in capabilities.text
        registered = client.post(
            "/auth/register",
            json={
                "username": "api_email_student",
                "password": PASSWORD,
                "email": "api@example.edu",
            },
        )
        assert registered.status_code == 200, registered.text
        assert registered.json()["verificationRequired"] is True
        assert client.cookies.get("ecg_session") is None
        message = mailer.messages(purpose="email_verification")[-1]
        verified = client.post(
            "/auth/email/verify/confirm",
            json={
                "challengeId": message.challenge_id,
                "token": message.secret,
                "password": PASSWORD,
            },
        )
        assert verified.status_code == 200, verified.text
        assert client.cookies.get("ecg_session")


def test_registration_api_existing_email_matches_new_account_public_contract(
    tmp_path,
    monkeypatch,
) -> None:
    store, guests, mailer, auth = _services(tmp_path)
    _pending, _verified = _register_and_verify(auth, mailer, "oracle")
    mailer.clear()
    monkeypatch.setattr(main_module, "store", store)
    monkeypatch.setattr(main_module, "guest_progress_service", guests)
    monkeypatch.setattr(main_module, "auth_service", auth)

    with TestClient(app) as client:
        fresh = client.post(
            "/auth/register",
            json={
                "username": "fresh_oracle",
                "password": PASSWORD,
                "email": "someone-new@example.edu",
            },
        )
        existing = client.post(
            "/auth/register",
            json={
                "username": "existing_email_oracle",
                "password": PASSWORD,
                "email": "student.oracle@example.edu",
            },
        )

        assert fresh.status_code == existing.status_code == 200
        assert set(fresh.json()) == set(existing.json())
        for body in (fresh.json(), existing.json()):
            assert body["verificationRequired"] is True
            assert body["maskedEmail"] == "s***@e***.edu"
            assert body["guestClaimPendingVerification"] is False
            assert isinstance(body["challengeId"], str)
            assert isinstance(body["expiresAt"], str)
            assert "token" not in body
            assert "user" not in body
        assert client.cookies.get("ecg_session") is None

        resolution = mailer.messages(purpose="registration_resolution")[-1]
        resolved = client.post(
            "/auth/email/verify/confirm",
            json={
                "challengeId": resolution.challenge_id,
                "token": resolution.secret,
                "password": "not used for owner-only account resolution",
            },
        )
        assert resolved.status_code == 200, resolved.text
        assert resolved.json()["accountResolutionRequired"] is True
        assert resolved.json()["suggestedAction"] == "sign_in_or_reset_password"
        assert client.cookies.get("ecg_session") is None


def test_verified_account_can_explicitly_claim_positive_legacy_cookie(
    tmp_path, monkeypatch
) -> None:
    store, guests, mailer, auth = _services(tmp_path)
    _pending, session = _register_and_verify(auth, mailer, "claim_endpoint")
    guest_id = f"g_{'z' * 24}"
    foreign_id = f"g_{'y' * 24}"
    store.ensure_profile(guest_id, "Legacy")
    with store.connect() as conn:
        conn.execute(
            "INSERT INTO attempts (learner_id, case_id, mode, structured_answer_json, "
            "free_text_answer, confidence, hints_used, score, correct_objectives_json, "
            "missed_objectives_json, misconception_tags_json, feedback, created_at) "
            "VALUES (?, 'claimable-case', 'rapid', '{}', '', 3, 0, 1, "
            "'[]', '[]', '[]', '', ?)",
            (guest_id, datetime.now(UTC).isoformat()),
        )
    monkeypatch.setattr(main_module, "store", store)
    monkeypatch.setattr(main_module, "guest_progress_service", guests)
    monkeypatch.setattr(main_module, "auth_service", auth)

    with TestClient(app) as client:
        client.cookies.set(
            "ecg_guest", guest_id, domain="testserver.local", path="/"
        )
        monkeypatch.setattr(
            main_module, "current_claimable_guest_learner", lambda: foreign_id
        )
        foreign = client.post(
            "/auth/guest-progress/claim",
            headers={"Authorization": f"Bearer {session['token']}"},
        )
        assert foreign.status_code == 400
        assert guests.summary(guest_id)["attempts"] == 1

        monkeypatch.setattr(
            main_module, "current_claimable_guest_learner", lambda: guest_id
        )
        response = client.post(
            "/auth/guest-progress/claim",
            headers={"Authorization": f"Bearer {session['token']}"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["guestClaim"]["claimed"] is True
        assert client.cookies.get("ecg_guest") is None
    assert guests.summary(guest_id)["hasProgress"] is False


@pytest.mark.parametrize(
    "path",
    [
        "/learners/demo",
        "/learning/preferences",
        "/learners/demo/mastery",
        "/learners/demo/competencies",
        "/adaptive/plan",
        "/learning/resume",
        "/learning/activity",
        "/learners/demo/pathway-progress",
        "/tutor/threads",
        "/curriculum",
        "/training/campaigns/active",
        "/rapid/rounds/active",
        "/clinical/shift/active",
    ],
)
def test_production_learning_surfaces_reject_anonymous_owner(
    path, tmp_path, monkeypatch
) -> None:
    store, guests, _mailer, auth = _services(tmp_path)
    monkeypatch.setattr(main_module, "store", store)
    monkeypatch.setattr(main_module, "guest_progress_service", guests)
    monkeypatch.setattr(main_module, "auth_service", auth)
    monkeypatch.setattr(main_module, "settings", SimpleNamespace(app_env="production"))

    with TestClient(app) as client:
        response = client.get(path)
    assert response.status_code == 401, (path, response.text)
    assert response.json()["detail"]["code"] == "authentication_required"
    assert response.headers.get("set-cookie") is None


def test_production_requires_verified_account_and_allows_verified_owner(
    tmp_path, monkeypatch
) -> None:
    store, guests, mailer, auth = _services(tmp_path)
    monkeypatch.setattr(main_module, "store", store)
    monkeypatch.setattr(main_module, "guest_progress_service", guests)
    monkeypatch.setattr(main_module, "auth_service", auth)
    monkeypatch.setattr(main_module, "settings", SimpleNamespace(app_env="production"))

    legacy = auth.register("legacy_upgrade", PASSWORD)
    _pending, verified = _register_and_verify(auth, mailer, "production")
    with TestClient(app) as client:
        blocked = client.get(
            "/learning/preferences",
            headers={"Authorization": f"Bearer {legacy['token']}"},
        )
        allowed = client.get(
            "/learning/preferences",
            headers={"Authorization": f"Bearer {verified['token']}"},
        )
    assert blocked.status_code == 403
    assert blocked.json()["detail"]["code"] == "email_upgrade_required"
    assert allowed.status_code == 200, allowed.text
