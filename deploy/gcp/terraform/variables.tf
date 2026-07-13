variable "project_id" {
  description = "GCP project that will own the deployment resources."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.project_id))
    error_message = "project_id must be a valid GCP project ID."
  }
}

variable "region" {
  description = "Single GCP region for compute, disks, buckets, registry, and secrets."
  type        = string
  default     = "us-east1"
}

variable "zone" {
  description = "Compute zone within region."
  type        = string
  default     = "us-east1-b"
}

variable "name_prefix" {
  description = "Lowercase prefix used for regional resource names."
  type        = string
  default     = "ecg-tool"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,27}$", var.name_prefix))
    error_message = "name_prefix must be 3-28 lowercase letters, digits, or hyphens and start with a letter."
  }
}

variable "environment" {
  description = "Deployment environment label."
  type        = string
  default     = "demo"

  validation {
    condition     = contains(["demo", "staging", "production"], var.environment)
    error_message = "environment must be demo, staging, or production."
  }
}

variable "labels" {
  description = "Additional labels applied through the Google provider."
  type        = map(string)
  default     = {}
}

variable "billing_acknowledged" {
  description = "Explicit cost gate. No foundation plan/apply proceeds until an operator accepts that disks, static IPs, storage, logging, and compute can incur charges."
  type        = bool
  default     = false
}

variable "billing_account_id" {
  description = "Cloud Billing account ID used for the Terraform-managed project-scoped budget (format 000000-000000-000000)."
  type        = string
  default     = ""

  validation {
    condition     = var.billing_account_id == "" || can(regex("^[0-9A-F]{6}-[0-9A-F]{6}-[0-9A-F]{6}$", var.billing_account_id))
    error_message = "billing_account_id must use 000000-000000-000000 format."
  }
}

variable "monthly_budget_usd" {
  description = "Project-scoped monthly Cloud Billing budget in USD. Budgets alert but do not hard-cap spend."
  type        = number
  default     = 100

  validation {
    condition     = var.monthly_budget_usd == floor(var.monthly_budget_usd) && var.monthly_budget_usd >= 10 && var.monthly_budget_usd <= 100000
    error_message = "monthly_budget_usd must be a whole-dollar value from 10 through 100000."
  }
}

variable "vercel_spend_limit_reference" {
  description = "Auditable ticket/URL/reference proving Vercel spend controls were reviewed and configured."
  type        = string
  default     = ""
}

variable "llm_spend_limit_reference" {
  description = "Auditable provider project/limit reference proving an independent LLM spend cap was configured."
  type        = string
  default     = ""
}

variable "provision_instance" {
  description = "Explicit release gate. Leave false while uploading the corpus/image and adding secret versions; set true only when every runtime prerequisite is ready."
  type        = bool
  default     = false
}

variable "network_cidr" {
  description = "Private IPv4 CIDR for the dedicated regional subnet."
  type        = string
  default     = "10.40.0.0/24"

  validation {
    condition     = can(cidrhost(var.network_cidr, 1))
    error_message = "network_cidr must be a valid IPv4 CIDR."
  }
}

variable "machine_type" {
  description = "GCE machine type for the single application VM."
  type        = string
  default     = "e2-small"
}

variable "backend_memory_limit_mb" {
  description = "Hard Docker memory ceiling for the backend container in MiB."
  type        = number
  default     = 1536

  validation {
    condition     = var.backend_memory_limit_mb == floor(var.backend_memory_limit_mb) && var.backend_memory_limit_mb >= 512 && var.backend_memory_limit_mb <= 65536
    error_message = "backend_memory_limit_mb must be an integer from 512 through 65536."
  }
}

variable "backend_memory_reservation_mb" {
  description = "Soft Docker memory reservation for the backend container in MiB; must not exceed the hard limit."
  type        = number
  default     = 1024

  validation {
    condition     = var.backend_memory_reservation_mb == floor(var.backend_memory_reservation_mb) && var.backend_memory_reservation_mb >= 256 && var.backend_memory_reservation_mb <= 65536
    error_message = "backend_memory_reservation_mb must be an integer from 256 through 65536."
  }
}

