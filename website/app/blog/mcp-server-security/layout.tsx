import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "MCP Server Security: OWASP Top 10 for Model Context Protocol",
  description:
    "66% of community MCP servers have critical security issues. Learn the OWASP MCP Top 10, tool poisoning attacks, CVE risks, and how to audit your MCP servers before they compromise your agents.",
  keywords: [
    "MCP server security",
    "MCP OWASP",
    "model context protocol security",
    "MCP tool poisoning",
    "MCP CVE",
    "secure MCP server",
    "MCP authentication",
    "MCP vulnerability",
    "AI agent security",
  ],
  alternates: { canonical: "https://langsight.dev/blog/mcp-server-security/" },
  openGraph: {
    title: "MCP Server Security: OWASP Top 10 for Model Context Protocol",
    description:
      "66% of community MCP servers have critical security issues. Learn the OWASP MCP Top 10 and how to audit your MCP servers.",
    url: "https://langsight.dev/blog/mcp-server-security/",
    type: "article",
    siteName: "LangSight",
    publishedTime: "2026-03-22T00:00:00Z",
    modifiedTime: "2026-03-22T00:00:00Z",
    authors: ["https://langsight.dev"],
    tags: ["MCP Security", "OWASP", "CVE", "MCP server security", "model context protocol security", "AI agent security"],
  },
  twitter: {
    card: "summary_large_image",
    title: "MCP Server Security: OWASP Top 10 for Model Context Protocol",
    description:
      "66% of community MCP servers have critical security issues. Learn how to audit yours.",
  },
};

const jsonLd = {
  "@context": "https://schema.org",
  "@type": "TechArticle",
  headline: "MCP Server Security: OWASP Top 10 for Model Context Protocol",
  description:
    "66% of community MCP servers have critical security issues. Learn the OWASP MCP Top 10, tool poisoning attacks, CVE risks, and how to audit your MCP servers before they compromise your agents.",
  datePublished: "2026-03-22T00:00:00Z",
  dateModified: "2026-03-22T00:00:00Z",
  wordCount: 2200,
  mainEntityOfPage: {
    "@type": "WebPage",
    "@id": "https://langsight.dev/blog/mcp-server-security/",
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
  image: "https://langsight.dev/og-image.svg",
  keywords: "MCP server security, MCP OWASP, model context protocol security, MCP tool poisoning, MCP CVE, AI agent security",
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
