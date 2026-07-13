terraform {
  required_version = ">= 1.6.0, < 2.0.0"

  # Deliberately has no local fallback. Supply an approved, pre-created GCS
  # backend config during init; see backend.hcl.example.
  backend "gcs" {}

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 7.30"
    }
  }
}
