import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "LangSight Pricing — Free Self-Hosted MCP Observability",
  description:
    "LangSight is free forever. Apache 2.0 open source — self-host the entire platform at $0. No free tier, no feature gating. Full MCP observability and security scanning, always free.",
  keywords: [
    "LangSight pricing",
    "free self-hosted observability",
    "open source AI agent monitoring",
    "MCP observability free",
    "self-hosted LLM tracing",
  ],
  openGraph: {
    title: "LangSight Pricing — Free Self-Hosted MCP Observability",
    description:
      "LangSight is Apache 2.0 open source. Self-host the entire platform at $0. No free tier, no feature gating.",
    url: "https://langsight.dev/pricing",
    siteName: "LangSight",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "LangSight Pricing — Free Self-Hosted MCP Observability",
    description:
      "Free forever. Apache 2.0 open source. Self-host LangSight at $0 with no feature gating.",
  },
  alternates: {
    canonical: "https://langsight.dev/pricing/",
  },
};

export default function PricingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
