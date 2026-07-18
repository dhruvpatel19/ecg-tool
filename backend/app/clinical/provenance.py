"""Fail-closed provenance rules for learner-facing Clinical Decisions items.

Synthetic ``fixture-*`` and ``seed-*`` packets remain useful for deterministic
harness/grader tests, but they are never valid inputs to a learner shift.  This
module is deliberately small and independent of the item generator so the same
contract can be asserted both at startup and immediately before serving/grading.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Callable, Iterable

from ..ingest.source_contract import KNOWN_SOURCES
from .schemas import ClinicalCaseItem

PacketProvider = Callable[[str], dict[str, Any] | None]

LEARNER_CLINICAL_SOURCES = frozenset({"ptbxl", "prepared_bundle"})
# A source can be valid for a single learner-facing tracing without yet being
# approved for patient-linked comparison.  Keep longitudinal admission as an
# explicit, version-pinned allow-list so a new corpus source or source upgrade
# cannot silently unlock old-versus-new claims.
LEARNER_LONGITUDINAL_SOURCES = frozenset({"ptbxl"})
SYNTHETIC_ID_PREFIXES = ("seed-", "fixture-")
LOCKED_OBJECTIVES = frozenset({"wide_complex_tachycardia"})


def _is_synthetic_id(value: str | None) -> bool:
    return bool(value) and str(value).lower().startswith(SYNTHETIC_ID_PREFIXES)


def _longitudinal_identity(
    packet: dict[str, Any],
    *,
    expected_ecg_id: str | None,
) -> dict[str, str]:
    """Return the normalized, source-verified identity for one pair member."""

    case_id = str(packet.get("case_id") or "").strip()
    source = str(packet.get("source") or "").strip().lower()
    identity = packet.get("record_identity")
    provenance = packet.get("source_provenance")
    if not case_id or not isinstance(identity, dict) or not isinstance(provenance, dict):
        raise RuntimeError("Longitudinal ECG packet lacks immutable source identity.")
    if expected_ecg_id is not None and case_id != str(expected_ecg_id):
        raise RuntimeError("Longitudinal ECG packet resolved to the wrong record.")
    if source not in LEARNER_LONGITUDINAL_SOURCES:
        raise RuntimeError(
            f"Longitudinal ECG packet resolved to unapproved source {source!r}."
        )

    descriptor = KNOWN_SOURCES.get(source)
    if descriptor is None:
        raise RuntimeError("Longitudinal ECG source has no approved source contract.")
    identity_source = str(identity.get("sourceId") or "").strip().lower()
    provenance_source = str(provenance.get("sourceId") or "").strip().lower()
    version = str(identity.get("sourceVersion") or "").strip()
    provenance_version = str(provenance.get("sourceVersion") or "").strip()
    license_id = str(identity.get("licenseId") or "").strip()
    provenance_license = str(provenance.get("licenseId") or "").strip()
    record_id = str(identity.get("sourceRecordId") or "").strip()
    patient_id = str(identity.get("patientId") or "").strip()
    if identity_source != source or provenance_source != source:
        raise RuntimeError("Longitudinal ECG source identity is inconsistent.")
    if version != descriptor.version or provenance_version != descriptor.version:
        raise RuntimeError("Longitudinal ECG source version is not approved.")
    if license_id != descriptor.license_id or provenance_license != descriptor.license_id:
        raise RuntimeError("Longitudinal ECG license identity is inconsistent.")
    if not record_id or record_id != case_id:
        raise RuntimeError("Longitudinal ECG source-record identity is inconsistent.")
    if not patient_id:
        raise RuntimeError("Longitudinal ECG packet has no patient-linkage identity.")
    provenance_patient = provenance.get("patientId")
    if provenance_patient is not None and str(provenance_patient).strip() != patient_id:
        raise RuntimeError("Longitudinal ECG patient identity is inconsistent.")
    return {
        "caseId": case_id,
        "source": source,
        "sourceVersion": version,
        "patientId": patient_id,
    }


def _recording_datetime(packet: dict[str, Any]) -> datetime:
    """Read a source-owned acquisition timestamp without accepting authored context."""

    identity = packet.get("record_identity") or {}
    provenance = packet.get("source_provenance") or {}
    ptbxl_metadata = ((packet.get("ptbxl") or {}).get("metadata") or {})
    raw = (
        identity.get("recordingDate")
        or identity.get("recordedAt")
        or provenance.get("recordingDate")
        or provenance.get("recordedAt")
        or ptbxl_metadata.get("recording_date")
    )
    if not isinstance(raw, str) or not raw.strip():
        raise RuntimeError("Longitudinal ECG packet has no recording timestamp.")
    normalized = raw.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise RuntimeError("Longitudinal ECG recording timestamp is invalid.") from exc


def _assert_pair_signal_eligible(packet: dict[str, Any]) -> None:
    """Require an explicitly acceptable, human-validated comparison member."""

    quality = packet.get("signal_quality")
    if not isinstance(quality, dict):
        raise RuntimeError("Longitudinal ECG signal-quality metadata is invalid.")
    if str(quality.get("status") or "").strip().lower() != "acceptable":
        raise RuntimeError("Longitudinal ECG signal quality is not acceptable.")
    if quality.get("human_validated") is not True:
        raise RuntimeError("Longitudinal ECG lacks human signal validation.")
    metadata = ((packet.get("ptbxl") or {}).get("metadata") or {})
    if "validated_by_human" in metadata and metadata.get("validated_by_human") is not True:
        raise RuntimeError("Longitudinal ECG lacks human source validation.")


def assert_longitudinal_pair_provenance(
    current_packet: dict[str, Any],
    prior_packet: dict[str, Any],
    *,
    current_ecg_id: str | None = None,
    prior_ecg_id: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Fail closed unless two packets form an authenticated chronological pair.

    Patient ids and acquisition timestamps remain server-only provenance.  This
    validator establishes only that the two recordings are distinct,
    same-patient, same-approved-source observations in a defensible order; it
    does not infer an admission, intervention, symptom, laboratory result, or
    treatment response.
    """

    if not isinstance(current_packet, dict) or not isinstance(prior_packet, dict):
        raise RuntimeError("Longitudinal ECG pair is incomplete.")
    current = _longitudinal_identity(
        current_packet, expected_ecg_id=current_ecg_id
    )
    prior = _longitudinal_identity(prior_packet, expected_ecg_id=prior_ecg_id)
    if current["caseId"] == prior["caseId"]:
        raise RuntimeError("Longitudinal ECG pair must use distinct records.")
    if (
        current["source"] != prior["source"]
        or current["sourceVersion"] != prior["sourceVersion"]
    ):
        raise RuntimeError("Longitudinal ECG pair must use one approved source version.")
    if current["patientId"] != prior["patientId"]:
        raise RuntimeError("Longitudinal ECG pair does not share one patient identity.")

    prior_at = _recording_datetime(prior_packet)
    current_at = _recording_datetime(current_packet)
    if (prior_at.tzinfo is None) != (current_at.tzinfo is None):
        raise RuntimeError("Longitudinal ECG timestamps use incompatible timezone semantics.")
    if prior_at.tzinfo is not None:
        prior_at = prior_at.astimezone(UTC)
        current_at = current_at.astimezone(UTC)
    if prior_at >= current_at:
        raise RuntimeError("Longitudinal ECG prior must precede the current recording.")

    _assert_pair_signal_eligible(prior_packet)
    _assert_pair_signal_eligible(current_packet)
    return current_packet, prior_packet


