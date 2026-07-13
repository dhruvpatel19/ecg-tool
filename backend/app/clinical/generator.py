"""Phase 4 — nano generation, gated by the harness.

A cheap model DRAFTS an item from a grounded packet (constrained by supported_objectives,
the acuity cap, required-safety tokens, and the distractor rubric); the draft is then run
through the claim-check guards + the validation harness, and only a passing item is cached.
This is the feasibility spike: ``generate_and_vet`` returns the accept/reject verdict so a
batch run can MEASURE the reject rate / convergence rather than guess it.

The actual draft quality depends on a real model (LLM_PROVIDER=openai-compatible). With the
mock provider (CI/keyless), drafts won't parse to a ClinicalCaseItem, so they are rejected —
which still exercises the gate. The pipeline wiring is what this module guarantees.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from ..schemas import LEADS
from .constants import SAFETY_TOKENS
from .content_tables import ACUITY_BASE, ACUITY_CAP_BY_CONCEPT, REQUIRED_SAFETY_ACTIONS
from .grounding import CONCEPT_TO_ROI, features, rois, supported_objectives
from .harness import run_harness
from .harness.result import HarnessReport
from .schemas import ClinicalCaseItem

_VALID_LEADS = set(LEADS)
_VALID_SAFETY_TOKENS = SAFETY_TOKENS

CLINICAL_GEN_SYSTEM_PROMPT = """You author ONE board-style "Clinical Decisions" ECG item as STRICT JSON.
The tracing is REAL and curation-grounded; the clinical vignette is authored. The answer is a
clinical DECISION/management action — NOT an interpretation label. Output ONLY a JSON object, no prose.
Follow the `type_guidance` for the requested question_type exactly.

EXACT VALUES (using any other value will be REJECTED):
- `situation`: one of "clinic","ward","ed","triage" (lowercase).
- `question_type`: exactly the requested type.
- `acuity_tier`: one of "none","low","moderate","moderate_high","high"; must not exceed the given acuity_ceiling.
- each option `answer_class`: one of "ideal","acceptable","over_triage_safe","under_triage","unsafe","insufficient_data".
  Provide 3-4 options with EXACTLY ONE "ideal". Do NOT invent classes like "correct" or "distractor".
- `chips`: {age:<integer>, setting:<string>, symptom:<string>, bp:<string>}. USE THE PROVIDED `demographics` age/sex; if age is null, pick a plausible adult age (40-85) — do NOT default to 45. age MUST be an integer. OMIT any unknown field.
- each ecg_supports `source_type`: one of "measured","curated_label","authored_context"; `epistemic_status`: "determined" or "intentionally_underdetermined".

ANSWER-CLASS DEFINITIONS — classify each option by what is clinically TRUE of it (a wrong class is a defect):
- ideal: the single best management action.
- acceptable: reasonable and safe, only slightly suboptimal or less complete than ideal.
- over_triage_safe: MORE than needed / too aggressive, but not harmful (e.g. unnecessary admit, cardiology, or ED transfer for a benign finding; "immediate ED for ACS" on a normal ECG is OVER-triage).
- under_triage: does too LITTLE — misses or delays a needed action.
- unsafe: actively harmful, contraindicated, or dangerous (a wrong drug; discharging a dangerous finding; an irrelevant/absurd action like "order a CT head" for a tachycardia is unsafe or under_triage, NOT insufficient_data).
- insufficient_data: ONLY for a genuine "gather a specific piece of data before acting" option; NEVER for irrelevant or absurd actions.

HARD RULES (a validator enforces these):
- The tracing is a RESTING / CHRONIC 12-lead ECG. Any MI / ischemia / ST-T findings are ESTABLISHED / OLD, not an active event. Do NOT write acute, evolving, sudden-onset, or "spreading/radiating" symptom narratives, and do NOT imply an acute coronary event — frame the vignette as a resting ECG with established findings.
- Only claim findings in `supported_objectives`. Never invent territory/acuity.
- For a high-acuity concept in `required_safety_actions`, every ideal/acceptable option MUST include one of its safety tokens (put them in `required_safety_tokens`).
- No acute/temporal language ("acute","evolving","started minutes ago","rising troponin") unless serial/acute evidence exists.
- Options must be plausible management choices, same specificity, safe to teach against — no cartoonish options.
- Distractors must be plausible ON THEIR FACE — NEVER write an option that states why it is wrong. Banned in option text: "despite", "solely", "based solely on", "even though", "no acute symptoms", "because the ECG is chronic".
- Refer to MI/ischemia as an "old-MI pattern" / "established (chronic) pattern" — NEVER "known prior MI", "documented MI", or "secondary prevention is required" (an ECG pattern is not a documented history).
- Decisions must be CONDITIONAL on assessment, not automatic: anticoagulation depends on stroke/bleeding risk (CHA2DS2-VASc); if the ventricular rate is already slow do NOT add rate control; call QTc "prolonged" only if it truly exceeds the sex threshold (≥470 ms male / ≥480 ms female) with a regular rhythm.
- A finding must not be keyed as the CAUSE of a symptom it cannot explain.
- Vary the stem opening, clinical context, and distractor types across items; avoid formulaic phrasing.

