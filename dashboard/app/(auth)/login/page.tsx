"use client";

import { useState } from "react";
import { signIn } from "next-auth/react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Eye, EyeOff, Loader2 } from "lucide-react";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState(process.env.NODE_ENV !== "production" ? "admin@admin.com" : "");
  const [password, setPassword] = useState(process.env.NODE_ENV !== "production" ? "admin" : "");
  const [show, setShow] = useState(false);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    const res = await signIn("credentials", { email, password, redirect: false });
    setLoading(false);
    if (res?.error) {
      toast.error("Invalid email or password");
    } else {
      router.push("/");
      router.refresh();
    }
  }

  return (
    <div
      className="min-h-screen flex"
      style={{ background: "hsl(var(--background))" }}
    >
      {/* ── Left panel — branding ──────────────────────────────── */}
      <div
        className="hidden lg:flex lg:w-[44%] flex-col justify-between p-10 relative overflow-hidden"
        style={{ background: "hsl(240 10% 5%)" }}
      >
        {/* Glow */}
        <div
          className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[480px] h-[480px] rounded-full blur-[120px] pointer-events-none"
          style={{ background: "hsl(var(--primary) / 0.12)" }}
        />

        {/* Logo */}
        <div className="relative flex items-center gap-2.5">
          <div
            className="w-8 h-8 rounded-xl flex items-center justify-center shadow-lg"
            style={{ background: "hsl(var(--primary))" }}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="9" stroke="white" strokeWidth="2.5" fill="none"/>
              <circle cx="12" cy="12" r="2.5" fill="white"/>
              <line x1="18" y1="6" x2="23" y2="1" stroke="white" strokeWidth="2.5" strokeLinecap="round"/>
            </svg>
          </div>
          <span className="font-bold text-[15px] text-white">LangSight</span>
          <span
            className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full ml-1"
            style={{ background: "hsl(var(--primary) / 0.2)", color: "hsl(var(--primary))" }}
          >
            v0.2
          </span>
        </div>

        {/* Center copy */}
        <div className="relative space-y-8">
          <div>
            <h2
              className="font-bold leading-tight mb-4"
              style={{ fontSize: "clamp(1.6rem, 3vw, 2.4rem)", color: "white" }}
            >
              Full visibility into<br />
              everything your<br />
              <span style={{ color: "hsl(var(--primary))" }}>agents call.</span>
            </h2>
            <p className="text-sm leading-relaxed" style={{ color: "hsl(0 0% 60%)" }}>
              Traces, costs, MCP health checks, and security scanning — instrument once,
              see everything.
            </p>
          </div>

          {/* Feature list */}
          <div className="space-y-3">
            {[
              { icon: "🔭", text: "Full session traces across multi-agent trees" },
              { icon: "💰", text: "Per-tool, per-agent cost attribution" },
              { icon: "♥", text: "Proactive MCP health monitoring" },
              { icon: "🛡", text: "CVE + OWASP security scanning" },
            ].map((f, i) => (
              <div key={i} className="flex items-center gap-3 text-sm" style={{ color: "hsl(0 0% 70%)" }}>
                <span className="text-base">{f.icon}</span>
                <span>{f.text}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Bottom */}
        <div className="relative">
          <p className="text-xs" style={{ color: "hsl(0 0% 35%)" }}>
            Apache 2.0 · Self-hosted · Your data stays yours
          </p>
        </div>
      </div>

      {/* ── Right panel — form ─────────────────────────────────── */}
      <div className="flex-1 flex items-center justify-center p-6">
        {/* Mobile logo */}
        <div className="absolute top-6 left-6 flex items-center gap-2 lg:hidden">
          <div
            className="w-7 h-7 rounded-lg flex items-center justify-center"
            style={{ background: "hsl(var(--primary))" }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="9" stroke="white" strokeWidth="2.5" fill="none"/>
              <circle cx="12" cy="12" r="2.5" fill="white"/>
              <line x1="18" y1="6" x2="23" y2="1" stroke="white" strokeWidth="2.5" strokeLinecap="round"/>
            </svg>
          </div>
          <span className="font-bold text-[14px] text-foreground">LangSight</span>
        </div>

        <div className="w-full max-w-[380px]">
          {/* Heading */}
          <div className="mb-8">
            <h1 className="text-2xl font-bold text-foreground mb-1.5">Sign in</h1>
            <p className="text-sm text-muted-foreground">
              Enter your credentials to access the dashboard
            </p>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Email */}
            <div>
              <label
                htmlFor="email"
                className="block text-[13px] font-medium text-foreground mb-1.5"
              >
                Email
              </label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="input-base"
                placeholder="admin@admin.com"
                autoComplete="email"
              />
            </div>

            {/* Password */}
            <div>
              <label
                htmlFor="password"
                className="block text-[13px] font-medium text-foreground mb-1.5"
              >
                Password
              </label>
              <div className="relative">
                <input
                  id="password"
                  type={show ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  className="input-base pr-10"
                  placeholder="••••••••"
                  autoComplete="current-password"
                />
                <button
                  type="button"
                  onClick={() => setShow((s) => !s)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                  aria-label={show ? "Hide password" : "Show password"}
                >
                  {show ? <EyeOff size={15} /> : <Eye size={15} />}
                </button>
              </div>
            </div>

            {/* Submit */}
            <button
              type="submit"
              disabled={loading}
              className="btn btn-primary w-full justify-center py-2.5 text-[14px]"
            >
              {loading && <Loader2 size={15} className="animate-spin" />}
              {loading ? "Signing in…" : "Sign in"}
            </button>
          </form>

          {/* Demo hint — only shown in development; hidden in production builds */}
          {process.env.NODE_ENV !== "production" && (
            <div
              className="mt-6 p-3.5 rounded-xl text-[12px] leading-relaxed"
              style={{
                background: "hsl(var(--primary) / 0.06)",
                border: "1px solid hsl(var(--primary) / 0.15)",
              }}
            >
              <p className="font-semibold mb-0.5" style={{ color: "hsl(var(--primary))" }}>
                Demo credentials
              </p>
              <p className="text-muted-foreground font-mono">
                admin@admin.com / admin
              </p>
            </div>
          )}

          {/* Footer */}
          <div className="mt-8 pt-6 flex items-center justify-center gap-4" style={{ borderTop: "1px solid hsl(var(--border) / 0.5)" }}>
            {[
              { label: "Docs", href: "https://docs.langsight.dev" },
              { label: "GitHub", href: "https://github.com/langsight/langsight" },
              { label: "Apache 2.0", href: "https://www.apache.org/licenses/LICENSE-2.0" },
            ].map(({ label, href }) => (
              <a
                key={label}
                href={href}
                target="_blank"
                rel="noreferrer"
                className="text-[11px] text-muted-foreground hover:text-foreground transition-colors"
              >
                {label}
              </a>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
