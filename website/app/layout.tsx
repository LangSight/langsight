import type { Metadata } from "next";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import "./globals.css";

export const metadata: Metadata = {
  title: "LangSight — MCP Observability & AI Agent Tracing",
  description:
    "Your agent broke. Here's exactly why. Trace every tool call, monitor MCP server health, scan for CVEs and OWASP issues, and attribute costs. Open-source MCP observability — self-host free.",
  keywords: [
    "MCP observability",
    "AI agent tracing",
    "MCP server monitoring",
    "agent tool call tracing",
    "MCP health check",
    "MCP security scanning",
    "open source AI observability",
    "AI agent debugging",
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
    title: "LangSight — MCP Observability & AI Agent Tracing",
    description:
      "Your agent broke. Here's exactly why. Open-source MCP observability: trace every tool call, monitor MCP health, scan for CVEs and OWASP issues. Self-host free.",
    url: "https://langsight.dev",
    siteName: "LangSight",
    type: "website",
    images: [{ url: "/og-image.svg", width: 1200, height: 630 }],
  },
  twitter: {
    card: "summary_large_image",
    title: "LangSight — MCP Observability & AI Agent Tracing",
    description:
      "Your agent broke. Here's exactly why. Open-source MCP observability — self-host free.",
    images: ["/og-image.svg"],
  },
};

const jsonLd = {
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  name: "LangSight",
  applicationCategory: "DeveloperApplication",
  operatingSystem: "Linux, macOS, Windows",
  description:
    "Open-source MCP observability and security platform for AI agents. Trace every tool call, monitor MCP server health, scan for CVEs and OWASP issues, and attribute costs. Self-host free.",
  url: "https://langsight.dev",
  softwareVersion: "0.2.0",
  license: "https://www.apache.org/licenses/LICENSE-2.0",
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
  },
  sameAs: ["https://github.com/LangSight/langsight"],
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${GeistSans.variable} ${GeistMono.variable}`}>
      <head>
        {/* Preconnect to Cloudflare CDN to reduce CSS blocking time */}
        <link rel="preconnect" href="https://langsight.dev" />
        <link rel="dns-prefetch" href="https://langsight.dev" />
        {/* JSON-LD structured data — SoftwareApplication schema */}
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
