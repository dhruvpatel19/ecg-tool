"""Corpus-backed case repository (SQLite case store + compact waveform store).

Presents the same surface the API/adaptive layer needs, but serves the full
PTB-XL corpus from disk-backed stores instead of an in-memory dict, with no
serve-time WFDB/Drive dependency. Learner-facing configuration fails closed
without that corpus; the fixture repository is an explicit test-only opt-out.
"""

from __future__ import annotations

from functools import lru_cache
import json
import hashlib
import math
from pathlib import Path
from typing import Any

from .config import Settings
from .ontology import PRACTICE_GROUPS
from .schemas import LEADS
from .rapid_rhythm_supplement import (
    RUNTIME_LEAD,
    RUNTIME_MANIFEST_NAME,
    RUNTIME_MAPPING_VERSION,
    RUNTIME_SCOPE,
    RapidRhythmSupplement,
    SUPPLEMENT_DIRECTORY,
)
from .source_policy import NEVER_LEARNER_SERVE_SOURCES, packet_mode_policy
from .store import CaseStore, LocalWaveformStore


# A dataset must receive an explicit code review before its raw packets are
# allowed into the deployable learner artifact. This is deliberately narrower
# than the ingestion registry (which also contains controlled research sources).
DEPLOYABLE_CORPUS_SOURCES = frozenset({"ptbxl", "prepared_bundle", "leipzig-heart-center"})


def build_repository(settings: Settings):
    """Select the real corpus, or an explicitly enabled test fixture repository."""
    root = resolve_corpus_root(settings)
    if root is not None:
        return CorpusRepository(settings, root)
    from .data_sources import CaseRepository

    return CaseRepository(settings)


def corpus_ready_count(path: Path) -> int | None:
    """Return the case count of a COMPLETE corpus, or None if absent/in-progress.

    A corpus is only selectable when it has corpus.db AND a manifest.json marked
    ``complete: true`` — so an in-progress (still-building) directory is never
    auto-selected, and we never open a mutating DB just to count it.
    """
    manifest_path = path / "manifest.json"
    if not (path / "corpus.db").exists() or not manifest_path.exists():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not manifest.get("complete"):
        return None
    return int(manifest.get("totalCases") or 0)


def resolve_corpus_root(settings: Settings) -> Path | None:
    """Find a COMPLETE built corpus directory (manifest-gated)."""
    configured = getattr(settings, "corpus_root", None)
    if configured:
        path = Path(configured)
        return path if corpus_ready_count(path) is not None else None
    candidates: list[Path] = []
    cwd = Path.cwd()
    for base in (cwd, cwd.parent):
        data = base / "data"
        if data.exists():
            candidates.extend(sorted({data / "ecg_corpus", data / "ecg_corpus_smoke", *data.glob("ecg_corpus*")}))
    seen: set[str] = set()
    best: tuple[int, Path] | None = None
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        count = corpus_ready_count(candidate)
        if count and (best is None or count > best[0]):
            best = (count, candidate)
    return best[1] if best else None


