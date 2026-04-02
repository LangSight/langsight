import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "LangSight vs Langfuse: Different Tools, Different Problems",
  description:
    "LangSight and Langfuse solve fundamentally different problems. Langfuse watches the brain (LLM observability). LangSight watches the hands (runtime reliability). Use both.",
  keywords: [
    "LangSight vs Langfuse",
    "Langfuse alternative",
    "LLM observability comparison",
    "AI agent monitoring tools",
    "Langfuse comparison",
    "agent observability",
    "MCP monitoring vs LLM tracing",
    "AI observability stack",
  ],
  alternates: { canonical: "https://langsight.dev/blog/langsight-vs-langfuse/" },
  openGraph: {
    title: "LangSight vs Langfuse: Different Tools, Different Problems",
    description:
      "Langfuse watches the brain. LangSight watches the hands. Use both for complete agent observability.",
    url: "https://langsight.dev/blog/langsight-vs-langfuse/",
    type: "article",
    siteName: "LangSight",
    publishedTime: "2026-04-02T00:00:00Z",
    modifiedTime: "2026-04-02T00:00:00Z",
    section: "Comparison",
    authors: ["https://langsight.dev"],
    tags: ["Comparison", "Langfuse", "Observability", "LangSight vs Langfuse", "AI observability stack"],
    images: [{ url: "https://langsight.dev/blog/langsight-vs-langfuse.png", width: 1200, height: 630, alt: "LangSight vs Langfuse Comparison" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "LangSight vs Langfuse: Different Tools, Different Problems",
    description:
      "Langfuse watches the brain. LangSight watches the hands. Use both for complete agent observability.",
    images: ["https://langsight.dev/blog/langsight-vs-langfuse.png"],
  },
};

const jsonLd = [
  {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      { "@type": "ListItem", position: 1, name: "Home", item: "https://langsight.dev/" },
      { "@type": "ListItem", position: 2, name: "Blog", item: "https://langsight.dev/blog/" },
      { "@type": "ListItem", position: 3, name: "LangSight vs Langfuse", item: "https://langsight.dev/blog/langsight-vs-langfuse/" },
    ],
  },
  {
    "@context": "https://schema.org",
    "@type": "TechArticle",
    headline: "LangSight vs Langfuse: Different Tools for Different Problems",
    description:
      "LangSight and Langfuse solve fundamentally different problems. Langfuse watches the brain (LLM observability). LangSight watches the hands (runtime reliability). Use both.",
    datePublished: "2026-04-02T00:00:00Z",
    dateModified: "2026-04-02T00:00:00Z",
    wordCount: 1600,
    mainEntityOfPage: { "@type": "WebPage", "@id": "https://langsight.dev/blog/langsight-vs-langfuse/" },
    author: { "@type": "Organization", name: "LangSight", url: "https://langsight.dev" },
    publisher: {
      "@type": "Organization",
      name: "LangSight",
      url: "https://langsight.dev",
      logo: { "@type": "ImageObject", url: "https://langsight.dev/logo-256.png", width: 256, height: 256 },
    },
    image: "https://langsight.dev/blog/langsight-vs-langfuse.png",
    keywords: "LangSight vs Langfuse, Langfuse alternative, LLM observability comparison, AI agent monitoring tools",
  },
  {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: [
      {
        "@type": "Question",
        name: "Should I use LangSight or Langfuse?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "Use both. They solve fundamentally different problems. Langfuse provides LLM observability (tracing, prompt management, evaluations, token cost tracking). LangSight provides runtime reliability (MCP health monitoring, security scanning, loop detection, budget enforcement, circuit breakers). Together they cover the full agent stack.",
        },
      },
      {
        "@type": "Question",
        name: "What is the difference between LangSight and Langfuse?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "Langfuse watches the brain: what the LLM decided, prompt quality, token costs, and model comparisons. LangSight watches the hands: whether MCP servers are healthy, if tools have security vulnerabilities, if agents are stuck in loops, and if sessions are within budget. If the agent gave a wrong answer due to bad reasoning, check Langfuse. If the agent failed because a tool was down, check LangSight.",
        },
      },
      {
        "@type": "Question",
        name: "Is LangSight a Langfuse alternative?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "No. LangSight is complementary to Langfuse, not a replacement. They cover non-overlapping gaps in the AI observability stack. LangSight does not do prompt management or LLM evaluations. Langfuse does not do MCP health monitoring or security scanning. Both are open source and self-hostable.",
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
