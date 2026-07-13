"""Corpus-backed case repository (SQLite case store + compact waveform store).

Presents the same surface the API/adaptive layer needs, but serves the full
PTB-XL corpus from disk-backed stores instead of an in-memory dict, with no
serve-time WFDB/Drive dependency. Learner-facing configuration fails closed
without that corpus; the fixture repository is an explicit test-only opt-out.
"""

from __future__ import annotations

import json
import hashlib
import math
from pathlib import Path
from typing import Any

from .config import Settings
from .schemas import LEADS
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
        self.status = {
            "active_source": "corpus",
            "fixture_fallback": False,
            "data_readiness": "real_data_active",
            "corpus_root": str(self.root),
            "case_count": self.store.count(),
            "student_facing_count": self.store.student_facing_count(),
            "tier_distribution": self.store.tier_counts(),
            "manifest": self.manifest,
            "requires_real_data": settings.require_real_data,
        }
        # Expensive packet-policy reconciliation happens once at process start,
        # not on every load-balancer probe. The immutable corpus hash pins the
        # audited result for this running release.
        self._deployment_check = self._build_deployment_check()

    def build_index(self, limit: int | None = None) -> dict[str, Any]:
        """The corpus is prebuilt offline; refresh the live status counters."""
        self.status["case_count"] = self.store.count()
        self.status["student_facing_count"] = self.store.student_facing_count()
        self.status["tier_distribution"] = self.store.tier_counts()
        return self.status

    # --- case access ------------------------------------------------------------

    def get_case(self, case_id: str) -> dict[str, Any] | None:
        return self.store.get_packet(case_id)

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
        return self.store.concept_ab_counts()

    def group_reliable_count(self, concept_ids: list[str]) -> int:
        return self.store.distinct_case_count(concept_ids)

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

    # --- waveform access --------------------------------------------------------

    def get_waveform_window(
        self,
        case_id: str,
        leads: list[str] | None = None,
        start: float = 0,
        end: float | None = None,
        max_points: int = 1200,
    ) -> dict[str, Any] | None:
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
