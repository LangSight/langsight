import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "How to Monitor MCP Servers in Production",
  description:
    "Your agents depend on MCP servers. If one goes down, your agents fail silently. Here is how to set up proactive health monitoring, latency tracking, and uptime alerting for your entire MCP fleet.",
  keywords: [
    "MCP server monitoring",
    "MCP health check",
    "monitor MCP servers",
    "MCP server health",
    "MCP observability",
    "MCP server uptime",
    "AI agent tool monitoring",
    "MCP latency tracking",
    "MCP fleet monitoring",
  ],
  alternates: { canonical: "https://langsight.dev/blog/mcp-monitoring-production/" },
  openGraph: {
    title: "How to Monitor MCP Servers in Production",
    description:
      "Your agents depend on MCP servers. If one goes down, your agents fail silently. Here is how to set up proactive health monitoring and uptime alerting.",
    url: "https://langsight.dev/blog/mcp-monitoring-production/",
    type: "article",
    siteName: "LangSight",
    publishedTime: "2026-04-02T00:00:00Z",
    modifiedTime: "2026-04-02T00:00:00Z",
    section: "MCP Monitoring",
    authors: ["https://langsight.dev"],
    tags: ["MCP Monitoring", "Health Checks", "Production", "MCP server monitoring", "MCP observability"],
    images: [{ url: "https://langsight.dev/blog/mcp-monitoring-production.png", width: 1200, height: 630, alt: "How to Monitor MCP Servers in Production" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "How to Monitor MCP Servers in Production",
    description:
      "Your agents depend on MCP servers. If one goes down, your agents fail silently. Here is how to set up proactive health monitoring.",
    images: ["https://langsight.dev/blog/mcp-monitoring-production.png"],
  },
};

const jsonLd = [
  {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      { "@type": "ListItem", position: 1, name: "Home", item: "https://langsight.dev/" },
      { "@type": "ListItem", position: 2, name: "Blog", item: "https://langsight.dev/blog/" },
      { "@type": "ListItem", position: 3, name: "MCP Monitoring in Production", item: "https://langsight.dev/blog/mcp-monitoring-production/" },
    ],
  },
  {
    "@context": "https://schema.org",
    "@type": "TechArticle",
    headline: "How to Monitor MCP Servers in Production",
    description:
      "Your agents depend on MCP servers. If one goes down, your agents fail silently. Here is how to set up proactive health monitoring, latency tracking, and uptime alerting for your entire MCP fleet.",
    datePublished: "2026-04-02T00:00:00Z",
    dateModified: "2026-04-02T00:00:00Z",
    wordCount: 2100,
    mainEntityOfPage: {
      "@type": "WebPage",
      "@id": "https://langsight.dev/blog/mcp-monitoring-production/",
    },
    author: {
      "@type": "Organization",
      name: "LangSight",
      url: "https://langsight.dev",
    },
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
    image: "https://langsight.dev/blog/mcp-monitoring-production.png",
    keywords: "MCP server monitoring, MCP health check, monitor MCP servers, MCP server health, MCP observability, MCP server uptime, AI agent tool monitoring",
  },
  {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: [
      {
        "@type": "Question",
        name: "What are the three MCP transport types and how do they fail?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "MCP supports three transport types: stdio (process crashes, OOM, hanging calls), SSE (connection drops and event stream stalls), and StreamableHTTP (session management and standard HTTP failures). Each requires different monitoring approaches because their failure modes are fundamentally different.",
        },
      },
      {
        "@type": "Question",
        name: "What five signals should you monitor for MCP servers?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "Monitor latency distribution (p50, p95, p99), error rate by category, uptime and availability over rolling windows, schema consistency (tool count and schema changes), and tool call success rate. Missing any one leaves a blind spot in your MCP observability.",
        },
      },
      {
        "@type": "Question",
        name: "What is the difference between proactive and passive MCP monitoring?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "Passive monitoring records traces of real agent sessions and reports after the fact. Proactive monitoring sends synthetic health probes to every MCP server on a schedule, detecting failures before any agent is affected. LangSight does both, but proactive monitoring is what prevents 2 AM pages.",
        },
      },
    ],
  },
];

export default function Layout({ children }: { children: React.ReactNode }) {
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
