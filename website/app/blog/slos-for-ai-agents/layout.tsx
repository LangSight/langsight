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
    section: "Reliability Engineering",
    authors: ["https://langsight.dev"],
    tags: ["SLOs", "Reliability Engineering", "Monitoring", "AI agent SLO", "SRE AI agents"],
    images: [{ url: "https://langsight.dev/blog/slos-for-ai-agents.png", width: 1200, height: 630, alt: "Setting SLOs for AI Agents" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "Setting SLOs for AI Agents: A Practical Guide",
    description:
      "AI agents are non-deterministic. Traditional uptime SLOs are not enough. Here is how to define SLOs that work.",
    images: ["https://langsight.dev/blog/slos-for-ai-agents.png"],
  },
};

const jsonLd = [
  {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      { "@type": "ListItem", position: 1, name: "Home", item: "https://langsight.dev/" },
      { "@type": "ListItem", position: 2, name: "Blog", item: "https://langsight.dev/blog/" },
      { "@type": "ListItem", position: 3, name: "SLOs for AI Agents", item: "https://langsight.dev/blog/slos-for-ai-agents/" },
    ],
  },
  {
    "@context": "https://schema.org",
    "@type": "TechArticle",
    headline: "Setting SLOs for AI Agents: A Practical Guide",
    description:
      "AI agents are non-deterministic, which makes traditional uptime SLOs insufficient. Here is how to define, measure, and enforce SLOs for success rate, latency, loop rate, and budget adherence.",
    datePublished: "2026-04-02T00:00:00Z",
    dateModified: "2026-04-02T00:00:00Z",
    wordCount: 1900,
    mainEntityOfPage: { "@type": "WebPage", "@id": "https://langsight.dev/blog/slos-for-ai-agents/" },
    author: { "@type": "Organization", name: "LangSight", url: "https://langsight.dev" },
    publisher: {
      "@type": "Organization",
      name: "LangSight",
      url: "https://langsight.dev",
      logo: { "@type": "ImageObject", url: "https://langsight.dev/logo-256.png", width: 256, height: 256 },
    },
    image: "https://langsight.dev/blog/slos-for-ai-agents.png",
    keywords: "AI agent SLO, SLO for AI agents, agent reliability metrics, AI agent success rate, agent latency SLO, error budget AI agents",
  },
  {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: [
      {
        "@type": "Question",
        name: "What SLO metrics should you track for AI agents?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "Track four metrics: (1) Success rate, the percentage of sessions that complete without failure; (2) Latency p99, the 99th percentile end-to-end session duration; (3) Loop rate, the percentage of sessions that trigger loop detection; and (4) Budget adherence, the percentage of sessions that complete within their configured cost budget.",
        },
      },
      {
        "@type": "Question",
        name: "What is a realistic SLO target for AI agent success rate?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "For well-tuned agents, 95-98% success rate is achievable. Start with a conservative 90% target, measure for 2-4 weeks, then tighten based on actual data. 99%+ is unrealistic for agents handling diverse real-world inputs. Setting targets too aggressively leads to immediate SLO violations and loss of credibility.",
        },
      },
      {
        "@type": "Question",
        name: "How do error budgets work for AI agents?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "An error budget is the inverse of the SLO target. If success rate target is 95%, the error budget is 5% of sessions can fail. When the error budget is exhausted, trigger alert escalation, freeze deployments, create postmortems, and allocate reliability sprints. Without policies, SLOs are just numbers on a dashboard.",
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
