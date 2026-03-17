import type { Metadata } from "next";
import { Plus_Jakarta_Sans, Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";

const jakarta = Plus_Jakarta_Sans({
  subsets: ["latin"],
  variable: "--font-display",
  display: "swap",
});

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

const jetbrains = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains",
  display: "swap",
});

export const metadata: Metadata = {
  title: "LangSight — Agent Observability Platform",
  description:
    "Complete observability for everything an AI agent calls. Traces, costs, health checks, and security scanning for MCP servers, HTTP APIs, and multi-agent workflows.",
  openGraph: {
    title: "LangSight — Agent Observability Platform",
    description:
      "Traces, costs, health checks, and security scanning for AI agent tool calls.",
    url: "https://langsight.io",
    siteName: "LangSight",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "LangSight — Agent Observability Platform",
    description: "Complete observability for everything an AI agent calls.",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${jakarta.variable} ${inter.variable} ${jetbrains.variable}`}>
      <body>{children}</body>
    </html>
  );
}
