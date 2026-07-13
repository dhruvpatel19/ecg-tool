from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.guest_identity import GUEST_COOKIE_NAME, GuestIdentityMiddleware, current_guest_learner


def _guest_test_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(GuestIdentityMiddleware, app_env="development")
    notes: dict[str, str] = {}

    @app.get("/whoami")
    def whoami() -> dict[str, str | None]:
        guest_id = current_guest_learner()
        return {"guestId": guest_id, "note": notes.get(guest_id)}

    @app.post("/note/{value}")
    def save_note(value: str) -> dict[str, str]:
        guest_id = current_guest_learner()
        notes[guest_id] = value
        return {"guestId": guest_id}

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


def test_guest_cookie_is_private_stable_httponly_and_time_bounded() -> None:
    app = _guest_test_app()
    with TestClient(app) as first, TestClient(app) as second:
        first_identity = first.get("/whoami")
        second_identity = second.get("/whoami")
        first_id = first_identity.json()["guestId"]
        second_id = second_identity.json()["guestId"]
        assert first_id.startswith("g_") and second_id.startswith("g_")
        assert first_id != second_id

        set_cookie = first_identity.headers["set-cookie"].lower()
        assert f"{GUEST_COOKIE_NAME}=" in set_cookie
        assert "httponly" in set_cookie
        assert "samesite=lax" in set_cookie
        assert "max-age=2592000" in set_cookie

        assert first.post("/note/first-private-draft").json()["guestId"] == first_id
        assert first.get("/whoami").json() == {"guestId": first_id, "note": "first-private-draft"}
        assert second.get("/whoami").json() == {"guestId": second_id, "note": None}


def test_invalid_guest_cookie_is_rotated_instead_of_selecting_an_owner() -> None:
    app = _guest_test_app()
    with TestClient(app) as client:
        client.cookies.set(GUEST_COOKIE_NAME, "g_known-or-malformed")
        response = client.get("/whoami")
        assert response.status_code == 200
        assert response.json()["guestId"] != "g_known-or-malformed"
        assert response.headers.get("set-cookie")


def test_public_probes_never_create_guest_cookies() -> None:
    app = _guest_test_app()
    with TestClient(app) as client:
        for path in ("/health", "/livez", "/readyz"):
            response = client.get(path)
            assert response.status_code == 200
            assert response.headers.get("set-cookie") is None
        assert client.cookies.get(GUEST_COOKIE_NAME) is None
