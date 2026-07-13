resource "google_service_account" "vm" {
  project      = var.project_id
  account_id   = "${substr(var.name_prefix, 0, 19)}-vm"
  display_name = "TRACE ECG application VM"
  description  = "Runtime identity with only corpus-read, backup-create/read, image-pull, and scoped secret-read permissions."

  depends_on = [google_project_service.required]
}

resource "google_storage_bucket_iam_member" "corpus_exact_object_reader" {
  bucket = google_storage_bucket.corpus.name
  role   = "roles/storage.objectViewer"
  member = local.service_account_member

  condition {
    title       = "read_exact_versioned_corpus_object"
    description = "Restrict the VM to the configured release object; the startup config pins its generation."
    expression  = "resource.type == \"storage.googleapis.com/Object\" && resource.name == \"${local.corpus_object_resource}\""
  }
}

resource "google_storage_bucket_iam_member" "backup_prefix_creator" {
  bucket = google_storage_bucket.backup.name
  role   = "roles/storage.objectCreator"
  member = local.service_account_member

  condition {
    title       = "append_only_learner_backups"
    description = "Allow new backup objects only under the application prefix; no read, overwrite, or delete."
    expression  = "resource.type == \"storage.googleapis.com/Object\" && resource.name.startsWith(\"${local.backup_object_resource}\")"
  }
}

# Restore is an explicit IAP-admin operation, but the VM still needs object-get
# permission on the selected backup. It cannot overwrite or delete objects.
resource "google_storage_bucket_iam_member" "backup_prefix_reader" {
  bucket = google_storage_bucket.backup.name
  role   = "roles/storage.objectViewer"
  member = local.service_account_member

  condition {
    title       = "read_learner_backups_for_restore"
    description = "Read only application backups under the dedicated prefix."
    expression  = "resource.type == \"storage.googleapis.com/Object\" && resource.name.startsWith(\"${local.backup_object_resource}\")"
  }
}

# Cloud Storage authorizes object listing against the bucket resource, so the
# object-name condition above cannot grant storage.objects.list. The backup
# script needs list only because `gcloud storage cp --if-generation-match=0`
# checks the append-only destination before upload. Scope this bucket-level
# permission to the dedicated backup bucket; object reads remain constrained to
# the application prefix by backup_prefix_reader.
resource "google_storage_bucket_iam_member" "backup_bucket_lister" {
  bucket = google_storage_bucket.backup.name
  role   = "roles/storage.legacyBucketReader"
  member = local.service_account_member
}

resource "google_artifact_registry_repository_iam_member" "backend_reader" {
  project    = var.project_id
  location   = google_artifact_registry_repository.backend.location
  repository = google_artifact_registry_repository.backend.repository_id
  role       = "roles/artifactregistry.reader"
  member     = local.service_account_member
}

resource "google_secret_manager_secret_iam_member" "runtime_accessor" {
  for_each = google_secret_manager_secret.runtime

  project   = var.project_id
  secret_id = each.value.id
  role      = "roles/secretmanager.secretAccessor"
  member    = local.service_account_member
}

# IAP is intentionally granted on the one instance, not project-wide. OS Login
# itself is a project-level role in Google Cloud. Operators still need ordinary
# read access to discover the instance (typically inherited from an admin group).
resource "google_iap_tunnel_instance_iam_member" "ssh" {
  for_each = var.provision_instance ? var.iap_ssh_members : toset([])

  project  = var.project_id
  zone     = var.zone
  instance = google_compute_instance.app[0].name
  role     = "roles/iap.tunnelResourceAccessor"
  member   = each.value
}

resource "google_project_iam_member" "os_admin_login" {
  for_each = var.provision_instance ? var.iap_ssh_members : toset([])

  project = var.project_id
  role    = "roles/compute.osAdminLogin"
  member  = each.value
}

# OS Login checks iam.serviceAccounts.actAs whenever the VM has an attached
# service account. Scope that permission to this one runtime identity.
resource "google_service_account_iam_member" "iap_ssh_act_as" {
  for_each = var.provision_instance ? var.iap_ssh_members : toset([])

  service_account_id = google_service_account.vm.name
  role               = "roles/iam.serviceAccountUser"
  member             = each.value
}
