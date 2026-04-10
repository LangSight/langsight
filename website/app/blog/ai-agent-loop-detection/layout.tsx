import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "AI Agent Loop Detection: 3 Patterns, Code Examples & Auto-Kill",
  description:
    "Your agent called the same tool 47 times and burned $200. Here are the 3 loop patterns that cause it, how to detect each one in code, and how to terminate automatically — with real examples from Claude Agent SDK and CrewAI.",
  keywords: [
    "AI agent loop detection",
    "detect AI agent looping",
    "agent infinite loop",
    "how to detect infinite loops in ai agents",
    "agent stuck in loop",
    "stop agent loops production",
    "Claude agent loop",
    "CrewAI loop detection",
    "MCP agent loop",
    "tools to monitor agent behavior",
  ],
  alternates: { canonical: "https://langsight.dev/blog/ai-agent-loop-detection/" },
  openGraph: {
    title: "AI Agent Loop Detection: 3 Patterns, Code Examples & Auto-Kill",
    description:
      "The same tool called 47 times, $200 burned, nothing produced. 3 loop patterns, detection code, and how to auto-terminate — Claude SDK and CrewAI examples included.",
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
    title: "AI Agent Loop Detection: 3 Patterns, Code Examples & Auto-Kill",
    description:
      "Same tool called 47 times, $200 burned. 3 loop patterns, detection code, and how to auto-terminate agents in production.",
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
    headline: "AI Agent Loop Detection: 3 Patterns, Code Examples & Auto-Kill",
    description:
      "Your agent called the same tool 47 times and burned $200. Here are the 3 loop patterns that cause it, how to detect each one in code, and how to terminate automatically.",
    datePublished: "2026-03-22T00:00:00Z",
    dateModified: "2026-04-10T00:00:00Z",
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
      {
        "@type": "Question",
        name: "My production agent is consuming 3x more tokens than expected and calling the same tool repeatedly with slight variations. What is the best immediate action?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "This is a sliding-window loop — the arguments vary slightly so argument-hash detection misses it. The best immediate action is: (1) Kill the session now to stop the bleeding. (2) Check the tool's recent output — the agent is likely getting an ambiguous or error response that causes it to retry. (3) Enable sliding-window rate detection, which fires when the same tool is called more than N times in any window regardless of argument variation. In LangSight, set loop_detection.strategy: sliding_window and loop_detection.window_calls: 5 in your agent config.",
        },
      },
      {
        "@type": "Question",
        name: "What tools can monitor agent behavior for loops, wrong tool selection, and context loss?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "LangSight monitors all three: loop detection (argument-hash and sliding-window), tool selection anomalies (unexpected tool call sequences flagged as anomalies), and context loss (session length and token usage spikes that indicate the agent is re-discovering context). For prompt-level issues, use Langfuse or LangSmith alongside LangSight.",
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
