"use client";

export const dynamic = "force-dynamic";

import { useState, useRef } from "react";
import useSWR from "swr";
import {
  Key, Plus, Trash2, Copy, Check, ExternalLink, Shield, Database,
  Info, AlertTriangle, Eye, EyeOff, Users, UserPlus, UserX, ShieldCheck,
  DollarSign, Pencil, X, Folder, ChevronDown, ChevronRight,
} from "lucide-react";
import { fetcher, getApiKeys, createApiKey, revokeApiKey, listUsers, inviteUser, deactivateUser, updateUserRole, listModelPricing, createModelPricing, updateModelPricing, deactivateModelPricing, listProjects, createProject, deleteProject, listProjectMembers, addProjectMember, removeProjectMember } from "@/lib/api";
import type { ApiKeyResponse, ApiKeyCreatedResponse, ApiStatus, DashboardUser, InviteResponse, ModelPricingEntry, ProjectResponse, ProjectMember } from "@/lib/types";
import { cn, timeAgo } from "@/lib/utils";
import { toast } from "sonner";

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
    <div
      className="rounded-xl border overflow-hidden"
      style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
    >
      <div
        className="flex items-start gap-3 px-5 py-4 border-b"
        style={{ borderColor: "hsl(var(--border))", background: "hsl(var(--card-raised))" }}
      >
        <div
          className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5"
          style={{ background: "hsl(var(--primary) / 0.1)" }}
        >
          <Icon size={14} style={{ color: "hsl(var(--primary))" }} />
        </div>
        <div>
          <h2 className="text-[13px] font-semibold text-foreground">{title}</h2>
          {description && (
            <p className="text-[11px] text-muted-foreground mt-0.5">{description}</p>
          )}
        </div>
      </div>
      <div className="px-5 py-5">{children}</div>
    </div>
  );
}

// ─── Projects Section ──────────────────────────────────────────────────────────

