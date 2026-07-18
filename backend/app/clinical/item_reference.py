"""Opaque learner-facing handles for authored Clinical items.

The internal item ids are useful authoring keys, but many contain the finding
name (for example ``...-svt-...``).  They must never double as a pre-commit
transport identifier.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re

from ..config import get_settings


_PUBLIC_ITEM_REFERENCE = re.compile(r"^ci_[A-Za-z0-9_-]{43}$")
_PUBLIC_OPTION_REFERENCE = re.compile(r"^co_[A-Za-z0-9_-]{43}$")


def _public_reference(prefix: str, purpose: str, *parts: str) -> str:
    digest = hmac.new(
        get_settings().adaptive_plan_context_secret.encode("utf-8"),
        (purpose + "\0" + "\0".join(str(part or "") for part in parts)).encode("utf-8"),
        hashlib.sha256,
    ).digest()
    encoded = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return f"{prefix}_{encoded}"


def public_item_reference(
    item_id: str,
    *,
    learner_id: str,
    session_id: str,
) -> str:
    """Issue an opaque Clinical item handle bound to one owner session.

    The canonical authoring id is intentionally not recoverable from the
    handle.  Including both owner and session prevents a shared handle from
    becoming a cross-learner answer-position key.
    """

    if not str(learner_id or "") or not str(session_id or ""):
        raise ValueError("Clinical item references require learner and session scope")
    return _public_reference(
        "ci",
        "clinical-item-reference-v2",
        learner_id,
        session_id,
        item_id,
    )


def public_option_reference(
    item_id: str,
    option_id: str,
    *,
    learner_id: str,
    session_id: str,
) -> str:
    """Issue an owner/session/item-bound handle for one selectable option."""

    if not str(learner_id or "") or not str(session_id or ""):
        raise ValueError("Clinical option references require learner and session scope")
    return _public_reference(
        "co",
        "clinical-option-reference-v1",
        learner_id,
        session_id,
        item_id,
        option_id,
    )


def legacy_public_item_reference(item_id: str) -> str:
    """Recreate the retired global v1 handle for durable-session migration only."""

    return _public_reference("ci", "clinical-item-reference-v1", item_id)


def is_public_item_reference(value: str) -> bool:
    return bool(_PUBLIC_ITEM_REFERENCE.fullmatch(str(value or "")))


def is_public_option_reference(value: str) -> bool:
    return bool(_PUBLIC_OPTION_REFERENCE.fullmatch(str(value or "")))
