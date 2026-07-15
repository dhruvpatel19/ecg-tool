from __future__ import annotations

import re
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app, clinical_item_store


PASSWORD = "Boundary-Audit-Pw-9!"


def _register(client: TestClient, prefix: str) -> None:
    response = client.post(
        "/auth/register",
        json={
            "username": f"{prefix}_{uuid.uuid4().hex[:10]}",
            "password": PASSWORD,
        },
    )
    assert response.status_code == 200, response.text


@pytest.mark.parametrize("authorization", ["Bearer  ", "bearer     "])
def test_whitespace_only_bearer_is_an_invalid_session_not_a_server_error(
    authorization: str,
) -> None:
    with TestClient(app) as client:
        response = client.get(
            "/auth/me", headers={"Authorization": authorization}
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid or expired session"


def test_clinical_precommit_handles_do_not_disclose_authored_diagnosis_ids() -> None:
    with TestClient(app) as client:
        _register(client, "opaque_clinical")
        response = client.post(
            "/clinical/shift/start",
            json={
                "lane": "ed",
                "tier": "learn",
                "length": 1,
                "focus": "supraventricular_tachycardia",
                "subskill": "apply_in_context",
            },
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        session_id = payload["session"]["sessionId"]
        public_id = payload["next"]["itemId"]
        assert re.fullmatch(r"ci_[A-Za-z0-9_-]{43}", public_id)
        assert payload["session"]["pendingItemId"] == public_id
        assert payload["next"]["item"]["item_id"] == public_id

        authored = clinical_item_store.get_item(public_id)
        assert authored is not None
        assert authored.item_id != public_id
        assert authored.item_id not in response.text
        assert "-svt-" not in response.text.casefold()

        # Even an internal id learned out-of-band is not accepted as the
        # browser's current item capability, and the error does not echo it.
        raw_probe = client.post(
            f"/clinical/shift/{session_id}/context",
            json={
                "itemId": authored.item_id,
                "answer": {
                    "firstLookFinding": "uncertain",
                    "firstLookConfidence": 3,
                },
            },
        )
        assert raw_probe.status_code == 409
        assert raw_probe.json()["detail"]["pendingItemId"] == public_id
        assert authored.item_id not in raw_probe.text

        committed_first_look = client.post(
            f"/clinical/shift/{session_id}/context",
            json={
                "itemId": public_id,
                "answer": {
                    "firstLookFinding": "uncertain",
                    "firstLookConfidence": 3,
                },
            },
        )
        assert committed_first_look.status_code == 200, committed_first_look.text
        assert committed_first_look.json()["itemId"] == public_id
        assert committed_first_look.json()["item"]["item_id"] == public_id
