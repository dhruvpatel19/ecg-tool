from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator


LEADS = ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]
TUTOR_MESSAGE_MAX_CHARS = 4_000
TUTOR_VIEWER_STATE_MAX_BYTES = 32 * 1024


def validate_tutor_viewer_state(value: dict[str, Any]) -> dict[str, Any]:
    """Keep user-controlled prompt context small enough for safe remote use."""

    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > TUTOR_VIEWER_STATE_MAX_BYTES:
        raise ValueError(
            f"viewerState must be at most {TUTOR_VIEWER_STATE_MAX_BYTES} UTF-8 bytes"
        )
    return value


Tier = Literal["A", "B", "C", "D"]
SignalQualityStatus = Literal["acceptable", "borderline", "poor"]


class ConceptConfidence(BaseModel):
    score: float = Field(ge=0, le=1)
    tier: Tier
    evidence: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class WaveformSummary(BaseModel):
    path: str | None = None
    sampling_frequency: int = 100
    duration_sec: float = 10
    leads: list[str] = Field(default_factory=lambda: LEADS.copy())
    source: str = "fixture"


class SignalQuality(BaseModel):
    status: SignalQualityStatus = "acceptable"
    reasons: list[str] = Field(default_factory=list)


class ViewerAction(BaseModel):
    type: Literal[
        "zoom",
        "highlightLead",
        "highlightROI",
        "circleROI",
        "drawCaliper",
        "showFiducial",
        "resetView",
    ]
    leads: list[str] | None = None
    lead: str | None = None
    timeStart: float | None = None
    timeEnd: float | None = None
    ampMin: float | None = None
    ampMax: float | None = None
    timeSec: float | None = None
    label: str | None = None

    model_config = {"extra": "forbid"}

    @field_validator("lead")
    @classmethod
    def known_lead(cls, value: str | None) -> str | None:
        if value is not None and value not in LEADS:
            raise ValueError(f"Unknown ECG lead: {value}")
        return value

    @field_validator("leads")
    @classmethod
    def known_leads(cls, value: list[str] | None) -> list[str] | None:
        if value is not None:
            unknown = [lead for lead in value if lead not in LEADS]
            if unknown:
                raise ValueError(f"Unknown ECG leads: {', '.join(unknown)}")
        return value

    @model_validator(mode="after")
    def required_fields(self) -> "ViewerAction":
        if self.type == "resetView":
            return self
        if self.type == "zoom" and not self.leads:
            raise ValueError("zoom requires leads")
        if self.type in {"highlightLead", "highlightROI", "circleROI", "drawCaliper", "showFiducial"} and not self.lead:
            raise ValueError(f"{self.type} requires lead")
        if self.type in {"zoom", "highlightROI", "circleROI", "drawCaliper"}:
            if self.timeStart is None or self.timeEnd is None:
                raise ValueError(f"{self.type} requires timeStart and timeEnd")
            if self.timeEnd <= self.timeStart:
                raise ValueError("timeEnd must be greater than timeStart")
        if self.type == "showFiducial" and self.timeSec is None:
            raise ValueError("showFiducial requires timeSec")
        if self.type == "highlightROI":
            if self.ampMin is None or self.ampMax is None:
                raise ValueError("highlightROI requires ampMin and ampMax")
            if self.ampMax <= self.ampMin:
                raise ValueError("ampMax must be greater than ampMin")
        return self


class ObjectiveUpdate(BaseModel):
    objective: str
    delta: float = Field(ge=-1, le=1)
    reason: str


class TutorResponse(BaseModel):
    tutorMessage: str
    feedback: str = ""
    viewerActions: list[ViewerAction] = Field(default_factory=list)
    objectiveUpdates: list[ObjectiveUpdate] = Field(default_factory=list)
    misconceptions: list[str] = Field(default_factory=list)
    uncertaintyWarnings: list[str] = Field(default_factory=list)
    suggestedNextStep: str = ""
    # Conversational / tutorial fields
    socraticQuestion: str = ""
    citedEvidence: list[str] = Field(default_factory=list)
    onLessonTopic: bool = True

    model_config = {"extra": "forbid"}


def _sanitize_tutor_payload(payload: Any) -> Any:
    """Salvage a real-LLM response: drop malformed list entries instead of failing the
    whole response. Cheap nano models sometimes emit viewerActions/objectiveUpdates as
    bare strings (e.g. "highlightLead", "sinus_rhythm") rather than objects; we keep only
    the entries that individually validate so the tutorMessage/feedback still survive."""
    if not isinstance(payload, dict):
        return payload
    clean = dict(payload)

    def keep_valid(items: Any, model: type[BaseModel]) -> list[dict[str, Any]]:
        valid: list[dict[str, Any]] = []
        for item in items if isinstance(items, list) else []:
            if isinstance(item, dict):
                try:
                    model.model_validate(item)
                    valid.append(item)
                except ValidationError:
                    continue
        return valid

    if "viewerActions" in clean:
        clean["viewerActions"] = keep_valid(clean["viewerActions"], ViewerAction)
    if "objectiveUpdates" in clean:
        clean["objectiveUpdates"] = keep_valid(clean["objectiveUpdates"], ObjectiveUpdate)
    for key in ("misconceptions", "uncertaintyWarnings", "citedEvidence"):
        if isinstance(clean.get(key), list):
            clean[key] = [s for s in clean[key] if isinstance(s, str)]
    return clean


