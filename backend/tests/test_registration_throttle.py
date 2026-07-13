"""Privacy-preserving, NAT-tolerant account registration throttling."""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app import auth as auth_module
from app.auth import AuthError, AuthService
from app.main import app
from app.storage import LearningStore


_PASSWORD = "Registration-Throttle-Test!"


def _service(tmp_path) -> tuple[LearningStore, AuthService]:
    store = LearningStore(tmp_path / f"throttle-{uuid.uuid4().hex}.db")
    return store, AuthService(store, registration_rate_limit_secret="unit-test-secret")


def test_case_and_whitespace_variants_share_pair_bucket_without_raw_identifiers(
    tmp_path, monkeypatch
) -> None:
    store, auth = _service(tmp_path)
    monkeypatch.setattr(auth_module, "REGISTRATION_PAIR_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(auth_module, "REGISTRATION_IP_MAX_ATTEMPTS", 20)
    monkeypatch.setattr(auth_module, "REGISTRATION_GLOBAL_MAX_ATTEMPTS", 100)

    for username in (" xy ", "XY"):
        with pytest.raises(AuthError) as error:
            auth.register(username, _PASSWORD, client_ip="203.0.113.10")
        assert error.value.code == "invalid_username"
    with pytest.raises(AuthError) as blocked:
        auth.register("xY", _PASSWORD, client_ip="203.0.113.10")
    assert blocked.value.code == "registration_throttled"

    with store.connect() as conn:
        rows = conn.execute(
            "SELECT scope, key_hash FROM auth_registration_throttle ORDER BY scope"
        ).fetchall()
    assert {row["scope"] for row in rows} == {"global", "ip", "pair"}
    assert all(len(row["key_hash"]) == 64 for row in rows)
    serialized = " ".join(row["key_hash"] for row in rows)
    assert "203.0.113.10" not in serialized
    assert "xy" not in serialized


def test_higher_ip_bucket_allows_unique_names_and_isolates_direct_peers(
    tmp_path, monkeypatch
) -> None:
    _, auth = _service(tmp_path)
    monkeypatch.setattr(auth_module, "REGISTRATION_PAIR_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(auth_module, "REGISTRATION_IP_MAX_ATTEMPTS", 3)
    monkeypatch.setattr(auth_module, "REGISTRATION_GLOBAL_MAX_ATTEMPTS", 100)

    for username in ("x0", "x1", "x2"):
        with pytest.raises(AuthError) as invalid:
            auth.register(username, _PASSWORD, client_ip="198.51.100.20")
        assert invalid.value.code == "invalid_username"
    with pytest.raises(AuthError) as blocked:
        auth.register("x3", _PASSWORD, client_ip="198.51.100.20")
    assert blocked.value.code == "registration_throttled"

    # A different socket peer has an independent aggregate bucket.
    with pytest.raises(AuthError) as other_peer:
        auth.register("x3", _PASSWORD, client_ip="198.51.100.21")
    assert other_peer.value.code == "invalid_username"


def test_successful_registration_still_consumes_capacity(tmp_path, monkeypatch) -> None:
    _, auth = _service(tmp_path)
    monkeypatch.setattr(auth_module, "REGISTRATION_PAIR_MAX_ATTEMPTS", 1)
    monkeypatch.setattr(auth_module, "REGISTRATION_IP_MAX_ATTEMPTS", 20)
    monkeypatch.setattr(auth_module, "REGISTRATION_GLOBAL_MAX_ATTEMPTS", 100)
    username = f"success_{uuid.uuid4().hex[:8]}"

    issued = auth.register(username, _PASSWORD, client_ip="192.0.2.40")
    assert issued["user"]["username"] == username
    with pytest.raises(AuthError) as blocked:
        auth.register(username.upper(), _PASSWORD, client_ip="192.0.2.40")
    # Throttling happens before duplicate-account disclosure.
    assert blocked.value.code == "registration_throttled"


def test_concurrent_consumption_allows_exactly_the_configured_pair_quota(tmp_path) -> None:
    store, _ = _service(tmp_path)

    def consume(_: int) -> bool:
        return store.consume_registration_attempt(
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


def test_repeated_pair_block_does_not_burn_registration_ip_or_global_capacity(
    tmp_path,
) -> None:
    store, _ = _service(tmp_path)

    def consume() -> bool:
        return store.consume_registration_attempt(
            pair_key_hash="d" * 64,
            ip_key_hash="e" * 64,
            global_key_hash="f" * 64,
            max_pair_attempts=2,
            max_ip_attempts=100,
            max_global_attempts=100,
            window_minutes=15,
            block_minutes=15,
        )

    assert consume() is False
    assert consume() is False
    assert all(consume() is True for _ in range(20))
    with store.connect() as conn:
        counts = {
            row["scope"]: row["attempt_count"]
            for row in conn.execute(
                "SELECT scope, attempt_count FROM auth_registration_throttle"
            ).fetchall()
        }
    assert counts == {"pair": 2, "ip": 2, "global": 2}


def test_distributed_registration_sources_hit_global_before_additional_hash_work(
    tmp_path, monkeypatch
) -> None:
    store, auth = _service(tmp_path)
    monkeypatch.setattr(auth_module, "REGISTRATION_PAIR_MAX_ATTEMPTS", 100)
    monkeypatch.setattr(auth_module, "REGISTRATION_IP_MAX_ATTEMPTS", 100)
    monkeypatch.setattr(auth_module, "REGISTRATION_GLOBAL_MAX_ATTEMPTS", 2)
    hash_calls = 0

    def fake_hash(_password: str, *args, **kwargs) -> str:
        del args, kwargs
        nonlocal hash_calls
        hash_calls += 1
        return "test-password-hash"

    monkeypatch.setattr(auth_module, "hash_password", fake_hash)
    suffix = uuid.uuid4().hex[:6]
    for index in range(2):
        issued = auth.register(
            f"global{suffix}{index}",
            _PASSWORD,
            client_ip=f"203.0.113.{index + 1}",
        )
        assert issued["user"]["username"].endswith(str(index))

    for index in range(2, 12):
        with pytest.raises(AuthError) as blocked:
            auth.register(
                f"global{suffix}{index}",
                _PASSWORD,
                client_ip=f"203.0.113.{index + 1}",
            )
        assert blocked.value.code == "registration_throttled"
    assert hash_calls == 2

    with store.connect() as conn:
        rows = conn.execute(
            "SELECT scope, COUNT(*) AS bucket_count, SUM(attempt_count) AS attempts "
            "FROM auth_registration_throttle GROUP BY scope"
        ).fetchall()
    assert {
        row["scope"]: (row["bucket_count"], row["attempts"]) for row in rows
    } == {"global": (1, 2), "ip": (2, 2), "pair": (2, 2)}


def test_api_ignores_spoofed_forwarding_headers_and_returns_generic_429(monkeypatch) -> None:
    monkeypatch.setattr(auth_module, "REGISTRATION_PAIR_MAX_ATTEMPTS", 3)
    monkeypatch.setattr(auth_module, "REGISTRATION_IP_MAX_ATTEMPTS", 200)
    monkeypatch.setattr(auth_module, "REGISTRATION_GLOBAL_MAX_ATTEMPTS", 10_000)
    invalid_username = f"z{uuid.uuid4().hex[:1]}"  # always under the 3-char minimum

    with TestClient(app) as client:
        for index in range(3):
            response = client.post(
                "/auth/register",
                headers={
                    "X-Forwarded-For": f"203.0.113.{index + 1}",
                    "Forwarded": f"for=198.51.100.{index + 1}",
                    "X-Real-IP": f"192.0.2.{index + 1}",
                },
                json={"username": invalid_username, "password": _PASSWORD},
            )
            assert response.status_code == 400
            assert response.json()["detail"]["code"] == "invalid_username"

        blocked = client.post(
            "/auth/register",
            headers={"X-Forwarded-For": "8.8.8.8"},
            json={"username": invalid_username.upper(), "password": _PASSWORD},
        )
        assert blocked.status_code == 429
        assert blocked.json() == {
            "detail": {
                "message": "Too many registration attempts. Please wait and try again."
            }
        }
        assert blocked.headers["retry-after"] == "900"