variable "backend_cpu_limit" {
  description = "Hard Docker CPU quota expressed as logical CPUs."
  type        = number
  default     = 1.5

  validation {
    condition     = var.backend_cpu_limit >= 0.25 && var.backend_cpu_limit <= 64
    error_message = "backend_cpu_limit must be from 0.25 through 64 logical CPUs."
  }
}

variable "source_image" {
  description = "Concrete, date-versioned Debian 12 boot image resource path. Image-family aliases are rejected when provisioning."
  type        = string
  default     = ""
}

variable "boot_disk_size_gb" {
  description = "Ephemeral boot disk size in GiB. Learner state and corpus data do not belong on this disk."
  type        = number
  default     = 20

  validation {
    condition     = var.boot_disk_size_gb >= 20
    error_message = "boot_disk_size_gb must be at least 20 GiB."
  }
}

variable "boot_disk_type" {
  description = "Ephemeral boot-disk Persistent Disk type."
  type        = string
  default     = "pd-standard"

  validation {
    condition     = contains(["pd-balanced", "pd-ssd", "pd-standard"], var.boot_disk_type)
    error_message = "boot_disk_type must be pd-balanced, pd-ssd, or pd-standard."
  }
}

variable "data_disk_size_gb" {
  description = "Dedicated persistent disk size in GiB for the hydrated corpus, SQLite learner database, and runtime state."
  type        = number
  default     = 20

  validation {
    condition     = var.data_disk_size_gb >= 20
    error_message = "data_disk_size_gb must be at least 20 GiB."
  }
}

variable "data_disk_type" {
  description = "Persistent disk type."
  type        = string
  default     = "pd-standard"

  validation {
    condition     = contains(["pd-balanced", "pd-ssd", "pd-standard"], var.data_disk_type)
    error_message = "data_disk_type must be pd-balanced, pd-ssd, or pd-standard."
  }
}

variable "data_mount_path" {
  description = "Absolute mount path managed by the external install script."
  type        = string
  default     = "/srv/ecg-data"
}

variable "allow_initial_disk_format" {
  description = "Explicitly authorize formatting only an attached disk with no filesystem, signatures, or partitions. Set true for the first boot of this Terraform-created disk."
  type        = bool
  default     = false
}

variable "instance_deletion_protection" {
  description = "Protect the VM from accidental deletion. Disable explicitly before an intentional destroy."
  type        = bool
  default     = true
}

variable "snapshot_start_time" {
  description = "UTC start time for the daily data-disk snapshot schedule, in HH:MM."
  type        = string
  default     = "05:00"

  validation {
    condition     = can(regex("^(?:[01][0-9]|2[0-3]):[0-5][0-9]$", var.snapshot_start_time))
    error_message = "snapshot_start_time must use 24-hour UTC HH:MM format."
  }
}

variable "snapshot_retention_days" {
  description = "Number of days scheduled data-disk snapshots are retained."
  type        = number
  default     = 14

  validation {
    condition     = var.snapshot_retention_days >= 7 && var.snapshot_retention_days <= 365
    error_message = "snapshot_retention_days must be between 7 and 365."
  }
}

variable "corpus_bucket_name" {
  description = "Globally unique name for the Terraform-managed private, versioned release-corpus bucket. Do not point this at MIMIC."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9._-]{1,61}[a-z0-9]$", var.corpus_bucket_name))
    error_message = "corpus_bucket_name must be a valid globally unique Cloud Storage bucket name."
  }
}

variable "backup_bucket_name" {
  description = "Globally unique name for the Terraform-managed private, versioned learner-state backup bucket."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9._-]{1,61}[a-z0-9]$", var.backup_bucket_name))
    error_message = "backup_bucket_name must be a valid globally unique Cloud Storage bucket name."
  }
}

variable "bucket_retention_seconds" {
  description = "Unlocked minimum object retention applied to corpus and backup buckets."
  type        = number
  default     = 2592000

  validation {
    condition     = var.bucket_retention_seconds >= 604800
    error_message = "bucket_retention_seconds must be at least seven days."
  }
}

variable "bucket_soft_delete_seconds" {
  description = "Cloud Storage soft-delete retention for both buckets (7-90 days)."
  type        = number
  default     = 604800

  validation {
    condition     = var.bucket_soft_delete_seconds >= 604800 && var.bucket_soft_delete_seconds <= 7776000
    error_message = "bucket_soft_delete_seconds must be between 604800 and 7776000 seconds."
  }
}

