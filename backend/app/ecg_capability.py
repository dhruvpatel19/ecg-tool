"""Opaque, owner-bound references for learner-facing ECG access.

The browser must never receive a corpus identifier and then use it as an
authorization credential.  These references contain no encoded payload: the
server can validate one only when it already knows the canonical ECG that is
allowed for the owner, mode, and learning session.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re


_PREFIX = "ec_"
_REFERENCE_RE = re.compile(r"\Aec_[A-Za-z0-9_-]{43}\Z")
_DOMAIN = b"ecg-learner-capability-v1\x00"


def _message(owner_id: str, mode: str, session_id: str, canonical_id: str) -> bytes:
    # Length-prefix every field so values containing delimiters cannot collide.
    fields = (owner_id, mode, session_id, canonical_id)
    encoded = bytearray(_DOMAIN)
    for field in fields:
        raw = str(field).encode("utf-8")
        encoded.extend(len(raw).to_bytes(4, "big"))
        encoded.extend(raw)
    return bytes(encoded)


def issue_ecg_capability(
    secret: str,
    owner_id: str,
    mode: str,
    session_id: str,
    canonical_id: str,
) -> str:
    """Return a deterministic, payload-free reference for one allowed ECG."""

    digest = hmac.new(
        str(secret).encode("utf-8"),
        _message(owner_id, mode, session_id, canonical_id),
        hashlib.sha256,
    ).digest()
    token = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return f"{_PREFIX}{token}"


def is_ecg_capability(reference: object) -> bool:
    """Return whether ``reference`` has the bounded public capability shape."""

    return isinstance(reference, str) and _REFERENCE_RE.fullmatch(reference) is not None


def matches_ecg_capability(
    reference: object,
    secret: str,
    owner_id: str,
    mode: str,
    session_id: str,
    canonical_id: str,
) -> bool:
    """Constant-time validation against server-owned canonical state."""

    if not is_ecg_capability(reference):
        return False
    expected = issue_ecg_capability(
        secret, owner_id, mode, session_id, canonical_id
    )
    return hmac.compare_digest(str(reference), expected)


__all__ = [
    "is_ecg_capability",
    "issue_ecg_capability",
    "matches_ecg_capability",
]
