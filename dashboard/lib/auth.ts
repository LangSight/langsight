import NextAuth from "next-auth";
import Credentials from "next-auth/providers/credentials";

// Demo users — replace with real DB in production
const DEMO_USERS = [
  { id: "1", name: "Suman Sahoo", email: "admin@langsight.io", role: "admin" },
  { id: "2", name: "Demo User",   email: "demo@langsight.io",  role: "viewer" },
];

export const { handlers, auth, signIn, signOut } = NextAuth({
  providers: [
    Credentials({
      credentials: {
        email:    { label: "Email",    type: "email" },
        password: { label: "Password", type: "password" },
      },
      async authorize(credentials) {
        // Demo mode: any known email + any password works
        const user = DEMO_USERS.find(u => u.email === credentials?.email);
        if (!user) return null;
        return user;
      },
    }),
  ],
  pages: { signIn: "/login" },
  callbacks: {
    jwt({ token, user }) {
      if (user) {
        token.role  = (user as typeof DEMO_USERS[0]).role;
        token.id    = user.id;
      }
      return token;
    },
    session({ session, token }) {
      if (session.user) {
        (session.user as typeof session.user & { role: string; id: string }).role = token.role as string;
        (session.user as typeof session.user & { role: string; id: string }).id   = token.id as string;
      }
      return session;
    },
  },
  session: { strategy: "jwt" },
  secret: process.env.NEXTAUTH_SECRET ?? "langsight-dev-secret",
});
