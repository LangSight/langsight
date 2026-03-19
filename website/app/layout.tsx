import type { Metadata } from "next";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import "./globals.css";

export const metadata: Metadata = {
  title: "LangSight — AI Agent Observability",
  description:
    "When your AI agent fails, LangSight tells you exactly which tool broke it. Full traces of every tool call across single and multi-agent workflows. MCP health checks, CVE scanning, and cost attribution built in.",
  keywords: ["AI agent observability", "MCP monitoring", "LangChain tracing", "agent debugging", "MCP security"],
  openGraph: {
    title: "LangSight — AI Agent Observability",
    description:
      "When your AI agent fails, LangSight tells you exactly which tool broke it.",
    url: "https://langsight.io",
    siteName: "LangSight",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "LangSight — AI Agent Observability",
    description: "When your AI agent fails, LangSight tells you exactly which tool broke it.",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${GeistSans.variable} ${GeistMono.variable}`}>
      <body>{children}</body>
    </html>
  );
}
