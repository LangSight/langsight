import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "MCP Tool Poisoning: How Attackers Hijack AI Agents Through Tool Descriptions",
  description:
    "Tool poisoning is the most dangerous attack vector in MCP: hidden instructions in tool descriptions that manipulate LLM behavior. Three attack patterns, real examples, and automated detection.",
  keywords: [
    "MCP tool poisoning",
    "tool description injection",
    "MCP attack vector",
    "AI agent hijack",
    "prompt injection MCP",
    "MCP security vulnerability",
    "tool description manipulation",
    "MCP hidden instructions",
  ],
  alternates: { canonical: "https://langsight.dev/blog/mcp-tool-poisoning/" },
  openGraph: {
    title: "MCP Tool Poisoning: How Attackers Hijack AI Agents Through Tool Descriptions",
    description:
      "Hidden instructions in MCP tool descriptions that manipulate LLM behavior. Three attack patterns and automated detection.",
    url: "https://langsight.dev/blog/mcp-tool-poisoning/",
    type: "article",
    siteName: "LangSight",
    publishedTime: "2026-04-02T00:00:00Z",
    modifiedTime: "2026-04-02T00:00:00Z",
    authors: ["https://langsight.dev"],
    tags: ["Tool Poisoning", "Security", "Attack Vectors", "MCP tool poisoning", "prompt injection MCP"],
  },
  twitter: {
    card: "summary_large_image",
    title: "MCP Tool Poisoning: How Attackers Hijack AI Agents Through Tool Descriptions",
    description:
      "Hidden instructions in MCP tool descriptions that manipulate LLM behavior. Three attack patterns and automated detection.",
  },
};

const jsonLd = {
  "@context": "https://schema.org",
  "@type": "TechArticle",
  headline: "MCP Tool Poisoning: How Attackers Hijack AI Agents Through Tool Descriptions",
  description:
    "Tool poisoning is the most dangerous attack vector in MCP: hidden instructions in tool descriptions that manipulate LLM behavior. Three attack patterns, real examples, and automated detection.",
  datePublished: "2026-04-02T00:00:00Z",
  dateModified: "2026-04-02T00:00:00Z",
  wordCount: 1900,
  mainEntityOfPage: {
    "@type": "WebPage",
    "@id": "https://langsight.dev/blog/mcp-tool-poisoning/",
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
  keywords: "MCP tool poisoning, tool description injection, MCP attack vector, AI agent hijack, prompt injection MCP",
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