class CorpusRepository:
    def __init__(self, settings: Settings, root: Path):
        self.settings = settings
        self.root = Path(root)
        # Serving is intentionally immutable. Offline build/import tools open a
        # writable CaseStore directly, then publish a complete versioned corpus.
        self.store = CaseStore(self.root / "corpus.db", read_only=True)
        self.waveforms = LocalWaveformStore(self.root / "waveforms")
        self.manifest: dict[str, Any] = {}
        manifest_path = self.root / "manifest.json"
        if manifest_path.exists():
            try:
                self.manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                self.manifest = {}
        self.rapid_rhythm_supplement: RapidRhythmSupplement | None = None
        self.rapid_rhythm_supplement_error: str | None = None
        supplement_reference = self.manifest.get("rapidRhythmSupplement")
        if supplement_reference is not None:
            try:
                if not isinstance(supplement_reference, dict):
                    raise ValueError("supplement reference is not an object")
                self.rapid_rhythm_supplement = RapidRhythmSupplement(
                    self.root / SUPPLEMENT_DIRECTORY,
                    expected=supplement_reference,
                )
            except (OSError, TypeError, ValueError) as exc:
                # Keep liveness for rollback/diagnostics, but readiness below
                # fails closed so a partially published supplement can never
                # be silently ignored in production.
                self.rapid_rhythm_supplement_error = type(exc).__name__
        self.status = {
            "active_source": "corpus",
            "fixture_fallback": False,
            "data_readiness": "real_data_active",
            "corpus_root": str(self.root),
            "case_count": self.store.count(),
            "student_facing_count": self.store.student_facing_count(),
            "tier_distribution": self.store.tier_counts(),
            "manifest": self.manifest,
            "rapid_rhythm_supplement_count": (
                self.rapid_rhythm_supplement.count
                if self.rapid_rhythm_supplement is not None
                else 0
            ),
            "requires_real_data": settings.require_real_data,
        }
        # Expensive packet-policy reconciliation happens once at process start,
        # not on every load-balancer probe. The immutable corpus hash pins the
        # audited result for this running release.
        self._deployment_check = self._build_deployment_check()
        # The release corpus is read-only for the lifetime of this repository.
        # Availability powers several setup pages, so precompute the small set
        # of public practice-group counts once instead of reopening the 879 MiB
        # SQLite index for every `/concepts` request.
        self._concept_ab_count_cache = self.store.concept_ab_counts()
        # The emergency-rhythm supplement is a separate, explicitly selected
        # pool, but its reviewed recognition inventory must still be visible to
        # objective coverage, the mastery planner, calendar suggestions, and
        # coach grounding.  Keep broad ``candidates()`` isolated below; only
        # publish the supplement's manifest-verified exact target counts here.
        if self.rapid_rhythm_supplement is not None:
            for concept_id, count in self.rapid_rhythm_supplement.target_counts.items():
                self._concept_ab_count_cache[concept_id] = (
                    int(self._concept_ab_count_cache.get(concept_id, 0)) + int(count)
                )
        for group in PRACTICE_GROUPS:
            self._group_reliable_count_cached(
                tuple(sorted(set(str(item) for item in group.get("concepts", []))))
            )

    def build_index(self, limit: int | None = None) -> dict[str, Any]:
        """The corpus is prebuilt offline; refresh the live status counters."""
        self.status["case_count"] = self.store.count()
        self.status["student_facing_count"] = self.store.student_facing_count()
        self.status["tier_distribution"] = self.store.tier_counts()
        return self.status

    # --- case access ------------------------------------------------------------

    def get_case(self, case_id: str) -> dict[str, Any] | None:
        packet = self.store.get_packet(case_id)
        if packet is not None:
            return packet
        if self.rapid_rhythm_supplement is not None:
            return self.rapid_rhythm_supplement.get_case(case_id)
        return None

    def rapid_rhythm_candidates(
        self, concept_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Return only the explicit emergency-rhythm supplement pool."""

        if self.rapid_rhythm_supplement is None:
            return []
        return self.rapid_rhythm_supplement.candidates(concept_id)

    def rapid_rhythm_status(self) -> dict[str, Any]:
        if self.rapid_rhythm_supplement is None:
            return {
                "available": False,
                "count": 0,
                "targetCounts": {},
            }
        return {
            "available": True,
            "count": self.rapid_rhythm_supplement.count,
            "targetCounts": self.rapid_rhythm_supplement.target_counts,
            "runtimeScope": "rapid_emergency_rhythm",
            "singleLead": "MLII",
            "algorithmVersion": "2025 AHA CPR and ECC",
            "managementQuestionsFormativeOnly": True,
        }

    def list_cases(
        self, concept: str | None = None, include_uncertain: bool = False, query: str | None = None,
        limit: int = 200, offset: int = 0,
    ) -> list[dict[str, Any]]:
        return self.store.summaries(
            concept=concept,
            include_uncertain=include_uncertain,
            query=query,
            limit=limit,
            offset=offset,
        )

    def candidates(self, concept_id: str | None = None) -> list[dict[str, Any]]:
        return self.store.candidates(concept_id)

    def training_candidates(
        self,
        *,
        segment: str | None = None,
        leads: list[str] | None = None,
        measurement_key: str | None = None,
        truth_key: str | None = None,
    ) -> list[dict[str, Any]]:
        return self.store.training_candidates(
            segment=segment,
            leads=leads,
            measurement_key=measurement_key,
            truth_key=truth_key,
        )

    def concept_ab_counts(self) -> dict[str, int]:
        return dict(self._concept_ab_count_cache)

    def group_reliable_count(self, concept_ids: list[str]) -> int:
        return self._group_reliable_count_cached(
            tuple(sorted(set(str(item) for item in concept_ids)))
        )

    @lru_cache(maxsize=256)
    def _group_reliable_count_cached(self, concept_ids: tuple[str, ...]) -> int:
        main_count = self.store.distinct_case_count(list(concept_ids))
        supplement = getattr(self, "rapid_rhythm_supplement", None)
        if supplement is None:
            return main_count
        supplemental_count = sum(
            int(supplement.target_counts.get(concept_id, 0))
            for concept_id in concept_ids
        )
        return main_count + supplemental_count

    def deployment_readiness(self) -> tuple[bool, str]:
        """Return the cached, fail-closed release-corpus capability verdict."""
        return self._deployment_check

    def _build_deployment_check(self) -> tuple[bool, str]:
        """Reconcile manifest, packet policy, and representative waveforms.

        Tier A/B alone is not a serving contract. Every learner-eligible packet
        is passed through the same source policy used by Training and Rapid,
        then one waveform per source/mode is actually decoded. This catches a
        valid-looking SQLite file whose sources or waveform paths are unusable.
        """
        if self.manifest.get("rapidRhythmSupplement") is not None and (
            self.rapid_rhythm_supplement is None
            or self.rapid_rhythm_supplement_error is not None
        ):
            return False, "rapid_rhythm_supplement_invalid"

        try:
            total = self.store.count()
            source_counts = self.store.source_counts()
            student_count = self.store.student_facing_count()
            manifest_total = int(self.manifest.get("totalCases") or self.manifest.get("built") or 0)
            manifest_sources = {
                str(source): int(count)
                for source, count in (self.manifest.get("sourceCounts") or {}).items()
            }
            manifest_students = int(self.manifest.get("studentFacing") or 0)
        except (AttributeError, TypeError, ValueError, OSError):
            return False, "corpus_release_contract_invalid"

        if total != manifest_total or source_counts != manifest_sources or student_count != manifest_students:
            return False, "corpus_manifest_counts_mismatch"
        if total < int(self.settings.min_corpus_cases):
            return False, "corpus_below_release_minimum"
        if source_counts.get("ptbxl", 0) < int(self.settings.min_ptbxl_cases):
            return False, "ptbxl_release_incomplete"
        if not source_counts or not set(source_counts) <= DEPLOYABLE_CORPUS_SOURCES:
            return False, "corpus_contains_unapproved_source"
        if set(source_counts) & NEVER_LEARNER_SERVE_SOURCES:
            return False, "corpus_contains_research_only_source"

        if bool(getattr(self.settings, "require_release_audit", False)):
            audit_path = self.root / "release-audit.json"
            try:
                audit = json.loads(audit_path.read_text(encoding="utf-8"))
                manifest_sha = hashlib.sha256(
                    (self.root / "manifest.json").read_bytes()
                ).hexdigest()
                audit_sources = {
                    str(source): int(count)
                    for source, count in (audit.get("sourceCounts") or {}).items()
                }
                waveform_audit = audit.get("waveforms") or {}
                clinical_audit = audit.get("clinical") or {}
            except (AttributeError, json.JSONDecodeError, OSError, TypeError, ValueError):
                return False, "corpus_release_audit_invalid"
            if (
                int(audit.get("schemaVersion") or 0) != 1
                or audit.get("manifestSha256") != manifest_sha
                or int(audit.get("totalCases") or 0) != total
                or audit_sources != source_counts
                or waveform_audit.get("complete") is not True
                or int(waveform_audit.get("caseFilesChecked") or 0) != total
                or int(waveform_audit.get("npyFilesFound") or 0) != total
                or clinical_audit.get("harnessPassed") is not True
                or int(clinical_audit.get("distinctRealEcgs") or 0)
                < int(self.settings.min_clinical_cases)
            ):
                return False, "corpus_release_audit_mismatch"
            if not self._rapid_rhythm_release_audit_matches(audit):
                return False, "rapid_rhythm_release_audit_mismatch"

        eligible = {"training": 0, "rapid": 0}
        representatives: dict[tuple[str, str], str] = {}
        try:
            for packet in self.store.iter_student_packets():
                source = str(packet.get("source") or "")
                for mode in ("training", "rapid"):
                    if packet_mode_policy(packet, mode).allowed:
                        eligible[mode] += 1
                        representatives.setdefault((source, mode), str(packet.get("case_id") or ""))
        except (OSError, TypeError, ValueError):
            return False, "corpus_packet_policy_audit_failed"

        minimum = int(self.settings.min_practice_cases)
        if any(eligible[mode] < minimum for mode in eligible):
            return False, "practice_pool_below_release_minimum"

        student_sources = {source for source, count in self.store.student_source_counts().items() if count > 0}
        if any((source, mode) not in representatives for source in student_sources for mode in eligible):
            return False, "learner_source_has_no_eligible_packets"

        try:
            for case_id in representatives.values():
                values = self.waveforms.read(case_id, ["II"]).get("II") or []
                if len(values) < 2 or not all(math.isfinite(float(value)) for value in values):
                    return False, "representative_waveform_unreadable"
        except (OSError, TypeError, ValueError):
            return False, "representative_waveform_unreadable"
        return True, "ready"

    def _rapid_rhythm_release_audit_matches(self, audit: dict[str, Any]) -> bool:
        """Pin an advertised supplement to its exhaustive publication audit."""

        reference = self.manifest.get("rapidRhythmSupplement")
        if reference is None:
            return True
        reader = self.rapid_rhythm_supplement
        if not isinstance(reference, dict) or reader is None:
            return False
        supplement_audit = audit.get("rapidRhythmSupplement")
        if not isinstance(supplement_audit, dict):
            return False
        waveform_audit = supplement_audit.get("waveforms") or {}
        identity_audit = supplement_audit.get("identity") or {}
        try:
            supplement_root = self.root / SUPPLEMENT_DIRECTORY
            runtime_path = supplement_root / RUNTIME_MANIFEST_NAME
            source_manifest_path = supplement_root / "manifest.json"
            database_path = supplement_root / "rhythm_streams.db"
            expected_top_level = {
                "manifest.json",
                RUNTIME_MANIFEST_NAME,
                "rhythm_streams.db",
                "waveforms",
            }
            actual_top_level = {path.name for path in supplement_root.iterdir()}
            contains_symlink = any(path.is_symlink() for path in supplement_root.rglob("*"))
            contains_non_npy_waveform = any(
                path.is_file() and path.suffix != ".npy"
                for path in reader.waveform_root.rglob("*")
            )
            runtime_sha = hashlib.sha256(runtime_path.read_bytes()).hexdigest()
            source_manifest_sha = hashlib.sha256(source_manifest_path.read_bytes()).hexdigest()
            database_sha = hashlib.sha256(database_path.read_bytes()).hexdigest()
            waveform_files_digest = hashlib.sha256()
            waveform_paths = sorted(
                reader.waveform_root.rglob("*.npy"),
                key=lambda path: path.relative_to(reader.root).as_posix(),
            )
            for waveform_path in waveform_paths:
                file_sha = hashlib.sha256(waveform_path.read_bytes()).hexdigest()
                relative = waveform_path.relative_to(reader.root).as_posix()
                waveform_files_digest.update(
                    f"{file_sha}  {relative}\n".encode("ascii")
                )
            waveform_files_sha = waveform_files_digest.hexdigest()
            audited_targets = {
                str(target): int(count)
                for target, count in (
                    supplement_audit.get("learnerTargetCounts") or {}
                ).items()
            }
            reference_targets = {
                str(target): int(count)
                for target, count in (reference.get("learnerTargetCounts") or {}).items()
            }
            count = int(reference.get("fragmentCount") or 0)
            audited_count = int(supplement_audit.get("fragmentCount") or 0)
            audited_schema = int(supplement_audit.get("schemaVersion") or 0)
            audited_case_files = int(waveform_audit.get("caseFilesChecked") or 0)
            audited_npy_files = int(waveform_audit.get("npyFilesFound") or 0)
            audited_columns = int(waveform_audit.get("expectedColumns") or 0)
        except (AttributeError, OSError, TypeError, ValueError):
            return False
        return (
            supplement_audit.get("present") is True
            and supplement_audit.get("complete") is True
            and audited_schema == 1
            and supplement_audit.get("path") == SUPPLEMENT_DIRECTORY
            and supplement_audit.get("sourceId") == reference.get("sourceId")
            and reference.get("schemaVersion") == 1
            and reference.get("path") == SUPPLEMENT_DIRECTORY
            and reference.get("runtimeScope") == RUNTIME_SCOPE
            and reference.get("mappingVersion") == RUNTIME_MAPPING_VERSION
            and actual_top_level == expected_top_level
            and contains_symlink is False
            and contains_non_npy_waveform is False
            and audited_count == count
            and count == reader.count
            and len(waveform_paths) == count
            and audited_targets == reference_targets == reader.target_counts
            and supplement_audit.get("runtimeManifestSha256") == runtime_sha
            and reference.get("runtimeManifestSha256") == runtime_sha
            and supplement_audit.get("sourceManifestSha256") == source_manifest_sha
            and reader.runtime_manifest.get("sourceManifestSha256") == source_manifest_sha
            and supplement_audit.get("databaseSha256") == database_sha
            and supplement_audit.get("contentIndexSha256")
            == reader.runtime_manifest.get("contentIndexSha256")
            and isinstance(waveform_audit, dict)
            and waveform_audit.get("complete") is True
            and audited_case_files == count
            and audited_npy_files == count
            and audited_columns == 1
            and waveform_audit.get("lead") == RUNTIME_LEAD
            and waveform_audit.get("dtype") == "int16"
            and waveform_audit.get("filesSha256") == waveform_files_sha
            and isinstance(identity_audit, dict)
            and identity_audit.get("opaqueOnly") is True
            and identity_audit.get("rawPatientIdentifiersIncluded") is False
            and identity_audit.get("rawRecordIdentifiersIncluded") is False
            and supplement_audit.get("clinicalManagementEligible") is False
            and supplement_audit.get("shockabilityClassificationEligible") is False
            and supplement_audit.get("actionQuestionsFormativeOnly") is True
        )

    # --- waveform access --------------------------------------------------------

    def get_waveform_window(
        self,
        case_id: str,
        leads: list[str] | None = None,
        start: float = 0,
        end: float | None = None,
        max_points: int = 1200,
    ) -> dict[str, Any] | None:
        if self.rapid_rhythm_supplement is not None:
            supplemental = self.rapid_rhythm_supplement.get_case(case_id)
            if supplemental is not None:
                return self.rapid_rhythm_supplement.get_waveform_window(
                    case_id,
                    leads=leads,
                    start=start,
                    end=end,
                    max_points=max_points,
                )
        wanted = [lead for lead in (leads or LEADS) if lead in LEADS]
        data = self.waveforms.read(case_id, wanted)
        if not data:
            return None
        fs = int(self.manifest.get("samplingFrequency") or 100)
        n = max((len(v) for v in data.values()), default=0)
        duration = round(n / fs, 3)
        end = duration if end is None else min(end, duration)
        start = max(0, min(start, end))
        start_idx = int(start * fs)
        end_idx = int(end * fs)
        step = max(1, (end_idx - start_idx) // max(1, max_points))
        indices = list(range(start_idx, end_idx, step))
        times = [round(i / fs, 3) for i in indices]
        return {
            "caseId": case_id,
            "samplingFrequency": fs,
            "durationSec": duration,
            "startSec": start,
            "endSec": end,
            "leads": [
                {
                    "lead": lead,
                    "points": [
                        {"timeSec": t, "amplitudeMv": values[i]}
                        for t, i in zip(times, indices)
                        if i < len(values)
                    ],
                }
                for lead, values in data.items()
            ],
        }
