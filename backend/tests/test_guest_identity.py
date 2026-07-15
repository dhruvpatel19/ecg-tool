from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.guest_identity import (
    GUEST_COOKIE_NAME,
    GuestIdentityMiddleware,
    current_claimable_guest_learner,
    current_guest_learner,
)


def _guest_test_app(app_env: str = "development") -> FastAPI:
    app = FastAPI()
    app.add_middleware(GuestIdentityMiddleware, app_env=app_env)

    @app.get("/whoami")
    def whoami() -> dict[str, str | None]:
        return {
            "guestId": current_guest_learner(),
            "claimableGuestId": current_claimable_guest_learner(),
        }

    @app.get("/health")
    def health() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/livez")
    def livez() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/readyz")
    def readyz() -> dict[str, bool]:
        return {"ok": True}

    return app


def test_deployed_middleware_never_manufactures_guest_identity_or_cookie() -> None:
    with TestClient(_guest_test_app()) as client:
        response = client.get("/whoami")
        assert response.status_code == 200
        assert response.json() == {"guestId": None, "claimableGuestId": None}
        assert response.headers.get("set-cookie") is None
        assert client.cookies.get(GUEST_COOKIE_NAME) is None


def test_valid_preexisting_cookie_is_exposed_only_for_legacy_migration() -> None:
    legacy_id = f"g_{'a' * 24}"
    with TestClient(_guest_test_app()) as client:
        client.cookies.set(GUEST_COOKIE_NAME, legacy_id)
        response = client.get("/whoami")
        assert response.json() == {
            "guestId": legacy_id,
            "claimableGuestId": legacy_id,
        }
        # Reading a migration identity never refreshes its lifetime.
        assert response.headers.get("set-cookie") is None


def test_invalid_guest_cookie_is_ignored_and_never_rotated() -> None:
    with TestClient(_guest_test_app()) as client:
        client.cookies.set(GUEST_COOKIE_NAME, "g_known-or-malformed")
        response = client.get("/whoami")
        assert response.status_code == 200
        assert response.json() == {"guestId": None, "claimableGuestId": None}
        assert response.headers.get("set-cookie") is None


def test_exact_test_environment_retains_internal_demo_fixture_without_cookie() -> None:
    with TestClient(_guest_test_app("test")) as client:
        response = client.get("/whoami")
        assert response.json() == {
            "guestId": "demo",
            "claimableGuestId": "demo",
        }
        assert response.headers.get("set-cookie") is None


def test_public_probes_never_create_guest_cookies() -> None:
    with TestClient(_guest_test_app()) as client:
        for path in ("/health", "/livez", "/readyz"):
            response = client.get(path)
            assert response.status_code == 200
            assert response.headers.get("set-cookie") is None
        assert client.cookies.get(GUEST_COOKIE_NAME) is None
