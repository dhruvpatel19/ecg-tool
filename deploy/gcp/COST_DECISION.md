# Deployment cost decision — 2026-07-14

## Decision

Keep the current **Vercel → one `e2-small` VM → local SQLite/local corpus**
shape for the demo and first low-volume release. It is the cheapest option that
preserves the application's current durability, authentication, progress,
adaptive-learning, waveform, and live-tutor behavior without a risky storage
rewrite.

Cloud Storage is already being used in the cost-effective role: the immutable
release archive and append-only learner backups are stored in GCS, while the
active corpus and writable learner database are hydrated onto block storage.
Moving the writable SQLite database to GCS is not a valid optimization.

This is a configuration-based estimate, not an invoice reconciliation. The
workstation used for this audit does not have `gcloud` or Terraform installed,
so the live resource inventory and current billing export still need to be
checked in Cloud Console.

## Checked deployment shape

- Project configuration: `mimic-ecg-vcg-analysis`, `us-east1-b`, demo
  environment, one always-on `e2-small` (2 GB memory, 0.5 sustained fractional
  vCPU), one static Premium-tier IPv4 address.
- Storage: 20 GiB `pd-standard` boot disk plus 20 GiB `pd-standard` protected
  data disk, daily data-disk snapshots, one regional corpus bucket, one regional
  backup bucket, and Artifact Registry.
- Corpus: 22,497 waveforms. The checked release archive is 480,488,162 bytes
  (about 458 MiB); the active `corpus.db` plus waveform files are about 1.36 GiB
  expanded. Hydration also retains the compressed artifact temporarily, so the
  20 GiB data disk has ample operating and rollback headroom.
- Learner state: one local SQLite/WAL database contains accounts, sessions,
  authentication throttles, preferences, mastery, attempts, Guided events,
  Training campaigns, Rapid rounds, Clinical shifts, tutor threads, quotas,
  exports, and maintenance coordination. Four online backups run daily.
- Frontend: the same-origin Next.js proxy runs in Vercel `iad1`, which is close
  to the `us-east1` backend and preserves the current HttpOnly-cookie/origin-key
  security boundary.

## Monthly cost envelope

