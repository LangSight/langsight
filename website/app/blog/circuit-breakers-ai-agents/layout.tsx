import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Circuit Breakers for AI Agents: Preventing Cascading Failures",
  description:
    "When an MCP server goes down, every agent that depends on it fails. Circuit breakers stop cascading failures by detecting tool failures and preventing wasted tool calls, tokens, and user sessions.",
  keywords: [
    "AI agent circuit breaker",
    "cascading failure prevention",
    "MCP fault tolerance",
    "agent reliability pattern",
    "tool failure isolation",
    "circuit breaker pattern",
    "MCP server failure",
    "agent resilience",
  ],
  alternates: { canonical: "https://langsight.dev/blog/circuit-breakers-ai-agents/" },
  openGraph: {
    title: "Circuit Breakers for AI Agents: Preventing Cascading Failures",
    description:
      "When an MCP server goes down, every agent that depends on it fails. Circuit breakers stop cascading failures.",
    url: "https://langsight.dev/blog/circuit-breakers-ai-agents/",
    type: "article",
    siteName: "LangSight",
    publishedTime: "2026-04-02T00:00:00Z",
    modifiedTime: "2026-04-02T00:00:00Z",
    authors: ["https://langsight.dev"],
    tags: ["Circuit Breaker", "Reliability", "Fault Tolerance", "AI agent circuit breaker", "cascading failure prevention"],
  },
  twitter: {
    card: "summary_large_image",
    title: "Circuit Breakers for AI Agents: Preventing Cascading Failures",
    description:
      "When an MCP server goes down, every agent that depends on it fails. Circuit breakers stop the cascade.",
  },
};

const jsonLd = {
  "@context": "https://schema.org",
  "@type": "TechArticle",
  headline: "Circuit Breakers for AI Agents: Preventing Cascading Failures",
  description:
    "When an MCP server goes down, every agent that depends on it fails. Circuit breakers stop cascading failures by detecting tool failures and preventing wasted tool calls, tokens, and user sessions.",
  datePublished: "2026-04-02T00:00:00Z",
  dateModified: "2026-04-02T00:00:00Z",
  wordCount: 1900,
  mainEntityOfPage: {
    "@type": "WebPage",
    "@id": "https://langsight.dev/blog/circuit-breakers-ai-agents/",
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
  keywords: "AI agent circuit breaker, cascading failure prevention, MCP fault tolerance, agent reliability pattern, tool failure isolation",
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