def assert_learner_item_provenance(
    item: ClinicalCaseItem,
    packet_provider: PacketProvider,
) -> dict[str, Any]:
    """Return the grounded packet or raise when an item is unsafe to serve.

    Old/new is admitted only when ``prior_ecg_id`` resolves through the strict
    same-patient longitudinal contract below. WCT remains locked until an
    appropriately sourced authored case is added. These checks prevent a stale
    database row from bypassing the startup bank builder.
    """

    identifiers = (item.item_id, item.ecg_id, item.prior_ecg_id)
    if any(_is_synthetic_id(value) for value in identifiers):
        raise RuntimeError(
            f"Learner Clinical item {item.item_id!r} references a synthetic identifier."
        )
    if item.question_type == "oldnew" and not item.prior_ecg_id:
        raise RuntimeError(
            f"Learner Clinical item {item.item_id!r} uses old/new without a prior ECG."
        )
    if item.prior_ecg_id and str(item.prior_ecg_id) == str(item.ecg_id):
        raise RuntimeError("Longitudinal ECG pair must use distinct records.")
    objectives = {
        claim.objective_id for claim in item.evidence_manifest.ecg_supports
    }
    locked = objectives & LOCKED_OBJECTIVES
    if locked:
        raise RuntimeError(
            f"Learner Clinical item {item.item_id!r} uses locked objective(s): {sorted(locked)}."
        )

    packet = packet_provider(item.ecg_id)
    if packet is None:
        raise RuntimeError(
            f"Learner Clinical item {item.item_id!r} has no grounded packet for ECG {item.ecg_id!r}."
        )
    source = str(packet.get("source") or "").lower()
    if source not in LEARNER_CLINICAL_SOURCES:
        raise RuntimeError(
            f"Learner Clinical item {item.item_id!r} resolved to disallowed source {source!r}."
        )
    if str(packet.get("case_id")) != str(item.ecg_id):
        raise RuntimeError(
            f"Learner Clinical item {item.item_id!r} resolved to the wrong packet id."
        )
    if item.prior_ecg_id:
        prior_packet = packet_provider(item.prior_ecg_id)
        if prior_packet is None:
            raise RuntimeError(
                f"Learner Clinical item {item.item_id!r} has no grounded prior packet."
            )
        assert_longitudinal_pair_provenance(
            packet,
            prior_packet,
            current_ecg_id=item.ecg_id,
            prior_ecg_id=item.prior_ecg_id,
        )
    return packet


def assert_serving_bank_provenance(
    items: Iterable[ClinicalCaseItem],
    packet_provider: PacketProvider,
) -> None:
    """Assert the provenance contract for every startup-loaded serving item."""

    for item in items:
        if item.validation_status == "harness_pass":
            assert_learner_item_provenance(item, packet_provider)
