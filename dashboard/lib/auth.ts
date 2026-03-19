import NextAuth from "next-auth";
import Credentials from "next-auth/providers/credentials";

/**
 * Dashboard authentication via the LangSight users API.
 *
 * Login flow:
 *   1. User submits email + password on /login
 *   2. NextAuth calls /api/users/verify (unauthenticated endpoint)
 *   3. API bcrypt-verifies the password against the DB
 *   4. On success: NextAuth creates a JWT session with id, email, role
 *
 * First-run / bootstrap:
 *   If no users exist in the DB, the API startup routine creates the first
 *   admin from LANGSIGHT_ADMIN_EMAIL + LANGSIGHT_ADMIN_PASSWORD env vars.
 *   After that, all user management happens through the /settings/users panel.
 *
 * Adding users:
 *   Admin generates an invite via /settings/users → shares the invite URL →
 *   new user opens the URL, sets their password, account is created.
 *
 * AUTH_SECRET is required — generate with: openssl rand -base64 32
 */

const LANGSIGHT_API_URL = process.env.LANGSIGHT_API_URL ?? "http://localhost:8000";

export const { handlers, auth, signIn, signOut } = NextAuth({
  providers: [
    Credentials({
      credentials: {
        email:    { label: "Email",    type: "email" },
        password: { label: "Password", type: "password" },
      },
      async authorize(credentials, request) {
        const email    = credentials?.email    as string | undefined;
        const password = credentials?.password as string | undefined;

        if (!email || !password) return null;

        // Forward the real client IP so the backend can rate-limit per user,
        // not per dashboard container (which would share one bucket).
        const forwarded = (request as Request | undefined)?.headers?.get?.("x-forwarded-for")
          ?? (request as Request | undefined)?.headers?.get?.("x-real-ip")
          ?? "";

        try {
          const headers: Record<string, string> = { "Content-Type": "application/json" };
          if (forwarded) headers["X-Forwarded-For"] = forwarded;

          const res = await fetch(`${LANGSIGHT_API_URL}/api/users/verify`, {
            method: "POST",
            headers,
            body: JSON.stringify({ email, password }),
            // Short timeout — login should be fast
            signal: AbortSignal.timeout(5000),
          });

          if (!res.ok) return null;

          const user = await res.json() as {
            id: string;
            email: string;
            role: string;
            name: string;
          };

          return {
            id:    user.id,
            name:  user.name,
            email: user.email,
            role:  user.role,
          };
        } catch (err) {
          console.error("[auth] verify request failed:", err);
          return null;
        }
      },
    }),
  ],
  pages: { signIn: "/login" },
  callbacks: {
    jwt({ token, user }) {
      if (user) {
        token.role = (user as { role?: string }).role ?? "viewer";
        token.id   = user.id;
      }
      return token;
    },
    session({ session, token }) {
      if (session.user) {
        (session.user as typeof session.user & { role: string; id: string }).role =
          token.role as string;
        (session.user as typeof session.user & { role: string; id: string }).id =
          token.id as string;
      }
      // Expose id + role on the session so the proxy route can forward them
      (session as typeof session & { userId: string; userRole: string }).userId =
        token.id as string;
      (session as typeof session & { userId: string; userRole: string }).userRole =
        token.role as string;
      return session;
    },
  },
  session: { strategy: "jwt" },
  secret: process.env.AUTH_SECRET,
});
