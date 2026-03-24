/**
 * Streaming SSE proxy for /api/live/events.
 *
 * Uses an explicit ReadableStream to pipe the backend SSE stream chunk-by-chunk.
 * next NextResponse(res.body) is unreliable in Next.js production — it may buffer
 * the entire response before sending. The explicit ReadableStream approach flushes
 * each chunk immediately as it arrives from the backend.
 */
import { auth } from "@/lib/auth";
import { NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.LANGSIGHT_API_URL ?? "http://localhost:8000";
const BACKEND_API_KEY = (process.env.LANGSIGHT_API_KEY ?? "").split(",")[0].trim();

type SessionWithMeta = { userId?: string; userRole?: string };

export const dynamic = "force-dynamic";

export async function GET(req: NextRequest): Promise<NextResponse> {
  const session = await auth();
  if (!session) {
    return NextResponse.json({ detail: "Authentication required" }, { status: 401 });
  }

  const { userId, userRole } = session as typeof session & SessionWithMeta;

  const projectId = req.nextUrl.searchParams.get("project_id");
  const upstream = `${BACKEND}/api/live/events${projectId ? `?project_id=${encodeURIComponent(projectId)}` : ""}`;

  const headers: Record<string, string> = { Accept: "text/event-stream" };
  if (userId) headers["X-User-Id"] = userId;
  if (userRole) headers["X-User-Role"] = userRole;
  if (BACKEND_API_KEY) headers["X-API-Key"] = BACKEND_API_KEY;

  let res: Response;
  try {
    res = await fetch(upstream, { headers, cache: "no-store" });
  } catch {
    return NextResponse.json({ detail: "Backend unreachable" }, { status: 502 });
  }

  if (!res.ok || !res.body) {
    return NextResponse.json({ detail: "SSE stream unavailable" }, { status: res.status });
  }

  // Explicit ReadableStream — enqueues each chunk immediately as it arrives.
  // This is required for SSE in Next.js production; passing res.body directly
  // may buffer the stream before sending to the client.
  const reader = res.body.getReader();
  const stream = new ReadableStream({
    async start(controller) {
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          controller.enqueue(value);
        }
      } catch {
        // Client disconnected or backend closed — normal for SSE
      } finally {
        controller.close();
      }
    },
    cancel() {
      reader.cancel().catch(() => {});
    },
  });

  return new NextResponse(stream, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      "Connection": "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
