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
  },
  twitter: {
    card: "summary_large_image",
    title: "How to Detect and Stop AI Agent Loops in Production",
    description:
      "AI agent loops burn tokens and produce nothing. Learn detection patterns and guardrails to stop them automatically.",
  },
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
