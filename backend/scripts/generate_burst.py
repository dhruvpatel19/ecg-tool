"""Run one generation burst against real corpus cases and print a detailed inspection report.

Usage (from backend/):
    python -m scripts.generate_burst [n] [question_type] [concept]

Prints, for EVERY accepted item: grounding vs claims, the stem/chips, options + answer-classes,
the evidence manifest, and a live grading spot-check (ideal vs a wrong option). Plus rejects with
reasons, diversity, and per-concept spread. This is the artifact to scrutinize before scaling up.
"""

from __future__ import annotations

import sys

from app.clinical.burst import run_burst
from app.clinical.clinical_grading import grade_clinical_answer
from app.clinical.grounding import features, supported_objectives
from app.clinical.schemas import ClinicalAnswer
from app.config import get_settings
from app.llm import TutorService
from app.main import clinical_packet, repo


def _grade(item, packet, answer_class):
    opt = next((o for o in item.options if o.answer_class == answer_class), None)
    if not opt:
        return None
    g = grade_clinical_answer(item, packet, ClinicalAnswer(selected_option_id=opt.id, confidence=4))
    return opt.text[:70], round(g["score"], 2)


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    qtype = sys.argv[2] if len(sys.argv) > 2 else "mcq"
    concept = sys.argv[3] if len(sys.argv) > 3 else None

    provider = TutorService(get_settings()).provider
    burst = run_burst(repo, clinical_packet, provider, n=n, question_type=qtype, concept=concept)
    s = burst["summary"]

    print(f"# Generation burst — n={s['attempts']} type={qtype} concept={concept or 'spread'}\n")
    print(f"accepted {s['accepted']}/{s['attempts']} ({int(s['accept_rate']*100)}%) · "
          f"distinct signatures {s['distinct_signatures']} · concepts {s['concepts_covered']}")
    print(f"reject reasons: {s['reject_reasons']}\n")

    print("## Accepted items (inspect each)\n")
    for i, r in enumerate(burst["accepted"], 1):
        it = r["item"]
        pkt = r["packet"]
        sup = sorted(supported_objectives(pkt))
        feats = features(pkt)
        targets = [c.objective_id for c in it.evidence_manifest.ecg_supports]
        print(f"### {i}. ECG {it.ecg_id} · {r['situation']} · {it.question_type} · acuity={it.acuity_tier}")
        print(f"- grounded supported_objectives: {sup}")
        print(f"- HR={feats.get('heart_rate')} PR={feats.get('pr_ms')} QRS={feats.get('qrs_ms')} QTc={feats.get('qtc_ms')} axis={feats.get('axis_deg')}")
        print(f"- claimed targets: {targets}")
        chips = it.chips
        print(f"- stem: {it.stem}")
        print(f"- chips: age={chips.age} setting={chips.setting} symptom={chips.symptom} bp={chips.bp}")
        print(f"- prompt: {it.prompt}")
        for o in it.options:
            print(f"    - [{o.answer_class}] {o.text}")
        print(f"- rationale: {it.evidence_manifest.action_rationale}")
        ideal = _grade(it, pkt, "ideal")
        for wrong_class in ("unsafe", "under_triage", "over_triage_safe"):
            wrong = _grade(it, pkt, wrong_class)
            if wrong:
                break
        print(f"- grading spot-check: ideal {ideal} | {wrong_class if wrong else '—'} {wrong}")
        print()

    print("## Rejected\n")
    for r in burst["results"]:
        if not r["accepted"]:
            print(f"- ECG {r['ecg_id']}: {r['reason']}")


if __name__ == "__main__":
    main()
