import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Self-Hosting AI Observability: Keep Your Data Private",
  description:
    "Agent traces contain PII, API keys, business logic, and database queries. Sending them to a third-party SaaS creates data residency, compliance, and security risks. Self-hosting keeps your data in your network.",
  keywords: [
    "self-hosted AI observability",
    "self-host agent monitoring",
    "AI data privacy",
    "agent trace data residency",
    "open source observability",
    "AI compliance SOC2 GDPR",
    "self-hosted LLM monitoring",
    "Apache 2.0 observability",
  ],
  alternates: { canonical: "https://langsight.dev/blog/self-hosting-ai-observability/" },
  openGraph: {
    title: "Self-Hosting AI Observability: Keep Your Data Private",
    description:
      "Agent traces contain PII, API keys, and business logic. Self-hosting keeps your data in your network.",
    url: "https://langsight.dev/blog/self-hosting-ai-observability/",
    type: "article",
    siteName: "LangSight",
    publishedTime: "2026-04-02T00:00:00Z",
    modifiedTime: "2026-04-02T00:00:00Z",
    section: "Data Privacy",
    authors: ["https://langsight.dev"],
    tags: ["Self-Hosted", "Data Privacy", "Open Source", "self-hosted AI observability", "AI data privacy"],
    images: [{ url: "https://langsight.dev/blog/self-hosting-ai-observability.png", width: 1200, height: 630, alt: "Self-Hosting AI Observability" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "Self-Hosting AI Observability: Keep Your Data Private",
    description:
      "Agent traces contain PII, API keys, and business logic. Self-hosting keeps your data in your network.",
    images: ["https://langsight.dev/blog/self-hosting-ai-observability.png"],
  },
};

const jsonLd = [
  {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      { "@type": "ListItem", position: 1, name: "Home", item: "https://langsight.dev/" },
      { "@type": "ListItem", position: 2, name: "Blog", item: "https://langsight.dev/blog/" },
      { "@type": "ListItem", position: 3, name: "Self-Hosting AI Observability", item: "https://langsight.dev/blog/self-hosting-ai-observability/" },
    ],
  },
  {
    "@context": "https://schema.org",
    "@type": "TechArticle",
    headline: "Self-Hosting AI Observability: Why Your Data Should Never Leave",
    description:
      "Agent traces contain PII, API keys, business logic, and database queries. Sending them to a third-party SaaS creates data residency, compliance, and security risks. Self-hosting keeps your data in your network.",
    datePublished: "2026-04-02T00:00:00Z",
    dateModified: "2026-04-02T00:00:00Z",
    wordCount: 1600,
    mainEntityOfPage: { "@type": "WebPage", "@id": "https://langsight.dev/blog/self-hosting-ai-observability/" },
    author: { "@type": "Organization", name: "LangSight", url: "https://langsight.dev" },
    publisher: {
      "@type": "Organization",
      name: "LangSight",
      url: "https://langsight.dev",
      logo: { "@type": "ImageObject", url: "https://langsight.dev/logo-256.png", width: 256, height: 256 },
    },
    image: "https://langsight.dev/blog/self-hosting-ai-observability.png",
    keywords: "self-hosted AI observability, self-host agent monitoring, AI data privacy, agent trace data residency, open source observability",
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
