resource "google_compute_disk" "data" {
  project                   = var.project_id
  name                      = "${var.name_prefix}-${var.environment}-data"
  zone                      = var.zone
  type                      = var.data_disk_type
  size                      = var.data_disk_size_gb
  physical_block_size_bytes = 4096
  description               = "Durable TRACE ECG corpus, learner database, and runtime state"

  lifecycle {
    prevent_destroy = true

    precondition {
      condition     = startswith(var.zone, "${var.region}-")
      error_message = "zone must belong to region."
    }

  }

  depends_on = [google_project_service.required]
}

resource "google_compute_resource_policy" "data_snapshots" {
  project = var.project_id
  name    = "${var.name_prefix}-${var.environment}-daily-snapshots"
  region  = var.region

  snapshot_schedule_policy {
    schedule {
      daily_schedule {
        days_in_cycle = 1
        start_time    = var.snapshot_start_time
      }
    }

    retention_policy {
      max_retention_days    = var.snapshot_retention_days
      on_source_disk_delete = "KEEP_AUTO_SNAPSHOTS"
    }

    snapshot_properties {
      # SQLite GCS backups are application-consistent. Scheduled disk snapshots
      # are explicitly crash-consistent because no guest-flush hooks are used.
      guest_flush       = false
      storage_locations = [var.region]
      labels            = local.labels
    }
  }

  depends_on = [google_project_service.required]
}

resource "google_compute_disk_resource_policy_attachment" "data_snapshots" {
  project = var.project_id
  name    = google_compute_resource_policy.data_snapshots.name
  disk    = google_compute_disk.data.name
  zone    = var.zone
}

