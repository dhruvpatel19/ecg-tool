# Account lifecycle, verification, and recovery

## Account trust states

Learner-owned progress is available only to an authenticated, verified account
in development and production. The three explicit account states are:

- `verified`: a normalized unique email was proved and learning APIs are open;
- `email_verification_required`: an email is attached but has not been proved;
- `email_upgrade_required`: a pre-email legacy account must add and verify one.

`APP_ENV=test` retains an internal `demo` owner so deterministic curriculum tests
do not need to manufacture accounts. That fixture is not a deployable guest mode.
The production guest middleware never creates or refreshes `ecg_guest`. It only
recognizes an already-present, valid legacy cookie for preview, one-time claim,
or explicit erasure. A claim requires real unclaimed work, transfers every
learner ledger in one transaction, and clears the cookie. Empty or already
claimed namespaces cannot be used as an account-validity oracle.

## Registration and sign-in

New registration requires username, password, and email. Usernames and email are
normalized before unique lookup. Registration atomically creates the user,
profile, default objective rows, and a hashed email-verification challenge. It
does **not** create a learning session or transfer legacy progress. When a
positive legacy claim was requested, only its opaque guest id is bound to the
challenge; the cookie and data remain recoverable until the one-time email proof
**and a fresh re-entry of the registration password** atomically verify the
account, transfer progress, and create the first session. A link never activates
an attacker-chosen pending credential by itself. A verified account can also
explicitly attach or discard a positive
legacy record from Account settings.

An available username plus an existing email follows the same public 200/check-
email response shape as a new account and performs comparable password-hash,
write, and delivery work. The existing address receives an owner-only resolution
code. Proving it grants no session or mutation; it directs the owner to sign-in
or password recovery. Username availability remains public. If both identifiers
collide, the public username collision always wins so a known username cannot be
combined with candidate emails as a membership probe. The first existing-email
submission atomically creates a credentialless username reservation in the same
unique namespace. Therefore an exact second submission returns the same public
`username_taken` transition as a second submission for a genuinely new pending
account; the two-request sequence cannot reveal email membership. Reservations
have no profile, session, email, or learning graph and expire with empty pending
registration shells.

Login accepts one `identifier`, which may be a username or normalized email.
Legacy clients may still submit the same value as `username`. Missing accounts,
invalid email-shaped identifiers, and incorrect passwords perform the reviewed
dummy/real PBKDF2 path and return the same generic failure. Registration, login,
password confirmation, and recovery requests have persistent pair/IP/global
pre-hash limits so CPU-expensive password work is bounded.

Passwords use PBKDF2-HMAC-SHA256 with a random 16-byte salt and a current
600,000-iteration policy. Valid older hashes are upgraded during a successful
credential-checked session transaction. Password verification and session
insertion recheck the stored hash under one writer lock, so a concurrent password
change cannot mint a stale session. A legacy row's verification is padded to the
current total PBKDF2 work, so a wrong password is not cheaper than the unknown-
account dummy path. Readiness exposes only aggregate current/legacy/future/invalid
hash counts to operators; invalid rows fail closed and no identity is included.
Raw session tokens are never stored; SQLite contains only SHA-256 lookup digests.

New passwords are 10–256 characters. Long passphrases are accepted without
arbitrary composition rules; exact usernames, repeated-character strings,
whitespace-only values, and a small reviewed common-password set are rejected.

## Email challenge security

Verification, reset, and email change use one purpose-bound challenge
ledger. Each challenge has an opaque public id, independent random secret,
expiry, durable attempt counter, maximum attempts, one-time consumed marker,
resend cooldown, and send ceiling. Reset/email-change link tokens are generated
from 32 random bytes. Email verification codes are six random digits.
Verification mail shows the human-enterable code and a link carrying the
same one-time proof. Link secrets are placed only in the URL fragment, which is
not sent in the HTTP request target, proxy logs, or `Referer`; only the opaque
challenge id is a query parameter. The destination page immediately removes the
fragment and challenge id from the address bar, then requires an explicit action
and fresh password re-entry. Only an HMAC of
`purpose + challenge id + secret` is stored, preventing offline brute force of a
six-digit code from a database copy. Plaintext tokens/codes exist only in the
mailer call and are never written to the database or logs.

Email verification codes expire after 15 minutes, password-reset links after 30
minutes, and email-change links after 24 hours. Resend
rotates to a new independent secret and
invalidates the old one. A failed SMTP attempt releases only the cooldown; the
undelivered secret remains irrecoverable and the next resend rotates again.
Public registration-resolution and password-reset requests cannot create a new
challenge after the current per-account challenge reaches its five-send ceiling;
the ceiling resets only after that challenge window expires. Challenge selection,
replacement, username reservation, and delivery ownership occur under one
immediate writer transaction. Concurrent requests reuse the single winner and
only that winner may send, preventing stale-code emails and per-row ceiling
bypasses. Wrong registration-verification codes also increment a separate rolling
account-or-email budget that survives resend, expiry, and challenge reissue; a
fresh row cannot reset the guessing ceiling.

