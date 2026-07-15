import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const routePath = resolve(here, "../src/app/api/backend/[...path]/route.ts");
const source = readFileSync(routePath, "utf8");
const functionMatch = source.match(
  /function learnerCookieHeader[\s\S]*?\n}\n\nfunction learnerResponseHeaders/,
);

if (!functionMatch) {
  throw new Error("[auth-cookie-proxy] learner cookie allowlist function is missing");
}

const names = [...functionMatch[0].matchAll(/name === "([^"]+)"/g)]
  .map((match) => match[1])
  .sort();
const expected = [
  "__Host-ecg_session",
  "ecg_export_auth",
  "ecg_guest",
  "ecg_session",
].sort();

if (JSON.stringify(names) !== JSON.stringify(expected)) {
  throw new Error(
    `[auth-cookie-proxy] cookie allowlist mismatch: ${JSON.stringify(names)}`,
  );
}
if (!source.includes('headers.set("cookie", cookies)')) {
  throw new Error("[auth-cookie-proxy] filtered cookies are not forwarded upstream");
}
if (!source.includes("upstream.headers.getSetCookie()")) {
  throw new Error("[auth-cookie-proxy] repeatable Set-Cookie forwarding is missing");
}

console.log("[auth-cookie-proxy] production, legacy, guest, and export cookie boundary verified");
