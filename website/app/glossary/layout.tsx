import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "AI Agent & MCP Glossary — Key Terms for Agent Monitoring",
  description:
    "Glossary of AI agent monitoring and MCP server terms. Definitions for MCP server, tool call tracing, circuit breaker, schema drift detection, tool poisoning, OWASP MCP Top 10, agent session, and more.",
  keywords: [
    "what is MCP server",
    "MCP observability definition",
    "agent runtime reliability",
    "circuit breaker AI agent",
    "tool call tracing",
    "schema drift detection",
    "AI agent guardrails",
    "MCP health check",
    "tool poisoning definition",
    "OWASP MCP Top 10",
    "AI agent monitoring glossary",
  ],
  openGraph: {
    title: "AI Agent & MCP Glossary — Key Terms for Agent Monitoring | LangSight",
    description:
      "Plain-English definitions for MCP server, tool call tracing, circuit breaker, schema drift, tool poisoning, and other AI agent monitoring terms.",
    url: "https://langsight.dev/glossary",
    siteName: "LangSight",
    type: "website",
    images: [{ url: "/og-image.png", width: 1200, height: 630, alt: "LangSight AI Agent & MCP Glossary" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "AI Agent & MCP Glossary | LangSight",
    description:
      "Plain-English definitions for MCP server, circuit breaker, agent runtime reliability, tool call tracing, schema drift, and more.",
    images: ["/og-image.png"],
  },
  alternates: {
    canonical: "https://langsight.dev/glossary/",
  },
};

const glossaryJsonLd = [
  {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      { "@type": "ListItem", position: 1, name: "Home", item: "https://langsight.dev/" },
      { "@type": "ListItem", position: 2, name: "Glossary", item: "https://langsight.dev/glossary/" },
    ],
  },
  {
    "@context": "https://schema.org",
    "@type": "DefinedTermSet",
    name: "AI Agent & MCP Monitoring Glossary",
    description: "Definitions for key terms in AI agent monitoring and MCP server observability.",
    url: "https://langsight.dev/glossary/",
    hasDefinedTerm: [
      {
        "@type": "DefinedTerm",
        name: "MCP Server",
        description: "A process that exposes tools, prompts, or resources to an AI agent via the Model Context Protocol.",
        url: "https://langsight.dev/glossary/#mcp-server",
      },
      {
        "@type": "DefinedTerm",
        name: "MCP Observability",
        description: "The practice of instrumenting, monitoring, and understanding the behavior of MCP servers and tool calls made against them.",
        url: "https://langsight.dev/glossary/#mcp-observability",
      },
      {
        "@type": "DefinedTerm",
        name: "Tool Call Tracing",
        description: "Recording the full lifecycle of a tool invocation by an AI agent, including arguments, results, latency, and errors.",
        url: "https://langsight.dev/glossary/#tool-call-tracing",
      },
      {
        "@type": "DefinedTerm",
        name: "Schema Drift Detection",
        description: "Automatically detecting when an MCP server's tool schema changes unexpectedly between scans.",
        url: "https://langsight.dev/glossary/#schema-drift-detection",
      },
      {
        "@type": "DefinedTerm",
        name: "Tool Poisoning",
        description: "An attack where an MCP server's tool description is modified to contain hidden instructions that manipulate agent behavior.",
        url: "https://langsight.dev/glossary/#tool-poisoning",
      },
      {
        "@type": "DefinedTerm",
        name: "MCP Health Check",
        description: "A proactive connection test against an MCP server that verifies reachability, latency, and expected tool schema.",
        url: "https://langsight.dev/glossary/#mcp-health-check",
      },
      {
        "@type": "DefinedTerm",
        name: "OWASP MCP Top 10",
        description: "A community-maintained list of the ten most critical security risks specific to MCP-based systems.",
        url: "https://langsight.dev/glossary/#owasp-mcp",
      },
      {
        "@type": "DefinedTerm",
        name: "Agent Session",
        description: "A single end-to-end execution of an AI agent workflow, from initial input through all tool calls to final output.",
        url: "https://langsight.dev/glossary/#agent-session",
      },
      {
        "@type": "DefinedTerm",
        name: "Agent Runtime Reliability",
        description: "The practice of keeping AI agent toolchains running correctly in production, including loop detection, budget enforcement, and circuit breaking.",
        url: "https://langsight.dev/glossary/#agent-runtime-reliability",
      },
      {
        "@type": "DefinedTerm",
        name: "Circuit Breaker",
        description: "A runtime safety mechanism that automatically disables a tool after consecutive failures, preventing cascading errors.",
        url: "https://langsight.dev/glossary/#circuit-breaker",
      },
    ],
  },
];

export default function GlossaryLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(glossaryJsonLd) }}
      />
      {children}
    </>
  );
}
