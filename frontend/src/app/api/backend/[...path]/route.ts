import { NextRequest } from "next/server";
import { isIP } from "node:net";

const CONFIGURED_BACKEND_API_BASE =
  process.env.ECG_BACKEND_API_BASE ?? process.env.BACKEND_API_BASE;
const ORIGIN_SHARED_SECRET = process.env.ECG_ORIGIN_SHARED_SECRET;
const MAX_PROXY_BODY_BYTES = 1024 * 1024;
const UPSTREAM_TIMEOUT_MS = 45_000;
const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

class ProxyBodyTooLarge extends Error {}

function isSameOriginMutation(request: NextRequest): boolean {
  if (SAFE_METHODS.has(request.method)) return true;

  // SameSite cookies already block ordinary cross-site fetches, but validating
  // browser provenance here also prevents login-CSRF and protects deployments
  // if cookie policy changes later. Requests without browser provenance headers
  // remain available to trusted CLI/health tooling and carry no ambient cookie
  // unless that caller explicitly supplies one.
  const origin = request.headers.get("origin");
  if (origin) {
    try {
      if (new URL(origin).origin !== request.nextUrl.origin) return false;
    } catch {
      return false;
    }
  }
  const fetchSite = request.headers.get("sec-fetch-site");
  if (fetchSite && fetchSite !== "same-origin") return false;
  return true;
}

function learnerCookieHeader(raw: string | null): string | null {
  if (!raw) return null;
  const allowed = raw
    .split(";")
    .map((part) => part.trim())
    .filter((part) => {
      const name = part.slice(0, part.indexOf("="));
      return name === "ecg_session" || name === "ecg_guest";
    });
  return allowed.length ? allowed.join("; ") : null;
}

function learnerResponseHeaders(upstream: Response): Headers {
  const headers = new Headers();
  for (const name of [
    "cache-control",
    "content-disposition",
    "content-language",
    "content-type",
    "retry-after",
    "www-authenticate",
  ]) {
    const value = upstream.headers.get(name);
    if (value) headers.set(name, value);
  }

  // Set-Cookie is intentionally the only repeatable upstream header. Node's
  // server-side Headers implementation exposes each cookie separately, which
  // preserves simultaneous session + guest-identity rotation responses.
  for (const cookie of upstream.headers.getSetCookie()) {
    headers.append("set-cookie", cookie);
  }
  if (!headers.has("cache-control")) headers.set("cache-control", "no-store");
  return headers;
}

async function boundedRequestBody(request: NextRequest): Promise<ArrayBuffer | undefined> {
  if (request.method === "GET" || request.method === "HEAD" || !request.body) return undefined;
  const advertised = request.headers.get("content-length");
  if (advertised && (!/^\d+$/.test(advertised) || Number(advertised) > MAX_PROXY_BODY_BYTES)) {
    throw new ProxyBodyTooLarge();
  }

  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > MAX_PROXY_BODY_BYTES) {
      await reader.cancel("request body exceeds proxy limit");
      throw new ProxyBodyTooLarge();
    }
    chunks.push(value);
  }
  const body = new ArrayBuffer(total);
  const view = new Uint8Array(body);
  let offset = 0;
  for (const chunk of chunks) {
    view.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return body;
}

function backendApiBase(frontendOrigin: string): string | null {
  if (CONFIGURED_BACKEND_API_BASE) {
    try {
      const configured = new URL(CONFIGURED_BACKEND_API_BASE);
      if (process.env.VERCEL) {
        const invalidShape = configured.protocol !== "https:"
          || Boolean(configured.username || configured.password || configured.search || configured.hash)
          || (configured.pathname !== "" && configured.pathname !== "/")
          || Boolean(configured.port && configured.port !== "443");
        const hostname = configured.hostname.toLowerCase();
        const invalidHost = isIP(hostname) !== 0
          || !hostname.includes(".")
          || hostname === "localhost"
          || hostname.endsWith(".local");
        const unsafePreview = Boolean(
          process.env.VERCEL_ENV
          && process.env.VERCEL_ENV !== "production"
          && process.env.ECG_ALLOW_ISOLATED_PREVIEW_BACKEND !== "1",
        );
        if (invalidShape || invalidHost || configured.origin === frontendOrigin || unsafePreview) return null;
      }
      return configured.origin;
    } catch {
      return null;
    }
  }
  // `next start` remains convenient on a workstation. Vercel must never fall
  // through to its own loopback interface; the prebuild gate also rejects that
  // deployment before publication.
  return process.env.VERCEL ? null : "http://127.0.0.1:8000";
}

type RouteContext = {
  params: Promise<{ path?: string[] }>;
};

async function proxy(request: NextRequest, context: RouteContext) {
  if (!isSameOriginMutation(request)) {
    return Response.json(
      { detail: "Cross-site state changes are not allowed", code: "cross_site_request_rejected" },
      { status: 403 },
    );
  }
  const backendBase = backendApiBase(request.nextUrl.origin);
  if (!backendBase) {
    return Response.json(
      { detail: "Hosted backend is not configured", code: "backend_not_configured" },
      { status: 503 },
    );
  }
  const { path = [] } = await context.params;
  const sourceUrl = new URL(request.url);
  const targetUrl = new URL(`${backendBase}/${path.map(encodeURIComponent).join("/")}`);
  targetUrl.search = sourceUrl.search;

  // Build an explicit end-to-end allowlist. This drops every hop-by-hop and
  // Vercel platform/geolocation header instead of trying to enumerate them.
  const headers = new Headers();
  for (const name of ["accept", "authorization", "content-type"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  const cookies = learnerCookieHeader(request.headers.get("cookie"));
  if (cookies) headers.set("cookie", cookies);
  // Injected only by the server runtime. Never trust a browser-supplied value
  // and never expose this as a NEXT_PUBLIC setting.
  if (ORIGIN_SHARED_SECRET) {
    headers.set("x-ecg-origin-key", ORIGIN_SHARED_SECRET);
    // Vercel documents this platform header as the canonical public client IP
    // and overwrites its forwarding identity to prevent spoofing. Forward only
    // one syntactically valid address in a private, server-to-server header.
    const vercelClientIp = process.env.VERCEL
      ? request.headers.get("x-vercel-forwarded-for")?.trim()
      : undefined;
    if (vercelClientIp && isIP(vercelClientIp)) {
      headers.set("x-ecg-client-ip", vercelClientIp);
    }
  }

  let body: ArrayBuffer | undefined;
  try {
    body = await boundedRequestBody(request);
  } catch (error) {
    if (error instanceof ProxyBodyTooLarge) {
      return Response.json(
        { detail: "Request body exceeds the 1 MiB proxy limit", code: "request_too_large" },
        { status: 413 },
      );
    }
    throw error;
  }
  let upstream: Response;
  try {
    upstream = await fetch(targetUrl, {
      method: request.method,
      headers,
      body,
      cache: "no-store",
      redirect: "manual",
      signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
    });
  } catch {
    return Response.json(
      { detail: "Hosted backend is unavailable", code: "backend_unavailable" },
      { status: 502 },
    );
  }

  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: learnerResponseHeaders(upstream),
  });
}

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 60;
export const preferredRegion = "iad1";
export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