## Recovery and email change

`POST /auth/password-reset/request` always returns the same response for invalid,
missing, and eligible email addresses. A valid one-time reset proof updates the
password and revokes every session, export grant, and other outstanding auth
challenge in one transaction. It does not silently keep the current browser
signed in. A still-pending registration is also eligible for this generic flow:
the reset proof establishes control of its email, atomically replaces the
attacker-chosen credential, marks the email verified, and still requires an
ordinary sign-in. This prevents a third party from reserving someone else's email
for the full pending-account retention window. The same transaction replaces
attacker-selected username/display text in both `users` and `learner_profiles`.
The proof holder may submit an intended available username/display name; older
clients receive a unique neutral `student_<id>` username and `Student` display
name. A collision rolls the credential, verification marker, profile, sessions,
and one-time proof back together so the owner can retry safely.

Reset confirmation reserves pair/IP/deployment-wide capacity before challenge
lookup, password-policy evaluation, or PBKDF2 hashing, bounding random-id CPU
floods. Durable account origin distinguishes this genuinely new pending shell
from an established legacy account that merely attached an unverified address.
Only the former is eligible for identity recovery; an established legacy typo
receives the same generic reset-request response but no reset mail and can never
transfer its password, username, profile, or learning history.

Legacy accounts can attach an email only after current-password reauthentication.
Learning remains blocked until proof. A verified account can request an email
change after the same reauthentication; the existing email remains active until
the new destination is proved and uniquely swapped in one transaction. The
change challenge is bound to the current password fingerprint. Successful swap replaces the proving
session credential, revokes every other session and export grant, and consumes
all other outstanding auth challenges.

A mistyped setup address is recoverable without a guest or verification bypass.
`POST /auth/email/unverified/replace` accepts the current verification challenge
plus original password for a public pending registration, or an active session
plus current password for an established legacy account. The address swap and
new `email_verification` proof commit atomically and consume every old proof.
`POST /auth/email/unverified/cancel` deletes a never-activated pending shell (and
releases its username/email) or detaches a legacy setup address while preserving
the account and progress. Duplicate destinations and compare-and-swap races use
one neutral failure. An authenticated owner may also consume a pending
`email_change` proof through `/auth/email/change/cancel`; UI dismissal therefore
cannot leave the old link active.

Email-code two-step verification is retired from deployed environments. Early
pilot accounts that enabled it are migrated back to verified email + password
after the next successful password proof. Legacy factor routines remain
test-only while the old database column is preserved for a safe schema migration;
their routes are not registered outside the test environment.

Password change/reset, successful email replacement,
and account deletion queue secret-free security notices after the database
mutation commits. Email replacement alerts the previous address. A delivery
failure never reverses a completed account change; the bounded dispatcher counts
it as aggregate failed telemetry without logging recipient or account data.

No administrator bypass or institutional SSO is simulated.
OIDC/SAML linking, deprovisioning, and administrative recovery remain explicit
future institutional decisions.

## Mail transport and readiness

The mailer boundary is provider-neutral. `memory` is an ephemeral test/development
outbox and is refused in production. `smtp` uses Python's standard SMTP client,
required production STARTTLS and authentication, fixed safe text/HTML templates,
header-injection checks, TLS 1.2+, and a bounded timeout. Messages include Date,
Message-ID, Auto-Submitted, auto-response suppression, and a validated monitored
Reply-To. No provider credentials or paid service are selected by the application.

Production configuration requires:

- `AUTH_EMAIL_DELIVERY_MODE=smtp`;
- `AUTH_EMAIL_FROM_ADDRESS`, monitored `AUTH_EMAIL_REPLY_TO`, and
  `AUTH_PUBLIC_APP_URL`;
- `AUTH_SMTP_HOST`, `AUTH_SMTP_PORT`, `AUTH_SMTP_STARTTLS`, and
  `AUTH_SMTP_TIMEOUT_SECONDS`; and
- both `AUTH_SMTP_USERNAME` and `AUTH_SMTP_PASSWORD`.

`AUTH_PUBLIC_APP_URL` must use HTTPS in production because verification and
reset links carry one-time bearer secrets. HTTP is accepted only by local
development's non-production adapters.

