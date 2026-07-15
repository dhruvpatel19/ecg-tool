from __future__ import annotations

from copy import deepcopy
from typing import Any

from fastapi.testclient import TestClient

import app.main as main_module
from app.data_sources import case_summary
from app.fixtures import build_fixture_cases
from app.ingest.leipzig import SURFACE_LEADS, WindowSpec, build_window_packet


class FakeRepo:
    def __init__(self, cases: list[dict[str, Any]]):
        self.cases = {str(case["case_id"]): case for case in cases}

    def get_case(self, case_id: str) -> dict[str, Any] | None:
        return self.cases.get(str(case_id))

    def list_cases(
        self,
        concept: str | None = None,
        include_uncertain: bool = False,
        query: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        del include_uncertain, query
        cases = [
            case
            for case in self.cases.values()
            if concept is None or concept in set(case.get("supported_objectives") or [])
        ]
        return [case_summary(case) for case in cases[offset : offset + limit]]

    def candidates(self, concept_id: str | None = None) -> list[dict[str, Any]]:
        return [
            {
                "case_id": case["case_id"],
                "source": case["source"],
                "teaching_tier": case["teaching_tier"],
                "concept_tier": "A",
                "supported_objectives": list(case.get("supported_objectives") or []),
            }
            for case in self.cases.values()
            if concept_id is None
            or concept_id in set(case.get("supported_objectives") or [])
        ]

    def concept_ab_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for case in self.cases.values():
            for concept in case.get("supported_objectives") or []:
                counts[str(concept)] = counts.get(str(concept), 0) + 1
        return counts

    def group_reliable_count(self, concept_ids: list[str]) -> int:
        wanted = set(concept_ids)
        return sum(
            bool(wanted & set(case.get("supported_objectives") or []))
            for case in self.cases.values()
        )

    def get_waveform_window(
        self,
        case_id: str,
        leads: list[str] | None = None,
        start: float = 0,
        end: float | None = None,
        max_points: int = 1200,
    ) -> dict[str, Any] | None:
        del max_points
        if case_id not in self.cases:
            return None
        lead = (leads or ["II"])[0]
        return {
            "caseId": case_id,
            "samplingFrequency": 100,
            "startSec": start,
            "endSec": end or 10.0,
            "leads": [
                {
                    "lead": lead,
                    "points": [
                        {"timeSec": start, "amplitudeMv": 0.0},
                        {"timeSec": min(end or 10.0, start + 0.01), "amplitudeMv": 0.1},
                    ],
                }
            ],
        }


def _ptb_case() -> dict[str, Any]:
    case = deepcopy(build_fixture_cases()[0])
    case.update(
        {
            "case_id": "ptb-allowed",
            "display_id": "Allowed PTB case",
            "source": "ptbxl",
            "teaching_tier": "A",
            "supported_objectives": ["normal_ecg"],
            "concept_confidence": {
                "normal_ecg": {"tier": "A", "score": 0.95, "evidence": [], "warnings": []}
            },
        }
    )
    case["waveform"] = {**case["waveform"], "source": "corpus_store"}
    return case


def _leipzig_case() -> dict[str, Any]:
    spec = WindowSpec(
        record_name="x0010",
        patient_id="0010",
        sampling_frequency=1_000,
        start_sample=10_000,
        end_sample=20_000,
        episode_start_sample=9_500,
        episode_end_sample=20_500,
        raw_rhythm_aux="(AVNRT",
        rhythm_code="AVNRT",
        concept_id="supraventricular_tachycardia",
        beat_samples=tuple(range(10_300, 20_000, 350)),
    )
    signal = {
        lead: [((index % 31) - 15) / 100 for index in range(1_000)]
        for lead in SURFACE_LEADS
    }
    return build_window_packet(spec, signal)


def _mimic_case(source: str) -> dict[str, Any]:
    case = deepcopy(_leipzig_case())
    is_ext = source == "mimic-iv-ecg-ext"
    version = "1.0.1" if is_ext else "1.0"
    license_id = (
        "PhysioNet-Credentialed-Health-Data-License-1.5.0"
        if is_ext
        else "ODbL-1.0"
    )
    label_authority = (
        "encounter-linked ICD-10 labels; not ECG morphology ground truth"
        if is_ext
        else "linked cardiologist reports when available"
    )
    record_id = "forbidden-ext" if is_ext else "forbidden-waveform"
    case.update({"case_id": f"{source}:{record_id}", "source": source})
    case["record_identity"].update(
        {
            "sourceId": source,
            "sourceRecordId": record_id,
            "sourceVersion": version,
            "licenseId": license_id,
        }
    )
    case["source_provenance"].update(
        {
            "sourceId": source,
            "sourceVersion": version,
            "licenseId": license_id,
            "labelAuthority": label_authority,
        }
    )
    case["educational_eligibility"].update(
        {
            "educationalUse": "static_12_lead" if not is_ext else "clinical_context",
            "eligibleModes": ["training", "rapid"],
        }
    )
    return case


def _client(monkeypatch) -> tuple[TestClient, dict[str, dict[str, Any]]]:
    cases = [_ptb_case(), _leipzig_case(), _mimic_case("mimic-iv-ecg"), _mimic_case("mimic-iv-ecg-ext")]
    monkeypatch.setattr(main_module, "repo", FakeRepo(cases))
    return TestClient(main_module.app), {str(case["source"]): case for case in cases}


def test_generic_case_catalog_and_direct_routes_never_expose_mimic(monkeypatch) -> None:
    client, cases = _client(monkeypatch)

    catalog = client.get("/cases?limit=20")
    assert catalog.status_code == 200
    assert {row["caseId"] for row in catalog.json()} == {"ptb-allowed"}

    for source in ("mimic-iv-ecg", "mimic-iv-ecg-ext"):
        case_id = cases[source]["case_id"]
        assert client.get(f"/cases/{case_id}").status_code == 404
        assert client.get(f"/cases/{case_id}/packet").status_code == 404
        assert client.get(f"/cases/{case_id}/waveform").status_code == 404
        assert client.get(f"/cases/{case_id}/ptbxl-plus").status_code == 404

    # A validated specialist packet remains directly reachable after a
    # Training/Rapid session has authorized its case id.
    leipzig_id = cases["leipzig-heart-center"]["case_id"]
    assert client.get(f"/cases/{leipzig_id}").status_code == 200
    assert client.get(f"/cases/{leipzig_id}/packet").status_code == 200
    assert client.get(f"/cases/{leipzig_id}/waveform").status_code == 200


def test_generic_practice_tutorial_and_legacy_review_exclude_target_only_and_mimic(
    monkeypatch,
) -> None:
    client, _ = _client(monkeypatch)

    practice = client.get(
        "/practice/next?conceptId=supraventricular_tachycardia"
    )
    assert practice.status_code == 200
    assert practice.json()["requestedConceptUnavailable"] is True
    assert practice.json()["case"]["caseId"] == "ptb-allowed"

    tutorial = client.get(
        "/tutorials/svt?concept=supraventricular_tachycardia"
    )
    assert tutorial.status_code == 200
    assert tutorial.json()["selection"]["requestedConceptUnavailable"] is True
    assert tutorial.json()["recommendedCase"]["caseId"].startswith("ec_")
    assert "ptb-allowed" not in tutorial.text
    assert tutorial.json()["recommendedPacket"]["source"] == "audited_waveform"

    review = client.post(
        "/review/start",
        json={
            "conceptId": "supraventricular_tachycardia",
            "targetMastery": 0.8,
            "maxCases": 5,
        },
    )
    assert review.status_code == 410
    assert review.json()["detail"]["code"] == "legacy_review_deprecated"
    assert review.json()["detail"]["replacement"] == {
        "method": "GET",
        "path": "/adaptive/plan",
    }
