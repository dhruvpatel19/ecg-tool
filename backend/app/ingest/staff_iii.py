"""Offline, checksum-gated STAFF III comparison-episode adapter.

STAFF III provides protocol-timed standard ECG recordings around elective PTCA
balloon occlusion.  It can establish recording order and protocol phase; it
does *not* by itself establish a learner-facing morphology answer, spontaneous
acute coronary syndrome, treatment response, or a management decision.

This adapter therefore builds a dedicated authoring artifact containing an
opaque baseline -> controlled-occlusion -> recovery sequence.  Raw source
record and patient identifiers are used only while reading local source files
and are never serialized.  A separate clinical review must add adjudicated
change ROIs before any episode may enter Rapid or Clinical runtime selection.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import io
from pathlib import Path, PurePosixPath
import re
from typing import Any, Iterable, Mapping, Sequence
import xml.etree.ElementTree as ET
import zipfile

import numpy as np

from ..store.waveform_store import LEADS, waveform_fingerprint
from .source_contract import KNOWN_SOURCES, source_catalog_entry


SOURCE_ID = "staff-iii"
DESCRIPTOR = KNOWN_SOURCES[SOURCE_ID]
EXTRACTION_VERSION = "staff-iii-comparison-episode-v1"
ARTIFACT_SCHEMA_VERSION = 1
SOURCE_FS = 1000
TARGET_FS = 250
FRAME_SECONDS = 10.0
EVENT_GUARD_SECONDS = 2.0
RAW_LEADS = ("V1", "V2", "V3", "V4", "V5", "V6", "I", "II", "III")
# The source workbook explicitly warns that some leads for these patients were
# later identified as incorrect (possible lead or sign reversal). They remain
# inventory-visible but cannot enter an educational comparison candidate.
KNOWN_LEAD_CONFIGURATION_EXCLUSIONS = frozenset({1, 4, 5, 6, 89})

# The official checksum manifest is itself pinned before its rows are trusted.
CHECKSUM_MANIFEST_SHA256 = (
    "e4c71aa1b47b8fd17b1549b5f650770df63f4cb795388d129c6ca78cd7a78269"
)
RECORDS_SHA256 = "fb841c0cc77a16c19ad835f91b9735904bfd6a8e4929c4c25b8cbb425f80a5fb"
METADATA_XLSX_SHA256 = (
    "37b89f20830ad73f4ce7d2fdd9d035ccc33a2ec3f0d05c995d6c2cb106de129e"
)
METADATA_FILENAME = "STAFF-III-Database-Annotations.xlsx"

_BASELINE_COLUMNS = (("F", "BC2"), ("E", "BC1"), ("D", "BR"))
_RECOVERY_COLUMNS = (("Y", "PC1"), ("Z", "PC2"), ("AA", "PR1"), ("AB", "PR2"))
_INFLATION_COLUMNS = (
    ("G", "H", "I", "J", 1),
    ("K", "L", "M", "N", 2),
    ("O", "P", "Q", "R", 3),
    ("S", "T", "U", None, 4),
    ("V", "W", "X", None, 5),
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
    """Parse only a caller-pinned STAFF III checksum manifest."""

    if _sha256_bytes(raw) != expected_manifest_sha256:
        raise ValueError("STAFF III checksum manifest does not match the pinned 1.0.0 release")
    values: dict[str, str] = {}
    for line_number, line in enumerate(raw.decode("ascii").splitlines(), start=1):
        match = re.fullmatch(r"([0-9a-f]{64})\s+(.+)", line.strip())
        if not match:
            raise ValueError(f"malformed STAFF III checksum row {line_number}")
        checksum, filename = match.groups()
        normalized = str(PurePosixPath(filename))
        if normalized.startswith("../") or normalized.startswith("/"):
            raise ValueError("STAFF III checksum paths must remain inside the source root")
        if normalized in values:
            raise ValueError(f"duplicate STAFF III checksum entry for {normalized}")
        values[normalized] = checksum
    if values.get("RECORDS") != RECORDS_SHA256:
        raise ValueError("STAFF III RECORDS checksum is not the pinned 1.0.0 release")
    if values.get(METADATA_FILENAME) != METADATA_XLSX_SHA256:
        raise ValueError("STAFF III metadata workbook is not the pinned 1.0.0 release")
    return values


def load_checksum_manifest(source_root: str | Path) -> dict[str, str]:
    path = Path(source_root) / "SHA256SUMS.txt"
    if not path.is_file():
        raise FileNotFoundError(f"STAFF III checksum manifest not found at {path}")
    return parse_checksum_manifest(path.read_bytes())


def verify_artifact(path: str | Path, expected_sha256: str) -> None:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    actual = sha256_file(path)
    if actual != expected_sha256:
        raise ValueError(
            f"checksum mismatch for STAFF III artifact {path.name}: "
            f"expected {expected_sha256}, got {actual}"
        )


def load_record_names(
    source_root: str | Path, checksums: Mapping[str, str]
) -> tuple[str, ...]:
    path = Path(source_root) / "RECORDS"
    verify_artifact(path, checksums.get("RECORDS", ""))
    records = tuple(
        str(PurePosixPath(value.strip()))
        for value in path.read_text(encoding="ascii").splitlines()
        if value.strip()
    )
    if len(records) != 520 or len(set(records)) != 520:
        raise ValueError("STAFF III 1.0.0 must contain exactly 520 unique records")
    if any(not re.fullmatch(r"data/\d{3}[a-z]", value) for value in records):
        raise ValueError("STAFF III RECORDS contains an unexpected record path")
    return records


def _normalize_record_name(value: Any) -> str | None:
    text = str(value or "").strip().casefold()
    match = re.fullmatch(r"0*(\d{1,3})([a-z])", text)
    if not match:
        return None
    return f"{int(match.group(1)):03d}{match.group(2)}"


def _column_letters(reference: str) -> str:
    match = re.match(r"([A-Z]+)", reference)
    return match.group(1) if match else ""


def _xlsx_rows(raw: bytes) -> list[dict[str, str]]:
    """Read plain cell values from the single-sheet pinned metadata workbook.

    The source workbook has no formulas needed by the adapter, so a small
    standard-library parser avoids adding a spreadsheet dependency to runtime.
    """

    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise ValueError("STAFF III metadata workbook is not a valid xlsx archive") from exc
    namespace = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    try:
        strings_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
        sheet_root = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    except (KeyError, ET.ParseError) as exc:
        raise ValueError("STAFF III metadata workbook is missing required XML") from exc
    shared = [
        "".join(node.text or "" for node in item.iter(f"{{{namespace['m']}}}t"))
        for item in strings_root.findall("m:si", namespace)
    ]
    rows: list[dict[str, str]] = []
    for row in sheet_root.findall(".//m:sheetData/m:row", namespace):
        values: dict[str, str] = {}
        for cell in row.findall("m:c", namespace):
            reference = str(cell.attrib.get("r") or "")
            column = _column_letters(reference)
            value_node = cell.find("m:v", namespace)
            value = "" if value_node is None else str(value_node.text or "")
            if cell.attrib.get("t") == "s" and value:
                try:
                    value = shared[int(value)]
                except (IndexError, ValueError) as exc:
                    raise ValueError("STAFF III workbook has an invalid shared-string index") from exc
            if column:
                values[column] = value.strip()
        rows.append(values)
    return rows


def _parse_seconds(value: Any, *, expected: int | None = None) -> tuple[float, ...]:
    text = str(value or "").strip()
    if not text:
        return ()
    try:
        values = tuple(float(part.strip()) for part in text.split(";") if part.strip())
    except ValueError as exc:
        raise ValueError(f"invalid STAFF III protocol timing {text!r}") from exc
    if expected is not None and len(values) != expected:
        raise ValueError(f"STAFF III protocol timing {text!r} must contain {expected} values")
    if any(not np.isfinite(item) or item < 0 for item in values):
        raise ValueError("STAFF III protocol timings must be finite and non-negative")
    return values


@dataclass(frozen=True)
class InflationProtocol:
    record_name: str
    ordinal: int
    artery: str
    pre_inflation_seconds: float
    inflation_seconds: float
    post_inflation_seconds: float
    documented_injection_seconds: tuple[float, ...]


@dataclass(frozen=True)
class PatientProtocol:
    # These raw source fields never leave this offline adapter.
    source_patient_number: int
    baseline_record: str
    baseline_kind: str
    recovery_record: str
    recovery_kind: str
    inflations: tuple[InflationProtocol, ...]


def parse_protocol_workbook(raw: bytes) -> tuple[PatientProtocol, ...]:
    """Parse only records/timings needed for comparison extraction.

    Age, sex, prior-MI status, and every other patient attribute are ignored by
    construction so they cannot leak into the derived artifact.
    """

    protocols: list[PatientProtocol] = []
    for row in _xlsx_rows(raw):
        patient_text = str(row.get("A") or "").strip()
        if not re.fullmatch(r"\d{1,3}", patient_text):
            continue
        baseline = next(
            (
                (_normalize_record_name(row.get(column)), kind)
                for column, kind in _BASELINE_COLUMNS
                if _normalize_record_name(row.get(column))
            ),
            None,
        )
        recovery = next(
            (
                (_normalize_record_name(row.get(column)), kind)
                for column, kind in _RECOVERY_COLUMNS
                if _normalize_record_name(row.get(column))
            ),
            None,
        )
        if not baseline or not recovery:
            continue
        inflations: list[InflationProtocol] = []
        for record_col, artery_col, timing_col, injection_col, ordinal in _INFLATION_COLUMNS:
            record_name = _normalize_record_name(row.get(record_col))
            if not record_name:
                continue
            timing = _parse_seconds(row.get(timing_col), expected=3)
            injections = _parse_seconds(row.get(injection_col)) if injection_col else ()
            inflations.append(
                InflationProtocol(
                    record_name=record_name,
                    ordinal=ordinal,
                    artery=str(row.get(artery_col) or "").strip(),
                    pre_inflation_seconds=timing[0],
                    inflation_seconds=timing[1],
                    post_inflation_seconds=timing[2],
                    documented_injection_seconds=injections,
                )
            )
        if inflations:
            protocols.append(
                PatientProtocol(
                    source_patient_number=int(patient_text),
                    baseline_record=str(baseline[0]),
                    baseline_kind=baseline[1],
                    recovery_record=str(recovery[0]),
                    recovery_kind=recovery[1],
                    inflations=tuple(inflations),
                )
            )
    if not protocols:
        raise ValueError("STAFF III metadata workbook yielded no complete comparison protocols")
    return tuple(protocols)


def load_protocols(
    source_root: str | Path, checksums: Mapping[str, str]
) -> tuple[PatientProtocol, ...]:
    path = Path(source_root) / METADATA_FILENAME
    verify_artifact(path, checksums.get(METADATA_FILENAME, ""))
    return parse_protocol_workbook(path.read_bytes())


@dataclass(frozen=True)
class HeaderSummary:
    record_name: str
    sampling_frequency: int
    sample_count: int
    leads: tuple[str, ...]


def parse_header(text: str, expected_record_name: str) -> HeaderSummary:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        raise ValueError("STAFF III header is empty")
    first = lines[0].split()
    if len(first) < 4:
        raise ValueError("STAFF III header first row is malformed")
    record_name, signal_count, fs, sample_count = first[:4]
    if record_name != expected_record_name:
        raise ValueError("STAFF III header record identity does not match its path")
    try:
        signal_count_i = int(signal_count)
        fs_i = int(float(fs))
        sample_count_i = int(sample_count)
    except ValueError as exc:
        raise ValueError("STAFF III header dimensions are malformed") from exc
    signal_rows = [line for line in lines[1:] if not line.startswith("#")][:signal_count_i]
    leads = tuple(line.split()[-1] for line in signal_rows)
    if signal_count_i != 9 or fs_i != SOURCE_FS or set(leads) != set(RAW_LEADS):
        raise ValueError("STAFF III record must be the expected 9-channel, 1000-Hz source ECG")
    if sample_count_i <= 0:
        raise ValueError("STAFF III record has no waveform samples")
    return HeaderSummary(record_name, fs_i, sample_count_i, leads)


def load_header(
    source_root: str | Path, record_name: str, checksums: Mapping[str, str]
) -> HeaderSummary:
    relative = f"data/{record_name}.hea"
    path = Path(source_root) / relative
    verify_artifact(path, checksums.get(relative, ""))
    return parse_header(path.read_text(encoding="ascii"), record_name)


@dataclass(frozen=True)
class FrameSpec:
    role: str
    source_record_name: str
    start_sample: int
    end_sample: int
    source_phase: str


@dataclass(frozen=True)
class ComparisonEpisodeSpec:
    episode_id: str
    baseline: FrameSpec
    occlusion: FrameSpec
    recovery: FrameSpec
    occlusion_ordinal: int
    occluded_artery: str
    documented_injection_seconds: tuple[float, ...]

    @property
    def frames(self) -> tuple[FrameSpec, FrameSpec, FrameSpec]:
        return (self.baseline, self.occlusion, self.recovery)


class SourceFrameQualityError(ValueError):
    """A source waveform window is unusable but does not invalidate the release."""

    reason = "non_finite_source_samples"


def _ordinary_frame(
    role: str, record_name: str, sample_count: int, source_phase: str
) -> FrameSpec | None:
    length = int(round(FRAME_SECONDS * SOURCE_FS))
    guard = int(round(EVENT_GUARD_SECONDS * SOURCE_FS))
    if sample_count < length + 2 * guard:
        return None
    if role == "baseline":
        end = sample_count - guard
        start = end - length
    else:
        start = guard
        end = start + length
    return FrameSpec(role, record_name, start, end, source_phase)


def _occlusion_frame(
    inflation: InflationProtocol, sample_count: int
) -> FrameSpec | None:
    length = int(round(FRAME_SECONDS * SOURCE_FS))
    guard = int(round(EVENT_GUARD_SECONDS * SOURCE_FS))
    inflation_start = int(round(inflation.pre_inflation_seconds * SOURCE_FS))
    inflation_end = min(
        sample_count,
        int(round((inflation.pre_inflation_seconds + inflation.inflation_seconds) * SOURCE_FS)),
    )
    earliest = inflation_start + guard
    latest_end = inflation_end - guard
    if latest_end - earliest < length:
        return None

    # Prefer a late-occlusion frame, but avoid every *documented* contrast
    # injection by a conservative guard. The source warns that injection
    # annotations are incomplete, which is retained in the artifact ceiling.
    candidate_end = latest_end
    injection_samples = sorted(
        int(round(value * SOURCE_FS)) for value in inflation.documented_injection_seconds
    )
    while candidate_end - length >= earliest:
        start = candidate_end - length
        overlaps = [
            value for value in injection_samples if start - guard < value < candidate_end + guard
        ]
        if not overlaps:
            return FrameSpec(
                "occlusion",
                inflation.record_name,
                start,
                candidate_end,
                "controlled_balloon_occlusion",
            )
        candidate_end = min(overlaps) - guard
    return None


def build_episode_specs(
    protocols: Sequence[PatientProtocol],
    headers: Mapping[str, HeaderSummary],
) -> tuple[ComparisonEpisodeSpec, ...]:
    """Create deterministic complete triples without serializing source ids."""

    candidates: list[tuple[PatientProtocol, InflationProtocol, FrameSpec, FrameSpec, FrameSpec]] = []
    for protocol in sorted(protocols, key=lambda item: item.source_patient_number):
        if protocol.source_patient_number in KNOWN_LEAD_CONFIGURATION_EXCLUSIONS:
            continue
        baseline_header = headers.get(protocol.baseline_record)
        recovery_header = headers.get(protocol.recovery_record)
        if not baseline_header or not recovery_header:
            continue
        baseline = _ordinary_frame(
            "baseline",
            protocol.baseline_record,
            baseline_header.sample_count,
            f"baseline_{protocol.baseline_kind.casefold()}",
        )
        recovery = _ordinary_frame(
            "recovery",
            protocol.recovery_record,
            recovery_header.sample_count,
            f"post_inflation_{protocol.recovery_kind.casefold()}",
        )
        if not baseline or not recovery:
            continue
        for inflation in protocol.inflations:
            inflation_header = headers.get(inflation.record_name)
            if not inflation_header:
                continue
            occlusion = _occlusion_frame(inflation, inflation_header.sample_count)
            if occlusion:
                candidates.append((protocol, inflation, baseline, occlusion, recovery))

    episodes: list[ComparisonEpisodeSpec] = []
    for sequence, (_, inflation, baseline, occlusion, recovery) in enumerate(candidates, start=1):
        episodes.append(
            ComparisonEpisodeSpec(
                episode_id=f"staff-iii-episode-{sequence:04d}",
                baseline=baseline,
                occlusion=occlusion,
                recovery=recovery,
                occlusion_ordinal=inflation.ordinal,
                occluded_artery=inflation.artery,
                documented_injection_seconds=inflation.documented_injection_seconds,
            )
        )
    return tuple(episodes)


@dataclass(frozen=True)
class SourceInventory:
    source_root: Path
    protocols: tuple[PatientProtocol, ...]
    episodes: tuple[ComparisonEpisodeSpec, ...]
    record_count: int
    total_protocol_count: int
    errors: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "sourceId": SOURCE_ID,
            "sourceVersion": DESCRIPTOR.version,
            "datasetTitle": DESCRIPTOR.dataset_title,
            "licenseId": DESCRIPTOR.license_id,
            "labelAuthority": DESCRIPTOR.label_authority,
            "recordCount": self.record_count,
            "protocolPatientCount": self.total_protocol_count,
            "protocolPatientsScanned": len(self.protocols),
            "candidateEpisodeCount": len(self.episodes),
            "candidateFrameCount": len(self.episodes) * 3,
            "phaseCounts": {"baseline": len(self.episodes), "occlusion": len(self.episodes), "recovery": len(self.episodes)},
            "checksumManifestSha256": CHECKSUM_MANIFEST_SHA256,
            "metadataWorkbookSha256": METADATA_XLSX_SHA256,
            "artifactSchemaVersion": ARTIFACT_SCHEMA_VERSION,
            "extractionVersion": EXTRACTION_VERSION,
            "currentRuntimeConnected": False,
            "reviewRequiredBeforeLearnerServing": True,
            "errors": list(self.errors),
        }


def inventory_source(source_root: str | Path, *, protocol_limit: int = 0) -> SourceInventory:
    if protocol_limit < 0:
        raise ValueError("protocol limit may not be negative")
    root = Path(source_root)
    checksums = load_checksum_manifest(root)
    records = load_record_names(root, checksums)
    all_protocols = load_protocols(root, checksums)
    protocols = all_protocols[:protocol_limit] if protocol_limit else all_protocols
    needed_records = sorted(
        {
            value
            for protocol in protocols
            for value in (
                protocol.baseline_record,
                protocol.recovery_record,
                *(item.record_name for item in protocol.inflations),
            )
        }
    )
    record_set = {PurePosixPath(item).name for item in records}
    errors: list[str] = []
    headers: dict[str, HeaderSummary] = {}
    for record_name in needed_records:
        if record_name not in record_set:
            errors.append("metadata references a record absent from RECORDS")
            continue
        try:
            headers[record_name] = load_header(root, record_name, checksums)
        except Exception as exc:
            errors.append(f"header validation failed: {type(exc).__name__}: {exc}")
    episodes = build_episode_specs(protocols, headers)
    return SourceInventory(
        root,
        protocols,
        episodes,
        len(records),
        len(all_protocols),
        tuple(errors),
    )


def select_episodes(
    episodes: Sequence[ComparisonEpisodeSpec], *, limit: int = 0
) -> tuple[ComparisonEpisodeSpec, ...]:
    if limit < 0:
        raise ValueError("limit may not be negative")
    ordered = tuple(sorted(episodes, key=lambda item: item.episode_id))
    return ordered[:limit] if limit else ordered


def _derive_twelve_leads(raw: Mapping[str, Sequence[float]]) -> dict[str, np.ndarray]:
    missing = set(RAW_LEADS) - set(raw)
    if missing:
        raise ValueError(f"STAFF III source frame is missing required leads: {sorted(missing)}")
    arrays = {lead: np.asarray(raw[lead], dtype=np.float64) for lead in RAW_LEADS}
    lengths = {len(value) for value in arrays.values()}
    if len(lengths) != 1 or not lengths or next(iter(lengths)) == 0:
        raise ValueError("STAFF III source leads must have one non-empty common length")
    if not all(np.isfinite(value).all() for value in arrays.values()):
        raise SourceFrameQualityError(
            "STAFF III source frame contains missing or non-finite lead samples"
        )
    lead_i = arrays["I"]
    lead_ii = arrays["II"]
    return {
        "I": lead_i,
        "II": lead_ii,
        "III": arrays["III"],
        "aVR": -(lead_i + lead_ii) / 2.0,
        "aVL": lead_i - lead_ii / 2.0,
        "aVF": lead_ii - lead_i / 2.0,
        **{lead: arrays[lead] for lead in ("V1", "V2", "V3", "V4", "V5", "V6")},
    }


def _downsample(signal: np.ndarray, source_fs: int, target_fs: int) -> np.ndarray:
    if source_fs % target_fs != 0:
        raise ValueError("STAFF III target sampling rate must divide the 1000-Hz source rate")
    factor = source_fs // target_fs
    usable = (len(signal) // factor) * factor
    if usable <= 0:
        raise ValueError("STAFF III frame is too short to downsample")
    # Deterministic boxcar anti-aliasing before decimation.
    return signal[:usable].reshape(-1, factor).mean(axis=1)


def read_frame(
    source_root: str | Path,
    frame: FrameSpec,
    checksums: Mapping[str, str],
) -> dict[str, list[float]]:
    """Checksum-verify and read one local WFDB frame; no remote fallback."""

    root = Path(source_root)
    for suffix in ("hea", "dat"):
        relative = f"data/{frame.source_record_name}.{suffix}"
        expected = checksums.get(relative)
        if not expected:
            raise ValueError(f"STAFF III checksum manifest has no {relative} entry")
        verify_artifact(root / relative, expected)
    try:
        import wfdb  # type: ignore
    except ImportError as exc:  # pragma: no cover - environment-specific error path
        raise RuntimeError("offline STAFF III import requires the wfdb package") from exc
    signal, fields = wfdb.rdsamp(
        str(root / "data" / frame.source_record_name),
        sampfrom=frame.start_sample,
        sampto=frame.end_sample,
    )
    names = [str(value) for value in fields.get("sig_name") or []]
    if int(round(float(fields.get("fs") or 0))) != SOURCE_FS or signal.ndim != 2:
        raise ValueError("STAFF III WFDB frame dimensions do not match the source contract")
    raw = {name: signal[:, index].tolist() for index, name in enumerate(names)}
    twelve = _derive_twelve_leads(raw)
    return {
        lead: _downsample(twelve[lead], SOURCE_FS, TARGET_FS).round(6).tolist()
        for lead in LEADS
    }


def _frame_artifact(
    episode_id: str,
    frame: FrameSpec,
    signal: Mapping[str, Sequence[float]],
) -> dict[str, Any]:
    expected_points = int(round(FRAME_SECONDS * TARGET_FS))
    if set(signal) != set(LEADS) or {len(signal[lead]) for lead in LEADS} != {expected_points}:
        raise ValueError("STAFF III derived frame must be a complete 10-second 12-lead ECG")
    frame_id = f"{episode_id}:{frame.role}"
    return {
        "frameId": frame_id,
        "role": frame.role,
        "sourcePhase": frame.source_phase,
        "signalFingerprint": waveform_fingerprint(signal),
        "waveform": {
            "leads": list(LEADS),
            "samplingFrequency": TARGET_FS,
            "durationSeconds": FRAME_SECONDS,
            "isTwelveLead": True,
            "surfaceLeadConfiguration": "precordial_standard_limb_mason_likar",
            "derivedLeads": ["aVR", "aVL", "aVF"],
        },
    }


def build_episode_artifact(
    spec: ComparisonEpisodeSpec,
    signals_by_role: Mapping[str, Mapping[str, Sequence[float]]],
) -> dict[str, Any]:
    """Build the public authoring packet with an explicit evidence ceiling."""

    if set(signals_by_role) != {"baseline", "occlusion", "recovery"}:
        raise ValueError("STAFF III comparison episode requires all three protocol phases")
    frames = [
        _frame_artifact(spec.episode_id, frame, signals_by_role[frame.role])
        for frame in spec.frames
    ]
    return {
        "schemaVersion": ARTIFACT_SCHEMA_VERSION,
        "episodeId": spec.episode_id,
        "source": SOURCE_ID,
        "sourceVersion": DESCRIPTOR.version,
        "licenseId": DESCRIPTOR.license_id,
        "extractionVersion": EXTRACTION_VERSION,
        "sequence": ["baseline", "occlusion", "recovery"],
        "frames": frames,
        "protocolContext": {
            "setting": "elective_ptca",
            "middlePhase": "controlled_balloon_occlusion",
            "occlusionOrdinal": spec.occlusion_ordinal,
            "occludedArterySourceText": spec.occluded_artery or None,
            "documentedContrastInjectionCount": len(spec.documented_injection_seconds),
            "contrastAnnotationComplete": False,
        },
        "sourceProvenance": {
            **source_catalog_entry(SOURCE_ID),
            "checksumManifestSha256": CHECKSUM_MANIFEST_SHA256,
            "metadataWorkbookSha256": METADATA_XLSX_SHA256,
            "rawPatientIdentifiersIncluded": False,
            "rawRecordIdentifiersIncluded": False,
        },
        "comparisonTruth": {
            "protocolOrderVerified": True,
            "sameSourcePatientVerifiedOffline": True,
            "adjudicatedMorphologyChanges": [],
            "adjudicatedUnchangedRegions": [],
            "morphologyAnswerKeyReady": False,
        },
        "educationalEligibility": {
            "educationalUse": "acute_serial",
            "candidateTasks": ["compare_waveforms", "mark_observed_change"],
            "eligibleModes": [],
            "eligibleSubskills": {},
            "currentRuntimeModeConnected": False,
            "rapidPracticeEligible": False,
            "clinicalCaseEligible": False,
            "clinicalManagementEligible": False,
            "masteryEvidenceEligible": False,
            "reviewRequiredBeforeLearnerServing": True,
        },
        "llmAllowedClaims": [
            "The frames are ordered baseline, protocol-timed controlled occlusion, then recovery.",
            "Describe visible differences only after a reviewer-authored comparison key is present.",
        ],
        "llmForbiddenClaims": [
            "Do not call a spontaneous ACS, STEMI, OMI, infarction, or treatment response from protocol phase alone.",
            "Do not infer symptoms, hemodynamics, prognosis, medication, intervention, or management.",
            "Do not convert the source artery field into an ECG localization answer key without review.",
        ],
        "currentStudentServingEligible": False,
    }


def artifact_fingerprint(episodes: Sequence[Mapping[str, Any]]) -> str:
    import json

    payload = json.dumps(list(episodes), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _sha256_bytes(payload)


def validate_episode_artifact(episode: Mapping[str, Any]) -> None:
    frames = episode.get("frames") or []
    eligibility = episode.get("educationalEligibility") or {}
    truth = episode.get("comparisonTruth") or {}
    roles = [frame.get("role") for frame in frames if isinstance(frame, Mapping)]
    fingerprints = [
        str(frame.get("signalFingerprint") or "")
        for frame in frames
        if isinstance(frame, Mapping)
    ]
    if (
        episode.get("schemaVersion") != ARTIFACT_SCHEMA_VERSION
        or episode.get("source") != SOURCE_ID
        or episode.get("sourceVersion") != DESCRIPTOR.version
        or episode.get("sequence") != ["baseline", "occlusion", "recovery"]
        or roles != ["baseline", "occlusion", "recovery"]
        or len(fingerprints) != 3
        or not all(re.fullmatch(r"[0-9a-f]{64}", value) for value in fingerprints)
        or not isinstance(eligibility, Mapping)
        or eligibility.get("eligibleModes") != []
        or eligibility.get("currentRuntimeModeConnected") is not False
        or eligibility.get("clinicalManagementEligible") is not False
        or eligibility.get("masteryEvidenceEligible") is not False
        or eligibility.get("reviewRequiredBeforeLearnerServing") is not True
        or not isinstance(truth, Mapping)
        or truth.get("protocolOrderVerified") is not True
        or truth.get("morphologyAnswerKeyReady") is not False
        or episode.get("currentStudentServingEligible") is not False
    ):
        raise ValueError("STAFF III comparison artifact violates its review-gated contract")


def build_release_manifest(
    episodes: Sequence[Mapping[str, Any]],
    *,
    source_candidate_episode_count: int | None = None,
    quality_exclusion_counts: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    episode_list = list(episodes)
    for episode in episode_list:
        validate_episode_artifact(episode)
    exclusions = {
        str(reason): int(count)
        for reason, count in (quality_exclusion_counts or {}).items()
        if int(count) > 0
    }
    excluded_count = sum(exclusions.values())
    candidate_count = (
        len(episode_list) + excluded_count
        if source_candidate_episode_count is None
        else int(source_candidate_episode_count)
    )
    if candidate_count != len(episode_list) + excluded_count:
        raise ValueError("STAFF III candidate and quality-exclusion counts do not reconcile")
    return {
        "version": 1,
        "complete": True,
        "artifactType": "ecg_comparison_episode_candidates",
        "artifactSchemaVersion": ARTIFACT_SCHEMA_VERSION,
        "sourceCatalog": {SOURCE_ID: source_catalog_entry(SOURCE_ID)},
        "sourceId": SOURCE_ID,
        "sourceVersion": DESCRIPTOR.version,
        "extractionVersion": EXTRACTION_VERSION,
        "episodeCount": len(episode_list),
        "frameCount": len(episode_list) * 3,
        "sourceCandidateEpisodeCount": candidate_count,
        "qualityExcludedEpisodeCount": excluded_count,
        "qualityExclusionCounts": exclusions,
        "sequenceCounts": dict(
            Counter("->".join(str(value) for value in item.get("sequence") or []) for item in episode_list)
        ),
        "episodesSha256": artifact_fingerprint(episode_list),
        "rawPatientIdentifiersIncluded": False,
        "rawRecordIdentifiersIncluded": False,
        "currentRuntimeConnected": False,
        "reviewRequiredBeforeLearnerServing": True,
    }


def source_record_names(spec: ComparisonEpisodeSpec) -> tuple[str, ...]:
    """Offline-only helper for checksum/read orchestration; never serialize it."""

    return tuple(frame.source_record_name for frame in spec.frames)


def artifact_contains_raw_record_identity(
    artifact: Mapping[str, Any], record_names: Iterable[str]
) -> bool:
    """Detect a leaked raw record token without false-matching opaque hashes.

    STAFF record names are short hexadecimal-looking tokens such as ``017b``.
    A plain substring scan can therefore find one by chance inside a SHA-256
    fingerprint. Traverse the authored structure and require token boundaries:
    an exact value or path component is rejected, while the same characters
    embedded in an opaque digest are not.
    """

    patterns = tuple(
        re.compile(rf"(?<![A-Za-z0-9]){re.escape(str(name))}(?![A-Za-z0-9])")
        for name in record_names
        if str(name)
    )

    def contains(value: Any) -> bool:
        if isinstance(value, Mapping):
            return any(contains(key) or contains(item) for key, item in value.items())
        if isinstance(value, (list, tuple, set)):
            return any(contains(item) for item in value)
        if isinstance(value, str):
            return any(pattern.search(value) for pattern in patterns)
        return False

    return contains(artifact)


def iter_frame_roles() -> Iterable[str]:
    return ("baseline", "occlusion", "recovery")
