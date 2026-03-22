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

export default function BlogLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
