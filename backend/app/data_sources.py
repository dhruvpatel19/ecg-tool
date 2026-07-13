"""Fixture-fallback case repository + shared case helpers.

The canonical data path is the built corpus (see ``corpus_repository``/``store``).
This module provides the keyless **fixture fallback** used when no corpus is built,
plus ``case_summary`` (the shared summary shape) and ``load_case_signal`` (waveform
decoding for fixture/raw records).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import Settings
from .fixtures import build_fixture_cases
from .schemas import LEADS


def waveform_window_from_case(
    case: dict[str, Any],
    leads: list[str] | None = None,
    start: float = 0,
    end: float | None = None,
    max_points: int = 1200,
) -> dict[str, Any]:
    """Render a bounded waveform window from an inline/authored case packet.

    This is also used when the production corpus is active but a clearly labeled
    fixture Clinical item is requested. Keeping that path explicit prevents an
    alphanumeric id such as ``fixture-af-001`` from being normalized to real PTB
    record ``1`` by the sharded numeric waveform store.
    """
    waveform = case["waveform"]
    fs = int(waveform["sampling_frequency"])
    duration = float(waveform["duration_sec"])
    end = duration if end is None else min(end, duration)
    start = max(0, min(start, end))
    selected_leads = [lead for lead in (leads or LEADS) if lead in LEADS]
    data = load_case_signal(case, selected_leads)
    start_idx, end_idx = int(start * fs), int(end * fs)
    step = max(1, max(1, end_idx - start_idx) // max_points)
    indices = list(range(start_idx, end_idx, step))
    times = [round(idx / fs, 3) for idx in indices]
    return {
        "caseId": case["case_id"],
        "samplingFrequency": fs,
        "durationSec": duration,
        "startSec": start,
        "endSec": end,
        "leads": [
            {
                "lead": lead,
                "points": [
                    {"timeSec": time, "amplitudeMv": values[index]}
                    for time, index in zip(times, indices)
                    if index < len(values)
                ],
            }
            for lead, values in data.items()
            if lead in selected_leads
        ],
    }


class CaseRepository:
    """In-memory repository over synthetic fixtures — the no-corpus fallback."""

    def __init__(self, settings: Settings, limit: int | None = None):
        self.settings = settings
        self.limit = settings.case_limit if limit is None else limit
        self.cases: dict[str, dict[str, Any]] = {}
        self.status: dict[str, Any] = {}
        self.build_index(limit=self.limit)

    def build_index(self, limit: int | None = None) -> dict[str, Any]:
        limit = self.limit if limit is None else limit
        if self.settings.require_real_data:
            raise RuntimeError(
                "ECG_REQUIRE_REAL_DATA=1 but no built corpus was found. "
                "Build one with: python scripts/build_corpus.py --limit 0 --out data/ecg_corpus"
            )
        cases = build_fixture_cases()
        if limit and limit > 0:
            cases = cases[:limit]
        self.cases = {case["case_id"]: case for case in cases}
        self.status = {
            "active_source": "fixture",
            "fixture_fallback": True,
            "fixture_warning": "Synthetic demo waveforms are non-clinical; build a corpus for real PTB-XL data.",
            "case_count": len(self.cases),
            "case_limit": limit,
            "student_facing_count": len([c for c in self.cases.values() if c["teaching_tier"] in {"A", "B"}]),
            "data_readiness": "fixture_degraded",
            "requires_real_data": self.settings.require_real_data,
        }
        return self.status

    def list_cases(
        self, concept: str | None = None, include_uncertain: bool = False, query: str | None = None,
        limit: int = 200, offset: int = 0,
    ) -> list[dict[str, Any]]:
        cases = list(self.cases.values())
        if not include_uncertain:
            cases = [case for case in cases if case["teaching_tier"] in {"A", "B"}]
        if concept:
            cases = [c for c in cases if (c["concept_confidence"].get(concept) or {}).get("tier") in {"A", "B"}]
        if query:
            lowered = query.lower()
            cases = [
                c
                for c in cases
                if lowered in c["case_id"].lower()
                or lowered in c.get("display_id", "").lower()
                or lowered in (c.get("ptbxl", {}).get("report") or "").lower()
            ]
        ordered = sorted(cases, key=lambda item: item["case_id"])
        return [case_summary(case) for case in ordered[offset:offset + limit]]

    def get_case(self, case_id: str) -> dict[str, Any] | None:
        return self.cases.get(case_id)

    def candidates(self, concept_id: str | None = None) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for case in self.cases.values():
            if case["teaching_tier"] not in {"A", "B"}:
                continue
            if concept_id and (case["concept_confidence"].get(concept_id) or {}).get("tier") not in {"A", "B"}:
                continue
            item = {
                "case_id": case["case_id"],
                "teaching_tier": case["teaching_tier"],
                "source": case.get("source", "unknown"),
                "supported_objectives": case.get("supported_objectives", []),
            }
            if concept_id:
                item["concept_tier"] = (case["concept_confidence"].get(concept_id) or {}).get("tier")
            out.append(item)
        return out

    def concept_ab_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for case in self.cases.values():
            for concept_id, confidence in (case.get("concept_confidence") or {}).items():
                if confidence.get("tier") in {"A", "B"}:
                    counts[concept_id] = counts.get(concept_id, 0) + 1
        return counts

    def group_reliable_count(self, concept_ids: list[str]) -> int:
        wanted = set(concept_ids)
        return sum(
            1
            for case in self.cases.values()
            if case["teaching_tier"] in {"A", "B"}
            and any((case["concept_confidence"].get(cid) or {}).get("tier") in {"A", "B"} for cid in wanted)
        )

    def get_waveform_window(
        self,
        case_id: str,
        leads: list[str] | None = None,
        start: float = 0,
        end: float | None = None,
        max_points: int = 1200,
    ) -> dict[str, Any] | None:
        case = self.get_case(case_id)
        if not case:
            return None
        return waveform_window_from_case(case, leads, start, end, max_points)


def case_summary(case: dict[str, Any]) -> dict[str, Any]:
    # Lean shape {id, tier, score} so list and detail summaries agree.
    top_concepts = sorted(
        [
            {"id": concept_id, "tier": confidence.get("tier"), "score": confidence.get("score", 0)}
            for concept_id, confidence in case["concept_confidence"].items()
            if confidence["tier"] in {"A", "B"}
        ],
        key=lambda item: item["score"],
        reverse=True,
    )[:6]
    return {
        "caseId": case["case_id"],
        "displayId": case.get("display_id", case["case_id"]),
        "source": case.get("source", "unknown"),
        "teachingTier": case["teaching_tier"],
        "clinicalStem": case.get("clinical_stem", ""),
        "topConcepts": top_concepts,
        "report": case.get("ptbxl", {}).get("report", ""),
        "studentFacing": case["teaching_tier"] in {"A", "B"},
    }


def normalize_lead_name(value: Any) -> str:
    return "".join(char.lower() for char in str(value) if char.isalnum())


def load_case_signal(case: dict[str, Any], leads: list[str]) -> dict[str, list[float]]:
    """Decode a case's lead signals: inline fixture data, a JSON waveform, or a WFDB record."""
    if case.get("waveform_data"):
        return {lead: case["waveform_data"][lead] for lead in leads if lead in case["waveform_data"]}
    path = (case.get("waveform") or {}).get("path")
    if path:
        record = Path(path)
        if record.suffix.lower() == ".json" and record.exists():
            payload = json.loads(record.read_text(encoding="utf-8"))
            signal = payload.get("signal") or payload.get("waveform_data") or {}
            return {lead: [round(float(v), 4) for v in signal.get(lead, [])] for lead in leads if lead in signal}
        try:
            import wfdb  # type: ignore

            signal, fields = wfdb.rdsamp(str(record.with_suffix("")))
            name_index = {normalize_lead_name(n): i for i, n in enumerate(fields.get("sig_name", LEADS))}
            return {
                lead: [round(float(row[name_index[normalize_lead_name(lead)]]), 4) for row in signal]
                for lead in leads
                if normalize_lead_name(lead) in name_index
            }
        except Exception:
            pass
    return {lead: [] for lead in leads}
