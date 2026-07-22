"""Owner-bound, post-completion reconstruction of submitted learning items.

The ordinary learning-session review intentionally remains answer-free.  This
module provides a separate, lazy read model for learners who explicitly open a
completed item.  It never returns raw answer rows: every response is projected
through a small allowlist and every ECG is addressed by a payload-free,
owner/attempt-bound capability.
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import parse_qs

from .assessment_presentation import assessment_display_id
from .clinical.provenance import assert_learner_item_provenance
from .clinical.shift import blind_clinical_item
from .ecg_capability import issue_ecg_capability, matches_ecg_capability
from .learning_sessions import _resolve_completed_session
from .objectives import objective_definition
from .ontology import PRACTICE_GROUPS, concept_label
from .subskill_tasks import build_subskill_task
from .training_routes import (
    TRAINING_CLASSIFICATION_CONTRACT_VERSION,
    TRAINING_QUESTION_SNAPSHOT_VERSION,
    build_training_classification_contract,
    training_task_concept,
)


REPLAY_VERSION = "learning-session-replay-v1"
REPLAY_CAPABILITY_MODE = "learning-review"
_TOKEN = re.compile(r"^[A-Za-z0-9_-]{1,120}$")
_STRUCTURED_FIELDS = (
    "framework",
    "rate",
    "rhythm",
    "axis",
    "intervals",
    "conduction",
    "st_t",
    "hypertrophy",
    "synthesis",
)


PacketProvider = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class LearningReplayAttempt:
    mode: str
    session_id: str
    source_answer_id: int
    attempt_index: int
    canonical_ecg_id: str
    submitted_at: str
    data: dict[str, Any]

    @property
    def capability_scope(self) -> str:
        return f"{self.mode}:{self.session_id}:{self.source_answer_id}"


def _json_object(value: object) -> dict[str, Any] | None:
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _text(value: object, limit: int = 6_000) -> str:
    return str(value)[:limit] if isinstance(value, str) else ""


def _optional_text(value: object, limit: int = 6_000) -> str | None:
    text = _text(value, limit).strip()
    return text or None


def _token(value: object) -> str | None:
    return str(value) if isinstance(value, str) and _TOKEN.fullmatch(value) else None


def _number(value: object, *, minimum: float | None = None, maximum: float | None = None) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    if minimum is not None and parsed < minimum:
        return None
    if maximum is not None and parsed > maximum:
        return None
    return parsed


def _integer(value: object, *, minimum: int = 0, maximum: int = 10_000_000) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if minimum <= parsed <= maximum else None


def _score(value: object) -> float | None:
    parsed = _number(value, minimum=0.0, maximum=1.0)
    return round(parsed, 4) if parsed is not None else None


def _tokens(values: object, *, maximum: int = 24) -> list[str]:
    if not isinstance(values, list):
        return []
    return [token for value in values[:maximum] if (token := _token(value)) is not None]


def _texts(values: object, *, maximum: int = 24, limit: int = 500) -> list[str]:
    if not isinstance(values, list):
        return []
    return [text for value in values[:maximum] if (text := _optional_text(value, limit))]


def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _resolve_training_attempt(
    conn: sqlite3.Connection, session_id: str, attempt_index: int
) -> LearningReplayAttempt | None:
    rows = conn.execute(
        """
        SELECT answers.id AS source_answer_id, answers.ordinal, answers.case_id,
               answers.response_json, answers.grade_json, answers.summary_json,
               answers.created_at, campaigns.status AS session_status,
               campaigns.concept_id, campaigns.subskill, campaigns.context_key,
               slots.phase, slots.case_focus
        FROM training_campaign_answers AS answers
        JOIN training_campaigns AS campaigns
          ON campaigns.campaign_id = answers.campaign_id
        LEFT JOIN training_campaign_slots AS slots
          ON slots.campaign_id = answers.campaign_id
         AND slots.ordinal = answers.ordinal
        WHERE answers.campaign_id = ?
          AND answers.integrity_status IN ('atomic_v1', 'atomic_v2')
        ORDER BY answers.ordinal, answers.id
        """,
        (session_id,),
    ).fetchall()
    if attempt_index < 1 or attempt_index > len(rows):
        return None
    row = rows[attempt_index - 1]
    response = _json_object(row["response_json"])
    grade = _json_object(row["grade_json"])
    summary = _json_object(row["summary_json"])
    if response is None or grade is None or summary is None:
        return None
    case_id = str(row["case_id"] or "")
    if not case_id:
        return None
    data = _row_dict(row)
    data.update({"response": response, "grade": grade, "summary": summary})
    return LearningReplayAttempt(
        mode="training",
        session_id=session_id,
        source_answer_id=int(row["source_answer_id"]),
        attempt_index=attempt_index,
        canonical_ecg_id=case_id,
        submitted_at=str(row["created_at"]),
        data=data,
    )


def _resolve_rapid_attempt(
    conn: sqlite3.Connection, session_id: str, attempt_index: int
) -> LearningReplayAttempt | None:
    rows = conn.execute(
        """
        SELECT answers.id AS source_answer_id, answers.case_id,
               answers.response_json, answers.grade_json, answers.result_json,
               answers.trace_grade_json, answers.tested_manifest_json,
               answers.created_at, rounds.status AS session_status,
               rounds.pace, rounds.assessment_scope,
               rounds.focus_concept, rounds.focus_subskill
        FROM rapid_round_answers AS answers
        JOIN rapid_rounds AS rounds ON rounds.round_id = answers.round_id
        WHERE answers.round_id = ?
          AND answers.integrity_status IN ('atomic_v1', 'atomic_v2')
        ORDER BY answers.id
        """,
        (session_id,),
    ).fetchall()
    if attempt_index < 1 or attempt_index > len(rows):
        return None
    row = rows[attempt_index - 1]
    response = _json_object(row["response_json"])
    grade = _json_object(row["grade_json"])
    result = _json_object(row["result_json"])
    manifest = _json_object(row["tested_manifest_json"])
    trace_grade = (
        _json_object(row["trace_grade_json"])
        if row["trace_grade_json"] is not None
        else None
    )
    if response is None or grade is None or result is None or manifest is None:
        return None
    case_id = str(row["case_id"] or "")
    if not case_id:
        return None
    data = _row_dict(row)
    data.update(
        {
            "response": response,
            "grade": grade,
            "result": result,
            "manifest": manifest,
            "traceGrade": trace_grade,
        }
    )
    return LearningReplayAttempt(
        mode="rapid",
        session_id=session_id,
        source_answer_id=int(row["source_answer_id"]),
        attempt_index=attempt_index,
        canonical_ecg_id=case_id,
        submitted_at=str(row["created_at"]),
        data=data,
    )


def _resolve_clinical_attempt(
    conn: sqlite3.Connection, session_id: str, attempt_index: int
) -> LearningReplayAttempt | None:
    rows = conn.execute(
        """
        SELECT answers.id AS source_answer_id, answers.item_id, answers.ecg_id,
               answers.response_json, answers.grade_json, answers.score,
               answers.correct, answers.answer_time_ms, answers.created_at,
               sessions.status AS session_status, sessions.lane, sessions.tier
        FROM clinical_shift_answers AS answers
        JOIN clinical_shift_sessions AS sessions
          ON sessions.session_id = answers.session_id
        WHERE answers.session_id = ?
        ORDER BY answers.id
        """,
        (session_id,),
    ).fetchall()
    if attempt_index < 1 or attempt_index > len(rows):
        return None
    row = rows[attempt_index - 1]
    response = _json_object(row["response_json"])
    grade = _json_object(row["grade_json"])
    if response is None or grade is None:
        return None
    case_id = str(row["ecg_id"] or "")
    item_id = str(row["item_id"] or "")
    if not case_id or not item_id:
        return None
    data = _row_dict(row)
    data.update({"response": response, "grade": grade})
    return LearningReplayAttempt(
        mode="clinical",
        session_id=session_id,
        source_answer_id=int(row["source_answer_id"]),
        attempt_index=attempt_index,
        canonical_ecg_id=case_id,
        submitted_at=str(row["created_at"]),
        data=data,
    )


def resolve_learning_replay_attempt(
    conn: sqlite3.Connection,
    learner_id: str,
    *,
    session_secret: str,
    session_ref: str,
    attempt_index: int,
) -> LearningReplayAttempt | None:
    """Resolve one eligible answer only inside an owned completed session."""

    index = int(attempt_index)
    if index < 1 or index > 5000:
        return None
    session = _resolve_completed_session(
        conn,
        learner_id,
        secret=session_secret,
        session_ref=session_ref,
    )
    if session is None:
        return None
    mode = str(session["mode"])
    session_id = str(session["session_id"])
    if mode == "training":
        return _resolve_training_attempt(conn, session_id, index)
    if mode == "rapid":
        return _resolve_rapid_attempt(conn, session_id, index)
    if mode == "clinical":
        return _resolve_clinical_attempt(conn, session_id, index)
    return None


def issue_learning_replay_ecg_ref(
    attempt: LearningReplayAttempt,
    *,
    learner_id: str,
    capability_secret: str,
    canonical_ecg_id: str | None = None,
) -> str:
    return issue_ecg_capability(
        capability_secret,
        learner_id,
        REPLAY_CAPABILITY_MODE,
        attempt.capability_scope,
        canonical_ecg_id or attempt.canonical_ecg_id,
    )


def matches_learning_replay_ecg_ref(
    attempt: LearningReplayAttempt,
    reference: object,
    *,
    learner_id: str,
    capability_secret: str,
    canonical_ecg_id: str | None = None,
) -> bool:
    return matches_ecg_capability(
        reference,
        capability_secret,
        learner_id,
        REPLAY_CAPABILITY_MODE,
        attempt.capability_scope,
        canonical_ecg_id or attempt.canonical_ecg_id,
    )


def learning_replay_comparison_ecg_id(
    attempt: LearningReplayAttempt, *, clinical_item_store: Any
) -> str | None:
    """Resolve a Clinical comparison ECG only through its durable item key."""

    if attempt.mode != "clinical":
        return None
    item = clinical_item_store.get_item(str(attempt.data.get("item_id") or ""))
    if item is None or str(item.ecg_id) != attempt.canonical_ecg_id:
        return None
    prior_ecg_id = str(item.prior_ecg_id or "")
    if not prior_ecg_id or prior_ecg_id == attempt.canonical_ecg_id:
        return None
    return prior_ecg_id


def resolve_learning_replay_ecg_target(
    attempt: LearningReplayAttempt,
    reference: object,
    *,
    learner_id: str,
    capability_secret: str,
    clinical_item_store: Any,
) -> str | None:
    """Match one opaque replay capability to its current or comparison ECG."""

    candidates = [attempt.canonical_ecg_id]
    comparison_id = learning_replay_comparison_ecg_id(
        attempt, clinical_item_store=clinical_item_store
    )
    if comparison_id:
        candidates.append(comparison_id)
    return next(
        (
            canonical_id
            for canonical_id in candidates
            if matches_learning_replay_ecg_ref(
                attempt,
                reference,
                learner_id=learner_id,
                capability_secret=capability_secret,
                canonical_ecg_id=canonical_id,
            )
        ),
        None,
    )


def learning_replay_attempt_is_available(
    attempt: LearningReplayAttempt, *, repo: Any, clinical_item_store: Any
) -> bool:
    """Fail closed when current reconstruction dependencies no longer agree."""

    if not isinstance(repo.get_case(attempt.canonical_ecg_id), dict):
        return False
    if attempt.mode != "clinical":
        return True
    item = clinical_item_store.get_item(str(attempt.data.get("item_id") or ""))
    if item is None or str(item.ecg_id) != attempt.canonical_ecg_id:
        return False
    try:
        assert_learner_item_provenance(item, repo.get_case)
    except (KeyError, RuntimeError, TypeError, ValueError):
        return False
    prior_ecg_id = str(item.prior_ecg_id or "")
    return not prior_ecg_id or isinstance(repo.get_case(prior_ecg_id), dict)


def _contrast_family(concept: str) -> set[str]:
    if concept == "sinus_rhythm":
        return {
            "sinus_rhythm",
            "atrial_fibrillation",
            "atrial_flutter",
            "supraventricular_tachycardia",
            "paced_rhythm",
        }
    groups = [group for group in PRACTICE_GROUPS if concept in group.get("concepts", [])]
    selected = next(
        (group for group in groups if group.get("id") != "normal_ecg"),
        groups[0] if groups else None,
    )
    return set(selected.get("concepts", [])) if selected else {concept}


def _safe_task(task: object) -> dict[str, Any] | None:
    if not isinstance(task, dict):
        return None
    public: dict[str, Any] = {}
    for key in (
        "kind",
        "subskill",
        "variant",
        "prompt",
        "responseLabel",
        "unit",
        "minValue",
        "maxValue",
        "step",
        "required",
        "gradingBoundary",
        "frameworkVersion",
    ):
        if key in task and isinstance(task[key], (str, int, float, bool)):
            public[key] = task[key]
    for key in ("options", "choices"):
        rows = task.get(key)
        if isinstance(rows, list):
            public[key] = [
                {"id": _text(row.get("id"), 120), "label": _text(row.get("label"), 1_000)}
                for row in rows[:12]
                if isinstance(row, dict)
                and _text(row.get("id"), 120)
                and _text(row.get("label"), 1_000)
            ]
    rows = task.get("rows")
    if isinstance(rows, list):
        public["rows"] = [
            {"id": _text(row.get("id"), 120), "clause": _text(row.get("clause"), 1_000)}
            for row in rows[:12]
            if isinstance(row, dict)
            and _text(row.get("id"), 120)
            and _text(row.get("clause"), 1_000)
        ]
    framework_steps = task.get("frameworkSteps")
    if isinstance(framework_steps, list):
        public["frameworkSteps"] = []
        for row in framework_steps[:8]:
            if not isinstance(row, dict):
                continue
            key = _token(row.get("key"))
            label = _optional_text(row.get("label"), 200)
            prompt = _optional_text(row.get("prompt"), 1_000)
            placeholder = _optional_text(row.get("placeholder"), 1_000)
            if None in {key, label, prompt, placeholder}:
                continue
            step: dict[str, Any] = {
                "key": key,
                "label": label,
                "prompt": prompt,
                "placeholder": placeholder,
            }
            choices = _texts(row.get("choices"), maximum=12, limit=300)
            if choices:
                step["choices"] = choices
            public["frameworkSteps"].append(step)
    return public or None


def _safe_systematic_interpretation(value: object) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None
    keys = (
        "rate",
        "rhythm",
        "axis",
        "intervals",
        "conduction",
        "st_t",
        "hypertrophy",
        "synthesis",
    )
    interpretation = {
        key: _text(value.get(key), 2_000).strip()
        for key in keys
    }
    return interpretation if any(interpretation.values()) else None


def _safe_reviewed_framework(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, Any]] = []
    for row in value[:8]:
        if not isinstance(row, dict):
            continue
        key = _token(row.get("key"))
        label = _optional_text(row.get("label"), 200)
        review = _optional_text(row.get("review"), 2_000)
        grounded = row.get("grounded")
        if key is None or label is None or review is None or not isinstance(grounded, bool):
            continue
        rows.append(
            {"key": key, "label": label, "review": review, "grounded": grounded}
        )
    return rows


def _safe_training_question_snapshot(value: object) -> dict[str, Any] | None:
    """Project one frozen, answer-free Focused Practice question contract."""

    if (
        not isinstance(value, dict)
        or value.get("version") != TRAINING_QUESTION_SNAPSHOT_VERSION
    ):
        return None
    raw_classification = value.get("classification")
    if (
        not isinstance(raw_classification, dict)
        or raw_classification.get("version")
        != TRAINING_CLASSIFICATION_CONTRACT_VERSION
        or raw_classification.get("kind") != "single_choice"
        or not isinstance(raw_classification.get("required"), bool)
    ):
        return None
    prompt = _optional_text(raw_classification.get("prompt"), 2_000)
    raw_options = raw_classification.get("options")
    if prompt is None or not isinstance(raw_options, list) or len(raw_options) != 2:
        return None
    options = [
        {
            "id": _optional_text(row.get("id"), 120),
            "label": _optional_text(row.get("label"), 1_000),
        }
        for row in raw_options
        if isinstance(row, dict)
    ]
    if (
        len(options) != 2
        or any(row["id"] is None or row["label"] is None for row in options)
        or {row["id"] for row in options} != {"present", "absent"}
    ):
        return None
    labels_by_id = {str(row["id"]): str(row["label"]) for row in options}
    present_label = _optional_text(raw_classification.get("presentLabel"), 1_000)
    absent_label = _optional_text(raw_classification.get("absentLabel"), 1_000)
    if (
        present_label != labels_by_id["present"]
        or absent_label != labels_by_id["absent"]
    ):
        return None
    raw_task = value.get("task")
    task = _safe_task(raw_task)
    if raw_task is not None and task is None:
        return None
    return {
        "version": TRAINING_QUESTION_SNAPSHOT_VERSION,
        "classification": {
            "version": TRAINING_CLASSIFICATION_CONTRACT_VERSION,
            "kind": "single_choice",
            "prompt": prompt,
            "presentLabel": present_label,
            "absentLabel": absent_label,
            "options": options,
            "required": raw_classification["required"],
        },
        "task": task,
    }


def _safe_task_result(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    result: dict[str, Any] = {
        "kind": _optional_text(value.get("kind"), 80),
        "complete": bool(value.get("complete")),
        "correct": bool(value.get("correct")),
        "score": _score(value.get("score")),
    }
    for key in ("submittedAnswer", "correctAnswer", "unit"):
        result[key] = _optional_text(value.get(key), 160)
    for key in ("submittedValue", "expectedValue", "tolerance", "absoluteError"):
        result[key] = _number(value.get(key), minimum=0.0, maximum=100_000.0)
    rows = value.get("rows")
    if isinstance(rows, list):
        result["rows"] = [
            {
                "rowId": _optional_text(row.get("rowId"), 120),
                "submittedChoiceId": _optional_text(row.get("submittedChoiceId"), 120),
                "correctChoiceId": _optional_text(row.get("correctChoiceId"), 120),
                "correct": bool(row.get("correct")),
            }
            for row in rows[:12]
            if isinstance(row, dict)
        ]
    if isinstance(value.get("systematicInterpretationComplete"), bool):
        result["systematicInterpretationComplete"] = value[
            "systematicInterpretationComplete"
        ]
    systematic = _safe_systematic_interpretation(
        value.get("systematicInterpretation")
    )
    if systematic is not None:
        result["systematicInterpretation"] = systematic
    reviewed = _safe_reviewed_framework(value.get("reviewedFramework"))
    if reviewed:
        result["reviewedFramework"] = reviewed
    return result


def _training_review_domain(concept: str) -> tuple[str, list[str]]:
    """Mirror the reviewed Focused viewer domain without importing route internals."""

    if "lead_territor" in concept or "frontal_lead_map" in concept:
        return "qrs_complex", ["II", "III", "aVF"]
    if "axis" in concept:
        return "qrs_complex", ["I", "aVF"]
    if "bundle" in concept or "qrs" in concept or "conduction" in concept:
        return "qrs_complex", ["V1", "V6"]
    if "av_block" in concept or concept.startswith("pr_"):
        return "pr_interval", ["II"]
    if "qt" in concept:
        return "qt_segment", ["II", "V5"]
    if (
        any(token in concept for token in ("st_", "t_wave", "myocardial"))
        or concept.endswith("_mi")
    ):
        leads = (
            ["II", "III", "aVF"]
            if "inferior" in concept
            else ["I", "aVL", "V5", "V6"]
            if "lateral" in concept
            else ["V2", "V3", "V4"]
        )
        return ("t_wave" if "t_wave" in concept else "st_segment"), leads
    if any(token in concept for token in ("atrial", "sinus", "flutter")):
        return "p_wave", ["II"]
    if any(token in concept for token in ("hypertrophy", "enlargement", "r_wave")):
        return "qrs_complex", ["V1", "V5", "V6"]
    return "qrs_complex", ["II"]


def _packet_review_rois(packet: object) -> list[dict[str, Any]]:
    if not isinstance(packet, dict):
        return []
    plus = packet.get("ptbxl_plus")
    if not isinstance(plus, dict):
        return []
    fiducials = plus.get("fiducials")
    if not isinstance(fiducials, dict):
        return []
    rois = fiducials.get("rois")
    return [row for row in rois if isinstance(row, dict)] if isinstance(rois, list) else []


def _review_roi_geometry(roi: dict[str, Any]) -> dict[str, Any] | None:
    """Allowlist only coordinates that ECGViewer needs for a reviewed overlay."""

    lead = _optional_text(roi.get("lead"), 8)
    start = _number(roi.get("timeStartSec"), minimum=0.0, maximum=86_400.0)
    end = _number(roi.get("timeEndSec"), minimum=0.0, maximum=86_400.0)
    amp_min = _number(roi.get("ampMinMv"), minimum=-100.0, maximum=100.0)
    amp_max = _number(roi.get("ampMaxMv"), minimum=-100.0, maximum=100.0)
    if (
        lead is None
        or start is None
        or end is None
        or end <= start
        or amp_min is None
        or amp_max is None
    ):
        return None
    return {
        "lead": lead,
        "timeStart": start,
        "timeEnd": end,
        "ampMin": min(amp_min, amp_max),
        "ampMax": max(amp_min, amp_max),
    }


def _training_review_actions(
    attempt: LearningReplayAttempt, *, packet: object
) -> list[dict[str, Any]]:
    """Project bounded post-commit references for a missed trace-native task.

    These actions are a learner-facing redraw contract, not a grading record.
    Concept keys, ROI labels, provenance, confidence, and correctness fields are
    deliberately excluded from every returned action.
    """

    if attempt.mode != "training":
        return []
    data = attempt.data
    subskill = _token(data.get("subskill"))
    if subskill not in {"localize", "measure"}:
        return []
    summary = data.get("summary")
    grade = data.get("grade")
    response = data.get("response")
    if not isinstance(summary, dict) or not isinstance(grade, dict) or not isinstance(response, dict):
        return []
    evidence_correct = grade.get("trainingSubskillEvidenceCorrect")
    if evidence_correct is not False and summary.get("correct") is not False:
        return []
    if _safe_viewer_task_evidence(response.get("viewerTaskEvidence")) is None:
        return []

    campaign_concept = _token(data.get("concept_id")) or ""
    case_focus = _token(data.get("case_focus")) or campaign_concept
    review_concept = (
        campaign_concept
        if subskill == "measure" or response.get("expectedAnswer") == "present"
        else case_focus
    )
    segment, preferred_leads = _training_review_domain(review_concept)
    raw_rois = _packet_review_rois(packet)

    # Rate is measured between consecutive ventricular anchors rather than
    # across one component ROI. Use two reviewed QRS centers on the same lead.
    if subskill == "measure" and review_concept == "rate":
        for lead in preferred_leads:
            anchors: list[dict[str, Any]] = []
            for roi in raw_rois:
                if roi.get("concept") != "qrs_complex" or roi.get("lead") != lead:
                    continue
                geometry = _review_roi_geometry(roi)
                if geometry is not None:
                    anchors.append(geometry)
            anchors.sort(key=lambda row: float(row["timeStart"]))
            if len(anchors) >= 2:
                first = (float(anchors[0]["timeStart"]) + float(anchors[0]["timeEnd"])) / 2
                second = (float(anchors[1]["timeStart"]) + float(anchors[1]["timeEnd"])) / 2
                if second > first:
                    return [{
                        "type": "drawCaliper",
                        "lead": lead,
                        "timeStart": first,
                        "timeEnd": second,
                        "label": "Reviewed interval",
                    }]
        return []

    by_lead: dict[str, dict[str, Any]] = {}
    for roi in raw_rois:
        lead = _optional_text(roi.get("lead"), 8)
        if roi.get("concept") != segment or lead not in preferred_leads or lead in by_lead:
            continue
        geometry = _review_roi_geometry(roi)
        if geometry is not None:
            by_lead[lead] = geometry

    ordered = [by_lead[lead] for lead in preferred_leads if lead in by_lead]
    if subskill == "measure":
        return [
            {
                "type": "drawCaliper",
                "lead": geometry["lead"],
                "timeStart": geometry["timeStart"],
                "timeEnd": geometry["timeEnd"],
                "label": "Reviewed interval",
            }
            for geometry in ordered[:1]
        ]
    return [
        {
            "type": "highlightROI",
            **geometry,
            "label": "Reviewed localization",
        }
        for geometry in ordered[:2]
    ]


def _training_projection(
    attempt: LearningReplayAttempt,
    *,
    case: dict[str, Any],
    packet_provider: PacketProvider,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    data = attempt.data
    response = data["response"]
    grade = data["grade"]
    summary = data["summary"]
    concept = _token(data.get("concept_id")) or "unknown"
    subskill = _token(data.get("subskill")) or "unknown"
    context_values = parse_qs(str(data.get("context_key") or ""), keep_blank_values=False)
    requested_objective = _token(
        str((context_values.get("receiptConcept") or [concept])[0]).strip()
    ) or concept
    definition = objective_definition(requested_objective)
    if (
        definition is None
        or subskill not in definition.allowed_subskills
        or concept not in definition.case_concepts
    ):
        requested_objective = concept
        definition = objective_definition(requested_objective)
    case_focus = _token(data.get("case_focus")) or concept
    snapshot = _safe_training_question_snapshot(response.get("questionSnapshot"))
    if snapshot is not None:
        classification = snapshot["classification"]
        task = snapshot["task"]
    else:
        # Legacy rows predate persisted question contracts. Reconstruct them
        # deterministically from the same public builders used at launch.
        ordinal = int(data.get("ordinal") or 0)
        classification = build_training_classification_contract(concept, ordinal)
        task = None
        try:
            legacy_task_concept = training_task_concept(
                concept, subskill, requested_objective
            )
            contract = build_subskill_task(
                case_id=attempt.canonical_ecg_id,
                case_concept=legacy_task_concept,
                subskill=subskill,
                case_focus=case_focus,
                contrast_family=_contrast_family(concept),
                variant=ordinal,
                case_packet=packet_provider(case),
            )
            task = _safe_task(contract.public if contract else None)
        except (KeyError, TypeError, ValueError):
            task = None
    question = {
        "kind": "training",
        "prompt": classification["prompt"],
        "target": {
            "objectiveId": requested_objective,
            "objectiveLabel": (
                definition.label if definition is not None else concept_label(requested_objective)
            ),
            "caseConceptId": concept,
            "caseConceptLabel": concept_label(concept),
            "subskill": subskill,
        },
        "classificationOptions": classification["options"],
        "subskillTask": task,
    }
    selected_answer = response.get("selectedAnswer")
    expected_answer = response.get("expectedAnswer")
    submission = {
        "selectedAnswer": selected_answer if selected_answer in {"present", "absent"} else None,
        "hintsUsed": _integer(response.get("hintsUsed"), maximum=1_000),
        "evidenceNote": _text(response.get("evidenceNote")),
        "subskillTaskAnswer": _optional_text(response.get("subskillTaskAnswer"), 160),
        "subskillTaskMatches": {
            str(key)[:120]: str(value)[:120]
            for key, value in (response.get("subskillTaskMatches") or {}).items()
            if isinstance(key, str) and isinstance(value, str)
        }
        if isinstance(response.get("subskillTaskMatches"), dict)
        else {},
        "subskillTaskValue": _number(
            response.get("subskillTaskValue"), minimum=0.0, maximum=100_000.0
        ),
        "viewerTaskEvidence": _safe_viewer_task_evidence(
            response.get("viewerTaskEvidence")
        ),
    }
    systematic_interpretation = _safe_systematic_interpretation(
        response.get("structuredInterpretation")
    )
    if systematic_interpretation is not None:
        submission["structuredInterpretation"] = systematic_interpretation
    if subskill == "calibrate_confidence":
        submission["confidence"] = _integer(
            response.get("confidence"), minimum=1, maximum=5
        )
    task_result = _safe_task_result(grade.get("trainingSubskillTaskResult"))
    skill_correct = bool(summary.get("correct"))
    feedback = {
        # The selected skill is the scored Focused Practice construct. Keep
        # the generic pattern grader as a separately named explanation so a
        # correct measure/mechanism result cannot be presented as a failed
        # question merely because the first classification differed.
        "score": 1.0 if skill_correct else 0.0,
        "selectedSkillFeedback": (
            "The selected skill task was met."
            if skill_correct
            else "The selected skill task needs review."
        ),
        "patternFeedback": _text(grade.get("feedback"), 2_000),
        "classificationCorrect": bool(grade.get("trainingClassificationCorrect")),
        "skillCorrect": skill_correct,
        "misconceptions": _texts(summary.get("misconceptions"), limit=240),
    }
    answer_guide = {
        "expectedAnswer": expected_answer if expected_answer in {"present", "absent"} else None,
        "subskillTaskResult": task_result,
    }
    if task_result and "systematicInterpretationComplete" in task_result:
        answer_guide["systematicInterpretationComplete"] = task_result[
            "systematicInterpretationComplete"
        ]
    if task_result and task_result.get("reviewedFramework"):
        answer_guide["reviewedFramework"] = task_result["reviewedFramework"]
    return question, submission, feedback, answer_guide


def _safe_manifest(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"taskKind": None, "assessmentScope": None, "objectives": []}
    objectives = []
    for row in value.get("objectives") or []:
        if not isinstance(row, dict):
            continue
        objective = _token(row.get("objectiveId"))
        subskill = _token(row.get("subskill"))
        if objective and subskill:
            objectives.append(
                {
                    "objectiveId": objective,
                    "subskill": subskill,
                    "role": _optional_text(row.get("role"), 80),
                    "source": _optional_text(row.get("source"), 120),
                    "lapseEligible": bool(row.get("lapseEligible")),
                }
            )
    return {
        "taskKind": _optional_text(value.get("taskKind"), 80),
        "assessmentScope": _optional_text(value.get("assessmentScope"), 80),
        "objectives": objectives[:12],
    }


def _safe_structured_answer(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {field: "" for field in _STRUCTURED_FIELDS} | {"selectedConcepts": []}
    answer = {field: _text(value.get(field), 2_000) for field in _STRUCTURED_FIELDS}
    answer["selectedConcepts"] = _tokens(value.get("selectedConcepts"), maximum=8)
    return answer


def _safe_viewer_task_evidence(value: object) -> dict[str, Any] | None:
    """Project only learner-authored geometry needed to redraw a review mark."""

    if not isinstance(value, dict):
        return None
    mode = value.get("mode")
    if mode == "point":
        point = value.get("point")
        if not isinstance(point, dict):
            return None
        lead = _optional_text(point.get("lead"), 8)
        time_sec = _number(point.get("timeSec"), minimum=0.0, maximum=86_400.0)
        amplitude = _number(point.get("amplitudeMv"), minimum=-100.0, maximum=100.0)
        if lead is None or time_sec is None or amplitude is None:
            return None
        return {
            "mode": "point",
            "point": {
                "lead": lead,
                "timeSec": time_sec,
                "amplitudeMv": amplitude,
            },
        }
    if mode == "region":
        roi = value.get("roi")
        if not isinstance(roi, dict):
            return None
        lead = _optional_text(roi.get("lead"), 8)
        start = _number(roi.get("timeStartSec"), minimum=0.0, maximum=86_400.0)
        end = _number(roi.get("timeEndSec"), minimum=0.0, maximum=86_400.0)
        amp_min = _number(roi.get("ampMinMv"), minimum=-100.0, maximum=100.0)
        amp_max = _number(roi.get("ampMaxMv"), minimum=-100.0, maximum=100.0)
        if (
            lead is None
            or start is None
            or end is None
            or end <= start
            or amp_min is None
            or amp_max is None
        ):
            return None
        return {
            "mode": "region",
            "roi": {
                "lead": lead,
                "timeStartSec": start,
                "timeEndSec": end,
                "ampMinMv": min(amp_min, amp_max),
                "ampMaxMv": max(amp_min, amp_max),
                "label": "Your selected region",
                "concept": "learner_evidence",
                "source": "user",
                "confidence": "recorded",
            },
        }
    if mode == "caliper":
        lead = _optional_text(value.get("lead"), 8)
        start = _number(value.get("timeStartSec"), minimum=0.0, maximum=86_400.0)
        end = _number(value.get("timeEndSec"), minimum=0.0, maximum=86_400.0)
        value_ms = _number(value.get("valueMs"), minimum=0.001, maximum=86_400_000.0)
        if lead is None or start is None or end is None or end <= start or value_ms is None:
            return None
        return {
            "mode": "caliper",
            "lead": lead,
            "timeStartSec": start,
            "timeEndSec": end,
            "valueMs": value_ms,
        }
    return None


def _safe_trace(value: object) -> dict[str, Any] | None:
    evidence = _safe_viewer_task_evidence(value)
    if evidence is None:
        return None
    return evidence


def _safe_rapid_task_packet(value: object) -> dict[str, Any] | None:
    """Release the frozen mixed-v2 prompts without their private grade keys."""

    if not isinstance(value, dict) or value.get("version") != "rapid-task-packet-v1":
        return None
    display = value.get("display")
    if not isinstance(display, dict):
        return None
    display_kind = _token(display.get("kind"))
    if display_kind not in {
        "twelve_lead",
        "rhythm_strip",
        "lead_subset",
        "single_beat",
        "serial_compare",
    }:
        return None
    public_display: dict[str, Any] = {"kind": display_kind}
    leads = _texts(display.get("leads"), maximum=12, limit=8)
    if leads:
        public_display["leads"] = leads
    label = _optional_text(display.get("label"), 160)
    if label:
        public_display["label"] = label

    tasks: list[dict[str, Any]] = []
    scalar_text_fields = {
        "prompt": 2_000,
        "unit": 40,
        "placeholder": 300,
        "responseLabel": 300,
    }
    token_fields = ("bloomLevel", "topicId", "skillId", "subskill")
    for raw_task in (value.get("tasks") or [])[:5]:
        if not isinstance(raw_task, dict):
            continue
        task_id = _token(raw_task.get("id"))
        task_type = _token(raw_task.get("type"))
        prompt = _optional_text(raw_task.get("prompt"), 2_000)
        if not task_id or not task_type or not prompt:
            continue
        task: dict[str, Any] = {
            "id": task_id,
            "type": task_type,
            "prompt": prompt,
        }
        for key, limit in scalar_text_fields.items():
            text = _optional_text(raw_task.get(key), limit)
            if text is not None:
                task[key] = text
        for key in token_fields:
            token = _token(raw_task.get(key))
            if token is not None:
                task[key] = token
        for key in ("minValue", "maxValue", "step"):
            number = _number(
                raw_task.get(key), minimum=-100_000.0, maximum=100_000.0
            )
            if number is not None:
                task[key] = number
        if isinstance(raw_task.get("required"), bool):
            task["required"] = raw_task["required"]
        options = raw_task.get("options")
        if isinstance(options, list):
            task["options"] = [
                {"id": option_id, "label": option_label}
                for row in options[:12]
                if isinstance(row, dict)
                and (option_id := _token(row.get("id"))) is not None
                and (option_label := _optional_text(row.get("label"), 1_000))
                is not None
            ]
        tasks.append(task)
    if not tasks:
        return None
    packet: dict[str, Any] = {
        "version": "rapid-task-packet-v1",
        "display": public_display,
        "tasks": tasks,
    }
    estimated = _integer(value.get("estimatedSeconds"), minimum=1, maximum=3_600)
    if estimated is not None:
        packet["estimatedSeconds"] = estimated
    return packet


def _safe_rapid_task_responses(
    value: object, task_packet: dict[str, Any]
) -> dict[str, Any]:
    """Project only responses keyed to the immutable public task packet."""

    if not isinstance(value, dict):
        return {}
    safe: dict[str, Any] = {}
    for task in task_packet.get("tasks") or []:
        task_id = str(task.get("id") or "")
        task_type = str(task.get("type") or "")
        if not task_id or task_id not in value:
            continue
        raw = value[task_id]
        if task_type in {"numeric", "numeric_fill_in", "fill_in"}:
            number = _number(raw, minimum=-100_000.0, maximum=100_000.0)
            if number is not None:
                safe[task_id] = number
            continue
        if task_type in {"point_localization", "trace_point"}:
            point = raw.get("point") if isinstance(raw, dict) else None
            if isinstance(point, dict):
                lead = _optional_text(point.get("lead"), 8)
                time_sec = _number(point.get("timeSec"), minimum=0.0, maximum=86_400.0)
                amplitude = _number(
                    point.get("amplitudeMv"), minimum=-100.0, maximum=100.0
                )
                if lead is not None and time_sec is not None:
                    safe[task_id] = {
                        "point": {
                            "lead": lead,
                            "timeSec": time_sec,
                            "amplitudeMv": amplitude,
                        }
                    }
            continue
        if task_type == "full_interpretation" and isinstance(raw, dict):
            fields = {
                key: text
                for key in ("rate", "rhythm", "conduction", "stT", "impression")
                if (text := _optional_text(raw.get(key), 2_000)) is not None
            }
            if fields:
                safe[task_id] = fields
            continue
        if isinstance(raw, str):
            safe[task_id] = _text(raw)
        elif isinstance(raw, list):
            selected = _tokens(raw, maximum=12)
            if selected:
                safe[task_id] = selected
        elif isinstance(raw, dict):
            # Older clients wrapped choice/text responses in a single public
            # key. Keep those semantic values without copying arbitrary JSON.
            wrapped = {
                key: safe_value
                for key in (
                    "choiceId",
                    "optionId",
                    "value",
                    "answer",
                    "text",
                    "numericValue",
                )
                if (
                    (safe_value := _optional_text(raw.get(key), 6_000))
                    is not None
                )
            }
            if wrapped:
                safe[task_id] = wrapped
    return safe


def _safe_rapid_task_feedback(
    value: object, task_packet: dict[str, Any]
) -> list[dict[str, Any]]:
    """Release committed per-task outcomes through a bounded field allowlist."""

    if not isinstance(value, list):
        return []
    task_ids = {
        str(task.get("id") or "") for task in task_packet.get("tasks") or []
    }
    rows: list[dict[str, Any]] = []
    for raw in value[:5]:
        if not isinstance(raw, dict):
            continue
        task_id = _token(raw.get("taskId"))
        if not task_id or task_id not in task_ids:
            continue
        row: dict[str, Any] = {"taskId": task_id}
        for key in ("type", "topicId", "skillId", "objectiveId"):
            token = _token(raw.get(key))
            if token is not None:
                row[key] = token
        for key in ("complete", "correct", "timedOut", "formativeOnly", "noTarget"):
            if isinstance(raw.get(key), bool):
                row[key] = raw[key]
        score = _score(raw.get("score"))
        if score is not None:
            row["score"] = score
        for key, limit in {
            "feedback": 2_000,
            "referenceLabel": 500,
            "correctAnswer": 1_000,
            "correctChoiceId": 120,
            "unit": 40,
            "supportingFieldsEvidence": 120,
        }.items():
            text = _optional_text(raw.get(key), limit)
            if text is not None:
                row[key] = text
        for key in ("expectedValue", "tolerance", "absoluteError"):
            number = _number(raw.get(key), minimum=0.0, maximum=100_000.0)
            if number is not None:
                row[key] = number
        supporting = _texts(
            raw.get("supportingFieldsReviewed"), maximum=12, limit=120
        )
        if supporting:
            row["supportingFieldsReviewed"] = supporting
        matched_roi = raw.get("matchedRoi")
        if isinstance(matched_roi, dict):
            safe_roi: dict[str, Any] = {}
            for key in ("concept", "lead"):
                text = _optional_text(matched_roi.get(key), 120)
                if text is not None:
                    safe_roi[key] = text
            for key in ("start", "end", "startSec", "endSec"):
                number = _number(
                    matched_roi.get(key), minimum=0.0, maximum=86_400.0
                )
                if number is not None:
                    safe_roi[key] = number
            if safe_roi:
                row["matchedRoi"] = safe_roi
        rows.append(row)
    return rows


def _rapid_projection(
    attempt: LearningReplayAttempt,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    data = attempt.data
    response = data["response"]
    grade = data["grade"]
    result = data["result"]
    raw_manifest = data["manifest"]
    manifest = _safe_manifest(raw_manifest)
    scope = _optional_text(data.get("assessment_scope"), 80) or manifest["assessmentScope"]
    pace = _optional_text(data.get("pace"), 80)
    task_packet = _safe_rapid_task_packet(
        raw_manifest.get("taskPacket") if isinstance(raw_manifest, dict) else None
    )
    question: dict[str, Any] = {
        "kind": "rapid",
        "pace": pace,
        "assessmentScope": scope,
        "testedObjectiveManifest": manifest,
    }
    if task_packet is not None:
        question["taskPacket"] = task_packet
    else:
        question["prompt"] = (
            "Commit the dominant finding supported by this ECG."
            if scope == "dominant_finding"
            else "Complete the structured ECG interpretation and commit the findings supported by the tracing."
        )
    submission = {
        "structuredAnswer": _safe_structured_answer(response.get("structuredAnswer")),
        "freeTextAnswer": _text(response.get("freeTextAnswer")),
        "confidence": _integer(response.get("confidence"), minimum=1, maximum=5),
        "traceEvidence": _safe_trace(response.get("traceEvidence")),
    }
    if task_packet is not None:
        submission["taskResponses"] = _safe_rapid_task_responses(
            response.get("taskResponses"), task_packet
        )
    trace_grade = data.get("traceGrade") if isinstance(data.get("traceGrade"), dict) else None
    feedback = {
        "score": _score(result.get("score")),
        "feedback": _text(grade.get("feedback"), 2_000),
        "timedOut": bool(result.get("timedOut")),
        "responseMs": _integer(result.get("responseMs"), maximum=86_400_000),
        "trace": (
            {
                "correct": bool(trace_grade.get("correct")),
                "noTarget": bool(trace_grade.get("noTarget")),
                "feedback": _text(trace_grade.get("feedback"), 1_000),
            }
            if trace_grade is not None
            else None
        ),
    }
    if task_packet is not None:
        feedback["taskFeedback"] = _safe_rapid_task_feedback(
            grade.get("taskFeedback"), task_packet
        )
    answer_guide = {
        "correctObjectives": _tokens(result.get("correctObjectives")),
        "missedObjectives": _tokens(result.get("missedObjectives")),
        "overcalledObjectives": _tokens(result.get("overcalledObjectives")),
        "revealedDiagnosis": _optional_text(result.get("revealedDiagnosis"), 1_000),
    }
    return question, submission, feedback, answer_guide


def _safe_clinical_stage(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    prompt = _optional_text(value.get("prompt"), 2_000)
    if prompt is None:
        return None
    stage: dict[str, Any] = {
        "prompt": prompt,
        "options": [
            {"text": option_text}
            for option in (value.get("options") or [])[:12]
            if isinstance(option, dict)
            and (option_text := _optional_text(option.get("text"), 1_000))
            is not None
        ],
    }
    stage_kind = _token(value.get("stage_kind"))
    if stage_kind in {"ecg", "decision", "reassessment", "handoff"}:
        stage["stageKind"] = stage_kind
    for source_key, public_key, limit in (
        ("stage_title", "stageTitle", 500),
        ("elapsed_label", "elapsedLabel", 160),
        ("clinical_update", "clinicalUpdate", 2_000),
    ):
        text = _optional_text(value.get(source_key), limit)
        if text is not None:
            stage[public_key] = text
    data_points: list[dict[str, Any]] = []
    raw_points = value.get("data_points")
    for point in raw_points[:24] if isinstance(raw_points, list) else []:
        if not isinstance(point, dict):
            continue
        label = _optional_text(point.get("label"), 300)
        point_value = _optional_text(point.get("value"), 500)
        if label is None or point_value is None:
            continue
        public_point: dict[str, Any] = {"label": label, "value": point_value}
        detail = _optional_text(point.get("detail"), 1_000)
        if detail is not None:
            public_point["detail"] = detail
        trend = _token(point.get("trend"))
        if trend in {"up", "down", "stable", "new"}:
            public_point["trend"] = trend
        source = _token(point.get("source"))
        if source in {"source_metadata", "authored_simulation"}:
            public_point["source"] = source
        data_points.append(public_point)
    if data_points:
        stage["dataPoints"] = data_points
    return stage


def _clinical_question(item: Any) -> dict[str, Any]:
    public = blind_clinical_item(item, reveal_context=True)
    chips = public.get("chips") if isinstance(public.get("chips"), dict) else {}
    question: dict[str, Any] = {
        "kind": "clinical",
        "questionType": _optional_text(public.get("question_type"), 80),
        "situation": _optional_text(public.get("situation"), 80),
        "stem": _text(public.get("stem"), 4_000),
        "chips": {
            "age": _integer(chips.get("age"), maximum=130),
            "setting": _optional_text(chips.get("setting"), 200),
            "symptom": _optional_text(chips.get("symptom"), 300),
            "bp": _optional_text(chips.get("bp"), 80),
            "mentalStatus": _optional_text(chips.get("mental_status"), 200),
        },
        "prompt": _text(public.get("prompt"), 2_000),
        "options": [
            {
                "id": _text(row.get("id"), 120),
                "text": _text(row.get("text"), 2_000),
                "value": _optional_text(row.get("value"), 120),
            }
            for row in (public.get("options") or [])[:12]
            if isinstance(row, dict) and _text(row.get("id"), 120)
        ],
        "steps": [
            stage
            for step in (public.get("steps") or [])[:12]
            if (stage := _safe_clinical_stage(step)) is not None
        ],
        "clickableLeads": _texts(public.get("clickable_leads"), maximum=12, limit=8),
        "clickTargetType": _optional_text(public.get("click_target_type"), 80),
        "machineRead": [
            {"id": _text(row.get("id"), 120), "text": _text(row.get("text"), 1_000)}
            for row in (public.get("machine_read") or [])[:20]
            if isinstance(row, dict) and _text(row.get("id"), 120)
        ],
    }
    fill = public.get("fill_in_task")
    if isinstance(fill, dict):
        question["fillInTask"] = {
            "responseLabel": _text(fill.get("response_label"), 300),
            "unit": _optional_text(fill.get("unit"), 20),
            "minValue": _number(fill.get("min_value")),
            "maxValue": _number(fill.get("max_value")),
            "step": _number(fill.get("step"), minimum=0.0),
        }
    matching = public.get("matching_task")
    if isinstance(matching, dict):
        question["matchingTask"] = {
            "choices": [
                {"id": _text(row.get("id"), 120), "label": _text(row.get("label"), 1_000)}
                for row in (matching.get("choices") or [])[:12]
                if isinstance(row, dict)
            ],
            "rows": [
                {"id": _text(row.get("id"), 120), "clause": _text(row.get("clause"), 1_000)}
                for row in (matching.get("rows") or [])[:12]
                if isinstance(row, dict)
            ],
        }
    display = public.get("display_spec")
    if isinstance(display, dict):
        question["display"] = {
            "mode": _optional_text(display.get("mode"), 80),
            "pinnedStripLead": _optional_text(display.get("pinned_strip_lead"), 8),
            "zoomLead": _optional_text(display.get("zoom_lead"), 8),
            "testedScope": _optional_text(display.get("tested_scope"), 80),
        }
    return question


def _clinical_submission(response: dict[str, Any]) -> dict[str, Any]:
    click = response.get("click")
    safe_click = None
    if isinstance(click, dict):
        lead = _optional_text(click.get("lead"), 8)
        time_sec = _number(click.get("time_sec"), minimum=0.0, maximum=86_400.0)
        if lead and time_sec is not None:
            safe_click = {
                "lead": lead,
                "timeSec": time_sec,
                "amplitudeMv": _number(click.get("amplitude_mv"), minimum=-100.0, maximum=100.0),
            }
    matches = response.get("matches")
    return {
        "firstLookFinding": _optional_text(response.get("first_look_finding"), 120),
        "selectedOptionId": _optional_text(response.get("selected_option_id"), 120),
        "click": safe_click,
        "machineLineId": _optional_text(response.get("machine_line_id"), 120),
        "fillInValue": _number(response.get("fill_in_value"), minimum=0.0, maximum=5_000.0),
        "answerTimeMs": _integer(response.get("answer_time_ms"), maximum=86_400_000),
        "timedOut": bool(response.get("timed_out")),
        "stepAnswers": [
            value
            for raw in (response.get("step_answers") or [])[:24]
            if (value := _integer(raw, maximum=24)) is not None
        ],
        "matches": {
            str(key)[:120]: str(value)[:120]
            for key, value in (matches or {}).items()
            if isinstance(key, str) and isinstance(value, str)
        }
        if isinstance(matches, dict)
        else {},
    }


def _packet_features(packet: dict[str, Any]) -> dict[str, Any]:
    plus = packet.get("ptbxl_plus") or {}
    if not isinstance(plus, dict):
        return {}
    features = plus.get("features") if isinstance(plus.get("features"), dict) else {}
    measurements = plus.get("measurements") if isinstance(plus.get("measurements"), dict) else {}
    return {**features, **measurements}


def _clinical_answer_guide(item: Any, packet: dict[str, Any]) -> dict[str, Any]:
    expected_measurement = None
    if item.fill_in_task is not None:
        value = _number(
            _packet_features(packet).get(item.fill_in_task.expected_feature),
            minimum=0.0,
            maximum=100_000.0,
        )
        if value is not None:
            expected_measurement = {
                "value": value,
                "tolerance": float(item.fill_in_task.tolerance),
                "unit": item.fill_in_task.unit,
            }
    return {
        "recommendedOptionIds": [
            option.id
            for option in item.options
            if option.answer_class in {"ideal", "acceptable"}
        ],
        "correctStepAnswers": [
            [index for index, option in enumerate(step.options) if option.correct]
            for step in item.steps
        ],
        "correctMatches": (
            {row.id: row.correct_choice_id for row in item.matching_task.rows}
            if item.matching_task is not None
            else {}
        ),
        "expectedMeasurement": expected_measurement,
        "incorrectMachineLineIds": [line.id for line in item.machine_read if line.bad],
        "traceTarget": (
            {
                "concept": item.roi_target.concept,
                "leads": list(item.roi_target.leads),
            }
            if item.roi_target is not None
            else None
        ),
    }


def _safe_clinical_step_feedback(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    feedback: list[dict[str, Any]] = []
    for raw in value[:12]:
        if not isinstance(raw, dict):
            continue
        stage_index = _integer(raw.get("stageIndex"), maximum=24)
        if stage_index is None:
            continue
        row: dict[str, Any] = {"stageIndex": stage_index}
        for key in ("stageKind",):
            token = _token(raw.get(key))
            if token in {"ecg", "decision", "reassessment", "handoff"}:
                row[key] = token
        for key, limit in {
            "stageTitle": 500,
            "elapsedLabel": 160,
            "clinicalUpdate": 2_000,
            "prompt": 2_000,
            "learnerAnswer": 2_000,
            "supportedAnswer": 2_000,
            "explanation": 4_000,
        }.items():
            text = _optional_text(raw.get(key), limit)
            if text is not None:
                row[key] = text
        for key in ("learnerOptionIndex", "supportedOptionIndex"):
            index = _integer(raw.get(key), maximum=24)
            if index is not None:
                row[key] = index
        for key in ("correct", "selectionCorrect", "timedOut"):
            if isinstance(raw.get(key), bool):
                row[key] = raw[key]
        # These are the same explicitly sourced values shown in the episode
        # timeline. They are repeated in the committed grade so a replay stays
        # durable even if presentation code changes.
        data_points: list[dict[str, Any]] = []
        raw_points = raw.get("dataPoints")
        for point in raw_points[:24] if isinstance(raw_points, list) else []:
            if not isinstance(point, dict):
                continue
            label = _optional_text(point.get("label"), 300)
            point_value = _optional_text(point.get("value"), 500)
            source = _token(point.get("source"))
            if label is None or point_value is None or source not in {
                "source_metadata",
                "authored_simulation",
            }:
                continue
            public_point: dict[str, Any] = {
                "label": label,
                "value": point_value,
                "source": source,
            }
            detail = _optional_text(point.get("detail"), 1_000)
            if detail is not None:
                public_point["detail"] = detail
            trend = _token(point.get("trend"))
            if trend in {"up", "down", "stable", "new"}:
                public_point["trend"] = trend
            data_points.append(public_point)
        if data_points:
            row["dataPoints"] = data_points
        feedback.append(row)
    return feedback


def _safe_clinical_competency_outcomes(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    outcomes: list[dict[str, Any]] = []
    for raw in value[:36]:
        if not isinstance(raw, dict):
            continue
        concept = _token(raw.get("concept"))
        subskill = _token(raw.get("subskill"))
        score = _score(raw.get("score"))
        if concept is None or subskill is None or score is None:
            continue
        row: dict[str, Any] = {
            "concept": concept,
            "subskill": subskill,
            "score": score,
            "correct": bool(raw.get("correct")),
        }
        stage_index = _integer(raw.get("stageIndex"), maximum=24)
        row["stageIndex"] = stage_index
        stage_title = _optional_text(raw.get("stageTitle"), 500)
        if stage_title is not None:
            row["stageTitle"] = stage_title
        stage_kind = _token(raw.get("stageKind"))
        if stage_kind in {"ecg", "decision", "reassessment", "handoff"}:
            row["stageKind"] = stage_kind
        evidence_source = _token(raw.get("evidenceSource"))
        if evidence_source in {
            "clinical_step_server_grade",
            "clinical_action_server_grade",
        }:
            row["evidenceSource"] = evidence_source
        outcomes.append(row)
    return outcomes


def _clinical_projection(
    attempt: LearningReplayAttempt,
    *,
    case: dict[str, Any],
    clinical_item_store: Any,
    packet_provider: PacketProvider,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]] | None:
    item = clinical_item_store.get_item(str(attempt.data.get("item_id") or ""))
    if item is None or str(item.ecg_id) != attempt.canonical_ecg_id:
        return None
    response = attempt.data["response"]
    grade = attempt.data["grade"]
    packet = packet_provider(case)
    axes = grade.get("axisScores") if isinstance(grade.get("axisScores"), dict) else {}
    feedback = {
        "score": _score(attempt.data.get("score")),
        "correct": bool(attempt.data.get("correct")),
        "feedback": _text(grade.get("feedback"), 2_000),
        "teachingPoints": _texts(grade.get("teachingPoints"), maximum=12, limit=1_000),
        "axisScores": {
            token: score
            for key, value in axes.items()
            if (token := _token(key)) is not None and (score := _score(value)) is not None
        },
        "safetyFlags": _tokens(grade.get("safetyFlags"), maximum=12),
        "timedOut": bool(grade.get("timedOut")),
        "clinicalApplicationEvidence": _optional_text(
            grade.get("clinicalApplicationEvidence"), 120
        ),
        "stepFeedback": _safe_clinical_step_feedback(grade.get("stepFeedback")),
        "competencyOutcomes": _safe_clinical_competency_outcomes(
            grade.get("competencyOutcomes")
        ),
    }
    return (
        _clinical_question(item),
        _clinical_submission(response),
        feedback,
        _clinical_answer_guide(item, packet),
    )


def _waveform_replay_presentation(
    case: dict[str, Any],
) -> tuple[bool, dict[str, Any]]:
    waveform = case.get("waveform")
    available = bool(isinstance(waveform, dict) and waveform.get("leads"))
    leads = (
        [str(value) for value in waveform.get("leads") or [] if str(value)]
        if isinstance(waveform, dict)
        else []
    )
    eligibility = case.get("educational_eligibility") or {}
    rhythm_strip = bool(
        isinstance(eligibility, dict)
        and eligibility.get("educationalUse") == "rhythm_stream"
        and leads
    )
    return (
        available,
        (
            {"kind": "rhythm_strip", "leads": leads[:3]}
            if rhythm_strip
            else {"kind": "twelve_lead", "leads": []}
        ),
    )


def build_learning_replay(
    attempt: LearningReplayAttempt,
    *,
    learner_id: str,
    session_ref: str,
    capability_secret: str,
    repo: Any,
    packet_provider: PacketProvider,
    clinical_item_store: Any,
) -> dict[str, Any] | None:
    """Build one strict, identity-free reconstructed replay payload."""

    if not learning_replay_attempt_is_available(
        attempt,
        repo=repo,
        clinical_item_store=clinical_item_store,
    ):
        return None
    case = repo.get_case(attempt.canonical_ecg_id)
    if not isinstance(case, dict):
        return None
    comparison_ecg_id: str | None = None
    review_actions: list[dict[str, Any]] = []
    if attempt.mode == "training":
        projection = _training_projection(
            attempt, case=case, packet_provider=packet_provider
        )
        try:
            review_actions = _training_review_actions(
                attempt, packet=packet_provider(case)
            )
        except (KeyError, TypeError, ValueError):
            # A missing optional review anchor must not make the committed
            # question, learner response, or waveform unavailable.
            review_actions = []
        display_id = assessment_display_id("training", attempt.attempt_index)
        provenance = {
            "tracing": "real_deidentified_ecg",
            "learningEvidence": _optional_text(
                attempt.data["summary"].get("evidenceLevel"), 120
            )
            or "recorded_training_outcome",
        }
    elif attempt.mode == "rapid":
        projection = _rapid_projection(attempt)
        display_id = assessment_display_id("rapid", attempt.attempt_index)
        provenance = {
            "tracing": "real_deidentified_ecg",
            "learningEvidence": "independent_assessment",
        }
    elif attempt.mode == "clinical":
        clinical_projection = _clinical_projection(
            attempt,
            case=case,
            clinical_item_store=clinical_item_store,
            packet_provider=packet_provider,
        )
        if clinical_projection is None:
            return None
        projection = clinical_projection
        comparison_ecg_id = learning_replay_comparison_ecg_id(
            attempt, clinical_item_store=clinical_item_store
        )
        display_id = f"Clinical ECG {attempt.attempt_index:04d}"
        provenance = {
            "tracing": "real_deidentified_ecg",
            "context": "authored_simulation",
            "learningEvidence": "formative_only",
            "contentLabel": (
                (
                    "Authenticated same-patient ECG comparison · authored simulated "
                    "clinical timeline · formative only · pending named clinician sign-off"
                )
                if comparison_ecg_id
                else (
                    "Automated-screened authored vignette · real de-identified ECG · "
                    "formative only · pending named clinician sign-off"
                )
            ),
        }
        if comparison_ecg_id:
            provenance["comparison"] = "same_patient_time_ordered_real_ecgs"
    else:
        return None

    question, submission, feedback, answer_guide = projection
    session_status = (
        "abandoned"
        if attempt.mode == "rapid"
        and attempt.data.get("session_status") == "abandoned"
        else "complete"
    )
    ecg_ref = issue_learning_replay_ecg_ref(
        attempt,
        learner_id=learner_id,
        capability_secret=capability_secret,
    )
    waveform_available, waveform_presentation = _waveform_replay_presentation(case)
    comparison: dict[str, Any] | None = None
    if comparison_ecg_id:
        comparison_case = repo.get_case(comparison_ecg_id)
        if not isinstance(comparison_case, dict):
            return None
        comparison_available, comparison_presentation = (
            _waveform_replay_presentation(comparison_case)
        )
        comparison = {
            "role": "prior",
            "label": "Earlier comparison ECG",
            "ecgRef": issue_learning_replay_ecg_ref(
                attempt,
                learner_id=learner_id,
                capability_secret=capability_secret,
                canonical_ecg_id=comparison_ecg_id,
            ),
            "waveformAvailable": comparison_available,
            "waveformPresentation": comparison_presentation,
            "provenance": "same_patient_time_ordered_real_ecgs",
        }
    replay = {
        "version": REPLAY_VERSION,
        "fidelity": "reconstructed",
        "sessionRef": session_ref,
        "attemptIndex": attempt.attempt_index,
        "mode": attempt.mode,
        "sessionStatus": session_status,
        "displayId": display_id,
        "submittedAt": attempt.submitted_at,
        "ecgRef": ecg_ref,
        "waveformAvailable": waveform_available,
        "waveformPresentation": waveform_presentation,
        "comparison": comparison,
        "question": question,
        "submission": submission,
        "feedback": feedback,
        "answerGuide": answer_guide,
        "provenance": provenance,
    }
    if review_actions:
        replay["reviewActions"] = review_actions
    return replay


__all__ = [
    "LearningReplayAttempt",
    "build_learning_replay",
    "issue_learning_replay_ecg_ref",
    "learning_replay_comparison_ecg_id",
    "learning_replay_attempt_is_available",
    "matches_learning_replay_ecg_ref",
    "resolve_learning_replay_ecg_target",
    "resolve_learning_replay_attempt",
]
