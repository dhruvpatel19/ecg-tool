from __future__ import annotations

import uuid
from collections.abc import Iterable

from fastapi.testclient import TestClient

from app.adaptive import next_case
from app.foundations_case_pools import (
    foundations_case_pool_summary,
    preferred_foundations_case_ids,
)
from app.main import app, repo, store


_PASSWORD = "Foundations-private-pool!"
_ROLE_SLOTS = {
    "modeled": "foundations:S10:modeled",
    "guided": "foundations:S11:guided",
    "immediate_integration": "foundations:S12:integration",
    "equivalent_retry": "foundations:equivalent-retry",
    "component_contrast": "foundations:S5:component",
}
_IDENTITY_KEYS = {
    "caseId",
    "case_id",
    "ecgId",
    "ecg_id",
    "recordId",
    "record_id",
    "sourceRecordId",
    "source_record_id",
    "path",
    "filename",
    "filename_lr",
    "filename_hr",
    "uri",
    "gcs_uri",
}


def _register(client: TestClient, prefix: str) -> dict:
    username = f"{prefix[:18]}_{uuid.uuid4().hex[:10]}"
    response = client.post(
        "/auth/register",
        json={
            "username": username,
            "password": _PASSWORD,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["user"]


def _identity_values(value: object) -> Iterable[str]:
    if isinstance(value, list):
        for item in value:
            yield from _identity_values(item)
        return
    if not isinstance(value, dict):
        return
    for key, item in value.items():
        if key in _IDENTITY_KEYS and item is not None:
            yield str(item)
        yield from _identity_values(item)


def _allocated_ids() -> set[str]:
    allocated: set[str] = set()
    for slot in _ROLE_SLOTS.values():
        order = preferred_foundations_case_ids(
            slot,
            learner_id="allocation-audit",
            secret="allocation-audit-secret",
        )
        assert order is not None
        allocated.update(order)
    return allocated


def test_private_case_roles_have_24_unique_cases_and_stable_learner_order() -> None:
    summary = foundations_case_pool_summary()
    counts = {str(row["role"]): int(row["count"]) for row in summary}
    assert counts == {
        "modeled": 2,
        "guided": 3,
        "immediate_integration": 2,
        "equivalent_retry": 4,
        "component_contrast": 13,
    }
    assert sum(counts.values()) == 24

    allocated: set[str] = set()
    for role, slot in _ROLE_SLOTS.items():
        first = preferred_foundations_case_ids(
            slot,
            learner_id="learner-a",
            secret="unit-secret",
        )
        replay = preferred_foundations_case_ids(
            slot,
            learner_id="learner-a",
            secret="unit-secret",
        )
        assert first == replay
        assert first is not None
        assert len(first) == counts[role]
        assert len(set(first)) == len(first)
        allocated.update(first)

    assert len(allocated) == 24
    assert all(repo.get_case(case_id) is not None for case_id in allocated)
    assert preferred_foundations_case_ids(
        "foundations:S5:component",
        learner_id="learner-a",
        secret="unit-secret",
    ) != preferred_foundations_case_ids(
        "foundations:S5:component",
        learner_id="learner-b",
        secret="unit-secret",
    )
    assert preferred_foundations_case_ids(
        None,
        learner_id="learner-a",
        secret="unit-secret",
    ) is None


def test_adaptive_selector_prefers_an_eligible_private_case_and_falls_back() -> None:
    preferred = next_case(
        repo,
        store,
        learner_id=f"pool-preferred-{uuid.uuid4().hex}",
        concept_id="normal_ecg",
        preferred_case_ids=("21",),
    )
    assert preferred["case"] is not None
    assert preferred["case"]["caseId"] == "21"

    fallback = next_case(
        repo,
        store,
        learner_id=f"pool-fallback-{uuid.uuid4().hex}",
        concept_id="normal_ecg",
        # This allocated tracing does not satisfy the requested Normal ECG
        # concept. A preference must never bypass the existing eligibility gate.
        preferred_case_ids=("279",),
    )
    assert fallback["case"] is not None
    assert fallback["case"]["caseId"] != "279"


def test_tutorial_rejects_unknown_foundations_case_pool_slot() -> None:
    with TestClient(app) as client:
        _register(client, "foundation_pool_invalid")
        response = client.get(
            "/tutorials/orientation",
            params={"casePoolSlot": "foundations:S99:not-real"},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == {
        "code": "invalid_foundations_case_pool",
        "message": "The requested Foundations case slot is not available.",
    }


def test_foundations_pool_response_is_opaque_and_forced_to_contrast_only() -> None:
    allocated_ids = _allocated_ids()
    with TestClient(app) as client:
        user = _register(client, "foundation_pool_private")
        response = client.get(
            "/tutorials/orientation",
            params={
                "concept": "sinus_rhythm",
                "casePoolSlot": "foundations:S5:component",
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        with store.connect() as conn:
            event = conn.execute(
                "SELECT ecg_id FROM learner_events WHERE owner_id = ? "
                "AND mode = 'guided' AND session_id = ? "
                "AND event_type = 'item_presented' ORDER BY occurred_at DESC LIMIT 1",
                (user["userId"], "tutorial:orientation"),
            ).fetchone()

    assert event is not None
    canonical_id = str(event[0])
    assert canonical_id in allocated_ids
    assert body["selection"]["preferredCasePoolMatched"] is True
    assert body["selection"]["reason"].startswith(
        "A governed Foundations contrast ECG"
    )
    assert body["guidedEligibility"]["eligible"] is False
    assert body["guidedEligibility"]["missingRequirementCount"] >= 1
    assert "governed teaching contrast" in body["guidedEligibility"]["message"]
    assert "authored action" in body["guidedEligibility"]["message"]
    assert body["assessmentPrivacy"] == {
        "opaqueEcgReference": True,
        "answerFieldsWithheldUntilCommit": True,
        "sourceRecordIdentityWithheld": True,
    }

    identity_values = set(_identity_values(body))
    assert canonical_id not in identity_values
    assert identity_values.isdisjoint(allocated_ids)
    assert body["recommendedCase"]["caseId"].startswith("ec_")
    assert body["recommendedPacket"]["case_id"] == body["recommendedCase"]["caseId"]
