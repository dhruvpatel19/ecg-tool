"""Durable, privacy-preserving protection for expensive login hashing."""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app import auth as auth_module
from app.auth import AuthError, AuthService, LOGIN_BLOCK_MINUTES
from app.main import app, store as app_store
from app.storage import LearningStore


_PASSWORD = "Login-Throttle-Test!"


def _service(tmp_path) -> tuple[LearningStore, AuthService]:
    store = LearningStore(tmp_path / f"login-throttle-{uuid.uuid4().hex}.db")
    return store, AuthService(store, registration_rate_limit_secret="unit-test-secret")


def _fast_password_verifier(password: str, _stored: str) -> bool:
    return password == _PASSWORD


def test_pair_limit_rejects_before_user_lookup_or_password_hash_and_hides_identifiers(
    tmp_path, monkeypatch
) -> None:
    store, auth = _service(tmp_path)
    store.create_user("u_target", "target", "Target", "test-hash")
    monkeypatch.setattr(auth_module, "LOGIN_PAIR_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(auth_module, "LOGIN_IP_MAX_ATTEMPTS", 20)
    monkeypatch.setattr(auth_module, "LOGIN_GLOBAL_MAX_ATTEMPTS", 100)

    hash_calls = 0

    def reject_password(_password: str, _stored: str) -> bool:
        nonlocal hash_calls
        hash_calls += 1
        return False

    monkeypatch.setattr(auth_module, "verify_password", reject_password)
    for _ in range(2):
        with pytest.raises(AuthError) as invalid:
            auth.login(" Target ", "wrong", client_ip="203.0.113.10")
        assert invalid.value.code == "invalid"

    # Both the account lookup and the slow hash are behind the reservation.
    monkeypatch.setattr(
        auth,
        "_user_by_username",
        lambda _username: pytest.fail("throttled login reached the user lookup"),
    )
    with pytest.raises(AuthError) as blocked:
        auth.login("TARGET", "wrong", client_ip="203.0.113.10")
    assert blocked.value.code == "login_throttled"
    assert hash_calls == 2

    with store.connect() as conn:
        rows = conn.execute(
            "SELECT scope, key_hash FROM auth_login_throttle ORDER BY scope"
        ).fetchall()
    assert {row["scope"] for row in rows} == {"global", "ip", "pair"}
    assert all(len(row["key_hash"]) == 64 for row in rows)
    serialized = " ".join(row["key_hash"] for row in rows)
    assert "target" not in serialized
    assert "203.0.113.10" not in serialized


def test_rotating_usernames_are_bounded_by_the_shared_ip_bucket(
    tmp_path, monkeypatch
) -> None:
    _, auth = _service(tmp_path)
    monkeypatch.setattr(auth_module, "LOGIN_PAIR_MAX_ATTEMPTS", 100)
    monkeypatch.setattr(auth_module, "LOGIN_IP_MAX_ATTEMPTS", 3)
    monkeypatch.setattr(auth_module, "LOGIN_GLOBAL_MAX_ATTEMPTS", 100)
    hash_calls = 0

    def reject_password(_password: str, _stored: str) -> bool:
        nonlocal hash_calls
        hash_calls += 1
        return False

    monkeypatch.setattr(auth_module, "verify_password", reject_password)
    for username in ("random-one", "random-two", "random-three"):
        with pytest.raises(AuthError) as invalid:
            auth.login(username, "wrong", client_ip="198.51.100.20")
        assert invalid.value.code == "invalid"

    with pytest.raises(AuthError) as blocked:
        auth.login("random-four", "wrong", client_ip="198.51.100.20")
    assert blocked.value.code == "login_throttled"
    assert hash_calls == 3

    # A second source remains independent until the deployment-wide breaker.
    with pytest.raises(AuthError) as other_source:
        auth.login("random-four", "wrong", client_ip="198.51.100.21")
    assert other_source.value.code == "invalid"
    assert hash_calls == 4


def test_distributed_sources_are_bounded_by_global_bucket_without_debiting_rejected_work(
    tmp_path, monkeypatch
) -> None:
    store, auth = _service(tmp_path)
    monkeypatch.setattr(auth_module, "LOGIN_PAIR_MAX_ATTEMPTS", 100)
    monkeypatch.setattr(auth_module, "LOGIN_IP_MAX_ATTEMPTS", 100)
    monkeypatch.setattr(auth_module, "LOGIN_GLOBAL_MAX_ATTEMPTS", 2)
    hash_calls = 0

    def reject_password(_password: str, _stored: str) -> bool:
        nonlocal hash_calls
        hash_calls += 1
        return False

    monkeypatch.setattr(auth_module, "verify_password", reject_password)
    for index in range(2):
        with pytest.raises(AuthError) as invalid:
            auth.login(
                f"distributed-{index}",
                "wrong",
                client_ip=f"203.0.113.{index + 1}",
            )
        assert invalid.value.code == "invalid"

    for index in range(2, 12):
        with pytest.raises(AuthError) as blocked:
            auth.login(
                f"distributed-{index}",
                "wrong",
                client_ip=f"203.0.113.{index + 1}",
            )
        assert blocked.value.code == "login_throttled"
    assert hash_calls == 2

    with store.connect() as conn:
        rows = conn.execute(
            "SELECT scope, COUNT(*) AS bucket_count, SUM(attempt_count) AS attempts "
            "FROM auth_login_throttle GROUP BY scope"
        ).fetchall()
    summary = {
        row["scope"]: (row["bucket_count"], row["attempts"]) for row in rows
    }
    # Rejections at the global breaker do not create new pair/IP telemetry or
    # claim work that never reached the password verifier.
    assert summary == {"global": (1, 2), "ip": (2, 2), "pair": (2, 2)}


def test_repeated_pair_block_rejections_do_not_burn_ip_or_global_capacity(
    tmp_path, monkeypatch
) -> None:
    store, auth = _service(tmp_path)
    monkeypatch.setattr(auth_module, "LOGIN_PAIR_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(auth_module, "LOGIN_IP_MAX_ATTEMPTS", 100)
    monkeypatch.setattr(auth_module, "LOGIN_GLOBAL_MAX_ATTEMPTS", 100)
    monkeypatch.setattr(auth_module, "verify_password", lambda *_args: False)

    for _ in range(2):
        with pytest.raises(AuthError):
            auth.login("focused", "wrong", client_ip="203.0.113.50")
    for _ in range(20):
        with pytest.raises(AuthError) as blocked:
            auth.login("focused", "wrong", client_ip="203.0.113.50")
        assert blocked.value.code == "login_throttled"

    with store.connect() as conn:
        counts = {
            row["scope"]: row["attempt_count"]
            for row in conn.execute(
                "SELECT scope, attempt_count FROM auth_login_throttle"
            ).fetchall()
        }
    assert counts == {"pair": 2, "ip": 2, "global": 2}


def test_source_a_cannot_lock_a_known_learner_out_from_source_b_and_success_clears_only_pair(
    tmp_path, monkeypatch
) -> None:
    store, auth = _service(tmp_path)
    store.create_user("u_known", "known", "Known Learner", "test-hash")
    monkeypatch.setattr(auth_module, "LOGIN_PAIR_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(auth_module, "LOGIN_IP_MAX_ATTEMPTS", 100)
    monkeypatch.setattr(auth_module, "LOGIN_GLOBAL_MAX_ATTEMPTS", 100)
    monkeypatch.setattr(auth_module, "verify_password", _fast_password_verifier)

    for _ in range(2):
        with pytest.raises(AuthError) as invalid:
            auth.login("known", "wrong", client_ip="192.0.2.40")
        assert invalid.value.code == "invalid"
    with pytest.raises(AuthError) as blocked:
        auth.login("known", "wrong", client_ip="192.0.2.40")
    assert blocked.value.code == "login_throttled"

    issued = auth.login("KNOWN", _PASSWORD, client_ip="192.0.2.41")
    assert issued["user"]["userId"] == "u_known"

    source_a_pair = auth._rate_limit_digest(
        "ecg-login-v1", "pair", "192.0.2.40", "known"
    )
    source_b_pair = auth._rate_limit_digest(
        "ecg-login-v1", "pair", "192.0.2.41", "known"
    )
    source_b_ip = auth._rate_limit_digest("ecg-login-v1", "ip", "192.0.2.41")
    global_key = auth._rate_limit_digest("ecg-login-v1", "global")
    with store.connect() as conn:
        buckets = {
            (row["scope"], row["key_hash"]): row["attempt_count"]
            for row in conn.execute(
                "SELECT scope, key_hash, attempt_count FROM auth_login_throttle"
            ).fetchall()
        }
    assert ("pair", source_a_pair) in buckets
    assert ("pair", source_b_pair) not in buckets
    assert buckets[("ip", source_b_ip)] == 1
    assert buckets[("global", global_key)] == 3


def test_concurrent_login_reservations_allow_exactly_the_configured_pair_quota(
    tmp_path,
) -> None:
    store, _ = _service(tmp_path)

    def consume(_: int) -> bool:
        return store.consume_login_attempt(
            pair_key_hash="a" * 64,
            ip_key_hash="b" * 64,
            global_key_hash="c" * 64,
            max_pair_attempts=5,
            max_ip_attempts=100,
            max_global_attempts=100,
            window_minutes=15,
            block_minutes=15,
        )

    with ThreadPoolExecutor(max_workers=10) as pool:
        limited = list(pool.map(consume, range(10)))
    assert limited.count(False) == 5
    assert limited.count(True) == 5


def test_api_ignores_spoofed_forwarding_headers_and_returns_generic_429(
    monkeypatch,
) -> None:
    monkeypatch.setattr(auth_module, "LOGIN_PAIR_MAX_ATTEMPTS", 3)
    monkeypatch.setattr(auth_module, "LOGIN_IP_MAX_ATTEMPTS", 100)
    monkeypatch.setattr(auth_module, "LOGIN_GLOBAL_MAX_ATTEMPTS", 100)
    monkeypatch.setattr(auth_module, "verify_password", lambda *_args: False)
    username = f"missing-{uuid.uuid4().hex[:8]}"
    with app_store.connect() as conn:
        conn.execute("DELETE FROM auth_login_throttle")

    try:
        with TestClient(app) as client:
            for index in range(3):
                response = client.post(
                    "/auth/login",
                    headers={
                        "X-Forwarded-For": f"203.0.113.{index + 1}",
                        "Forwarded": f"for=198.51.100.{index + 1}",
                        "X-Real-IP": f"192.0.2.{index + 1}",
                    },
                    json={"username": username, "password": "wrong"},
                )
                assert response.status_code == 401
                assert response.json() == {
                    "detail": {"message": "Invalid username or password."}
                }

            blocked = client.post(
                "/auth/login",
                headers={"X-Forwarded-For": "8.8.8.8"},
                json={"username": username.upper(), "password": "wrong"},
            )
            assert blocked.status_code == 429
            assert blocked.json() == {
                "detail": {"message": "Invalid username or password."}
            }
            assert blocked.headers["retry-after"] == str(LOGIN_BLOCK_MINUTES * 60)
    finally:
        with app_store.connect() as conn:
            conn.execute("DELETE FROM auth_login_throttle")
