import type { Metadata } from "next";
import { cookies } from "next/headers";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import { Providers } from "@/components/providers";
import { auth } from "@/lib/auth";
import type { Session } from "next-auth";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "LangSight", template: "%s · LangSight" },
  description: "Agent runtime reliability — prevent loops, enforce budgets, trace every tool call, monitor MCP health, and scan for security issues.",
};

function getPlaywrightSession(): Session & { userId: string; userRole: string } {
  return {
    user: {
      id: "usr_test_001",
      name: "Admin User",
      email: "admin@langsight.io",
      role: "admin",
    },
    expires: new Date(Date.now() + 86_400_000).toISOString(),
    userId: "usr_test_001",
    userRole: "admin",
  };
}

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const cookieStore = await cookies();
  const usePlaywrightSession = process.env.PLAYWRIGHT_TEST === "1"
    && cookieStore.get("langsight_e2e_auth")?.value === "1";
  const session = usePlaywrightSession ? getPlaywrightSession() : await auth();
  return (
    <html lang="en" suppressHydrationWarning className={`${GeistSans.variable} ${GeistMono.variable}`}>
      <body>
        <Providers session={session}>{children}</Providers>
      </body>
    </html>
  );
}
