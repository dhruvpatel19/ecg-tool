resource "google_service_account" "github_actions_publisher" {
  count = var.enable_github_actions_publisher ? 1 : 0

  project      = var.project_id
  account_id   = "${substr(var.name_prefix, 0, 16)}-gha-publisher"
  display_name = "TRACE ECG GitHub image publisher"
  description  = "OIDC-only identity that can write backend images to the one TRACE Artifact Registry repository."

  depends_on = [google_project_service.required]
}

resource "google_iam_workload_identity_pool" "github_actions" {
  count = var.enable_github_actions_publisher ? 1 : 0

  project                   = var.project_id
  workload_identity_pool_id = "${substr(var.name_prefix, 0, 16)}-github-actions"
  display_name              = "TRACE GitHub Actions"
  description               = "Federation pool restricted to the reviewed TRACE backend-image workflow repository and release refs."

  depends_on = [google_project_service.required]
}

resource "google_iam_workload_identity_pool_provider" "github_actions" {
  count = var.enable_github_actions_publisher ? 1 : 0

  project                            = var.project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.github_actions[0].workload_identity_pool_id
  workload_identity_pool_provider_id = "github"
  display_name                       = "TRACE GitHub OIDC"
  description                        = "Accepts only dhruvpatel19/ecg-tool tokens from main or release/* refs."

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
  }
  attribute_condition = "assertion.repository == '${var.github_actions_repository}' && (assertion.ref == 'refs/heads/main' || assertion.ref.startsWith('refs/heads/release/'))"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account_iam_member" "github_actions_workload_identity_user" {
  count = var.enable_github_actions_publisher ? 1 : 0

  service_account_id = google_service_account.github_actions_publisher[0].name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github_actions[0].name}/attribute.repository/${var.github_actions_repository}"

  depends_on = [google_iam_workload_identity_pool_provider.github_actions]
}

resource "google_artifact_registry_repository_iam_member" "github_actions_backend_writer" {
  count = var.enable_github_actions_publisher ? 1 : 0

  project    = var.project_id
  location   = google_artifact_registry_repository.backend.location
  repository = google_artifact_registry_repository.backend.repository_id
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.github_actions_publisher[0].email}"

  lifecycle {
    precondition {
      condition     = var.artifact_repository_id == "ecg-tool-backend"
      error_message = "The GitHub publisher is release-locked to the ecg-tool-backend Artifact Registry repository."
    }
  }
}
