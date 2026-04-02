import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "How to Monitor MCP Servers in Production",
  description:
    "Your agents depend on MCP servers. If one goes down, your agents fail silently. Here's how to set up proactive health monitoring, latency tracking, and uptime alerting for your entire MCP fleet.",
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
      "Your agents depend on MCP servers. If one goes down, your agents fail silently. Here's how to set up proactive health monitoring and uptime alerting.",
    url: "https://langsight.dev/blog/mcp-monitoring-production/",
    type: "article",
    siteName: "LangSight",
    publishedTime: "2026-04-02T00:00:00Z",
    modifiedTime: "2026-04-02T00:00:00Z",
    authors: ["https://langsight.dev"],
    tags: ["MCP Monitoring", "Health Checks", "Production", "MCP server monitoring", "MCP observability"],
  },
  twitter: {
    card: "summary_large_image",
    title: "How to Monitor MCP Servers in Production",
    description:
      "Your agents depend on MCP servers. If one goes down, your agents fail silently. Here's how to set up proactive health monitoring.",
  },
};

const jsonLd = {
  "@context": "https://schema.org",
  "@type": "TechArticle",
  headline: "How to Monitor MCP Servers in Production",
  description:
    "Your agents depend on MCP servers. If one goes down, your agents fail silently. Here's how to set up proactive health monitoring, latency tracking, and uptime alerting for your entire MCP fleet.",
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
  image: "https://langsight.dev/og-image.png",
  keywords: "MCP server monitoring, MCP health check, monitor MCP servers, MCP server health, MCP observability, MCP server uptime, AI agent tool monitoring",
};

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
