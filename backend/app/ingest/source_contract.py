"""Admission contract for adding ECG datasets to the unified corpus.

Adapters run offline. Runtime practice sees only normalized, provenance-complete
packets in the corpus store, so Google Drive, WFDB, and source-specific label
formats never leak into learner-serving code.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, Sequence


EducationalUse = Literal[
    "static_12_lead",
    "rhythm_stream",
    "acute_serial",
    "clinical_context",
]


@dataclass(frozen=True)
class SourceDescriptor:
    source_id: str
    version: str
    license_id: str
    access: Literal["open", "credentialed", "local_research_only"]
    label_authority: str
    patient_ids_available: bool
    educational_uses: tuple[EducationalUse, ...]
    dataset_title: str = ""
    license_name: str = ""
    source_url: str = ""
    doi: str = ""
    corpus_role: str = "waveform_and_labels"
    published_uncompressed_size: str = ""


@dataclass(frozen=True)
class SourceRecord:
    source_record_id: str
    patient_id: str | None
    signal_by_lead: dict[str, Sequence[float]]
    sampling_frequency: int
    labels: tuple[str, ...]
    label_provenance: str


class SourceAdapter(Protocol):
    descriptor: SourceDescriptor

    def records(self) -> Sequence[SourceRecord]: ...


def namespaced_case_id(source_id: str, source_record_id: str) -> str:
    if not source_id or ":" in source_id or not source_record_id:
        raise ValueError("source and record identifiers must be non-empty; source may not contain ':'")
    return f"{source_id}:{source_record_id}"


def validate_source_record(descriptor: SourceDescriptor, record: SourceRecord) -> None:
    if descriptor.patient_ids_available and not record.patient_id:
        raise ValueError("patient identity is required by this source contract")
    if not record.labels or not record.label_provenance:
        raise ValueError("admitted records require labels and explicit label provenance")
    if record.sampling_frequency <= 0:
        raise ValueError("sampling frequency must be positive")
    if not record.signal_by_lead:
        raise ValueError("a record must contain waveform leads")


def source_catalog_entry(source_id: str) -> dict[str, object]:
    """Return the public, version-specific provenance for one admitted source.

    License identifiers are part of the executable source contract rather than
    presentation-only metadata. Corpus builders use this function for both case
    packets and manifests so a source cannot silently acquire a different
    license in one layer.
    """

    descriptor = KNOWN_SOURCES[source_id]
    entry: dict[str, object] = {
        "sourceId": descriptor.source_id,
        "sourceVersion": descriptor.version,
        "licenseId": descriptor.license_id,
        "labelAuthority": descriptor.label_authority,
        "educationalUses": list(descriptor.educational_uses),
        "corpusRole": descriptor.corpus_role,
    }
    optional = {
        "datasetTitle": descriptor.dataset_title,
        "licenseName": descriptor.license_name,
        "sourceUrl": descriptor.source_url,
        "doi": descriptor.doi,
        "publishedUncompressedSize": descriptor.published_uncompressed_size,
    }
    entry.update({key: value for key, value in optional.items() if value})
    return entry


# Admission candidates found in the local ResearchGrind #6-ECG-VCG collection.
# A descriptor is not permission to publish: each adapter must still enforce the
# source's license/access rules and the allowed-use lane below.
KNOWN_SOURCES: dict[str, SourceDescriptor] = {
    "ptbxl": SourceDescriptor(
        source_id="ptbxl", version="1.0.3", license_id="CC-BY-4.0", access="open",
        label_authority="cardiologist-reviewed SCP-ECG statements",
        patient_ids_available=True, educational_uses=("static_12_lead",),
        dataset_title="PTB-XL, a large publicly available electrocardiography dataset",
        license_name="Creative Commons Attribution 4.0 International",
        source_url="https://physionet.org/content/ptb-xl/1.0.3/",
        doi="https://doi.org/10.13026/kfzx-aw45",
        corpus_role="waveform_and_cardiologist_labels",
    ),
    "ptbxl-plus": SourceDescriptor(
        source_id="ptbxl-plus", version="1.0.1", license_id="CC-BY-4.0", access="open",
        label_authority=(
            "algorithm-derived ECG features, fiducials, median beats, and diagnostic statements"
        ),
        patient_ids_available=False, educational_uses=("static_12_lead",),
        dataset_title="PTB-XL+, a comprehensive electrocardiographic feature dataset",
        license_name="Creative Commons Attribution 4.0 International",
        source_url="https://physionet.org/content/ptb-xl-plus/1.0.1/",
        doi="https://doi.org/10.13026/g6h6-7g88",
        corpus_role="derived_evidence",
    ),
    "mimic-iv-ecg": SourceDescriptor(
        source_id="mimic-iv-ecg", version="1.0", license_id="ODbL-1.0",
        access="open", label_authority="linked cardiologist reports when available",
        patient_ids_available=True, educational_uses=("static_12_lead",),
    ),
    "mimic-iv-ecg-ext": SourceDescriptor(
        source_id="mimic-iv-ecg-ext", version="1.0.1",
        license_id="PhysioNet-Credentialed-Health-Data-License-1.5.0",
        access="local_research_only",
        label_authority="encounter-linked ICD-10 labels; not ECG morphology ground truth",
        patient_ids_available=True,
        educational_uses=(),
    ),
    "leipzig-heart-center": SourceDescriptor(
        source_id="leipzig-heart-center", version="1.0.0", license_id="ODC-BY-1.0",
        access="open", label_authority="expert beat and rhythm annotations",
        patient_ids_available=True, educational_uses=("rhythm_stream",),
        dataset_title=(
            "Leipzig Heart Center ECG-Database: Arrhythmias in Children and Patients "
            "with Congenital Heart Disease"
        ),
        license_name="Open Data Commons Attribution License (ODC-By) 1.0",
        source_url="https://physionet.org/content/leipzig-heart-center-ecg/1.0.0/",
        doi="https://doi.org/10.13026/7a4j-vn37",
        corpus_role="expert_rhythm_waveform_and_labels",
    ),
    "staff-iii": SourceDescriptor(
        source_id="staff-iii", version="1.0.0", license_id="ODC-BY-1.0",
        access="open", label_authority="protocol-timed PTCA ischemia recordings",
        patient_ids_available=True, educational_uses=("acute_serial",),
        dataset_title="STAFF III Database: ECGs Recorded During Acutely Induced Myocardial Ischemia",
        license_name="Open Data Commons Attribution License (ODC-By) 1.0",
        source_url="https://physionet.org/content/staffiii/1.0.0/",
        doi="https://doi.org/10.13026/C20P4H",
        corpus_role="protocol_timed_twelve_lead_comparison_source",
        published_uncompressed_size="3.2 GB",
    ),
    "ecg-fragment-dangerous-arrhythmia": SourceDescriptor(
        source_id="ecg-fragment-dangerous-arrhythmia",
        version="1.0.0",
        license_id="ODC-BY-1.0",
        access="open",
        label_authority=(
            "author-reviewed short-fragment rhythm labels derived from the MIT-BIH "
            "Malignant Ventricular Ectopy Database"
        ),
        # Source record numbers are not asserted to be patient identities and
        # are deliberately replaced with content-addressed ids at import.
        patient_ids_available=False,
        educational_uses=("rhythm_stream",),
        dataset_title="ECG Fragment Database for the Exploration of Dangerous Arrhythmia",
        license_name="Open Data Commons Attribution License (ODC-By) 1.0",
        source_url=(
            "https://physionet.org/content/ecg-fragment-high-risk-label/1.0.0/"
        ),
        doi="https://doi.org/10.13026/kpfg-xs25",
        corpus_role="reviewed_single_lead_rhythm_fragment_waveform_and_labels",
        published_uncompressed_size="5.6 MB",
    ),
    "mit-bih-vfdb": SourceDescriptor(
        source_id="mit-bih-vfdb",
        version="1.0.0",
        license_id="ODC-BY-1.0",
        access="open",
        label_authority=(
            "expert reference WFDB rhythm-change annotations; rhythm labels only, no beat labels"
        ),
        patient_ids_available=True,
        educational_uses=("rhythm_stream",),
        dataset_title="MIT-BIH Malignant Ventricular Ectopy Database",
        license_name="Open Data Commons Attribution License (ODC-By) 1.0",
        source_url="https://physionet.org/content/vfdb/1.0.0/",
        doi="https://doi.org/10.13026/C22P44",
        corpus_role="expert_two_channel_rhythm_stream_waveform_and_labels",
        published_uncompressed_size="33.1 MB",
    ),
}
