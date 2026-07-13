from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from app.config import Settings
from app.curation import curate_case
from app.data_sources import CaseRepository, normalize_lead_name
from app.fixtures import build_fixture_cases
from app.llm import OpenAICompatibleProvider
from app.main import packet_for_case
from app.schemas import LEADS


def _curate_codes(scp: dict[str, float], statements=None, features=None, report: str = "") -> dict:
    """Run curation on a minimal packet carrying the given SCP codes (presence-based)."""
    packet = {
        "case_id": "t",
        "waveform": {"leads": list(LEADS), "duration_sec": 10},
        "ptbxl": {"scp_codes": scp, "report": report},
        "ptbxl_plus": {
            "statements": statements or [],
            "features": features or {},
            "fiducials": {"rois": []},
            "per_lead_st_mv": {},
        },
        "signal_quality": {"status": "acceptable"},
    }
    return curate_case(packet)["concept_confidence"]


def test_full_scp_vocabulary_resurrects_previously_zero_concepts() -> None:
    # Each was 0 A/B before (STE_ typo, unmapped INVT/EL/PVC/WPW/LAFB). PTB-XL stores
    # these at likelihood 0, so curation must be presence-based.
    assert _curate_codes({"INVT": 0.0})["t_wave_inversion"]["tier"] in {"A", "B"}
    assert _curate_codes({"EL": 0.0})["electrolyte_drug_pattern"]["tier"] in {"A", "B"}
    assert _curate_codes({"PVC": 0.0})["premature_ventricular_complex"]["tier"] in {"A", "B"}
    assert _curate_codes({"WPW": 0.0})["wolff_parkinson_white"]["tier"] in {"A", "B"}
    assert _curate_codes({"STE_": 0.0})["st_elevation"]["tier"] in {"A", "B"}
    # LAFB + concordant left axis -> Tier A (two independent sources).
    assert _curate_codes({"LAFB": 0.0}, features={"axis_deg": -60})["left_anterior_fascicular_block"]["tier"] in {"A", "B"}


def test_supraventricular_statement_does_not_trigger_wide_complex_tachycardia() -> None:
    # Word-boundary guard: "supraventricular tachycardia" must NOT credit VT (absent in PTB-XL).
    cc = _curate_codes({"SVTAC": 0.0}, statements=["Supraventricular tachycardia (100%)"])
    assert cc["wide_complex_tachycardia"]["tier"] not in {"A", "B"}
    assert cc["supraventricular_tachycardia"]["tier"] in {"A", "B"}


def test_fixture_fallback_builds_student_facing_cases() -> None:
    repo = CaseRepository(
        Settings(require_real_data=False, ptbxl_data_root=None, database_url="sqlite:///:memory:")
    )

    assert repo.status["active_source"] == "fixture"
    assert repo.status["fixture_fallback"] is True
    assert repo.status["student_facing_count"] >= 6


def test_curation_excludes_uncertain_fixture() -> None:
    cases = {case["case_id"]: case for case in build_fixture_cases()}
    uncertain = cases["fixture-uncertain-noisy-001"]

    assert uncertain["teaching_tier"] == "C"
    assert uncertain["teaching_tier"] not in {"A", "B"}
    assert "Case is withheld from default student workflows." in uncertain["exclusion_reasons"]


def test_case_packet_contains_grounding_and_forbidden_claims() -> None:
    case = build_fixture_cases()[0]
    packet = packet_for_case(case)

    assert packet["case_id"] == case["case_id"]
    assert packet["ptbxl"]["scp_codes"]
    assert packet["concept_confidence"]["normal_ecg"]["tier"] == "A"
    assert "waveform_data" not in packet
    assert packet["llm_forbidden_claims"]


def test_bundle_branch_block_specificity_requires_matching_evidence() -> None:
    cases = {case["case_id"]: case for case in build_fixture_cases()}
    rbbb = cases["fixture-rbbb-001"]

    assert rbbb["concept_confidence"]["right_bundle_branch_block"]["tier"] == "A"
    assert rbbb["concept_confidence"]["left_bundle_branch_block"]["tier"] == "D"


def test_bundle_branch_cross_source_contradiction_is_not_student_facing() -> None:
    confidence = _curate_codes(
        {"IRBBB": 100.0},
        statements=["Complete right bundle branch block (100%)"],
        features={"qrs_ms": 142},
        report="Sinusrhythmus Linksschenkelblock unbestätigter Bericht",
    )

    assert confidence["right_bundle_branch_block"]["tier"] not in {"A", "B"}
    assert any("contradiction" in warning.lower() for warning in confidence["right_bundle_branch_block"]["warnings"])


def test_wfdb_lead_names_normalize_augmented_limb_leads() -> None:
    assert normalize_lead_name("AVR") == normalize_lead_name("aVR")
    assert normalize_lead_name("AVL") == normalize_lead_name("aVL")
    assert normalize_lead_name("AVF") == normalize_lead_name("aVF")


def test_fixture_packets_include_realistic_ptbxl_plus_median_fallback() -> None:
    packet = packet_for_case(build_fixture_cases()[0])

    median = packet["ptbxl_plus"]["median_beats"]
    assert median["source"] == "fixture_synthetic"
    assert median["beats"]["II"]["samplesMv"]


def test_openai_compatible_provider_without_key_never_requires_remote_call() -> None:
    raw = OpenAICompatibleProvider(
        Settings(
            ptbxl_data_root=None,
            ptbxl_plus_data_root=None,
            database_url="sqlite:///:memory:",
            llm_provider="openai-compatible",
            llm_api_key=None,
        )
    ).generate([], {})

    assert "no LLM_API_KEY" in raw
    assert "no remote call was made" in raw


def test_openai_compatible_provider_calls_openai_style_endpoint() -> None:
    captured: dict[str, object] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            captured["path"] = self.path
            captured["authorization"] = self.headers.get("Authorization")
            length = int(self.headers.get("Content-Length", "0"))
            captured["body"] = json.loads(self.rfile.read(length).decode("utf-8"))
            response = {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "tutorMessage": "Look at lead II.",
                                    "feedback": "Grounded stub feedback.",
                                    "viewerActions": [],
                                    "objectiveUpdates": [],
                                    "misconceptions": [],
                                    "uncertaintyWarnings": [],
                                    "suggestedNextStep": "Submit a structured interpretation.",
                                }
                            )
                        }
                    }
                ]
            }
            payload = json.dumps(response).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_args: object) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        raw = OpenAICompatibleProvider(
            Settings(
                ptbxl_data_root=None,
                ptbxl_plus_data_root=None,
                database_url="sqlite:///:memory:",
                llm_provider="openai-compatible",
                llm_api_key="test-key",
                llm_model="test-model",
                llm_base_url=f"http://127.0.0.1:{server.server_port}/v1",
            )
        ).generate([{"role": "user", "content": "Read this ECG."}], {"casePacket": {"case_id": "stub"}})
    finally:
        server.shutdown()
        thread.join(timeout=3)

    parsed = json.loads(raw)
    body = captured["body"]
    assert captured["path"] == "/v1/chat/completions"
    assert captured["authorization"] == "Bearer test-key"
    assert body["model"] == "test-model"
    assert body["response_format"] == {"type": "json_object"}
    assert body["max_completion_tokens"] == 1200
    assert parsed["tutorMessage"] == "Look at lead II."
