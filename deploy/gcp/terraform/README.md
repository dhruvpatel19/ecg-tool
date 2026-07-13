# TRACE ECG durable GCP foundation

This Terraform package defines a deliberately gated, single-region deployment for the TRACE ECG FastAPI backend. It creates the durable/security foundation first and creates exactly one GCE VM only after `provision_instance = true`.

Terraform does **not** upload an image, corpus archive, license-restricted data, or secret payload. It does not reference or grant access to the MIMIC source bucket. Do not use the release-corpus bucket as a replacement for the governed raw-source boundary.

## What it creates

- a custom VPC/subnet and one reserved regional public IPv4 address;
- firewall ingress limited to public TCP 80/443 plus TCP 22 only from Google's IAP range;
- one Shielded, non-preemptible GCE VM with deletion protection and OS Login;
- one independently retained persistent data disk with daily regional snapshots;
- private, regional corpus and learner-backup buckets with uniform access, public-access prevention, versioning, retention, soft delete, and destroy guards;
- one private Artifact Registry Docker repository whose disposable unique build
  tags are cleanup-managed while every deployment is pinned to a content digest;
  cleanup keeps the active digest plus explicitly declared recovery digests;
- empty Secret Manager containers for the auth-rate-limit HMAC key and origin shared secret, plus an optional LLM key container;
- a dedicated VM service account and resource-scoped IAM;
- a public `/readyz` dependency-aware uptime check and failure alert policy;
- a project-filtered monthly Cloud Billing budget with current/forecast alerts
  (an alerting control, not a hard spend cap).

The VM identity receives only:

- `roles/storage.objectViewer` conditionally on one configured corpus object (the generation is also pinned in metadata);
- `roles/storage.objectCreator` and `roles/storage.objectViewer` conditionally under one backup prefix, so it can create/restore but cannot overwrite or delete backups;
- repository-level `roles/artifactregistry.reader`;
- secret-level `roles/secretmanager.secretAccessor` on the runtime secret containers;

The `cloud-platform` OAuth scope is intentionally broad because IAM is the permission boundary; there are no project-wide Storage, Artifact Registry, Logging, Monitoring, or Secret Manager grants.

## Prerequisites and two-phase release gate

Use Terraform 1.6+ and Application Default Credentials for an infrastructure operator with permission to enable services, create the declared resources, and create/update a budget on the selected Cloud Billing account. Configure a pre-created remote GCS backend according to the institution's state policy; the empty backend block deliberately prevents silent local state. Copy `backend.hcl.example` to ignored `backend.hcl` only after the state bucket receives uniform access, public-access prevention, versioning, retention, and tightly scoped operator IAM.

1. Copy `terraform.tfvars.example` to `terraform.tfvars`, set unique bucket names, and keep `provision_instance = false`.
2. Review billable resources, configure the billing account/monthly GCP budget and auditable Vercel/LLM spend-limit references, then set `billing_acknowledged = true` only with explicit approval. Any missing gate blocks the foundation before resource creation. GCP budgets alert but do not cap or disable billing.
3. Run `terraform init -backend-config=backend.hcl -input=false`, `terraform fmt -check`, `terraform validate`, and review `terraform plan`.
4. Apply the foundation. No application VM exists yet.
5. Build and push the backend image outside Terraform. Record the immutable Artifact Registry reference returned by the registry (`...@sha256:<64 hex>`); a tag is rejected by the VM precondition. Before replacing an existing `backend_image`, add its digest to `artifact_recovery_image_digests` so cleanup continues to protect the rollback artifact.
6. Upload the approved corpus archive outside Terraform. Record both its GCS object generation and local SHA-256. This must be the release corpus, never a raw credentialed MIMIC archive.
7. Add secret **versions** outside Terraform. The containers are outputs; payloads must never appear in `.tf`, `.tfvars`, plan output, or Terraform state. At minimum populate the auth-rate-limit and origin-shared-secret containers. The production example also requires the LLM API-key version. Configure the same origin value securely in the Vercel server environment.
8. Set the image digest, corpus generation/SHA, DNS health hostname, ACME email, and `provision_instance = true`; plan and apply again.

The checked demo example uses one `e2-small` VM with 20 GiB standard boot and
data disks in `us-east1`. It retains the complete corpus, durable SQLite state,
backup, and rollback behavior, but has less concurrency and latency headroom
than `e2-medium`/`pd-balanced`; resize only after observing the documented load
signals.

Before step 8, resolve `debian-12` with `gcloud compute images
describe-from-family --format='value(name)'` and set `source_image` to the concrete
`projects/debian-cloud/global/images/debian-12-bookworm-vYYYYMMDD` resource path. Mutable family aliases are
rejected. A production environment also fails planning unless the uptime check
validates HTTPS and at least one notification channel is configured.

Example out-of-band secret version commands (values are read interactively/stdin and are not Terraform-managed):

