import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "MCP & AI Agent Observability Glossary | LangSight",
  description:
    "Definitions for key terms in MCP server monitoring and AI agent observability: MCP server, tool call tracing, schema drift detection, MCP observability, OWASP MCP, and more.",
  keywords: [
    "what is MCP server",
    "MCP observability",
    "tool call tracing",
    "schema drift detection",
    "AI agent observability",
    "MCP health check",
    "tool poisoning",
    "OWASP MCP",
  ],
  openGraph: {
    title: "MCP & AI Agent Observability Glossary | LangSight",
    description:
      "Plain-English definitions for MCP server, tool call tracing, schema drift, OWASP MCP, and other key terms in AI agent observability.",
    url: "https://langsight.dev/glossary",
    siteName: "LangSight",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "MCP & AI Agent Observability Glossary | LangSight",
    description:
      "Plain-English definitions for MCP, tool call tracing, schema drift, and AI agent observability terms.",
  },
  alternates: {
    canonical: "https://langsight.dev/glossary/",
  },
};

export default function GlossaryLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
