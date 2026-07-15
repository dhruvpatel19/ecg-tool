# TRACE authentication email: provider, domain, and cost gate

Updated: 2026-07-14

## Decision status

The application and GCP release path are provider-neutral and ready for SMTP
submission with authenticated STARTTLS on port 587. They cover account
verification, password recovery, email changes, email sign-in codes, and
secret-free security notices. GCP stores only the SMTP password in Secret
Manager; the browser and Vercel never receive SMTP credentials.

No provider account, sender, DNS record, secret version, paid plan, overage, or
domain purchase has been activated by this repository. Production remains
fail-closed until all of those external prerequisites are reviewed and supplied.

The current public frontend is `ecg-tool.vercel.app`. That is a shared Vercel
platform domain, not a sender domain the project controls. It therefore cannot
be used to complete a polished, authenticated sender setup. Resend explicitly
requires a domain the sender owns and controls, with SPF and DKIM records, before
mail can be sent broadly ([Resend domain requirements](https://resend.com/docs/dashboard/domains/introduction)).

**Conclusion:** there is no zero-cost, branded sender available from the current
domain inventory. A polished learner launch must first bring or purchase a
domain the owner controls. Domain registration and mailbox costs vary by
registrar/TLD and require explicit approval before purchase.

## Current provider comparison

Published limits must be rechecked on the activation date.

| Option | Published entry terms | Fit now | Important constraint |
|---|---|---|---|
| Brevo Free | $0/month, no card/time limit, 300 sends/day; transactional email is included ([Brevo plans](https://help.brevo.com/hc/en-us/articles/208589409-About-Brevo-s-pricing-plans), [free limits](https://help.brevo.com/hc/en-us/articles/208580669-FAQs-What-are-the-limits-of-the-Free-plan)) | Only acceptable as a tightly limited pilot before a custom domain exists | Brevo can verify an individual sender by a code sent to that mailbox ([sender setup](https://help.brevo.com/hc/en-us/articles/208836149-Create-a-new-sender-From-name-and-From-email)), but Free mail carries Brevo branding and Brevo rewrites unauthenticated/free-domain transactional From addresses to a provider domain. Brevo calls this a temporary stopgap and warns that recipients may not recognize it ([free limits](https://help.brevo.com/hc/en-us/articles/208580669-FAQs-What-are-the-limits-of-the-Free-plan), [sender requirements](https://help.brevo.com/hc/en-us/articles/14925263522578-Comply-with-Gmail-Yahoo-and-Microsoft-s-requirements-for-email-senders)). |
| Resend Free | $0/month, 3,000 emails/month and 100/day; no overage on Free ([Resend pricing](https://resend.com/pricing?product=transactional)) | Recommended small-pilot transport **after** a controlled domain is available | Requires a verified owned domain and API key. SMTP uses `smtp.resend.com`, username `resend`, password = API key, port 587 STARTTLS ([Resend SMTP](https://resend.com/docs/send-with-smtp)). |
| Amazon SES | Usage-based with no contract/minimum; current account credits/free eligibility and regional charges vary | Lowest direct sending cost may be attractive at sustained volume, but not the fastest cross-cloud launch | A new regional SES account starts in a sandbox, can send only to verified recipients, and needs a production-access request; From identities must remain verified ([SES sandbox](https://docs.aws.amazon.com/ses/latest/dg/request-production-access.html), [verified identities](https://docs.aws.amazon.com/ses/latest/dg/verify-addresses-and-domains.html)). Confirm the current estimate in the official [SES pricing page](https://aws.amazon.com/ses/pricing/) immediately before approval rather than relying on a copied unit price. |

Google Compute Engine permits external SMTP traffic on ports 587 and 465 but
generally blocks external port 25. The reviewed application path uses port 587
with STARTTLS, so no always-on mail VM or port-25 exception is needed
([Google Cloud mail guidance](https://cloud.google.com/compute/docs/tutorials/sending-mail)).

The added Secret Manager version may be $0 incremental while the billing account
stays within Google's six active-version and 10,000-access monthly free
allowances; usage above those allowances is billable. Recheck the billing account
inventory and the official [Secret Manager pricing](https://cloud.google.com/secret-manager/pricing)
before adding a version.

## Recommendation

1. For the fastest limited pilot with the existing domain inventory, Brevo Free
   is the only reviewed $0 route: verify a mailbox the owner controls, accept the
   provider-rewritten From address explicitly, keep the 300/day hard ceiling,
   and disclose that this is not the polished launch configuration. Do not use
   it for a cohort until Gmail, Outlook, and institutional delivery tests pass.
2. For a polished pilot/launch, first bring or purchase a controlled domain.
   Create a dedicated sending subdomain, publish SPF/DKIM/DMARC, and use Resend
   Free up to its 100/day and 3,000/month caps. Keep paid overages disabled.
3. If projected auth traffic can exceed the free caps, compare current Resend,
   Brevo, and SES quotes plus operational/privacy costs. Do not activate a paid
   plan or pay-as-you-go option without explicit owner approval.

## External activation steps

These actions are intentionally not automated because they create external
accounts, DNS changes, credentials, and possible cost.

### Shared steps for a polished launch

1. Select a domain the project legally controls and approve any registrar and
   mailbox cost. Prefer an isolated sending subdomain to protect reputation.
2. Create `no-reply@<sending-domain>` as the From identity and a genuinely
   monitored `support@<domain>` mailbox for `AUTH_EMAIL_REPLY_TO`. Never use an
   individual's private account address in committed configuration or docs.
3. Add exactly the SPF/DKIM records generated by the selected provider. Add a
   DMARC record initially in monitoring mode, verify alignment, then tighten it
   only after all legitimate senders pass. Resend documents the staged approach
   ([DMARC guide](https://resend.com/docs/dashboard/domains/dmarc)).
4. Review the provider's privacy notice/DPA, data region/retention, subprocessors,
   bounce/complaint handling, and institutional requirements.

### Resend values after domain verification

```text
auth_email_delivery_mode  = "smtp"
auth_email_from_address   = "TRACE <no-reply@YOUR_SENDING_DOMAIN>"
auth_email_reply_to       = "TRACE support <support@YOUR_DOMAIN>"
auth_public_app_url       = "https://YOUR_FINAL_FRONTEND_ORIGIN"
auth_smtp_host            = "smtp.resend.com"
auth_smtp_port            = 587
auth_smtp_username        = "resend"
auth_smtp_starttls        = true
```

Create a domain-scoped, send-only API key if the provider/account supports that
scope. Add it as the SMTP password Secret Manager version from stdin; never put
it in Terraform, Vercel, Git, shell history, or a browser environment variable.

### Brevo limited-pilot values

Create and verify the individual sender, then retrieve the dedicated SMTP login
and SMTP key. Brevo says the SMTP password must be an SMTP key, not an API key
([Brevo SMTP setup](https://help.brevo.com/hc/en-us/articles/7924908994450-Send-transactional-emails-using-Brevo-SMTP)).

```text
auth_smtp_host       = "smtp-relay.brevo.com"
auth_smtp_port       = 587
auth_smtp_username   = "THE_PROVIDER_ISSUED_SMTP_LOGIN"
auth_smtp_starttls   = true
```

Store the SMTP key as the password Secret Manager version. Record explicit owner
acceptance that the visible From address may be rewritten until a controlled
domain is authenticated.

## Release verification and operations

- Run `python scripts/smoke_auth_email_local.py`; it exercises every challenge
  and security-notice purpose against an in-process loopback SMTP sink and emits
  no secrets or message content.
- Inside the backend container, run `python -m app.auth_mailer_cli`. It performs
  no network call and reports only mode/readiness plus safe environment-variable
  identifiers. Public `/readyz` continues to return only `{"ok": true|false}`.
- Complete one real end-to-end flow for verification, reset, email change, and
  each active security notice. Check both text and HTML variants, the UTC expiry
  wording, one-time/expiration behavior, Date/Message-ID headers, Reply-To, and
  inbox placement at Gmail, Outlook, and an institutional mailbox.
- Confirm SPF, DKIM, and DMARC pass in received headers. Test bounce, suppression,
  quota exhaustion, provider outage, credential rotation, and resend recovery.
- Monitor provider delivery/bounce/complaint dashboards and the backend's
  aggregate `auth_email_background_task_failed` and
  `auth_email_background_queue_full` events. Never alert with message bodies,
  recipients, tokens, codes, or provider response bodies.
- Set quota/billing alerts before enabling the provider. Record a rollback owner,
  incident contact, sender-domain owner, and credential-rotation date.

Vercel receives only `ECG_BACKEND_API_BASE` and the server-only
`ECG_ORIGIN_SHARED_SECRET`. SMTP credentials and sender settings belong solely
to the GCP backend runtime.
