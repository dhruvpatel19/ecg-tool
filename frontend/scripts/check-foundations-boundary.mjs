/**
 * Fail closed if the retired static Foundations prototype is published again.
 *
 * The native `/learn/foundations` runtime obtains opaque ECG capabilities from
 * the backend. A static case bundle would disclose assignment IDs, reports,
 * labels, and reviewed answer features to every authenticated browser.
 */
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, extname, resolve } from "node:path";

function fail(message) {
  throw new Error(`[foundations-boundary] ${message}`);
}

function filesUnder(directory) {
  if (!existsSync(directory)) return [];
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = resolve(directory, entry.name);
    return entry.isDirectory() ? filesUnder(path) : [path];
  });
}

export function verifyFoundationsBoundary(publicDirectory) {
  const legacyDirectory = resolve(publicDirectory, "foundations");
  const legacyFiles = filesUnder(legacyDirectory);
  if (legacyFiles.length) {
    fail(`retired public prototype is present (${legacyFiles.length} files)`);
  }

  const suspiciousJson = filesUnder(publicDirectory).filter((path) => {
    if (extname(path).toLowerCase() !== ".json" || statSync(path).size === 0) return false;
    const source = readFileSync(path, "utf8");
    return /[\"']ecg_id[\"']/.test(source)
      && /[\"'](?:features|report|category)[\"']/.test(source);
  });
  if (suspiciousJson.length) {
    fail(`answer-bearing ECG JSON exists under public (${suspiciousJson.join(", ")})`);
  }

  return { retiredStaticPrototype: true, publicLegacyFiles: 0, answerBearingJsonFiles: 0 };
}

const here = dirname(fileURLToPath(import.meta.url));
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const target = process.argv[2] ? resolve(process.argv[2]) : resolve(here, "..", "public");
  const result = verifyFoundationsBoundary(target);
  console.log(`[foundations-boundary] native-only public boundary verified (${result.publicLegacyFiles} legacy files)`);
}