variable "corpus_noncurrent_generation_retention_days" {
  description = "Days to retain noncurrent corpus object generations. Live pinned releases are never age-deleted automatically."
  type        = number
  default     = 90

  validation {
    condition     = var.corpus_noncurrent_generation_retention_days == floor(var.corpus_noncurrent_generation_retention_days) && var.corpus_noncurrent_generation_retention_days >= 30 && var.corpus_noncurrent_generation_retention_days <= 365
    error_message = "corpus_noncurrent_generation_retention_days must be an integer from 30 through 365."
  }
}

variable "corpus_inventory_review_reference" {
  description = "Auditable review proving live corpus objects were inventoried and the pinned name/generation was excluded from manual cleanup. Required for production."
  type        = string
  default     = ""
}

variable "backup_retention_days" {
  description = "Online SQLite backup object retention/RPO history bound."
  type        = number
  default     = 90

  validation {
    condition     = var.backup_retention_days == floor(var.backup_retention_days) && var.backup_retention_days >= 30 && var.backup_retention_days <= 365
    error_message = "backup_retention_days must be an integer from 30 through 365."
  }
}

variable "artifact_delete_after_days" {
  description = "Artifact Registry images older than this are eligible for cleanup unless protected by the recent-version keep rule."
  type        = number
  default     = 90

  validation {
    condition     = var.artifact_delete_after_days == floor(var.artifact_delete_after_days) && var.artifact_delete_after_days >= 30 && var.artifact_delete_after_days <= 365
    error_message = "artifact_delete_after_days must be an integer from 30 through 365."
  }
}

variable "artifact_keep_recent_count" {
  description = "Minimum recent Artifact Registry image versions retained for rollback."
  type        = number
  default     = 10

  validation {
    condition     = var.artifact_keep_recent_count == floor(var.artifact_keep_recent_count) && var.artifact_keep_recent_count >= 3 && var.artifact_keep_recent_count <= 50
    error_message = "artifact_keep_recent_count must be an integer from 3 through 50."
  }
}

variable "artifact_recovery_image_digests" {
  description = "Additional exact backend sha256 digests retained by Artifact Registry cleanup for intentional rollback/recovery. The active backend_image digest is protected automatically."
  type        = list(string)
  default     = []

  validation {
    condition = alltrue([
      for digest in var.artifact_recovery_image_digests : can(regex("^sha256:[a-f0-9]{64}$", digest))
    ])
    error_message = "artifact_recovery_image_digests entries must be lowercase sha256 digests."
  }
}

variable "corpus_object_name" {
  description = "Exact object name of the release corpus archive. Upload is deliberately outside Terraform."
  type        = string
  default     = "releases/ecg-corpus.tar.zst"

  validation {
    condition     = can(regex("^[A-Za-z0-9][A-Za-z0-9._/-]+$", var.corpus_object_name)) && !endswith(var.corpus_object_name, "/")
    error_message = "corpus_object_name must be a non-directory Cloud Storage object path."
  }
}

variable "corpus_object_generation" {
  description = "Immutable numeric generation of the uploaded corpus object. Required when provision_instance=true."
  type        = string
  default     = ""
}

variable "corpus_archive_sha256" {
  description = "Expected lowercase SHA-256 of the corpus archive. Required when provision_instance=true."
  type        = string
  default     = ""
}

variable "backup_object_prefix" {
  description = "Object prefix to which the VM may append new backups."
  type        = string
  default     = "backups/ecg-tool"

  validation {
    condition     = can(regex("^[A-Za-z0-9][A-Za-z0-9._/-]*$", var.backup_object_prefix))
    error_message = "backup_object_prefix must be a safe Cloud Storage object prefix."
  }
}

variable "artifact_repository_id" {
  description = "Private Artifact Registry Docker repository ID. Terraform creates the repository but never uploads an image."
  type        = string
  default     = "ecg-tool-backend"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,62}$", var.artifact_repository_id))
    error_message = "artifact_repository_id must be 3-63 lowercase letters, digits, or hyphens."
  }
}

variable "backend_image" {
  description = "Immutable Artifact Registry backend image reference ending in @sha256:<64 hex>. Required when provision_instance=true; tags are rejected."
  type        = string
  default     = ""
}

