/**
 * Authenticated proxy to the LangSight FastAPI backend.
 *
 * All dashboard API calls go through this route. It:
 *   1. Reads the NextAuth session server-side (no client-side token exposure)
 *   2. Returns 401 if the user is not authenticated
 *   3. Forwards the request to FastAPI with:
 *      - X-User-Id:   the authenticated user's ID
 *      - X-User-Role: the authenticated user's role (admin / viewer)
 *      - X-API-Key:   optional backend API key (when LANGSIGHT_API_KEYS is set)
 *
 * Usage: frontend calls /api/proxy/health/servers
 *        → proxied to  http://localhost:8000/api/health/servers
 */
import { auth } from "@/lib/auth";
import { createHmac } from "crypto";
import { NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.LANGSIGHT_API_URL ?? "http://localhost:8000";
// LANGSIGHT_API_KEYS may be a comma-separated list; the proxy needs exactly one
// key. Split and take the first to avoid forwarding "key1,key2" as a single key.
const BACKEND_API_KEY = (process.env.LANGSIGHT_API_KEY ?? "").split(",")[0].trim();
// Shared secret for HMAC-signing proxy headers — must match LANGSIGHT_PROXY_SECRET on API side.
const PROXY_SECRET = process.env.LANGSIGHT_PROXY_SECRET ?? "";

type SessionWithMeta = {
  userId?: string;
  userRole?: string;
};

async function proxyRequest(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
): Promise<NextResponse> {
  // Verify session
  const session = await auth();
  if (!session) {
    return NextResponse.json({ detail: "Authentication required" }, { status: 401 });
  }

  const { userId, userRole } = session as typeof session & SessionWithMeta;

  // Build upstream URL
  const { path } = await params;
  const upstreamPath = path.join("/");
  const search = req.nextUrl.search ?? "";
  const upstream = `${BACKEND}/api/${upstreamPath}${search}`;

  // Build headers to forward
  const headers: Record<string, string> = {
    "Content-Type": req.headers.get("Content-Type") ?? "application/json",
  };
  if (userId)       headers["X-User-Id"]   = userId;
  if (userRole)     headers["X-User-Role"] = userRole;
  if (BACKEND_API_KEY) headers["X-API-Key"] = BACKEND_API_KEY;

  // HMAC-sign the proxy headers so FastAPI can verify they came from this proxy,
  // not a forged request from within the trusted CIDR.
  if (PROXY_SECRET && userId) {
    const ts = Math.floor(Date.now() / 1000).toString();
    const payload = `${userId}:${userRole ?? ""}:${ts}`;
    const sig = createHmac("sha256", PROXY_SECRET).update(payload).digest("hex");
    headers["X-Proxy-Timestamp"] = ts;
    headers["X-Proxy-Signature"] = sig;
  }

  // Forward only the first entry of X-Forwarded-For (the real client IP).
  // Forwarding the full header verbatim allows spoofing: a client can prepend
  // arbitrary IPs to the list and inflate the rate-limit bucket. Taking only
  // the first hop — set by the edge/load balancer — is safe.
  const rawForwarded = req.headers.get("x-forwarded-for") ?? req.headers.get("x-real-ip");
  const clientIp = rawForwarded ? rawForwarded.split(",")[0].trim() : null;
  if (clientIp) headers["X-Forwarded-For"] = clientIp;

  // Forward request body for POST / PATCH / PUT
  let body: string | undefined;
  if (["POST", "PUT", "PATCH"].includes(req.method)) {
    body = await req.text();
  }

  try {
    const res = await fetch(upstream, {
      method: req.method,
      headers,
      body,
      signal: AbortSignal.timeout(30_000),
      cache: "no-store",
    });

    // 204 / 304 must be returned with no body — the Response constructor throws
    // if you pass a body string for these status codes (Next.js Edge Runtime).
    if (res.status === 204 || res.status === 304) {
      return new NextResponse(null, { status: res.status });
    }

    // Stream response back
    const data = await res.text();
    return new NextResponse(data, {
      status: res.status,
      headers: { "Content-Type": res.headers.get("Content-Type") ?? "application/json" },
    });
  } catch (err) {
    // Log method + path only — never the full constructed URL which may contain IDs
    const logPath = `/${upstreamPath}${search}`;
    console.error("[proxy] upstream request failed:", req.method, logPath, (err as Error)?.message);
    return NextResponse.json(
      { detail: "Backend unreachable" },
      { status: 502 }
    );
  }
}

export const GET     = proxyRequest;
export const POST    = proxyRequest;
export const PUT     = proxyRequest;
export const PATCH   = proxyRequest;
export const DELETE  = proxyRequest;
