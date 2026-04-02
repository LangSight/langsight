import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "OWASP MCP Top 10 Explained: A Practical Guide",
  description:
    "The OWASP MCP Top 10 defines the most critical security risks for Model Context Protocol servers. Here's what each risk means, real-world examples, and how to audit your servers against every check.",
  keywords: [
    "OWASP MCP Top 10",
    "MCP security risks",
    "MCP server security audit",
    "OWASP MCP",
    "MCP vulnerability",
    "MCP security best practices",
    "MCP compliance",
    "MCP authentication",
    "MCP tool poisoning",
    "MCP schema drift",
  ],
  alternates: { canonical: "https://langsight.dev/blog/owasp-mcp-top-10-guide/" },
  openGraph: {
    title: "OWASP MCP Top 10 Explained: A Practical Guide",
    description:
      "The OWASP MCP Top 10 defines the most critical security risks for MCP servers. Real-world examples and remediation for every check.",
    url: "https://langsight.dev/blog/owasp-mcp-top-10-guide/",
    type: "article",
    siteName: "LangSight",
    publishedTime: "2026-04-02T00:00:00Z",
    modifiedTime: "2026-04-02T00:00:00Z",
    authors: ["https://langsight.dev"],
    tags: ["OWASP", "MCP Security", "Compliance", "OWASP MCP Top 10", "MCP vulnerability"],
  },
  twitter: {
    card: "summary_large_image",
    title: "OWASP MCP Top 10 Explained: A Practical Guide",
    description:
      "The OWASP MCP Top 10 defines the most critical security risks for MCP servers. Real-world examples and remediation for every check.",
  },
};

const jsonLd = {
  "@context": "https://schema.org",
  "@type": "TechArticle",
  headline: "OWASP MCP Top 10 Explained: A Practical Guide",
  description:
    "The OWASP MCP Top 10 defines the most critical security risks for Model Context Protocol servers. Here's what each risk means, real-world examples, and how to audit your servers against every check.",
  datePublished: "2026-04-02T00:00:00Z",
  dateModified: "2026-04-02T00:00:00Z",
  wordCount: 2600,
  mainEntityOfPage: {
    "@type": "WebPage",
    "@id": "https://langsight.dev/blog/owasp-mcp-top-10-guide/",
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
  keywords: "OWASP MCP Top 10, MCP security risks, MCP server security audit, OWASP MCP, MCP vulnerability, MCP security best practices, MCP compliance",
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
