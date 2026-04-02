import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Blast Radius Mapping: Understanding AI Agent Dependencies",
  description:
    "When an MCP server goes down, how many agents are affected? Which sessions will fail? Blast radius mapping gives you the dependency graph to answer these questions before incidents happen.",
  keywords: [
    "blast radius mapping",
    "AI agent dependencies",
    "MCP dependency graph",
    "agent tool dependencies",
    "impact analysis AI agents",
    "MCP server outage impact",
    "agent topology",
    "multi-agent dependencies",
  ],
  alternates: { canonical: "https://langsight.dev/blog/blast-radius-mapping/" },
  openGraph: {
    title: "Blast Radius Mapping: Understanding AI Agent Dependencies",
    description:
      "When an MCP server goes down, how many agents and sessions are affected? Blast radius mapping answers this.",
    url: "https://langsight.dev/blog/blast-radius-mapping/",
    type: "article",
    siteName: "LangSight",
    publishedTime: "2026-04-02T00:00:00Z",
    modifiedTime: "2026-04-02T00:00:00Z",
    authors: ["https://langsight.dev"],
    tags: ["Blast Radius", "Dependencies", "Reliability", "blast radius mapping", "AI agent dependencies"],
  },
  twitter: {
    card: "summary_large_image",
    title: "Blast Radius Mapping: Understanding AI Agent Dependencies",
    description:
      "When an MCP server goes down, how many agents and sessions are affected? Blast radius mapping answers this.",
  },
};

const jsonLd = {
  "@context": "https://schema.org",
  "@type": "TechArticle",
  headline: "Blast Radius Mapping: Understanding AI Agent Dependencies",
  description:
    "When an MCP server goes down, how many agents are affected? Which sessions will fail? Blast radius mapping gives you the dependency graph to answer these questions before incidents happen.",
  datePublished: "2026-04-02T00:00:00Z",
  dateModified: "2026-04-02T00:00:00Z",
  wordCount: 1900,
  mainEntityOfPage: {
    "@type": "WebPage",
    "@id": "https://langsight.dev/blog/blast-radius-mapping/",
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
  keywords: "blast radius mapping, AI agent dependencies, MCP dependency graph, agent tool dependencies, impact analysis AI agents",
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
