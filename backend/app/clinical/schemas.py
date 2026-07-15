"""Pydantic models for Clinical Decisions items (the versioned item-bank contract).

Mirrors the design in ``docs/storyboard-clinical-case.md`` §16. Every model forbids
extra keys so a malformed (e.g. nano-generated) item fails loudly rather than
silently dropping fields. The *honesty* invariants (claims bind to grounding, acuity
≤ ceiling, etc.) are NOT enforced here — they live in :mod:`app.clinical.harness`,
which validates an item against its grounded packet. These models only enforce shape.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel

from ..schemas import LEADS
from .constants import SAFETY_TOKENS, SYMPTOMS

# Answer inputs accept camelCase JSON from the JS client while exposing snake_case
# attributes to the grader.
_CAMEL_IN = ConfigDict(extra="forbid", alias_generator=to_camel, populate_by_name=True)

# --- enums (Literal aliases, matching the codebase convention) --------------------
AcuityTier = Literal["none", "low", "moderate", "moderate_high", "high"]
ActionUrgency = Literal["routine", "workup", "admit", "urgent", "act_now"]
Strength = Literal["may_explain", "may_contextualize", "must_not_explain"]
AnswerClass = Literal[
    "ideal", "acceptable", "over_triage_safe", "under_triage", "unsafe", "insufficient_data"
]
QuestionType = Literal[
    "triage", "stepwise", "click", "spoterror", "fillin", "matching", "oldnew", "mcq"
]
Situation = Literal["clinic", "ward", "ed", "triage", "code"]
TestedScope = Literal["full_12_lead", "rhythm_only", "zoom_lead"]
SourceType = Literal["measured", "curated_label", "authored_context"]
MatchingSourceType = Literal["ecg_support", "authored_context", "unsupported_claim"]
EpistemicStatus = Literal["determined", "intentionally_underdetermined"]
DisplayMode = Literal[
    "twelve_lead",
    "twelve_lead_pinned_strip",
    "twelve_lead_machine_panel",
    "stacked_twelve_lead",
    "zoom_lead",
]
TargetType = Literal["point", "interval", "segment", "territory", "lead_panel"]
Provenance = Literal["hand_authored", "nano_generated"]
ValidationStatus = Literal["draft", "harness_pass", "clinician_reviewed", "vetted", "rejected"]

_FORBID = {"extra": "forbid"}


def _check_leads(value: list[str]) -> list[str]:
    unknown = [lead for lead in value if lead not in LEADS]
    if unknown:
        raise ValueError(f"Unknown ECG leads: {', '.join(unknown)}")
    return value


class EvidenceClaim(BaseModel):
    """One grounded thing the tracing shows (§16B4). Must bind to a curation objective.

    The harness asserts ``objective_id`` ∈ the packet's supported_objectives, evaluates
    ``threshold`` against the packet features, and (for a territory) requires a matching
    ROI in ``leads``. ``source_type`` records where the claim is anchored.
    """

    objective_id: str
    threshold: str | None = None  # e.g. "qrs_ms>=120"; evaluated vs ptbxl_plus.features
    leads: list[str] = Field(default_factory=list)
    roi_concept: str | None = None
    source_type: SourceType = "curated_label"

    model_config = _FORBID

    @field_validator("leads")
    @classmethod
    def _leads_known(cls, value: list[str]) -> list[str]:
        return _check_leads(value)


class EvidenceManifest(BaseModel):
    """The 3-layer manifest (§16B): what the ECG supports, what the stem adds, the action
    rationale, plus forbidden claims, the defensible range, and epistemic status."""

    ecg_supports: list[EvidenceClaim] = Field(default_factory=list)
    stem_adds: list[str] = Field(default_factory=list)
    action_rationale: str = ""
    forbidden_claims: list[str] = Field(default_factory=list)
    acceptable_range: list[str] = Field(default_factory=list)
    epistemic_status: EpistemicStatus = "determined"

    model_config = _FORBID


class ParsedComponents(BaseModel):
    """Result of compound-option parsing (§16A1). Computed by the harness if absent."""

    get_more_data: bool = False
    safety_action_present: bool = False
    safety_tokens: list[str] = Field(default_factory=list)
    action_delayed: bool = False

    model_config = _FORBID

    @field_validator("safety_tokens")
    @classmethod
    def _tokens_known(cls, value: list[str]) -> list[str]:
        unknown = [t for t in value if t not in SAFETY_TOKENS]
        if unknown:
            raise ValueError(f"Unknown safety tokens: {', '.join(unknown)}")
        return value


class Option(BaseModel):
    """A selectable answer for mcq/triage/stepwise-disposition/oldnew."""

    id: str
    text: str
    answer_class: AnswerClass
    value: str | None = None  # stable key for triage (act/workup/routine) / oldnew (old/new/cannot_determine)
    axis_scores: dict[str, float] = Field(default_factory=dict)
    required_safety_tokens: list[str] = Field(default_factory=list)
    parsed: ParsedComponents | None = None

    model_config = _FORBID

    @field_validator("required_safety_tokens")
    @classmethod
    def _tokens_known(cls, value: list[str]) -> list[str]:
        unknown = [t for t in value if t not in SAFETY_TOKENS]
        if unknown:
            raise ValueError(f"Unknown safety tokens: {', '.join(unknown)}")
        return value


class StepOption(BaseModel):
    text: str
    correct: bool

    model_config = _FORBID


class StepwiseStep(BaseModel):
    prompt: str
    options: list[StepOption]

    model_config = _FORBID


class MachineLine(BaseModel):
    """A line of the machine read for spot-the-error items."""

    id: str
    text: str
    bad: bool = False

    model_config = _FORBID


class StemChips(BaseModel):
    age: int | None = None
    setting: str | None = None
    symptom: str | None = None
    bp: str | None = None
    mental_status: str | None = None

    model_config = _FORBID

    @field_validator("symptom")
    @classmethod
    def _symptom_known(cls, value: str | None) -> str | None:
        if value is not None and value not in SYMPTOMS:
            raise ValueError(f"Unknown symptom: {value}")
        return value


class RoiTarget(BaseModel):
    """Click/measure target (§16A2 click items use ROI geometry, not answer classes)."""

    concept: str
    leads: list[str] = Field(default_factory=list)
    target_type: TargetType = "interval"

    model_config = _FORBID

    @field_validator("leads")
    @classmethod
    def _leads_known(cls, value: list[str]) -> list[str]:
        return _check_leads(value)


class FillInTask(BaseModel):
    """A unit-aware numeric evidence task graded from a grounded packet feature.

    ``expected_feature`` and ``tolerance`` are server-side key material.  The
    blinded transport exposes only the response label, unit, and input bounds.
    Keeping the target as a feature name (rather than copying a numeric answer
    into every item) binds grading to the exact ECG packet served to the learner.
    """

    response_label: str
    unit: Literal["ms", "bpm", "mV", "degrees"]
    objective_id: str
    expected_feature: Literal["qt_ms", "qtc_ms", "pr_ms", "qrs_ms", "heart_rate"]
    tolerance: float = Field(gt=0)
    min_value: float
    max_value: float
    step: float = Field(gt=0)

    model_config = _FORBID

    @model_validator(mode="after")
    def _valid_range(self) -> "FillInTask":
        if self.max_value <= self.min_value:
            raise ValueError("fill-in max_value must be greater than min_value")
        return self


class MatchingChoice(BaseModel):
    """One public evidence-boundary target in a Clinical matching task."""

    id: str = Field(min_length=1)
    label: str = Field(min_length=1)

    model_config = _FORBID


class MatchingRow(BaseModel):
    """One clause and its server-only evidence-boundary key.

    ``clause`` is learner-facing.  The remaining fields are deliberately kept
    on the server and bind the key to the exact packet manifest rather than to
    an unreviewed free-text interpretation.
    """

    id: str = Field(min_length=1)
    clause: str = Field(min_length=1)
    source_type: MatchingSourceType
    correct_choice_id: str = Field(min_length=1)
    source_reference: str = Field(min_length=1)
    objective_id: str | None = None

    model_config = _FORBID


class MatchingTask(BaseModel):
    """Accessible clause-to-source mapping task; no drag gesture is required."""

    choices: list[MatchingChoice]
    rows: list[MatchingRow]

    model_config = _FORBID

    @model_validator(mode="after")
    def _complete_bijection(self) -> "MatchingTask":
        if len(self.choices) != 3 or len(self.rows) != 3:
            raise ValueError("matching tasks require exactly three choices and three rows")
        choice_ids = [choice.id for choice in self.choices]
        row_ids = [row.id for row in self.rows]
        if len(set(choice_ids)) != len(choice_ids):
            raise ValueError("matching choice ids must be unique")
        if len(set(row_ids)) != len(row_ids):
            raise ValueError("matching row ids must be unique")
        keyed = [row.correct_choice_id for row in self.rows]
        if set(keyed) != set(choice_ids) or len(set(keyed)) != len(keyed):
            raise ValueError("matching rows must form a one-to-one mapping to every choice")
        source_types = {row.source_type for row in self.rows}
        if source_types != {"ecg_support", "authored_context", "unsupported_claim"}:
            raise ValueError("matching tasks require one ECG, one vignette, and one unsupported row")
        for row in self.rows:
            if row.source_type == "ecg_support" and not row.objective_id:
                raise ValueError("the ECG-support matching row requires an objective_id")
            if row.source_type != "ecg_support" and row.objective_id is not None:
                raise ValueError("only the ECG-support matching row may carry an objective_id")
        return self


class DisplaySpec(BaseModel):
    """What is on screen (§16E). Default is the full 12-lead."""

    mode: DisplayMode = "twelve_lead"
    pinned_strip_lead: str | None = None
    zoom_lead: str | None = None
    tested_scope: TestedScope = "full_12_lead"

    model_config = _FORBID

    @field_validator("pinned_strip_lead", "zoom_lead")
    @classmethod
    def _lead_known(cls, value: str | None) -> str | None:
        if value is not None and value not in LEADS:
            raise ValueError(f"Unknown ECG lead: {value}")
        return value


class DifficultyVector(BaseModel):
    """Hidden 5-dim difficulty (§16: difficulty is a vector, so Challenge needs no rewrite)."""

    rarity: float = 0.0
    subtlety: float = 0.0
    distractor_closeness: float = 0.0
    time_pressure: float = 0.0
    multi_step: float = 0.0

    model_config = _FORBID


class ClinicalClick(BaseModel):
    lead: str
    time_sec: float
    amplitude_mv: float = 0.0
    beat_index: int | None = None
    viewport_state: str | None = None

    model_config = _CAMEL_IN

    @field_validator("lead")
    @classmethod
    def _lead_known(cls, value: str) -> str:
        if value not in LEADS:
            raise ValueError(f"Unknown ECG lead: {value}")
        return value


class ClinicalAnswer(BaseModel):
    """A learner's submission for one item (the grader dispatches on the item type)."""

    selected_option_id: str | None = None
    first_look_finding: Literal[
        "normal_or_no_dominant_abnormality",
        "rate_or_rhythm",
        "conduction_or_interval",
        "st_t_or_ischemia",
        "chamber_or_voltage",
        "uncertain",
    ] | None = None
    first_look_confidence: Literal[2, 3, 5] | None = None
    click: ClinicalClick | None = None
    machine_line_id: str | None = None
    fill_in_value: float | None = Field(default=None, ge=0, le=5000)
    confidence: int | None = Field(default=None, ge=1, le=5)  # required in Shift, absent in Learn
    answer_time_ms: int | None = None
    confidence_time_ms: int | None = None  # logged separately from decision time (§16D)
    timed_out: bool = False
    step_answers: list[int] = Field(default_factory=list)
    matches: dict[str, str] = Field(default_factory=dict, max_length=3)

    model_config = _CAMEL_IN


