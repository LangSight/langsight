import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "LangSight vs Langfuse vs LangWatch — MCP Observability Comparison",
  description:
    "How does LangSight compare to Langfuse and LangWatch? LangSight is the only platform purpose-built for MCP server monitoring, security scanning, and AI agent tool call tracing. Free self-hosted.",
  keywords: [
    "LangSight vs Langfuse",
    "LangSight vs LangWatch",
    "MCP observability comparison",
    "AI agent monitoring alternatives",
    "Langfuse alternative",
    "LangWatch alternative",
    "open source AI observability",
  ],
  openGraph: {
    title: "LangSight vs Langfuse vs LangWatch — MCP Observability Comparison",
    description:
      "LangSight is purpose-built for MCP server monitoring and AI agent tool call tracing. Compare features, pricing, and architecture against Langfuse and LangWatch.",
    url: "https://langsight.dev/alternatives",
    siteName: "LangSight",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "LangSight vs Langfuse vs LangWatch",
    description:
      "The only MCP-native observability platform. Compare LangSight vs Langfuse vs LangWatch.",
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
