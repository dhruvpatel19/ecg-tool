provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone

  # Required by the Cloud Billing Budget API when an operator uses user ADCs.
  billing_project       = var.project_id
  user_project_override = true

  default_labels = local.labels
}
