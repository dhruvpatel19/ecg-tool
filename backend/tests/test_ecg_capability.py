from __future__ import annotations

from app.ecg_capability import (
    is_ecg_capability,
    issue_ecg_capability,
    matches_ecg_capability,
)


SECRET = "test-ecg-capability-secret-with-at-least-thirty-two-characters"


def test_capability_is_payload_free_deterministic_and_bounded() -> None:
    canonical = "ptbxl/records500/01000/01234_hr"
    first = issue_ecg_capability(
        SECRET, "learner-a", "training", "campaign-a", canonical
    )
    second = issue_ecg_capability(
        SECRET, "learner-a", "training", "campaign-a", canonical
    )

    assert first == second
    assert is_ecg_capability(first)
    assert len(first) == 46
    assert canonical not in first
    assert "/" not in first


def test_capability_is_bound_to_every_authorization_dimension() -> None:
    reference = issue_ecg_capability(
        SECRET, "learner-a", "rapid", "round-a", "ecg-a"
    )
    assert matches_ecg_capability(
        reference, SECRET, "learner-a", "rapid", "round-a", "ecg-a"
    )
    for candidate in (
        ("learner-b", "rapid", "round-a", "ecg-a"),
        ("learner-a", "training", "round-a", "ecg-a"),
        ("learner-a", "rapid", "round-b", "ecg-a"),
        ("learner-a", "rapid", "round-a", "ecg-b"),
    ):
        assert not matches_ecg_capability(reference, SECRET, *candidate)


def test_malformed_references_fail_closed() -> None:
    for value in (
        None,
        "",
        "ec_short",
        "ec_" + "a" * 42,
        "ec_" + "a" * 44,
        "ec_" + "!" * 43,
        "ptbxl-123",
    ):
        assert not is_ecg_capability(value)
        assert not matches_ecg_capability(
            value, SECRET, "learner-a", "rapid", "round-a", "ecg-a"
        )
