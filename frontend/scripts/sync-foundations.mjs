// Copies the canonical Foundations module (repo-root `foundations/`) into the
// checked-in deployment snapshot at `frontend/public/foundations/`, which Next
// serves at `/foundations/index.html`. Keeping the snapshot in Git makes a
// `frontend/`-root Vercel build self-contained; local/repository-root builds
// refresh it from the canonical source before dev/build.
//
// Canonical source stays at repo-root `foundations/`. Wired through
// `predev`/`prebuild`; when the parent directory is intentionally unavailable
// (an isolated frontend build), the verified checked-in snapshot is retained.
import { cpSync, rmSync, existsSync, mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { verifyFoundationsBoundary } from "./check-foundations-boundary.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const src = resolve(here, "..", "..", "foundations");
const dest = resolve(here, "..", "public", "foundations");

if (!existsSync(src)) {
  if (existsSync(resolve(dest, "index.html"))) {
    const result = verifyFoundationsBoundary(dest);
    console.log(`[sync-foundations] canonical source unavailable; verified checked-in snapshot (${result.cases} real PTB ECGs)`);
    process.exit(0);
  }
  console.error("[sync-foundations] neither canonical source nor deployment snapshot is available");
  process.exit(1);
}

rmSync(dest, { recursive: true, force: true });
mkdirSync(dest, { recursive: true });
// Ship the runnable module only — skip the markdown review docs (MODULE_GUIDE/TEXT).
cpSync(src, dest, { recursive: true, filter: (s) => !s.toLowerCase().endsWith(".md") });

const result = verifyFoundationsBoundary(dest);
console.log(`[sync-foundations] synced and verified ${result.cases} real PTB ECGs`, src, "->", dest);