JSON keys: situation, question_type, acuity_tier, stem, chips, prompt,
options[{text,answer_class,value?,required_safety_tokens?}],
evidence_manifest{ecg_supports[{objective_id,threshold?,leads?,source_type}],stem_adds[],action_rationale,forbidden_claims[],acceptable_range[],epistemic_status},
tested_scope, display_spec{mode,pinned_strip_lead?,tested_scope}."""


# Per-question-type authoring guidance (the safety/structure rules stay in the system prompt).
TYPE_GUIDANCE: dict[str, str] = {
    "mcq": "Produce 3-4 management options; exactly one 'ideal'. Classify each option by answer_class.",
    "triage": (
        "SICK / NOT-SICK triage. Produce EXACTLY 3 options and set each option's `value` to one of "
        "'act' (act now), 'workup' (work it up), 'routine' (routine / not sick). Exactly one is 'ideal'; "
        "classify the other two by answer_class. The prompt asks: act now, work up, or routine?"
    ),
    "stepwise": (
        "DECISION-FIRST stepwise. Produce 3-4 disposition options (exactly one 'ideal', classify the rest) "
        "AND a `steps` array of 2-3 reasoning steps. Each step = {prompt, options:[{text, correct:bool}]} with "
        "2-3 options and EXACTLY ONE correct. Steps walk rate → rhythm → key finding → disposition."
    ),
    "click": "Write ONLY a brief clinical vignette (age/setting/relevant context). Do NOT mention clicking, the learner, the trace, the objective, or the task, and do NOT write options or a prompt — the click prompt is added separately.",
}


def build_generation_context(packet: dict[str, Any], situation: str, question_type: str) -> dict[str, Any]:
    sup = sorted(supported_objectives(packet))
    ceiling = max((ACUITY_CAP_BY_CONCEPT.get(c, "workup") for c in sup), default="workup",
                  key=lambda u: ["routine", "workup", "admit", "urgent", "act_now"].index(u))
    meta = (packet.get("ptbxl") or {}).get("metadata") or {}
    raw_age = meta.get("age")
    # PTB-XL codes ages ≥90 (and missing) as 300 — sanitize so the model never writes "age 300".
    age = raw_age if isinstance(raw_age, (int, float)) and 0 < raw_age <= 95 else None
    sex = {0: "male", 1: "female", "0": "male", "1": "female", "M": "male", "F": "female"}.get(meta.get("sex"))
    return {
        "situation": situation,
        "question_type": question_type,
        "supported_objectives": sup,
        "acuity_base": {c: ACUITY_BASE.get(c, "low") for c in sup},
        "acuity_ceiling": ceiling,
        "required_safety_actions": {c: REQUIRED_SAFETY_ACTIONS[c] for c in sup if c in REQUIRED_SAFETY_ACTIONS},
        "measurements": features(packet),
        "demographics": {"age": age, "sex": sex},  # real (sanitized) patient age/sex for diversity + grounding
        "type_guidance": TYPE_GUIDANCE.get(question_type, ""),
    }


def build_messages(packet: dict[str, Any], situation: str, question_type: str) -> list[dict[str, str]]:
    ctx = build_generation_context(packet, situation, question_type)
    return [
        {"role": "system", "content": CLINICAL_GEN_SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(ctx)},
    ]


_SITUATION_SYNONYMS = {"emergency": "ed", "emergency dept": "ed", "emergency department": "ed", "er": "ed"}


def _normalize_draft(data: dict[str, Any]) -> dict[str, Any]:
    """Light, lossless cleanup so a cheap model's near-misses validate: lowercase enums,
    coerce age to int, drop placeholder chip strings, snap symptom to the known vocabulary."""
    from .constants import SYMPTOMS

    for key in ("situation", "question_type", "acuity_tier", "tested_scope"):
        if isinstance(data.get(key), str):
            v = data[key].strip().lower()
            data[key] = _SITUATION_SYNONYMS.get(v, v) if key == "situation" else v
    chips = data.get("chips")
    if isinstance(chips, dict):
        age = chips.get("age")
        if isinstance(age, str):
            m = re.search(r"\d+", age)
            chips["age"] = int(m.group()) if m else None
        sym = chips.get("symptom")
        if isinstance(sym, str):
            snapped = sym.strip().lower().replace(" ", "_")
            chips["symptom"] = snapped if snapped in SYMPTOMS else None
        for k in ("setting", "symptom", "bp", "mental_status"):
            v = chips.get(k)
            if isinstance(v, str) and v.strip().lower() in {"not provided", "unknown", "n/a", "none given", "none", ""}:
                chips[k] = None

    # Snap enum-ish fields to valid values (the model emits "12_lead", "twelve_lead", etc.).
    _TESTED = {"full_12_lead", "rhythm_only", "zoom_lead"}
    _MODES = {"twelve_lead", "twelve_lead_pinned_strip", "twelve_lead_machine_panel", "stacked_twelve_lead", "zoom_lead"}
    ts = data.get("tested_scope")
    if not (isinstance(ts, str) and ts in _TESTED):
        data["tested_scope"] = "zoom_lead" if data.get("question_type") == "click" else "full_12_lead"
    ds = data.get("display_spec")
    if isinstance(ds, dict):
        mode = ds.get("mode")
        if isinstance(mode, str):
            mode = ds["mode"] = mode.strip().lower()
        if not (isinstance(mode, str) and mode in _MODES):
            ds["mode"] = "twelve_lead"
        dts = ds.get("tested_scope")
        if isinstance(dts, str):
            dts = ds["tested_scope"] = dts.strip().lower()
        if not (isinstance(dts, str) and dts in _TESTED):
            ds["tested_scope"] = data["tested_scope"]
    elif ds is not None:
        data["display_spec"] = {"mode": "twelve_lead", "tested_scope": data["tested_scope"]}

    # Coerce nested objects to the schema: a cheap model over-generates keys (e.g. nests
    # epistemic_status inside a claim) or copies the literal "?" optional marker into a key.
    _CLAIM = {"objective_id", "threshold", "leads", "roi_concept", "source_type"}
    _MANIFEST = {"ecg_supports", "stem_adds", "action_rationale", "forbidden_claims", "acceptable_range", "epistemic_status"}
    _OPTION = {"id", "text", "answer_class", "value", "axis_scores", "required_safety_tokens", "parsed"}

    def _strip_qmarks(d: dict) -> None:
        for k in list(d):
            if k.endswith("?"):
                base = k[:-1]
                d.setdefault(base, d.pop(k))

    em = data.get("evidence_manifest")
    if isinstance(em, dict):
        _strip_qmarks(em)
        claims = em.get("ecg_supports")
        if isinstance(claims, list):
            for cl in claims:
                if not isinstance(cl, dict):
                    continue
                _strip_qmarks(cl)
                if "epistemic_status" in cl and "epistemic_status" not in em:
                    em["epistemic_status"] = cl["epistemic_status"]  # hoist a misplaced field
                # threshold must be a "feature<cmp>value" string. Reconstruct from a structured
                # {feature, op, value} object (the model's common shape) so the harness can EVALUATE
                # it and reject a false claim — never silently drop it (round-3 anti-laundering).
                th = cl.get("threshold")
                if isinstance(th, dict):
                    feat = th.get("feature")
                    op = th.get("op") or th.get("comparator") or ">="
                    val = th.get("value")
                    cl["threshold"] = f"{feat}{op}{val}" if (feat and val is not None) else None
                    if cl["threshold"] is None:
                        cl.pop("threshold")
                elif "threshold" in cl and not isinstance(cl["threshold"], str):
                    cl.pop("threshold")
                # leads must be a list of VALID leads; wrap a stray scalar, drop garbage ("I/").
                if isinstance(cl.get("leads"), str):
                    cl["leads"] = [cl["leads"]]
                if isinstance(cl.get("leads"), list):
                    cl["leads"] = [l for l in cl["leads"] if l in _VALID_LEADS]
                elif "leads" in cl:
                    cl.pop("leads")
                # coerce an out-of-vocabulary source_type; "measured" w/o threshold → curated_label.
                if cl.get("source_type") not in {"measured", "curated_label", "authored_context"}:
                    cl["source_type"] = "curated_label"
                if cl.get("source_type") == "measured" and not cl.get("threshold"):
                    cl["source_type"] = "curated_label"
                for k in list(cl):
                    if k not in _CLAIM:
                        cl.pop(k)
        for k in list(em):
            if k not in _MANIFEST:
                em.pop(k)
    opts = data.get("options")
    if isinstance(opts, list):
        for o in opts:
            if isinstance(o, dict):
                _strip_qmarks(o)
                if o.get("value") is not None and not isinstance(o["value"], str):
                    o["value"] = str(o["value"])
                if isinstance(o.get("required_safety_tokens"), list):
                    o["required_safety_tokens"] = [t for t in o["required_safety_tokens"] if t in _VALID_SAFETY_TOKENS]
                for k in list(o):
                    if k not in _OPTION:
                        o.pop(k)
    ds2 = data.get("display_spec")
    if isinstance(ds2, dict):
        _strip_qmarks(ds2)
        for k in list(ds2):
            if k not in {"mode", "pinned_strip_lead", "zoom_lead", "tested_scope"}:
                ds2.pop(k)
    return data


def parse_draft(raw: str | dict[str, Any], ecg_id: str, situation: str, question_type: str) -> tuple[ClinicalCaseItem | None, str | None]:
    """Returns (item, error). error is 'unparseable' (bad JSON) or 'schema:<msg>' (validation)."""
    try:
        data = json.loads(raw) if isinstance(raw, str) else dict(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None, "unparseable"
    if not isinstance(data, dict):
        return None, "unparseable"
    data = _normalize_draft(data)
    data.setdefault("item_id", f"gen-{ecg_id}-{question_type}")
    data["ecg_id"] = ecg_id
    data.setdefault("situation", situation)
    data.setdefault("question_type", question_type)
    data["provenance"] = "nano_generated"
    data["validation_status"] = "draft"
    # A drafting model won't reliably emit option/line ids; assign them deterministically.
    for idx, opt in enumerate(data.get("options", []) or []):
        if isinstance(opt, dict):
            opt.setdefault("id", f"o{idx}")
    for idx, line in enumerate(data.get("machine_read", []) or []):
        if isinstance(line, dict):
            line.setdefault("id", f"m{idx}")
    try:
        return ClinicalCaseItem.model_validate(data), None
    except ValidationError as exc:
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(p) for p in first.get("loc", []))
        return None, f"schema:{loc}:{first.get('msg', '')}"[:80]


_FOUNDATIONAL = {"rate", "sinus_rhythm", "axis_normal", "qt_interval", "normal_ecg"}


def _ground_manifest(item: ClinicalCaseItem, packet: dict[str, Any]) -> ClinicalCaseItem:
    """Lock the safety-critical ecg_supports to the curation: keep only the model's claims that
    are in supported_objectives, as `curated_label` (drop model-invented thresholds — the model
    writes "79 bpm"/"QTc ~421 ms" which aren't bound). Prefer PATHOLOGY concepts and cap at 4, so
    the item credits what it actually drills (not "rate/axis") — this is what the mastery loop
    rewards. Prose overclaims are still caught by the harness's text checks."""
    from .schemas import EvidenceClaim

    supported = supported_objectives(packet)
    claimed: list[str] = []
    for claim in item.evidence_manifest.ecg_supports:
        if claim.objective_id in supported and claim.objective_id not in claimed:
            claimed.append(claim.objective_id)
    pathology = [c for c in claimed if c not in _FOUNDATIONAL]
    chosen = (pathology or claimed)[:4]
    if not chosen and supported:
        chosen = [sorted(supported)[0]]
    item.evidence_manifest.ecg_supports = [EvidenceClaim(objective_id=c, source_type="curated_label") for c in chosen]
    return item


_ROI_CLICK_LABEL = {
    "pr_interval": "PR interval", "qrs_complex": "QRS complex", "st_segment": "ST segment",
    "t_wave": "T wave", "qt_segment": "QT interval", "p_wave": "P wave",
}
# Nonspecific concepts must NOT be chosen over a specific one with the same ROI (round-4 audit).
_LOW_SPECIFICITY = {"nonspecific_st_t_change", "nonspecific_intraventricular_conduction_delay"}
# Concept → what to tell the learner to click (names the abnormality, not just the segment).
_CLICK_INSTRUCTION = {
    "av_block_first_degree": "the prolonged PR interval (P-wave onset to QRS onset)",
    "st_depression": "a depressed ST segment", "st_elevation": "an elevated ST segment",
    "t_wave_inversion": "an inverted T wave", "qtc_prolongation": "the QT interval", "qt_interval": "the QT interval",
    "right_bundle_branch_block": "the wide QRS complex", "left_bundle_branch_block": "the wide QRS complex",
    "qrs_duration": "the wide QRS complex", "left_ventricular_hypertrophy": "the high-voltage QRS complex",
    "pathologic_q_waves": "a pathologic Q wave",
}


def _template_click(item: ClinicalCaseItem, packet: dict[str, Any]) -> ClinicalCaseItem | None:
    """Click items can't be safely model-authored (the ROI target must match real geometry), so WE
    set it deterministically: pick the MOST SPECIFIC supported concept whose neutral ROI is grounded,
    point the click there, name the abnormality in the prompt, and keep only the model's clinical stem.
    Returns None if nothing specific is clickable."""
    from .schemas import DisplaySpec, EvidenceClaim, RoiTarget

    supported = supported_objectives(packet)
    present = {r.get("concept") for r in rois(packet)}
    # pathology first, then specific-over-nonspecific
    order = sorted(supported, key=lambda c: (c in _FOUNDATIONAL, c in _LOW_SPECIFICITY))
    chosen = chosen_roi = None
    for concept in order:
        roi_concept = CONCEPT_TO_ROI.get(concept)
        if roi_concept and roi_concept in present:
            chosen, chosen_roi = concept, roi_concept
            break
    if not chosen:
        return None
    leads = sorted({r.get("lead") for r in rois(packet) if r.get("concept") == chosen_roi})
    lead = next((l for l in ("II", "V2", "V5") if l in leads), leads[0] if leads else "II")
    item.roi_target = RoiTarget(concept=chosen, leads=[lead], target_type="interval")
    item.options = []
    item.steps = []
    item.machine_read = []
    instruction = _CLICK_INSTRUCTION.get(chosen, "the " + _ROI_CLICK_LABEL.get(chosen_roi, chosen.replace("_", " ")))
    item.prompt = f"Click {instruction}."
    item.tested_scope = "zoom_lead"
    item.display_spec = DisplaySpec(mode="zoom_lead", zoom_lead=lead, tested_scope="zoom_lead")
    item.evidence_manifest.ecg_supports = [EvidenceClaim(objective_id=chosen, source_type="curated_label")]
    return item


# --- deterministic triage answer-class derivation (round-4 audit fixed an inversion bug) ---
_TRIAGE_RANK = {"routine": 0, "workup": 1, "act": 2}
# Only ACTUAL harmful interventions on a stable patient are unsafe; "resuscitation/monitoring
# escalation" is over-triage, not harmful (round-4 audit's distinction).
_HARMFUL_ACT = ("pacing", "cardiovert", "intubat", "transvenous", "defibrillat", "atropine")


def _derive_triage_classes(item: ClinicalCaseItem) -> ClinicalCaseItem:
    """Triage `value` (routine<workup<act) is an action INTENSITY; answer_class is RELATIVE to the
    ideal. The model conflates them, so derive classes deterministically: higher-intensity-than-ideal
    = over_triage_safe (or unsafe if it's an actual harmful intervention), lower = under_triage
    (or unsafe if it discharges a non-low-acuity finding)."""
    ideal = next((o for o in item.options if o.answer_class == "ideal"), None)
    if not ideal or (ideal.value or "").lower() not in _TRIAGE_RANK:
        return item
    irank = _TRIAGE_RANK[(ideal.value or "").lower()]
    for o in item.options:
        if o is ideal:
            continue
        rank = _TRIAGE_RANK.get((o.value or "").lower())
        if rank is None:
            continue
        low = o.text.lower()
        if rank > irank:
            o.answer_class = "unsafe" if any(t in low for t in _HARMFUL_ACT) else "over_triage_safe"
        elif rank < irank:
            o.answer_class = "unsafe" if ("discharge" in low and item.acuity_tier in {"moderate", "moderate_high", "high"}) else "under_triage"
    return item


def generate_and_vet(
    packet: dict[str, Any],
    situation: str,
    question_type: str,
    provider: Any,
    prior_packet: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Draft via the provider, then gate on the harness. Returns the verdict for batch
    convergence measurement: {accepted, reason, item, report}."""
    messages = build_messages(packet, situation, question_type)
    gen_ctx = {"mode": "clinical_gen", "casePacket": packet}
    try:
        # Prefer overriding the provider's default (tutor) system prompt with the generation
        # prompt; the mock provider doesn't accept that kwarg, so fall back.
        try:
            raw = provider.generate(messages, gen_ctx, system_prompt=CLINICAL_GEN_SYSTEM_PROMPT)
        except TypeError:
            raw = provider.generate(messages, gen_ctx)
    except Exception as exc:  # provider/network failure is a (recorded) rejection
        return {"accepted": False, "reason": f"provider_error:{type(exc).__name__}", "item": None, "report": None}
    item, parse_error = parse_draft(raw, str(packet.get("case_id")), situation, question_type)
    if item is None:
        return {"accepted": False, "reason": parse_error or "unparseable", "item": None, "report": None}
    item = _ground_manifest(item, packet)
    if question_type == "click":
        item = _template_click(item, packet)
        if item is None:
            return {"accepted": False, "reason": "no_clickable_roi", "item": None, "report": None}
    elif question_type == "triage":
        item = _derive_triage_classes(item)
    report: HarnessReport = run_harness(item, packet, prior_packet)
    if report.passed:
        item.validation_status = "harness_pass"  # served only as automated-screened formative content
        return {"accepted": True, "reason": None, "item": item, "report": report}
    return {"accepted": False, "reason": "harness:" + ",".join(report.failing_checks()), "item": item, "report": report}


REALIZE_SYSTEM_PROMPT = """You write ONE board-style ECG decision MCQ as STRICT JSON — SURFACE REALIZATION ONLY.
You are given: a clinical_frame, patient age/sex, the ECG's primary_finding + other_findings (all on a
RESTING / CHRONIC 12-lead ECG — findings are ESTABLISHED, not acute), the real measurements, and an ordered
list `actions_to_paraphrase`.
Write:
1. "stem": a varied, realistic 2-3 sentence clinical vignette that uses the clinical_frame and patient.
   CENTER it on the primary_finding (as a resting/established finding). You MAY mention at most ONE
   other_finding briefly as an incidental/background detail — do NOT enumerate a list of diagnoses, and
   never let another finding compete with or overshadow the primary_finding. Do NOT use acute/evolving/
   sudden/"spreading" language. Do NOT state which action is correct. VARY your wording — do not sound
   templated. You may state the given measurements accurately; do NOT invent numbers that were not provided.
2. "options": rewrite EACH action in actions_to_paraphrase, IN THE SAME ORDER, as a natural clinically-worded
   management option. Keep each action's MEANING exactly. Vary the wording; do NOT copy verbatim. NEVER add
   words that signal correctness (no "despite","solely","unnecessary","inappropriately","obviously","incorrectly").
Output ONLY JSON: {"stem":"...","options":["...", ...]} with options.length == actions_to_paraphrase.length."""


def _sanitized_demo(packet: dict[str, Any]) -> tuple[int | None, str | None]:
    meta = (packet.get("ptbxl") or {}).get("metadata") or {}
    raw_age = meta.get("age")
    age = raw_age if isinstance(raw_age, (int, float)) and 0 < raw_age <= 95 else None
    sex = {0: "male", 1: "female", "0": "male", "1": "female", "M": "male", "F": "female"}.get(meta.get("sex"))
    return (int(age) if age is not None else None), sex


def generate_skeleton_and_vet(
    packet: dict[str, Any], concept: str, provider: Any, situation: str, seed: int = 0,
    prior_packet: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Two-layer generation: a DETERMINISTIC option skeleton (correct classes from the action library,
    rotated by seed for variety) + LLM SURFACE realization (varied vignette + paraphrased options)."""
    from ..ontology import concept_label
    from .action_library import select_frame, select_options
    from .schemas import DisplaySpec, EvidenceClaim, EvidenceManifest, Option, StemChips

    actions = select_options(concept, seed)
    if len(actions) < 3:
        return {"accepted": False, "reason": "insufficient_actions", "item": None, "report": None}
    frame = select_frame(seed)
    age, sex = _sanitized_demo(packet)
    feats = features(packet)
    ctx = {
        "clinical_frame": frame,
        "patient": {"age": age, "sex": sex},
        "primary_finding": concept_label(concept),
        # At most ONE meaningful incidental finding — a targeted decision item shouldn't enumerate a
        # laundry-list of diagnoses (that buries the concept under test and reads unrealistically).
        # Foundational/nonspecific labels are background, not worth naming.
        "other_findings": [
            concept_label(c) for c in sorted(supported_objectives(packet))
            if c != concept and c not in _FOUNDATIONAL and c not in _LOW_SPECIFICITY
        ][:1],
        "measurements": {k: feats.get(k) for k in ("heart_rate", "pr_ms", "qrs_ms", "qtc_ms", "axis_deg") if feats.get(k) is not None},
        "actions_to_paraphrase": [intent for _, intent in actions],
    }
    messages = [{"role": "system", "content": REALIZE_SYSTEM_PROMPT}, {"role": "user", "content": json.dumps(ctx)}]
    try:
        try:
            raw = provider.generate(messages, {"mode": "clinical_realize"}, system_prompt=REALIZE_SYSTEM_PROMPT)
        except TypeError:
            raw = provider.generate(messages, {"mode": "clinical_realize"})
    except Exception as exc:
        return {"accepted": False, "reason": f"provider_error:{type(exc).__name__}", "item": None, "report": None}
    try:
        data = json.loads(raw) if isinstance(raw, str) else dict(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return {"accepted": False, "reason": "unparseable", "item": None, "report": None}
    stem = (data or {}).get("stem")
    opts = (data or {}).get("options")
    if not isinstance(stem, str) or not isinstance(opts, list) or len(opts) != len(actions):
        return {"accepted": False, "reason": "realize_shape", "item": None, "report": None}
    options = [Option(id=f"o{i}", text=str(opts[i]).strip(), answer_class=cls) for i, (cls, _) in enumerate(actions)]
    item = ClinicalCaseItem(
        item_id=f"gen-{packet.get('case_id')}-{concept}-{seed}", ecg_id=str(packet.get("case_id")),
        situation=situation, question_type="mcq", acuity_tier=ACUITY_BASE.get(concept, "low"),
        stem=stem.strip(), chips=StemChips(age=age, setting=situation), prompt="Most appropriate next step?",
        options=options,
        evidence_manifest=EvidenceManifest(
            ecg_supports=[EvidenceClaim(objective_id=concept, source_type="curated_label")],
            action_rationale=actions[0][1], epistemic_status="determined",
        ),
        tested_scope="full_12_lead",
        display_spec=DisplaySpec(mode="twelve_lead_pinned_strip", pinned_strip_lead="II", tested_scope="full_12_lead"),
        provenance="nano_generated", validation_status="draft",
    )
    report: HarnessReport = run_harness(item, packet, prior_packet)
    if report.passed:
        item.validation_status = "harness_pass"
        return {"accepted": True, "reason": None, "item": item, "report": report}
    return {"accepted": False, "reason": "harness:" + ",".join(report.failing_checks()), "item": item, "report": report}


def measure_convergence(
    packets: list[dict[str, Any]],
    situation: str,
    question_type: str,
    provider: Any,
) -> dict[str, Any]:
    """Run the generator over many packets and report the reject rate + failing-check histogram."""
    results = [generate_and_vet(p, situation, question_type, provider) for p in packets]
    accepted = [r for r in results if r["accepted"]]
    reasons: dict[str, int] = {}
    for r in results:
        if not r["accepted"]:
            reasons[r["reason"]] = reasons.get(r["reason"], 0) + 1
    # Diversity: distinct (ecg_id, question_type) signatures among accepted. If << accepted, the
    # bank is filling with near-duplicates (same tracing, same type) — variety is bounded by the
    # distinct real ECGs available per concept.
    signatures = {(r["item"].ecg_id, r["item"].question_type) for r in accepted}
    return {
        "attempts": len(results),
        "accepted": len(accepted),
        "accept_rate": round(len(accepted) / len(results), 3) if results else 0.0,
        "distinct_signatures": len(signatures),
        "reject_reasons": reasons,
        "items": [r["item"] for r in accepted],
    }
