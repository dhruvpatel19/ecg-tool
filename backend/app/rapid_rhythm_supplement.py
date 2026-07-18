"""Manifest-gated high-risk rhythm supplement for Rapid Practice.

The source adapter deliberately writes disconnected, single-channel packets.
This module is the separate learner-serving promotion boundary.  Only the
source-author-labelled ventricular rhythm families listed below are projected into an
explicit Rapid emergency-rhythm lane.  The projection can support recognition
and discrimination evidence, but it never turns a waveform label into pulse,
stability, arrest, shockability, medication, electricity, or management truth.

The optional supplement lives inside an immutable corpus release under
``rapid_rhythm_supplement/``.  Absence or any manifest/hash/count mismatch is a
normal fail-closed state: the ordinary 12-lead corpus remains available, while
the emergency-rhythm lane is not advertised or selected.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterator, Mapping

from .ingest.dangerous_arrhythmia import (
    EXTRACTION_VERSION,
    SOURCE_ID,
    signal_fingerprint,
)
from .source_policy import packet_allows_learning_evidence, packet_mode_policy
from .store.rhythm_stream_store import RhythmStreamStore
from .store.waveform_store import LocalWaveformStore


SUPPLEMENT_DIRECTORY = "rapid_rhythm_supplement"
RUNTIME_MANIFEST_NAME = "runtime-manifest.json"
RUNTIME_SCHEMA_VERSION = 1
RUNTIME_MAPPING_VERSION = "high-risk-ventricular-rhythm-v1"
RUNTIME_SCOPE = "rapid_emergency_rhythm"
RUNTIME_LEAD = "MLII"


@dataclass(frozen=True)
class RuntimeRhythmTarget:
    objective_id: str
    label: str
    report: str
    teaching_points: tuple[str, ...]


# The source's TdP label is intentionally projected to the observable rhythm
# class.  Torsades de pointes additionally requires preceding long-QT context,
# which is not contained in a two-second fragment.
RUNTIME_TARGETS: Mapping[str, RuntimeRhythmTarget] = {
    "VF": RuntimeRhythmTarget(
        "ventricular_fibrillation",
        "Ventricular fibrillation",
        "Ventricular fibrillation pattern in a source-author-labelled single-channel fragment.",
        (
            "The fragment supports rhythm recognition only; it does not establish pulse or cardiac arrest.",
            "Use a separately supplied patient state before applying any resuscitation pathway.",
        ),
    ),
    "VFL": RuntimeRhythmTarget(
        "ventricular_flutter",
        "Ventricular flutter",
        "Ventricular flutter pattern in a source-author-labelled single-channel fragment.",
        (
            "Ventricular flutter is a very rapid, organized ventricular rhythm pattern.",
            "A rhythm fragment alone does not establish perfusion, arrest, or treatment.",
        ),
    ),
    "VTHR": RuntimeRhythmTarget(
        "ventricular_tachycardia",
        "Ventricular tachycardia",
        "High-rate ventricular tachycardia in a source-author-labelled single-channel fragment.",
        (
            "Name the ventricular rhythm before using bedside information to assess stability.",
            "The ECG pattern cannot tell you whether a pulse is present.",
        ),
    ),
    "VTLR": RuntimeRhythmTarget(
        "ventricular_tachycardia",
        "Ventricular tachycardia",
        "Lower-rate ventricular tachycardia in a source-author-labelled single-channel fragment.",
        (
            "Rate does not remove the need to recognize the ventricular rhythm pattern.",
            "Pulse, perfusion, symptoms, and management require separate clinical data.",
        ),
    ),
    "VTTdP": RuntimeRhythmTarget(
        "polymorphic_ventricular_tachycardia",
        "Polymorphic ventricular tachycardia",
        (
            "Polymorphic ventricular tachycardia in a fragment carrying the source's torsades label; "
            "definitive torsades classification requires preceding long-QT evidence not present here."
        ),
        (
            "Describe the visible rhythm as polymorphic ventricular tachycardia.",
            "Reserve torsades de pointes for polymorphic VT with grounded preceding QT prolongation.",
        ),
    ),
}

RUNTIME_OBJECTIVE_IDS = frozenset(
    target.objective_id for target in RUNTIME_TARGETS.values()
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"rhythm supplement metadata is unreadable: {path.name}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"rhythm supplement metadata is not an object: {path.name}")
    return value


def _runtime_content_index_entry(packet: Mapping[str, Any]) -> str:
    """Bind each promoted label to the exact checksum-verified waveform.

    Counting targets and hashing waveform fingerprints independently would not
    detect a label swap between two fragments in the same target family.  The
    runtime index therefore commits the opaque case id, signal fingerprint,
    source rhythm code, and learner target as one indivisible row.
    """

    labels = packet.get("source_labels") or {}
    rhythm = labels.get("rhythm") if isinstance(labels, Mapping) else None
    code = str((rhythm or {}).get("rhythmCode") or "") if isinstance(rhythm, Mapping) else ""
    target = RUNTIME_TARGETS.get(code)
    case_id = str(packet.get("case_id") or "")
    fingerprint = str(packet.get("signal_fingerprint") or "")
    if target is None or not case_id or len(fingerprint) != 64:
        raise ValueError("rhythm packet cannot be bound to the runtime content index")
    return "\0".join((case_id, fingerprint, code, target.objective_id))


def build_runtime_manifest(
    *,
    source_manifest_path: Path,
    packets: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the immutable opt-in contract for one reviewed supplement."""

    source_manifest = _json(source_manifest_path)
    if (
        source_manifest.get("complete") is not True
        or source_manifest.get("sourceId") != SOURCE_ID
        or source_manifest.get("extractionVersion") != EXTRACTION_VERSION
        or int(source_manifest.get("fragmentCount") or 0) != len(packets)
        or source_manifest.get("currentRuntimeConnected") is not False
        or source_manifest.get("clinicalManagementEligible") is not False
        or source_manifest.get("shockabilityClassificationEligible") is not False
    ):
        raise ValueError("disconnected source manifest is not eligible for Rapid promotion")

    target_counts: dict[str, int] = {}
    source_code_counts: dict[str, int] = {}
    content_index_entries: list[str] = []
    for packet in packets:
        labels = packet.get("source_labels") or {}
        rhythm = labels.get("rhythm") if isinstance(labels, dict) else None
        eligibility = packet.get("educational_eligibility") or {}
        waveform = packet.get("waveform") or {}
        code = str((rhythm or {}).get("rhythmCode") or "") if isinstance(rhythm, dict) else ""
        target = RUNTIME_TARGETS.get(code)
        fingerprint = str(packet.get("signal_fingerprint") or "")
        if (
            target is None
            or packet.get("source") != SOURCE_ID
            or packet.get("current_student_serving_eligible") is not False
            or not isinstance(eligibility, dict)
            or eligibility.get("currentRuntimeModeConnected") is not False
            or eligibility.get("masteryEvidenceEligible") is not False
            or eligibility.get("clinicalManagementEligible") is not False
            or eligibility.get("treatmentOrActionSequenceEligible") is not False
            or eligibility.get("shockabilityClassificationEligible") is not False
            or not isinstance(waveform, dict)
            or waveform.get("leads") != [RUNTIME_LEAD]
            or waveform.get("isSingleModifiedLimbLeadII") is not True
            or len(fingerprint) != 64
        ):
            raise ValueError("source packet violates the reviewed Rapid promotion boundary")
        target_counts[target.objective_id] = target_counts.get(target.objective_id, 0) + 1
        source_code_counts[code] = source_code_counts.get(code, 0) + 1
        content_index_entries.append(_runtime_content_index_entry(packet))

    content_digest = hashlib.sha256()
    for entry in sorted(content_index_entries):
        content_digest.update(entry.encode("utf-8"))
    return {
        "schemaVersion": RUNTIME_SCHEMA_VERSION,
        "complete": True,
        "sourceId": SOURCE_ID,
        "sourceVersion": "1.0.0",
        "sourceExtractionVersion": EXTRACTION_VERSION,
        "mappingVersion": RUNTIME_MAPPING_VERSION,
        "runtimeScope": RUNTIME_SCOPE,
        "sourceManifestSha256": _sha256(source_manifest_path),
        "contentIndexSha256": content_digest.hexdigest(),
        "fragmentCount": len(packets),
        "sourceRhythmCodeCounts": dict(sorted(source_code_counts.items())),
        "learnerTargetCounts": dict(sorted(target_counts.items())),
        "singleLead": RUNTIME_LEAD,
        "recognitionEvidenceEligible": True,
        "discriminationEvidenceEligible": True,
        "clinicalCaseEligible": False,
        "hemodynamicContextAvailable": False,
        "stabilityInferenceEligible": False,
        "cardiacArrestInferenceEligible": False,
        "shockabilityClassificationEligible": False,
        "clinicalManagementEligible": False,
        "treatmentOrActionSequenceEligible": False,
        "actionQuestionsRequireSeparateAuthoredContext": True,
        "actionQuestionsFormativeOnly": True,
        "algorithmContext": {
            "name": "2025 American Heart Association Guidelines for CPR and ECC",
            "cardiacArrestAlgorithm": (
                "https://www.heart.org/-/media/CPR-Files/CPR-Guidelines-Files/"
                "2025-Algorithms/Algorithm-ACLS-CA-250527.pdf"
            ),
            "tachycardiaWithPulseAlgorithm": (
                "https://cpr.heart.org/-/media/CPR-Files/CPR-Guidelines-Files/"
                "2025-Algorithms/Algorithm-ACLS-Tachycardia-250514.pdf?sc_lang=en"
            ),
        },
    }