Assumptions: 730 hours/month, on-demand US list pricing, one continuously
running VM, current 40 GiB standard Persistent Disk allocation, low demo
traffic, and no negotiated discounts. Confirm the VM line in the official
[Google Cloud Pricing Calculator](https://cloud.google.com/products/calculator)
immediately before a cost approval.

| Item | Estimate | Basis |
| --- | ---: | --- |
| `e2-small` compute | about **$12.2** | Current US on-demand shared-core estimate; Google documents `e2-small` as 2 GB RAM with 0.5 sustained fractional vCPU in the [E2 machine guide](https://docs.cloud.google.com/compute/docs/general-purpose-machines). |
| In-use external IPv4 | **$3.65** | $0.005/hour × 730; see [VPC external IP pricing](https://cloud.google.com/vpc/pricing#ipaddress). |
| 40 GiB `pd-standard` | **$0.40 if the account's 30 GiB allowance is available; $1.60 list price otherwise** | US standard PD is $0.04/GiB-month and the first 30 GiB-months are free; see [disk pricing](https://cloud.google.com/compute/disks-image-pricing#disk). |
| Corpus/backup GCS | normally **$0–$0.10** at current size | Regional Standard storage is about $0.02/GiB-month and the first 5 GiB-months are free in `us-east1`; versions and soft-deleted objects also count. See [Cloud Storage pricing](https://cloud.google.com/storage/pricing). |
| Snapshots, Artifact Registry, secrets, uptime checks | normally **$0–$1** at current size | Snapshot free allowance is 5 GiB-months in eligible US regions; Artifact Registry includes 0.5 GiB and then charges $0.10/GiB-month; Secret Manager includes six active versions and 10,000 accesses/month. See [disk](https://cloud.google.com/compute/disks-image-pricing), [Artifact Registry](https://cloud.google.com/artifact-registry/pricing), and [Secret Manager](https://cloud.google.com/secret-manager/pricing) pricing. |
| Transactional authentication email | **not activated; provider/domain-dependent** | Brevo can support a $0 limited pilot but may rewrite an unauthenticated From address; Resend's $0 tier requires a sender domain the project controls. The current `ecg-tool.vercel.app` hostname is not such a domain. The deployment creates a password secret container in SMTP mode but does not enroll a provider, buy a domain, create DNS records, or add a secret version. Review `docs/AUTH_EMAIL_PROVIDER_DECISION.md` and obtain explicit approval before any domain purchase, paid plan, or overage. |
| Network/firewall logs | variable | VPC Flow Logs and firewall logs are vended network logs; current pricing is $0.25/GiB with no free allotment. See [Observability pricing](https://cloud.google.com/products/observability). |
| Premium network egress | variable | First 1 GiB/month is free, then North America is $0.12/GiB at the current tier. See [VPC internet egress pricing](https://cloud.google.com/vpc/pricing#internet_egress). |

Expected fixed GCP cost is therefore about **$16–$20/month before AI and
traffic-dependent logging/egress**. This is not an 80 GiB VM: it is a 2 GB VM
with 40 GiB of disk allocation in total.

Authentication email is a functional release dependency but is not included in
that fixed GCP estimate. `provision_instance=true` now fails closed unless SMTP
settings are complete; bootstrap also fails if an authenticated SMTP username
has no readable password secret version or the required monitored Reply-To is
missing. This wiring does not authorize provider enrollment, DNS changes,
domain purchase, or cost. SMTP credentials remain solely on the GCP backend;
there is no incremental Vercel mail runtime or secret copy.

Vercel is separate:

- Hobby is $0 but is restricted to personal, non-commercial use under
  [Vercel's fair-use policy](https://vercel.com/docs/limits/fair-use-guidelines).
- A commercial/institutional production deployment should budget **$20/month
  per Pro developer seat**, including $20 of usage credit, per the
  [Vercel pricing page](https://vercel.com/pricing). Fixed-window WAF rate
  limiting must be confirmed for the selected plan before launch.

The live tutor is also separate. The configured `gpt-5.6-luna` list price is
$1/million input tokens and $6/million output tokens. The application caps
remote calls at 100/day and output at 1,200 tokens/call. If every reserved call
hit the output cap, output alone would be at most about **$21.60/month**; input
cost is additional and depends on grounded-context size. Use
`$1 × input_MTok + $6 × output_MTok` and reconcile against the provider bill.
See the [official model page](https://developers.openai.com/api/docs/models/gpt-5.6-luna).
The app currently records reservations but not provider-reported token usage,
so the provider project spend limit remains mandatory.

## Alternatives considered

| Option | Cost direction | Full-function verdict |
| --- | --- | --- |
| Keep `e2-small` + local PD + GCS source | About $16–$20 GCP fixed | **Use now.** No migration; warm local corpus; durable single writer; current backup/restore path remains valid. |
| Resize to free-tier `e2-micro` | Could reduce GCP fixed cost to roughly the IPv4 charge plus small overages | **Benchmark candidate only.** `e2-micro` has 1 GB RAM and 0.25 sustained fractional vCPU; the current backend alone has a 1,536 MiB hard limit and 1,024 MiB reservation, before Docker/Caddy/backups. It cannot be accepted without a cold-boot, backup, concurrency, memory, and p95 waveform test. The [Free Tier](https://docs.cloud.google.com/free/docs/free-cloud-features) covers one eligible `e2-micro` and 30 GiB-months of standard PD. |
| Cloud Run with current SQLite | Low request-based compute at idle | **Reject.** Cloud Run's writable filesystem does not persist when an instance stops; see the [container contract](https://docs.cloud.google.com/run/docs/container-contract). Auth and progress would be lossy. |
| Cloud Run + GCS/FUSE for SQLite | Superficially cheap storage | **Reject.** GCS FUSE lacks POSIX/file-lock semantics and Google explicitly says not to use it as a database backend; see [Cloud Storage FUSE limitations](https://docs.cloud.google.com/storage/docs/cloud-storage-fuse/overview). Cloud Run volume mounts also lack concurrency control for writes. |
| Cloud Run + smallest Cloud SQL + object corpus | Roughly $7.67/month for `db-f1-micro` compute, plus DB storage/backups and Cloud Run | **Not a current saving.** The smallest shared-core tier has no SLA and is billed while running; see [Cloud SQL pricing](https://cloud.google.com/sql/pricing). The code only accepts SQLite, uses SQLite-specific transactions throughout, and has no object-backed waveform/corpus adapter. The rewrite and migration risk outweigh a single-digit monthly saving. |
| Cloud Run + Firestore + object corpus | Potentially near $0 at very low traffic; Firestore includes 1 GiB, 50k reads/day, and 20k writes/day | **Long-term option, major rewrite.** Every relational transaction, lease, idempotency guarantee, export/delete flow, and mastery query needs redesign and migration. See [Firestore free quotas](https://docs.cloud.google.com/firestore/quotas). |
| Cloud Run-hosted Next.js frontend + existing VM backend | Could avoid the $20 Pro platform fee | **Future production experiment only.** It needs a new frontend container/deploy path, custom-domain routing, replacement edge throttling/WAF controls, and cold-start measurement. Vercel Hobby already costs $0 for the current non-commercial demo, so this saves nothing today. |

Cloud Run itself has useful request-based free quotas and can scale to zero, but
that only helps after durable learner state is externalized. Current rates and
free quotas are documented in [Cloud Run pricing](https://cloud.google.com/run/pricing).

## Lowest-risk cost optimizations

1. **Keep the GCS hydration design.** The object-store copy already costs
   pennies; the local hydrated copy avoids a remote database read and 22,497
   per-waveform object reads in the student hot path.
2. **Measure before resizing.** Gather VM CPU/memory, `/readyz`, p50/p95 packet
   and 12-lead waveform latency, backup duration, and concurrent-session load
   for at least seven representative days. Only then test `e2-micro` in staging.
3. **Evaluate Standard network tier in staging.** The current backend uses
   Premium tier (1 GiB free, then $0.12/GiB to North America). Standard tier
   includes the first 200 GiB/month and is then $0.085/GiB; see
   [Network Service Tiers pricing](https://cloud.google.com/network-tiers/pricing).
   Because the Vercel proxy is already pinned to `iad1` and the backend is in
   `us-east1`, Standard tier may be acceptable, but changing the address tier
   replaces the static IP and requires a DNS/TLS cutover. Approve and benchmark
   it; do not mutate the live address speculatively.
4. **Do not shrink disks for a $0.40/month saving.** Persistent disks cannot be
   shrunk in place, and the current split protects learner state during VM/image
   replacement. A boot/data migration and reduced rollback headroom are not
   justified by the saving.
5. **Monitor vended network-log volume.** The current 50% VPC flow sampling and
   firewall logging can become a larger cost than corpus storage under scan or
   attack traffic. Keep the security evidence, but review actual GiB after the
   demo and tune sampling/retention deliberately.

## Architecture and operations gaps before production

- The checked demo is deployed in the same project as the raw MIMIC research
  data, contrary to the deployment README's isolation recommendation. Project
  creation itself has no monthly fee. A dedicated app project would separate
  IAM and cost attribution; this matters because OS Admin Login is
  project-scoped and the current app budget is mixed with research-project
  spend. Treat the shared project as an approved demo exception, not the final
  production boundary.
- The live inventory and bill have not been reconciled from this workstation.
  Compare Cloud Billing by SKU and label for 7- and 30-day windows before
  changing the estimate.
- There is no Postgres/Firestore learner-store adapter, migration ledger for a
  managed database, dual-read verifier, or rollback drill.
- `WaveformStore` has only a local implementation, and corpus metadata is an
  immutable local SQLite database. There is no private object-store adapter,
  bounded cache, or equivalent release-integrity path for a serverless backend.
- The LLM adapter does not persist provider token-usage fields, so per-mode and
  per-learner AI cost cannot yet be attributed without provider-side reporting.
- Vercel authentication WAF rules remain external/manual controls rather than
  infrastructure-as-code. Production must record their published versions and
  verify edge 429 behavior.
- `environment="demo"` currently permits no Monitoring notification channel.
  Production Terraform intentionally requires a reviewed channel and the
  authenticated-retention-policy gate.

## Approval gates

No cloud mutation follows from this document. Obtain explicit cost approval
before any Vercel plan upgrade, new Cloud Run/Cloud SQL/Firestore resource,
static-IP/network-tier replacement, disk migration, project migration, or LLM
limit increase.

Before production approval, record:

1. an official GCP calculator estimate plus actual 7-/30-day Billing-by-SKU
   evidence;
2. the selected Vercel plan, seat count, WAF eligibility, and spend controls;
3. the OpenAI project limit and observed input/output tokens per tutor call;
4. a monthly ceiling that separately budgets GCP fixed cost, network/logging,
   Vercel, and AI; and
5. an owner for every alert. The configured GCP budget is an alert, not a hard
   cap; Google explicitly notes that budgets do not automatically stop usage in
   its [budget documentation](https://docs.cloud.google.com/billing/docs/how-to/budgets).
