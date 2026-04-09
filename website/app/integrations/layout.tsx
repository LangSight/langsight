import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Integrations — Claude Agent SDK, CrewAI, OpenAI & More",
  description:
    "Monitor AI agents built with Claude Agent SDK, CrewAI, Anthropic SDK, OpenAI, Google Gemini, and any OTLP-compatible framework. Zero-code instrumentation with auto_patch(). Add monitoring in 2 lines of Python.",
  keywords: [
    "Claude Agent SDK monitoring",
    "CrewAI monitoring",
    "AI agent monitoring setup",
    "Anthropic SDK observability",
    "OpenAI agent monitoring",
    "Gemini agent tracing",
    "OTLP agent monitoring",
    "auto_patch AI agents",
    "AI agent instrumentation",
    "MCP server monitoring",
    "agent tool call tracing",
  ],
  openGraph: {
    title: "LangSight Integrations — Monitor Claude Agent SDK, CrewAI, OpenAI & More",
    description:
      "Zero-code monitoring for Claude Agent SDK, CrewAI, OpenAI, and Gemini agents. Add observability in 2 lines of Python. Free, open source.",
    url: "https://langsight.dev/integrations",
    siteName: "LangSight",
    type: "website",
    images: [{ url: "/og-image.png", width: 1200, height: 630, alt: "LangSight Integrations — AI Agent Monitoring for Every Framework" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "LangSight Integrations — Claude Agent SDK, CrewAI, OpenAI & More",
    description:
      "Zero-code monitoring for Claude Agent SDK, CrewAI, OpenAI, and Gemini agents. 2 lines of Python. Free, open source.",
    images: ["/og-image.png"],
  },
  alternates: {
    canonical: "https://langsight.dev/integrations/",
  },
};

const integrationsJsonLd = [
  {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      { "@type": "ListItem", position: 1, name: "Home", item: "https://langsight.dev/" },
      { "@type": "ListItem", position: 2, name: "Integrations", item: "https://langsight.dev/integrations/" },
    ],
  },
  {
    "@context": "https://schema.org",
    "@type": "WebPage",
    name: "LangSight Integrations — AI Agent Monitoring for Every Framework",
    description:
      "Monitor AI agents built with Claude Agent SDK, CrewAI, Anthropic SDK, OpenAI, Google Gemini, and any OTLP-compatible framework.",
    url: "https://langsight.dev/integrations/",
  },
  {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: [
      {
        "@type": "Question",
        name: "How do I monitor Claude Agent SDK with LangSight?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "Add two lines to your agent: import langsight and call langsight.auto_patch(). This automatically instruments all Claude Agent SDK operations including multi-agent handoffs, tool calls, LLM reasoning, and sub-agent invocations. No wrappers or decorators needed. LangSight captured 57 spans in benchmarks compared to 0 tool spans from Langfuse and LangSmith.",
        },
      },
      {
        "@type": "Question",
        name: "How do I monitor CrewAI agents with LangSight?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "LangSight integrates with CrewAI through its native event bus with 19 event handlers. Call langsight.auto_patch() before your crew runs. LangSight captures crew input/output, task execution, agent-to-agent handoffs (A2A), and LLM spans from Anthropic, OpenAI, and Gemini SDKs.",
        },
      },
      {
        "@type": "Question",
        name: "Does LangSight work with OpenAI and Gemini?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "Yes. LangSight captures LLM tracing, token counts, and cost tracking for OpenAI Chat Completions and Google Gemini generate_content calls. Both are in beta and support llm_input/llm_output capture on spans.",
        },
      },
    ],
  },
];

export default function IntegrationsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(integrationsJsonLd) }}
      />
      {children}
    </>
  );
}
