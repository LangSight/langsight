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
    section: "Security",
    authors: ["https://langsight.dev"],
    tags: ["MCP Security", "OWASP", "CVE", "MCP server security", "model context protocol security", "AI agent security"],
    images: [{ url: "https://langsight.dev/blog/mcp-server-security.png", width: 1200, height: 630, alt: "MCP Server Security" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "MCP Server Security: OWASP Top 10 for Model Context Protocol",
    description:
      "66% of community MCP servers have critical security issues. Learn how to audit yours.",
    images: ["https://langsight.dev/blog/mcp-server-security.png"],
  },
};

const jsonLd = [
  {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      { "@type": "ListItem", position: 1, name: "Home", item: "https://langsight.dev/" },
      { "@type": "ListItem", position: 2, name: "Blog", item: "https://langsight.dev/blog/" },
      { "@type": "ListItem", position: 3, name: "MCP Server Security", item: "https://langsight.dev/blog/mcp-server-security/" },
    ],
  },
  {
    "@context": "https://schema.org",
    "@type": "TechArticle",
    headline: "MCP Server Security: OWASP Top 10 for Model Context Protocol",
    description:
      "66% of community MCP servers have critical security issues. Learn the OWASP MCP Top 10, tool poisoning attacks, CVE risks, and how to audit your MCP servers before they compromise your agents.",
    datePublished: "2026-03-22T00:00:00Z",
    dateModified: "2026-03-22T00:00:00Z",
    wordCount: 2200,
    mainEntityOfPage: { "@type": "WebPage", "@id": "https://langsight.dev/blog/mcp-server-security/" },
    author: { "@type": "Organization", name: "LangSight", url: "https://langsight.dev" },
    publisher: {
      "@type": "Organization",
      name: "LangSight",
      url: "https://langsight.dev",
      logo: { "@type": "ImageObject", url: "https://langsight.dev/logo-256.png", width: 256, height: 256 },
    },
    image: "https://langsight.dev/blog/mcp-server-security.png",
    keywords: "MCP server security, MCP OWASP, model context protocol security, MCP tool poisoning, MCP CVE, AI agent security",
  },
  {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: [
      {
        "@type": "Question",
        name: "How do you run a security audit on MCP servers?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "Install LangSight with pip install langsight, run langsight init to auto-discover MCP servers from your Claude Desktop, Cursor, or VS Code config, then run langsight security-scan. The scan checks all servers against the OWASP MCP Top 10, the OSV CVE database, and a tool poisoning detector in under 60 seconds.",
        },
      },
      {
        "@type": "Question",
        name: "What are the most critical MCP security vulnerabilities in 2026?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "The highest-priority CVEs are CVE-2025-6514 in mcp-remote (remote code execution, upgrade to 0.1.16+), CVE-2025-3201 in fastmcp (SSRF, upgrade to 2.0.1+), and CVE-2026-0112 in anthropic-mcp (upgrade to 1.2.0+). Tool description injection (OWASP MCP-01) remains the highest-severity risk category.",
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
