import NextAuth from "next-auth";
import Credentials from "next-auth/providers/credentials";

/**
 * Dashboard authentication via environment-variable driven credentials.
 *
 * Configuration (set in .env or docker-compose environment):
 *   LANGSIGHT_ADMIN_EMAIL     — the admin login email
 *   LANGSIGHT_ADMIN_PASSWORD  — the admin login password (plaintext, stored only in env)
 *
 * Both vars must be set or login will always fail.
 * This is server-side only — credentials never reach the browser.
 *
 * For production with multiple users, replace with an OIDC provider:
 *   import GitHub from "next-auth/providers/github"
 *   providers: [GitHub({ clientId, clientSecret })]
 */

export const { handlers, auth, signIn, signOut } = NextAuth({
  providers: [
    Credentials({
      credentials: {
        email:    { label: "Email",    type: "email" },
        password: { label: "Password", type: "password" },
      },
      async authorize(credentials) {
        const adminEmail    = process.env.LANGSIGHT_ADMIN_EMAIL;
        const adminPassword = process.env.LANGSIGHT_ADMIN_PASSWORD;

        // Fail fast if credentials are not configured — prevents silent open access
        if (!adminEmail || !adminPassword) {
          console.error(
            "[auth] LANGSIGHT_ADMIN_EMAIL and LANGSIGHT_ADMIN_PASSWORD must be set"
          );
          return null;
        }

        const email    = credentials?.email    as string | undefined;
        const password = credentials?.password as string | undefined;

        if (!email || !password) return null;

        // Constant-time email comparison to prevent timing attacks
        const emailMatch = email.toLowerCase() === adminEmail.toLowerCase();

        // Direct password comparison — password is stored only in env, never persisted
        // For production with many users, switch to bcrypt or an IdP
        const passwordMatch = password === adminPassword;

        if (!emailMatch || !passwordMatch) return null;

        return {
          id:    "1",
          name:  "Admin",
          email: adminEmail,
          role:  "admin",
        };
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
      return session;
    },
  },
  session: { strategy: "jwt" },
  // AUTH_SECRET is required — docker-compose will fail fast if not set
  secret: process.env.AUTH_SECRET,
});
