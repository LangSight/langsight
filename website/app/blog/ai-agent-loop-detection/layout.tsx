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
    section: "Agent Reliability",
    authors: ["https://langsight.dev"],
    tags: ["Loop Detection", "Agent Reliability", "Production", "AI agent loop detection", "MCP agent loop"],
    images: [{ url: "https://langsight.dev/blog/ai-agent-loop-detection.png", width: 1200, height: 630, alt: "AI Agent Loop Detection" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "How to Detect and Stop AI Agent Loops in Production",
    description:
      "AI agent loops burn tokens and produce nothing. Learn detection patterns and guardrails to stop them automatically.",
    images: ["https://langsight.dev/blog/ai-agent-loop-detection.png"],
  },
};

const jsonLd = [
  {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      { "@type": "ListItem", position: 1, name: "Home", item: "https://langsight.dev/" },
      { "@type": "ListItem", position: 2, name: "Blog", item: "https://langsight.dev/blog/" },
      { "@type": "ListItem", position: 3, name: "AI Agent Loop Detection", item: "https://langsight.dev/blog/ai-agent-loop-detection/" },
    ],
  },
  {
    "@context": "https://schema.org",
    "@type": "TechArticle",
    headline: "How to Detect and Stop AI Agent Loops in Production",
    description:
      "AI agent loops are the most common production failure: the same tool called 47 times, $200 burned, nothing produced. Learn how loop detection works and how to stop it automatically.",
    datePublished: "2026-03-22T00:00:00Z",
    dateModified: "2026-03-22T00:00:00Z",
    wordCount: 1800,
    mainEntityOfPage: { "@type": "WebPage", "@id": "https://langsight.dev/blog/ai-agent-loop-detection/" },
    author: { "@type": "Organization", name: "LangSight", url: "https://langsight.dev" },
    publisher: {
      "@type": "Organization",
      name: "LangSight",
      url: "https://langsight.dev",
      logo: { "@type": "ImageObject", url: "https://langsight.dev/logo-256.png", width: 256, height: 256 },
    },
    image: "https://langsight.dev/blog/ai-agent-loop-detection.png",
    keywords: "AI agent loop detection, agent infinite loop, LangGraph loop detection, stop agent loops, MCP agent loop",
  },
  {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: [
      {
        "@type": "Question",
        name: "What is an AI agent loop?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "An AI agent loop occurs when an agent calls the same tool or sequence of tools repeatedly without making meaningful progress. There are three patterns: direct repetition (same tool, same arguments), ping-pong (alternating between two tools), and retry-without-progress (the tool succeeds but the agent never converges on a solution).",
        },
      },
      {
        "@type": "Question",
        name: "How do you detect AI agent loops?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "Three approaches: (1) Argument hash comparison, which detects the same tool called with identical arguments N times; (2) Sliding window rate detection, which catches high-frequency calls regardless of argument variation; and (3) LLM output similarity, which detects when the agent generates the same reasoning steps repeatedly. Approaches 1 and 2 catch over 90% of real-world loops.",
        },
      },
      {
        "@type": "Question",
        name: "What should happen when an AI agent loop is detected?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "Three options: (1) Warn and continue, logging the detection and alerting the team; (2) Terminate the session with a loop_detected status; or (3) Inject a recovery message telling the agent it is stuck, giving it a chance to self-recover before termination. Option 2 is the right default for production systems.",
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
