import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Schema Drift in MCP: The Silent Agent Failure",
  description:
    "When an MCP server changes its tool schemas, agents tested against the old schema silently start failing. Here is how schema drift happens, why agents cannot detect it, and how to monitor for it.",
  keywords: [
    "MCP schema drift",
    "MCP tool schema change",
    "MCP breaking change",
    "schema drift detection",
    "MCP version management",
    "AI agent silent failure",
    "MCP schema monitoring",
    "tool schema versioning",
  ],
  alternates: { canonical: "https://langsight.dev/blog/mcp-schema-drift/" },
  openGraph: {
    title: "Schema Drift in MCP: The Silent Agent Failure",
    description:
      "When an MCP server changes its tool schemas, agents silently start failing. How to detect and prevent schema drift.",
    url: "https://langsight.dev/blog/mcp-schema-drift/",
    type: "article",
    siteName: "LangSight",
    publishedTime: "2026-04-02T00:00:00Z",
    modifiedTime: "2026-04-02T00:00:00Z",
    section: "MCP Reliability",
    authors: ["https://langsight.dev"],
    tags: ["Schema Drift", "MCP Health", "Silent Failures", "MCP schema drift", "schema drift detection"],
    images: [{ url: "https://langsight.dev/blog/mcp-schema-drift.png", width: 1200, height: 630, alt: "Schema Drift in MCP" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "Schema Drift in MCP: The Silent Agent Failure",
    description:
      "When an MCP server changes its tool schemas, agents silently start failing. How to detect and prevent schema drift.",
    images: ["https://langsight.dev/blog/mcp-schema-drift.png"],
  },
};

const jsonLd = [
  {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      { "@type": "ListItem", position: 1, name: "Home", item: "https://langsight.dev/" },
      { "@type": "ListItem", position: 2, name: "Blog", item: "https://langsight.dev/blog/" },
      { "@type": "ListItem", position: 3, name: "MCP Schema Drift", item: "https://langsight.dev/blog/mcp-schema-drift/" },
    ],
  },
  {
    "@context": "https://schema.org",
    "@type": "TechArticle",
    headline: "Schema Drift in MCP: The Silent Failure Your Agents Cannot Detect",
    description:
      "When an MCP server changes its tool schemas, agents tested against the old schema silently start failing. Here is how schema drift happens, why agents cannot detect it, and how to monitor for it.",
    datePublished: "2026-04-02T00:00:00Z",
    dateModified: "2026-04-02T00:00:00Z",
    wordCount: 1900,
    mainEntityOfPage: { "@type": "WebPage", "@id": "https://langsight.dev/blog/mcp-schema-drift/" },
    author: { "@type": "Organization", name: "LangSight", url: "https://langsight.dev" },
    publisher: {
      "@type": "Organization",
      name: "LangSight",
      url: "https://langsight.dev",
      logo: { "@type": "ImageObject", url: "https://langsight.dev/logo-256.png", width: 256, height: 256 },
    },
    image: "https://langsight.dev/blog/mcp-schema-drift.png",
    keywords: "MCP schema drift, MCP tool schema change, schema drift detection, MCP version management, AI agent silent failure",
  },
  {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: [
      {
        "@type": "Question",
        name: "What is MCP schema drift?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "MCP schema drift occurs when an MCP server changes a tool's input schema between versions. A parameter gets renamed, a field type changes, a new required argument is added, or a tool is removed. Agents tested against the old schema continue calling with old argument names, leading to silent failures or incorrect results.",
        },
      },
      {
        "@type": "Question",
        name: "What are the three failure modes of schema drift?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "The three failure modes are: (1) Hard failure where the server rejects invalid arguments with a clear error; (2) Partial results where the server ignores unrecognized arguments and returns incomplete data; and (3) Semantic shift where field names stay the same but meanings change, making detection nearly impossible without full schema comparison.",
        },
      },
    ],
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
