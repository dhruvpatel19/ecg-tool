resource "google_monitoring_uptime_check_config" "app" {
  count = var.provision_instance ? 1 : 0

  project            = var.project_id
  display_name       = "${var.name_prefix}-${var.environment}-health"
  timeout            = "10s"
  period             = var.health_check_period
  checker_type       = "STATIC_IP_CHECKERS"
  log_check_failures = true

  http_check {
    path           = var.health_check_path
    port           = var.health_check_use_ssl ? 443 : 80
    use_ssl        = var.health_check_use_ssl
    validate_ssl   = var.health_check_validate_ssl
    request_method = "GET"
  }

  monitored_resource {
    type = "uptime_url"
    labels = {
      project_id = var.project_id
      host       = local.health_check_host
    }
  }

  content_matchers {
    content = "\"ok\":true"
    matcher = "CONTAINS_STRING"
  }

  user_labels = local.labels

  depends_on = [google_compute_instance.app]
}

resource "google_monitoring_alert_policy" "app_unhealthy" {
  count = var.provision_instance ? 1 : 0

  project               = var.project_id
  display_name          = "${var.name_prefix}-${var.environment} health check failing"
  combiner              = "OR"
  enabled               = true
  notification_channels = var.alert_notification_channels

  documentation {
    content   = "The public TRACE ECG /readyz endpoint has failed for at least two minutes. Check the VM startup log, reverse proxy, backend systemd unit, persistent-disk mount, learner database, and exact corpus generation."
    mime_type = "text/markdown"
  }

  conditions {
    display_name = "Uptime probes are failing"

    condition_threshold {
      filter          = "resource.type = \"uptime_url\" AND metric.type = \"monitoring.googleapis.com/uptime_check/check_passed\" AND metric.label.check_id = \"${google_monitoring_uptime_check_config.app[0].uptime_check_id}\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "120s"

      aggregations {
        alignment_period     = "60s"
        per_series_aligner   = "ALIGN_NEXT_OLDER"
        cross_series_reducer = "REDUCE_COUNT_FALSE"
        group_by_fields      = ["resource.label.host"]
      }

      trigger {
        count = 1
      }
    }
  }

  user_labels = local.labels
}
