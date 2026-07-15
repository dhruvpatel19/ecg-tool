# TRACE public entry and authentication audit

Updated: 2026-07-14

## Product contract

TRACE has one public marketing surface and one account-scoped learning product.
The landing page, authentication, privacy, terms, accessibility, and source
attribution remain public. Every learning mode, dashboard, competency view,
coach, account page, and progress API requires an authenticated student account.
There is no guest learning mode.

Existing browser-only records are migration data, not a continuing product
identity. They may be claimed through one explicit, owner-safe transition during
the legacy migration window. New anonymous learning writes are not permitted.

The intended entry sequence is:

`public landing -> account registration -> verified email -> optional onboarding -> dashboard -> first activity`

Returning learners use:

`email + password -> safe requested destination or dashboard`

## Audit findings and disposition

| Priority | Finding | Product decision | Status |
|---|---|---|---|
| P0 | Guest learning was advertised from landing, login, navigation, and account settings. | Remove every guest entry point and prevent anonymous mode/API use. Preserve legacy records only through a bounded migration path. | Complete and focused-test verified |
| P0 | Private routes could mount before authentication resolved. | Fail closed before child mode UI or private requests mount; preserve a same-origin return path. | Complete and browser-tested |
| P0 | Public landing and dashboard shared `/` and changed after session hydration. | `/` is always public; `/dashboard` is the private learning home. | Complete |
| P0 | Username-only accounts were unrecoverable. | Make registration and sign-in email-first; add verification and enumeration-safe password reset. | Backend and browser flows complete and focused-test verified |
| P0 | Production email delivery had no provider boundary or deployment handoff. | Use a provider-neutral delivery interface, authenticated STARTTLS, a monitored Reply-To, non-secret GCP transport configuration, and a dedicated Secret Manager password. | Brevo Free pilot sender and GCP secret wiring configured; controlled-domain authentication remains a production follow-up |
| P1 | “Real ECG” was illustrated with a repeating hand-authored waveform. | Render an actual deidentified PTB-XL Lead II sample and show source/license provenance. | Complete |
| P1 | Public mobile page was approximately 5,377 px long. | Merge repetitive proof sections, use a compact mode pathway, and keep the ECG in the first viewport. | Complete; current 390 px capture is materially shorter |
| P1 | Registration did not disclose privacy, AI use, retention limits, or dataset provenance. | Publish factual public privacy, terms, accessibility, and source pages; link them before account creation and in the footer. | Pages complete; terms/legal approval remains a release gate |
| P1 | Authentication errors were largely global and could expose raw backend text. | Use field-associated friendly errors, focus the first invalid field, and map all backend error codes. | Backend and browser mapping complete |
| P1 | Authentication had no verified recovery channel or anti-enumeration reset flow. | Generic reset-request responses, one-time hashed tokens, bounded expiry/attempts, resend cooldown, and full session revocation after reset. | Backend/browser complete and focused-test verified; provider activation remains external |
| P1 | Strong public AI claims were not visibly bounded. | Explain why recommendations are made; AI can support reasoning and questions but cannot award mastery or diagnose. | Public wording complete; product-contract tests remain |
| P2 | Registration and sign-in used the same marketing-heavy split layout. | Registration may retain a compact ECG/context panel; returning sign-in should be a focused single-column task. | Complete and browser-tested |
| P2 | No explicit first-run orientation follows verification. | Add a short optional orientation and honest baseline explanation; self-report must never count as competency evidence. | Separate dashboard/onboarding work |

## Visual concept comparison

Five intentionally different image-generation studies were produced before the
implementation was changed:

- [`concept-a-ecg-studio.png`](ui-studies/entry-auth/concept-a-ecg-studio.png): strongest ECG focus and clearest above-the-fold
  product demonstration. Its real-workspace hierarchy informed the implemented
  hero.
- [`concept-b-learning-journey.png`](ui-studies/entry-auth/concept-b-learning-journey.png): clearly communicates four connected modes,
  but is too dense for the first viewport. Its continuous pathway informed the
  compact mode list below the hero.
- [`concept-c-editorial.png`](ui-studies/entry-auth/concept-c-editorial.png): strongest calm hierarchy, progressive disclosure,
  account requirement, and footer trust layer. Those principles were combined
  with concept A.
- [`concept-auth-registration.png`](ui-studies/entry-auth/concept-auth-registration.png): appropriate contextual support for a new
  learner without hiding the form.
- [`concept-auth-signin.png`](ui-studies/entry-auth/concept-auth-signin.png): best returning-user flow because it removes
  marketing content and centers the credential task.

The generated concepts are design studies, not production assets. The live UI
is code-native, responsive, accessible, and renders an approved corpus ECG
rather than an image-generated waveform.

## Reference principles

The redesign borrows principles, not visual assets, from established education
and authentication patterns:

