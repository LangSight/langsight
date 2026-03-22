import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "MCP Security Scanning — OWASP MCP Top 10 | LangSight",
  description:
    "Automated MCP security scanning for AI agent runtime reliability. Detect CVEs, run OWASP MCP Top 10 checks, find tool poisoning attacks, and audit auth gaps. One command, plugs into CI/CD.",
  keywords: [
    "MCP security scanning",
    "OWASP MCP",
    "MCP CVE detection",
    "AI agent security",
    "agent runtime reliability",
    "agent guardrails",
    "tool poisoning detection",
    "MCP server security audit",
  ],
  openGraph: {
    title: "MCP Security Scanning — OWASP MCP Top 10 | LangSight",
    description:
      "Automated CVE detection, OWASP MCP checks, tool poisoning detection, and auth gap analysis for your entire MCP fleet.",
    url: "https://langsight.dev/security",
    siteName: "LangSight",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "MCP Security Scanning — OWASP MCP Top 10 | LangSight",
    description:
      "Automated MCP security scanning: CVEs, OWASP MCP Top 10, tool poisoning, auth gaps. One command, CI/CD ready.",
  },
  alternates: {
    canonical: "https://langsight.dev/security/",
  },
};

export default function SecurityLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
