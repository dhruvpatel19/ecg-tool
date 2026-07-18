from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from app.clinical.schemas import ClinicalCaseItem
from app.store.clinical_item_store import ClinicalItemStore


def _item(
    item_id: str,
    ecg_id: str,
    *,
    prior_ecg_id: str | None = None,
) -> ClinicalCaseItem:
    return ClinicalCaseItem(
        item_id=item_id,
        ecg_id=ecg_id,
        prior_ecg_id=prior_ecg_id,
        situation="clinic",
        question_type="mcq",
        acuity_tier="low",
        stem="A learner-facing clinical vignette.",
        prompt="Choose the best interpretation.",
        validation_status="harness_pass",
    )


def test_release_readiness_accepts_unique_primary_and_prior_ecgs() -> None:
    store = ClinicalItemStore(":memory:")
    store.replace_items_atomically(
        [
            _item("ptb-item-a", "100", prior_ecg_id="99"),
            _item("ptb-item-b", "101", prior_ecg_id="98"),
        ]
    )

    assert store.release_readiness(2) == (True, "ready")


def test_memory_store_serializes_concurrent_readers() -> None:
    store = ClinicalItemStore(":memory:")
    item = _item("ptb-concurrent-item", "100")
    store.upsert_item(item)
    workers = 8
    start = Barrier(workers)

    def read_many() -> None:
        start.wait()
        for _ in range(250):
            loaded = store.get_item(item.item_id)
            assert loaded is not None
            assert loaded.item_id == item.item_id

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(lambda _: read_many(), range(workers)))


@pytest.mark.parametrize(
    "items",
    [
        [
            _item("ptb-item-a", "100", prior_ecg_id="99"),
            _item("ptb-item-b", "99"),
        ],
        [
            _item("ptb-item-a", "100", prior_ecg_id="99"),
            _item("ptb-item-b", "101", prior_ecg_id="99"),
        ],
        [_item("ptb-item-a", "100", prior_ecg_id="100")],
    ],
    ids=["prior_reused_as_primary", "prior_reused_as_prior", "self_pair"],
)
def test_release_readiness_rejects_reuse_across_all_ecg_slots(
    items: list[ClinicalCaseItem],
) -> None:
    store = ClinicalItemStore(":memory:")
    store.replace_items_atomically(items)

    assert store.release_readiness(len(items)) == (
        False,
        "clinical_bank_reuses_ecg",
    )
