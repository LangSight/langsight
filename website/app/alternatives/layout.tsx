import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "LangSight vs Langfuse vs LangWatch — Agent Runtime Reliability Comparison",
  description:
    "How does LangSight compare to Langfuse and LangWatch? LangSight is the only platform purpose-built for agent runtime reliability — MCP health, security scanning, circuit breakers, and guardrails. Free self-hosted.",
  keywords: [
    "LangSight vs Langfuse",
    "LangSight vs LangWatch",
    "agent runtime reliability comparison",
    "AI agent guardrails alternatives",
    "Langfuse alternative",
    "LangWatch alternative",
    "open source agent runtime reliability",
  ],
  openGraph: {
    title: "LangSight vs Langfuse vs LangWatch — Agent Runtime Reliability Comparison",
    description:
      "LangSight is purpose-built for agent runtime reliability — MCP health, security, circuit breakers, and guardrails. Compare features, pricing, and architecture against Langfuse and LangWatch.",
    url: "https://langsight.dev/alternatives",
    siteName: "LangSight",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "LangSight vs Langfuse vs LangWatch",
    description:
      "The only MCP-native agent runtime reliability platform. Compare LangSight vs Langfuse vs LangWatch.",
  },
  alternates: {
    canonical: "https://langsight.dev/alternatives/",
  },
};

export default function AlternativesLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
