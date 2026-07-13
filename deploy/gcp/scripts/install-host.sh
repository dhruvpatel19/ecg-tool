#!/usr/bin/env bash
# Idempotent first-boot installer for the single TRACE ECG application VM.

set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "${SCRIPT_DIR}/lib.sh"
require_root

CONFIG_PATH=/etc/ecg/deployment.env
if [[ "${1:-}" == "--config" && -n "${2:-}" ]]; then
  CONFIG_PATH="$2"
elif [[ $# -ne 0 ]]; then
  die "usage: $0 [--config /absolute/deployment.env]"
fi
[[ "${CONFIG_PATH}" == /* ]] || die "deployment config path must be absolute"

METADATA_BASE=http://metadata.google.internal/computeMetadata/v1
metadata() {
  curl --fail --silent --show-error --retry 8 --retry-all-errors \
    --retry-delay 2 --connect-timeout 5 --max-time 30 \
    --header 'Metadata-Flavor: Google' "${METADATA_BASE}/$1"
}

log "installing signed operating-system dependencies"
export DEBIAN_FRONTEND=noninteractive
retry 6 5 apt-get update -y
retry 6 5 apt-get install -y --no-install-recommends \
  ca-certificates caddy curl docker.io e2fsprogs gzip iptables jq python3 sqlite3 util-linux zstd
if ! command -v gcloud >/dev/null 2>&1; then
  retry 6 5 apt-get install -y --no-install-recommends google-cloud-cli \
    || die "google-cloud-cli is unavailable on the selected image"
fi
systemctl enable --now docker.service

DATA_DEVICE="$(metadata instance/attributes/ecg-data-device)"
DATA_MOUNT="$(metadata instance/attributes/ecg-data-mount)"
ALLOW_DISK_FORMAT="$(metadata instance/attributes/ecg-allow-disk-format)"
[[ "${DATA_DEVICE}" == /dev/disk/by-id/google-* ]] || die "unexpected persistent-disk device path"
[[ "${DATA_MOUNT}" == /srv/* ]] || die "data mount must be below /srv"
[[ -b "${DATA_DEVICE}" ]] || die "persistent data disk is not attached"
mkdir -p "${DATA_MOUNT}"

DEVICE_ROWS="$(lsblk --noheadings --raw --output NAME,TYPE "${DATA_DEVICE}" | sed '/^[[:space:]]*$/d')"
FSTYPE="$(lsblk --noheadings --raw --output FSTYPE "${DATA_DEVICE}" | tr -d '[:space:]')"
if [[ -z "${FSTYPE}" ]]; then
  [[ "${ALLOW_DISK_FORMAT,,}" == "true" ]] \
    || die "blank disk formatting was not explicitly authorized"
  [[ "$(printf '%s\n' "${DEVICE_ROWS}" | wc -l)" -eq 1 \
    && "$(printf '%s\n' "${DEVICE_ROWS}" | awk '{print $2}')" == "disk" ]] \
    || die "unformatted data device has partitions or an unexpected layout"
  [[ -z "$(wipefs --noheadings --output TYPE "${DATA_DEVICE}" 2>/dev/null | tr -d '[:space:]')" ]] \
    || die "unformatted data device contains a recognized signature"
  log "formatting the new persistent data disk"
  mkfs.ext4 -F -m 0 -L ecg-data "${DATA_DEVICE}"
elif [[ "${FSTYPE}" != "ext4" ]]; then
  die "data disk filesystem must be ext4, found ${FSTYPE}"
fi

DISK_UUID="$(blkid -s UUID -o value "${DATA_DEVICE}")"
[[ -n "${DISK_UUID}" ]] || die "data disk UUID is unavailable"
if ! grep -q "^UUID=${DISK_UUID}[[:space:]]" /etc/fstab; then
  if awk -v mount_path="${DATA_MOUNT}" -v wanted="UUID=${DISK_UUID}" \
    '$2 == mount_path && $1 != wanted { found=1 } END { exit !found }' /etc/fstab; then
    die "fstab already maps the data mount to a different device"
  fi
  printf 'UUID=%s %s ext4 defaults,nofail,discard 0 2\n' "${DISK_UUID}" "${DATA_MOUNT}" >>/etc/fstab
fi
mountpoint -q "${DATA_MOUNT}" || mount "${DATA_MOUNT}"
MOUNTED_UUID="$(findmnt --noheadings --output UUID --target "${DATA_MOUNT}" | tr -d '[:space:]')"
[[ "${MOUNTED_UUID}" == "${DISK_UUID}" ]] \
  || die "mounted data filesystem UUID does not match the attached disk"

# The reviewed units use this stable path even if an operator selects another
# /srv mount. Refuse to overwrite a real directory.
if [[ "${DATA_MOUNT}" != /srv/ecg-data ]]; then
  [[ ! -e /srv/ecg-data || -L /srv/ecg-data ]] || die "/srv/ecg-data is not a symlink"
  ln -sfn "${DATA_MOUNT}" /srv/ecg-data
fi
mkdir -p "${DATA_MOUNT}/state" "${DATA_MOUNT}/corpus" "${DATA_MOUNT}/artifacts" /var/lib/ecg-gcloud
chown 10001:10001 "${DATA_MOUNT}/state"
chmod 0750 "${DATA_MOUNT}/state"
install -d -o root -g 10001 -m 0750 "${DATA_MOUNT}/ops"
validate_ops_root "${DATA_MOUNT}/ops"
chmod 0700 /var/lib/ecg-gcloud

PROJECT_ID="$(metadata project/project-id)"
BACKEND_IMAGE="$(metadata instance/attributes/ecg-backend-image)"
CORPUS_URI="$(metadata instance/attributes/ecg-corpus-uri)"
CORPUS_SHA="$(metadata instance/attributes/ecg-corpus-sha256)"
BACKUP_URI="$(metadata instance/attributes/ecg-backup-uri)"
AUTH_SECRET="$(metadata instance/attributes/ecg-auth-secret)"
ORIGIN_SECRET="$(metadata instance/attributes/ecg-origin-secret)"
LLM_SECRET="$(metadata instance/attributes/ecg-llm-secret || true)"
BACKEND_DOMAIN="$(metadata instance/attributes/ecg-backend-domain)"
ACME_EMAIL="$(metadata instance/attributes/ecg-acme-email)"
LLM_PROVIDER="$(metadata instance/attributes/ecg-llm-provider)"
LLM_MODEL="$(metadata instance/attributes/ecg-llm-model || true)"
LLM_BASE_URL="$(metadata instance/attributes/ecg-llm-base-url || true)"
LLM_REQUIRED="$(metadata instance/attributes/ecg-llm-required)"
LLM_MAX_COMPLETION_TOKENS="$(metadata instance/attributes/ecg-llm-max-completion-tokens)"
LLM_REQUEST_TIMEOUT_SECONDS="$(metadata instance/attributes/ecg-llm-request-timeout-seconds)"
LLM_MAX_REQUEST_BYTES="$(metadata instance/attributes/ecg-llm-max-request-bytes)"
LLM_MAX_RESPONSE_BYTES="$(metadata instance/attributes/ecg-llm-max-response-bytes)"
LLM_AUTHENTICATED_DAILY_LIMIT="$(metadata instance/attributes/ecg-llm-authenticated-daily-limit)"
LLM_GUEST_DAILY_LIMIT="$(metadata instance/attributes/ecg-llm-guest-daily-limit)"
LLM_IP_HOURLY_LIMIT="$(metadata instance/attributes/ecg-llm-ip-hourly-limit)"
LLM_GLOBAL_DAILY_LIMIT="$(metadata instance/attributes/ecg-llm-global-daily-limit)"
BACKUP_MAX_AGE_SECONDS="$(metadata instance/attributes/ecg-backup-max-age-seconds)"
MIN_STATE_FREE_BYTES="$(metadata instance/attributes/ecg-min-state-free-bytes)"
require_sha256 "${CORPUS_SHA}"
[[ "${BACKEND_IMAGE}" =~ @sha256:[a-f0-9]{64}$ ]] || die "backend image is not digest-pinned"
[[ "${BACKEND_DOMAIN}" =~ ^[A-Za-z0-9.-]+$ && "${BACKEND_DOMAIN}" == *.* ]] \
  || die "backend DNS hostname is invalid"
[[ "${ACME_EMAIL}" == *@*.* ]] || die "ACME contact email is invalid"

CORPUS_RELEASE="release-${CORPUS_SHA:0:16}"
umask 077
mkdir -p "$(dirname "${CONFIG_PATH}")" /etc/ecg
CONFIG_NEW="$(mktemp "$(dirname "${CONFIG_PATH}")/deployment.env.XXXXXX")"
{
  printf 'ECG_STATE_DB=%q\n' "${DATA_MOUNT}/state/ecg_learning.db"
  printf 'ECG_OPS_ROOT=%q\n' "${DATA_MOUNT}/ops"
  printf 'ECG_BACKUP_GCS_PREFIX=%q\n' "${BACKUP_URI%/}"
  printf 'ECG_CORPUS_GCS_URI=%q\n' "${CORPUS_URI}"
  printf 'ECG_CORPUS_RELEASE=%q\n' "${CORPUS_RELEASE}"
  printf 'ECG_CORPUS_SHA256=%q\n' "${CORPUS_SHA}"
  printf 'ECG_BACKEND_DOMAIN=%q\n' "${BACKEND_DOMAIN}"
  printf 'ECG_ACME_EMAIL=%q\n' "${ACME_EMAIL}"
  printf 'GCP_PROJECT_ID=%q\n' "${PROJECT_ID}"
  printf 'ECG_AUTH_SECRET_ID=%q\n' "${AUTH_SECRET}"
  printf 'ECG_ORIGIN_SECRET_ID=%q\n' "${ORIGIN_SECRET}"
  printf 'ECG_LLM_PROVIDER=%q\n' "${LLM_PROVIDER:-mock}"
  printf 'ECG_LLM_SECRET_ID=%q\n' "${LLM_SECRET}"
  printf 'ECG_LLM_MODEL=%q\n' "${LLM_MODEL}"
  printf 'ECG_LLM_BASE_URL=%q\n' "${LLM_BASE_URL}"
  printf 'ECG_LLM_REQUIRED=%q\n' "${LLM_REQUIRED}"
  printf 'ECG_LLM_MAX_COMPLETION_TOKENS=%q\n' "${LLM_MAX_COMPLETION_TOKENS}"
  printf 'ECG_LLM_REQUEST_TIMEOUT_SECONDS=%q\n' "${LLM_REQUEST_TIMEOUT_SECONDS}"
  printf 'ECG_LLM_MAX_REQUEST_BYTES=%q\n' "${LLM_MAX_REQUEST_BYTES}"
  printf 'ECG_LLM_MAX_RESPONSE_BYTES=%q\n' "${LLM_MAX_RESPONSE_BYTES}"
  printf 'ECG_LLM_AUTHENTICATED_DAILY_LIMIT=%q\n' "${LLM_AUTHENTICATED_DAILY_LIMIT}"
  printf 'ECG_LLM_GUEST_DAILY_LIMIT=%q\n' "${LLM_GUEST_DAILY_LIMIT}"
  printf 'ECG_LLM_IP_HOURLY_LIMIT=%q\n' "${LLM_IP_HOURLY_LIMIT}"
  printf 'ECG_LLM_GLOBAL_DAILY_LIMIT=%q\n' "${LLM_GLOBAL_DAILY_LIMIT}"
  printf 'ECG_BACKUP_MAX_AGE_SECONDS=%q\n' "${BACKUP_MAX_AGE_SECONDS}"
  printf 'ECG_MIN_STATE_FREE_BYTES=%q\n' "${MIN_STATE_FREE_BYTES}"
} >"${CONFIG_NEW}"
chmod 0600 "${CONFIG_NEW}"
mv -f "${CONFIG_NEW}" "${CONFIG_PATH}"

log "installing reviewed runtime assets"
install -d -m 0755 /usr/local/lib/ecg-deploy /etc/caddy /etc/systemd/system/caddy.service.d
install -m 0755 "${SCRIPT_DIR}"/*.sh /usr/local/lib/ecg-deploy/
install -m 0644 "${SCRIPT_DIR}/../systemd/ecg-backend.service" /etc/systemd/system/
install -m 0644 "${SCRIPT_DIR}/../systemd/ecg-metadata-firewall.service" /etc/systemd/system/
install -m 0644 "${SCRIPT_DIR}/../systemd/ecg-metadata-firewall.timer" /etc/systemd/system/
install -m 0644 "${SCRIPT_DIR}/../systemd/ecg-sqlite-backup.service" /etc/systemd/system/
install -m 0644 "${SCRIPT_DIR}/../systemd/ecg-sqlite-backup.timer" /etc/systemd/system/
install -m 0644 "${SCRIPT_DIR}/../caddy/Caddyfile" /etc/caddy/Caddyfile

cat >/etc/ecg/caddy.env <<EOF
ECG_BACKEND_DOMAIN=${BACKEND_DOMAIN}
ECG_ACME_EMAIL=${ACME_EMAIL}
EOF
chmod 0600 /etc/ecg/caddy.env
cat >/etc/systemd/system/caddy.service.d/ecg-environment.conf <<'EOF'
[Service]
EnvironmentFile=/etc/ecg/caddy.env
EOF

export CLOUDSDK_CONFIG=/var/lib/ecg-gcloud HOME=/root DOCKER_CONFIG=/root/.docker
install -d -m 0700 /root/.docker
REGISTRY_HOST="${BACKEND_IMAGE%%/*}"
retry 8 2 gcloud auth configure-docker "${REGISTRY_HOST}" --quiet
/bin/bash /usr/local/lib/ecg-deploy/ensure-metadata-firewall.sh
/bin/bash /usr/local/lib/ecg-deploy/render-runtime-env.sh
/bin/bash /usr/local/lib/ecg-deploy/hydrate-corpus.sh \
  "${CORPUS_URI}" "${CORPUS_RELEASE}" "${CORPUS_SHA}" "${DATA_MOUNT}"

printf 'ECG_BACKEND_IMAGE=%s\n' "${BACKEND_IMAGE}" >/etc/ecg/image.env
chmod 0600 /etc/ecg/image.env
ECG_BACKEND_DOMAIN="${BACKEND_DOMAIN}" ECG_ACME_EMAIL="${ACME_EMAIL}" \
  caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
systemctl daemon-reload
systemctl enable ecg-backend.service caddy.service ecg-metadata-firewall.timer ecg-sqlite-backup.timer
systemctl restart ecg-backend.service
systemctl restart caddy.service
systemctl start ecg-sqlite-backup.service
systemctl start ecg-metadata-firewall.timer ecg-sqlite-backup.timer

wait_ready 240 || die "backend failed the post-install readiness gate"
prune_docker_cache 720h
log "host installation complete"
