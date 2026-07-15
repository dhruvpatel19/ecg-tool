from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.mark.parametrize("path", ["/auth/login", "/auth/register"])
def test_auth_validation_never_reflects_submitted_password(path: str) -> None:
    secret = f"NEVER-REFLECT-{uuid.uuid4().hex}-" + "x" * 300
    with TestClient(app) as client:
        response = client.post(
            path,
            json={"username": "student", "password": secret},
        )

    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"
    assert secret not in response.text
    assert response.json()["detail"][0]["loc"] == ["body", "password"]
    assert "input" not in response.json()["detail"][0]


def test_malformed_auth_json_does_not_reflect_request_fragment() -> None:
    secret = f"MALFORMED-NEVER-REFLECT-{uuid.uuid4().hex}"
    with TestClient(app) as client:
        response = client.post(
            "/auth/login",
            content=f'{{"username":"student","password":"{secret}"',
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"
    assert secret not in response.text
    assert "input" not in response.text


def test_non_auth_validation_uses_the_same_privacy_safe_contract() -> None:
    with TestClient(app) as client:
        response = client.get("/cases", params={"limit": 5001})

    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"
    error = response.json()["detail"][0]
    assert error["loc"] == ["query", "limit"]
    assert error["type"] == "less_than_equal"
    assert "input" not in error
