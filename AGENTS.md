# TRACE production safety contract

These rules apply to every change in this repository. Production reliability and
learner data integrity take priority over deployment speed.

## Publication path

1. GitHub is the source of truth. Do not run `vercel deploy`, `vercel --prod`, or
   otherwise upload a local workspace directly to Vercel unless the user explicitly
   authorizes a one-off exception in the current conversation.
2. Vercel production builds must come from the repository's configured Git
   integration and the `main` branch. Do not change the Vercel project, team, root
   directory, production alias, or Git connection as part of an application change.
3. Work on a `codex/*` feature branch. Push that branch, inspect the complete diff,
   and require green CI before merging to `main`. Never force-push `main`, rewrite
   published history, or bypass a required check.
4. A preview failure must not be "fixed" by giving a preview deployment production
   secrets or the production backend. TRACE intentionally requires an isolated
   preview backend. Use GitHub CI for pre-merge validation when an isolated preview
   is unavailable.

## Required pre-push checks

- Inspect `git status -sb`, the full diff/stat, and all untracked files. Stage only
  the intended product change. Do not use `git add -A` until the entire worktree has
  been reviewed as one coherent change set.
- Confirm `.env*`, `.vercel/`, Terraform `*.tfvars`/state/plan files, databases,
  credentials, SMTP keys, API keys, and generated build/test artifacts are ignored
  and absent from the staged diff.
- Run `git diff --check` and inspect `git diff --cached --check` after staging.
- Backend: run the full Python test suite for backend-impacting changes.
- Frontend: run type checking, lint, the production Next.js build, and the relevant
  Playwright tests. Authentication, proxy, routing, or shell changes require the
  auth/public-route browser suite.
- Infrastructure: run shell syntax checks for changed deployment scripts and
  `terraform fmt -check` plus `terraform validate` for Terraform changes. Review a
  plan before any apply; do not accept replacement or destruction of protected
  production resources without explicit user approval.
- Do not push if a required gate is red, skipped without a documented reason, or
  relies on a local secret that GitHub/Vercel will not have.

## Environment and secret safety

- Before a production merge, verify the existing Vercel project is
  `challengeat7-4423s-projects/ecg-tool`, its Root Directory remains `frontend`, and
  `ECG_BACKEND_API_BASE` plus `ECG_ORIGIN_SHARED_SECRET` exist for Production.
- Vercel CLI pulls may redact encrypted values to empty strings. Treat `Encrypted`
  in `vercel env ls production` as presence; never replace a production value with
  a blank locally pulled placeholder.
- Backend email/LLM credentials belong in GCP Secret Manager, never Vercel, Git,
  Terraform variables, VM metadata, command output, or documentation.
- Tell the user before enabling a service or infrastructure change that can add
  cost. Prefer bounded/free/serverless options when function and student experience
  remain equivalent.

## Deployment order and verification

1. Preserve backward compatibility across the deployment boundary. When both sides
   change, deploy and verify the backward-compatible backend first, then merge the
   frontend.
2. After merge, watch GitHub checks and the Git-triggered Vercel production build.
   Confirm that the new deployment belongs to the expected project and commit before
   accepting its production alias.
3. Smoke-test the public landing page, sign-in, registration, verification link,
   password reset, authenticated session persistence, dashboard redirect, API proxy,
   backend `/readyz`, and at least one learning-mode launch.
4. Stop rollout or restore the last known-good production deployment if health,
   auth/session persistence, core navigation, or protected learner-data checks fail.
   Do not stack speculative fixes onto a broken production release.
5. Record the deployed commit, checks, live URLs, known limitations, and rollback
   point in the handoff.

## Data protection

- Never delete, reset, replace, or reformat the learner database, persistent disk,
  corpus release, backup bucket, or Secret Manager values during an application
  deployment.
- Preserve the immutable backend-image digest and the previous recovery digest.
- Use disposable, clearly named test accounts for live auth checks and delete them
  after verification. Do not inspect unrelated mailbox content.
