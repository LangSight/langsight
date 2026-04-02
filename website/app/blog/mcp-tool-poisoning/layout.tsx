import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "MCP Tool Poisoning: How Attackers Hijack AI Agents",
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
    title: "MCP Tool Poisoning: How Attackers Hijack AI Agents",
    description:
      "Hidden instructions in MCP tool descriptions that manipulate LLM behavior. Three attack patterns and automated detection.",
    url: "https://langsight.dev/blog/mcp-tool-poisoning/",
    type: "article",
    siteName: "LangSight",
    publishedTime: "2026-04-02T00:00:00Z",
    modifiedTime: "2026-04-02T00:00:00Z",
    section: "Security",
    authors: ["https://langsight.dev"],
    tags: ["Tool Poisoning", "Security", "Attack Vectors", "MCP tool poisoning", "prompt injection MCP"],
    images: [{ url: "https://langsight.dev/blog/mcp-tool-poisoning.png", width: 1200, height: 630, alt: "MCP Tool Poisoning: How Attackers Hijack AI Agents" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "MCP Tool Poisoning: How Attackers Hijack AI Agents",
    description:
      "Hidden instructions in MCP tool descriptions that manipulate LLM behavior. Three attack patterns and automated detection.",
    images: ["https://langsight.dev/blog/mcp-tool-poisoning.png"],
  },
};

const jsonLd = [
  {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      { "@type": "ListItem", position: 1, name: "Home", item: "https://langsight.dev/" },
      { "@type": "ListItem", position: 2, name: "Blog", item: "https://langsight.dev/blog/" },
      { "@type": "ListItem", position: 3, name: "MCP Tool Poisoning", item: "https://langsight.dev/blog/mcp-tool-poisoning/" },
    ],
  },
  {
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
    image: "https://langsight.dev/blog/mcp-tool-poisoning.png",
    keywords: "MCP tool poisoning, tool description injection, MCP attack vector, AI agent hijack, prompt injection MCP",
  },
  {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: [
      {
        "@type": "Question",
        name: "What is MCP tool poisoning?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "MCP tool poisoning is the act of embedding malicious instructions inside a tool's description. Because the LLM treats tool descriptions as part of its system context with the same trust level as the system prompt, hidden instructions in descriptions are followed as faithfully as explicit developer instructions.",
        },
      },
      {
        "@type": "Question",
        name: "What are the three attack patterns for MCP tool poisoning?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "The three attack patterns are: (1) Instruction injection, where imperative commands are appended to tool descriptions; (2) Hidden Unicode, where zero-width characters encode invisible payloads; and (3) Base64 encoded payloads, where encoded instructions are embedded as seemingly legitimate example data.",
        },
      },
      {
        "@type": "Question",
        name: "How do you detect MCP tool poisoning?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "Detection involves scanning tool descriptions for imperative instruction patterns, extracting and verifying URLs and email addresses, detecting zero-width Unicode characters, finding and decoding base64 strings, and comparing current descriptions against previous snapshots. LangSight automates all five checks in its security scanner.",
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
