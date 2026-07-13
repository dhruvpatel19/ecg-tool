"""Narrow source-text repair for legacy PTB-XL corpus releases.

PTB-XL's database CSV is UTF-8.  An earlier corpus builder opened it as
Windows-1252, turning characters such as ``Ä`` into ``Ã„``.  Keep the
source report visible, but repair that reversible decoding error at the corpus
read boundary so already-built releases remain readable while the next rebuild
uses the correct encoding.
"""

from __future__ import annotations

from typing import Any


_MOJIBAKE_MARKERS = ("Ã", "Â", "â€")


def repair_utf8_mojibake(value: str) -> str:
    """Undo UTF-8 bytes decoded once as CP-1252 when evidence is explicit.

    The conversion is deliberately fail-closed: ordinary Unicode is returned
    unchanged, and a candidate is accepted only when it reduces known
    mojibake markers.  This avoids rewriting legitimate source text merely
    because it contains non-ASCII characters.
    """

    if not any(marker in value for marker in _MOJIBAKE_MARKERS):
        return value
    try:
        repaired = value.encode("cp1252").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value
    before = sum(value.count(marker) for marker in _MOJIBAKE_MARKERS)
    after = sum(repaired.count(marker) for marker in _MOJIBAKE_MARKERS)
    return repaired if after < before else value


def repair_packet_source_text(packet: dict[str, Any]) -> dict[str, Any]:
    """Repair visible PTB-XL report text in a freshly decoded packet."""

    ptbxl = packet.get("ptbxl")
    if isinstance(ptbxl, dict) and isinstance(ptbxl.get("report"), str):
        ptbxl["report"] = repair_utf8_mojibake(ptbxl["report"])
    teaching_points = packet.get("teaching_points")
    if isinstance(teaching_points, list):
        packet["teaching_points"] = [
            repair_utf8_mojibake(item) if isinstance(item, str) else item
            for item in teaching_points
        ]
    return packet