```bash
openssl rand -hex 32 | gcloud secrets versions add ecg-auth-rate-limit-secret --data-file=-
openssl rand -hex 32 | gcloud secrets versions add ecg-origin-shared-secret --data-file=-
gcloud secrets versions add ecg-llm-api-key --data-file=-
```

If an LLM provider is enabled, create the optional container through Terraform and add its value the same way. Do not paste a key on a command line that will be retained in shell history.

## Trusted installer contract

Terraform compresses the reviewed host scripts, systemd units, and Caddyfile
into non-secret instance metadata. `startup.sh.tftpl` stages that bundle locally
and invokes:

```text
<ecg-install-script-path> --config <ecg-runtime-config-path>
```

No repository is cloned and no executable deployment code is downloaded at
boot. All instance metadata is non-secret. The trusted installer is responsible
for idempotently:

- formatting (only when blank) and mounting `/dev/disk/by-id/google-ecg-data` at the configured data path;
- downloading the exact `gs://...#generation` corpus object and verifying its configured SHA-256 before atomic promotion;
- authenticating Docker with the VM service account and pulling the exact `@sha256:` backend image;
- reading secret payloads from Secret Manager and writing a root-owned, mode `0600` environment file;
- setting `APP_ENV=production`, `ECG_REQUIRE_REAL_DATA=1`, the persistent `DATABASE_URL`, `ECG_CORPUS_ROOT`, `AUTH_RATE_LIMIT_SECRET`, and `ECG_ORIGIN_SHARED_SECRET`;
- installing/restarting the backend and reverse-proxy systemd units, exposing only 80/443;
- enforcing the reviewed Docker CPU, memory-reservation, hard-memory, and no-swap-growth ceilings;
- installing an idempotent backup timer that writes uniquely named objects under the granted backup prefix.
- isolating root operational locks/temp/quarantine from the app-writable state
  directory and exposing only the backup marker through a read-only container
  mount;
- blocking UID 10001 from both GCE metadata IPs before backend start and
  reconciling that host rule every minute.

Metadata is not a secret store. Secret resource names are safe configuration; secret values must only be materialized at runtime into the root-only file.

Terraform metadata is the durable desired state, but changing it does not
execute the startup script on an already-running VM. For image updates, apply
the new digest first and then run `install-release.sh`; that script rejects
manual drift from metadata. If its readiness rollback fires, re-apply the old
digest so the next boot agrees with the rollback. For embedded installer/unit,
corpus, secret-ID, or tutor-config changes, apply and run
`sudo google_metadata_script_runner startup` (or perform a controlled reboot)
so the metadata startup bundle is re-staged and reconciled.

## Health and recovery behavior

The VM automatically restarts after host failure and migrates during maintenance. Cloud Monitoring checks `/readyz` for `"ok":true`; that route verifies the real corpus, an SQLite write lock, a create/`fsync` probe and configurable free-space floor on the state filesystem (2 GiB by default), freshness marker from the online SQLite backup, and required live tutor configuration. The backend unit waits only for process liveness during bootstrap, so a missing backup marker fails readiness immediately while still permitting the installer to create the schema and run its mandatory initial backup. A marker older than 14 hours also fails readiness. An alert policy fires after two minutes of readiness failures. Set a real DNS hostname and enable TLS validation before a showcase or production release.

The data disk survives VM replacement and is guarded by Terraform `prevent_destroy`. The VM also has deletion protection. Scheduled snapshots are explicitly crash-consistent (`guest_flush = false`); append-only online SQLite backups are the application-consistent layer whose freshness blocks readiness. An operator must still test restore procedures. To intentionally destroy protected resources, first make an explicit reviewed change that disables deletion protection/destroy guards.

Default retention is bounded where automatic deletion is recovery-safe: online
backups 90 days, crash-consistent disk snapshots 14 days, noncurrent corpus
generations 90 days, and registry images 90 days while always keeping the ten
most recent versions, the active deployment digest, and explicitly declared
recovery digests. The live pinned corpus object is intentionally exempt;
quarterly operator cleanup must compare object name/generation with Terraform
before deleting older uniquely named releases. With the timer/host healthy, the
scheduled RPO target is roughly 6h15 plus backup duration (including randomized
delay); readiness becomes unhealthy after 14 hours without success, which is a
separate outage tolerance rather than the RPO.

Set `allow_initial_disk_format = true` only for the first boot of the newly
created blank disk. After a successful mount/initial backup, change it back to
`false` and apply. This closes the formatting authorization for later VM
replacements while preserving the disk by UUID.

## IAP SSH

SSH is never public. Listed `iap_ssh_members` receive instance-scoped IAP tunnel access, project OS Admin Login, and `iam.serviceAccounts.actAs` on only this VM's service account (an OS Login requirement for service-account-backed VMs). They also need ordinary read permission to discover the VM, normally inherited from the deployment-operator group.

```bash
terraform output -raw iap_ssh_command
```

Keep the operator list empty if no interactive administration is required.