variable "startup_install_script_path" {
  description = "Absolute path where the startup shim stages the Terraform-reviewed installer."
  type        = string
  default     = "/opt/ecg-tool/deploy/gcp/scripts/install-host.sh"
}

variable "runtime_config_path" {
  description = "Absolute root-only runtime environment file that the install script will materialize from metadata plus Secret Manager."
  type        = string
  default     = "/etc/ecg/deployment.env"
}

variable "acme_email" {
  description = "Operations contact used by Caddy for public ACME certificate issuance."
  type        = string
  default     = ""

  validation {
    condition     = var.acme_email == "" || can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", var.acme_email))
    error_message = "acme_email must be empty during foundation setup or a valid email address."
  }
}

variable "llm_provider" {
  description = "Runtime tutor provider. Production tutoring uses openai-compatible; mock is for deterministic non-production validation only."
  type        = string
  default     = "mock"

  validation {
    condition     = contains(["mock", "openai-compatible"], var.llm_provider)
    error_message = "llm_provider must be mock or openai-compatible."
  }
}

variable "llm_model" {
  description = "Optional runtime LLM model name."
  type        = string
  default     = ""
}

variable "llm_base_url" {
  description = "Optional OpenAI-compatible LLM base URL."
  type        = string
  default     = ""

  validation {
    condition     = var.llm_base_url == "" || can(regex("^https://", var.llm_base_url))
    error_message = "llm_base_url must be empty or use HTTPS."
  }
}

variable "llm_required" {
  description = "Make a configured remote AI tutor a readiness dependency. Set true for the showcase/production runtime."
  type        = bool
  default     = false
}

variable "llm_max_completion_tokens" {
  description = "Maximum completion-token budget for one remote tutor request."
  type        = number
  default     = 1200

  validation {
    condition     = var.llm_max_completion_tokens == floor(var.llm_max_completion_tokens) && var.llm_max_completion_tokens >= 128 && var.llm_max_completion_tokens <= 4096
    error_message = "llm_max_completion_tokens must be an integer from 128 through 4096."
  }
}

variable "llm_request_timeout_seconds" {
  description = "Remote tutor request deadline in seconds."
  type        = number
  default     = 30

  validation {
    condition     = var.llm_request_timeout_seconds == floor(var.llm_request_timeout_seconds) && var.llm_request_timeout_seconds >= 5 && var.llm_request_timeout_seconds <= 60
    error_message = "llm_request_timeout_seconds must be an integer from 5 through 60."
  }
}

variable "llm_max_request_bytes" {
  description = "Maximum serialized request body sent to the remote tutor provider."
  type        = number
  default     = 131072

  validation {
    condition     = var.llm_max_request_bytes == floor(var.llm_max_request_bytes) && var.llm_max_request_bytes >= 32768 && var.llm_max_request_bytes <= 524288
    error_message = "llm_max_request_bytes must be an integer from 32768 through 524288."
  }
}

variable "llm_max_response_bytes" {
  description = "Maximum response body accepted from the remote tutor provider."
  type        = number
  default     = 131072

  validation {
    condition     = var.llm_max_response_bytes == floor(var.llm_max_response_bytes) && var.llm_max_response_bytes >= 16384 && var.llm_max_response_bytes <= 1048576
    error_message = "llm_max_response_bytes must be an integer from 16384 through 1048576."
  }
}

variable "llm_authenticated_daily_limit" {
  description = "Per-authenticated-learner daily remote tutor reservation limit."
  type        = number
  default     = 60

  validation {
    condition     = var.llm_authenticated_daily_limit == floor(var.llm_authenticated_daily_limit) && var.llm_authenticated_daily_limit >= 1
    error_message = "llm_authenticated_daily_limit must be a positive integer."
  }
}

variable "llm_guest_daily_limit" {
  description = "Per-guest daily remote tutor reservation limit."
  type        = number
  default     = 15

  validation {
    condition     = var.llm_guest_daily_limit == floor(var.llm_guest_daily_limit) && var.llm_guest_daily_limit >= 1
    error_message = "llm_guest_daily_limit must be a positive integer."
  }
}

