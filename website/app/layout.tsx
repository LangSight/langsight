import type { Metadata } from "next";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import "./globals.css";

export const metadata: Metadata = {
  title: "LangSight — Agent Runtime Reliability for AI Toolchains",
  description:
    "Your agent failed. How do we stop it next time? Detect loops, enforce budgets, break failing tools, map blast radius. MCP health checks, security scanning, schema drift. Self-host free.",
  keywords: [
    "agent runtime reliability",
    "AI agent guardrails",
    "MCP server monitoring",
    "agent loop detection",
    "MCP health check",
    "MCP security scanning",
    "agent cost guardrails",
    "AI agent debugging",
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
    title: "LangSight — Agent Runtime Reliability for AI Toolchains",
    description:
      "Your agent failed. How do we stop it next time? Detect loops, enforce budgets, break failing tools, map blast radius. Self-host free.",
    url: "https://langsight.dev",
    siteName: "LangSight",
    type: "website",
    images: [{ url: "/og-image.svg", width: 1200, height: 630 }],
  },
  twitter: {
    card: "summary_large_image",
    title: "LangSight — Agent Runtime Reliability for AI Toolchains",
    description:
      "Your agent failed. How do we stop it next time? Detect loops, enforce budgets, break failing tools. Self-host free.",
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
    "Agent runtime reliability platform. Detect loops, enforce budgets, break failing tools, map blast radius. MCP health checks, CVE scanning, schema drift detection. Self-host free.",
  url: "https://langsight.dev",
  softwareVersion: "0.2.0",
  license: "https://github.com/LangSight/langsight/blob/main/LICENSE",
  offers: {
    "@type": "Offer",
    price: "0",
    priceCurrency: "USD",
    description: "Free self-hosted, BSL 1.1 open source",
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