def validate_tutor_response(raw: str | dict[str, Any]) -> tuple[TutorResponse, str | None]:
    try:
        payload = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        return _tutor_fallback(str(exc)), str(exc)
    # First try strict; if it fails, salvage the well-formed parts before giving up.
    try:
        return TutorResponse.model_validate(payload), None
    except (ValidationError, TypeError, ValueError):
        pass
    try:
        return TutorResponse.model_validate(_sanitize_tutor_payload(payload)), None
    except (ValidationError, TypeError, ValueError) as exc:
        return _tutor_fallback(str(exc)), str(exc)


def _tutor_fallback(error: str) -> TutorResponse:
    return TutorResponse(
        tutorMessage="I could not validate the tutor response, so I am falling back to grounded feedback.",
        feedback="Review the deterministic teaching points and case packet evidence before making claims.",
        uncertaintyWarnings=[error],
        suggestedNextStep="Try the next guided prompt or submit a narrower question.",
    )


class StructuredInterpretation(BaseModel):
    framework: Literal["clerkship", "hearts"] = "clerkship"
    rate: str = ""
    rhythm: str = ""
    axis: str = ""
    intervals: str = ""
    conduction: str = ""
    st_t: str = ""
    hypertrophy: str = ""
    synthesis: str = ""
    selectedConcepts: list[str] = Field(default_factory=list)


class AttemptRequest(BaseModel):
    learnerId: str = "demo"
    caseId: str
    mode: Literal["rapid_practice", "concept_practice", "tutorial"] = "rapid_practice"
    structuredAnswer: StructuredInterpretation = Field(default_factory=StructuredInterpretation)
    freeTextAnswer: str = Field(default="", max_length=6_000)
    confidence: int = Field(default=3, ge=1, le=5)
    hintsUsed: int = Field(default=0, ge=0)
    focusObjective: str | None = None
    assessmentScope: Literal["full_read", "dominant_finding"] = "full_read"


class TutorChatRequest(BaseModel):
    learnerId: str = Field(default="demo", max_length=160)
    mode: str = Field(default="rapid_practice", max_length=80)
    lessonId: str | None = Field(default=None, max_length=160)
    caseId: str | None = Field(default=None, max_length=240)
    learnerMessage: str = Field(default="", max_length=TUTOR_MESSAGE_MAX_CHARS)
    viewerState: dict[str, Any] = Field(default_factory=dict)
    structuredAnswer: StructuredInterpretation | None = None

    _bounded_viewer_state = field_validator("viewerState")(validate_tutor_viewer_state)


LearningSubskill = Literal[
    "recognize",
    "localize",
    "measure",
    "discriminate",
    "explain_mechanism",
    "synthesize",
    "apply_in_context",
    "calibrate_confidence",
]


class GuidedLearningEventRequest(BaseModel):
    learnerId: str = "demo"
    eventKey: str | None = Field(default=None, min_length=8, max_length=160)
    moduleId: str = Field(min_length=1, max_length=120)
    sceneId: str = Field(min_length=1, max_length=120)
    interactionId: str = Field(min_length=1, max_length=160)
    concept: str = Field(min_length=1, max_length=160)
    subskills: list[LearningSubskill] = Field(min_length=1)
    score: float = Field(ge=0, le=1)
    correct: bool
    attempts: int = Field(ge=1)
    assistance: Literal["independent", "scaffolded"]
    hintsUsed: int = Field(default=0, ge=0)
    confidence: int | None = Field(default=None, ge=1, le=5)
    evidenceLevel: Literal["exposure", "guided", "independent_transfer"] = "guided"
    # Training receipts carry an explicit phase and evidence source so the
    # server can enforce the independent-transfer boundary. These fields are
    # optional for the guided curriculum and older clients.
    trainingPhase: Literal["target", "mimic", "negative", "transfer"] | None = None
    evidenceSource: Literal[
        "response",
        "trace_native",
        "labeled_contrast_task",
        "curated_mechanism_task",
        "confidence_commit",
        "structured_sweep",
    ] = "response"
    caseId: str | None = None
    caseProvenance: Literal["real_eligible", "real_reviewed", "authored_simulation", "contrast_only", "none"] = "none"
    caseEligible: bool = False
    misconceptions: list[str] = Field(default_factory=list)


PathwaySceneStatus = Literal[
    "not-started", "viewed", "attempted", "needs-review", "complete", "skipped"
]


class PathwayProgressItem(BaseModel):
    pathwayId: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9_.:-]+$")
    moduleId: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9_.:-]+$")
    sceneId: str = Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9_.:-]+$")
    status: PathwaySceneStatus
    activeInteractionIndex: int = Field(default=0, ge=0, le=500)
    completedActionIds: list[str] = Field(default_factory=list, max_length=250)
    state: dict[str, Any] = Field(default_factory=dict)

    @field_validator("completedActionIds")
    @classmethod
    def bounded_action_ids(cls, value: list[str]) -> list[str]:
        if any(not item or len(item) > 160 for item in value):
            raise ValueError("completed action ids must be 1-160 characters")
        return list(dict.fromkeys(value))


class PathwayProgressUpsertRequest(BaseModel):
    learnerId: str = "demo"
    items: list[PathwayProgressItem] = Field(min_length=1, max_length=500)
    source: Literal["server", "guest_import"] = "server"
    merge: bool = True
