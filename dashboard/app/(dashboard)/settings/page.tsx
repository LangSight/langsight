"use client";

export const dynamic = "force-dynamic";

import { useState, useRef } from "react";
import useSWR from "swr";
import {
  Key, Plus, Trash2, Copy, Check, ExternalLink, Shield, Database,
  Info, AlertTriangle, Eye, EyeOff,
} from "lucide-react";
import { fetcher, getApiKeys, createApiKey, revokeApiKey } from "@/lib/api";
import { cn, timeAgo } from "@/lib/utils";
import { toast } from "sonner";
import type { ApiKeyResponse, ApiKeyCreatedResponse, ApiStatus } from "@/lib/types";

function Skeleton({ className }: { className?: string }) {
  return <div className={cn("skeleton", className)} />;
}

// ─── Create Key Dialog ─────────────────────────────────────────────────────────

function CreateKeyDialog({ onClose, onCreated }: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(false);
  const [created, setCreated] = useState<ApiKeyCreatedResponse | null>(null);
  const [copied, setCopied] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  async function handleCreate() {
    const trimmed = name.trim();
    if (!trimmed) {
      toast.error("Key name is required");
      inputRef.current?.focus();
      return;
    }
    setLoading(true);
    try {
      const result = await createApiKey(trimmed);
      setCreated(result);
      onCreated();
    } catch (err) {
      toast.error(`Failed to create API key: ${err instanceof Error ? err.message : "unknown error"}`);
    } finally {
      setLoading(false);
    }
  }

  async function handleCopy() {
    if (!created) return;
    await navigator.clipboard.writeText(created.key);
    setCopied(true);
    toast.success("API key copied to clipboard");
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="fixed inset-0 bg-black/60 backdrop-blur-sm" onClick={created ? onClose : undefined} />
      <div
        className="relative z-10 w-full max-w-md rounded-xl border shadow-2xl"
        style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
      >
        {/* Header */}
        <div className="flex items-center gap-3 px-6 py-4 border-b" style={{ borderColor: "hsl(var(--border))" }}>
          <div className="p-2 rounded-lg" style={{ background: "hsl(var(--primary))" }}>
            <Key size={14} className="text-white" />
          </div>
          <div>
            <h2 className="text-sm font-semibold" style={{ color: "hsl(var(--foreground))" }}>
              {created ? "API Key Created" : "Create API Key"}
            </h2>
            <p className="text-xs" style={{ color: "hsl(var(--muted-foreground))" }}>
              {created ? "Store this key securely — it will not be shown again" : "Name your key for identification"}
            </p>
          </div>
        </div>

        {/* Body */}
        <div className="px-6 py-5 space-y-4">
          {!created ? (
            <>
              <div>
                <label className="block text-xs font-medium mb-1.5" style={{ color: "hsl(var(--foreground))" }}>
                  Key name <span className="text-red-500">*</span>
                </label>
                <input
                  ref={inputRef}
                  type="text"
                  value={name}
                  onChange={e => setName(e.target.value)}
                  onKeyDown={e => e.key === "Enter" && handleCreate()}
                  placeholder="e.g. production-agent, ci-runner"
                  autoFocus
                  className="w-full px-3 py-2 rounded-lg border text-sm outline-none focus:ring-2 transition-all"
                  style={{
                    background: "hsl(var(--background))",
                    borderColor: "hsl(var(--border))",
                    color: "hsl(var(--foreground))",
                  }}
                />
              </div>
            </>
          ) : (
            <>
              {/* Warning banner */}
              <div className="flex items-start gap-3 p-3 rounded-lg border border-amber-500/30 bg-amber-500/10">
                <AlertTriangle size={14} className="text-amber-500 mt-0.5 flex-shrink-0" />
                <p className="text-xs text-amber-600 dark:text-amber-400 leading-relaxed">
                  <strong>Copy this key now.</strong> For security reasons, it will not be shown again.
                  Store it in a secrets manager or environment variable.
                </p>
              </div>

              {/* Key display */}
              <div>
                <label className="block text-xs font-medium mb-1.5" style={{ color: "hsl(var(--muted-foreground))" }}>
                  Your new API key
                </label>
                <div
                  className="flex items-center gap-2 p-3 rounded-lg border font-mono text-xs break-all"
                  style={{ background: "hsl(var(--muted))", borderColor: "hsl(var(--border))", color: "hsl(var(--foreground))" }}
                >
                  <span className="flex-1 select-all">{created.key}</span>
                  <button
                    onClick={handleCopy}
                    className="flex-shrink-0 p-1.5 rounded-md transition-colors hover:bg-accent"
                    style={{ color: "hsl(var(--muted-foreground))" }}
                    title="Copy to clipboard"
                  >
                    {copied ? <Check size={13} className="text-emerald-500" /> : <Copy size={13} />}
                  </button>
                </div>
              </div>

              <div className="flex items-center justify-between text-xs" style={{ color: "hsl(var(--muted-foreground))" }}>
                <span>Prefix: <code className="font-mono">{created.key_prefix}</code></span>
                <span>Created: {new Date(created.created_at).toLocaleString()}</span>
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t" style={{ borderColor: "hsl(var(--border))" }}>
          {!created ? (
            <>
              <button
                onClick={onClose}
                className="px-4 py-2 rounded-lg text-sm transition-colors hover:bg-accent"
                style={{ color: "hsl(var(--muted-foreground))" }}
              >
                Cancel
              </button>
              <button
                onClick={handleCreate}
                disabled={loading || !name.trim()}
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
                style={{ background: "hsl(var(--primary))" }}
              >
                {loading ? (
                  <span className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                ) : (
                  <Plus size={14} />
                )}
                Create key
              </button>
            </>
          ) : (
            <button
              onClick={onClose}
              className="px-4 py-2 rounded-lg text-sm font-medium text-white transition-opacity hover:opacity-90"
              style={{ background: "hsl(var(--primary))" }}
            >
              Done
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Revoke Confirm Dialog ─────────────────────────────────────────────────────

function RevokeDialog({ apiKey, onClose, onRevoked }: {
  apiKey: ApiKeyResponse;
  onClose: () => void;
  onRevoked: () => void;
}) {
  const [loading, setLoading] = useState(false);

  async function handleRevoke() {
    setLoading(true);
    try {
      await revokeApiKey(apiKey.id);
      toast.success(`API key "${apiKey.name}" revoked`);
      onRevoked();
      onClose();
    } catch (err) {
      toast.error(`Failed to revoke key: ${err instanceof Error ? err.message : "unknown error"}`);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="fixed inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div
        className="relative z-10 w-full max-w-sm rounded-xl border shadow-2xl"
        style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
      >
        <div className="px-6 py-5 space-y-3">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-red-500/10">
              <Trash2 size={14} className="text-red-500" />
            </div>
            <h2 className="text-sm font-semibold" style={{ color: "hsl(var(--foreground))" }}>Revoke API Key</h2>
          </div>
          <p className="text-sm" style={{ color: "hsl(var(--muted-foreground))" }}>
            Are you sure you want to revoke <strong style={{ color: "hsl(var(--foreground))" }}>{apiKey.name}</strong>{" "}
            (<code className="font-mono text-xs">{apiKey.key_prefix}...</code>)?
            Any integrations using this key will immediately lose access.
          </p>
        </div>
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t" style={{ borderColor: "hsl(var(--border))" }}>
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg text-sm transition-colors hover:bg-accent"
            style={{ color: "hsl(var(--muted-foreground))" }}
          >
            Cancel
          </button>
          <button
            onClick={handleRevoke}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium text-white bg-red-500 transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            {loading ? (
              <span className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            ) : (
              <Trash2 size={13} />
            )}
            Revoke key
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Section wrapper ───────────────────────────────────────────────────────────

function Section({ title, description, icon: Icon, children }: {
  title: string;
  description?: string;
  icon: React.ElementType;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border" style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}>
      <div className="px-6 py-4 border-b" style={{ borderColor: "hsl(var(--border))" }}>
        <div className="flex items-center gap-2.5">
          <Icon size={15} style={{ color: "hsl(var(--primary))" }} />
          <h2 className="text-sm font-semibold" style={{ color: "hsl(var(--foreground))" }}>{title}</h2>
        </div>
        {description && (
          <p className="text-xs mt-0.5 ml-[23px]" style={{ color: "hsl(var(--muted-foreground))" }}>{description}</p>
        )}
      </div>
      <div className="px-6 py-5">{children}</div>
    </div>
  );
}

// ─── API Keys Table ────────────────────────────────────────────────────────────

function ApiKeysSection() {
  const { data: keys, isLoading, mutate } = useSWR<ApiKeyResponse[]>(
    "/api/auth/api-keys",
    fetcher,
    { refreshInterval: 30_000 },
  );
  const [showCreate, setShowCreate] = useState(false);
  const [revokeTarget, setRevokeTarget] = useState<ApiKeyResponse | null>(null);

  const activeKeys = keys?.filter(k => !k.revoked_at) ?? [];
  const revokedKeys = keys?.filter(k => k.revoked_at) ?? [];

  return (
    <Section
      title="API Keys"
      description="Manage authentication keys for the LangSight API and SDK"
      icon={Key}
    >
      {/* Create button */}
      <div className="flex items-center justify-between mb-4">
        <p className="text-xs" style={{ color: "hsl(var(--muted-foreground))" }}>
          {isLoading ? "Loading…" : `${activeKeys.length} active key${activeKeys.length !== 1 ? "s" : ""}`}
        </p>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-white transition-opacity hover:opacity-90"
          style={{ background: "hsl(var(--primary))" }}
        >
          <Plus size={12} /> Create API Key
        </button>
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-10 w-full rounded-lg" />
          ))}
        </div>
      ) : !keys || keys.length === 0 ? (
        <div className="py-10 text-center flex flex-col items-center gap-3">
          <svg width="44" height="44" viewBox="0 0 44 44" fill="none" className="opacity-20">
            <circle cx="18" cy="18" r="10" stroke="currentColor" strokeWidth="1.5"/>
            <path d="M25.5 25.5l10 10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
            <path d="M14 18h8M18 14v8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
          </svg>
          <div>
            <p className="text-sm font-medium" style={{ color: "hsl(var(--foreground))" }}>No API keys yet</p>
            <p className="text-xs mt-1" style={{ color: "hsl(var(--muted-foreground))" }}>Create a key to authenticate SDK and CLI requests</p>
          </div>
        </div>
      ) : (
        <div className="overflow-x-auto -mx-6">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b" style={{ borderColor: "hsl(var(--border))" }}>
                {["Name", "Prefix", "Created", "Last Used", "Status", ""].map(h => (
                  <th key={h} className="px-6 py-2.5 text-left font-medium" style={{ color: "hsl(var(--muted-foreground))" }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {[...activeKeys, ...revokedKeys].map(k => (
                <tr
                  key={k.id}
                  className="border-b transition-colors hover:bg-accent/30"
                  style={{ borderColor: "hsl(var(--border))", opacity: k.revoked_at ? 0.55 : 1 }}
                >
                  <td className="px-6 py-3 font-medium" style={{ color: "hsl(var(--foreground))" }}>{k.name}</td>
                  <td className="px-6 py-3">
                    <code className="font-mono text-xs px-1.5 py-0.5 rounded" style={{ background: "hsl(var(--muted))", color: "hsl(var(--foreground))" }}>
                      {k.key_prefix}…
                    </code>
                  </td>
                  <td className="px-6 py-3" style={{ color: "hsl(var(--muted-foreground))" }}>
                    {new Date(k.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-6 py-3" style={{ color: "hsl(var(--muted-foreground))" }}>
                    {k.last_used_at ? timeAgo(k.last_used_at) : <span className="italic">Never</span>}
                  </td>
                  <td className="px-6 py-3">
                    {k.revoked_at ? (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border border-red-500/30 bg-red-500/10 text-red-500">
                        Revoked
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border border-emerald-500/30 bg-emerald-500/10 text-emerald-500">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                        Active
                      </span>
                    )}
                  </td>
                  <td className="px-6 py-3">
                    {!k.revoked_at && (
                      <button
                        onClick={() => setRevokeTarget(k)}
                        className="flex items-center gap-1 px-2 py-1 rounded-md text-xs text-red-500 hover:bg-red-500/10 transition-colors"
                        title="Revoke key"
                      >
                        <Trash2 size={11} /> Revoke
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showCreate && (
        <CreateKeyDialog
          onClose={() => setShowCreate(false)}
          onCreated={() => mutate()}
        />
      )}
      {revokeTarget && (
        <RevokeDialog
          apiKey={revokeTarget}
          onClose={() => setRevokeTarget(null)}
          onRevoked={() => mutate()}
        />
      )}
    </Section>
  );
}

// ─── Instance Section ──────────────────────────────────────────────────────────

function InstanceSection() {
  const { data: status, isLoading } = useSWR<ApiStatus>("/api/status", fetcher, { refreshInterval: 60_000 });

  const rows: { label: string; value: React.ReactNode }[] = [
    {
      label: "API URL",
      value: (
        <a
          href={process.env.NEXT_PUBLIC_LANGSIGHT_API_URL ?? "http://localhost:8000"}
          target="_blank"
          rel="noreferrer"
          className="font-mono text-xs flex items-center gap-1 hover:underline"
          style={{ color: "hsl(var(--primary))" }}
        >
          {process.env.NEXT_PUBLIC_LANGSIGHT_API_URL ?? "http://localhost:8000"}
          <ExternalLink size={10} />
        </a>
      ),
    },
    {
      label: "Version",
      value: isLoading ? <Skeleton className="h-4 w-16" /> : (
        <code className="font-mono text-xs" style={{ color: "hsl(var(--foreground))" }}>
          {status?.version ?? "—"}
        </code>
      ),
    },
    {
      label: "Storage mode",
      value: isLoading ? <Skeleton className="h-4 w-20" /> : (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border"
          style={{ borderColor: "hsl(var(--border))", color: "hsl(var(--muted-foreground))" }}>
          <Database size={10} />
          {status?.storage_mode ?? "unknown"}
        </span>
      ),
    },
    {
      label: "Authentication",
      value: isLoading ? <Skeleton className="h-4 w-16" /> : (
        status?.auth_enabled === false ? (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border border-amber-500/30 bg-amber-500/10 text-amber-500">
            <EyeOff size={10} /> Disabled
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border border-emerald-500/30 bg-emerald-500/10 text-emerald-500">
            <Shield size={10} /> Enabled
          </span>
        )
      ),
    },
    {
      label: "Servers configured",
      value: isLoading ? <Skeleton className="h-4 w-8" /> : (
        <span className="text-xs font-mono" style={{ color: "hsl(var(--foreground))" }}>
          {status?.servers_configured ?? "—"}
        </span>
      ),
    },
  ];

  return (
    <Section title="Instance" description="Current LangSight backend configuration" icon={Database}>
      <dl className="space-y-3">
        {rows.map(({ label, value }) => (
          <div key={label} className="flex items-center justify-between py-2 border-b last:border-0" style={{ borderColor: "hsl(var(--border))" }}>
            <dt className="text-xs" style={{ color: "hsl(var(--muted-foreground))" }}>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
    </Section>
  );
}

// ─── About Section ─────────────────────────────────────────────────────────────

function AboutSection() {
  return (
    <Section title="About" description="LangSight open-source AI agent observability" icon={Info}>
      <div className="space-y-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center text-white flex-shrink-0"
            style={{ background: "hsl(var(--primary))" }}>
            <svg width="18" height="18" viewBox="0 0 14 14" fill="none">
              <path d="M2 7h10M7 2v10M4 4l6 6M10 4l-6 6" stroke="white" strokeWidth="1.5" strokeLinecap="round"/>
            </svg>
          </div>
          <div>
            <p className="text-sm font-semibold" style={{ color: "hsl(var(--foreground))" }}>LangSight</p>
            <p className="text-xs" style={{ color: "hsl(var(--muted-foreground))" }}>
              Open-source observability for AI agent actions
            </p>
          </div>
        </div>
        <p className="text-xs leading-relaxed" style={{ color: "hsl(var(--muted-foreground))" }}>
          Full traces of every tool call across single and multi-agent workflows, with deep MCP health monitoring and security scanning.
          Instrument once at the agent level and capture everything: MCP servers, HTTP APIs, Python functions, and sub-agents.
        </p>
        <div className="flex items-center gap-3">
          <a
            href="https://github.com/langsight/langsight"
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs transition-colors hover:bg-accent"
            style={{ borderColor: "hsl(var(--border))", color: "hsl(var(--muted-foreground))" }}
          >
            <svg viewBox="0 0 24 24" width="12" height="12" fill="currentColor">
              <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"/>
            </svg>
            GitHub
          </a>
          <a
            href="http://localhost:8000/docs"
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs transition-colors hover:bg-accent"
            style={{ borderColor: "hsl(var(--border))", color: "hsl(var(--muted-foreground))" }}
          >
            <ExternalLink size={11} /> API Docs
          </a>
        </div>
        <p className="text-xs" style={{ color: "hsl(var(--muted-foreground))" }}>
          Licensed under{" "}
          <a href="https://www.apache.org/licenses/LICENSE-2.0" target="_blank" rel="noreferrer"
            className="hover:underline" style={{ color: "hsl(var(--primary))" }}>
            Apache 2.0
          </a>
        </p>
      </div>
    </Section>
  );
}

// ─── Page ──────────────────────────────────────────────────────────────────────

export default function SettingsPage() {
  return (
    <div className="space-y-6 max-w-3xl">
      {/* Header */}
      <div>
        <h1 className="text-xl font-bold" style={{ color: "hsl(var(--foreground))" }}>Settings</h1>
        <p className="text-sm" style={{ color: "hsl(var(--muted-foreground))" }}>
          Manage API keys, instance configuration, and account preferences
        </p>
      </div>

      <ApiKeysSection />
      <InstanceSection />
      <AboutSection />
    </div>
  );
}
