import type { NextAuthConfig } from "next-auth";

/**
 * Edge-compatible auth config — no Node.js-only providers here.
 *
 * Middleware runs on Edge Runtime which does not support Node.js crypto.
 * Credentials provider's `authorize()` uses Node.js fetch + bcrypt via the
 * LangSight API, so it lives in auth.ts (Node.js runtime only).
 *
 * This file contains only the session strategy and callbacks that the
 * Edge middleware needs to read JWT sessions — no provider-specific code.
 */
export const authConfig: NextAuthConfig = {
  providers: [],  // providers added in auth.ts (Node.js runtime)
  pages: { signIn: "/login" },
  callbacks: {
    authorized({ auth, request: { nextUrl } }) {
      const isLoggedIn = !!auth?.user;
      const isAuthPage =
        nextUrl.pathname.startsWith("/login") ||
        nextUrl.pathname.startsWith("/accept-invite");
      if (!isLoggedIn && !isAuthPage) return false;
      return true;
    },
  },
  session: { strategy: "jwt" },
};
