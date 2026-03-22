import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "How to Detect and Stop AI Agent Loops in Production",
  description:
    "AI agent loops are the most common production failure: the same tool called 47 times, $200 burned, nothing produced. Learn how loop detection works and how to stop it automatically.",
  keywords: [
    "AI agent loop detection",
    "agent infinite loop",
    "LangGraph loop detection",
    "stop agent loops",
    "agent stuck in loop",
    "agent loop prevention",
    "LangChain loop",
    "CrewAI loop detection",
    "MCP agent loop",
  ],
  alternates: { canonical: "https://langsight.dev/blog/ai-agent-loop-detection/" },
  openGraph: {
    title: "How to Detect and Stop AI Agent Loops in Production",
    description:
      "AI agent loops burn tokens and produce nothing. Learn detection patterns, circuit breakers, and guardrails to stop them automatically.",
    url: "https://langsight.dev/blog/ai-agent-loop-detection/",
    type: "article",
    siteName: "LangSight",
    publishedTime: "2026-03-22T00:00:00Z",
    modifiedTime: "2026-03-22T00:00:00Z",
    authors: ["https://langsight.dev"],
    tags: ["Loop Detection", "Agent Reliability", "Production", "AI agent loop detection", "MCP agent loop"],
  },
  twitter: {
    card: "summary_large_image",
    title: "How to Detect and Stop AI Agent Loops in Production",
    description:
      "AI agent loops burn tokens and produce nothing. Learn detection patterns and guardrails to stop them automatically.",
  },
};

const jsonLd = {
  "@context": "https://schema.org",
  "@type": "TechArticle",
  headline: "How to Detect and Stop AI Agent Loops in Production",
  description:
    "AI agent loops are the most common production failure: the same tool called 47 times, $200 burned, nothing produced. Learn how loop detection works and how to stop it automatically.",
  datePublished: "2026-03-22T00:00:00Z",
  dateModified: "2026-03-22T00:00:00Z",
  wordCount: 1800,
  mainEntityOfPage: {
    "@type": "WebPage",
    "@id": "https://langsight.dev/blog/ai-agent-loop-detection/",
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
  image: "https://langsight.dev/og-image.svg",
  keywords: "AI agent loop detection, agent infinite loop, LangGraph loop detection, stop agent loops, MCP agent loop",
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
