import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "MCP Security Scanning — CVE Detection & OWASP MCP Top 10",
  description:
    "Automated MCP security scanning for AI agent toolchains. Detect CVEs, run 5 of 10 OWASP MCP checks, find tool poisoning attacks, and audit auth gaps across your entire MCP fleet. One CLI command. CI/CD ready.",
  keywords: [
    "MCP security scanning",
    "OWASP MCP Top 10",
    "MCP CVE detection",
    "AI agent security",
    "MCP server security audit",
    "tool poisoning detection",
    "agent runtime reliability",
    "MCP auth audit",
    "AI agent guardrails",
    "schema drift detection",
  ],
  openGraph: {
    title: "MCP Security Scanning — CVE Detection & OWASP MCP Top 10 | LangSight",
    description:
      "Automated CVE detection, OWASP MCP checks, tool poisoning detection, and auth gap analysis for your entire MCP fleet. Free, open source, CI/CD ready.",
    url: "https://langsight.dev/security",
    siteName: "LangSight",
    type: "website",
    images: [{ url: "/og-image.png", width: 1200, height: 630, alt: "LangSight MCP Security Scanner — CVE and OWASP MCP Top 10 scanning" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "MCP Security Scanning — CVE Detection & OWASP MCP Top 10 | LangSight",
    description:
      "Automated MCP security scanning: CVEs, OWASP MCP Top 10, tool poisoning, auth gaps. One command, CI/CD ready.",
    images: ["/og-image.png"],
  },
  alternates: {
    canonical: "https://langsight.dev/security/",
  },
};

const securityJsonLd = [
  {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      { "@type": "ListItem", position: 1, name: "Home", item: "https://langsight.dev/" },
      { "@type": "ListItem", position: 2, name: "MCP Security Scanning", item: "https://langsight.dev/security/" },
    ],
  },
  {
    "@context": "https://schema.org",
    "@type": "WebPage",
    name: "MCP Security Scanning — CVE Detection & OWASP MCP Top 10",
    description:
      "Automated MCP security scanning for AI agent toolchains. Detect CVEs, run OWASP MCP Top 10 checks, find tool poisoning attacks, and audit auth gaps.",
    url: "https://langsight.dev/security/",
    isPartOf: {
      "@type": "WebSite",
      name: "LangSight",
      url: "https://langsight.dev",
    },
    mainEntity: {
      "@type": "SoftwareApplication",
      name: "LangSight Security Scanner",
      applicationCategory: "SecurityApplication",
      operatingSystem: "Linux, macOS, Windows",
      description:
        "CLI-based MCP security scanner that detects CVEs, runs OWASP MCP Top 10 checks, identifies tool poisoning attacks, and audits authentication gaps. Integrates into CI/CD pipelines.",
      offers: {
        "@type": "Offer",
        price: "0",
        priceCurrency: "USD",
      },
    },
  },
  {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: [
      {
        "@type": "Question",
        name: "What is MCP security scanning?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "MCP security scanning is the automated process of checking MCP (Model Context Protocol) servers for security vulnerabilities. This includes CVE detection against known vulnerability databases, OWASP MCP Top 10 compliance checks, tool poisoning detection, auth gap analysis, and schema drift monitoring. LangSight automates 5 of the 10 OWASP MCP checks.",
        },
      },
      {
        "@type": "Question",
        name: "What is the OWASP MCP Top 10?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "The OWASP MCP Top 10 is a community-maintained list of the ten most critical security risks in MCP-based systems: MCP-01 (No Authentication), MCP-02 (Destructive Tools Without Auth), MCP-03 (Training Data Poisoning), MCP-04 (Schema Drift / Rug Pull), MCP-05 (Missing Input Validation), MCP-06 (Plaintext Transport), MCP-07 (Insecure Plugin Design), MCP-08 (Excessive Agency), MCP-09 (Overreliance on LLM), and MCP-10 (Insufficient Logging).",
        },
      },
      {
        "@type": "Question",
        name: "How does tool poisoning detection work?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "Tool poisoning attacks embed malicious instructions inside MCP tool descriptions. LangSight detects three patterns: prompt injection phrases hidden in tool descriptions, zero-width and invisible Unicode characters that hide commands, and base64-encoded payloads embedded in descriptions. The scanner flags all known patterns automatically during security scans.",
        },
      },
    ],
  },
];

export default function SecurityLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(securityJsonLd) }}
      />
      {children}
    </>
  );
}