def project_runtime_packet(packet: dict[str, Any]) -> dict[str, Any]:
    """Project one disconnected source packet into the explicit Rapid lane."""

    labels = packet.get("source_labels") or {}
    rhythm = labels.get("rhythm") if isinstance(labels, dict) else None
    code = str((rhythm or {}).get("rhythmCode") or "") if isinstance(rhythm, dict) else ""
    target = RUNTIME_TARGETS.get(code)
    if target is None:
        raise ValueError("rhythm code is outside the reviewed emergency-rhythm release")

    projected = deepcopy(packet)
    projected["display_id"] = "Rapid emergency rhythm"
    projected["current_student_serving_eligible"] = True
    projected["clinical_stem"] = "Source-author-labelled single-channel rhythm fragment. Patient state is not supplied."
    projected["supported_objectives"] = [target.objective_id]
    projected["unsupported_objectives"] = []
    projected["concept_confidence"] = {
        target.objective_id: {
            "tier": "A",
            "score": 1.0,
            "evidence": ["source-author rhythm-fragment label mapped through a reviewed runtime contract"],
        }
    }
    projected["signal_quality"] = {
        "status": "acceptable",
        "source": "checksum-verified finite single-channel fragment",
    }
    projected["ptbxl"] = {
        "report": target.report,
        "diagnostic_superclass": [],
        "diagnostic_subclass": [],
    }
    projected["ptbxl_plus"] = {
        "fiducials": {"rois": []},
        "median_beats": None,
        "features": {},
        "measurements": {},
    }
    projected["inclusion_reasons"] = [
        "checksum-verified source-author rhythm label",
        "reviewed high-risk ventricular rhythm mapping",
        "explicit Rapid emergency-rhythm selection only",
    ]
    projected["exclusion_reasons"] = []
    projected["teaching_points"] = list(target.teaching_points)
    projected["source_labels"]["rhythm"].update(
        {
            "sourceCanonicalRhythmId": projected["source_labels"]["rhythm"].get(
                "canonicalRhythmId"
            ),
            "canonicalRhythmId": target.objective_id,
            "runtimeLabel": target.label,
        }
    )
    projected["educational_eligibility"].update(
        {
            "eligibleModes": ["rapid"],
            "eligibleSubskills": {
                target.objective_id: ["recognize", "discriminate"]
            },
            "currentRuntimeModeConnected": True,
            "runtimeScope": RUNTIME_SCOPE,
            "masteryEvidenceEligible": True,
            "clinicalCaseEligible": False,
            "clinicalManagementEligible": False,
            "hemodynamicContextAvailable": False,
            "stabilityInferenceEligible": False,
            "cardiacArrestInferenceEligible": False,
            "shockabilityClassificationEligible": False,
            "treatmentOrActionSequenceEligible": False,
            "actionQuestionsRequireSeparateAuthoredContext": True,
            "actionQuestionsFormativeOnly": True,
        }
    )
    projected["rapid_formative_context"] = {
        "algorithmVersion": "2025 AHA CPR and ECC",
        "patientStateSource": "separately_authored_simulation",
        "managementEvidenceEligible": False,
    }

    if not packet_mode_policy(projected, "rapid").allowed:
        raise ValueError("promoted rhythm packet failed the shared Rapid source policy")
    for subskill in ("recognize", "discriminate"):
        if not packet_allows_learning_evidence(
            projected, "rapid", target.objective_id, subskill
        ).allowed:
            raise ValueError("promoted rhythm packet failed its exact evidence policy")
    if packet_allows_learning_evidence(
        projected, "rapid", target.objective_id, "apply_in_context"
    ).allowed:
        raise ValueError("rhythm packet unexpectedly permits management evidence")
    return projected


