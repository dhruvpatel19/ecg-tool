"""Offline adapter for the Leipzig Heart Center expert rhythm database.

The source is a long-form electrophysiology recording, not an authored clinical
case.  This adapter therefore admits only stable, expert-labelled 10-second
rhythm windows for Training and Rapid practice.  It deliberately does not
manufacture symptoms, hemodynamics, management decisions, a "normal ECG"
claim, or any other context that is absent from the source.

Runtime code never reads WFDB files.  The CLI in ``scripts/import_leipzig.py``
uses these helpers offline and writes normalized packets plus 100 Hz surface
12-lead waveforms into the ordinary corpus stores.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import csv
import math
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from ..ontology import CONCEPTS, concept_label
from ..store import waveform_fingerprint
from .source_contract import (
    KNOWN_SOURCES,
    SourceRecord,
    namespaced_case_id,
    validate_source_record,
)


SOURCE_ID = "leipzig-heart-center"
DESCRIPTOR = KNOWN_SOURCES[SOURCE_ID]
EXTRACTION_VERSION = "leipzig-rhythm-window-v1"
TARGET_FS = 100
WINDOW_SECONDS = 10.0
DEFAULT_BOUNDARY_GUARD_SECONDS = 0.5
DEFAULT_STRIDE_SECONDS = 10.0
SURFACE_LEADS = ("I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6")

# Only mappings explicitly justified by the source annotation dictionary and
# the platform's rhythm objectives are admitted.  Other expert rhythm markers
# remain visible in dry-run inventory but are not silently generalized.
RHYTHM_TO_CONCEPT: dict[str, str] = {
    "N": "sinus_rhythm",
    "AVNRT": "supraventricular_tachycardia",
    "AVRT": "supraventricular_tachycardia",
    "VT": "wide_complex_tachycardia",
    "AFIB": "atrial_fibrillation",
    "/A": "paced_rhythm",
    "/V": "paced_rhythm",
}

RHYTHM_NAMES = {
    "N": "Sinus rhythm",
    "AVNRT": "Atrioventricular nodal reentrant tachycardia",
    "AVRT": "Atrioventricular reentrant tachycardia",
    "VT": "Ventricular tachycardia",
    "AFIB": "Atrial fibrillation",
    "/A": "Atrial paced rhythm",
    "/V": "Ventricular paced rhythm",
}

# Symbols observed in this source's expert annotation files that mark beats.
# Rhythm-change (+) and signal-quality (~) markers are intentionally excluded.
LEIPZIG_BEAT_SYMBOLS = frozenset({"/", "A", "F", "J", "L", "N", "Q", "R", "V", "X", "a", "b", "f", "j"})


@dataclass(frozen=True)
class RhythmEpisode:
    raw_aux: str
    rhythm_code: str
    concept_id: str
    start_sample: int
    end_sample: int


@dataclass(frozen=True)
class WindowSpec:
    record_name: str
    patient_id: str
    sampling_frequency: int
    start_sample: int
    end_sample: int
    episode_start_sample: int
    episode_end_sample: int
    raw_rhythm_aux: str
    rhythm_code: str
    concept_id: str
    beat_samples: tuple[int, ...]

    @property
    def source_record_id(self) -> str:
        return f"{self.record_name}@{self.start_sample:012d}-{self.end_sample:012d}"

    @property
    def case_id(self) -> str:
        return namespaced_case_id(SOURCE_ID, self.source_record_id)


@dataclass(frozen=True)
class SourceInventory:
    source_root: Path
    records_scanned: int
    windows: tuple[WindowSpec, ...]
    unsupported_rhythm_markers: dict[str, int]
    missing_waveform_records: tuple[str, ...]
    errors: tuple[str, ...]

    @property
    def concept_counts(self) -> dict[str, int]:
        return dict(sorted(Counter(item.concept_id for item in self.windows).items()))

    @property
    def patient_counts(self) -> dict[str, int]:
        return dict(sorted(Counter(item.patient_id for item in self.windows).items()))

    def as_dict(self) -> dict[str, Any]:
        missing = set(self.missing_waveform_records)
        readable = [item for item in self.windows if item.record_name not in missing]
        return {
            "sourceId": SOURCE_ID,
            "sourceVersion": DESCRIPTOR.version,
            "licenseId": DESCRIPTOR.license_id,
            "labelAuthority": DESCRIPTOR.label_authority,
            "educationalUses": list(DESCRIPTOR.educational_uses),
            "recordsScanned": self.records_scanned,
            "waveformDataRecordsAvailable": self.records_scanned - len(missing),
            "waveformDataRecordsMissing": list(self.missing_waveform_records),
            "uniquePatients": len(self.patient_counts),
            "stableWindowCount": len(self.windows),
            "locallyReadableWindowCount": len(readable),
            "locallyReadableConceptCounts": dict(
                sorted(Counter(item.concept_id for item in readable).items())
            ),
            "conceptCounts": self.concept_counts,
            "unsupportedRhythmMarkers": dict(sorted(self.unsupported_rhythm_markers.items())),
            "errors": list(self.errors),
        }


def normalize_rhythm_aux(aux_note: str | None) -> str:
    """Normalize a WFDB rhythm aux string while retaining its source meaning."""

    value = str(aux_note or "").replace("\x00", "").strip()
    return value[1:] if value.startswith("(") else value


def map_rhythm_aux(aux_note: str | None) -> str | None:
    """Map a supported expert rhythm marker to a corpus concept id."""

    return RHYTHM_TO_CONCEPT.get(normalize_rhythm_aux(aux_note))


def segment_rhythm_episodes(
    samples: Sequence[int],
    symbols: Sequence[str],
    aux_notes: Sequence[str],
    record_end_sample: int,
) -> list[RhythmEpisode]:
    """Return supported expert-labelled intervals bounded by *all* rhythm markers.

    An unsupported marker still terminates the preceding interval.  This is
    crucial: an AVNRT window must never spill into a subsequent AFL/EAT episode
    simply because that next label is not currently eligible in the ontology.
    """

    if not (len(samples) == len(symbols) == len(aux_notes)):
        raise ValueError("annotation samples, symbols, and aux notes must have equal lengths")
    if record_end_sample <= 0:
        raise ValueError("record end sample must be positive")

    markers = [
        (int(sample), str(aux))
        for sample, symbol, aux in zip(samples, symbols, aux_notes)
        if str(symbol) == "+" and normalize_rhythm_aux(aux)
    ]
    markers.sort(key=lambda item: item[0])
    episodes: list[RhythmEpisode] = []
    for index, (start, raw_aux) in enumerate(markers):
        end = markers[index + 1][0] if index + 1 < len(markers) else int(record_end_sample)
        if start < 0 or end <= start or start >= record_end_sample:
            continue
        code = normalize_rhythm_aux(raw_aux)
        concept = RHYTHM_TO_CONCEPT.get(code)
        if concept:
            episodes.append(
                RhythmEpisode(
                    raw_aux=raw_aux,
                    rhythm_code=code,
                    concept_id=concept,
                    start_sample=start,
                    end_sample=min(end, int(record_end_sample)),
                )
            )
    return episodes


def signal_quality_intervals(
    samples: Sequence[int], symbols: Sequence[str], record_end_sample: int
) -> list[tuple[int, int]]:
    """Pair Leipzig ``~`` markers into conservative unusable-signal intervals."""

    if len(samples) != len(symbols):
        raise ValueError("annotation samples and symbols must have equal lengths")
    markers = sorted(int(sample) for sample, symbol in zip(samples, symbols) if str(symbol) == "~")
    intervals: list[tuple[int, int]] = []
    for index in range(0, len(markers), 2):
        start = markers[index]
        end = markers[index + 1] if index + 1 < len(markers) else int(record_end_sample)
        if end > start:
            intervals.append((max(0, start), min(int(record_end_sample), end)))
    return intervals


def beat_samples_from_annotations(samples: Sequence[int], symbols: Sequence[str]) -> list[int]:
    if len(samples) != len(symbols):
        raise ValueError("annotation samples and symbols must have equal lengths")
    return sorted(
        {int(sample) for sample, symbol in zip(samples, symbols) if str(symbol) in LEIPZIG_BEAT_SYMBOLS}
    )


def _overlaps(start: int, end: int, intervals: Sequence[tuple[int, int]]) -> bool:
    return any(start < other_end and end > other_start for other_start, other_end in intervals)


def stable_windows(
    episode: RhythmEpisode,
    sampling_frequency: int,
    beat_samples: Sequence[int],
    excluded_intervals: Sequence[tuple[int, int]] = (),
    *,
    duration_seconds: float = WINDOW_SECONDS,
    stride_seconds: float = DEFAULT_STRIDE_SECONDS,
    boundary_guard_seconds: float = DEFAULT_BOUNDARY_GUARD_SECONDS,
    minimum_beats: int = 2,
) -> list[tuple[int, int, tuple[int, ...]]]:
    """Create deterministic, non-overlapping stable windows inside one episode."""

    if sampling_frequency <= 0 or duration_seconds <= 0:
        raise ValueError("sampling frequency and duration must be positive")
    if stride_seconds < duration_seconds:
        raise ValueError("stride must be at least the window duration; overlapping ECGs are not admitted")
    if boundary_guard_seconds < 0:
        raise ValueError("boundary guard may not be negative")

    length = int(round(duration_seconds * sampling_frequency))
    stride = int(round(stride_seconds * sampling_frequency))
    guard = int(round(boundary_guard_seconds * sampling_frequency))
    cursor = episode.start_sample + guard
    usable_end = episode.end_sample - guard
    beats = sorted(int(value) for value in beat_samples)
    windows: list[tuple[int, int, tuple[int, ...]]] = []
    while cursor + length <= usable_end:
        end = cursor + length
        within = tuple(value for value in beats if cursor <= value < end)
        if len(within) >= minimum_beats and not _overlaps(cursor, end, excluded_intervals):
            windows.append((cursor, end, within))
        cursor += stride
    return windows


def _read_subjects(root: Path) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    for name in ("children-subject-info.csv", "adults-subject-info.csv"):
        path = root / name
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                record_name = str(row.get("file_name") or "").strip()
                if record_name:
                    rows[record_name] = {str(key): str(value or "").strip() for key, value in row.items()}
    return rows


def inventory_source(
    source_root: str | Path,
    *,
    record_names: Sequence[str] | None = None,
    duration_seconds: float = WINDOW_SECONDS,
    stride_seconds: float = DEFAULT_STRIDE_SECONDS,
    boundary_guard_seconds: float = DEFAULT_BOUNDARY_GUARD_SECONDS,
) -> SourceInventory:
    """Read headers/annotations only and inventory eligible windows (no waveform I/O)."""

    import wfdb  # Offline-only optional dependency.

    root = Path(source_root)
    records_file = root / "RECORDS"
    if not records_file.exists():
        raise FileNotFoundError(f"Leipzig RECORDS file not found at {records_file}")
    available = [line.strip() for line in records_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    wanted = set(record_names or available)
    unknown = sorted(wanted - set(available))
    if unknown:
        raise ValueError(f"unknown Leipzig record(s): {', '.join(unknown)}")
    selected = [name for name in available if name in wanted]
    subjects = _read_subjects(root)

    specs: list[WindowSpec] = []
    unsupported: Counter[str] = Counter()
    missing_waveforms: list[str] = []
    errors: list[str] = []
    for record_name in selected:
        try:
            header = wfdb.rdheader(str(root / record_name))
            fs_value = float(header.fs)
            fs = int(round(fs_value))
            if not math.isclose(fs_value, fs, rel_tol=0, abs_tol=1e-6):
                raise ValueError(f"non-integral sampling frequency {fs_value}")
            missing_leads = [lead for lead in SURFACE_LEADS if lead not in list(header.sig_name)]
            if missing_leads:
                raise ValueError(f"missing surface leads: {', '.join(missing_leads)}")
            source_files = {str(value) for value in getattr(header, "file_name", []) if str(value)}
            if not source_files or any(not (root / name).exists() for name in source_files):
                missing_waveforms.append(record_name)
            ann = wfdb.rdann(str(root / record_name), "atr")
            samples = [int(value) for value in ann.sample]
            symbols = [str(value) for value in ann.symbol]
            aux_notes = [str(value) for value in (ann.aux_note or [""] * len(samples))]
            for symbol, aux in zip(symbols, aux_notes):
                if symbol == "+":
                    code = normalize_rhythm_aux(aux)
                    if code and code not in RHYTHM_TO_CONCEPT:
                        unsupported[code] += 1
            episodes = segment_rhythm_episodes(samples, symbols, aux_notes, int(header.sig_len))
            excluded = signal_quality_intervals(samples, symbols, int(header.sig_len))
            beats = beat_samples_from_annotations(samples, symbols)
            patient_id = str((subjects.get(record_name) or {}).get("subject_id") or record_name.removeprefix("x"))
            for episode in episodes:
                for start, end, within_beats in stable_windows(
                    episode,
                    fs,
                    beats,
                    excluded,
                    duration_seconds=duration_seconds,
                    stride_seconds=stride_seconds,
                    boundary_guard_seconds=boundary_guard_seconds,
                ):
                    specs.append(
                        WindowSpec(
                            record_name=record_name,
                            patient_id=patient_id,
                            sampling_frequency=fs,
                            start_sample=start,
                            end_sample=end,
                            episode_start_sample=episode.start_sample,
                            episode_end_sample=episode.end_sample,
                            raw_rhythm_aux=episode.raw_aux,
                            rhythm_code=episode.rhythm_code,
                            concept_id=episode.concept_id,
                            beat_samples=within_beats,
                        )
                    )
        except Exception as exc:  # inventory every independent record and report all failures
            errors.append(f"{record_name}: {exc}")
    return SourceInventory(
        source_root=root,
        records_scanned=len(selected),
        windows=tuple(specs),
        unsupported_rhythm_markers=dict(unsupported),
        missing_waveform_records=tuple(sorted(missing_waveforms)),
        errors=tuple(errors),
    )


def downsample_surface_signals(
    signal_by_lead: Mapping[str, Sequence[float]], input_fs: int, target_fs: int = TARGET_FS
) -> dict[str, list[float]]:
    """Polyphase-resample all 12 surface leads and return equal-length mV arrays."""

    from scipy.signal import resample_poly

    if input_fs <= 0 or target_fs <= 0:
        raise ValueError("sampling frequencies must be positive")
    missing = [lead for lead in SURFACE_LEADS if lead not in signal_by_lead]
    if missing:
        raise ValueError(f"missing surface leads: {', '.join(missing)}")
    lengths = {len(signal_by_lead[lead]) for lead in SURFACE_LEADS}
    if len(lengths) != 1 or not lengths or next(iter(lengths)) == 0:
        raise ValueError("surface leads must have one shared, non-zero length")
    source_length = next(iter(lengths))
    expected = int(round(source_length * target_fs / input_fs))
    divisor = math.gcd(int(input_fs), int(target_fs))
    up, down = target_fs // divisor, input_fs // divisor
    result: dict[str, list[float]] = {}
    for lead in SURFACE_LEADS:
        values = np.asarray(signal_by_lead[lead], dtype=np.float64)
        sampled = np.asarray(resample_poly(values, up, down), dtype=np.float64)[:expected]
        if len(sampled) != expected or not np.isfinite(sampled).all():
            raise ValueError(f"invalid downsampled signal for lead {lead}")
        result[lead] = np.round(sampled, 4).tolist()
    return result


def read_surface_window(source_root: str | Path, spec: WindowSpec) -> dict[str, list[float]]:
    """Read one source window in physical mV and normalize it to 12 leads / 100 Hz."""

    import wfdb  # Offline-only optional dependency.

    root = Path(source_root)
    header = wfdb.rdheader(str(root / spec.record_name))
    lead_indices = [list(header.sig_name).index(lead) for lead in SURFACE_LEADS]
    record = wfdb.rdrecord(
        str(root / spec.record_name),
        sampfrom=spec.start_sample,
        sampto=spec.end_sample,
        channels=lead_indices,
        physical=True,
    )
    if record.p_signal is None:
        raise ValueError(f"physical signal unavailable for {spec.record_name}")
    raw = {
        lead: np.asarray(record.p_signal[:, index], dtype=np.float64).tolist()
        for index, lead in enumerate(SURFACE_LEADS)
    }
    signal = downsample_surface_signals(raw, spec.sampling_frequency, TARGET_FS)
    expected = int(round(WINDOW_SECONDS * TARGET_FS))
    if any(len(values) != expected for values in signal.values()):
        raise ValueError(f"{spec.source_record_id} did not normalize to a 10-second signal")
    return signal


def derive_heart_rate(beat_samples: Sequence[int], sampling_frequency: int) -> float | None:
    unique = sorted({int(value) for value in beat_samples})
    if sampling_frequency <= 0 or len(unique) < 2:
        return None
    rr_seconds = [
        (right - left) / sampling_frequency
        for left, right in zip(unique, unique[1:])
        if right > left
    ]
    if not rr_seconds:
        return None
    return round(60.0 / median(rr_seconds), 1)


def _bounded_beats(beat_samples: Sequence[int], maximum: int = 24) -> list[int]:
    values = sorted({int(value) for value in beat_samples})
    if len(values) <= maximum:
        return values
    indices = np.linspace(0, len(values) - 1, maximum, dtype=int)
    return [values[int(index)] for index in indices]


def derive_qrs_rois(
    signal_by_lead: Mapping[str, Sequence[float]],
    beat_samples: Sequence[int],
    window_start_sample: int,
    source_fs: int,
) -> list[dict[str, Any]]:
    """Project expert beat times into neutral QRS-location ROIs on all 12 leads."""

    rois: list[dict[str, Any]] = []
    for sample in _bounded_beats(beat_samples):
        center = (sample - window_start_sample) / source_fs
        start = max(0.0, center - 0.06)
        end = min(WINDOW_SECONDS, center + 0.06)
        if end <= start:
            continue
        for lead in SURFACE_LEADS:
            values = signal_by_lead.get(lead) or []
            lo = max(0, int(math.floor(start * TARGET_FS)))
            hi = min(len(values), max(lo + 1, int(math.ceil(end * TARGET_FS))))
            segment = values[lo:hi]
            amp_min = round((min(segment) if segment else -1.5) - 0.15, 3)
            amp_max = round((max(segment) if segment else 1.5) + 0.15, 3)
            rois.append(
                {
                    "lead": lead,
                    "timeStartSec": round(start, 3),
                    "timeEndSec": round(end, 3),
                    "ampMinMv": amp_min,
                    "ampMaxMv": amp_max,
                    "label": "QRS complex",
                    "concept": "qrs_complex",
                    "source": "leipzig_expert_beat_timing",
                    "confidence": "medium",
                }
            )
    return rois


def _concept_confidence(spec: WindowSpec, heart_rate: float | None) -> dict[str, dict[str, Any]]:
    unavailable_warning = "Not eligible under the Leipzig rhythm-stream source label contract."
    rows = {
        concept.id: {"score": 0.0, "tier": "D", "evidence": [], "warnings": [unavailable_warning]}
        for concept in CONCEPTS
    }
    rows[spec.concept_id] = {
        "score": 0.88,
        "tier": "B",
        "evidence": [
            "expert_wfdb_rhythm_annotation",
            "stable_10_second_window_within_annotation",
            "surface_12_lead_waveform",
        ],
        "warnings": ["Rhythm evidence does not establish symptoms, hemodynamics, etiology, or management."],
    }
    if heart_rate is not None:
        rows["rate"] = {
            "score": 0.82,
            "tier": "B",
            "evidence": ["heart_rate_from_expert_beat_annotations"],
            "warnings": ["Rate is derived from annotated RR intervals in this 10-second window."],
        }
    # The source's N marker means sinus rhythm only.  It can never be promoted to
    # the much broader "normal ECG" objective.
    if spec.concept_id == "sinus_rhythm":
        rows["normal_ecg"] = {
            "score": 0.0,
            "tier": "D",
            "evidence": [],
            "warnings": ["Expert N rhythm annotation supports sinus rhythm, not a normal 12-lead ECG claim."],
        }
    return rows


def build_window_packet(
    spec: WindowSpec,
    signal_by_lead: Mapping[str, Sequence[float]],
    *,
    source_subject_metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a provenance-complete, source-restricted packet for one window."""

    source_record = SourceRecord(
        source_record_id=spec.source_record_id,
        patient_id=spec.patient_id,
        signal_by_lead={lead: signal_by_lead[lead] for lead in SURFACE_LEADS},
        sampling_frequency=TARGET_FS,
        labels=(spec.concept_id,),
        label_provenance="expert WFDB rhythm annotation; window fully contained within annotated episode",
    )
    validate_source_record(DESCRIPTOR, source_record)
    if any(len(source_record.signal_by_lead[lead]) != int(WINDOW_SECONDS * TARGET_FS) for lead in SURFACE_LEADS):
        raise ValueError("Leipzig packets require exactly 10 seconds at 100 Hz on all 12 surface leads")

    heart_rate = derive_heart_rate(spec.beat_samples, spec.sampling_frequency)
    confidence = _concept_confidence(spec, heart_rate)
    supported = [spec.concept_id] + (["rate"] if heart_rate is not None and spec.concept_id != "rate" else [])
    unsupported = [concept.id for concept in CONCEPTS if concept.id not in supported]
    rois = derive_qrs_rois(signal_by_lead, spec.beat_samples, spec.start_sample, spec.sampling_frequency)
    rhythm_name = RHYTHM_NAMES[spec.rhythm_code]
    start_sec = spec.start_sample / spec.sampling_frequency
    subject_metadata = {
        str(key): value
        for key, value in (source_subject_metadata or {}).items()
        if key in {"subject_id", "file_name", "gender", "age", "diagnosis", "ap_loacation", "ecg_duration"}
    }

    packet: dict[str, Any] = {
        "case_id": spec.case_id,
        "display_id": f"Leipzig {spec.record_name} · {start_sec:.1f}s",
        "clinical_stem": (
            "Expert-annotated 10-second rhythm window. Symptoms, hemodynamics, treatment, "
            "and encounter context are not available from this source."
        ),
        "source": SOURCE_ID,
        "waveform": {
            "path": None,
            "sampling_frequency": TARGET_FS,
            "duration_sec": WINDOW_SECONDS,
            "leads": list(SURFACE_LEADS),
            "source": "corpus_store",
        },
        # Compatibility envelope for existing readers.  Authoritative non-PTB
        # labels and provenance live in source_labels/source_provenance below.
        "ptbxl": {
            "scp_codes": {},
            "diagnostic_superclass": [],
            "diagnostic_subclass": [],
            "report": f"Expert rhythm annotation: {rhythm_name}",
            "fold": 0,
            "metadata": {},
            "compatibility_only": True,
        },
        "ptbxl_plus": {
            "statements": [],
            "statements_detailed": [],
            "statement_source": None,
            "features": {"heart_rate": heart_rate} if heart_rate is not None else {},
            "measurements": {"heart_rate": heart_rate} if heart_rate is not None else {},
            "fiducials": {
                "rois": rois,
                "fiducials_by_lead": {
                    "global": {
                        "qrs_peak_times_sec": [
                            round((sample - spec.start_sample) / spec.sampling_frequency, 3)
                            for sample in _bounded_beats(spec.beat_samples)
                        ],
                        "source": "leipzig_expert_beat_timing",
                    }
                },
            },
            "median_beats": {"available": False},
            "feature_sources": {"heart_rate": "expert_beat_annotation_rr_median"} if heart_rate is not None else {},
            "per_lead_st_mv": {},
        },
        "signal_quality": {
            "status": "acceptable",
            "reasons": ["Window does not overlap paired expert WFDB signal-quality exclusion markers."],
            "source": "leipzig_expert_annotation_filter",
        },
        "source_labels": {
            "rhythm": {
                "rawAux": spec.raw_rhythm_aux,
                "rhythmCode": spec.rhythm_code,
                "sourceDescription": rhythm_name,
                "canonicalConceptId": spec.concept_id,
                "authority": DESCRIPTOR.label_authority,
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
            "labelAuthority": DESCRIPTOR.label_authority,
            "recordName": spec.record_name,
            "annotationFile": f"{spec.record_name}.atr",
            "patientId": spec.patient_id,
            "windowStartSample": spec.start_sample,
            "windowEndSample": spec.end_sample,
            "episodeStartSample": spec.episode_start_sample,
            "episodeEndSample": spec.episode_end_sample,
            "sourceSamplingFrequency": spec.sampling_frequency,
            "extractionVersion": EXTRACTION_VERSION,
            "subjectMetadata": subject_metadata,
        },
        "record_identity": {
            "sourceId": SOURCE_ID,
            "sourceRecordId": spec.source_record_id,
            "patientId": spec.patient_id,
            "sourceVersion": DESCRIPTOR.version,
            "licenseId": DESCRIPTOR.license_id,
        },
        "educational_eligibility": {
            "educationalUse": "rhythm_stream",
            "eligibleModes": ["training", "rapid"],
            "eligibleSubskills": {
                spec.concept_id: ["recognize", "discriminate"],
                "rate": ["measure"],
                "qrs_complex": ["localize"],
            },
            "clinicalCaseEligible": False,
            "clinicalManagementEligible": False,
            "reason": "The source provides waveform rhythm/beat labels but no encounter or management ground truth.",
        },
        "concept_confidence": confidence,
        "supported_objectives": supported,
        "unsupported_objectives": unsupported,
        "teaching_tier": "B",
        "global_tier": "B",
        "inclusion_reasons": [
            "Entire 10-second waveform lies inside an expert rhythm annotation.",
            "Expert signal-quality exclusion intervals were filtered before admission.",
        ],
        "exclusion_reasons": [],
        "llm_allowed_claims": [
            f"May identify {concept_label(spec.concept_id)} from the expert rhythm label after learner submission.",
            "May cite heart rate only when the annotation-derived value is present.",
            "May use QRS ROIs only as neutral beat locations.",
        ],
        "llm_forbidden_claims": [
            "Do not infer symptoms, hemodynamics, diagnosis beyond the rhythm label, treatment, or management.",
            "Do not use this rhythm-stream packet as a Clinical Decisions management case.",
            "Do not infer QRS duration, axis, ischemia, QTc, or structural disease from unavailable measurements.",
            "Do not equate sinus rhythm with a normal ECG.",
        ],
        "teaching_points": [
            f"Expert WFDB rhythm annotation: {rhythm_name}.",
            *([f"Annotation-derived median RR heart rate: {heart_rate:g} bpm."] if heart_rate is not None else []),
        ],
    }
    packet["signal_fingerprint"] = waveform_fingerprint(source_record.signal_by_lead)
    return packet


def load_subject_metadata(source_root: str | Path) -> dict[str, dict[str, str]]:
    """Public wrapper used by the importer to preserve source-provided metadata."""

    return _read_subjects(Path(source_root))


def select_windows(
    windows: Iterable[WindowSpec],
    *,
    concept_ids: set[str] | None = None,
    limit: int = 0,
    max_per_concept: int = 0,
) -> list[WindowSpec]:
    """Deterministically filter inventory without turning exclusions into labels."""

    selected: list[WindowSpec] = []
    counts: Counter[str] = Counter()
    for item in windows:
        if concept_ids and item.concept_id not in concept_ids:
            continue
        if max_per_concept and counts[item.concept_id] >= max_per_concept:
            continue
        selected.append(item)
        counts[item.concept_id] += 1
        if limit and len(selected) >= limit:
            break
    return selected
