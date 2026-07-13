locals {
  required_services = toset([
    "artifactregistry.googleapis.com",
    "billingbudgets.googleapis.com",
    "compute.googleapis.com",
    "iap.googleapis.com",
    "iam.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "oslogin.googleapis.com",
    "secretmanager.googleapis.com",
    "storage.googleapis.com",
  ])
}

resource "terraform_data" "billing_approval" {
  input = {
    approved              = var.billing_acknowledged
    billing_account       = var.billing_account_id
    vercel_limit_evidence = var.vercel_spend_limit_reference
    llm_limit_evidence    = var.llm_spend_limit_reference
  }

  lifecycle {
    precondition {
      condition = (
        var.billing_acknowledged &&
        var.billing_account_id != "" &&
        length(trimspace(var.vercel_spend_limit_reference)) >= 8 &&
        length(trimspace(var.llm_spend_limit_reference)) >= 8
      )
      error_message = "Billing gate closed: acknowledge costs, provide a billing account for the managed GCP budget, and record auditable Vercel/LLM spend-limit references."
    }
  }
}

resource "google_project_service" "required" {
  for_each = local.required_services

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false

  depends_on = [terraform_data.billing_approval]
}
