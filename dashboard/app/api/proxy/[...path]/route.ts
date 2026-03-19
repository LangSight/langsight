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
import { NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.LANGSIGHT_API_URL ?? "http://localhost:8000";
const BACKEND_API_KEY = process.env.LANGSIGHT_API_KEY ?? "";

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
