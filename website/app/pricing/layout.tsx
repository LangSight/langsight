import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "LangSight Pricing — Free Self-Hosted Agent Runtime Reliability",
  description:
    "LangSight is free forever. Apache 2.0 — self-host the entire platform at $0. Loop detection, budget guardrails, MCP health, security scanning. No free tier, no feature gating.",
  keywords: [
    "LangSight pricing",
    "free self-hosted agent reliability",
    "open source AI agent guardrails",
    "MCP monitoring free",
    "agent runtime reliability pricing",
  ],
  openGraph: {
    title: "LangSight Pricing — Free Self-Hosted Agent Runtime Reliability",
    description:
      "Self-host the entire platform at $0. No free tier, no feature gating.",
    url: "https://langsight.dev/pricing",
    siteName: "LangSight",
    type: "website",
    images: [{ url: "/og-image.png", width: 1200, height: 630, alt: "LangSight — Free self-hosted agent reliability" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "LangSight Pricing — Free Self-Hosted",
    description:
      "Free forever. Apache 2.0. Self-host LangSight at $0 — loop detection, guardrails, MCP health, security.",
    images: ["/og-image.png"],
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