The production transport currently supports SMTP submission with STARTTLS. The
reviewed GCP deployment fixes this to port 587. Implicit TLS on port 465 is not
implemented; setting
`AUTH_SMTP_STARTTLS=0` fails production readiness rather than allowing account
credentials, links, or OTPs over plaintext SMTP.

Missing or invalid SMTP configuration fails the production readiness gate and
returns `email_delivery_unavailable` for features that require mail. A network
failure after registration commits does not produce an opaque duplicate-account
dead end: the API returns the normal verification-pending response with
`deliveryFailed=true` and an immediately available resend. Plaintext secrets are
not persisted to make a durable outbox.

Public `/readyz` exposes only a boolean. An operator can run
`python -m app.auth_mailer_cli` inside the backend container to see safe
configuration-variable identifiers without printing addresses, hosts, URLs,
credentials, or provider responses. `python scripts/smoke_auth_email_local.py`
exercises every mail purpose against a loopback-only in-memory SMTP sink.

Password-reset lookup and SMTP dispatch run behind a bounded worker queue, so
eligible and missing-email public responses do not diverge on provider latency.
Queue drops and worker failures increment aggregate counters and emit only the
fixed warnings `auth_email_background_queue_full` or
`auth_email_background_task_failed`; exception bodies, recipients, challenge
ids, tokens, and codes are never logged. Production monitoring should alert on
either warning or a rising `failed`/`dropped` counter. A learner retry safely
creates or rotates another hashed challenge after an outage.

## Session and account controls

Browser credentials use an `HttpOnly`, `SameSite=Lax` cookie. Development and
tests use `ecg_session`; production uses `__Host-ecg_session` with `Secure`,
`Path=/`, and no `Domain`, enforcing a host-only cookie at the browser boundary.
During the one-way migration, a still-valid legacy production cookie is accepted
only when no host-prefixed cookie exists, then replaced and expired in the same
response; the host-prefixed cookie always wins when both are present. Account
controls support password change with full session rotation,
listing/revoking other sessions, logout-all, owner-scoped JSON progress export
after five-minute one-use password reauthorization, and permanent account
deletion after current-password plus exact-username confirmation. Export grants
are stored only as digests in `HttpOnly`, `SameSite=Strict` cookies and are
invalidated by credential/session changes.

Account deletion removes owned parent rows, dependent answers/messages,
guest-claim receipts, sessions, grants, auth challenges, and the user row in one
immediate transaction. Before that purge, the same transaction writes a durable
account-generation tombstone. It contains only a domain-separated SHA-256 digest
of the random internal user id, the deletion time, a bounded reason code, and a
boundary version—never the raw id, username, email, display name, or learning
data. SQLite guards on every direct owner table and every transitive child
ledger reject a request that authenticated before deletion and resumes after
the purge; the API returns a neutral `account_unavailable` response rather than
recreating a profile or exposing storage details. A new registration receives a
new random user-id generation and is unaffected.

The non-identifying tombstone is retained indefinitely as a security and erasure
boundary and is deliberately excluded from routine retention cleanup. Removing
it would make delayed/replayed writes able to resurrect the deleted generation.
Legacy guest erasure does not create an account tombstone, so the historical
`demo`/`g_*` cleanup and one-time migration behavior is unchanged. Deployment
owners must still document encrypted-backup retention, legal holds, and restore
suppression; live deletion is not advertised as instantaneous erasure from
backups.

## Retention and verification

Historical guest rows retain a configurable inactivity cleanup window. New
deployed learning does not create them. Cleanup is bounded, leased, transactional,
idempotent, and logs only aggregate counts. Authenticated learner records are
never time-deleted automatically. Production readiness requires both an approved
authenticated-retention policy reference and enabled retention automation.

Never-verified registration shells do not reserve usernames/emails forever.
After `ECG_UNVERIFIED_ACCOUNT_EXPIRY_DAYS` (seven days by default), cleanup may
remove only an account that is still unverified and has no session, guest-claim
receipt, assessment exposure, preference, attempt, tutor/mode record, or mastery
activity. Verified and legacy accounts, and any unverified account with real
learning evidence, are excluded. Established legacy accounts with an unverified
setup email are never treated as pending registrations. Credentialless public-
username reservations use the same bounded expiry and are removed without
creating learner records.

Focused tests cover atomic account/session rollback, stale-password session
prevention, legacy-hash upgrade, unique normalized email, verification one-time
use, OTP attempt exhaustion, reset anti-enumeration and session revocation,
credential-bound email change, SMTP readiness/templates/failure recovery,
legacy guest migration, deletion-winning concurrency across profile, attempt,
pathway, tutor, Guided activity, Training, Rapid, Clinical, and auth writes, and
an anonymous production route matrix spanning core progress, tutor, Guided,
Training, Rapid, and Clinical APIs.
