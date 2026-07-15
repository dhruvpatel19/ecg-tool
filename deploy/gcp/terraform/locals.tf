locals {
  labels = merge(
    {
      app         = "ecg-tool"
      environment = var.environment
      managed-by  = "terraform"
    },
    var.labels,
  )

  service_account_member = "serviceAccount:${google_service_account.vm.email}"
  data_disk_device_name  = "ecg-data"
  backup_object_prefix   = trim(var.backup_object_prefix, "/")
  corpus_object_resource = "projects/_/buckets/${google_storage_bucket.corpus.name}/objects/${var.corpus_object_name}"
  backup_object_resource = "projects/_/buckets/${google_storage_bucket.backup.name}/objects/${local.backup_object_prefix}/"
  backend_repository_url = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.backend.repository_id}"
  backend_image_digest   = try(split("@", var.backend_image)[1], "")
  protected_backend_digests = distinct(compact(concat(
    [local.backend_image_digest],
    var.artifact_recovery_image_digests,
  )))
  # Artifact Registry limits cleanup-policy version-name prefixes to 64
  # characters, while a Docker version name is `sha256:` plus 64 hex digits.
  # Retain the scheme and first 57 digest digits so the prefix matches the
  # intended version with 228 bits of collision resistance.
  protected_backend_version_prefixes = [
    for digest in local.protected_backend_digests : substr(digest, 0, min(length(digest), 64))
  ]

  # Reviewed host assets are compressed into non-secret instance metadata and
  # staged locally by the startup shim. The VM never clones a repository or
  # downloads executable deployment code.
  runtime_assets = {
    "scripts/install-host.sh"               = base64encode(file("${path.module}/../scripts/install-host.sh"))
    "scripts/lib.sh"                        = base64encode(file("${path.module}/../scripts/lib.sh"))
    "scripts/hydrate-corpus.sh"             = base64encode(file("${path.module}/../scripts/hydrate-corpus.sh"))
    "scripts/render-runtime-env.sh"         = base64encode(file("${path.module}/../scripts/render-runtime-env.sh"))
    "scripts/backup-sqlite.sh"              = base64encode(file("${path.module}/../scripts/backup-sqlite.sh"))
    "scripts/restore-sqlite.sh"             = base64encode(file("${path.module}/../scripts/restore-sqlite.sh"))
    "scripts/install-release.sh"            = base64encode(file("${path.module}/../scripts/install-release.sh"))
    "scripts/ensure-metadata-firewall.sh"   = base64encode(file("${path.module}/../scripts/ensure-metadata-firewall.sh"))
    "systemd/ecg-backend.service"           = base64encode(file("${path.module}/../systemd/ecg-backend.service"))
    "systemd/ecg-metadata-firewall.service" = base64encode(file("${path.module}/../systemd/ecg-metadata-firewall.service"))
    "systemd/ecg-metadata-firewall.timer"   = base64encode(file("${path.module}/../systemd/ecg-metadata-firewall.timer"))
    "systemd/ecg-sqlite-backup.service"     = base64encode(file("${path.module}/../systemd/ecg-sqlite-backup.service"))
    "systemd/ecg-sqlite-backup.timer"       = base64encode(file("${path.module}/../systemd/ecg-sqlite-backup.timer"))
    "caddy/Caddyfile"                       = base64encode(file("${path.module}/../caddy/Caddyfile"))
  }
  # Keep the terminal newline: the startup shim streams this manifest through
  # Bash `read`, which otherwise omits the final asset record.
  runtime_asset_records = "${join("\n", [
    for path, payload in local.runtime_assets : "${path}\t${payload}"
  ])}\n"
  runtime_asset_bundle = base64gzip(local.runtime_asset_records)

  runtime_secrets = merge(
    {
      auth_rate_limit = var.auth_rate_limit_secret_id
      origin_shared   = var.origin_shared_secret_id
    },
    var.auth_email_delivery_mode == "smtp" ? {
      auth_smtp_password = var.auth_smtp_password_secret_id
    } : {},
    var.enable_llm_secret ? { llm_api_key = var.llm_api_key_secret_id } : {},
  )

  health_check_host = var.health_check_host != "" ? var.health_check_host : google_compute_address.web.address
}
