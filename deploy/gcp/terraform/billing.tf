data "google_project" "current" {
  project_id = var.project_id

  depends_on = [google_project_service.required]
}

resource "google_billing_budget" "project" {
  billing_account = "billingAccounts/${var.billing_account_id}"
  display_name    = "${var.name_prefix}-${var.environment}-monthly"

  budget_filter {
    projects = ["projects/${data.google_project.current.number}"]
  }

  amount {
    specified_amount {
      currency_code = "USD"
      units         = tostring(var.monthly_budget_usd)
    }
  }

  threshold_rules {
    threshold_percent = 0.5
  }

  threshold_rules {
    threshold_percent = 0.8
  }

  threshold_rules {
    threshold_percent = 1.0
  }

  threshold_rules {
    threshold_percent = 1.0
    spend_basis       = "FORECASTED_SPEND"
  }

  all_updates_rule {
    monitoring_notification_channels = var.alert_notification_channels
    disable_default_iam_recipients   = false
    enable_project_level_recipients  = true
  }

  lifecycle {
    prevent_destroy = true
  }

  depends_on = [google_project_service.required]
}
