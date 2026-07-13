resource "google_storage_bucket" "corpus" {
  name                        = var.corpus_bucket_name
  project                     = var.project_id
  location                    = var.region
  storage_class               = "STANDARD"
  force_destroy               = false
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  versioning {
    enabled = true
  }

  retention_policy {
    retention_period = var.bucket_retention_seconds
    is_locked        = false
  }

  soft_delete_policy {
    retention_duration_seconds = var.bucket_soft_delete_seconds
  }

  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      days_since_noncurrent_time = var.corpus_noncurrent_generation_retention_days
      with_state                 = "ARCHIVED"
    }
  }

  lifecycle {
    prevent_destroy = true
  }

  depends_on = [google_project_service.required]
}

resource "google_storage_bucket" "backup" {
  name                        = var.backup_bucket_name
  project                     = var.project_id
  location                    = var.region
  storage_class               = "STANDARD"
  force_destroy               = false
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  versioning {
    enabled = true
  }

  retention_policy {
    retention_period = var.bucket_retention_seconds
    is_locked        = false
  }

  soft_delete_policy {
    retention_duration_seconds = var.bucket_soft_delete_seconds
  }

  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      age        = var.backup_retention_days
      with_state = "ANY"
    }
  }

  lifecycle {
    prevent_destroy = true
  }

  depends_on = [google_project_service.required]
}

resource "google_artifact_registry_repository" "backend" {
  project       = var.project_id
  location      = var.region
  repository_id = var.artifact_repository_id
  description   = "Private immutable backend images for TRACE ECG"
  format        = "DOCKER"
  mode          = "STANDARD_REPOSITORY"

  docker_config {
    # Deployments accept only content digests. Disposable unique build tags stay
    # mutable at the service level so reviewed cleanup policies can remove old
    # artifacts; build-backend-image.sh never intentionally reuses a tag.
    immutable_tags = false
  }

  cleanup_policies {
    id     = "delete-old-images"
    action = "DELETE"

    condition {
      tag_state  = "ANY"
      older_than = "${var.artifact_delete_after_days * 86400}s"
    }
  }

  cleanup_policies {
    id     = "keep-recent-images"
    action = "KEEP"

    most_recent_versions {
      keep_count = var.artifact_keep_recent_count
    }
  }

  dynamic "cleanup_policies" {
    for_each = length(local.protected_backend_digests) > 0 ? [true] : []

    content {
      id     = "keep-pinned-deployment-images"
      action = "KEEP"

      condition {
        tag_state             = "ANY"
        version_name_prefixes = local.protected_backend_digests
      }
    }
  }

  lifecycle {
    prevent_destroy = true
  }

  depends_on = [google_project_service.required]
}

resource "google_secret_manager_secret" "runtime" {
  for_each = local.runtime_secrets

  project             = var.project_id
  secret_id           = each.value
  deletion_protection = var.secret_deletion_protection

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }

  depends_on = [google_project_service.required]
}
