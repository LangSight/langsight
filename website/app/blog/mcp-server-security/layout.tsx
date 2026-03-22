import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "MCP Server Security: OWASP Top 10 for Model Context Protocol",
  description:
    "66% of community MCP servers have critical security issues. Learn the OWASP MCP Top 10, tool poisoning attacks, CVE risks, and how to audit your MCP servers before they compromise your agents.",
  keywords: [
    "MCP server security",
    "MCP OWASP",
    "model context protocol security",
    "MCP tool poisoning",
    "MCP CVE",
    "secure MCP server",
    "MCP authentication",
    "MCP vulnerability",
    "AI agent security",
  ],
  alternates: { canonical: "https://langsight.dev/blog/mcp-server-security/" },
  openGraph: {
    title: "MCP Server Security: OWASP Top 10 for Model Context Protocol",
    description:
      "66% of community MCP servers have critical security issues. Learn the OWASP MCP Top 10 and how to audit your MCP servers.",
    url: "https://langsight.dev/blog/mcp-server-security/",
    type: "article",
    siteName: "LangSight",
  },
  twitter: {
    card: "summary_large_image",
    title: "MCP Server Security: OWASP Top 10 for Model Context Protocol",
    description:
      "66% of community MCP servers have critical security issues. Learn how to audit yours.",
  },
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
