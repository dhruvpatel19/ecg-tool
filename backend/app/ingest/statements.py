"""Render PTB-XL SCP codes into human-readable teaching prose.

The V1 audit found teaching points were raw ``str()`` of label/SNOMED tuples
(e.g. ``"[(320536, 100.0), ...]"``) shown verbatim to students. This module
maps SCP codes to their official descriptions (from ``scp_statements.csv``) and
produces readable statements like "Normal ECG (100%)" / "Low QRS voltages (100%)".
"""

from __future__ import annotations

import ast
import csv
from pathlib import Path
from typing import Any, Mapping

from ..source_text import repair_utf8_mojibake

# Fallbacks for the handful of high-frequency codes so prose stays readable even
# if scp_statements.csv is unavailable at runtime.
_FALLBACK_DESCRIPTIONS = {
    "NORM": "Normal ECG",
    "SR": "Sinus rhythm",
    "SBRAD": "Sinus bradycardia",
    "STACH": "Sinus tachycardia",
    "AFIB": "Atrial fibrillation",
    "AFLT": "Atrial flutter",
    "LVOLT": "Low QRS voltages",
    "IMI": "Inferior myocardial infarction",
    "AMI": "Anterior myocardial infarction",
    "ASMI": "Anteroseptal myocardial infarction",
    "LVH": "Left ventricular hypertrophy",
    "CRBBB": "Complete right bundle branch block",
    "CLBBB": "Complete left bundle branch block",
    "1AVB": "First-degree AV block",
}


def load_scp_reference(scp_csv_path: str | Path) -> dict[str, dict[str, str]]:
    """Load ``scp_statements.csv`` into ``{code: {description, class, subclass}}``."""
    reference: dict[str, dict[str, str]] = {}
    path = Path(scp_csv_path)
    if not path.exists():
        return reference
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        code_field = reader.fieldnames[0] if reader.fieldnames else ""
        for row in reader:
            code = (row.get(code_field) or "").strip()
            if not code:
                continue
            reference[code] = {
                "description": (row.get("description") or "").strip(),
                "diagnostic_class": (row.get("diagnostic_class") or "").strip(),
                "diagnostic_subclass": (row.get("diagnostic_subclass") or "").strip(),
            }
    return reference


def _describe(code: str, reference: Mapping[str, dict[str, str]]) -> str:
    entry = reference.get(code)
    if entry and entry.get("description"):
        return entry["description"]
    return _FALLBACK_DESCRIPTIONS.get(code, code)


def scp_descriptions(
    scp_codes: Mapping[str, float],
    reference: Mapping[str, dict[str, str]] | None = None,
) -> list[str]:
    """Return readable ``"<description> (<likelihood>%)"`` strings for SCP codes."""
    reference = reference or {}
    items = sorted(scp_codes.items(), key=lambda kv: (-float(kv[1] or 0), kv[0]))
    out: list[str] = []
    for code, likelihood in items:
        description = _describe(str(code), reference)
        try:
            pct = float(likelihood)
        except (TypeError, ValueError):
            pct = 0.0
        out.append(f"{description} ({pct:.0f}%)" if pct else description)
    return out


def readable_statements(
    scp_codes: Mapping[str, float],
    report: str | None,
    reference: Mapping[str, dict[str, str]] | None = None,
) -> list[str]:
    """Build the teaching-point list: readable SCP descriptions + the report text."""
    points = scp_descriptions(scp_codes, reference)
    report_text = repair_utf8_mojibake((report or "").strip())
    if report_text:
        points.append(f"PTB-XL report: {report_text}")
    return points


def is_readable(value: Any) -> bool:
    """Guard used by tests: reject raw repr-tuple / numeric-code teaching strings."""
    text = str(value)
    return not text.startswith("[(")


# --- real PTB-XL+ algorithmic statements (independent source for concordance) ---


def load_snomed_descriptions(path: str | Path) -> dict[int, dict[str, Any]]:
    """Load snomed_description.csv -> {snomed_id: {description, informative}}."""
    out: dict[int, dict[str, Any]] = {}
    p = Path(path)
    if not p.exists():
        return out
    with p.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                sid = int(row["snomed_id"])
            except (KeyError, ValueError, TypeError):
                continue
            out[sid] = {
                "description": (row.get("description") or "").strip(),
                "informative": str(row.get("informative", "")).strip().lower() in {"true", "1", "yes"},
            }
    return out


def ptbxl_plus_statements(
    snomed_ext: str | None,
    snomed_map: Mapping[int, dict[str, Any]],
    source: str = "ptbxl_plus_12sl",
) -> list[dict[str, Any]]:
    """Render a PTB-XL+ ``statements_ext_snomed`` cell into readable statements.

    Keeps only *informative* SNOMED concepts (drops hierarchy filler like
    "SNOMED CT Concept"), dedupes, and records provenance + likelihood. The result
    is an independent algorithmic read used for genuine concordance with PTB-XL labels.
    """
    if not snomed_ext or not isinstance(snomed_ext, str):
        return []
    try:
        pairs = ast.literal_eval(snomed_ext)
    except (ValueError, SyntaxError):
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in pairs if isinstance(pairs, (list, tuple)) else []:
        try:
            sid, likelihood = int(item[0]), float(item[1])
        except (TypeError, ValueError, IndexError):
            continue
        entry = snomed_map.get(sid)
        if not entry or not entry.get("informative") or not entry.get("description"):
            continue
        description = entry["description"]
        if description in seen:
            continue
        seen.add(description)
        out.append({"text": description, "source": source, "likelihood": likelihood, "snomedId": sid})
    return out


def statement_texts(statements: list[dict[str, Any]]) -> list[str]:
    """Flatten structured statements to readable strings for display/concordance."""
    return [f"{s['text']} ({s['likelihood']:.0f}%)" if s.get("likelihood") else s["text"] for s in statements]
