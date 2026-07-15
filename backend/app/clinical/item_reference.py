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


def public_item_reference(item_id: str) -> str:
    value = str(item_id or "")
    if _PUBLIC_ITEM_REFERENCE.fullmatch(value):
        return value
    digest = hmac.new(
        get_settings().adaptive_plan_context_secret.encode("utf-8"),
        f"clinical-item-reference-v1\0{value}".encode("utf-8"),
        hashlib.sha256,
    ).digest()
    encoded = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return f"ci_{encoded}"


def is_public_item_reference(value: str) -> bool:
    return bool(_PUBLIC_ITEM_REFERENCE.fullmatch(str(value or "")))
