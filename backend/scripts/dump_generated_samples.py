"""Generate a representative set of items across types/concepts and print them VERBATIM (untruncated)
for an external review packet. Spend-bounded: a few accepted items per (type, concept)."""

from __future__ import annotations

from app.clinical.clinical_grading import grade_clinical_answer, periodic_click_match
from app.clinical.generator import generate_and_vet
from app.clinical.grounding import features, rois, supported_objectives
from app.clinical.schemas import ClinicalAnswer, ClinicalClick
from app.config import get_settings
from app.llm import TutorService
from app.main import clinical_packet, repo

# (question_type, concept, situation, how many accepted to keep, max attempts)
PLAN = [
    ("mcq", "atrial_fibrillation", "ward", 2, 6),
    ("mcq", "left_ventricular_hypertrophy", "clinic", 1, 6),
    ("triage", "bradycardia", "ed", 2, 6),
    ("stepwise", "av_block_first_degree", "ward", 2, 6),
    ("click", "av_block_first_degree", "clinic", 1, 5),
    ("click", "st_depression", "ed", 1, 5),
]


def _candidate_ids(concept, limit):
    seen, out = set(), []
    for c in repo.candidates(concept):
        cid = str(c["case_id"])
        if cid not in seen:
            seen.add(cid); out.append(cid)
        if len(out) >= limit:
            break
    return out


def _dump(item, packet):
    f = features(packet)
    print(f"  ecg_id={item.ecg_id} situation={item.situation} type={item.question_type} acuity={item.acuity_tier}")
    print(f"  grounded_supported={sorted(supported_objectives(packet))}")
    print(f"  features: HR={f.get('heart_rate')} PR={f.get('pr_ms')} QRS={f.get('qrs_ms')} QTc={f.get('qtc_ms')} axis={f.get('axis_deg')}")
    print(f"  manifest_targets={[c.objective_id for c in item.evidence_manifest.ecg_supports]}")
    print(f"  chips: age={item.chips.age} sex={item.chips.setting and ''}setting={item.chips.setting} symptom={item.chips.symptom} bp={item.chips.bp}")
    print(f"  STEM: {item.stem}")
    print(f"  PROMPT: {item.prompt}")
    for o in item.options:
        print(f"    OPTION [{o.answer_class}]{(' value='+o.value) if o.value else ''}: {o.text}")
    for i, st in enumerate(item.steps, 1):
        print(f"    STEP {i}: {st.prompt}")
        for so in st.options:
            print(f"        - {'[correct] ' if so.correct else ''}{so.text}")
    if item.roi_target:
        print(f"    ROI_TARGET: concept={item.roi_target.concept} leads={item.roi_target.leads} type={item.roi_target.target_type}")
    print(f"  RATIONALE: {item.evidence_manifest.action_rationale}")
    print(f"  FORBIDDEN: {item.evidence_manifest.forbidden_claims}")
    # grading spot-check
    if item.options:
        ideal = next((o for o in item.options if o.answer_class == "ideal"), None)
        wrong = next((o for o in item.options if o.answer_class in ("unsafe", "under_triage", "over_triage_safe")), None)
        gi = grade_clinical_answer(item, packet, ClinicalAnswer(selected_option_id=ideal.id, confidence=4)) if ideal else None
        gw = grade_clinical_answer(item, packet, ClinicalAnswer(selected_option_id=wrong.id, confidence=4)) if wrong else None
        print(f"  GRADING: ideal={gi and gi['score']} wrong({wrong and wrong.answer_class})={gw and gw['score']}")
    elif item.roi_target:
        rc = item.roi_target.concept
        from app.clinical.grounding import CONCEPT_TO_ROI
        roiC = CONCEPT_TO_ROI.get(rc, rc)
        roi = next((x for x in rois(packet) if x.get("concept") == roiC and x.get("lead") == item.roi_target.leads[0]), None)
        if roi:
            t = (roi["timeStartSec"] + roi["timeEndSec"]) / 2
            g = grade_clinical_answer(item, packet, ClinicalAnswer(click=ClinicalClick(lead=item.roi_target.leads[0], time_sec=t)))
            gw = grade_clinical_answer(item, packet, ClinicalAnswer(click=ClinicalClick(lead="aVR", time_sec=0.05)))
            print(f"  GRADING: correct_click={g['score']} wrong_click={gw['score']}")
    print()


def main():
    provider = TutorService(get_settings()).provider
    for qtype, concept, situation, keep, max_attempts in PLAN:
        print(f"\n===== {qtype.upper()} · {concept} · {situation} =====")
        kept = 0
        for cid in _candidate_ids(concept, max_attempts):
            pkt = clinical_packet(cid)
            if not pkt:
                continue
            r = generate_and_vet(pkt, situation, qtype, provider)
            if r["accepted"]:
                _dump(r["item"], pkt)
                kept += 1
                if kept >= keep:
                    break
        if kept == 0:
            print("  (no accepted item in this attempt budget)")


if __name__ == "__main__":
    main()
