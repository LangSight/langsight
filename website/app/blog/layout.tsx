import type { Metadata } from "next";

export const metadata: Metadata = {
  title: { default: "Blog", template: "%s · LangSight Blog" },
  description:
    "Practical guides on AI agent reliability, MCP server monitoring, loop detection, cost guardrails, and security for teams running agents in production.",
  alternates: { canonical: "https://langsight.dev/blog/" },
  openGraph: {
    siteName: "LangSight",
    url: "https://langsight.dev/blog/",
    type: "website",
  },
};

const jsonLd = {
  "@context": "https://schema.org",
  "@type": "ItemList",
  name: "LangSight Blog",
  description:
    "Practical guides on AI agent reliability, MCP server monitoring, loop detection, cost guardrails, and security for teams running agents in production.",
  url: "https://langsight.dev/blog/",
  itemListElement: [
    {
      "@type": "ListItem",
      position: 1,
      url: "https://langsight.dev/blog/ai-agent-loop-detection/",
      name: "How to Detect and Stop AI Agent Loops in Production",
    },
    {
      "@type": "ListItem",
      position: 2,
      url: "https://langsight.dev/blog/mcp-server-security/",
      name: "MCP Server Security: OWASP Top 10 for Model Context Protocol",
    },
  ],
};

export default function BlogLayout({ children }: { children: React.ReactNode }) {
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
