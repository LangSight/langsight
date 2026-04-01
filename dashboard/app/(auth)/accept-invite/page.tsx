"use client";

import { useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Eye, EyeOff, Loader2, CheckCircle2, AlertCircle } from "lucide-react";
import Link from "next/link";

/* ── Left branding panel (shared shape with login) ───────────── */
function BrandPanel() {
  return (
    <div
      className="hidden lg:flex lg:w-[44%] flex-col justify-between p-10 relative overflow-hidden"
      style={{ background: "hsl(240 10% 5%)" }}
    >
      <div
        className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[480px] h-[480px] rounded-full blur-[120px] pointer-events-none"
        style={{ background: "hsl(var(--primary) / 0.12)" }}
      />

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
          v0.6.2
        </span>
      </div>

      <div className="relative space-y-4">
        <h2
          className="font-bold leading-tight"
          style={{ fontSize: "clamp(1.6rem, 3vw, 2.4rem)", color: "white" }}
        >
          You&apos;ve been<br />
          invited to{" "}
          <span style={{ color: "hsl(var(--primary))" }}>LangSight.</span>
        </h2>
        <p className="text-sm leading-relaxed" style={{ color: "hsl(0 0% 60%)" }}>
          Set your password to complete registration and start monitoring your AI agents.
        </p>
      </div>

      <div className="relative">
        <p className="text-xs" style={{ color: "hsl(0 0% 35%)" }}>
          Apache 2.0 · Self-hosted · Your data stays yours
        </p>
      </div>
    </div>
  );
}

/* ── Invalid / missing token state ───────────────────────────── */
function InvalidInvite({ message }: { message: string }) {
  return (
    <div
      className="min-h-screen flex items-center justify-center"
      style={{ background: "hsl(var(--background))" }}
    >
      <div className="text-center space-y-4 max-w-sm px-6">
        <div
          className="mx-auto w-12 h-12 rounded-full flex items-center justify-center"
          style={{ background: "hsl(var(--danger) / 0.1)" }}
        >
          <AlertCircle size={24} style={{ color: "hsl(var(--danger))" }} />
        </div>
        <h1 className="text-xl font-bold text-foreground">Invalid invite link</h1>
        <p className="text-sm text-muted-foreground">{message}</p>
        <Link
          href="/login"
          className="inline-block text-sm underline underline-offset-2 transition-colors hover:text-foreground text-muted-foreground"
        >
          Go to sign in →
        </Link>
      </div>
    </div>
  );
}

/* ── Success state ────────────────────────────────────────────── */
function SuccessState() {
  return (
    <div className="text-center space-y-4">
      <div
        className="mx-auto w-12 h-12 rounded-full flex items-center justify-center"
        style={{ background: "hsl(142 71% 45% / 0.15)" }}
      >
        <CheckCircle2 size={24} style={{ color: "hsl(142 71% 45%)" }} />
      </div>
      <h1 className="text-2xl font-bold text-foreground">Account created!</h1>
      <p className="text-sm text-muted-foreground">Redirecting you to sign in…</p>
      <Link
        href="/login"
        className="inline-block text-sm underline underline-offset-2 transition-colors hover:text-foreground text-muted-foreground"
      >
        Go to sign in →
      </Link>
    </div>
  );
}

/* ── Form ─────────────────────────────────────────────────────── */
function AcceptInviteForm({ token }: { token: string }) {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPass, setShowPass] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    if (password.length < 12) {
      setError("Password must be at least 12 characters.");
      return;
    }

    setLoading(true);
    try {
      const res = await fetch("/api/accept-invite", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, password }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.detail ?? "Something went wrong. Please try again.");
      } else {
        setDone(true);
        setTimeout(() => router.push("/login"), 2500);
      }
    } catch {
      setError("Could not reach the server. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  if (done) return <SuccessState />;

  return (
    <>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-foreground mb-1.5">Create your account</h1>
        <p className="text-sm text-muted-foreground">
          Choose a password to complete your registration.
        </p>
      </div>

      {error && (
        <div
          className="mb-4 flex items-start gap-2.5 p-3.5 rounded-xl text-[13px]"
          style={{
            background: "hsl(var(--danger) / 0.08)",
            border: "1px solid hsl(var(--danger) / 0.2)",
            color: "hsl(var(--danger))",
          }}
        >
          <AlertCircle size={15} className="flex-shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label htmlFor="password" className="block text-[13px] font-medium text-foreground mb-1.5">
            Password
          </label>
          <div className="relative">
            <input
              id="password"
              type={showPass ? "text" : "password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={12}
              className="input-base pr-10"
              placeholder="Min. 12 characters"
              autoComplete="new-password"
            />
            <button
              type="button"
              onClick={() => setShowPass((s) => !s)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
              aria-label={showPass ? "Hide password" : "Show password"}
            >
              {showPass ? <EyeOff size={15} /> : <Eye size={15} />}
            </button>
          </div>
        </div>

        <div>
          <label htmlFor="confirm" className="block text-[13px] font-medium text-foreground mb-1.5">
            Confirm password
          </label>
          <div className="relative">
            <input
              id="confirm"
              type={showConfirm ? "text" : "password"}
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              required
              className="input-base pr-10"
              placeholder="Repeat your password"
              autoComplete="new-password"
            />
            <button
              type="button"
              onClick={() => setShowConfirm((s) => !s)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
              aria-label={showConfirm ? "Hide password" : "Show password"}
            >
              {showConfirm ? <EyeOff size={15} /> : <Eye size={15} />}
            </button>
          </div>
        </div>

        <button
          type="submit"
          disabled={loading}
          className="btn btn-primary w-full justify-center py-2.5 text-[14px]"
        >
          {loading && <Loader2 size={15} className="animate-spin" />}
          {loading ? "Creating account…" : "Create account"}
        </button>
      </form>

      <p className="mt-6 text-center text-xs text-muted-foreground">
        Already have an account?{" "}
        <Link
          href="/login"
          className="underline underline-offset-2 transition-colors hover:text-foreground"
        >
          Sign in →
        </Link>
      </p>
    </>
  );
}

/* ── Inner page — reads searchParams ─────────────────────────── */
function AcceptInviteInner() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token");

  if (!token) {
    return <InvalidInvite message="This invite link is missing a token. Ask your admin to resend the invite." />;
  }

  return (
    <div className="min-h-screen flex" style={{ background: "hsl(var(--background))" }}>
      <BrandPanel />

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
          <AcceptInviteForm token={token} />
        </div>
      </div>
    </div>
  );
}

/* ── Page export — Suspense required for useSearchParams ─────── */
export default function AcceptInvitePage() {
  return (
    <Suspense fallback={null}>
      <AcceptInviteInner />
    </Suspense>
  );
}
