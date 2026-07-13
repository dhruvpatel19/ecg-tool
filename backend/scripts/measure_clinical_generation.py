"""Measure nano-generation convergence for Clinical Decisions (Phase 4 spike).

Runs the generator over grounded packets and reports the harness accept-rate + the
histogram of rejection reasons — the real answer to "will the model converge against the
guardrails", rather than a guess.

Usage (from backend/):
    python scripts/measure_clinical_generation.py [situation] [question_type] [n]

By default uses the bundled fixture packets and whatever LLM_PROVIDER is configured.
For a REAL run, set a (rotated) key + provider first, e.g.:
    LLM_PROVIDER=openai-compatible LLM_API_KEY=... LLM_MODEL=gpt-5.4-nano \
    LLM_BASE_URL=https://api.openai.com/v1 python scripts/measure_clinical_generation.py ed mcq 25

With the mock provider (no key) every draft is rejected at parse time — that still
exercises the gate and the reporting.
"""

from __future__ import annotations

import json
import sys

from app.clinical.fixture_items import FIXTURE_PACKETS
from app.clinical.generator import measure_convergence
from app.config import get_settings
from app.llm import TutorService


def main() -> None:
    situation = sys.argv[1] if len(sys.argv) > 1 else "ed"
    question_type = sys.argv[2] if len(sys.argv) > 2 else "mcq"
    n = int(sys.argv[3]) if len(sys.argv) > 3 else len(FIXTURE_PACKETS)

    settings = get_settings()
    provider = TutorService(settings).provider
    packets = list(FIXTURE_PACKETS.values())
    # repeat the fixture packets up to n attempts (a real run would pull n distinct corpus cases)
    attempts = [packets[i % len(packets)] for i in range(n)]

    print(f"provider={settings.llm_provider} situation={situation} type={question_type} attempts={len(attempts)}")
    summary = measure_convergence(attempts, situation, question_type, provider)
    summary.pop("items", None)  # don't dump full items, just the metrics
    print(json.dumps(summary, indent=2))
    if summary["accept_rate"] == 0.0 and settings.llm_provider == "mock":
        print("\n(note: the mock provider returns tutor JSON, not a clinical item, so all drafts are "
              "rejected at parse — set a real provider for a meaningful accept-rate.)")


if __name__ == "__main__":
    main()
