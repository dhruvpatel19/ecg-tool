from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_case_catalog_pages_across_the_full_corpus() -> None:
    first = client.get("/cases?limit=25&offset=0")
    second = client.get("/cases?limit=25&offset=25")
    assert first.status_code == second.status_code == 200
    assert len(first.json()) == len(second.json()) == 25
    assert {row["caseId"] for row in first.json()}.isdisjoint(
        {row["caseId"] for row in second.json()}
    )
    assert client.get("/cases?limit=5001").status_code == 422


def test_end_to_end_practice_api_flow() -> None:
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["ok"] is True

    cases = client.get("/cases").json()
    assert cases
    case_id = cases[0]["caseId"]

    packet = client.get(f"/cases/{case_id}/packet")
    assert packet.status_code == 200
    assert packet.json()["case_id"] == case_id

    waveform = client.get(f"/cases/{case_id}/waveform?leads=II,V2&maxPoints=300")
    assert waveform.status_code == 200
    assert len(waveform.json()["leads"]) >= 1
    assert waveform.json()["leads"][0]["points"]

    mapped = client.post(
        "/viewer/map-point",
        json={"x": 100, "y": 100, "width": 1200, "height": 900, "timeStartSec": 0, "timeEndSec": 10},
    )
    assert mapped.status_code == 200
    assert {"lead", "timeSec", "amplitudeMv"} <= set(mapped.json())

    answer = {
        "learnerId": "pytest",
        "caseId": case_id,
        "mode": "rapid_practice",
        "structuredAnswer": {
            "framework": "clerkship",
            "rate": "normal rate",
            "rhythm": "sinus rhythm",
            "axis": "normal axis",
            "intervals": "normal intervals",
            "conduction": "",
            "st_t": "",
            "hypertrophy": "",
            "synthesis": "normal ECG",
            "selectedConcepts": ["normal_ecg", "sinus_rhythm"],
        },
        "freeTextAnswer": "normal sinus rhythm",
        "confidence": 3,
        "hintsUsed": 0,
    }
    attempt = client.post("/attempts", json=answer)
    assert attempt.status_code == 200
    body = attempt.json()
    assert body["attemptId"] > 0
    assert "grade" in body
    assert body["tutor"]["viewerActions"] is not None

    adaptive = client.get("/practice/next?learnerId=pytest")
    assert adaptive.status_code == 200
    assert adaptive.json()["case"]["caseId"]


def test_tutorial_equivalent_retry_can_exclude_the_first_case() -> None:
    first = client.get("/tutorials/axis?concept=axis_normal")
    assert first.status_code == 200
    first_id = first.json()["recommendedCase"]["caseId"]

    second = client.get(f"/tutorials/axis?concept=axis_normal&excludeCaseId={first_id}")
    assert second.status_code == 200
    second_id = second.json()["recommendedCase"]["caseId"]
    assert second_id != first_id

    independent = client.get("/practice/next?conceptId=axis_normal")
    assert independent.status_code == 200
    assert independent.json()["case"]["caseId"] not in {first_id, second_id}


def test_practice_next_supports_bounded_round_no_repeat_exclusions() -> None:
    first = client.get("/practice/next?conceptId=normal_ecg")
    assert first.status_code == 200
    first_id = first.json()["case"]["caseId"]

    second = client.get(
        f"/practice/next?conceptId=normal_ecg&excludeCaseIds={first_id}"
    )
    assert second.status_code == 200
    assert second.json()["case"]["caseId"] != first_id

    abusive = ",".join(str(index) for index in range(101))
    rejected = client.get(f"/practice/next?excludeCaseIds={abusive}")
    assert rejected.status_code == 422