- [Brilliant](https://brilliant.org/) leads with a simple learning promise and
  explains interactive, adaptive work in learner language.
- [Osmosis](https://www.osmosis.org/) identifies the medical learner and outcome
  immediately, while keeping sign-in and the primary account action visible.
- [AMBOSS for students](https://www.amboss.com/us/students) presents one
  connected system across learning and practice rather than disconnected tools.
- [web.dev sign-in guidance](https://web.dev/articles/sign-in-form-best-practices)
  supports semantic forms, stable labels/names, correct autocomplete, password
  visibility, mobile-sized controls, and real-device testing.
- [OWASP authentication guidance](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html),
  [forgot-password guidance](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html),
  and [session guidance](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
  inform generic recovery responses, one-time tokens, throttling, session
  rotation, and revocation.
- [NIST SP 800-63B-4](https://pages.nist.gov/800-63-4/sp800-63b.html) supports
  length-first passwords, breached/common-password screening, long passphrases,
  and avoiding arbitrary composition rules.
- [WCAG 2.2 accessible authentication](https://www.w3.org/WAI/WCAG22/Understanding/accessible-authentication-minimum.html)
  informs password-manager support, paste/autofill, and avoidance of cognitive
  authentication puzzles.

## Authentication security acceptance criteria

### Registration and verification

- Email comparison uses a documented normalized form and a database uniqueness
  constraint. New and existing email registration attempts return the same
  public success shape and both deliver a real owner-only code; proving an
  existing-email resolution grants no session and directs the owner to sign-in
  or recovery. Username availability remains intentionally public. A username
  collision wins when both identifiers collide, preventing a combined probe.
- A new account cannot enter learning routes until its email is verified.
- Email verification requires both the one-time email proof and fresh re-entry
  of the account password; the link page never auto-submits. This prevents an
  unsolicited or scanner-opened link from activating an attacker-chosen pending
  credential.
- Verification secrets are random, stored as hashes, single-use, purpose-bound,
  time-limited, attempt-limited, and never logged in plaintext.
- Link secrets live only in URL fragments, never in the HTTP request URL or
  `Referer`; the client captures them in layout, scrubs query/fragment, and waits
  for an explicit user action. The opaque challenge id alone may be a query
  parameter.
- Resend is cooldown- and rate-limited. A resend supersedes earlier live tokens
  when appropriate and does not create parallel unlimited attempts. Public
  registration and reset requests cannot restart an exhausted per-account mail
  window, even when usernames or request IPs rotate.
- Successful verification creates or rotates the login session atomically.

### Sign-in

- Students sign in with their verified email and password; usernames are not a
  student-facing credential.
- Email-code two-step verification is absent from deployed routes and account
  settings. Early pilot flags are cleared after the next successful password
  proof so no account is stranded.
- All authentication cookies are `HttpOnly`, `Secure` in production,
  appropriately `SameSite`, narrowly scoped, and rotated after authentication
  state changes.

### Password recovery

- Reset request always returns the same public message for existing and
  non-existing addresses and has comparable timing behavior.
- Reset tokens are random, hashed, single-use, purpose-bound, and expiring.
- A successful reset invalidates all other reset/verification grants and every
  existing login session before the student signs in again.
- A pending, unverified registration can be reclaimed through the same generic
  reset flow: the email proof replaces the credential and verifies the address
  without issuing a session, closing a seven-day email-reservation denial.
- Pending recovery atomically removes attacker-selected identity text from both
  the account and learner profile. The owner may supply a replacement username
  and display name with the reset proof; older clients safely receive a unique
  neutral username and `Student` display name.
- Password managers can identify current, new, and confirmation password fields;
  paste and autofill are not blocked.

### Account lifecycle

- Email change requires current-password confirmation and verification of the
  new address before replacement.
- Password change/reset, email replacement (to the old
  address), and account deletion emit secret-free post-commit security notices.
  Delivery failure cannot roll back the mutation and is counted by aggregate
  dispatcher telemetry without logging account data.
- Password change rotates the current session and revokes other sessions.
- Sign-out-all and password rotation consume every outstanding authentication
  challenge in the same transaction as session revocation.
- Students can inspect/revoke sessions, export progress after reauthentication,
  and permanently delete the live account record with strong confirmation.
- Legacy username-only accounts are visibly required to add and verify email;
  they are not granted a silent permanent exemption.

## UI and accessibility acceptance criteria

- The public page renders without waiting for `/auth/me`; an auth outage cannot
  hide marketing, sign-in, recovery, or legal pages.
- There is one primary action per auth state. Returning sign-in does not place a
  feature tour before the form.
- Every field has a persistent label, correct input type/name/autocomplete,
  explicit requirements, `aria-invalid` when appropriate, and an associated
  error. The first invalid field receives focus.
- Password and OTP values can be pasted; password fields have accessible
  show/hide controls; OTP fields do not force six separate inaccessible inputs.
- Submit controls prevent duplicate requests while giving an immediate busy
  state. Network errors retain non-secret input and offer a safe retry.
- Keyboard focus remains visible; dialogs trap and restore focus; the public
  shell exposes skip, banner, navigation, main, and footer landmarks.
- At 320 px there is no horizontal overflow, controls are at least 44 px tall,
  and the first registration field appears without a long marketing preamble.
- Automated WCAG A/AA checks pass on landing, sign-in, registration,
  verification, reset request, and reset confirmation at desktop and phone
  widths.

## Remaining release decisions

1. Bring or purchase a controlled sender domain for a polished launch and
   authenticate it with SPF/DKIM/DMARC. The no-cost Brevo pilot currently uses
   the verified `challengeat7@gmail.com` sender and an SMTP credential stored in
   GCP Secret Manager; it is suitable for functional testing but not the final
   institutional sender identity.
2. Approve the public privacy/terms text, institutional retention reference,
   backup-deletion policy, and support contact.
3. Decide whether institutional OIDC/SAML should be added in addition to local
   email/password authentication.
4. Define abuse monitoring, account-support escalation, and provider outage
   procedures before enrolling real students.
5. Add server-owned Terms version/acceptance timestamp (and a Privacy notice
   version if counsel treats it as acknowledgement) before representing the
   checkbox as an auditable legal acceptance record. This remains P2 rather than
   inventing consent metadata retroactively.
6. Load-test shared IP/global auth circuit-breaker ceilings against expected
   classroom NAT bursts and approved edge-WAF capacity before broad enrollment.
