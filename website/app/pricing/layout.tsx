import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Pricing — Free Open Source AI Agent Monitoring",
  description:
    "LangSight is free forever. Apache 2.0 open source. Self-host the full AI agent monitoring platform at $0 — loop detection, budget guardrails, MCP health monitoring, security scanning. No feature gating.",
  keywords: [
    "LangSight pricing",
    "free AI agent monitoring",
    "open source AI observability",
    "free self-hosted agent monitoring",
    "MCP monitoring free",
    "agent runtime reliability pricing",
    "free MCP health monitoring",
  ],
  openGraph: {
    title: "LangSight Pricing — Free Open Source AI Agent Monitoring",
    description:
      "Self-host the full AI agent monitoring platform at $0. Loop detection, budget guardrails, MCP health, security scanning. Apache 2.0, no feature gating.",
    url: "https://langsight.dev/pricing",
    siteName: "LangSight",
    type: "website",
    images: [{ url: "/og-image.png", width: 1200, height: 630, alt: "LangSight Pricing — Free open source AI agent monitoring" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "LangSight Pricing — Free Open Source AI Agent Monitoring",
    description:
      "Free forever. Apache 2.0. Self-host LangSight at $0 — loop detection, guardrails, MCP health, security.",
    images: ["/og-image.png"],
  },
  alternates: {
    canonical: "https://langsight.dev/pricing/",
  },
};

const pricingJsonLd = [
  {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      { "@type": "ListItem", position: 1, name: "Home", item: "https://langsight.dev/" },
      { "@type": "ListItem", position: 2, name: "Pricing", item: "https://langsight.dev/pricing/" },
    ],
  },
  {
    "@context": "https://schema.org",
    "@type": "Product",
    name: "LangSight — Open Source AI Agent Monitoring",
    description:
      "Free, open source AI agent monitoring and MCP server observability platform. Loop detection, budget guardrails, circuit breakers, MCP health, security scanning. Apache 2.0.",
    brand: { "@type": "Brand", name: "LangSight" },
    offers: {
      "@type": "Offer",
      price: "0",
      priceCurrency: "USD",
      availability: "https://schema.org/InStock",
      description: "Free self-hosted, Apache 2.0 open source. No usage limits, no feature gating.",
      url: "https://langsight.dev/pricing/",
    },
  },
  {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: [
      {
        "@type": "Question",
        name: "Is LangSight really free?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "Yes. LangSight is Apache 2.0 open source. You can self-host it for free, forever, for any use including commercial. There is no paid tier today. When a cloud tier launches, the self-hosted version will remain free and fully featured.",
        },
      },
      {
        "@type": "Question",
        name: "What infrastructure do I need to self-host LangSight?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "LangSight requires Docker. Copy .env.example to .env, fill in the required passwords, then run docker compose up -d. PostgreSQL (metadata) and ClickHouse (analytics) both start automatically. The full stack is up in under 5 minutes.",
        },
      },
      {
        "@type": "Question",
        name: "Does my data leave my network with LangSight?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "No. LangSight is entirely self-hosted. Your agent traces, tool call payloads, and cost data never leave your infrastructure. The only outbound requests are CVE database lookups during security scans, which you can disable.",
        },
      },
    ],
  },
];

export default function PricingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(pricingJsonLd) }}
      />
      {children}
    </>
  );
}
