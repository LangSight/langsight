import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Setting SLOs for AI Agents: A Practical Guide",
  description:
    "AI agents are non-deterministic, which makes traditional uptime SLOs insufficient. Here is how to define, measure, and enforce SLOs for success rate, latency, loop rate, and budget adherence.",
  keywords: [
    "AI agent SLO",
    "SLO for AI agents",
    "agent reliability metrics",
    "AI agent success rate",
    "agent latency SLO",
    "error budget AI agents",
    "SRE AI agents",
    "agent reliability engineering",
  ],
  alternates: { canonical: "https://langsight.dev/blog/slos-for-ai-agents/" },
  openGraph: {
    title: "Setting SLOs for AI Agents: A Practical Guide",
    description:
      "AI agents are non-deterministic. Traditional uptime SLOs are not enough. Here is how to define SLOs that work.",
    url: "https://langsight.dev/blog/slos-for-ai-agents/",
    type: "article",
    siteName: "LangSight",
    publishedTime: "2026-04-02T00:00:00Z",
    modifiedTime: "2026-04-02T00:00:00Z",
    authors: ["https://langsight.dev"],
    tags: ["SLOs", "Reliability Engineering", "Monitoring", "AI agent SLO", "SRE AI agents"],
  },
  twitter: {
    card: "summary_large_image",
    title: "Setting SLOs for AI Agents: A Practical Guide",
    description:
      "AI agents are non-deterministic. Traditional uptime SLOs are not enough. Here is how to define SLOs that work.",
  },
};

const jsonLd = {
  "@context": "https://schema.org",
  "@type": "TechArticle",
  headline: "Setting SLOs for AI Agents: A Practical Guide",
  description:
    "AI agents are non-deterministic, which makes traditional uptime SLOs insufficient. Here is how to define, measure, and enforce SLOs for success rate, latency, loop rate, and budget adherence.",
  datePublished: "2026-04-02T00:00:00Z",
  dateModified: "2026-04-02T00:00:00Z",
  wordCount: 1900,
  mainEntityOfPage: {
    "@type": "WebPage",
    "@id": "https://langsight.dev/blog/slos-for-ai-agents/",
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
  keywords: "AI agent SLO, SLO for AI agents, agent reliability metrics, AI agent success rate, agent latency SLO, error budget AI agents",
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
