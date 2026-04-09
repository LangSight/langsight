"use client";

import { useTheme, Nav, Footer } from "@/components/site-shell";
import HeroSection from "@/components/hero/hero-section";
import BenchmarkSection from "@/components/hero/benchmark-section";
import FeaturesShowcase from "@/components/hero/features-showcase";
import IntegrationsSection from "@/components/hero/integrations-section";
import QuickstartSection from "@/components/hero/quickstart-section";
import { SharedKeyframes } from "@/components/hero/animated-primitives";

export default function HeroTestPage() {
  const { dark, toggle } = useTheme();

  return (
    <>
      {/* Obsidian palette — overrides for BOTH themes */}
      <style jsx global>{`
        :root {
          --indigo: #4F46E5;
          --indigo-dim: rgba(79,70,229,0.08);
          --indigo-glow: rgba(79,70,229,0.12);
          --indigo-strong: rgba(79,70,229,0.20);
          --violet: #7C3AED;
          --terminal-bg: #F8F9FA;
          --terminal-bar: #F1F2F4;
          --code-text: #4F46E5;
        }
        .dark {
          --bg: #050507;
          --bg-deep: #030305;
          --surface: #0E0E12;
          --surface-2: #131317;
          --border: #1E1E24;
          --border-dim: #141418;
          --text: #E8E8ED;
          --muted: #9898A6;
          --dimmer: #5C5C6B;
          --indigo: #6366F1;
          --indigo-dim: rgba(99,102,241,0.10);
          --indigo-glow: rgba(99,102,241,0.18);
          --indigo-strong: rgba(99,102,241,0.25);
          --violet: #A78BFA;
          --green: #34D399;
          --red: #F87171;
          --yellow: #FBBF24;
          --orange: #FB923C;
          --terminal-bg: #08080B;
          --terminal-bar: #0E0E12;
          --code-text: #C4B5FD;
        }
        .gradient-text {
          background: linear-gradient(135deg, var(--text) 0%, var(--muted) 100%);
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
          background-clip: text;
        }
        .gradient-indigo {
          background: linear-gradient(135deg, #818CF8 0%, #6366F1 50%, #A78BFA 100%);
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
          background-clip: text;
        }
      `}</style>

      {/* Noise grain overlay — dark mode only */}
      <div
        className="fixed inset-0 pointer-events-none dark:opacity-[0.025] opacity-0 transition-opacity"
        aria-hidden="true"
        style={{
          zIndex: 90,
          mixBlendMode: "overlay",
          backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.65' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")`,
        }}
      />

      <Nav dark={dark} toggle={toggle} />
      <main style={{ background: "var(--bg)" }}>
        <SharedKeyframes />
        <HeroSection />
        <BenchmarkSection />
        <FeaturesShowcase />
        <IntegrationsSection />
        <QuickstartSection />
      </main>
      <Footer />
    </>
  );
}
