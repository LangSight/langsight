import type { Metadata } from "next";

export const metadata: Metadata = {
  title: { default: "Blog — AI Agent Monitoring & MCP Security Guides", template: "%s | LangSight Blog" },
  description:
    "Practical engineering guides on AI agent monitoring, MCP server security, loop detection, cost attribution, and production reliability for teams running AI agents.",
  alternates: { canonical: "https://langsight.dev/blog/" },
  openGraph: {
    title: "LangSight Blog — AI Agent Reliability & MCP Monitoring",
    description:
      "Practical guides on AI agent reliability, MCP server monitoring, security scanning, loop detection, and cost guardrails for production agent systems.",
    siteName: "LangSight",
    url: "https://langsight.dev/blog/",
    type: "website",
    images: [{ url: "https://langsight.dev/og-image.png", width: 1200, height: 630 }],
  },
  twitter: {
    card: "summary_large_image",
    title: "LangSight Blog — AI Agent Reliability & MCP Monitoring",
    description:
      "Practical guides on MCP server monitoring, AI agent security, loop detection, and cost guardrails for production.",
    images: ["https://langsight.dev/og-image.png"],
  },
};

const jsonLd = [
  {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      {
        "@type": "ListItem",
        position: 1,
        name: "Home",
        item: "https://langsight.dev/",
      },
      {
        "@type": "ListItem",
        position: 2,
        name: "Blog",
        item: "https://langsight.dev/blog/",
      },
    ],
  },
  {
    "@context": "https://schema.org",
    "@type": "CollectionPage",
    name: "LangSight Blog",
    description:
      "Practical guides on AI agent reliability, MCP server monitoring, loop detection, cost guardrails, and security for teams running agents in production.",
    url: "https://langsight.dev/blog/",
    publisher: {
      "@type": "Organization",
      name: "LangSight",
      url: "https://langsight.dev",
      logo: {
        "@type": "ImageObject",
        url: "https://langsight.dev/logo-256.png",
        width: 256,
        height: 256,
      },
    },
    mainEntity: {
      "@type": "ItemList",
      numberOfItems: 12,
      itemListElement: [
        {
          "@type": "ListItem",
          position: 1,
          url: "https://langsight.dev/blog/mcp-monitoring-production/",
          name: "How to Monitor MCP Servers in Production",
        },
        {
          "@type": "ListItem",
          position: 2,
          url: "https://langsight.dev/blog/owasp-mcp-top-10-guide/",
          name: "OWASP MCP Top 10 Explained: A Practical Security Guide",
        },
        {
          "@type": "ListItem",
          position: 3,
          url: "https://langsight.dev/blog/mcp-tool-poisoning/",
          name: "MCP Tool Poisoning: How Attackers Hijack AI Agents Through Tool Descriptions",
        },
        {
          "@type": "ListItem",
          position: 4,
          url: "https://langsight.dev/blog/ai-agent-cost-attribution/",
          name: "AI Agent Cost Attribution: Tracking Spend Per Tool Call",
        },
        {
          "@type": "ListItem",
          position: 5,
          url: "https://langsight.dev/blog/mcp-schema-drift/",
          name: "Schema Drift in MCP: The Silent Failure Your Agents Cannot Detect",
        },
        {
          "@type": "ListItem",
          position: 6,
          url: "https://langsight.dev/blog/circuit-breakers-ai-agents/",
          name: "Circuit Breakers for AI Agents: Preventing Cascading Failures",
        },
        {
          "@type": "ListItem",
          position: 7,
          url: "https://langsight.dev/blog/langsight-vs-langfuse/",
          name: "LangSight vs Langfuse: Different Tools for Different Problems",
        },
        {
          "@type": "ListItem",
          position: 8,
          url: "https://langsight.dev/blog/self-hosting-ai-observability/",
          name: "Self-Hosting AI Observability: Why Your Data Should Never Leave",
        },
        {
          "@type": "ListItem",
          position: 9,
          url: "https://langsight.dev/blog/blast-radius-mapping/",
          name: "Blast Radius Mapping: Understanding AI Agent Dependencies",
        },
        {
          "@type": "ListItem",
          position: 10,
          url: "https://langsight.dev/blog/slos-for-ai-agents/",
          name: "Setting SLOs for AI Agents: A Practical Guide",
        },
        {
          "@type": "ListItem",
          position: 11,
          url: "https://langsight.dev/blog/ai-agent-loop-detection/",
          name: "How to Detect and Stop AI Agent Loops in Production",
        },
        {
          "@type": "ListItem",
          position: 12,
          url: "https://langsight.dev/blog/mcp-server-security/",
          name: "MCP Server Security: OWASP Top 10 for Model Context Protocol",
        },
      ],
    },
  },
];

export default function BlogLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
      {children}
    </>
  );
}
