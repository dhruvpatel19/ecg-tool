output "deployment_gate" {
  description = "Whether the application VM and health monitoring are currently enabled."
  value       = var.provision_instance
}

output "static_ip" {
  description = "Reserved public IPv4 address. Point the backend DNS A record here before enabling TLS validation."
  value       = google_compute_address.web.address
}

output "instance_name" {
  description = "Application VM name, or null while provision_instance=false."
  value       = try(google_compute_instance.app[0].name, null)
}

output "iap_ssh_command" {
  description = "IAP-only SSH command, or null while provision_instance=false."
  value       = var.provision_instance ? "gcloud compute ssh ${google_compute_instance.app[0].name} --project=${var.project_id} --zone=${var.zone} --tunnel-through-iap" : null
}

output "artifact_repository_url" {
  description = "Docker repository prefix. Push the backend outside Terraform, then set backend_image to its immutable digest."
  value       = local.backend_repository_url
}

output "corpus_bucket_uri" {
  description = "Private release-corpus bucket. Upload the archive outside Terraform."
  value       = "gs://${google_storage_bucket.corpus.name}"
}

output "configured_corpus_uri" {
  description = "Generation-pinned corpus URI, or null until a generation is configured."
  value       = var.corpus_object_generation != "" ? "gs://${google_storage_bucket.corpus.name}/${var.corpus_object_name}#${var.corpus_object_generation}" : null
}

output "backup_prefix_uri" {
  description = "Append-only backup destination visible to the VM service account."
  value       = "gs://${google_storage_bucket.backup.name}/${local.backup_object_prefix}/"
}

output "runtime_secret_resources" {
  description = "Secret container resource names only. Values/versions are never managed by this Terraform package."
  value = {
    for key, secret in google_secret_manager_secret.runtime : key => secret.id
  }
}

output "health_check_url" {
  description = "Monitored health URL, or null while provision_instance=false."
  value       = var.provision_instance ? format("%s://%s%s", var.health_check_use_ssl ? "https" : "http", local.health_check_host, var.health_check_path) : null
}

output "uptime_check_id" {
  description = "Cloud Monitoring uptime-check ID, or null while provision_instance=false."
  value       = try(google_monitoring_uptime_check_config.app[0].uptime_check_id, null)
}

output "data_disk" {
  description = "Persistent application disk retained independently of the VM."
  value = {
    name        = google_compute_disk.data.name
    zone        = google_compute_disk.data.zone
    device_path = "/dev/disk/by-id/google-${local.data_disk_device_name}"
  }
}
output "billing_budget_name" {
  description = "Terraform-managed project-scoped Cloud Billing budget resource. Alerts do not hard-cap spend."
  value       = google_billing_budget.project.name
}
