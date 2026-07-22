// Compatibility entry point retained for older local/CI commands. Foundations
// is native now; this command verifies that no retired static bundle can be
// republished instead of copying the repository-root prototype into `public`.
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { verifyFoundationsBoundary } from "./check-foundations-boundary.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const publicDirectory = resolve(here, "..", "public");
const result = verifyFoundationsBoundary(publicDirectory);
console.log(`[sync-foundations] native-only boundary verified (${result.publicLegacyFiles} legacy files)`);