class RapidRhythmSupplement:
    """Read-only optional supplement embedded in an immutable corpus release."""

    def __init__(self, root: str | Path, *, expected: Mapping[str, Any] | None = None):
        self.root = Path(root)
        self.source_manifest_path = self.root / "manifest.json"
        self.runtime_manifest_path = self.root / RUNTIME_MANIFEST_NAME
        self.database_path = self.root / "rhythm_streams.db"
        self.waveform_root = self.root / "waveforms"
        for required in (
            self.source_manifest_path,
            self.runtime_manifest_path,
            self.database_path,
        ):
            if not required.is_file():
                raise ValueError(f"rhythm supplement is incomplete: {required.name}")
        if not self.waveform_root.is_dir():
            raise ValueError("rhythm supplement is missing waveforms")

        self.source_manifest = _json(self.source_manifest_path)
        self.runtime_manifest = _json(self.runtime_manifest_path)
        if (
            self.runtime_manifest.get("schemaVersion") != RUNTIME_SCHEMA_VERSION
            or self.runtime_manifest.get("complete") is not True
            or self.runtime_manifest.get("sourceId") != SOURCE_ID
            or self.runtime_manifest.get("mappingVersion") != RUNTIME_MAPPING_VERSION
            or self.runtime_manifest.get("runtimeScope") != RUNTIME_SCOPE
            or self.runtime_manifest.get("sourceManifestSha256")
            != _sha256(self.source_manifest_path)
            or self.runtime_manifest.get("singleLead") != RUNTIME_LEAD
            or self.runtime_manifest.get("recognitionEvidenceEligible") is not True
            or self.runtime_manifest.get("discriminationEvidenceEligible") is not True
            or self.runtime_manifest.get("clinicalCaseEligible") is not False
            or self.runtime_manifest.get("hemodynamicContextAvailable") is not False
            or self.runtime_manifest.get("stabilityInferenceEligible") is not False
            or self.runtime_manifest.get("cardiacArrestInferenceEligible") is not False
            or self.runtime_manifest.get("clinicalManagementEligible") is not False
            or self.runtime_manifest.get("shockabilityClassificationEligible") is not False
            or self.runtime_manifest.get("treatmentOrActionSequenceEligible") is not False
            or self.runtime_manifest.get("actionQuestionsRequireSeparateAuthoredContext") is not True
            or self.runtime_manifest.get("actionQuestionsFormativeOnly") is not True
        ):
            raise ValueError("rhythm supplement runtime manifest is invalid")
        if expected is not None:
            expected_hash = str(expected.get("runtimeManifestSha256") or "")
            expected_count = int(expected.get("fragmentCount") or 0)
            if (
                expected.get("path") != SUPPLEMENT_DIRECTORY
                or expected.get("sourceId") != SOURCE_ID
                or expected_hash != _sha256(self.runtime_manifest_path)
                or expected_count != int(self.runtime_manifest.get("fragmentCount") or 0)
            ):
                raise ValueError("corpus manifest and rhythm supplement do not match")

        self.store = RhythmStreamStore(self.database_path, read_only=True)
        self.waveforms = LocalWaveformStore(self.waveform_root, leads=(RUNTIME_LEAD,))
        self._packets: dict[str, dict[str, Any]] = {}
        self._candidates_by_objective: dict[str, list[dict[str, Any]]] = {}
        self._validate_and_index()

    def _validate_and_index(self) -> None:
        expected_count = int(self.runtime_manifest.get("fragmentCount") or 0)
        if expected_count <= 0 or self.store.count() != expected_count:
            raise ValueError("rhythm supplement database count does not match its manifest")
        target_counts: dict[str, int] = {}
        content_index_entries: list[str] = []
        for source_packet in self.store.iter_packets():
            packet = project_runtime_packet(source_packet)
            case_id = str(packet.get("case_id") or "")
            objective = str((packet.get("supported_objectives") or [""])[0])
            values = self.waveforms.read(case_id, (RUNTIME_LEAD,)).get(RUNTIME_LEAD) or []
            duration = float((packet.get("waveform") or {}).get("duration_sec") or 0)
            frequency = float((packet.get("waveform") or {}).get("sampling_frequency") or 0)
            if (
                not case_id
                or not objective
                or len(values) != round(duration * frequency)
                or len(values) < 2
                or not all(math.isfinite(float(value)) for value in values)
                or signal_fingerprint(values)
                != str(source_packet.get("signal_fingerprint") or "")
            ):
                raise ValueError("rhythm supplement contains an unreadable packet or waveform")
            self._packets[case_id] = packet
            summary = {
                "case_id": case_id,
                "source": SOURCE_ID,
                "teaching_tier": "A",
                "supported_objectives": [objective],
            }
            self._candidates_by_objective.setdefault(objective, []).append(summary)
            target_counts[objective] = target_counts.get(objective, 0) + 1
            content_index_entries.append(_runtime_content_index_entry(source_packet))

        digest = hashlib.sha256()
        for entry in sorted(content_index_entries):
            digest.update(entry.encode("utf-8"))
        if (
            dict(sorted(target_counts.items()))
            != self.runtime_manifest.get("learnerTargetCounts")
            or digest.hexdigest() != self.runtime_manifest.get("contentIndexSha256")
        ):
            raise ValueError("rhythm supplement content index does not match its manifest")
        for rows in self._candidates_by_objective.values():
            rows.sort(key=lambda row: str(row["case_id"]))

    @property
    def count(self) -> int:
        return len(self._packets)

    @property
    def target_counts(self) -> dict[str, int]:
        return {
            objective: len(rows)
            for objective, rows in sorted(self._candidates_by_objective.items())
        }

    def get_case(self, case_id: str) -> dict[str, Any] | None:
        packet = self._packets.get(str(case_id))
        return deepcopy(packet) if packet is not None else None

    def candidates(self, objective_id: str | None = None) -> list[dict[str, Any]]:
        if objective_id:
            return deepcopy(self._candidates_by_objective.get(str(objective_id), []))
        rows = [row for values in self._candidates_by_objective.values() for row in values]
        unique = {str(row["case_id"]): row for row in rows}
        return deepcopy([unique[key] for key in sorted(unique)])

    def iter_packets(self) -> Iterator[dict[str, Any]]:
        for case_id in sorted(self._packets):
            yield deepcopy(self._packets[case_id])

    def get_waveform_window(
        self,
        case_id: str,
        *,
        leads: list[str] | None = None,
        start: float = 0,
        end: float | None = None,
        max_points: int = 1200,
    ) -> dict[str, Any] | None:
        packet = self._packets.get(str(case_id))
        if packet is None:
            return None
        requested = list(leads or (RUNTIME_LEAD,))
        if requested != [RUNTIME_LEAD]:
            return None
        values = self.waveforms.read(case_id, requested).get(RUNTIME_LEAD) or []
        waveform = packet.get("waveform") or {}
        frequency = int(waveform.get("sampling_frequency") or 0)
        if not values or frequency <= 0:
            return None
        duration = len(values) / frequency
        bounded_end = duration if end is None else min(float(end), duration)
        bounded_start = max(0.0, min(float(start), bounded_end))
        start_index = int(bounded_start * frequency)
        end_index = int(bounded_end * frequency)
        step = max(1, (end_index - start_index) // max(1, int(max_points)))
        indices = list(range(start_index, end_index, step))
        return {
            "caseId": case_id,
            "samplingFrequency": frequency,
            "durationSec": round(duration, 6),
            "startSec": bounded_start,
            "endSec": bounded_end,
            "leads": [
                {
                    "lead": RUNTIME_LEAD,
                    "points": [
                        {
                            "timeSec": round(index / frequency, 6),
                            "amplitudeMv": values[index],
                        }
                        for index in indices
                    ],
                }
            ],
        }


__all__ = [
    "RUNTIME_LEAD",
    "RUNTIME_MANIFEST_NAME",
    "RUNTIME_MAPPING_VERSION",
    "RUNTIME_SCOPE",
    "RUNTIME_TARGETS",
    "RapidRhythmSupplement",
    "SUPPLEMENT_DIRECTORY",
    "build_runtime_manifest",
    "project_runtime_packet",
]
