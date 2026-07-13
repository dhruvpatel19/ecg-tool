resource "google_compute_network" "app" {
  project                 = var.project_id
  name                    = "${var.name_prefix}-${var.environment}"
  auto_create_subnetworks = false
  routing_mode            = "REGIONAL"

  depends_on = [google_project_service.required]
}

resource "google_compute_subnetwork" "app" {
  project                  = var.project_id
  name                     = "${var.name_prefix}-${var.environment}-${var.region}"
  region                   = var.region
  network                  = google_compute_network.app.id
  ip_cidr_range            = var.network_cidr
  private_ip_google_access = true

  log_config {
    aggregation_interval = "INTERVAL_10_MIN"
    flow_sampling        = 0.5
    metadata             = "INCLUDE_ALL_METADATA"
  }
}

resource "google_compute_address" "web" {
  project      = var.project_id
  name         = "${var.name_prefix}-${var.environment}-web"
  region       = var.region
  address_type = "EXTERNAL"
  network_tier = "PREMIUM"

  depends_on = [google_project_service.required]
}

# Public ingress reaches only the reverse proxy. Backend/database/container
# ports are never opened by this module.
resource "google_compute_firewall" "public_web" {
  project   = var.project_id
  name      = "${var.name_prefix}-${var.environment}-public-web"
  network   = google_compute_network.app.name
  direction = "INGRESS"
  priority  = 1000

  source_ranges           = ["0.0.0.0/0"]
  target_service_accounts = [google_service_account.vm.email]

  allow {
    protocol = "tcp"
    ports    = ["80", "443"]
  }

  log_config {
    metadata = "INCLUDE_ALL_METADATA"
  }
}
# Google documents 35.235.240.0/20 as the IAP TCP-forwarding source range.
# There is deliberately no general public SSH rule.
resource "google_compute_firewall" "iap_ssh" {
  project   = var.project_id
  name      = "${var.name_prefix}-${var.environment}-iap-ssh"
  network   = google_compute_network.app.name
  direction = "INGRESS"
  priority  = 1000

  source_ranges           = ["35.235.240.0/20"]
  target_service_accounts = [google_service_account.vm.email]

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  log_config {
    metadata = "INCLUDE_ALL_METADATA"
  }
}
