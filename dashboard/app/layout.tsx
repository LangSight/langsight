import type { Metadata } from "next";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import { Providers } from "@/components/providers";
import { auth } from "@/lib/auth";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "LangSight", template: "%s · LangSight" },
  description: "AI agent observability — traces, costs, health checks, and security scanning for everything your agents call.",
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const session = await auth();
  return (
    <html lang="en" suppressHydrationWarning className={`${GeistSans.variable} ${GeistMono.variable}`}>
      <body>
        <Providers session={session}>{children}</Providers>
      </body>
    </html>
  );
}
