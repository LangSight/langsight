import type { Metadata } from "next";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import "./globals.css";

export const metadata: Metadata = {
  title: "LangSight — MCP Observability for AI Agents",
  description:
    "Your agent failed. Which tool broke — and why? Trace every tool call, monitor MCP server health, scan for CVEs and OWASP issues, and attribute costs. Self-host free.",
  keywords: ["AI agent observability", "MCP monitoring", "MCP health check", "MCP security", "LangChain tracing", "agent debugging", "tool call tracing"],
  icons: {
    icon: [
      { url: "/favicon-16.png", sizes: "16x16", type: "image/png" },
      { url: "/favicon-32.png", sizes: "32x32", type: "image/png" },
      { url: "/logo-256.png",   sizes: "256x256", type: "image/png" },
    ],
    apple: "/apple-touch-icon.png",
  },
  openGraph: {
    title: "LangSight — MCP Observability for AI Agents",
    description: "Your agent failed. Which tool broke — and why?",
    url: "https://langsight.dev",
    siteName: "LangSight",
    type: "website",
    images: [{ url: "/og-image.svg", width: 1200, height: 630 }],
  },
  twitter: {
    card: "summary_large_image",
    title: "LangSight — MCP Observability for AI Agents",
    description: "Your agent failed. Which tool broke — and why?",
    images: ["/og-image.svg"],
  },
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
      </head>
      <body>{children}</body>
    </html>
  );
}