function ProjectRow({ project, onDeleted }: { project: ProjectResponse; onDeleted: () => void }) {
  const [expanded, setExpanded] = useState(false);
  const [members, setMembers] = useState<ProjectMember[] | null>(null);
  const [users, setUsers] = useState<DashboardUser[]>([]);
  const [loadingMembers, setLoadingMembers] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [addingUser, setAddingUser] = useState(false);
  const [selectedUserId, setSelectedUserId] = useState("");
  const [selectedRole, setSelectedRole] = useState<"member" | "viewer" | "owner">("member");

  async function loadMembers() {
    if (members !== null) return;
    setLoadingMembers(true);
    try {
      const [m, u] = await Promise.all([listProjectMembers(project.id), listUsers()]);
      setMembers(m);
      setUsers(u);
    } catch {
      toast.error("Failed to load members");
    } finally {
      setLoadingMembers(false);
    }
  }

  async function handleExpand() {
    const next = !expanded;
    setExpanded(next);
    if (next) await loadMembers();
  }

  async function handleDelete() {
    setDeleting(true);
    try {
      await deleteProject(project.id);
      toast.success(`Project "${project.name}" deleted`);
      onDeleted();
    } catch (err) {
      toast.error(`Failed to delete: ${err instanceof Error ? err.message : "unknown"}`);
    } finally {
      setDeleting(false);
      setConfirmDelete(false);
    }
  }

  async function handleAddMember() {
    if (!selectedUserId) return;
    setAddingUser(true);
    try {
      const m = await addProjectMember(project.id, selectedUserId, selectedRole);
      setMembers((prev) => [...(prev ?? []), m]);
      setSelectedUserId("");
      toast.success("Member added");
    } catch (err) {
      toast.error(`Failed to add member: ${err instanceof Error ? err.message : "unknown"}`);
    } finally {
      setAddingUser(false);
    }
  }

  async function handleRemoveMember(userId: string) {
    try {
      await removeProjectMember(project.id, userId);
      setMembers((prev) => (prev ?? []).filter((m) => m.user_id !== userId));
      toast.success("Member removed");
    } catch {
      toast.error("Failed to remove member");
    }
  }

  const nonMembers = users.filter((u) => !(members ?? []).find((m) => m.user_id === u.id));

  return (
    <div
      className="rounded-xl border overflow-hidden"
      style={{ borderColor: "hsl(var(--border))", background: "hsl(var(--card-raised))" }}
    >
      {/* Row header */}
      <div className="flex items-center gap-3 px-4 py-3">
        <button
          onClick={handleExpand}
          className="flex items-center gap-2 flex-1 min-w-0 text-left"
        >
          {expanded
            ? <ChevronDown size={13} className="text-muted-foreground flex-shrink-0" />
            : <ChevronRight size={13} className="text-muted-foreground flex-shrink-0" />}
          <Folder size={14} className="text-primary flex-shrink-0" />
          <span className="text-[13px] font-medium text-foreground truncate">{project.name}</span>
          <code
            className="text-[10px] text-muted-foreground ml-1 hidden sm:inline"
            style={{ fontFamily: "var(--font-geist-mono)" }}
          >
            /{project.slug}
          </code>
        </button>

        <span className="text-[11px] text-muted-foreground tabular-nums flex-shrink-0">
          {project.member_count} {project.member_count === 1 ? "member" : "members"}
        </span>

        {!confirmDelete ? (
          <button
            onClick={() => setConfirmDelete(true)}
            className="btn btn-ghost p-1.5 text-muted-foreground hover:text-red-500 flex-shrink-0"
            title={`Delete ${project.name}`}
          >
            <Trash2 size={13} />
          </button>
        ) : (
          <div className="flex items-center gap-1.5 flex-shrink-0">
            <span className="text-[11px] text-red-500">Delete?</span>
            <button
              onClick={handleDelete}
              disabled={deleting}
              className="text-[11px] font-semibold px-2 py-0.5 rounded badge-danger transition-colors"
            >
              {deleting ? "…" : "Yes"}
            </button>
            <button
              onClick={() => setConfirmDelete(false)}
              className="text-[11px] px-2 py-0.5 rounded badge-muted transition-colors"
            >
              No
            </button>
          </div>
        )}
      </div>

      {/* Expanded: members */}
      {expanded && (
        <div
          className="border-t px-4 py-4 space-y-3"
          style={{ borderColor: "hsl(var(--border))" }}
        >
          {loadingMembers ? (
            <div className="space-y-2">
              {[1,2].map(i => <div key={i} className="skeleton h-8 rounded-lg" />)}
            </div>
          ) : (
            <>
              <p className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wide">
                Members
              </p>
              {(members ?? []).length === 0 ? (
                <p className="text-xs text-muted-foreground">No members yet</p>
              ) : (
                <div className="space-y-1.5">
                  {(members ?? []).map((m) => {
                    const user = users.find((u) => u.id === m.user_id);
                    return (
                      <div
                        key={m.user_id}
                        className="flex items-center justify-between px-3 py-2 rounded-lg"
                        style={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))" }}
                      >
                        <div>
                          <span className="text-[12.5px] text-foreground">
                            {user?.email ?? m.user_id.slice(0, 16) + "…"}
                          </span>
                          <span
                            className="text-[10px] ml-2 px-1.5 py-0.5 rounded-full capitalize badge-primary"
                          >
                            {m.role}
                          </span>
                        </div>
                        {m.role !== "owner" && (
                          <button
                            onClick={() => handleRemoveMember(m.user_id)}
                            className="btn btn-ghost p-1 text-muted-foreground hover:text-red-500"
                          >
                            <UserX size={12} />
                          </button>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Add member */}
              {nonMembers.length > 0 && (
                <div className="flex items-center gap-2 pt-1">
                  <select
                    value={selectedUserId}
                    onChange={(e) => setSelectedUserId(e.target.value)}
                    className="input-base text-[12px] h-8 flex-1"
                  >
                    <option value="">Add member…</option>
                    {nonMembers.map((u) => (
                      <option key={u.id} value={u.id}>{u.email}</option>
                    ))}
                  </select>
                  <select
                    value={selectedRole}
                    onChange={(e) => setSelectedRole(e.target.value as "member" | "viewer" | "owner")}
                    className="input-base text-[12px] h-8 w-24"
                  >
                    <option value="member">Member</option>
                    <option value="viewer">Viewer</option>
                    <option value="owner">Owner</option>
                  </select>
                  <button
                    onClick={handleAddMember}
                    disabled={addingUser || !selectedUserId}
                    className="btn btn-primary py-1 px-3 text-[12px]"
                  >
                    <UserPlus size={12} />
                    {addingUser ? "…" : "Add"}
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

function ProjectsSection() {
  const { data: projects, isLoading, mutate } = useSWR<ProjectResponse[]>(
    "/api/projects",
    fetcher,
    { refreshInterval: 30_000 }
  );
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleCreate() {
    const name = newName.trim();
    if (!name) return;
    setSubmitting(true);
    try {
      await createProject(name);
      await mutate();
      setNewName("");
      setCreating(false);
      toast.success(`Project "${name}" created`);
    } catch (err) {
      toast.error(`Failed to create project: ${err instanceof Error ? err.message : "unknown"}`);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Section
      title="Projects"
      description="Isolate traces, costs, and agents by team or workload. Each project has its own member list."
      icon={Folder}
    >
      {isLoading ? (
        <div className="space-y-2">
          {[1, 2].map(i => <div key={i} className="skeleton h-12 rounded-xl" />)}
        </div>
      ) : (
        <div className="space-y-2">
          {(projects ?? []).map((p) => (
            <ProjectRow key={p.id} project={p} onDeleted={() => mutate()} />
          ))}

          {(projects ?? []).length === 0 && (
            <p className="text-sm text-muted-foreground text-center py-6">
              No projects yet. Create one below.
            </p>
          )}

          {/* Create new project */}
          {creating ? (
            <div className="flex items-center gap-2 pt-1">
              <input
                type="text"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleCreate()}
                placeholder="Project name…"
                autoFocus
                className="input-base text-[13px] h-9 flex-1"
              />
              <button
                onClick={handleCreate}
                disabled={submitting || !newName.trim()}
                className="btn btn-primary py-1.5 px-4"
              >
                {submitting ? "Creating…" : "Create"}
              </button>
              <button
                onClick={() => { setCreating(false); setNewName(""); }}
                className="btn btn-ghost py-1.5 px-3"
              >
                Cancel
              </button>
            </div>
          ) : (
            <button
              onClick={() => setCreating(true)}
              className="btn btn-secondary w-full justify-center py-2 text-[13px]"
            >
              <Plus size={14} /> New project
            </button>
          )}
        </div>
      )}
    </Section>
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

// ─── Users Section ─────────────────────────────────────────────────────────────

function InviteDialog({ onClose, onInvited }: { onClose: () => void; onInvited: () => void }) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<"admin" | "viewer">("viewer");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<InviteResponse | null>(null);
  const [copied, setCopied] = useState(false);

  async function handleInvite() {
    if (!email.trim()) return;
    setLoading(true);
    try {
      const inv = await inviteUser(email.trim(), role);
      setResult(inv);
      onInvited();
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Failed to create invite");
    } finally {
      setLoading(false);
    }
  }

  function copyLink() {
    if (!result) return;
    navigator.clipboard.writeText(result.invite_url);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="rounded-xl border w-full max-w-md p-6 space-y-4" style={{ background: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}>
        <h3 className="text-sm font-semibold flex items-center gap-2" style={{ color: "hsl(var(--foreground))" }}>
          <UserPlus size={14} className="text-primary" /> Invite User
        </h3>

        {!result ? (
          <>
            <div className="space-y-3">
              <div>
                <label className="text-xs font-medium block mb-1" style={{ color: "hsl(var(--muted-foreground))" }}>Email</label>
                <input
                  type="email"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  onKeyDown={e => e.key === "Enter" && handleInvite()}
                  placeholder="teammate@example.com"
                  className="w-full px-3 py-2 rounded-lg border text-sm outline-none focus:ring-1 focus:ring-primary/30"
                  style={{ background: "hsl(var(--background))", borderColor: "hsl(var(--border))", color: "hsl(var(--foreground))" }}
                  autoFocus
                />
              </div>
              <div>
                <label className="text-xs font-medium block mb-1" style={{ color: "hsl(var(--muted-foreground))" }}>Role</label>
                <select
                  value={role}
                  onChange={e => setRole(e.target.value as "admin" | "viewer")}
                  className="w-full px-3 py-2 rounded-lg border text-sm outline-none"
                  style={{ background: "hsl(var(--background))", borderColor: "hsl(var(--border))", color: "hsl(var(--foreground))" }}
                >
                  <option value="viewer">Viewer — read-only access</option>
                  <option value="admin">Admin — full access</option>
                </select>
              </div>
            </div>
            <div className="flex items-center gap-2 pt-1">
              <button
                onClick={handleInvite}
                disabled={loading || !email.trim()}
                className="flex-1 py-2 rounded-lg text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
                style={{ background: "hsl(var(--primary))" }}>
                {loading ? "Creating…" : "Create Invite Link"}
              </button>
              <button onClick={onClose} className="px-4 py-2 rounded-lg border text-sm transition-colors hover:bg-accent" style={{ borderColor: "hsl(var(--border))", color: "hsl(var(--muted-foreground))" }}>
                Cancel
              </button>
            </div>
          </>
        ) : (
          <>
            <div className="rounded-lg border p-3 space-y-1" style={{ background: "hsl(var(--muted))", borderColor: "hsl(var(--border))" }}>
              <p className="text-xs font-medium" style={{ color: "hsl(var(--foreground))" }}>Invite link created</p>
              <p className="text-[11px]" style={{ color: "hsl(var(--muted-foreground))" }}>
                Send this to <strong>{result.email}</strong> — expires in 72 hours
              </p>
              <code className="text-[10px] font-mono block truncate mt-2" style={{ color: "hsl(var(--primary))" }}>
                {result.invite_url}
              </code>
            </div>
            <div className="flex gap-2">
              <button
                onClick={copyLink}
                className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg text-sm font-medium text-white transition-opacity hover:opacity-90"
                style={{ background: "hsl(var(--primary))" }}>
                {copied ? <><Check size={12}/>Copied!</> : <><Copy size={12}/>Copy Link</>}
              </button>
              <button onClick={onClose} className="px-4 py-2 rounded-lg border text-sm transition-colors hover:bg-accent" style={{ borderColor: "hsl(var(--border))", color: "hsl(var(--muted-foreground))" }}>
                Done
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function UsersSection() {
  const { data: users, isLoading, mutate } = useSWR<DashboardUser[]>("/api/users", fetcher);
  const [showInvite, setShowInvite] = useState(false);

  async function handleDeactivate(user: DashboardUser) {
    if (!confirm(`Deactivate ${user.email}? They will no longer be able to log in.`)) return;
    try {
      await deactivateUser(user.id);
      toast.success("User deactivated");
      mutate();
    } catch { toast.error("Failed to deactivate user"); }
  }

  async function handleRoleToggle(user: DashboardUser) {
    const newRole = user.role === "admin" ? "viewer" : "admin";
    try {
      await updateUserRole(user.id, newRole);
      toast.success(`Role changed to ${newRole}`);
      mutate();
    } catch { toast.error("Failed to update role"); }
  }

  return (
    <Section title="Users" description="Manage dashboard access — invite teammates, set roles, deactivate accounts" icon={Users}>
      <div className="flex items-center justify-between mb-4">
        <p className="text-xs" style={{ color: "hsl(var(--muted-foreground))" }}>
          {isLoading ? "Loading…" : `${users?.filter(u => u.active).length ?? 0} active user${(users?.filter(u => u.active).length ?? 0) !== 1 ? "s" : ""}`}
        </p>
        <button
          onClick={() => setShowInvite(true)}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-white transition-opacity hover:opacity-90"
          style={{ background: "hsl(var(--primary))" }}>
          <UserPlus size={12} /> Invite User
        </button>
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 2 }).map((_, i) => <Skeleton key={i} className="h-10 w-full rounded-lg" />)}
        </div>
      ) : !users || users.length === 0 ? (
        <div className="py-8 text-center">
          <Users size={32} className="mx-auto mb-3 opacity-20" />
          <p className="text-sm font-medium" style={{ color: "hsl(var(--foreground))" }}>No users yet</p>
          <p className="text-xs mt-1" style={{ color: "hsl(var(--muted-foreground))" }}>Invite teammates to give them dashboard access</p>
        </div>
      ) : (
        <div className="overflow-x-auto -mx-6">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b" style={{ borderColor: "hsl(var(--border))" }}>
                {["Email", "Role", "Last Login", "Status", ""].map(h => (
                  <th key={h} className="px-6 py-2.5 text-left font-medium" style={{ color: "hsl(var(--muted-foreground))" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {users.map(u => (
                <tr key={u.id} className="border-b transition-colors hover:bg-accent/30"
                  style={{ borderColor: "hsl(var(--border))", opacity: u.active ? 1 : 0.5 }}>
                  <td className="px-6 py-3 font-medium" style={{ color: "hsl(var(--foreground))" }}>{u.email}</td>
                  <td className="px-6 py-3">
                    <button
                      onClick={() => handleRoleToggle(u)}
                      disabled={!u.active}
                      className={cn(
                        "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border transition-colors",
                        u.role === "admin"
                          ? "border-primary/30 bg-primary/10 text-primary hover:bg-primary/20"
                          : "border-border text-muted-foreground hover:bg-accent"
                      )}
                      title="Click to toggle role">
                      {u.role === "admin" ? <><ShieldCheck size={10}/>Admin</> : <><Eye size={10}/>Viewer</>}
                    </button>
                  </td>
                  <td className="px-6 py-3" style={{ color: "hsl(var(--muted-foreground))" }}>
                    {u.last_login_at ? timeAgo(u.last_login_at) : <span className="italic">Never</span>}
                  </td>
                  <td className="px-6 py-3">
                    {u.active ? (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border border-emerald-500/30 bg-emerald-500/10 text-emerald-500">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" /> Active
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border border-border text-muted-foreground">
                        Deactivated
                      </span>
                    )}
                  </td>
                  <td className="px-6 py-3">
                    {u.active && (
                      <button
                        onClick={() => handleDeactivate(u)}
                        className="flex items-center gap-1 px-2 py-1 rounded-md text-xs text-red-500 hover:bg-red-500/10 transition-colors">
                        <UserX size={11} /> Deactivate
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showInvite && (
        <InviteDialog
          onClose={() => setShowInvite(false)}
          onInvited={() => mutate()}
        />
      )}
    </Section>
  );
}

// ─── Model Pricing Section ─────────────────────────────────────────────────────

const PROVIDER_ORDER = ["anthropic", "openai", "google", "aws", "meta", "custom"];
const PROVIDER_LABEL: Record<string, string> = {
  anthropic: "Anthropic", openai: "OpenAI", google: "Google",
  aws: "AWS Bedrock", meta: "Meta (self-hosted)", custom: "Custom",
};

function EditPricingRow({ entry, onSave, onCancel }: {
  entry: ModelPricingEntry;
  onSave: (inp: number, out: number, cache: number, notes: string) => Promise<void>;
  onCancel: () => void;
}) {
  const [inp, setInp] = useState(String(entry.input_per_1m_usd));
  const [out, setOut] = useState(String(entry.output_per_1m_usd));
  const [cache, setCache] = useState(String(entry.cache_read_per_1m_usd));
  const [notes, setNotes] = useState(entry.notes ?? "");
  const [saving, setSaving] = useState(false);

  async function handleSave() {
    setSaving(true);
    try {
      await onSave(parseFloat(inp) || 0, parseFloat(out) || 0, parseFloat(cache) || 0, notes);
    } finally { setSaving(false); }
  }

  const inputCls = "w-20 px-1.5 py-0.5 rounded border text-[11px] font-mono outline-none focus:ring-1 focus:ring-primary/30";
  const style = { background: "hsl(var(--background))", borderColor: "hsl(var(--border))", color: "hsl(var(--foreground))" };

  return (
    <tr className="bg-primary/5 border-b" style={{ borderColor: "hsl(var(--border))" }}>
      <td className="px-4 py-2 text-[11px]" style={{ color: "hsl(var(--muted-foreground))" }}>{entry.display_name}</td>
      <td className="px-4 py-2 text-[11px] font-mono" style={{ color: "hsl(var(--muted-foreground))" }}>{entry.model_id}</td>
      <td className="px-4 py-2"><input value={inp} onChange={e => setInp(e.target.value)} className={inputCls} style={style} /></td>
      <td className="px-4 py-2"><input value={out} onChange={e => setOut(e.target.value)} className={inputCls} style={style} /></td>
      <td className="px-4 py-2"><input value={cache} onChange={e => setCache(e.target.value)} className={inputCls} style={style} /></td>
      <td className="px-4 py-2 flex items-center gap-1.5 pt-3">
        <button onClick={handleSave} disabled={saving}
          className="flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium text-white bg-primary hover:opacity-90 disabled:opacity-50">
          <Check size={10}/>{saving ? "…" : "Save"}
        </button>
        <button onClick={onCancel} className="flex items-center gap-1 px-2 py-0.5 rounded text-[11px] border hover:bg-accent"
          style={{ borderColor: "hsl(var(--border))", color: "hsl(var(--muted-foreground))" }}>
          <X size={10}/>Cancel
        </button>
      </td>
    </tr>
  );
}

function ModelPricingSection() {
  const { data: entries, isLoading, mutate } = useSWR<ModelPricingEntry[]>("/api/costs/models", fetcher);
  const [editing, setEditing] = useState<string | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [addForm, setAddForm] = useState({ provider: "custom", model_id: "", display_name: "", input_per_1m_usd: "0", output_per_1m_usd: "0", cache_read_per_1m_usd: "0", notes: "" });
  const [adding, setAdding] = useState(false);

  const active = entries?.filter(e => e.is_active) ?? [];

  // Group by provider
  const grouped = PROVIDER_ORDER.reduce((acc, p) => {
    acc[p] = active.filter(e => e.provider === p);
    return acc;
  }, {} as Record<string, ModelPricingEntry[]>);
  const otherProviders = [...new Set(active.filter(e => !PROVIDER_ORDER.includes(e.provider)).map(e => e.provider))];
  otherProviders.forEach(p => { grouped[p] = active.filter(e => e.provider === p); });

  async function handleUpdate(entry: ModelPricingEntry, inp: number, out: number, cache: number, notes: string) {
    try {
      await updateModelPricing(entry.id, { ...entry, input_per_1m_usd: inp, output_per_1m_usd: out, cache_read_per_1m_usd: cache, notes });
      toast.success("Pricing updated");
      setEditing(null);
      mutate();
    } catch { toast.error("Failed to update pricing"); }
  }

  async function handleAdd() {
    if (!addForm.model_id.trim() || !addForm.display_name.trim()) return;
    setAdding(true);
    try {
      await createModelPricing({ ...addForm, input_per_1m_usd: parseFloat(addForm.input_per_1m_usd) || 0, output_per_1m_usd: parseFloat(addForm.output_per_1m_usd) || 0, cache_read_per_1m_usd: parseFloat(addForm.cache_read_per_1m_usd) || 0 });
      toast.success("Custom model added");
      setShowAdd(false);
      setAddForm({ provider: "custom", model_id: "", display_name: "", input_per_1m_usd: "0", output_per_1m_usd: "0", cache_read_per_1m_usd: "0", notes: "" });
      mutate();
    } catch { toast.error("Failed to add model"); }
    finally { setAdding(false); }
  }

  const inputCls = "px-2 py-1 rounded border text-[12px] outline-none focus:ring-1 focus:ring-primary/30";
  const inputStyle = { background: "hsl(var(--background))", borderColor: "hsl(var(--border))", color: "hsl(var(--foreground))" };

  return (
    <Section title="Model Pricing" description="Token-based costs for LLM providers. Used to calculate spend per session and agent." icon={DollarSign}>
      <div className="flex items-center justify-between mb-4">
        <p className="text-xs" style={{ color: "hsl(var(--muted-foreground))" }}>
          {isLoading ? "Loading…" : `${active.length} active models · prices per 1M tokens`}
        </p>
        <button onClick={() => setShowAdd(s => !s)}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-white transition-opacity hover:opacity-90"
          style={{ background: "hsl(var(--primary))" }}>
          <Plus size={12} /> Add Custom Model
        </button>
      </div>

      {showAdd && (
        <div className="rounded-lg border p-4 mb-4 space-y-3" style={{ background: "hsl(var(--muted))", borderColor: "hsl(var(--border))" }}>
          <p className="text-xs font-semibold" style={{ color: "hsl(var(--foreground))" }}>Add Custom Model</p>
          <div className="grid grid-cols-2 gap-2">
            {[
              { key: "display_name", label: "Display name", placeholder: "My Custom LLM" },
              { key: "model_id",     label: "Model ID",     placeholder: "my-custom-llm-v1" },
              { key: "provider",     label: "Provider",     placeholder: "custom" },
              { key: "notes",        label: "Notes",        placeholder: "Internal fine-tune" },
            ].map(({ key, label, placeholder }) => (
              <div key={key}>
                <label className="text-[11px] font-medium block mb-0.5" style={{ color: "hsl(var(--muted-foreground))" }}>{label}</label>
                <input value={(addForm as Record<string, string>)[key]} onChange={e => setAddForm(f => ({ ...f, [key]: e.target.value }))}
                  placeholder={placeholder} className={cn(inputCls, "w-full")} style={inputStyle} />
              </div>
            ))}
            {[
              { key: "input_per_1m_usd", label: "Input $/1M" },
              { key: "output_per_1m_usd", label: "Output $/1M" },
              { key: "cache_read_per_1m_usd", label: "Cache read $/1M" },
            ].map(({ key, label }) => (
              <div key={key}>
                <label className="text-[11px] font-medium block mb-0.5" style={{ color: "hsl(var(--muted-foreground))" }}>{label}</label>
                <input type="number" step="0.01" min="0" value={(addForm as Record<string, string>)[key]} onChange={e => setAddForm(f => ({ ...f, [key]: e.target.value }))}
                  className={cn(inputCls, "w-full font-mono")} style={inputStyle} />
              </div>
            ))}
          </div>
          <div className="flex gap-2">
            <button onClick={handleAdd} disabled={adding || !addForm.model_id.trim()}
              className="px-3 py-1.5 rounded-lg text-xs font-medium text-white disabled:opacity-50"
              style={{ background: "hsl(var(--primary))" }}>
              {adding ? "Adding…" : "Add Model"}
            </button>
            <button onClick={() => setShowAdd(false)} className="px-3 py-1.5 rounded-lg border text-xs transition-colors hover:bg-accent"
              style={{ borderColor: "hsl(var(--border))", color: "hsl(var(--muted-foreground))" }}>
              Cancel
            </button>
          </div>
        </div>
      )}

      <div className="overflow-x-auto -mx-6 space-y-4">
        {[...PROVIDER_ORDER, ...otherProviders].map(provider => {
          const models = grouped[provider];
          if (!models || models.length === 0) return null;
          return (
            <div key={provider}>
              <p className="text-[11px] font-semibold uppercase tracking-wider px-6 mb-1" style={{ color: "hsl(var(--muted-foreground))" }}>
                {PROVIDER_LABEL[provider] ?? provider}
              </p>
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b" style={{ borderColor: "hsl(var(--border))" }}>
                    {["Model", "ID", "Input $/1M", "Output $/1M", "Cache $/1M", ""].map(h => (
                      <th key={h} className="px-4 py-2 text-left font-medium" style={{ color: "hsl(var(--muted-foreground))" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {models.map(e => editing === e.id
                    ? <EditPricingRow key={e.id} entry={e} onSave={(inp, out, cache, notes) => handleUpdate(e, inp, out, cache, notes)} onCancel={() => setEditing(null)} />
                    : (
                      <tr key={e.id} className="border-b transition-colors hover:bg-accent/30" style={{ borderColor: "hsl(var(--border))" }}>
                        <td className="px-4 py-2.5 font-medium" style={{ color: "hsl(var(--foreground))" }}>
                          {e.display_name}
                          {e.is_custom && <span className="ml-1.5 text-[10px] px-1.5 py-0.5 rounded-full border border-primary/30 bg-primary/10 text-primary">custom</span>}
                        </td>
                        <td className="px-4 py-2.5 font-mono text-[11px]" style={{ color: "hsl(var(--muted-foreground))" }}>{e.model_id}</td>
                        <td className="px-4 py-2.5 font-mono" style={{ color: "hsl(var(--foreground))" }}>${e.input_per_1m_usd.toFixed(3)}</td>
                        <td className="px-4 py-2.5 font-mono" style={{ color: "hsl(var(--foreground))" }}>${e.output_per_1m_usd.toFixed(3)}</td>
                        <td className="px-4 py-2.5 font-mono" style={{ color: "hsl(var(--muted-foreground))" }}>${e.cache_read_per_1m_usd.toFixed(3)}</td>
                        <td className="px-4 py-2.5">
                          <button onClick={() => setEditing(e.id)}
                            className="flex items-center gap-1 px-2 py-1 rounded-md text-xs transition-colors hover:bg-accent"
                            style={{ color: "hsl(var(--muted-foreground))" }}>
                            <Pencil size={11}/> Edit
                          </button>
                        </td>
                      </tr>
                    )
                  )}
                </tbody>
              </table>
            </div>
          );
        })}
      </div>
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
    <div className="space-y-5 max-w-3xl page-in">
      <div>
        <h1 className="text-xl font-bold text-foreground">Settings</h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          Manage users, model pricing, API keys, and instance configuration
        </p>
      </div>

      <ProjectsSection />
      <UsersSection />
      <ModelPricingSection />
      <ApiKeysSection />
      <InstanceSection />
      <AboutSection />
    </div>
  );
}
