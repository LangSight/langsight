import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Circuit Breakers for AI Agents: Stop 1 MCP Failure From Taking Down Everything",
  description:
    "One MCP server goes down and 12 agents fail with it — all burning tokens, none recovering. Here is how circuit breakers work for AI agents, the 3 states, when to trip, and how to configure auto-recovery.",
  keywords: [
    "AI agent circuit breaker",
    "MCP server failure recovery",
    "cascading failure prevention AI",
    "agent fault tolerance",
    "MCP fault tolerance",
    "tool failure isolation",
    "circuit breaker pattern AI",
    "agent resilience production",
    "MCP circuit breaker",
  ],
  alternates: { canonical: "https://langsight.dev/blog/circuit-breakers-ai-agents/" },
  openGraph: {
    title: "Circuit Breakers for AI Agents: Stop 1 MCP Failure From Taking Down Everything",
    description:
      "One MCP server down = 12 agents failing and burning tokens. Circuit breakers isolate the failure. Here is how to implement them.",
    url: "https://langsight.dev/blog/circuit-breakers-ai-agents/",
    type: "article",
    siteName: "LangSight",
    publishedTime: "2026-04-02T00:00:00Z",
    modifiedTime: "2026-04-02T00:00:00Z",
    section: "Reliability",
    authors: ["https://langsight.dev"],
    tags: ["Circuit Breaker", "Reliability", "Fault Tolerance", "AI agent circuit breaker", "cascading failure prevention"],
    images: [{ url: "https://langsight.dev/blog/circuit-breakers-ai-agents.png", width: 1200, height: 630, alt: "Circuit Breakers for AI Agents" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "Circuit Breakers for AI Agents: Stop 1 MCP Failure From Taking Down Everything",
    description:
      "1 MCP server down = all agents burning tokens on retries. Circuit breakers isolate the failure in 3 states. Here is the implementation.",
    images: ["https://langsight.dev/blog/circuit-breakers-ai-agents.png"],
  },
};

const jsonLd = [
  {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      { "@type": "ListItem", position: 1, name: "Home", item: "https://langsight.dev/" },
      { "@type": "ListItem", position: 2, name: "Blog", item: "https://langsight.dev/blog/" },
      { "@type": "ListItem", position: 3, name: "Circuit Breakers for AI Agents", item: "https://langsight.dev/blog/circuit-breakers-ai-agents/" },
    ],
  },
  {
    "@context": "https://schema.org",
    "@type": "TechArticle",
    headline: "Circuit Breakers for AI Agents: Stop 1 MCP Failure From Taking Down Everything",
    description:
      "One MCP server goes down and every agent that depends on it fails — burning tokens on retries. Circuit breakers isolate the failure before it cascades. Here is how to implement them.",
    datePublished: "2026-04-02T00:00:00Z",
    dateModified: "2026-04-10T00:00:00Z",
    wordCount: 1900,
    mainEntityOfPage: { "@type": "WebPage", "@id": "https://langsight.dev/blog/circuit-breakers-ai-agents/" },
    author: { "@type": "Organization", name: "LangSight", url: "https://langsight.dev" },
    publisher: {
      "@type": "Organization",
      name: "LangSight",
      url: "https://langsight.dev",
      logo: { "@type": "ImageObject", url: "https://langsight.dev/logo-256.png", width: 256, height: 256 },
    },
    image: "https://langsight.dev/blog/circuit-breakers-ai-agents.png",
    keywords: "AI agent circuit breaker, cascading failure prevention, MCP fault tolerance, agent reliability pattern, tool failure isolation",
  },
  {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: [
      {
        "@type": "Question",
        name: "What is a circuit breaker for AI agents?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "A circuit breaker for AI agents is a reliability pattern that monitors tool call failure rates and temporarily disables a failing tool to prevent cascading failures. It has three states: Closed (tool calls allowed, failure rate monitored), Open (tool disabled, calls rejected immediately), and Half-Open (trial calls allowed to test recovery). When a tool exceeds the failure threshold, the breaker trips to Open and prevents all agents from wasting tokens retrying a broken tool.",
        },
      },
      {
        "@type": "Question",
        name: "How do circuit breakers prevent cascading failures in multi-agent systems?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "In a multi-agent system, one MCP server serves many agents simultaneously. Without circuit breakers, when that server degrades, every agent retries — amplifying the load and wasting tokens across all sessions. Circuit breakers isolate the failure: once the breaker trips, all agents receive an immediate rejection instead of a timeout, preventing token waste and allowing agents to handle the unavailability gracefully or skip to a fallback.",
        },
      },
      {
        "@type": "Question",
        name: "How long should a circuit breaker stay open before attempting recovery?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "The recovery timeout depends on the typical failure duration for your MCP servers. A 60-second open window works for transient network failures. For database MCP servers that need restart time, use 2–5 minutes. LangSight's circuit breaker uses a half-open state after the timeout — it allows 1–3 trial calls to verify recovery before fully closing. If the trial calls fail, the breaker reopens and resets the timeout.",
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
