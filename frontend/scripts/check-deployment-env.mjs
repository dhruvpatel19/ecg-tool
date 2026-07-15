// Fail a hosted build before it can publish a frontend whose same-origin API
// proxy points back to localhost. Local builds keep the ergonomic development
// default; Vercel deployments must name an HTTPS backend explicitly.

import { isIP } from "node:net";

const isVercel = Boolean(process.env.VERCEL);
const backend = process.env.ECG_BACKEND_API_BASE ?? process.env.BACKEND_API_BASE;
const originSecret = process.env.ECG_ORIGIN_SHARED_SECRET;

if (!isVercel) {
  console.log("[deployment-env] local build; hosted-backend gate skipped");
  process.exit(0);
}

const misplacedMailVariables = Object.keys(process.env)
  .filter((name) => name.startsWith("AUTH_EMAIL_") || name.startsWith("AUTH_SMTP_"))
  .sort();
if (misplacedMailVariables.length > 0) {
  console.error(
    `[deployment-env] backend mail settings must not be copied into Vercel: ${misplacedMailVariables.join(", ")}`,
  );
  process.exit(1);
}

if (!backend) {
  console.error("[deployment-env] ECG_BACKEND_API_BASE is required on Vercel");
  process.exit(1);
}

let url;
try {
  url = new URL(backend);
} catch {
  console.error("[deployment-env] ECG_BACKEND_API_BASE must be an absolute URL");
  process.exit(1);
}

if (url.protocol !== "https:") {
  console.error("[deployment-env] ECG_BACKEND_API_BASE must use HTTPS on Vercel");
  process.exit(1);
}

if (
  url.username ||
  url.password ||
  url.search ||
  url.hash ||
  (url.pathname && url.pathname !== "/") ||
  (url.port && url.port !== "443")
) {
  console.error(
    "[deployment-env] ECG_BACKEND_API_BASE must be a root HTTPS origin without credentials, query, fragment, or a nonstandard port",
  );
  process.exit(1);
}

const backendHostname = url.hostname.toLowerCase();
if (
  isIP(backendHostname) ||
  !backendHostname.includes(".") ||
  backendHostname === "localhost" ||
  backendHostname.endsWith(".local")
) {
  console.error("[deployment-env] ECG_BACKEND_API_BASE must use a public DNS hostname");
  process.exit(1);
}

const vercelHostnames = [
  process.env.VERCEL_URL,
  process.env.VERCEL_BRANCH_URL,
  process.env.VERCEL_PROJECT_PRODUCTION_URL,
]
  .filter(Boolean)
  .map((value) => value.replace(/^https?:\/\//, "").split("/")[0].split(":")[0].toLowerCase());
if (vercelHostnames.includes(backendHostname)) {
  console.error("[deployment-env] backend origin must not point back to this Vercel deployment");
  process.exit(1);
}

if (
  process.env.VERCEL_ENV &&
  process.env.VERCEL_ENV !== "production" &&
  process.env.ECG_ALLOW_ISOLATED_PREVIEW_BACKEND !== "1"
) {
  console.error(
    "[deployment-env] Preview deployments require an isolated backend and ECG_ALLOW_ISOLATED_PREVIEW_BACKEND=1; production credentials are not allowed",
  );
  process.exit(1);
}

if (process.env.NEXT_PUBLIC_API_BASE) {
  console.error(
    "[deployment-env] leave NEXT_PUBLIC_API_BASE unset; browser traffic must use the same-origin /api/backend proxy",
  );
  process.exit(1);
}

if (!originSecret || originSecret.length < 32 || /[\u0000-\u001f\u007f]/.test(originSecret)) {
  console.error(
    "[deployment-env] ECG_ORIGIN_SHARED_SECRET (32+ characters) is required in the Vercel server runtime",
  );
  process.exit(1);
}

console.log("[deployment-env] hosted API proxy configuration is valid");
