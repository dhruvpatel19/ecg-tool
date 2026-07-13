from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.config import Settings
from app.origin_guard import OriginKeyMiddleware, trusted_registration_ip


def guarded_client(secret: str | None = "deployment-secret") -> TestClient:
    app = FastAPI()
    app.add_middleware(OriginKeyMiddleware, shared_secret=secret)

    @app.get("/learner")
    def learner():
        return {"ok": True}

    @app.get("/readyz")
    def ready():
        return {"ok": True}

    @app.get("/client-ip")
    def client_ip(request: Request):
        return {"clientIp": trusted_registration_ip(request)}

    return TestClient(app)


def test_origin_guard_rejects_direct_learner_api_calls():
    response = guarded_client().get("/learner")

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "origin_key_required"


def test_origin_guard_accepts_shared_key_and_keeps_probe_public():
    client = guarded_client()

    assert client.get("/learner", headers={"X-ECG-Origin-Key": "deployment-secret"}).status_code == 200
    assert client.get("/readyz").status_code == 200


def test_origin_guard_is_disabled_when_not_configured():
    assert guarded_client(None).get("/learner").status_code == 200


def test_client_ip_header_is_trusted_only_with_verified_origin_key():
    client = guarded_client()

    rejected = client.get("/client-ip", headers={"X-ECG-Client-IP": "203.0.113.9"})
    accepted = client.get(
        "/client-ip",
        headers={
            "X-ECG-Origin-Key": "deployment-secret",
            "X-ECG-Client-IP": "2001:0db8:0000:0000:0000:0000:0000:0001",
        },
    )

    assert rejected.status_code == 403
    assert accepted.json() == {"clientIp": "2001:db8::1"}


def test_invalid_verified_client_ip_falls_back_to_socket_peer():
    response = guarded_client().get(
        "/client-ip",
        headers={"X-ECG-Origin-Key": "deployment-secret", "X-ECG-Client-IP": "spoofed"},
    )

    assert response.status_code == 200
    assert response.json()["clientIp"] == "testclient"


def test_production_requires_a_strong_origin_secret():
    for secret in (None, "short", "x" * 31, "x" * 32 + "\n", "x" * 32 + "\x7f"):
        settings = Settings(app_env="production", origin_shared_secret=secret)
        try:
            settings.origin_guard_secret
        except ValueError:
            pass
        else:  # pragma: no cover - assertion branch
            raise AssertionError("weak production origin secret was accepted")

    assert Settings(app_env="production", origin_shared_secret="x" * 32).origin_guard_secret == "x" * 32