variable "llm_ip_hourly_limit" {
  description = "Privacy-preserving per-client-IP hourly remote tutor reservation limit."
  type        = number
  default     = 240

  validation {
    condition     = var.llm_ip_hourly_limit == floor(var.llm_ip_hourly_limit) && var.llm_ip_hourly_limit >= 1
    error_message = "llm_ip_hourly_limit must be a positive integer."
  }
}

variable "llm_global_daily_limit" {
  description = "Global daily remote tutor reservation limit for this single backend."
  type        = number
  default     = 500

  validation {
    condition     = var.llm_global_daily_limit == floor(var.llm_global_daily_limit) && var.llm_global_daily_limit >= 1
    error_message = "llm_global_daily_limit must be a positive integer."
  }
}

variable "backup_max_age_seconds" {
  description = "Maximum age of the last successful online SQLite backup before readiness fails. Must exceed two six-hour timer intervals."
  type        = number
  default     = 50400

  validation {
    condition     = var.backup_max_age_seconds == floor(var.backup_max_age_seconds) && var.backup_max_age_seconds >= 46800 && var.backup_max_age_seconds <= 604800
    error_message = "backup_max_age_seconds must be an integer from 46800 through 604800."
  }
}

variable "min_state_free_bytes" {
  description = "Minimum free bytes required on the persistent learner-state filesystem for readiness to pass."
  type        = number
  default     = 2147483648

  validation {
    condition     = var.min_state_free_bytes == floor(var.min_state_free_bytes) && var.min_state_free_bytes >= 268435456 && var.min_state_free_bytes <= 53687091200
    error_message = "min_state_free_bytes must be an integer from 256 MiB through 50 GiB."
  }
}

variable "auth_rate_limit_secret_id" {
  description = "Secret Manager container ID for AUTH_RATE_LIMIT_SECRET. Terraform creates no secret version."
  type        = string
  default     = "ecg-auth-rate-limit-secret"
}

variable "origin_shared_secret_id" {
  description = "Secret Manager container ID for ECG_ORIGIN_SHARED_SECRET. Terraform creates no secret version."
  type        = string
  default     = "ecg-origin-shared-secret"
}

variable "enable_llm_secret" {
  description = "Create an optional LLM API-key secret container and grant the VM scoped accessor."
  type        = bool
  default     = false
}

variable "llm_api_key_secret_id" {
  description = "Secret Manager container ID for the optional LLM API key. Terraform creates no secret version."
  type        = string
  default     = "ecg-llm-api-key"
}

variable "secret_deletion_protection" {
  description = "Protect runtime secret containers from accidental deletion."
  type        = bool
  default     = true
}

variable "health_check_host" {
  description = "Public backend DNS hostname used by Caddy and the readiness uptime check. Required before provision_instance=true."
  type        = string
  default     = ""
}

variable "health_check_path" {
  description = "Application health path exposed by the HTTPS/HTTP reverse proxy."
  type        = string
  default     = "/readyz"

  validation {
    condition     = startswith(var.health_check_path, "/")
    error_message = "health_check_path must start with /."
  }
}

variable "health_check_use_ssl" {
  description = "Use HTTPS for the external uptime check."
  type        = bool
  default     = true
}

variable "health_check_validate_ssl" {
  description = "Validate the TLS certificate. Enable after health_check_host DNS and the certificate are ready."
  type        = bool
  default     = false
}

variable "health_check_period" {
  description = "Cloud Monitoring uptime-check period."
  type        = string
  default     = "60s"

  validation {
    condition     = contains(["60s", "300s", "600s", "900s"], var.health_check_period)
    error_message = "health_check_period must be 60s, 300s, 600s, or 900s."
  }
}

variable "alert_notification_channels" {
  description = "Existing Cloud Monitoring notification-channel resource names. Empty still creates the alert policy without notifications."
  type        = list(string)
  default     = []
}

variable "iap_ssh_members" {
  description = "Optional user:/group: principals granted instance-scoped IAP tunneling plus OS Admin Login. Keep this list small."
  type        = set(string)
  default     = []

  validation {
    condition = alltrue([
      for member in var.iap_ssh_members : can(regex("^(user|group):[^@\\s]+@[^@\\s]+$", member))
    ])
    error_message = "iap_ssh_members entries must be user: or group: principals."
  }
}
