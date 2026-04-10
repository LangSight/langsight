import type { Metadata } from "next";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL("https://langsight.dev"),
  title: {
    default: "LangSight — AI Agent Monitoring & MCP Server Observability",
    template: "%s | LangSight",
  },
  description:
    "Open source AI agent monitoring and MCP server observability. Detect loops, enforce budgets, circuit-break failing tools, scan for CVEs, and monitor MCP health. Self-host free, Apache 2.0.",
  keywords: [
    "AI agent monitoring",
    "MCP server monitoring",
    "MCP observability",
    "AI agent observability",
    "agent loop detection",
    "MCP health check",
    "MCP security scanning",
    "agent tool call tracing",
    "open source AI observability",
    "agent runtime reliability",
    "Claude Agent SDK monitoring",
    "CrewAI monitoring",
    "AI agent budget guardrails",
    "agent cost guardrails",
    "tool call circuit breaker",
  ],
  alternates: {
    canonical: "https://langsight.dev/",
  },
  icons: {
    icon: [
      { url: "/favicon-16.png", sizes: "16x16", type: "image/png" },
      { url: "/favicon-32.png", sizes: "32x32", type: "image/png" },
      { url: "/logo-256.png",   sizes: "256x256", type: "image/png" },
    ],
    apple: "/apple-touch-icon.png",
  },
  openGraph: {
    title: "LangSight — AI Agent Monitoring & MCP Server Observability",
    description:
      "Open source AI agent monitoring and MCP server observability. Detect loops, enforce budgets, circuit-break failing tools. Self-host free, Apache 2.0.",
    url: "https://langsight.dev",
    siteName: "LangSight",
    type: "website",
    locale: "en_US",
    images: [{ url: "/og-image.png", width: 1200, height: 630, alt: "LangSight — AI Agent Monitoring & MCP Server Observability" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "LangSight — AI Agent Monitoring & MCP Server Observability",
    description:
      "Open source AI agent monitoring and MCP observability. Detect loops, enforce budgets, circuit-break failing tools. Self-host free.",
    images: ["/og-image.png"],
    creator: "@LangSight",
  },
};

const jsonLd = [
  {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    name: "LangSight",
    applicationCategory: "DeveloperApplication",
    applicationSubCategory: "AI Agent Monitoring",
    operatingSystem: "Linux, macOS, Windows",
    description:
      "Open source AI agent monitoring and MCP server observability platform. Detect loops, enforce budgets, circuit-break failing tools, map blast radius. MCP health checks, CVE scanning, schema drift detection. Self-host free under Apache 2.0.",
    url: "https://langsight.dev",
    softwareVersion: "0.14.18",
    license: "https://github.com/LangSight/langsight/blob/main/LICENSE",
    offers: {
      "@type": "Offer",
      price: "0",
      priceCurrency: "USD",
      description: "Free self-hosted, Apache 2.0 open source",
    },
    author: {
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
    sameAs: ["https://github.com/LangSight/langsight"],
    featureList: [
      "AI agent loop detection",
      "Budget enforcement and cost guardrails",
      "Tool-level circuit breakers",
      "MCP server health monitoring",
      "MCP security scanning (CVE + OWASP)",
      "Schema drift detection",
      "Multi-agent call tree tracing",
      "Anomaly detection",
      "Blast radius mapping",
      "Cost attribution per tool call",
    ],
  },
  {
    "@context": "https://schema.org",
    "@type": "Organization",
    name: "LangSight",
    url: "https://langsight.dev",
    logo: "https://langsight.dev/logo-256.png",
    sameAs: ["https://github.com/LangSight/langsight"],
  },
  {
    "@context": "https://schema.org",
    "@type": "WebSite",
    name: "LangSight",
    url: "https://langsight.dev",
    potentialAction: {
      "@type": "SearchAction",
      target: "https://langsight.dev/glossary/?q={search_term_string}",
      "query-input": "required name=search_term_string",
    },
  },
];

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${GeistSans.variable} ${GeistMono.variable}`}>
      <head>
        {/* Inline script to apply saved theme class before first paint — prevents flash */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var s=localStorage.getItem('ls-theme');var d=s?s==='dark':window.matchMedia('(prefers-color-scheme: dark)').matches;if(d)document.documentElement.classList.add('dark');}catch(e){}})();`,
          }}
        />
        {/* Preconnect to third-party origins to reduce blocking time */}
        <link rel="preconnect" href="https://www.googletagmanager.com" />
        <link rel="dns-prefetch" href="https://www.google-analytics.com" />
        {/* JSON-LD structured data — SoftwareApplication schema */}
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
        />
        {/* Google Analytics GA4 */}
        <script async src="https://www.googletagmanager.com/gtag/js?id=G-S6E7SBNNXL" />
        <script
          dangerouslySetInnerHTML={{
            __html: `window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}gtag('js',new Date());gtag('config','G-S6E7SBNNXL');`,
          }}
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
