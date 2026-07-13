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