resource "google_compute_instance" "app" {
  count = var.provision_instance ? 1 : 0

  project                   = var.project_id
  name                      = "${var.name_prefix}-${var.environment}"
  zone                      = var.zone
  machine_type              = var.machine_type
  can_ip_forward            = false
  allow_stopping_for_update = true
  deletion_protection       = var.instance_deletion_protection

  boot_disk {
    auto_delete = true

    initialize_params {
      image = var.source_image
      size  = var.boot_disk_size_gb
      type  = var.boot_disk_type
      labels = merge(local.labels, {
        data-class = "ephemeral"
      })
    }
  }

  attached_disk {
    source      = google_compute_disk.data.id
    device_name = local.data_disk_device_name
    mode        = "READ_WRITE"
  }

  network_interface {
    subnetwork = google_compute_subnetwork.app.id
    stack_type = "IPV4_ONLY"

    access_config {
      nat_ip       = google_compute_address.web.address
      network_tier = "PREMIUM"
    }
  }

  service_account {
    email  = google_service_account.vm.email
    scopes = ["https://www.googleapis.com/auth/cloud-platform"]
  }

  scheduling {
    automatic_restart   = true
    on_host_maintenance = "MIGRATE"
    preemptible         = false
    provisioning_model  = "STANDARD"
  }

  shielded_instance_config {
    enable_secure_boot          = true
    enable_vtpm                 = true
    enable_integrity_monitoring = true
  }

  metadata = {
    enable-oslogin         = "TRUE"
    block-project-ssh-keys = "TRUE"
    serial-port-enable     = "FALSE"

    # Every value below is non-secret deployment configuration. Secret payloads
    # are fetched at runtime by the VM service account from Secret Manager.
    ecg-install-script-path           = var.startup_install_script_path
    ecg-runtime-config-path           = var.runtime_config_path
    ecg-backend-image                 = var.backend_image
    ecg-data-device                   = "/dev/disk/by-id/google-${local.data_disk_device_name}"
    ecg-data-mount                    = var.data_mount_path
    ecg-allow-disk-format             = tostring(var.allow_initial_disk_format)
    ecg-corpus-uri                    = "gs://${google_storage_bucket.corpus.name}/${var.corpus_object_name}#${var.corpus_object_generation}"
    ecg-corpus-sha256                 = var.corpus_archive_sha256
    ecg-backup-uri                    = "gs://${google_storage_bucket.backup.name}/${local.backup_object_prefix}/"
    ecg-auth-secret                   = google_secret_manager_secret.runtime["auth_rate_limit"].secret_id
    ecg-origin-secret                 = google_secret_manager_secret.runtime["origin_shared"].secret_id
    ecg-llm-secret                    = var.enable_llm_secret ? google_secret_manager_secret.runtime["llm_api_key"].secret_id : ""
    ecg-environment                   = var.environment
    ecg-backend-domain                = var.health_check_host
    ecg-acme-email                    = var.acme_email
    ecg-llm-provider                  = var.llm_provider
    ecg-llm-model                     = var.llm_model
    ecg-llm-base-url                  = var.llm_base_url
    ecg-llm-required                  = tostring(var.llm_required)
    ecg-llm-max-completion-tokens     = tostring(var.llm_max_completion_tokens)
    ecg-llm-request-timeout-seconds   = tostring(var.llm_request_timeout_seconds)
    ecg-llm-max-request-bytes         = tostring(var.llm_max_request_bytes)
    ecg-llm-max-response-bytes        = tostring(var.llm_max_response_bytes)
    ecg-llm-authenticated-daily-limit = tostring(var.llm_authenticated_daily_limit)
    ecg-llm-guest-daily-limit         = tostring(var.llm_guest_daily_limit)
    ecg-llm-ip-hourly-limit           = tostring(var.llm_ip_hourly_limit)
    ecg-llm-global-daily-limit        = tostring(var.llm_global_daily_limit)
    ecg-backup-max-age-seconds        = tostring(var.backup_max_age_seconds)
    ecg-min-state-free-bytes          = tostring(var.min_state_free_bytes)
    ecg-backend-memory-limit-mb       = tostring(var.backend_memory_limit_mb)
    ecg-backend-memory-reservation-mb = tostring(var.backend_memory_reservation_mb)
    ecg-backend-cpu-limit             = tostring(var.backend_cpu_limit)
    ecg-runtime-assets                = local.runtime_asset_bundle

    startup-script = file("${path.module}/startup.sh.tftpl")
  }

  lifecycle {
    precondition {
      condition     = startswith(var.zone, "${var.region}-")
      error_message = "zone must belong to region."
    }

    precondition {
      condition     = can(regex("^projects/debian-cloud/global/images/debian-12-bookworm-v[0-9]{8}$", var.source_image))
      error_message = "source_image must be a concrete date-versioned Debian 12 image (family aliases are rejected)."
    }

    precondition {
      condition     = can(regex("@sha256:[0-9a-f]{64}$", var.backend_image))
      error_message = "backend_image must be an immutable lowercase sha256 digest reference, not a tag."
    }

    precondition {
      condition     = var.backend_memory_reservation_mb <= var.backend_memory_limit_mb
      error_message = "backend_memory_reservation_mb must not exceed backend_memory_limit_mb."
    }

    precondition {
      condition     = startswith(var.backend_image, "${local.backend_repository_url}/")
      error_message = "backend_image must come from the Artifact Registry repository created by this module."
    }

    precondition {
      condition     = can(regex("^[0-9]+$", var.corpus_object_generation))
      error_message = "corpus_object_generation must pin the uploaded release object's numeric generation."
    }

    precondition {
      condition     = can(regex("^[0-9a-f]{64}$", var.corpus_archive_sha256))
      error_message = "corpus_archive_sha256 must be the release archive's lowercase SHA-256."
    }

    precondition {
      condition     = startswith(var.startup_install_script_path, "/") && startswith(var.runtime_config_path, "/") && startswith(var.data_mount_path, "/")
      error_message = "startup_install_script_path, runtime_config_path, and data_mount_path must be absolute paths."
    }

    precondition {
      condition     = !(var.health_check_use_ssl && var.health_check_validate_ssl && var.health_check_host == "")
      error_message = "Set health_check_host before enabling TLS certificate validation."
    }

    precondition {
      condition     = var.health_check_host != "" && var.acme_email != ""
      error_message = "A backend DNS hostname and ACME contact email are required before provisioning the HTTPS VM."
    }

    precondition {
      condition     = var.environment != "production" || (var.health_check_use_ssl && var.health_check_validate_ssl)
      error_message = "Production requires an HTTPS uptime check with certificate validation enabled."
    }

    precondition {
      condition     = var.environment != "production" || length(var.alert_notification_channels) > 0
      error_message = "Production requires at least one reviewed Cloud Monitoring notification channel."
    }

    precondition {
      condition     = length(local.runtime_asset_bundle) < 240000
      error_message = "The compressed runtime asset bundle exceeds the Compute Engine metadata value limit."
    }

    precondition {
      condition     = var.llm_provider == "mock" || var.enable_llm_secret
      error_message = "A non-mock llm_provider requires enable_llm_secret=true and a populated secret version."
    }

    precondition {
      condition = !var.llm_required || (
        var.llm_provider == "openai-compatible" &&
        var.enable_llm_secret &&
        trimspace(var.llm_model) != "" &&
        trimspace(var.llm_base_url) != ""
      )
      error_message = "llm_required=true requires openai-compatible, enable_llm_secret=true, and non-empty llm_model/HTTPS llm_base_url values."
    }

    precondition {
      condition     = var.environment != "production" || var.llm_required
      error_message = "Production requires the live grounded tutor readiness dependency (llm_required=true)."
    }

    precondition {
      condition     = var.environment != "production" || length(trimspace(var.corpus_inventory_review_reference)) >= 8
      error_message = "Production requires an auditable corpus inventory/cleanup review reference that protects the pinned object generation."
    }
  }

  depends_on = [
    google_artifact_registry_repository_iam_member.backend_reader,
    google_compute_disk_resource_policy_attachment.data_snapshots,
    google_secret_manager_secret_iam_member.runtime_accessor,
    google_storage_bucket_iam_member.backup_prefix_creator,
    google_storage_bucket_iam_member.backup_prefix_reader,
    google_storage_bucket_iam_member.corpus_exact_object_reader,
  ]
}
