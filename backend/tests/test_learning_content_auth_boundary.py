from __future__ import annotations

from types import SimpleNamespace
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.main as main_module
from app.auth import PRODUCTION_SESSION_COOKIE_NAME, SESSION_COOKIE_NAME
from app.main import app, store


PASSWORD = "Sup3r-Secret-Pw!"


def _register(client: TestClient, prefix: str) -> dict[str, object]:
    username = f"{prefix}_{uuid.uuid4().hex[:10]}"
    response = client.post(
        "/auth/register",
        json={"username": username, "password": PASSWORD, "displayName": prefix},
    )
    assert response.status_code == 200, response.text
    return response.json()["user"]


def _verify_account(user_id: str) -> None:
    now = "2026-07-14T12:00:00+00:00"
    with store.connect() as conn:
        conn.execute(
            "UPDATE users SET email_normalized = ?, email_verified_at = ? WHERE user_id = ?",
            (f"{uuid.uuid4().hex}@example.test", now, user_id),
        )


def _first_case_id() -> str:
    # APP_ENV=test intentionally retains its deterministic internal fixture so
    # the corpus test suite can obtain one valid audited id before exercising
    # the deployed account boundary below.
    with TestClient(app) as client:
        response = client.get("/cases?limit=1")
    assert response.status_code == 200, response.text
    return str(response.json()[0]["caseId"])


def _content_paths(case_id: str) -> list[str]:
    return [
        "/dataset/status",
        "/concepts",
        "/objectives",
        "/cases?limit=1",
        f"/cases/{case_id}",
        f"/cases/{case_id}/packet",
        f"/cases/{case_id}/waveform?leads=II&maxPoints=100",
        f"/cases/{case_id}/ptbxl-plus",
        "/tutorials",
        "/training/campaigns/pool?conceptId=normal_ecg&subskill=recognize",
        "/clinical/bank/status",
        "/clinical/bank/coverage",
    ]


def test_production_content_routes_reject_anonymous_and_legacy_guest_only(
    monkeypatch,
) -> None:
    case_id = _first_case_id()
    monkeypatch.setattr(main_module, "settings", SimpleNamespace(app_env="production"))

    for cookie_header in (None, f"ecg_guest=g_{'a' * 24}"):
        headers = {"Cookie": cookie_header} if cookie_header else {}
        with TestClient(app, base_url="https://learn.example.test") as client:
            for path in [*_content_paths(case_id), "/auth/learning-access"]:
                response = client.get(path, headers=headers)
                assert response.status_code == 401, (path, response.text)
                assert response.headers.get("set-cookie") is None


def test_production_content_routes_require_verified_email(monkeypatch) -> None:
    case_id = _first_case_id()
    with TestClient(app, base_url="https://learn.example.test") as client:
        _register(client, "content_pending")
        monkeypatch.setattr(main_module, "settings", SimpleNamespace(app_env="production"))

        for path in [*_content_paths(case_id), "/auth/learning-access"]:
            response = client.get(path)
            assert response.status_code == 403, (path, response.text)
            assert response.json()["detail"]["code"] == "email_upgrade_required"


def test_verified_account_can_open_every_content_surface_without_shared_caching(
    monkeypatch,
) -> None:
    case_id = _first_case_id()
    with TestClient(app, base_url="https://learn.example.test") as client:
        user = _register(client, "content_verified")
        _verify_account(str(user["userId"]))
        monkeypatch.setattr(main_module, "settings", SimpleNamespace(app_env="production"))

        for path in _content_paths(case_id):
            response = client.get(path)
            assert response.status_code == 200, (path, response.text)
            assert response.headers["cache-control"] == "private, no-store"
            assert "Cookie" in response.headers["vary"]

        access = client.get("/auth/learning-access")
        assert access.status_code == 204, access.text
        assert access.content == b""
        assert access.headers["cache-control"] == "private, no-store"


def test_production_host_cookie_alone_reaches_learning_access_and_content(
    monkeypatch,
) -> None:
    with TestClient(app, base_url="https://learn.example.test") as registration:
        user = _register(registration, "content_host_cookie")
        token = registration.cookies.get(SESSION_COOKIE_NAME)
    assert token
    _verify_account(str(user["userId"]))
    monkeypatch.setattr(main_module, "settings", SimpleNamespace(app_env="production"))

    # The imported test app was constructed in APP_ENV=test. Wrap that exact
    # route graph with the production cookie translator so this regression test
    # exercises the real dependencies using only the browser's __Host- cookie.
    production_wrapper = FastAPI()
    production_wrapper.mount("/", app)
    production_wrapper.add_middleware(
        main_module.SessionCookieMigrationMiddleware,
        app_env="production",
        resolver=main_module.auth_service.resolve,
    )
    headers = {"Cookie": f"{PRODUCTION_SESSION_COOKIE_NAME}={token}"}
    with TestClient(
        production_wrapper, base_url="https://learn.example.test"
    ) as client:
        access = client.get("/auth/learning-access", headers=headers)
        cases = client.get("/cases?limit=1", headers=headers)

    assert access.status_code == 204, access.text
    assert cases.status_code == 200, cases.text
    assert cases.headers["cache-control"] == "private, no-store"


def test_public_probes_and_stateless_viewer_math_remain_public(monkeypatch) -> None:
    monkeypatch.setattr(main_module, "settings", SimpleNamespace(app_env="production"))
    with TestClient(app, base_url="https://learn.example.test") as client:
        health = client.get("/health")
        coordinate = client.post(
            "/viewer/map-point",
            json={"x": 10, "y": 10, "width": 100, "height": 100},
        )
        live = client.get("/livez")
        ready = client.get("/readyz")

    assert health.status_code == 200
    assert coordinate.status_code == 200
    assert live.status_code == 200
    assert ready.status_code in {200, 503}
    assert all(
        response.headers.get("set-cookie") is None
        for response in (health, coordinate, live, ready)
    )
