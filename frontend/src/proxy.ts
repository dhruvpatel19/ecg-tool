import { NextRequest, NextResponse } from "next/server";

const CONFIGURED_BACKEND_API_BASE = process.env.ECG_BACKEND_API_BASE ?? process.env.BACKEND_API_BASE;
const ORIGIN_SHARED_SECRET = process.env.ECG_ORIGIN_SHARED_SECRET;
const FOUNDATIONS_AUTH_TIMEOUT_MS = 5_000;
const SESSION_COOKIE_NAMES = ["__Host-ecg_session", "ecg_session"] as const;

function contentSecurityPolicy(nonce: string, allowSameOriginEmbedding: boolean) {
  const developmentEval = process.env.NODE_ENV === "development" ? " 'unsafe-eval'" : "";
  const frameAncestors = allowSameOriginEmbedding ? "'self'" : "'none'";

  return [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}'${developmentEval}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self' data:",
    "connect-src 'self'",
    "media-src 'self'",
    "worker-src 'self' blob:",
    "frame-src 'self'",
    `frame-ancestors ${frameAncestors}`,
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "manifest-src 'self'",
  ].join("; ");
}

function foundationAssetRequest(request: NextRequest): boolean {
  const path = request.nextUrl.pathname;
  return path === "/foundations" || path.startsWith("/foundations/");
}

function backendOrigin(frontendOrigin: string): string | null {
  if (CONFIGURED_BACKEND_API_BASE) {
    try {
      const configured = new URL(CONFIGURED_BACKEND_API_BASE);
      if (configured.origin === frontendOrigin) return null;
      if (process.env.VERCEL && configured.protocol !== "https:") return null;
      return configured.origin;
    } catch {
      return null;
    }
  }
  return process.env.VERCEL ? null : "http://127.0.0.1:8000";
}

function sessionCookieHeader(request: NextRequest): string | null {
  const cookies = SESSION_COOKIE_NAMES.flatMap((name) => {
    const cookie = request.cookies.get(name);
    return cookie ? [`${name}=${cookie.value}`] : [];
  });
  return cookies.length ? cookies.join("; ") : null;
}

async function foundationsAccessDenial(request: NextRequest): Promise<NextResponse | null> {
  const cookies = sessionCookieHeader(request);
  if (!cookies) {
    return NextResponse.json(
      { detail: "Sign in to open learning content.", code: "authentication_required" },
      { status: 401 },
    );
  }

  const backend = backendOrigin(request.nextUrl.origin);
  if (!backend) {
    return NextResponse.json(
      { detail: "Learning content is temporarily unavailable.", code: "backend_not_configured" },
      { status: 503 },
    );
  }

  const headers = new Headers({
    accept: "application/json",
    cookie: cookies,
  });
  if (ORIGIN_SHARED_SECRET) headers.set("x-ecg-origin-key", ORIGIN_SHARED_SECRET);

  let access: Response;
  try {
    access = await fetch(`${backend}/auth/learning-access`, {
      method: "GET",
      headers,
      cache: "no-store",
      redirect: "manual",
      signal: AbortSignal.timeout(FOUNDATIONS_AUTH_TIMEOUT_MS),
    });
  } catch {
    return NextResponse.json(
      { detail: "Learning content is temporarily unavailable.", code: "backend_unavailable" },
      { status: 503 },
    );
  }

  if (access.status === 204) return null;
  if (access.status === 401 || access.status === 403) {
    return NextResponse.json(
      {
        detail: access.status === 401
          ? "Sign in to open learning content."
          : "Verify your account before opening learning content.",
        code: access.status === 401 ? "authentication_required" : "account_verification_required",
      },
      { status: access.status },
    );
  }
  return NextResponse.json(
    { detail: "Learning content is temporarily unavailable.", code: "learning_access_unavailable" },
    { status: 503 },
  );
}

function applySecurityHeaders(
  response: NextResponse,
  nonce: string,
  foundationAsset: boolean,
): NextResponse {
  response.headers.set("Content-Security-Policy", contentSecurityPolicy(nonce, foundationAsset));
  response.headers.set("X-Content-Type-Options", "nosniff");
  response.headers.set("X-Frame-Options", foundationAsset ? "SAMEORIGIN" : "DENY");
  response.headers.set("Referrer-Policy", "no-referrer");
  response.headers.set(
    "Permissions-Policy",
    "accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=(), browsing-topics=()",
  );
  if (foundationAsset) {
    response.headers.set("Cache-Control", "private, no-store");
    response.headers.set("Pragma", "no-cache");
    response.headers.set("Vary", "Cookie");
  }
  if (process.env.NODE_ENV === "production") {
    response.headers.set("Strict-Transport-Security", "max-age=31536000");
  }
  return response;
}

export async function proxy(request: NextRequest) {
  const nonce = crypto.randomUUID();
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);

  const foundationAsset = foundationAssetRequest(request);
  if (foundationAsset) {
    const denial = await foundationsAccessDenial(request);
    if (denial) return applySecurityHeaders(denial, nonce, true);
  }

  const response = NextResponse.next({
    request: { headers: requestHeaders },
  });
  return applySecurityHeaders(response, nonce, foundationAsset);
}

export const config = {
  matcher: [
    {
      source: "/((?!_next/static|_next/image|favicon.ico).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
