"""Generate an automated-harness-screened bank of skeleton-MCQ items and persist it to
data/generated_bank.json (loaded by main.py alongside the fixtures). Real PTB-XL tracings.

Usage (from backend/):  python -m scripts.build_generated_bank [per_concept] [max_attempts]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from app.clinical.action_library import CONCEPT_ACTIONS
from app.clinical.burst import situation_for
from app.clinical.generator import generate_skeleton_and_vet
from app.config import get_settings
from app.llm import TutorService
from app.main import clinical_packet, repo

# Concepts to seed the served bank with (must have an action library + corpus coverage).
CONCEPTS = [
    "atrial_fibrillation", "bradycardia", "qtc_prolongation",
    "left_ventricular_hypertrophy", "right_bundle_branch_block", "normal_ecg",
]


def _candidate_ids(concept: str, limit: int) -> list[str]:
    seen, out = set(), []
    for c in repo.candidates(concept):
        cid = str(c["case_id"])
        if cid not in seen:
            seen.add(cid)
            out.append(cid)
        if len(out) >= limit:
            break
    return out


def main() -> None:
    per_concept = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    max_attempts = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    provider = TutorService(get_settings()).provider

    screened: list[dict] = []
    for concept in CONCEPTS:
        kept = 0
        for seed, cid in enumerate(_candidate_ids(concept, max_attempts)):
            pkt = clinical_packet(cid)
            if not pkt:
                continue
            r = generate_skeleton_and_vet(pkt, concept, provider, situation_for(pkt), seed=seed)
            if r["accepted"]:
                item = r["item"]
                # The generator already assigns harness_pass. Never promote an
                # automated check to human review without a reviewer record.
                item.validation_status = "harness_pass"
                screened.append(item.model_dump())
                kept += 1
                if kept >= per_concept:
                    break
        print(f"{concept}: kept {kept}")

    out_path = Path(__file__).resolve().parent.parent / "data" / "generated_bank.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(screened, indent=1), encoding="utf-8")
    print(f"\nwrote {len(screened)} automated-screened items → {out_path}")


if __name__ == "__main__":
    main()
