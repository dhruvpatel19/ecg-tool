# TRACE authenticated data retention policy

Policy version: `demo-v1`
Effective date: 2026-07-15
Applies to: the TRACE hosted demonstration and direct student accounts

## Active accounts

TRACE retains a verified student's account and learning record while the account
exists. The record includes the email address, password hash, profile settings,
answers, annotations, competency evidence, practice history, tutor conversations,
and security/session metadata needed to operate and protect the account. TRACE does
not automatically delete a verified account merely because the student has not
used it recently.

Unverified registration shells that have no learning activity may be removed after
seven days. Expired authentication challenges, sessions, export grants, and legacy
anonymous records are removed by the bounded cleanup rules documented in
`docs/ACCOUNT_LIFECYCLE.md`.

## Student deletion and deprovisioning

A student may permanently delete the live account from account settings after
password confirmation. The application removes the account and its owned learning
data in one transaction and retains only a non-identifying deletion-boundary digest
that prevents delayed requests or a later restore from recreating the deleted
account generation.

This direct-to-student demonstration has no separate institutional roster. Student
deletion is therefore the deprovisioning mechanism. A future institutional launch
must add and document the institution's own deprovisioning process before enrollment.

## Backups and final expiry

- Application-consistent encrypted learner-database backups expire after 90 days.
- Crash-consistent persistent-disk snapshots expire after 14 days.
- Restores must preserve deletion-boundary tombstones and must not intentionally
  re-enable an account generation deleted before the recovery point.
- Deleted personal and learning data may therefore remain inaccessible in protected
  backups until the applicable backup or snapshot expires; it is not represented as
  erased from every backup immediately.

## Legal holds and exceptions

No legal-hold workflow is enabled for this demonstration. If a legal or regulatory
preservation requirement applies, public enrollment must be paused until the owner
documents the authority, scope, access controls, student notice, and eventual release
of the hold. This policy does not authorize indefinite retention for an unspecified
future purpose.

## Review

Review this policy before a public or institutional launch, whenever backup lifecycles
change, and at least annually. A controlled-domain sender, provider privacy/DPA review,
and named institutional data owner remain launch requirements beyond the demonstration.
