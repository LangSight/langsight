import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "MCP & Agent Runtime Reliability Glossary | LangSight",
  description:
    "Definitions for key terms in agent runtime reliability and MCP server monitoring: circuit breaker, agent runtime reliability, MCP server, tool call tracing, schema drift detection, and more.",
  keywords: [
    "what is MCP server",
    "agent runtime reliability",
    "circuit breaker AI agent",
    "tool call tracing",
    "schema drift detection",
    "AI agent guardrails",
    "MCP health check",
    "tool poisoning",
    "OWASP MCP",
  ],
  openGraph: {
    title: "MCP & Agent Runtime Reliability Glossary | LangSight",
    description:
      "Plain-English definitions for agent runtime reliability, circuit breaker, MCP server, tool call tracing, schema drift, and other key terms.",
    url: "https://langsight.dev/glossary",
    siteName: "LangSight",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "MCP & Agent Runtime Reliability Glossary | LangSight",
    description:
      "Plain-English definitions for circuit breaker, agent runtime reliability, MCP, tool call tracing, and schema drift terms.",
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
