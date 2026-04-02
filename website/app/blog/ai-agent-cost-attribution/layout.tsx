import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "AI Agent Cost Attribution: Tracking Spend Per Tool Call",
  description:
    "Teams know their total AI spend but cannot attribute costs to specific tools, agents, or sessions. Here is how to implement per-call cost tracking with budget guardrails.",
  keywords: [
    "AI agent cost tracking",
    "agent cost attribution",
    "LLM cost per session",
    "tool call cost",
    "AI budget guardrails",
    "agent spend optimization",
    "MCP cost monitoring",
    "AI agent budget",
  ],
  alternates: { canonical: "https://langsight.dev/blog/ai-agent-cost-attribution/" },
  openGraph: {
    title: "AI Agent Cost Attribution: Tracking Spend Per Tool Call",
    description:
      "Teams know their total AI spend but cannot attribute costs to specific tools, agents, or sessions. Here is how to implement per-call cost tracking.",
    url: "https://langsight.dev/blog/ai-agent-cost-attribution/",
    type: "article",
    siteName: "LangSight",
    publishedTime: "2026-04-02T00:00:00Z",
    modifiedTime: "2026-04-02T00:00:00Z",
    section: "Cost Management",
    authors: ["https://langsight.dev"],
    tags: ["Cost Tracking", "Budget", "Production", "AI agent cost tracking", "agent cost attribution"],
    images: [{ url: "https://langsight.dev/blog/ai-agent-cost-attribution.png", width: 1200, height: 630, alt: "AI Agent Cost Attribution" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "AI Agent Cost Attribution: Tracking Spend Per Tool Call",
    description:
      "Teams know their total AI spend but cannot attribute costs to specific tools, agents, or sessions.",
    images: ["https://langsight.dev/blog/ai-agent-cost-attribution.png"],
  },
};

const jsonLd = [
  {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      { "@type": "ListItem", position: 1, name: "Home", item: "https://langsight.dev/" },
      { "@type": "ListItem", position: 2, name: "Blog", item: "https://langsight.dev/blog/" },
      { "@type": "ListItem", position: 3, name: "AI Agent Cost Attribution", item: "https://langsight.dev/blog/ai-agent-cost-attribution/" },
    ],
  },
  {
    "@context": "https://schema.org",
    "@type": "TechArticle",
    headline: "AI Agent Cost Attribution: Tracking Spend Per Tool Call",
    description:
      "Teams know their total AI spend but cannot attribute costs to specific tools, agents, or sessions. Here is how to implement per-call cost tracking with budget guardrails.",
    datePublished: "2026-04-02T00:00:00Z",
    dateModified: "2026-04-02T00:00:00Z",
    wordCount: 1900,
    mainEntityOfPage: {
      "@type": "WebPage",
      "@id": "https://langsight.dev/blog/ai-agent-cost-attribution/",
    },
    author: { "@type": "Organization", name: "LangSight", url: "https://langsight.dev" },
    publisher: {
      "@type": "Organization",
      name: "LangSight",
      url: "https://langsight.dev",
      logo: { "@type": "ImageObject", url: "https://langsight.dev/logo-256.png", width: 256, height: 256 },
    },
    image: "https://langsight.dev/blog/ai-agent-cost-attribution.png",
    keywords: "AI agent cost tracking, agent cost attribution, LLM cost per session, tool call cost, AI budget guardrails",
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
