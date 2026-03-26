"use client";

/**
 * Shared site shell: useTheme, useScrollReveal, Logo, Nav, Footer.
 * Extracted from individual pages to eliminate duplication.
 * Import in every page: import { useTheme, useScrollReveal, Nav, Footer } from "@/components/site-shell";
 */

import { useEffect, useState } from "react";

/* ── Theme ──────────────────────────────────────────────────── */
export function useTheme() {
  const [dark, setDark] = useState(true);
  useEffect(() => {
    const saved = localStorage.getItem("ls-theme");
    setDark(saved ? saved === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches);
  }, []);
  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    localStorage.setItem("ls-theme", dark ? "dark" : "light");
  }, [dark]);
  return { dark, toggle: () => setDark((d) => !d) };
}

/* ── Scroll reveal ──────────────────────────────────────────── */
export function useScrollReveal() {
  useEffect(() => {
    const obs = new IntersectionObserver(
      (entries) => entries.forEach((e) => e.isIntersecting && e.target.classList.add("visible")),
      { threshold: 0.07 }
    );
    document.querySelectorAll("[data-reveal]").forEach((el) => obs.observe(el));
    return () => obs.disconnect();
  }, []);
}

/* ── Icons ──────────────────────────────────────────────────── */
function SunIcon() {
  return (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
      <circle cx="12" cy="12" r="5" />
      <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
      <path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z" />
    </svg>
  );
}

/* ── Logo ───────────────────────────────────────────────────── */
export function Logo() {
  return (
    <a href="/" className="flex items-center gap-2.5 shrink-0">
      <div className="w-9 h-9 rounded-xl flex items-center justify-center shrink-0" style={{ background: "var(--indigo)" }}>
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
          <circle cx="12" cy="12" r="9" stroke="white" strokeWidth="2.5" fill="none"/>
          <circle cx="12" cy="12" r="2.5" fill="white"/>
          <line x1="18" y1="6" x2="23" y2="1" stroke="white" strokeWidth="2.5" strokeLinecap="round"/>
        </svg>
      </div>
      <span className="font-bold text-lg tracking-tight" style={{ fontFamily: "var(--font-geist-sans)", color: "var(--text)" }}>
        Lang<span style={{ color: "var(--indigo)" }}>Sight</span>
      </span>
    </a>
  );
}

/* ── Nav ────────────────────────────────────────────────────── */
export function Nav({ dark, toggle }: { dark: boolean; toggle: () => void }) {
  const [scrolled, setScrolled] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    const handler = () => setScrolled(window.scrollY > 24);
    window.addEventListener("scroll", handler);
    return () => window.removeEventListener("scroll", handler);
  }, []);

  const navLinks = [
    { label: "Blog", href: "/blog" },
    { label: "Security", href: "/security" },
    { label: "Pricing", href: "/pricing" },
    { label: "Docs", href: "https://docs.langsight.dev" },
    { label: "GitHub", href: "https://github.com/LangSight/langsight" },
  ];

  return (
    <nav
      className="fixed top-0 left-0 right-0 z-50 transition-all duration-300"
      style={{
        background: scrolled ? "color-mix(in srgb, var(--bg) 88%, transparent)" : "transparent",
        backdropFilter: scrolled ? "blur(16px) saturate(180%)" : "none",
        WebkitBackdropFilter: scrolled ? "blur(16px) saturate(180%)" : "none",
        borderBottom: scrolled ? "1px solid var(--border)" : "1px solid transparent",
      }}
    >
      <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between gap-6">
        <Logo />
        <div className="hidden md:flex items-center gap-1">
          {navLinks.map((l) => (
            <a
              key={l.label}
              href={l.href}
              className="px-3 py-1.5 rounded-md text-sm transition-colors"
              style={{ color: "var(--muted)" }}
              onMouseEnter={(e) => (e.currentTarget.style.color = "var(--text)")}
              onMouseLeave={(e) => (e.currentTarget.style.color = "var(--muted)")}
            >
              {l.label}
            </a>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={toggle}
            aria-label="Toggle theme"
            className="w-9 h-9 rounded-lg flex items-center justify-center transition-all hover:scale-110"
            style={{ background: "var(--surface-2)", border: "1px solid var(--border)", color: "var(--muted)" }}
          >
            {dark ? <SunIcon /> : <MoonIcon />}
          </button>
          <a
            href="https://docs.langsight.dev/quickstart"
            className="hidden sm:flex items-center gap-1.5 text-sm font-semibold px-4 py-2 rounded-lg transition-all hover:opacity-90 hover:-translate-y-px"
            style={{ background: "var(--indigo)", color: "white" }}
          >
            Start self-hosting →
          </a>
          <button
            className="md:hidden w-9 h-9 flex flex-col items-center justify-center gap-1.5"
            onClick={() => setMobileOpen((o) => !o)}
            aria-label="Menu"
          >
            <span className="block w-5 h-px transition-all" style={{ background: "var(--muted)" }} />
            <span className="block w-5 h-px transition-all" style={{ background: "var(--muted)" }} />
            <span className="block w-3 h-px transition-all" style={{ background: "var(--muted)" }} />
          </button>
        </div>
      </div>
      {mobileOpen && (
        <div className="md:hidden px-6 pb-4 space-y-1" style={{ background: "var(--bg)", borderTop: "1px solid var(--border)" }}>
          {navLinks.map((l) => (
            <a
              key={l.label}
              href={l.href}
              className="block px-3 py-2.5 rounded-lg text-sm"
              style={{ color: "var(--muted)" }}
              onClick={() => setMobileOpen(false)}
            >
              {l.label}
            </a>
          ))}
          <a
            href="https://docs.langsight.dev/quickstart"
            className="block mt-2 px-3 py-2.5 rounded-lg text-sm font-semibold text-center"
            style={{ background: "var(--indigo)", color: "white" }}
          >
            Start self-hosting →
          </a>
        </div>
      )}
    </nav>
  );
}

/* ── Footer ─────────────────────────────────────────────────── */
export function Footer() {
  const links = [
    { label: "Docs", href: "https://docs.langsight.dev" },
    { label: "GitHub", href: "https://github.com/LangSight/langsight" },
    { label: "PyPI", href: "https://pypi.org/project/langsight/" },
    { label: "Changelog", href: "https://github.com/LangSight/langsight/blob/main/CHANGELOG.md" },
    { label: "Security", href: "/security" },
    { label: "Pricing", href: "/pricing" },
    { label: "Blog", href: "/blog" },
  ];

  return (
    <footer className="py-10" style={{ borderTop: "1px solid var(--border)" }}>
      <div className="max-w-6xl mx-auto px-6 flex flex-col sm:flex-row items-center justify-between gap-4">
        <Logo />
        <div className="flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-sm">
          {links.map((l) => (
            <a
              key={l.label}
              href={l.href}
              className="transition-colors"
              style={{ color: "var(--muted)" }}
              onMouseEnter={(e) => (e.currentTarget.style.color = "var(--text)")}
              onMouseLeave={(e) => (e.currentTarget.style.color = "var(--muted)")}
            >
              {l.label}
            </a>
          ))}
        </div>
        <p className="text-xs" style={{ color: "var(--dimmer)" }}>
          Apache 2.0 · v0.6.2
        </p>
      </div>
    </footer>
  );
}
