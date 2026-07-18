"""Shared learner-serving policy for legacy and normalized ECG source packets.

Dataset admission and educational evidence are separate decisions.  A packet
may be safe to show in Rapid while only a narrow concept/subskill pair is
eligible for mastery evidence.  This module keeps that boundary source-aware
without making Rapid import Training's private selection helpers.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any, Literal

from .ingest.source_contract import KNOWN_SOURCES


LearningMode = Literal["training", "rapid"]

LEGACY_AUDITED_SOURCES = frozenset({"ptbxl", "prepared_bundle"})
NEVER_LEARNER_SERVE_SOURCES = frozenset(
    {"fixture", "mimic-iv-ecg", "mimic-iv-ecg-ext"}
)
STUDENT_TIERS = frozenset({"A", "B"})
SURFACE_12_LEADS = frozenset({"I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"})
RHYTHM_STREAM_LEADS = SURFACE_12_LEADS | frozenset({"MLII", "ECG1", "ECG2"})
SYNTHETIC_CASE_ID_PREFIXES = ("fixture-", "seed-")


@dataclass(frozen=True)
class PacketPolicyDecision:
    allowed: bool
    reason: str
    source_kind: Literal["legacy", "normalized", "rejected"]


def _waveform_is_audited(packet: dict[str, Any]) -> bool:
    waveform = packet.get("waveform") or {}
    if not isinstance(waveform, dict):
        return False

    leads = waveform.get("leads")
    if isinstance(leads, list):
        lead_ids = leads
    else:
        channels = waveform.get("channels")
        if not isinstance(channels, list) or not all(
            isinstance(channel, dict) and isinstance(channel.get("id"), str)
            for channel in channels
        ):
            return False
        lead_ids = [str(channel["id"]) for channel in channels]
    if not lead_ids or len(set(lead_ids)) != len(lead_ids):
        return False

    source = str(packet.get("source") or "")
    descriptor = KNOWN_SOURCES.get(source)
    eligibility = packet.get("educational_eligibility") or {}
    educational_use = (
        str(eligibility.get("educationalUse") or "")
        if isinstance(eligibility, dict)
        else ""
    )
    is_audited_rhythm_stream = bool(
        descriptor
        and educational_use == "rhythm_stream"
        and educational_use in descriptor.educational_uses
    )
    if is_audited_rhythm_stream:
        if not set(lead_ids) <= RHYTHM_STREAM_LEADS:
            return False
    elif not SURFACE_12_LEADS <= set(lead_ids):
        return False

    try:
        sampling_frequency = float(waveform.get("sampling_frequency"))
        duration_sec = float(waveform.get("duration_sec"))
    except (TypeError, ValueError):
        return False
    return bool(
        math.isfinite(sampling_frequency)
        and sampling_frequency > 0
        and math.isfinite(duration_sec)
        and duration_sec > 0
    )


def _normalized_envelope(packet: dict[str, Any], mode: LearningMode) -> PacketPolicyDecision:
    source = str(packet.get("source") or "")
    descriptor = KNOWN_SOURCES.get(source)
    if not descriptor:
        return PacketPolicyDecision(False, "The source is not in the audited source registry.", "rejected")
    if descriptor.access != "open" or source in NEVER_LEARNER_SERVE_SOURCES:
        return PacketPolicyDecision(False, "The source is not approved for learner serving.", "rejected")

    identity = packet.get("record_identity") or {}
    provenance = packet.get("source_provenance") or {}
    eligibility = packet.get("educational_eligibility") or {}
    if not all(isinstance(value, dict) for value in (identity, provenance, eligibility)):
        return PacketPolicyDecision(False, "The normalized source envelope is malformed.", "rejected")
    source_record_id = str(identity.get("sourceRecordId") or "")
    patient_id = str(identity.get("patientId") or "")
    case_id = str(packet.get("case_id") or "")
    if (
        identity.get("sourceId") != source
        or provenance.get("sourceId") != source
        or not source_record_id
        or case_id != f"{source}:{source_record_id}"
    ):
        return PacketPolicyDecision(False, "Source and record identities do not match.", "rejected")
    if descriptor.patient_ids_available and not patient_id:
        return PacketPolicyDecision(False, "The source contract requires a patient identity.", "rejected")
    if (
        str(identity.get("sourceVersion") or "") != descriptor.version
        or str(provenance.get("sourceVersion") or "") != descriptor.version
        or str(identity.get("licenseId") or "") != descriptor.license_id
        or str(provenance.get("licenseId") or "") != descriptor.license_id
        or str(provenance.get("labelAuthority") or "") != descriptor.label_authority
    ):
        return PacketPolicyDecision(False, "Source version, license, or label authority is incomplete.", "rejected")
    if provenance.get("patientId") is not None and str(provenance.get("patientId")) != patient_id:
        return PacketPolicyDecision(False, "Packet and provenance patient identities differ.", "rejected")

    modes = {str(value).casefold() for value in eligibility.get("eligibleModes") or []}
    educational_use = str(eligibility.get("educationalUse") or "")
    subskills = eligibility.get("eligibleSubskills") or {}
    if (
        "current_student_serving_eligible" in packet
        and packet.get("current_student_serving_eligible") is not True
    ):
        return PacketPolicyDecision(
            False,
            "The packet has not been promoted for current student serving.",
            "rejected",
        )
    if (
        "currentRuntimeModeConnected" in eligibility
        and eligibility.get("currentRuntimeModeConnected") is not True
    ):
        return PacketPolicyDecision(
            False,
            "The packet's reviewed learner-mode connection is not active.",
            "rejected",
        )
    if (
        mode not in modes
        or educational_use not in descriptor.educational_uses
        or not isinstance(subskills, dict)
        or not any(isinstance(values, list) and values for values in subskills.values())
    ):
        return PacketPolicyDecision(False, f"The packet does not explicitly allow {mode}.", "rejected")
    fingerprint = str(packet.get("signal_fingerprint") or "")
    if not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
        return PacketPolicyDecision(False, "A normalized packet requires a content fingerprint.", "rejected")
    return PacketPolicyDecision(True, "Audited normalized source packet.", "normalized")


def packet_mode_policy(packet: dict[str, Any] | None, mode: LearningMode) -> PacketPolicyDecision:
    """Return whether a packet may enter the requested learner mode at all."""

    if not isinstance(packet, dict):
        return PacketPolicyDecision(False, "The case packet is missing.", "rejected")
    source = str(packet.get("source") or "")
    case_id = str(packet.get("case_id") or "")
    if (
        not source
        or source in NEVER_LEARNER_SERVE_SOURCES
        or case_id.casefold().startswith(("fixture-", "seed-"))
        or packet.get("teaching_tier") not in STUDENT_TIERS
        or not _waveform_is_audited(packet)
    ):
        return PacketPolicyDecision(False, "The packet is not an audited Tier A/B real waveform.", "rejected")
    if source in LEGACY_AUDITED_SOURCES:
        return PacketPolicyDecision(True, "Reviewed legacy PTB packet.", "legacy")
    return _normalized_envelope(packet, mode)


def learner_direct_packet_policy(packet: dict[str, Any] | None) -> PacketPolicyDecision:
    """Gate generic case/packet/waveform access without blocking an authorized mode.

    Direct waveform routes are also used after Training or Rapid has selected a
    specialist-source ECG, so an audited Leipzig packet must remain reachable.
    Sources that are never learner-facing, synthetic identifiers, unknown
    sources, and malformed normalized envelopes fail closed.
    """

    if not isinstance(packet, dict):
        return PacketPolicyDecision(False, "The case packet is missing.", "rejected")
    source = str(packet.get("source") or "")
    case_id = str(packet.get("case_id") or packet.get("caseId") or "")
    if (
        not source
        or not case_id
        or source in NEVER_LEARNER_SERVE_SOURCES
        or case_id.casefold().startswith(SYNTHETIC_CASE_ID_PREFIXES)
    ):
        return PacketPolicyDecision(False, "The source is never available to learners.", "rejected")
    if source in LEGACY_AUDITED_SOURCES:
        return PacketPolicyDecision(True, "Audited legacy packet.", "legacy")
    for mode in ("training", "rapid"):
        decision = packet_mode_policy(packet, mode)
        if decision.allowed:
            return PacketPolicyDecision(
                True,
                f"Audited normalized packet reachable after {mode} selection.",
                decision.source_kind,
            )
    return PacketPolicyDecision(
        False,
        "The normalized source has no audited learner-mode access contract.",
        "rejected",
    )


def generic_learner_candidate_policy(candidate: dict[str, Any] | None) -> PacketPolicyDecision:
    """Fast summary gate for broad Guided/practice/review/catalog selection.

    Supplemental sources are admitted only by their explicit Training/Rapid
    contracts. In particular, Leipzig rhythm labels are target-only rather
    than exhaustive full-read truth and therefore must not enter broad generic
    selectors.
    """

    if not isinstance(candidate, dict):
        return PacketPolicyDecision(False, "The candidate is missing.", "rejected")
    source = str(candidate.get("source") or "")
    case_id = str(candidate.get("case_id") or candidate.get("caseId") or "")
    if (
        not source
        or not case_id
        or source in NEVER_LEARNER_SERVE_SOURCES
        or case_id.casefold().startswith(SYNTHETIC_CASE_ID_PREFIXES)
    ):
        return PacketPolicyDecision(False, "The source is never available to learners.", "rejected")
    if source not in LEGACY_AUDITED_SOURCES:
        return PacketPolicyDecision(
            False,
            "A supplemental source requires an explicit mode-specific selector.",
            "rejected",
        )
    return PacketPolicyDecision(True, "Audited broad-selection source.", "legacy")


def generic_learner_packet_policy(packet: dict[str, Any] | None) -> PacketPolicyDecision:
    """Full packet gate for a broad generic learner selector."""

    summary_decision = generic_learner_candidate_policy(packet)
    if not summary_decision.allowed or packet is None:
        return summary_decision
    # Broad selectors are assessment/teaching surfaces, so require the same
    # audited Tier A/B real-waveform floor as the mode-specific selectors.
    return packet_mode_policy(packet, "training")


def _confidence_supports(packet: dict[str, Any], concept: str) -> bool:
    rows = packet.get("concept_confidence") or {}
    if not isinstance(rows, dict):
        return False
    confidence = rows.get(concept) or {}
    if not isinstance(confidence, dict) or confidence.get("tier") not in STUDENT_TIERS:
        return False
    try:
        return float(confidence.get("score") or 0) >= 0.58
    except (TypeError, ValueError):
        return False


def _has_neutral_roi(packet: dict[str, Any], concept: str) -> bool:
    plus = packet.get("ptbxl_plus") or {}
    if not isinstance(plus, dict):
        return False
    fiducials = plus.get("fiducials") or {}
    if not isinstance(fiducials, dict):
        return False
    rois = fiducials.get("rois") or []
    if not isinstance(rois, list):
        return False
    return any(isinstance(row, dict) and row.get("concept") == concept for row in rois)


def packet_allows_learning_evidence(
    packet: dict[str, Any] | None,
    mode: LearningMode,
    concept: str,
    subskill: str,
) -> PacketPolicyDecision:
    """Audit the exact concept/subskill evidence lane for one packet."""

    mode_decision = packet_mode_policy(packet, mode)
    if not mode_decision.allowed or packet is None:
        return mode_decision
    supported = packet.get("supported_objectives") or []
    if not isinstance(supported, (list, tuple, set)):
        return PacketPolicyDecision(False, "Supported objectives are malformed.", "rejected")

    if mode_decision.source_kind == "normalized":
        eligibility = packet.get("educational_eligibility") or {}
        if (
            "masteryEvidenceEligible" in eligibility
            and eligibility.get("masteryEvidenceEligible") is not True
        ):
            return PacketPolicyDecision(
                False,
                "The reviewed source contract does not permit mastery evidence.",
                "rejected",
            )
        rows = eligibility.get("eligibleSubskills") or {}
        allowed = rows.get(concept) if isinstance(rows, dict) else None
        if not isinstance(allowed, list) or subskill not in {str(value) for value in allowed}:
            return PacketPolicyDecision(
                False,
                f"The source packet does not allow {concept}/{subskill} evidence in {mode}.",
                "rejected",
            )

    if subskill == "localize":
        if not _has_neutral_roi(packet, concept):
            return PacketPolicyDecision(False, f"No grounded {concept} ROI is present.", "rejected")
        return PacketPolicyDecision(True, "Grounded neutral localization target.", mode_decision.source_kind)

    if concept not in supported or not _confidence_supports(packet, concept):
        return PacketPolicyDecision(False, "The exact concept is not a reliable supported objective.", "rejected")
    return PacketPolicyDecision(True, "Exact supported concept/subskill source contract.", mode_decision.source_kind)


def eligible_packet_objectives(
    packet: dict[str, Any] | None,
    mode: LearningMode,
    subskill: str = "recognize",
) -> list[str]:
    if not isinstance(packet, dict):
        return []
    supported = packet.get("supported_objectives") or []
    if not isinstance(supported, (list, tuple, set)):
        return []
    return [
        str(concept)
        for concept in supported
        if packet_allows_learning_evidence(packet, mode, str(concept), subskill).allowed
    ]


def retention_morphology_key(packet: dict[str, Any]) -> str | None:
    """Stable morphology family key without treating every ECG as a new form."""

    source = str(packet.get("source") or "unknown")
    source_labels = packet.get("source_labels") or {}
    rhythm = source_labels.get("rhythm") if isinstance(source_labels, dict) else {}
    rhythm = rhythm or {}
    canonical_rhythm = (
        rhythm.get("canonicalConceptId") or rhythm.get("canonicalRhythmId")
        if isinstance(rhythm, dict)
        else None
    )
    if canonical_rhythm:
        return f"{source}:{canonical_rhythm}:{rhythm.get('rhythmCode') or 'label'}"
    ptbxl = packet.get("ptbxl") or {}
    subclasses = ptbxl.get("diagnostic_subclass") if isinstance(ptbxl, dict) else []
    subclasses = subclasses or []
    if isinstance(subclasses, str):
        subclasses = [subclasses]
    values = sorted(str(value) for value in subclasses if value)
    if values:
        return f"{source}:" + "|".join(values)
    supported = sorted(str(value) for value in packet.get("supported_objectives") or [] if value)
    return f"{source}:" + "|".join(supported[:4]) if supported else None
