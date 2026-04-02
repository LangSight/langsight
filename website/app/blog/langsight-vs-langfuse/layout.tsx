import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "LangSight vs Langfuse: Different Tools for Different Problems",
  description:
    "LangSight and Langfuse solve fundamentally different problems. Langfuse watches the brain (LLM observability). LangSight watches the hands (runtime reliability). Use both.",
  keywords: [
    "LangSight vs Langfuse",
    "Langfuse alternative",
    "LLM observability comparison",
    "AI agent monitoring tools",
    "Langfuse comparison",
    "agent observability",
    "MCP monitoring vs LLM tracing",
    "AI observability stack",
  ],
  alternates: { canonical: "https://langsight.dev/blog/langsight-vs-langfuse/" },
  openGraph: {
    title: "LangSight vs Langfuse: Different Tools for Different Problems",
    description:
      "Langfuse watches the brain. LangSight watches the hands. Use both.",
    url: "https://langsight.dev/blog/langsight-vs-langfuse/",
    type: "article",
    siteName: "LangSight",
    publishedTime: "2026-04-02T00:00:00Z",
    modifiedTime: "2026-04-02T00:00:00Z",
    authors: ["https://langsight.dev"],
    tags: ["Comparison", "Langfuse", "Observability", "LangSight vs Langfuse", "AI observability stack"],
  },
  twitter: {
    card: "summary_large_image",
    title: "LangSight vs Langfuse: Different Tools for Different Problems",
    description:
      "Langfuse watches the brain. LangSight watches the hands. Use both.",
  },
};

const jsonLd = {
  "@context": "https://schema.org",
  "@type": "TechArticle",
  headline: "LangSight vs Langfuse: Different Tools for Different Problems",
  description:
    "LangSight and Langfuse solve fundamentally different problems. Langfuse watches the brain (LLM observability). LangSight watches the hands (runtime reliability). Use both.",
  datePublished: "2026-04-02T00:00:00Z",
  dateModified: "2026-04-02T00:00:00Z",
  wordCount: 1600,
  mainEntityOfPage: {
    "@type": "WebPage",
    "@id": "https://langsight.dev/blog/langsight-vs-langfuse/",
  },
  author: {
    "@type": "Organization",
    name: "LangSight",
    url: "https://langsight.dev",
  },
  publisher: {
    "@type": "Organization",
    name: "LangSight",
    url: "https://langsight.dev",
    logo: {
      "@type": "ImageObject",
      url: "https://langsight.dev/logo-256.png",
      width: 256,
      height: 256,
    },
  },
  image: "https://langsight.dev/og-image.png",
  keywords: "LangSight vs Langfuse, Langfuse alternative, LLM observability comparison, AI agent monitoring tools",
};

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
