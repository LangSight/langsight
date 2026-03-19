/**
 * Public proxy for the accept-invite endpoint.
 *
 * This route does NOT require a NextAuth session — the user is setting
 * their password before they have an account. It simply forwards the
 * {token, password} body to FastAPI's public /api/users/accept-invite.
 *
 * The backend URL is kept server-side only (never in client bundle).
 */
import { NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.LANGSIGHT_API_URL ?? "http://localhost:8000";

export async function POST(req: NextRequest): Promise<NextResponse> {
  const body = await req.text();
  try {
    const res = await fetch(`${BACKEND}/api/users/accept-invite`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
      signal: AbortSignal.timeout(15_000),
    });
    const data = await res.text();
    return new NextResponse(data, {
      status: res.status,
      headers: { "Content-Type": res.headers.get("Content-Type") ?? "application/json" },
    });
  } catch {
    return NextResponse.json({ detail: "Backend unreachable" }, { status: 502 });
  }
}
