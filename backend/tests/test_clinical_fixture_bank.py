"""Synthetic fixture content remains harness-only, never learner-serving."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.clinical.fixture_items import FIXTURE_ITEMS, FIXTURE_PACKETS
from app.clinical.harness import run_harness
from app.main import app


@pytest.mark.parametrize("item", FIXTURE_ITEMS, ids=lambda it: it.item_id)
def test_fixture_items_pass_harness(item):
    packet = FIXTURE_PACKETS.get(item.ecg_id)
    assert packet is not None, f"no fixture packet for {item.ecg_id}"
    prior = FIXTURE_PACKETS.get(item.prior_ecg_id) if item.prior_ecg_id else None
    report = run_harness(item, packet, prior)
    assert report.passed, (
        f"{item.item_id} failed: " + "; ".join(f"{c.check}: {c.messages}" for c in report.hard_stop_failures)
    )


def test_production_bank_contains_no_fixture_or_seed_items():
    from app.main import clinical_item_store

    counts = clinical_item_store.count_by_status()
    assert counts.get("harness_pass", 0) >= 20
    assert counts.get("vetted", 0) == 0
    for item in clinical_item_store.iter_items():
        assert not item.item_id.startswith(("fixture-", "seed-", "fx-"))
        assert not item.ecg_id.startswith(("fixture-", "seed-"))


def test_fixture_waveform_is_not_publicly_served() -> None:
    fixture_id = FIXTURE_ITEMS[0].ecg_id
    response = TestClient(app).get(f"/cases/{fixture_id}/waveform?leads=II&maxPoints=300")
    assert response.status_code == 404
