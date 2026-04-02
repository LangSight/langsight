// Import auth from the edge-compatible config, NOT from lib/auth.
// lib/auth.ts uses Credentials provider which imports Node.js crypto and
// cannot run on Edge Runtime.  NextAuth(authConfig) here only needs to
// read/verify the JWT session — no provider-specific code required.
import NextAuth from "next-auth";
import { authConfig } from "@/lib/auth.config";
import { NextResponse } from "next/server";

const { auth } = NextAuth(authConfig);

export default auth((req) => {
  if (
    process.env.NODE_ENV !== "production"
    && process.env.PLAYWRIGHT_TEST === "1"
    && req.cookies.get("langsight_e2e_auth")?.value === "1"
  ) {
    return NextResponse.next();
  }

  const isLoggedIn = !!req.auth;
  const { pathname } = req.nextUrl;
  const isAuthPage = pathname.startsWith("/login") || pathname.startsWith("/accept-invite");

  if (!isLoggedIn && !isAuthPage) {
    return NextResponse.redirect(new URL("/login", req.url));
  }
  if (isLoggedIn && isAuthPage) {
    return NextResponse.redirect(new URL("/", req.url));
  }
  return NextResponse.next();
});

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico).*)"],
};
