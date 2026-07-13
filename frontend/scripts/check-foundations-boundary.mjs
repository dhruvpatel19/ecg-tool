import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const REQUIRED_CATEGORIES = [
  "normal",
  "brady",
  "tachy",
  "non_sinus",
  "long_pr",
  "wide_qrs",
  "left_axis",
  "right_axis",
  "noisy",
];
const REQUIRED_LEADS = ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"];

function fail(message) {
  throw new Error(`[foundations-boundary] ${message}`);
}

export function verifyFoundationsBoundary(directory) {
  const bundlePath = resolve(directory, "data", "cases.json");
  const bundle = JSON.parse(readFileSync(bundlePath, "utf8"));
  const cases = Array.isArray(bundle.cases) ? bundle.cases : [];
  const leads = Array.isArray(bundle.leads) ? bundle.leads : [];

  if (leads.length !== REQUIRED_LEADS.length || REQUIRED_LEADS.some((lead) => !leads.includes(lead))) {
    fail("the teaching bundle must contain the calibrated 12-lead contract");
  }
  if (cases.length < REQUIRED_CATEGORIES.length) fail("the teaching bundle is empty or incomplete");

  const categories = new Set();
  for (const record of cases) {
    if (
      !record ||
      record.source !== "ptbxl" ||
      record.source_version !== "1.0.3" ||
      record.license_id !== "CC-BY-4.0" ||
      !record.ecg_id
    ) {
      fail("every learner ECG must carry the pinned PTB-XL provenance contract");
    }
    const hasTwelveLeadMedian = record.median && REQUIRED_LEADS.every(
      (lead) => Array.isArray(record.median[lead]) && record.median[lead].length,
    );
    const hasRealRhythmStrip = Array.isArray(record.lead_ii) && record.lead_ii.length;
    if (record.category === "noisy" ? !hasRealRhythmStrip : !hasTwelveLeadMedian) {
      fail(`ECG ${record.ecg_id} does not contain the real waveform required by its teaching task`);
    }
    categories.add(record.category);
  }
  const missing = REQUIRED_CATEGORIES.filter((category) => !categories.has(category));
  if (missing.length) fail(`the teaching bundle is missing categories: ${missing.join(", ")}`);

  const dataSource = readFileSync(resolve(directory, "data.js"), "utf8");
  const appSource = readFileSync(resolve(directory, "app.js"), "utf8");
  const scenesSource = readFileSync(resolve(directory, "scenes.js"), "utf8");
  const combined = `${dataSource}\n${appSource}\n${scenesSource}`;
  const forbidden = [
    /fall(?:ing)? back to synthetic/i,
    /fallback to synthetic/i,
    /synthetic case/i,
    /E\.renderLead\s*\(/,
    /E\.render12\s*\(/,
  ];
  const hit = forbidden.find((pattern) => pattern.test(combined));
  if (hit) fail(`learner scene source contains a forbidden synthetic fallback (${hit})`);
  if (!appSource.includes("No simulated ECG will replace missing real data.")) {
    fail("missing-data behavior must visibly fail closed");
  }
  if (!scenesSource.includes("Interactive mechanism schematic — not a patient ECG.")) {
    fail("authored mechanism drawings must be visibly distinguished from patient ECGs");
  }

  return { cases: cases.length, categories: categories.size };
}

const here = dirname(fileURLToPath(import.meta.url));
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const target = process.argv[2] ? resolve(process.argv[2]) : resolve(here, "..", "public", "foundations");
  const result = verifyFoundationsBoundary(target);
  console.log(`[foundations-boundary] verified ${result.cases} real PTB-XL ECGs across ${result.categories} categories`);
}
