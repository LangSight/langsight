import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "LangSight vs Langfuse vs LangWatch — AI Agent Monitoring Comparison",
  description:
    "Compare LangSight, Langfuse, and LangWatch for AI agent monitoring. LangSight is the only platform with MCP health monitoring, security scanning, circuit breakers, and runtime guardrails. Free self-hosted.",
  keywords: [
    "LangSight vs Langfuse",
    "LangSight vs LangWatch",
    "Langfuse alternative",
    "LangWatch alternative",
    "AI agent monitoring comparison",
    "MCP observability comparison",
    "open source AI observability",
    "agent runtime reliability",
    "LangSmith alternative",
  ],
  openGraph: {
    title: "LangSight vs Langfuse vs LangWatch — AI Agent Monitoring Comparison",
    description:
      "LangSight is purpose-built for agent runtime reliability. Compare MCP health, security, circuit breakers, and guardrails against Langfuse and LangWatch.",
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
    name: "LangSight vs Langfuse vs LangWatch — AI Agent Monitoring Comparison",
    description:
      "Feature-by-feature comparison of LangSight, Langfuse, and LangWatch for AI agent monitoring and MCP observability.",
    url: "https://langsight.dev/alternatives/",
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
