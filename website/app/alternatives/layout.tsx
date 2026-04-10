import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "LangSight vs Langfuse vs LangWatch vs LangTrace vs Arize Phoenix — Comparison",
  description:
    "Compare LangSight, Langfuse, LangWatch, LangTrace, Arize Phoenix, and LangSmith for AI agent monitoring. LangSight is the only platform with MCP health checks, security scanning, circuit breakers, and runtime guardrails. Free self-hosted.",
  keywords: [
    "LangSight vs Langfuse",
    "LangSight vs LangWatch",
    "langwatch vs langfuse",
    "langfuse vs langwatch",
    "langfuse vs langtrace",
    "langfuse vs langtrace ai",
    "LangTrace alternative",
    "Arize Phoenix alternative",
    "LangSmith alternative",
    "AI agent monitoring comparison",
    "MCP observability comparison",
    "open source AI observability",
    "agent runtime reliability",
  ],
  openGraph: {
    title: "LangSight vs Langfuse vs LangWatch vs LangTrace vs Arize Phoenix",
    description:
      "LangSight is purpose-built for agent runtime reliability. Compare MCP health, security, circuit breakers, and guardrails against Langfuse, LangWatch, LangTrace, Arize Phoenix, and LangSmith.",
    url: "https://langsight.dev/alternatives",
    siteName: "LangSight",
    type: "website",
    images: [{ url: "/og-image.png", width: 1200, height: 630, alt: "LangSight vs Langfuse vs LangWatch comparison" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "LangSight vs Langfuse vs LangWatch — AI Agent Monitoring Comparison",
    description:
      "The only MCP-native agent monitoring platform. Compare LangSight vs Langfuse vs LangWatch for AI agent observability.",
    images: ["/og-image.png"],
  },
  alternates: {
    canonical: "https://langsight.dev/alternatives/",
  },
};

const alternativesJsonLd = [
  {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      { "@type": "ListItem", position: 1, name: "Home", item: "https://langsight.dev/" },
      { "@type": "ListItem", position: 2, name: "Alternatives", item: "https://langsight.dev/alternatives/" },
    ],
  },
  {
    "@context": "https://schema.org",
    "@type": "WebPage",
    name: "LangSight vs Langfuse vs LangWatch vs LangTrace vs Arize Phoenix — Comparison",
    description:
      "Feature-by-feature comparison of LangSight, Langfuse, LangWatch, LangTrace, Arize Phoenix, and LangSmith for AI agent monitoring and MCP observability.",
    url: "https://langsight.dev/alternatives/",
  },
  {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: [
      {
        "@type": "Question",
        name: "What is the difference between LangSight and Langfuse?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "Langfuse focuses on LLM prompt engineering, evaluation, and cost tracking at the model layer. LangSight monitors the tool layer — MCP server health, security scanning (CVE + OWASP), circuit breakers, and loop detection. They are complementary: use Langfuse for prompt quality and LangSight for runtime reliability. Langfuse does not do MCP health checks, tool poisoning detection, or schema drift detection.",
        },
      },
      {
        "@type": "Question",
        name: "What is the difference between LangSight and LangWatch?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "LangWatch focuses on LLM output quality, safety guardrails, and content moderation. LangSight focuses on agent runtime reliability — preventing loops, enforcing budgets, monitoring MCP server health, and scanning for security vulnerabilities. LangWatch does not do MCP health checks or CVE scanning.",
        },
      },
      {
        "@type": "Question",
        name: "What is the difference between LangSight and LangTrace?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "LangTrace is an OpenTelemetry-native tracing platform focused on LLM observability — capturing spans, tokens, and latency. LangSight uses OTLP/OpenTelemetry as its ingestion format but adds a prevention and security layer on top: loop detection, budget enforcement, circuit breakers, MCP health monitoring, and CVE scanning. LangTrace does not do runtime guardrails or MCP security.",
        },
      },
      {
        "@type": "Question",
        name: "What is the difference between LangSight and Arize Phoenix?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "Arize Phoenix is focused on LLM evaluation, tracing, and prompt experimentation — particularly strong for retrieval-augmented generation (RAG) quality analysis. LangSight focuses on agent runtime reliability and MCP infrastructure: health monitoring, security scanning, circuit breakers, and guardrails. They cover different parts of the AI stack.",
        },
      },
    ],
  },
];

export default function AlternativesLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(alternativesJsonLd) }}
      />
      {children}
    </>
  );
}
