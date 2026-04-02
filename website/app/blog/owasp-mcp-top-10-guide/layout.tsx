import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "OWASP MCP Top 10 Explained: A Practical Guide",
  description:
    "The OWASP MCP Top 10 defines the most critical security risks for Model Context Protocol servers. Here is what each risk means, real-world examples, and how to audit your servers against every check.",
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
    section: "MCP Security",
    authors: ["https://langsight.dev"],
    tags: ["OWASP", "MCP Security", "Compliance", "OWASP MCP Top 10", "MCP vulnerability"],
    images: [{ url: "https://langsight.dev/blog/owasp-mcp-top-10-guide.png", width: 1200, height: 630, alt: "OWASP MCP Top 10 Explained" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "OWASP MCP Top 10 Explained: A Practical Guide",
    description:
      "The OWASP MCP Top 10 defines the most critical security risks for MCP servers. Real-world examples and remediation for every check.",
    images: ["https://langsight.dev/blog/owasp-mcp-top-10-guide.png"],
  },
};

const jsonLd = [
  {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      { "@type": "ListItem", position: 1, name: "Home", item: "https://langsight.dev/" },
      { "@type": "ListItem", position: 2, name: "Blog", item: "https://langsight.dev/blog/" },
      { "@type": "ListItem", position: 3, name: "OWASP MCP Top 10 Guide", item: "https://langsight.dev/blog/owasp-mcp-top-10-guide/" },
    ],
  },
  {
    "@context": "https://schema.org",
    "@type": "TechArticle",
    headline: "OWASP MCP Top 10 Explained: A Practical Guide",
    description:
      "The OWASP MCP Top 10 defines the most critical security risks for Model Context Protocol servers. Here is what each risk means, real-world examples, and how to audit your servers against every check.",
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
    image: "https://langsight.dev/blog/owasp-mcp-top-10-guide.png",
    keywords: "OWASP MCP Top 10, MCP security risks, MCP server security audit, OWASP MCP, MCP vulnerability, MCP security best practices, MCP compliance",
  },
  {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: [
      {
        "@type": "Question",
        name: "What is the OWASP MCP Top 10?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "The OWASP MCP Top 10 is a ranked list of the most critical security issues in Model Context Protocol implementations, published by the Open Worldwide Application Security Project in late 2025. It covers tool description injection, missing authentication, excessive permissions, input validation, schema drift, unencrypted transport, dependency CVEs, output trust, rate limiting, and insufficient logging.",
        },
      },
      {
        "@type": "Question",
        name: "What is the most critical risk in the OWASP MCP Top 10?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "MCP-01: Tool Description Injection is the highest-severity risk. It weaponizes the core mechanism of MCP by embedding instructions in tool descriptions that the LLM follows as system-level commands. This can cause agents to exfiltrate data, call unauthorized tools, or take harmful actions.",
        },
      },
      {
        "@type": "Question",
        name: "How do you audit MCP servers against the OWASP MCP Top 10?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "Use automated scanning tools like LangSight's security-scan command, which checks all configured MCP servers against all 10 OWASP risks. This includes CVE detection, tool poisoning pattern matching, authentication auditing, schema drift detection, and transport encryption verification. Run the scan in CI/CD to block deployments with critical findings.",
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
