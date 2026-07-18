"""Offline adapter for the reviewed dangerous-arrhythmia fragment dataset.

The source contains short, single-channel MLII fragments labelled for rhythm
recognition research.  It has no pulse, perfusion, symptoms, arrest state,
monitor/defibrillator context, treatment, or response-to-treatment data.
Accordingly, packets created here can support only rhythm recognition and
discrimination after a separate runtime review.  They may never key an ACLS
action, shockability, stability, or clinical-management question.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
from pathlib import Path, PurePosixPath
import re
from typing import Any, Mapping, Sequence

import numpy as np

from .source_contract import KNOWN_SOURCES, source_catalog_entry


SOURCE_ID = "ecg-fragment-dangerous-arrhythmia"
DESCRIPTOR = KNOWN_SOURCES[SOURCE_ID]
EXTRACTION_VERSION = "dangerous-arrhythmia-reviewed-fragment-v1"
CHECKSUM_MANIFEST_SHA256 = (
    "3f6f16dd8904c433f049899b6bbef04efccc460ff6196e124e460b162d108dd5"
)
RECORDS_SHA256 = "b5d496a2d056ef4f617ef09bd0d7d0f0fb23456f425bc5e0d7926635c158f950"
EXPECTED_FRAGMENT_COUNT = 1016
SOURCE_FS = 250
LEAD_NAME = "MLII"
FUTURE_MODE_ID = "rapid_rhythm_recognition"


@dataclass(frozen=True)
class RhythmContract:
    raw_code: str
    label: str
    canonical_rhythm_id: str
    eligible_subskills: tuple[str, ...] = ("recognize", "discriminate")


RHYTHM_LABELS: dict[str, RhythmContract] = {
    "VFL": RhythmContract("VFL", "Ventricular flutter", "ventricular_flutter"),
    "VF": RhythmContract("VF", "Ventricular fibrillation", "ventricular_fibrillation"),
    "VTTdP": RhythmContract("VTTdP", "Torsade de pointes label", "torsades_de_pointes"),
    "VTHR": RhythmContract("VTHR", "High-rate ventricular tachycardia", "ventricular_tachycardia_high_rate"),
    "VTLR": RhythmContract("VTLR", "Low-rate ventricular tachycardia", "ventricular_tachycardia_low_rate"),
    "B": RhythmContract("B", "Ventricular bigeminy", "ventricular_bigeminy"),
    "HGEA": RhythmContract("HGEA", "High-grade ventricular ectopic activity", "high_grade_ventricular_ectopy"),
    "VER": RhythmContract("VER", "Ventricular escape rhythm", "ventricular_escape_rhythm"),
    "AFIB": RhythmContract("AFIB", "Atrial fibrillation", "atrial_fibrillation"),
    "SVTA": RhythmContract("SVTA", "Supraventricular tachyarrhythmia", "supraventricular_tachyarrhythmia"),
    "SBR": RhythmContract("SBR", "Sinus bradycardia", "sinus_bradycardia"),
    "BI": RhythmContract("BI", "First-degree heart block label", "av_block_first_degree"),
    "NOD": RhythmContract("NOD", "Nodal rhythm", "junctional_rhythm"),
    "BBB": RhythmContract("BBB", "Sinus rhythm with bundle branch block", "bundle_branch_block"),
    "N": RhythmContract("N", "Normal sinus rhythm", "sinus_rhythm"),
    "Ne": RhythmContract("Ne", "Normal rhythm with one extrasystole", "sinus_rhythm_single_extrasystole"),
}

_RECORD_PATTERN = re.compile(
    r"(?P<class>[1-6]_[A-Za-z0-9_]+)/frag/"
    r"(?P<parent>\d+_C)_(?P<label>VTTdP|VTHR|VTLR|AFIB|SVTA|HGEA|VFL|SBR|NOD|BBB|VER|VF|BI|Ne|N|B)_"
    r"(?P<offset>\d+(?:_\d+)?)s_frag"
)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_checksum_manifest(
    raw: bytes, *, expected_manifest_sha256: str = CHECKSUM_MANIFEST_SHA256
) -> dict[str, str]:
    if _sha256_bytes(raw) != expected_manifest_sha256:
        raise ValueError(
            "dangerous-arrhythmia checksum manifest does not match the pinned 1.0.0 release"
        )
    values: dict[str, str] = {}
    for line_number, line in enumerate(raw.decode("ascii").splitlines(), start=1):
        match = re.fullmatch(r"([0-9a-f]{64})\s+(.+)", line.strip())
        if not match:
            raise ValueError(f"malformed dangerous-arrhythmia checksum row {line_number}")
        checksum, filename = match.groups()
        normalized = str(PurePosixPath(filename))
        if normalized.startswith("../") or normalized.startswith("/"):
            raise ValueError("dangerous-arrhythmia checksum path leaves the source root")
        if normalized in values:
            raise ValueError(f"duplicate checksum entry for {normalized}")
        values[normalized] = checksum
    if values.get("RECORDS") != RECORDS_SHA256:
        raise ValueError("dangerous-arrhythmia RECORDS is not the pinned 1.0.0 release")
    return values


def load_checksum_manifest(source_root: str | Path) -> dict[str, str]:
    path = Path(source_root) / "SHA256SUMS.txt"
    if not path.is_file():
        raise FileNotFoundError(path)
    return parse_checksum_manifest(path.read_bytes())


def verify_artifact(path: str | Path, expected_sha256: str) -> None:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    actual = sha256_file(path)
    if actual != expected_sha256:
        raise ValueError(
            f"checksum mismatch for dangerous-arrhythmia artifact {path.name}: "
            f"expected {expected_sha256}, got {actual}"
        )


@dataclass(frozen=True)
class FragmentSpec:
    # Raw values are kept only for local reads and are never serialized.
    relative_record_path: str
    source_parent_record: str
    source_offset_text: str
    source_class: str
    rhythm_code: str
    header_sha256: str
    data_sha256: str

    @property
    def contract(self) -> RhythmContract:
        return RHYTHM_LABELS[self.rhythm_code]

    @property
    def opaque_record_id(self) -> str:
        return f"fragment-{self.data_sha256[:20]}"

    @property
    def opaque_parent_id(self) -> str:
        digest = hashlib.sha256(
            f"{SOURCE_ID}:{DESCRIPTOR.version}:{self.source_parent_record}".encode("ascii")
        ).hexdigest()
        return f"source-group-{digest[:20]}"

    @property
    def window_id(self) -> str:
        return f"{SOURCE_ID}:{self.opaque_record_id}"


def load_fragment_specs(
    source_root: str | Path, checksums: Mapping[str, str]
) -> tuple[FragmentSpec, ...]:
    records_path = Path(source_root) / "RECORDS"
    verify_artifact(records_path, RECORDS_SHA256)
    values = tuple(
        str(PurePosixPath(line.strip()))
        for line in records_path.read_text(encoding="ascii").splitlines()
        if line.strip()
    )
    if len(values) != EXPECTED_FRAGMENT_COUNT or len(set(values)) != EXPECTED_FRAGMENT_COUNT:
        raise ValueError("dangerous-arrhythmia RECORDS must contain 1,016 unique fragments")
    specs: list[FragmentSpec] = []
    for value in values:
        match = _RECORD_PATTERN.fullmatch(value)
        if not match or match.group("label") not in RHYTHM_LABELS:
            raise ValueError("dangerous-arrhythmia RECORDS contains an unexpected path or label")
        header_name = f"{value}.hea"
        data_name = f"{value}.dat"
        header_sha = checksums.get(header_name)
        data_sha = checksums.get(data_name)
        if not header_sha or not data_sha:
            raise ValueError(f"checksum manifest is missing fragment artifacts for {value}")
        specs.append(
            FragmentSpec(
                relative_record_path=value,
                source_parent_record=match.group("parent"),
                source_offset_text=match.group("offset"),
                source_class=match.group("class"),
                rhythm_code=match.group("label"),
                header_sha256=header_sha,
                data_sha256=data_sha,
            )
        )
    return tuple(specs)


@dataclass(frozen=True)
class HeaderSummary:
    sampling_frequency: int
    sample_count: int
    source_signal_name: str


def parse_header(text: str, expected_record_name: str) -> HeaderSummary:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        raise ValueError("dangerous-arrhythmia fragment header is incomplete")
    first = lines[0].split()
    if len(first) < 4 or first[0] != expected_record_name:
        raise ValueError("dangerous-arrhythmia fragment header identity is invalid")
    try:
        signal_count = int(first[1])
        sampling_frequency = int(float(first[2]))
        sample_count = int(first[3])
    except ValueError as exc:
        raise ValueError("dangerous-arrhythmia header dimensions are malformed") from exc
    if signal_count != 1 or sampling_frequency != SOURCE_FS or sample_count <= 0:
        raise ValueError("dangerous-arrhythmia source must be one 250-Hz signal")
    return HeaderSummary(sampling_frequency, sample_count, lines[1].split()[-1])


@dataclass(frozen=True)
class SourceInventory:
    source_root: Path
    fragments: tuple[FragmentSpec, ...]
    errors: tuple[str, ...]

    @property
    def rhythm_counts(self) -> dict[str, int]:
        return dict(sorted(Counter(item.contract.canonical_rhythm_id for item in self.fragments).items()))

    @property
    def raw_label_counts(self) -> dict[str, int]:
        return dict(sorted(Counter(item.rhythm_code for item in self.fragments).items()))

    def as_dict(self) -> dict[str, Any]:
        return {
            "sourceId": SOURCE_ID,
            "sourceVersion": DESCRIPTOR.version,
            "datasetTitle": DESCRIPTOR.dataset_title,
            "licenseId": DESCRIPTOR.license_id,
            "labelAuthority": DESCRIPTOR.label_authority,
            "fragmentCount": len(self.fragments),
            "rawLabelCounts": self.raw_label_counts,
            "canonicalRhythmCounts": self.rhythm_counts,
            "checksumManifestSha256": CHECKSUM_MANIFEST_SHA256,
            "eligibleSubskills": ["recognize", "discriminate"],
            "hemodynamicContextAvailable": False,
            "treatmentOrActionSequenceEligible": False,
            "shockabilityClassificationEligible": False,
            "currentRuntimeConnected": False,
            "errors": list(self.errors),
        }


def inventory_source(source_root: str | Path) -> SourceInventory:
    root = Path(source_root)
    checksums = load_checksum_manifest(root)
    specs = load_fragment_specs(root, checksums)
    errors: list[str] = []
    for spec in specs:
        path = root / f"{spec.relative_record_path}.hea"
        try:
            verify_artifact(path, spec.header_sha256)
            parse_header(path.read_text(encoding="ascii"), PurePosixPath(spec.relative_record_path).name)
        except Exception as exc:
            errors.append(f"fragment header validation failed: {type(exc).__name__}: {exc}")
    return SourceInventory(root, specs, tuple(errors))


def select_fragments(
    fragments: Sequence[FragmentSpec],
    *,
    rhythm_codes: set[str] | None = None,
    limit: int = 0,
    max_per_rhythm: int = 0,
) -> tuple[FragmentSpec, ...]:
    if limit < 0 or max_per_rhythm < 0:
        raise ValueError("fragment limits may not be negative")
    unknown = set(rhythm_codes or ()) - set(RHYTHM_LABELS)
    if unknown:
        raise ValueError(f"unknown dangerous-arrhythmia rhythm codes: {sorted(unknown)}")
    counts: Counter[str] = Counter()
    selected: list[FragmentSpec] = []
    for spec in sorted(fragments, key=lambda item: (item.rhythm_code, item.data_sha256)):
        if rhythm_codes and spec.rhythm_code not in rhythm_codes:
            continue
        if max_per_rhythm and counts[spec.rhythm_code] >= max_per_rhythm:
            continue
        selected.append(spec)
        counts[spec.rhythm_code] += 1
        if limit and len(selected) >= limit:
            break
    return tuple(selected)


def read_fragment(
    source_root: str | Path, spec: FragmentSpec
) -> tuple[list[float], HeaderSummary]:
    root = Path(source_root)
    base = root / spec.relative_record_path
    verify_artifact(base.with_suffix(".hea"), spec.header_sha256)
    verify_artifact(base.with_suffix(".dat"), spec.data_sha256)
    header = parse_header(
        base.with_suffix(".hea").read_text(encoding="ascii"),
        PurePosixPath(spec.relative_record_path).name,
    )
    try:
        import wfdb  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("offline dangerous-arrhythmia import requires wfdb") from exc
    signal, fields = wfdb.rdsamp(str(base))
    if signal.ndim != 2 or signal.shape != (header.sample_count, 1):
        raise ValueError("dangerous-arrhythmia waveform dimensions do not match its header")
    if int(round(float(fields.get("fs") or 0))) != SOURCE_FS:
        raise ValueError("dangerous-arrhythmia waveform sampling rate changed during read")
    values = signal[:, 0].astype(np.float64)
    if not np.isfinite(values).all():
        raise ValueError("dangerous-arrhythmia waveform contains non-finite samples")
    return values.round(6).tolist(), header


def signal_fingerprint(values: Sequence[float]) -> str:
    array = np.asarray(values, dtype=np.float64)
    # Match LocalWaveformStore exactly so the immutable packaged .npy can be
    # re-hashed byte-for-byte during runtime and release audit.
    normalized = np.clip(np.round(array * 1000.0), -32767, 32767).astype("<i2")
    digest = hashlib.sha256()
    digest.update(LEAD_NAME.encode("ascii"))
    digest.update(len(normalized).to_bytes(8, "little"))
    digest.update(normalized.tobytes())
    return digest.hexdigest()


def build_fragment_packet(
    spec: FragmentSpec,
    values: Sequence[float],
    header: HeaderSummary,
) -> dict[str, Any]:
    if len(values) != header.sample_count or header.sampling_frequency != SOURCE_FS:
        raise ValueError("dangerous-arrhythmia packet signal does not match its verified header")
    contract = spec.contract
    fingerprint = signal_fingerprint(values)
    return {
        "stream_window_id": spec.window_id,
        "case_id": spec.window_id,
        "source": SOURCE_ID,
        "extraction_version": EXTRACTION_VERSION,
        "teaching_tier": "A",
        "current_student_serving_eligible": False,
        "record_identity": {
            "sourceId": SOURCE_ID,
            "sourceVersion": DESCRIPTOR.version,
            "licenseId": DESCRIPTOR.license_id,
            "sourceRecordId": spec.opaque_record_id,
            "parentRecordId": spec.opaque_parent_id,
            "patientId": "",
        },
        "source_provenance": {
            **source_catalog_entry(SOURCE_ID),
            "checksumManifestSha256": CHECKSUM_MANIFEST_SHA256,
            "extractionVersion": EXTRACTION_VERSION,
            "patientId": "",
            "artifactChecksums": {
                "headerSha256": spec.header_sha256,
                "dataSha256": spec.data_sha256,
            },
            "windowStartSample": 0,
            "windowEndSample": header.sample_count,
            "rawPatientIdentifiersIncluded": False,
            "rawRecordIdentifiersIncluded": False,
        },
        "source_labels": {
            "rhythm": {
                "rhythmCode": contract.raw_code,
                "sourceLabel": contract.label,
                "canonicalRhythmId": contract.canonical_rhythm_id,
                "labelAuthority": DESCRIPTOR.label_authority,
            }
        },
        "supported_objectives": [contract.canonical_rhythm_id],
        "concept_confidence": {
            contract.canonical_rhythm_id: {
                "tier": "A",
                "score": 1.0,
                "evidence": ["reviewed source fragment label"],
            }
        },
        "waveform": {
            "leads": [LEAD_NAME],
            "sampling_frequency": SOURCE_FS,
            "duration_sec": round(header.sample_count / SOURCE_FS, 6),
            "isTwelveLead": False,
            "isSingleModifiedLimbLeadII": True,
            "isMonitorOrDefibrillatorExport": False,
        },
        "signal_fingerprint": fingerprint,
        "educational_eligibility": {
            "educationalUse": "rhythm_stream",
            "eligibleModes": [FUTURE_MODE_ID],
            "eligibleSubskills": {
                contract.canonical_rhythm_id: list(contract.eligible_subskills)
            },
            "currentRuntimeModeConnected": False,
            "rapidPracticeEligibleAfterReview": True,
            "clinicalCaseEligible": False,
            "clinicalManagementEligible": False,
            "hemodynamicContextAvailable": False,
            "treatmentOrActionSequenceEligible": False,
            "shockabilityClassificationEligible": False,
            "masteryEvidenceEligible": False,
        },
        "llm_allowed_claims": [
            "Name or discriminate the reviewed source rhythm label in this short MLII fragment.",
            "Describe only waveform features visible in the supplied single-channel sample.",
        ],
        "llm_forbidden_claims": [
            "Do not infer pulse, perfusion, symptoms, hemodynamic stability, cardiac arrest, or etiology.",
            "Do not infer shockability, medication, electricity, treatment sequence, or clinical management.",
            "Do not present the fragment as a 12-lead ECG, monitor/defibrillator export, or full clinical case.",
        ],
    }


def build_release_manifest(packets: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    packet_list = list(packets)
    for packet in packet_list:
        eligibility = packet.get("educational_eligibility") or {}
        waveform = packet.get("waveform") or {}
        if (
            packet.get("source") != SOURCE_ID
            or packet.get("current_student_serving_eligible") is not False
            or not isinstance(eligibility, Mapping)
            or eligibility.get("currentRuntimeModeConnected") is not False
            or eligibility.get("clinicalManagementEligible") is not False
            or eligibility.get("treatmentOrActionSequenceEligible") is not False
            or eligibility.get("shockabilityClassificationEligible") is not False
            or eligibility.get("masteryEvidenceEligible") is not False
            or not isinstance(waveform, Mapping)
            or waveform.get("isTwelveLead") is not False
            or waveform.get("isSingleModifiedLimbLeadII") is not True
        ):
            raise ValueError(
                "dangerous-arrhythmia packet violates its disconnected recognition-only contract"
            )
    rhythm_counts = Counter(
        str(((item.get("source_labels") or {}).get("rhythm") or {}).get("canonicalRhythmId") or "")
        for item in packet_list
    )
    digest = hashlib.sha256()
    for packet in sorted(packet_list, key=lambda item: str(item.get("stream_window_id") or "")):
        digest.update(str(packet.get("stream_window_id") or "").encode("ascii"))
        digest.update(str(packet.get("signal_fingerprint") or "").encode("ascii"))
    return {
        "version": 1,
        "complete": True,
        "artifactType": "gated_rhythm_recognition_fragments",
        "sourceCatalog": {SOURCE_ID: source_catalog_entry(SOURCE_ID)},
        "sourceId": SOURCE_ID,
        "sourceVersion": DESCRIPTOR.version,
        "extractionVersion": EXTRACTION_VERSION,
        "fragmentCount": len(packet_list),
        "canonicalRhythmCounts": dict(sorted(rhythm_counts.items())),
        "contentIndexSha256": digest.hexdigest(),
        "eligibleSubskills": ["recognize", "discriminate"],
        "clinicalManagementEligible": False,
        "hemodynamicContextAvailable": False,
        "treatmentOrActionSequenceEligible": False,
        "shockabilityClassificationEligible": False,
        "rawPatientIdentifiersIncluded": False,
        "rawRecordIdentifiersIncluded": False,
        "currentRuntimeConnected": False,
    }