class ClinicalCaseItem(BaseModel):
    item_id: str
    ecg_id: str
    prior_ecg_id: str | None = None  # old-or-new comparison
    situation: Situation
    question_type: QuestionType
    acuity_tier: AcuityTier
    stem: str
    chips: StemChips = Field(default_factory=StemChips)
    prompt: str = ""
    options: list[Option] = Field(default_factory=list)
    steps: list[StepwiseStep] = Field(default_factory=list)
    roi_target: RoiTarget | None = None
    fill_in_task: FillInTask | None = None
    matching_task: MatchingTask | None = None
    machine_read: list[MachineLine] = Field(default_factory=list)
    evidence_manifest: EvidenceManifest = Field(default_factory=EvidenceManifest)
    # Exact concepts whose downstream clinical use is deliberately assessed by
    # this vignette.  This is narrower than ``ecg_supports``: an ECG may carry a
    # rate or rhythm fact that grounds the case without the management question
    # actually testing application of every one of those facts.  The field is
    # server-only and drives formative concept x apply_in_context receipts.
    application_objectives: list[str] = Field(default_factory=list)
    # Author-controlled source of truth for facts the vignette gives away before
    # ECG interpretation. These objectives are never allowed to gain recognition
    # mastery from a management answer.
    disclosed_objectives: list[str] = Field(default_factory=list)
    tested_scope: TestedScope = "full_12_lead"
    display_spec: DisplaySpec = Field(default_factory=DisplaySpec)
    difficulty_vector: DifficultyVector = Field(default_factory=DifficultyVector)
    provenance: Provenance = "hand_authored"
    validation_status: ValidationStatus = "draft"

    model_config = _FORBID

    @model_validator(mode="after")
    def _disclosures_must_be_manifested(self) -> "ClinicalCaseItem":
        manifested = {claim.objective_id for claim in self.evidence_manifest.ecg_supports}
        invalid = set(self.disclosed_objectives) - manifested
        if invalid:
            raise ValueError(f"disclosed objectives are not in the ECG evidence manifest: {sorted(invalid)}")
        invalid_application = set(self.application_objectives) - manifested
        if invalid_application:
            raise ValueError(
                "application objectives are not in the ECG evidence manifest: "
                f"{sorted(invalid_application)}"
            )
        self.disclosed_objectives = list(dict.fromkeys(self.disclosed_objectives))
        self.application_objectives = list(dict.fromkeys(self.application_objectives))
        if self.question_type == "matching":
            if self.matching_task is None:
                raise ValueError("matching item requires a matching_task")
            if (
                self.options
                or self.steps
                or self.machine_read
                or self.roi_target is not None
                or self.fill_in_task is not None
            ):
                raise ValueError("matching item must expose only its matching response surface")
            if self.application_objectives:
                raise ValueError("matching evidence-boundary tasks are formative and carry no application objectives")
        elif self.matching_task is not None:
            raise ValueError("non-matching item carries a hidden matching_task key")
        return self
