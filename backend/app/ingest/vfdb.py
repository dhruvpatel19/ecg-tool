"""Checksum-gated adapter for the MIT-BIH malignant ventricular ECG stream.

The MIT-BIH Malignant Ventricular Ectopy Database (VFDB) contains two-channel
ambulatory ECG recordings with expert *rhythm-change* annotations.  It does not
contain pulse, perfusion, treatment, response-to-treatment, or beat labels.

This module is intentionally an offline source foundation.  It creates real,
provenance-complete rhythm-window packets in a dedicated rhythm-stream store;
it does not connect them to the current Clinical UI or award ACLS/action
mastery.  A future reviewed resuscitation lane may use the packets only for the
exact rhythm-recognition/discrimination contract encoded below and must join a
separate bedside-state source plus a reviewed current algorithm for actions.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import math
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

import numpy as np

from .source_contract import (
    KNOWN_SOURCES,
    SourceRecord,
    namespaced_case_id,
    validate_source_record,
)


SOURCE_ID = "mit-bih-vfdb"
DESCRIPTOR = KNOWN_SOURCES[SOURCE_ID]
EXTRACTION_VERSION = "vfdb-guarded-rhythm-window-v1"
SOURCE_FS = 250
WINDOW_SECONDS = 10.0
DEFAULT_STRIDE_SECONDS = 10.0
DEFAULT_BOUNDARY_GUARD_SECONDS = 0.5
CHANNELS = ("ECG1", "ECG2")
SOURCE_SIGNAL_NAMES = ("ECG", "ECG")
FUTURE_MODE_ID = "clinical_resuscitation_rhythm"

# Version-pinned official release artifacts.  The local checksum manifest is
# itself pinned before any of its per-file values are trusted.
CHECKSUM_MANIFEST_SHA256 = "1157e2168f131f2c53e6eb0e3263c0835d286fc05de94066e069e29b810cd6f6"
RECORDS_SHA256 = "b9ec1c4db10959e3ed4a3534c2ad3f67910ef667c64adfbdae6edeb54f6c7156"
EXPECTED_RECORDS = (
    "418", "419", "420", "421", "422", "423", "424", "425", "426", "427", "428",
    "429", "430", "602", "605", "607", "609", "610", "611", "612", "614", "615",
)


@dataclass(frozen=True)
class RhythmLabelContract:
    raw_code: str
    description: str
    canonical_rhythm_id: str | None
    eligible_modes: tuple[str, ...]
    eligible_subskills: tuple[str, ...]

    @property
    def learner_window_eligible(self) -> bool:
        return bool(self.canonical_rhythm_id and self.eligible_modes and self.eligible_subskills)


def _rhythm(
    raw_code: str,
    description: str,
    canonical_rhythm_id: str,
) -> RhythmLabelContract:
    return RhythmLabelContract(
        raw_code=raw_code,
        description=description,
        canonical_rhythm_id=canonical_rhythm_id,
        eligible_modes=(FUTURE_MODE_ID,),
        eligible_subskills=("recognize", "discriminate"),
    )


# This is an exact transcription of the annotation dictionary published on the
# versioned PhysioNet VFDB page.  Source labels are preserved verbatim.  Where
# two source spellings mean the same rhythm (N/NSR and VF/VFIB), they share a
# canonical rhythm id without erasing the original code.
RHYTHM_LABELS: dict[str, RhythmLabelContract] = {
    "AFIB": _rhythm("AFIB", "Atrial fibrillation", "atrial_fibrillation"),
    "ASYS": _rhythm("ASYS", "Asystole", "asystole"),
    "B": _rhythm("B", "Ventricular bigeminy", "ventricular_bigeminy"),
    "BI": _rhythm("BI", "First-degree heart block", "av_block_first_degree"),
    "HGEA": _rhythm(
        "HGEA", "High-grade ventricular ectopic activity", "high_grade_ventricular_ectopy"
    ),
    "N": _rhythm("N", "Normal sinus rhythm", "sinus_rhythm"),
    "NSR": _rhythm("NSR", "Normal sinus rhythm", "sinus_rhythm"),
    "NOD": _rhythm("NOD", "Nodal (AV junctional) rhythm", "junctional_rhythm"),
    "PM": _rhythm("PM", "Pacemaker rhythm", "paced_rhythm"),
    "SBR": _rhythm("SBR", "Sinus bradycardia", "bradycardia"),
    "SVTA": _rhythm(
        "SVTA", "Supraventricular tachyarrhythmia", "supraventricular_tachyarrhythmia"
    ),
    "VER": _rhythm("VER", "Ventricular escape rhythm", "ventricular_escape_rhythm"),
    "VF": _rhythm("VF", "Ventricular fibrillation", "ventricular_fibrillation"),
    "VFIB": _rhythm("VFIB", "Ventricular fibrillation", "ventricular_fibrillation"),
    "VFL": _rhythm("VFL", "Ventricular flutter", "ventricular_flutter"),
    "VT": _rhythm("VT", "Ventricular tachycardia", "ventricular_tachycardia"),
    "NOISE": RhythmLabelContract(
        raw_code="NOISE",
        description="Noise interval",
        canonical_rhythm_id=None,
        eligible_modes=(),
        eligible_subskills=(),
    ),
}


@dataclass(frozen=True)
class RhythmEpisode:
    raw_aux: str
    rhythm_code: str
    start_sample: int
    end_sample: int
    annotation_index: int

    @property
    def contract(self) -> RhythmLabelContract:
        return RHYTHM_LABELS[self.rhythm_code]


@dataclass(frozen=True)
class WindowSpec:
    record_name: str
    patient_id: str
    sampling_frequency: int
    start_sample: int
    end_sample: int
    episode_start_sample: int
    episode_end_sample: int
    annotation_index: int
    raw_rhythm_aux: str
    rhythm_code: str
    canonical_rhythm_id: str

    @property
    def source_record_id(self) -> str:
        return f"{self.record_name}@{self.start_sample:09d}-{self.end_sample:09d}"

    @property
    def case_id(self) -> str:
        return namespaced_case_id(SOURCE_ID, self.source_record_id)


@dataclass(frozen=True)
class SourceInventory:
    source_root: Path
    records_scanned: int
    windows: tuple[WindowSpec, ...]
    annotation_counts: dict[str, int]
    episode_seconds: dict[str, float]
    missing_waveform_records: tuple[str, ...]
    checksums_by_record: dict[str, dict[str, str]]
    errors: tuple[str, ...]

    @property
    def rhythm_counts(self) -> dict[str, int]:
        return dict(sorted(Counter(item.canonical_rhythm_id for item in self.windows).items()))

    @property
    def raw_rhythm_counts(self) -> dict[str, int]:
        return dict(sorted(Counter(item.rhythm_code for item in self.windows).items()))

    @property
    def patient_count(self) -> int:
        return len({item.patient_id for item in self.windows})

    def as_dict(self) -> dict[str, Any]:
        missing = set(self.missing_waveform_records)
        readable = [item for item in self.windows if item.record_name not in missing]
        return {
            "sourceId": SOURCE_ID,
            "sourceVersion": DESCRIPTOR.version,
            "datasetTitle": DESCRIPTOR.dataset_title,
            "licenseId": DESCRIPTOR.license_id,
            "publishedUncompressedSize": DESCRIPTOR.published_uncompressed_size,
            "labelAuthority": DESCRIPTOR.label_authority,
            "recordsScanned": self.records_scanned,
            "uniqueSourcePatients": self.patient_count,
            "annotationCount": sum(self.annotation_counts.values()),
            "annotationCounts": dict(sorted(self.annotation_counts.items())),
            "episodeSeconds": {
                key: round(value, 3) for key, value in sorted(self.episode_seconds.items())
            },
            "eligibleWindowCount": len(self.windows),
            "eligibleCanonicalRhythmCounts": self.rhythm_counts,
            "eligibleRawRhythmCounts": self.raw_rhythm_counts,
            "locallyReadableWindowCount": len(readable),
            "missingWaveformRecords": list(self.missing_waveform_records),
            "checksumManifestSha256": CHECKSUM_MANIFEST_SHA256,
            "currentRuntimeConnected": False,
            "eligibleModes": [FUTURE_MODE_ID],
            "eligibleSubskills": ["recognize", "discriminate"],
            "errors": list(self.errors),
        }


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_checksum_manifest(raw: bytes) -> dict[str, str]:
    """Parse only the exact version-pinned official ``SHA256SUMS.txt``."""

    actual = _sha256_bytes(raw)
    if actual != CHECKSUM_MANIFEST_SHA256:
        raise ValueError(
            "VFDB SHA256SUMS.txt does not match the pinned PhysioNet 1.0.0 checksum manifest"
        )
    values: dict[str, str] = {}
    for line_number, line in enumerate(raw.decode("ascii").splitlines(), start=1):
        match = re.fullmatch(r"([0-9a-f]{64})\s+\*?([^\\/]+)", line.strip())
        if not match:
            raise ValueError(f"malformed VFDB checksum row {line_number}")
        checksum, filename = match.groups()
        if filename in values:
            raise ValueError(f"duplicate VFDB checksum entry for {filename}")
        values[filename] = checksum
    if values.get("RECORDS") != RECORDS_SHA256:
        raise ValueError("VFDB RECORDS checksum does not match the pinned 1.0.0 release")
    return values


def load_checksum_manifest(source_root: str | Path) -> dict[str, str]:
    path = Path(source_root) / "SHA256SUMS.txt"
    if not path.is_file():
        raise FileNotFoundError(f"VFDB checksum manifest not found at {path}")
    return parse_checksum_manifest(path.read_bytes())


def verify_artifact(path: str | Path, expected_sha256: str) -> None:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    actual = sha256_file(path)
    if actual != expected_sha256:
        raise ValueError(f"checksum mismatch for {path.name}: expected {expected_sha256}, got {actual}")


def load_record_names(source_root: str | Path, checksums: Mapping[str, str]) -> tuple[str, ...]:
    path = Path(source_root) / "RECORDS"
    verify_artifact(path, checksums.get("RECORDS", ""))
    records = tuple(value.strip() for value in path.read_text(encoding="ascii").splitlines() if value.strip())
    if records != EXPECTED_RECORDS:
        raise ValueError("VFDB RECORDS contents/order differ from the pinned 1.0.0 release")
    return records


def normalize_rhythm_aux(aux_note: str | None) -> str:
    value = str(aux_note or "").replace("\x00", "").strip()
    return value[1:] if value.startswith("(") else value


def segment_rhythm_episodes(
    samples: Sequence[int],
    symbols: Sequence[str],
    aux_notes: Sequence[str],
    record_end_sample: int,
) -> list[RhythmEpisode]:
    """Create exact source-labelled episodes bounded by every rhythm marker.

    ``NOISE`` is retained as an episode for provenance/inventory but it has no
    educational eligibility and yields no windows.  Samples before the first
    expert marker remain unlabelled and are never inferred.
    """

    if not (len(samples) == len(symbols) == len(aux_notes)):
        raise ValueError("annotation samples, symbols, and aux notes must have equal lengths")
    if record_end_sample <= 0:
        raise ValueError("record end sample must be positive")
    markers: list[tuple[int, str, str, int]] = []
    for index, (sample, symbol, aux) in enumerate(zip(samples, symbols, aux_notes)):
        code = normalize_rhythm_aux(aux)
        if str(symbol) != "+" or not code:
            raise ValueError("VFDB 1.0.0 .atr files must contain rhythm-change (+) annotations only")
        if code not in RHYTHM_LABELS:
            raise ValueError(f"unrecognized VFDB rhythm annotation: {code}")
        markers.append((int(sample), str(aux), code, index))
    if markers != sorted(markers, key=lambda row: row[0]):
        raise ValueError("VFDB rhythm annotations must be ordered by sample")

    episodes: list[RhythmEpisode] = []
    for position, (start, raw_aux, code, annotation_index) in enumerate(markers):
        end = markers[position + 1][0] if position + 1 < len(markers) else int(record_end_sample)
        if start < 0 or start >= record_end_sample or end <= start:
            raise ValueError(f"invalid VFDB episode boundary {start}:{end}")
        episodes.append(
            RhythmEpisode(
                raw_aux=raw_aux,
                rhythm_code=code,
                start_sample=start,
                end_sample=min(end, int(record_end_sample)),
                annotation_index=annotation_index,
            )
        )
    return episodes


def stable_windows(
    episode: RhythmEpisode,
    sampling_frequency: int,
    *,
    duration_seconds: float = WINDOW_SECONDS,
    stride_seconds: float = DEFAULT_STRIDE_SECONDS,
    boundary_guard_seconds: float = DEFAULT_BOUNDARY_GUARD_SECONDS,
) -> list[tuple[int, int]]:
    """Return deterministic, non-overlapping windows within one expert episode."""

    if sampling_frequency <= 0 or duration_seconds <= 0:
        raise ValueError("sampling frequency and duration must be positive")
    if stride_seconds < duration_seconds:
        raise ValueError("stride must be at least duration; overlapping windows are not admitted")
    if boundary_guard_seconds < 0:
        raise ValueError("boundary guard may not be negative")
    if not episode.contract.learner_window_eligible:
        return []
    length = int(round(duration_seconds * sampling_frequency))
    stride = int(round(stride_seconds * sampling_frequency))
    guard = int(round(boundary_guard_seconds * sampling_frequency))
    cursor = episode.start_sample + guard
    usable_end = episode.end_sample - guard
    windows: list[tuple[int, int]] = []
    while cursor + length <= usable_end:
        windows.append((cursor, cursor + length))
        cursor += stride
    return windows


def validate_vfdb_header(header: Any, record_name: str) -> None:
    """Fail closed if a local WFDB header differs from the pinned release shape."""

    fs = float(getattr(header, "fs", 0))
    if int(getattr(header, "n_sig", 0)) != 2:
        raise ValueError("VFDB records must contain exactly two ECG channels")
    if not math.isclose(fs, SOURCE_FS, rel_tol=0, abs_tol=1e-9):
        raise ValueError(f"VFDB record {record_name} has unexpected sampling frequency {fs}")
    if int(getattr(header, "sig_len", 0)) != 525_000:
        raise ValueError(f"VFDB record {record_name} has unexpected signal length")
    if tuple(getattr(header, "sig_name", ())) != SOURCE_SIGNAL_NAMES:
        raise ValueError(f"VFDB record {record_name} must preserve the two source ECG channel names")
    if tuple(getattr(header, "units", ())) != ("mV", "mV"):
        raise ValueError(f"VFDB record {record_name} must be calibrated in mV")
    if tuple(str(value) for value in getattr(header, "fmt", ())) != ("212", "212"):
        raise ValueError(f"VFDB record {record_name} has unexpected WFDB signal format")
    if tuple(float(value) for value in getattr(header, "adc_gain", ())) != (200.0, 200.0):
        raise ValueError(f"VFDB record {record_name} has unexpected ADC gain")
    source_files = tuple(str(value) for value in getattr(header, "file_name", ()))
    if source_files != (f"{record_name}.dat", f"{record_name}.dat"):
        raise ValueError(f"VFDB record {record_name} points at unexpected signal files")


def inventory_source(
    source_root: str | Path,
    *,
    record_names: Sequence[str] | None = None,
    duration_seconds: float = WINDOW_SECONDS,
    stride_seconds: float = DEFAULT_STRIDE_SECONDS,
    boundary_guard_seconds: float = DEFAULT_BOUNDARY_GUARD_SECONDS,
) -> SourceInventory:
    """Checksum-verify headers/annotations and inventory eligible real windows."""

    import wfdb  # Offline-only optional dependency.

    root = Path(source_root)
    checksums = load_checksum_manifest(root)
    available = load_record_names(root, checksums)
    wanted = set(record_names or available)
    unknown = sorted(wanted - set(available))
    if unknown:
        raise ValueError(f"unknown VFDB record(s): {', '.join(unknown)}")
    selected = [record for record in available if record in wanted]

    windows: list[WindowSpec] = []
    annotation_counts: Counter[str] = Counter()
    episode_seconds: Counter[str] = Counter()
    missing_waveforms: list[str] = []
    checksums_by_record: dict[str, dict[str, str]] = {}
    errors: list[str] = []
    for record_name in selected:
        try:
            names = (f"{record_name}.hea", f"{record_name}.atr", f"{record_name}.dat")
            expected: dict[str, str] = {}
            for filename in names:
                checksum = checksums.get(filename)
                if not checksum:
                    raise ValueError(f"official checksum manifest has no {filename} entry")
                expected[filename] = checksum
            verify_artifact(root / names[0], expected[names[0]])
            verify_artifact(root / names[1], expected[names[1]])
            if (root / names[2]).is_file():
                verify_artifact(root / names[2], expected[names[2]])
            else:
                missing_waveforms.append(record_name)
            checksums_by_record[record_name] = expected

            header = wfdb.rdheader(str(root / record_name))
            validate_vfdb_header(header, record_name)
            annotation = wfdb.rdann(str(root / record_name), "atr")
            samples = [int(value) for value in annotation.sample]
            symbols = [str(value) for value in annotation.symbol]
            aux_notes = [str(value) for value in (annotation.aux_note or [""] * len(samples))]
            episodes = segment_rhythm_episodes(samples, symbols, aux_notes, int(header.sig_len))
            for episode in episodes:
                annotation_counts[episode.rhythm_code] += 1
                episode_seconds[episode.rhythm_code] += (
                    episode.end_sample - episode.start_sample
                ) / SOURCE_FS
                contract = episode.contract
                if not contract.canonical_rhythm_id:
                    continue
                for start, end in stable_windows(
                    episode,
                    SOURCE_FS,
                    duration_seconds=duration_seconds,
                    stride_seconds=stride_seconds,
                    boundary_guard_seconds=boundary_guard_seconds,
                ):
                    windows.append(
                        WindowSpec(
                            record_name=record_name,
                            patient_id=record_name,
                            sampling_frequency=SOURCE_FS,
                            start_sample=start,
                            end_sample=end,
                            episode_start_sample=episode.start_sample,
                            episode_end_sample=episode.end_sample,
                            annotation_index=episode.annotation_index,
                            raw_rhythm_aux=episode.raw_aux,
                            rhythm_code=episode.rhythm_code,
                            canonical_rhythm_id=contract.canonical_rhythm_id,
                        )
                    )
        except Exception as exc:
            errors.append(f"{record_name}: {exc}")

    windows.sort(key=lambda item: (int(item.record_name), item.start_sample, item.end_sample))
    return SourceInventory(
        source_root=root,
        records_scanned=len(selected),
        windows=tuple(windows),
        annotation_counts=dict(annotation_counts),
        episode_seconds=dict(episode_seconds),
        missing_waveform_records=tuple(sorted(missing_waveforms, key=int)),
        checksums_by_record=checksums_by_record,
        errors=tuple(errors),
    )


def select_windows(
    windows: Sequence[WindowSpec],
    *,
    canonical_rhythm_ids: set[str] | None = None,
    limit: int = 0,
    max_per_rhythm: int = 0,
) -> list[WindowSpec]:
    if limit < 0 or max_per_rhythm < 0:
        raise ValueError("limit and max_per_rhythm may not be negative")
    selected: list[WindowSpec] = []
    counts: Counter[str] = Counter()
    for item in sorted(windows, key=lambda row: (int(row.record_name), row.start_sample)):
        if canonical_rhythm_ids and item.canonical_rhythm_id not in canonical_rhythm_ids:
            continue
        if max_per_rhythm and counts[item.canonical_rhythm_id] >= max_per_rhythm:
            continue
        selected.append(item)
        counts[item.canonical_rhythm_id] += 1
        if limit and len(selected) >= limit:
            break
    return selected


def read_window(source_root: str | Path, spec: WindowSpec) -> dict[str, list[float]]:
    """Read one checksum-verified source window in physical mV at native 250 Hz."""

    import wfdb  # Offline-only optional dependency.

    record = wfdb.rdrecord(
        str(Path(source_root) / spec.record_name),
        sampfrom=spec.start_sample,
        sampto=spec.end_sample,
        channels=[0, 1],
        physical=True,
    )
    if record.p_signal is None:
        raise ValueError(f"physical signal unavailable for {spec.source_record_id}")
    signal = np.asarray(record.p_signal, dtype=np.float64)
    expected = spec.end_sample - spec.start_sample
    if signal.shape != (expected, 2) or not np.isfinite(signal).all():
        raise ValueError(f"invalid VFDB signal window for {spec.source_record_id}")
    return {
        channel: np.round(signal[:, index], 5).tolist()
        for index, channel in enumerate(CHANNELS)
    }


def rhythm_waveform_fingerprint(signal_by_channel: Mapping[str, Sequence[float]]) -> str:
    """Stable SHA-256 over ordered channel content quantized to source µV."""

    digest = hashlib.sha256()
    digest.update(b"ecg-rhythm-content-v1\x00")
    for index, channel in enumerate(CHANNELS):
        if channel not in signal_by_channel:
            raise ValueError(f"missing rhythm channel {channel}")
        values = np.asarray(signal_by_channel[channel], dtype=np.float64)
        if values.ndim != 1 or not len(values) or not np.isfinite(values).all():
            raise ValueError(f"invalid rhythm channel {channel}")
        normalized = np.clip(np.round(values * 1000.0), -32767, 32767).astype("<i2")
        digest.update(index.to_bytes(1, "little"))
        digest.update(len(normalized).to_bytes(8, "little"))
        digest.update(normalized.tobytes())
    return digest.hexdigest()


def _validated_artifact_checksums(
    spec: WindowSpec, artifact_checksums: Mapping[str, str]
) -> dict[str, str]:
    required = [f"{spec.record_name}.{extension}" for extension in ("hea", "atr", "dat")]
    values: dict[str, str] = {}
    for filename in required:
        checksum = str(artifact_checksums.get(filename) or "")
        if not re.fullmatch(r"[0-9a-f]{64}", checksum):
            raise ValueError(f"missing or malformed pinned checksum for {filename}")
        values[filename] = checksum
    return values


def build_window_packet(
    spec: WindowSpec,
    signal_by_channel: Mapping[str, Sequence[float]],
    *,
    artifact_checksums: Mapping[str, str],
) -> dict[str, Any]:
    """Create a source-restricted real-rhythm packet, never a patient case."""

    contract = RHYTHM_LABELS[spec.rhythm_code]
    if contract.canonical_rhythm_id != spec.canonical_rhythm_id or not contract.learner_window_eligible:
        raise ValueError("window rhythm does not match an eligible VFDB label contract")
    expected_length = int(round(WINDOW_SECONDS * SOURCE_FS))
    normalized_signal = {channel: signal_by_channel[channel] for channel in CHANNELS}
    if any(len(normalized_signal[channel]) != expected_length for channel in CHANNELS):
        raise ValueError("VFDB packets require exactly 10 seconds / 2,500 samples on both channels")
    source_record = SourceRecord(
        source_record_id=spec.source_record_id,
        patient_id=spec.patient_id,
        signal_by_lead=normalized_signal,
        sampling_frequency=SOURCE_FS,
        labels=(spec.rhythm_code, spec.canonical_rhythm_id),
        label_provenance=(
            "expert reference WFDB rhythm-change annotation; guarded window fully contained in episode"
        ),
    )
    validate_source_record(DESCRIPTOR, source_record)
    checksums = _validated_artifact_checksums(spec, artifact_checksums)
    fingerprint = rhythm_waveform_fingerprint(normalized_signal)
    start_sec = spec.start_sample / SOURCE_FS
    end_sec = spec.end_sample / SOURCE_FS

    return {
        "case_id": spec.case_id,
        "stream_window_id": spec.case_id,
        "display_id": f"VFDB {spec.record_name} · {start_sec:.1f}–{end_sec:.1f}s",
        "source": SOURCE_ID,
        "student_serving_status": "foundation_only_not_connected",
        "current_student_serving_eligible": False,
        "waveform": {
            "storage": "dedicated_rhythm_stream_store",
            "sampling_frequency": SOURCE_FS,
            "duration_sec": WINDOW_SECONDS,
            "channels": [
                {"id": "ECG1", "sourceSignalName": "ECG", "sourceIndex": 0},
                {"id": "ECG2", "sourceSignalName": "ECG", "sourceIndex": 1},
            ],
            "isTwelveLead": False,
            "isMonitorOrDefibrillatorExport": False,
            "sourceModality": "two_channel_ambulatory_ecg",
        },
        "record_identity": {
            "sourceId": SOURCE_ID,
            "sourceRecordId": spec.source_record_id,
            "parentRecordId": spec.record_name,
            # VFDB publishes one de-identified record per described source
            # subject; retaining the record id groups all windows from that
            # subject without manufacturing a new identity.
            "patientId": spec.patient_id,
            "patientIdentityBasis": "source_record_identifier",
            "sourceVersion": DESCRIPTOR.version,
            "licenseId": DESCRIPTOR.license_id,
        },
        "source_labels": {
            "rhythm": {
                "rawAux": spec.raw_rhythm_aux,
                "rhythmCode": spec.rhythm_code,
                "sourceDescription": contract.description,
                "canonicalRhythmId": spec.canonical_rhythm_id,
                "authority": DESCRIPTOR.label_authority,
                "annotationIndex": spec.annotation_index,
            }
        },
        "source_provenance": {
            "sourceId": SOURCE_ID,
            "datasetTitle": DESCRIPTOR.dataset_title,
            "sourceVersion": DESCRIPTOR.version,
            "licenseId": DESCRIPTOR.license_id,
            "licenseName": DESCRIPTOR.license_name,
            "sourceUrl": DESCRIPTOR.source_url,
            "doi": DESCRIPTOR.doi,
            "publishedUncompressedSize": DESCRIPTOR.published_uncompressed_size,
            "labelAuthority": DESCRIPTOR.label_authority,
            "recordName": spec.record_name,
            "patientId": spec.patient_id,
            "annotationFile": f"{spec.record_name}.atr",
            "annotationIndex": spec.annotation_index,
            "windowStartSample": spec.start_sample,
            "windowEndSample": spec.end_sample,
            "episodeStartSample": spec.episode_start_sample,
            "episodeEndSample": spec.episode_end_sample,
            "sourceSamplingFrequency": SOURCE_FS,
            "extractionVersion": EXTRACTION_VERSION,
            "checksumManifest": {
                "file": "SHA256SUMS.txt",
                "sha256": CHECKSUM_MANIFEST_SHA256,
            },
            "sourceArtifacts": {
                filename: {"file": filename, "sha256": checksum}
                for filename, checksum in checksums.items()
            },
        },
        "educational_eligibility": {
            "educationalUse": "rhythm_stream",
            "eligibleModes": list(contract.eligible_modes),
            "eligibleSubskills": {
                spec.canonical_rhythm_id: list(contract.eligible_subskills),
            },
            "sourceLabelOnly": True,
            "scenarioWaveformEligibleAfterReview": True,
            "currentRuntimeModeConnected": False,
            "clinicalCaseEligible": False,
            "clinicalManagementEligible": False,
            "pulseOrPerfusionClaimsEligible": False,
            "cardiacArrestClaimEligible": False,
            "shockableStatusClaimEligible": False,
            "treatmentOrActionSequenceEligible": False,
            "reason": (
                "The source supports rhythm recognition/discrimination only. It contains no pulse, "
                "perfusion, arrest-state, intervention, response, or reviewed action algorithm."
            ),
        },
        "rhythm_label_evidence": {
            spec.canonical_rhythm_id: {
                "status": "source_reference_annotation",
                "evidence": [
                    "expert_reference_rhythm_change_annotation",
                    "guarded_window_fully_inside_annotated_episode",
                    "checksum_verified_source_artifacts",
                ],
                "warnings": [
                    "Rhythm label does not establish pulse, perfusion, arrest, etiology, or treatment."
                ],
            }
        },
        "supported_objectives": [spec.canonical_rhythm_id],
        "signal_quality": {
            "status": "source_window_eligible",
            "reasons": [
                "Window is outside source NOISE episodes and remains inside one expert rhythm interval."
            ],
            "independentSignalQualityLabelAvailable": False,
        },
        "signal_fingerprint": fingerprint,
        "llm_allowed_claims": [
            (
                f"After learner submission, may identify the expert source rhythm as "
                f"{contract.description}."
            ),
            "May explain that this is a two-channel ambulatory rhythm stream, not a 12-lead ECG.",
            "May cite the exact source record/window and checksum provenance.",
        ],
        "llm_forbidden_claims": [
            "Do not claim or infer a pulse, perfusion state, hemodynamic stability, or cardiac arrest.",
            "Do not classify shockability or recommend shock, medication, energy, timing, or any action.",
            "Do not present this source-only packet as a clinical case or ACLS performance assessment.",
            "Do not infer 12-lead axis, territory, intervals, QTc, ischemia, or structural findings.",
            "Do not equate a sinus-rhythm source label with a normal ECG.",
        ],
    }
