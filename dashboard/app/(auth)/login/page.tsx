"use client";

import { useState } from "react";
import { signIn } from "next-auth/react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Eye, EyeOff, Loader2 } from "lucide-react";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("admin@langsight.io");
  const [password, setPassword] = useState("demo");
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
    <div className="min-h-screen flex items-center justify-center p-4" style={{ background: "hsl(var(--background))" }}>
      {/* Background gradient */}
      <div className="absolute inset-0 pointer-events-none overflow-hidden">
        <div className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[400px] rounded-full opacity-20 blur-[100px]"
          style={{ background: "hsl(var(--primary))" }} />
      </div>

      <div className="relative w-full max-w-md">
        {/* Card */}
        <div className="rounded-2xl border p-8 shadow-2xl" style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}>
          {/* Logo */}
          <div className="flex items-center gap-3 mb-8">
            <div className="w-10 h-10 rounded-xl flex items-center justify-center shadow-lg" style={{ background: "hsl(var(--primary))" }}>
              <svg width="20" height="20" viewBox="0 0 14 14" fill="none">
                <path d="M2 7h10M7 2v10M4 4l6 6M10 4l-6 6" stroke="white" strokeWidth="1.5" strokeLinecap="round"/>
              </svg>
            </div>
            <div>
              <h1 className="text-lg font-bold" style={{ color: "hsl(var(--foreground))" }}>LangSight</h1>
              <p className="text-xs" style={{ color: "hsl(var(--muted-foreground))" }}>Observability Platform</p>
            </div>
          </div>

          <div className="mb-6">
            <h2 className="text-2xl font-bold mb-1" style={{ color: "hsl(var(--foreground))" }}>Sign in</h2>
            <p className="text-sm" style={{ color: "hsl(var(--muted-foreground))" }}>Monitor your AI agents and MCP servers</p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="text-sm font-medium block mb-1.5" style={{ color: "hsl(var(--foreground))" }}>Email</label>
              <input
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                required
                className="w-full px-3 py-2.5 rounded-lg text-sm outline-none transition-colors"
                style={{ background: "hsl(var(--muted))", border: "1px solid hsl(var(--border))", color: "hsl(var(--foreground))" }}
                placeholder="admin@langsight.io"
              />
            </div>
            <div>
              <label className="text-sm font-medium block mb-1.5" style={{ color: "hsl(var(--foreground))" }}>Password</label>
              <div className="relative">
                <input
                  type={show ? "text" : "password"}
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  required
                  className="w-full px-3 py-2.5 pr-10 rounded-lg text-sm outline-none transition-colors"
                  style={{ background: "hsl(var(--muted))", border: "1px solid hsl(var(--border))", color: "hsl(var(--foreground))" }}
                  placeholder="••••••••"
                />
                <button type="button" onClick={() => setShow(s => !s)}
                  className="absolute right-3 top-1/2 -translate-y-1/2"
                  style={{ color: "hsl(var(--muted-foreground))" }}>
                  {show ? <EyeOff size={16}/> : <Eye size={16}/>}
                </button>
              </div>
            </div>
            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 rounded-lg text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-60 flex items-center justify-center gap-2"
              style={{ background: "hsl(var(--primary))" }}>
              {loading && <Loader2 size={16} className="animate-spin"/>}
              Sign in
            </button>
          </form>

          {/* Demo hint */}
          <div className="mt-5 p-3 rounded-lg text-xs" style={{ background: "hsl(var(--muted))", color: "hsl(var(--muted-foreground))" }}>
            <strong>Demo:</strong> admin@langsight.io / any password
          </div>
        </div>
      </div>
    </div>
  );
}
