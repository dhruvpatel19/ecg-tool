#!/usr/bin/env bash

set -Eeuo pipefail

log() {
  printf '[ecg-deploy] %s\n' "$*" >&2
}

die() {
  log "ERROR: $*"
  exit 1
}

require_root() {
  [[ "${EUID}" -eq 0 ]] || die "run as root"
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "required command is missing: $1"
}

validate_ops_root() {
  local root="$1" mode owner resolved
  [[ "${root}" == /srv/* && -d "${root}" && ! -L "${root}" ]] \
    || die "operations root must be a non-symlink directory below /srv"
  resolved="$(realpath -e "${root}")"
  [[ "${resolved}" == "${root}" ]] || die "operations root must use its resolved path"
  owner="$(stat --format='%u' "${root}")"
  mode="$(stat --format='%a' "${root}")"
  [[ "${owner}" == "0" ]] || die "operations root must be owned by root"
  (( (8#${mode} & 0022) == 0 )) \
    || die "operations root must not be group/other writable"
}

remove_ops_worktree() {
  local root="$1" candidate="$2" root_real candidate_real
  [[ -n "${candidate}" && -d "${candidate}" && ! -L "${candidate}" ]] || return 0
  root_real="$(realpath -e "${root}")"
  candidate_real="$(realpath -e "${candidate}")"
  [[ "${candidate_real}" == "${root_real}/"* ]] \
    || die "refusing out-of-scope operations cleanup"
  rm -rf -- "${candidate_real}"
}

# Retry bounded, idempotent control-plane and artifact reads during bootstrap.
# Callers choose operations that are safe to repeat; the delay doubles to 30s.
retry() {
  [[ $# -ge 3 ]] || die "retry requires ATTEMPTS INITIAL_DELAY COMMAND..."
  local max_attempts="$1" delay="$2" attempt=1 status=0
  shift 2
  [[ "${max_attempts}" =~ ^[1-9][0-9]*$ && "${delay}" =~ ^[0-9]+$ ]] \
    || die "invalid retry bounds"
  while true; do
    if "$@"; then
      return 0
    else
      status=$?
    fi
    if (( attempt >= max_attempts )); then
      return "${status}"
    fi
    log "attempt ${attempt}/${max_attempts} failed; retrying in ${delay}s: $1"
    sleep "${delay}"
    attempt=$((attempt + 1))
    delay=$((delay < 15 ? delay * 2 : 30))
  done
}

require_safe_release() {
  [[ "$1" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$ ]] || die "invalid release identifier"
}

require_sha256() {
  [[ "$1" =~ ^[a-fA-F0-9]{64}$ ]] || die "expected a 64-character SHA-256"
}

sha256_file() {
  sha256sum "$1" | awk '{print $1}'
}

validate_corpus_tree() {
  local root="$1"
  [[ -f "${root}/manifest.json" ]] || die "corpus manifest.json is missing"
  [[ -f "${root}/release-audit.json" ]] || die "corpus release-audit.json is missing"
  [[ -f "${root}/corpus.db" ]] || die "corpus.db is missing"
  [[ -d "${root}/waveforms" ]] || die "waveforms directory is missing"

  jq -e '.complete == true' "${root}/manifest.json" >/dev/null \
    || die "corpus manifest is not marked complete"

  local integrity case_count expected_count waveform_count student_count manifest_sha audited_manifest_sha
  integrity="$(sqlite3 -readonly "${root}/corpus.db" 'PRAGMA integrity_check;')"
  [[ "${integrity}" == "ok" ]] || die "corpus.db integrity check failed"
  case_count="$(sqlite3 -readonly "${root}/corpus.db" 'SELECT COUNT(*) FROM cases;')"
  student_count="$(sqlite3 -readonly "${root}/corpus.db" \
    "SELECT COUNT(*) FROM cases WHERE teaching_tier IN ('A','B');")"
  expected_count="$(jq -r '.totalCases // .built // 0' "${root}/manifest.json")"
  [[ "${case_count}" =~ ^[0-9]+$ && "${case_count}" -gt 0 ]] || die "corpus contains no cases"
  [[ "${student_count}" =~ ^[0-9]+$ && "${student_count}" -gt 0 ]] \
    || die "corpus contains no student-facing cases"
  [[ "${expected_count}" == "${case_count}" ]] \
    || die "manifest/database case-count mismatch (${expected_count} != ${case_count})"
  waveform_count="$(find "${root}/waveforms" -type f -name '*.npy' -printf '.' | wc -c)"
  [[ "${waveform_count}" == "${case_count}" ]] \
    || die "waveform/database case-count mismatch (${waveform_count} != ${case_count})"
  manifest_sha="$(sha256_file "${root}/manifest.json")"
  audited_manifest_sha="$(jq -r '.manifestSha256 // ""' "${root}/release-audit.json")"
  [[ "${audited_manifest_sha}" == "${manifest_sha}" ]] \
    || die "release audit does not match manifest"
  jq -e --argjson count "${case_count}" '
    .schemaVersion == 1
    and .totalCases == $count
    and .waveforms.complete == true
    and .waveforms.caseFilesChecked == $count
    and .waveforms.npyFilesFound == $count
    and .eligibleCaseCounts.training >= 5000
    and .eligibleCaseCounts.rapid >= 5000
    and .clinical.harnessPassed == true
    and .clinical.distinctRealEcgs >= 100
  ' "${root}/release-audit.json" >/dev/null \
    || die "release audit does not satisfy product capability minima"

  if jq -e '.rapidRhythmSupplement != null' "${root}/manifest.json" >/dev/null; then
    local rhythm_path rhythm_root rhythm_integrity rhythm_count rhythm_waveform_count
    local rhythm_runtime_sha rhythm_reference_sha rhythm_source_sha rhythm_expected_source_sha
    local rhythm_database_sha rhythm_waveform_files_sha rhythm_reference_targets
    local rhythm_runtime_targets rhythm_audit_targets rhythm_top_level_count
    rhythm_path="$(jq -er '.rapidRhythmSupplement.path' "${root}/manifest.json")"
    [[ "${rhythm_path}" == "rapid_rhythm_supplement" ]] \
      || die "rapid rhythm supplement path is outside the reviewed release contract"
    rhythm_root="${root}/${rhythm_path}"
    [[ -d "${rhythm_root}" && ! -L "${rhythm_root}" ]] \
      || die "referenced rapid rhythm supplement directory is missing or unsafe"
    [[ -z "$(find "${rhythm_root}" -type l -print -quit)" ]] \
      || die "rapid rhythm supplement contains a symlink"
    rhythm_top_level_count="$(find "${rhythm_root}" -mindepth 1 -maxdepth 1 -printf '.' | wc -c)"
    [[ "${rhythm_top_level_count}" == "4" ]] \
      || die "rapid rhythm supplement contains unexpected top-level artifacts"
    [[ -f "${rhythm_root}/manifest.json" ]] \
      || die "rapid rhythm source manifest is missing"
    [[ -f "${rhythm_root}/runtime-manifest.json" ]] \
      || die "rapid rhythm runtime manifest is missing"
    [[ -f "${rhythm_root}/rhythm_streams.db" ]] \
      || die "rapid rhythm database is missing"
    [[ -d "${rhythm_root}/waveforms" ]] \
      || die "rapid rhythm waveforms directory is missing"
    [[ -z "$(find "${rhythm_root}/waveforms" -type f ! -name '*.npy' -print -quit)" ]] \
      || die "rapid rhythm waveform tree contains a non-NPY artifact"

    rhythm_integrity="$(sqlite3 -readonly "${rhythm_root}/rhythm_streams.db" \
      'PRAGMA integrity_check;')"
    [[ "${rhythm_integrity}" == "ok" ]] \
      || die "rapid rhythm database integrity check failed"
    rhythm_count="$(sqlite3 -readonly "${rhythm_root}/rhythm_streams.db" \
      'SELECT COUNT(*) FROM rhythm_windows;')"
    [[ "${rhythm_count}" =~ ^[0-9]+$ && "${rhythm_count}" -gt 0 ]] \
      || die "rapid rhythm supplement contains no fragments"
    rhythm_waveform_count="$(find "${rhythm_root}/waveforms" -type f -name '*.npy' -printf '.' | wc -c)"
    [[ "${rhythm_waveform_count}" == "${rhythm_count}" ]] \
      || die "rapid rhythm waveform/database count mismatch"

    rhythm_runtime_sha="$(sha256_file "${rhythm_root}/runtime-manifest.json")"
    rhythm_reference_sha="$(jq -r '.rapidRhythmSupplement.runtimeManifestSha256 // ""' \
      "${root}/manifest.json")"
    [[ "${rhythm_reference_sha}" == "${rhythm_runtime_sha}" ]] \
      || die "rapid rhythm parent/runtime manifest hash mismatch"
    rhythm_source_sha="$(sha256_file "${rhythm_root}/manifest.json")"
    rhythm_expected_source_sha="$(jq -r '.sourceManifestSha256 // ""' \
      "${rhythm_root}/runtime-manifest.json")"
    [[ "${rhythm_expected_source_sha}" == "${rhythm_source_sha}" ]] \
      || die "rapid rhythm source/runtime manifest hash mismatch"
    rhythm_database_sha="$(sha256_file "${rhythm_root}/rhythm_streams.db")"
    rhythm_waveform_files_sha="$(
      cd "${rhythm_root}"
      find waveforms -type f -name '*.npy' -print0 \
        | LC_ALL=C sort -z \
        | xargs -0 sha256sum \
        | sha256sum \
        | awk '{print $1}'
    )"
    rhythm_reference_targets="$(jq -cS '.rapidRhythmSupplement.learnerTargetCounts // {}' \
      "${root}/manifest.json")"
    rhythm_runtime_targets="$(jq -cS '.learnerTargetCounts // {}' \
      "${rhythm_root}/runtime-manifest.json")"
    rhythm_audit_targets="$(jq -cS '.rapidRhythmSupplement.learnerTargetCounts // {}' \
      "${root}/release-audit.json")"
    [[ "${rhythm_reference_targets}" == "${rhythm_runtime_targets}" \
      && "${rhythm_reference_targets}" == "${rhythm_audit_targets}" ]] \
      || die "rapid rhythm learner target counts do not reconcile"

    jq -e --argjson count "${rhythm_count}" \
      --arg runtime_sha "${rhythm_runtime_sha}" '
      .rapidRhythmSupplement.schemaVersion == 1
      and .rapidRhythmSupplement.path == "rapid_rhythm_supplement"
      and .rapidRhythmSupplement.sourceId == "ecg-fragment-dangerous-arrhythmia"
      and .rapidRhythmSupplement.runtimeScope == "rapid_emergency_rhythm"
      and .rapidRhythmSupplement.mappingVersion == "high-risk-ventricular-rhythm-v1"
      and .rapidRhythmSupplement.fragmentCount == $count
      and .rapidRhythmSupplement.runtimeManifestSha256 == $runtime_sha
    ' "${root}/manifest.json" >/dev/null \
      || die "rapid rhythm parent reference is invalid"
    jq -e --argjson count "${rhythm_count}" --arg source_sha "${rhythm_source_sha}" '
      .schemaVersion == 1
      and .complete == true
      and .sourceId == "ecg-fragment-dangerous-arrhythmia"
      and .mappingVersion == "high-risk-ventricular-rhythm-v1"
      and .runtimeScope == "rapid_emergency_rhythm"
      and .fragmentCount == $count
      and .sourceManifestSha256 == $source_sha
      and .clinicalCaseEligible == false
      and .hemodynamicContextAvailable == false
      and .stabilityInferenceEligible == false
      and .cardiacArrestInferenceEligible == false
      and .shockabilityClassificationEligible == false
      and .clinicalManagementEligible == false
      and .treatmentOrActionSequenceEligible == false
      and .actionQuestionsRequireSeparateAuthoredContext == true
      and .actionQuestionsFormativeOnly == true
    ' "${rhythm_root}/runtime-manifest.json" >/dev/null \
      || die "rapid rhythm runtime manifest violates its evidence boundary"
    jq -e --argjson count "${rhythm_count}" '
      .complete == true
      and .fragmentCount == $count
      and .rawPatientIdentifiersIncluded == false
      and .rawRecordIdentifiersIncluded == false
      and .currentRuntimeConnected == false
      and .clinicalManagementEligible == false
      and .shockabilityClassificationEligible == false
    ' "${rhythm_root}/manifest.json" >/dev/null \
      || die "rapid rhythm source manifest contains unsafe release claims"
    jq -e --argjson count "${rhythm_count}" \
      --arg runtime_sha "${rhythm_runtime_sha}" \
      --arg source_sha "${rhythm_source_sha}" \
      --arg database_sha "${rhythm_database_sha}" \
      --arg waveform_sha "${rhythm_waveform_files_sha}" \
      --arg content_sha "$(jq -r '.contentIndexSha256 // ""' \
        "${rhythm_root}/runtime-manifest.json")" '
      .rapidRhythmSupplement.present == true
      and .rapidRhythmSupplement.complete == true
      and .rapidRhythmSupplement.schemaVersion == 1
      and .rapidRhythmSupplement.path == "rapid_rhythm_supplement"
      and .rapidRhythmSupplement.sourceId == "ecg-fragment-dangerous-arrhythmia"
      and .rapidRhythmSupplement.fragmentCount == $count
      and .rapidRhythmSupplement.runtimeManifestSha256 == $runtime_sha
      and .rapidRhythmSupplement.sourceManifestSha256 == $source_sha
      and .rapidRhythmSupplement.databaseSha256 == $database_sha
      and .rapidRhythmSupplement.contentIndexSha256 == $content_sha
      and .rapidRhythmSupplement.waveforms.complete == true
      and .rapidRhythmSupplement.waveforms.caseFilesChecked == $count
      and .rapidRhythmSupplement.waveforms.npyFilesFound == $count
      and .rapidRhythmSupplement.waveforms.expectedColumns == 1
      and .rapidRhythmSupplement.waveforms.lead == "MLII"
      and .rapidRhythmSupplement.waveforms.dtype == "int16"
      and .rapidRhythmSupplement.waveforms.filesSha256 == $waveform_sha
      and .rapidRhythmSupplement.identity.opaqueOnly == true
      and .rapidRhythmSupplement.identity.rawPatientIdentifiersIncluded == false
      and .rapidRhythmSupplement.identity.rawRecordIdentifiersIncluded == false
      and .rapidRhythmSupplement.clinicalManagementEligible == false
      and .rapidRhythmSupplement.shockabilityClassificationEligible == false
      and .rapidRhythmSupplement.actionQuestionsFormativeOnly == true
    ' "${root}/release-audit.json" >/dev/null \
      || die "rapid rhythm exhaustive release audit does not match the packaged data"
  else
    jq -e '.rapidRhythmSupplement.present != true' "${root}/release-audit.json" >/dev/null \
      || die "release audit advertises an unreferenced rapid rhythm supplement"
  fi
}

wait_ready() {
  local timeout_seconds="${1:-180}"
  local deadline=$((SECONDS + timeout_seconds))
  while (( SECONDS < deadline )); do
    if curl --silent --show-error --fail --max-time 5 \
      http://127.0.0.1:8000/livez >/dev/null \
      && curl --silent --show-error --fail --max-time 10 \
      http://127.0.0.1:8000/readyz >/dev/null; then
      return 0
    fi
    sleep 2
  done
  return 1
}

wait_live() {
  local timeout_seconds="${1:-180}"
  local deadline=$((SECONDS + timeout_seconds))
  while (( SECONDS < deadline )); do
    if curl --silent --show-error --fail --max-time 5 \
      http://127.0.0.1:8000/livez >/dev/null; then
      return 0
    fi
    sleep 2
  done
  return 1
}

prune_docker_cache() {
  local retention="${1:-720h}"
  if ! docker image prune --all --force --filter "until=${retention}" >/dev/null; then
    log "warning: unable to prune unused local Docker images"
  fi
}

ensure_docker_image() {
  [[ $# -eq 1 ]] || die "ensure_docker_image requires one immutable image reference"
  if docker image inspect "$1" >/dev/null 2>&1; then
    log "using cached immutable backend image"
    return 0
  fi
  retry 8 2 docker pull "$1"
}
