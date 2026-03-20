"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { Pencil, Check, X, Plus, ExternalLink, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

/* ── Editable single-line text ─────────────────────────────── */
export function EditableText({
  value, onSave, placeholder, label,
}: {
  value: string; onSave: (v: string) => Promise<void>; placeholder?: string; label?: string;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const [saving, setSaving] = useState(false);
  const ref = useRef<HTMLInputElement>(null);

  useEffect(() => { setDraft(value); }, [value]);
  useEffect(() => { if (editing) ref.current?.focus(); }, [editing]);

  const save = useCallback(async () => {
    if (draft === value) { setEditing(false); return; }
    setSaving(true);
    try { await onSave(draft); setEditing(false); } finally { setSaving(false); }
  }, [draft, value, onSave]);

  if (editing) {
    return (
      <div className="flex items-center gap-1.5">
        <input ref={ref} value={draft} onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") save(); if (e.key === "Escape") { setDraft(value); setEditing(false); } }}
          className="input-base h-[28px] text-[12px] flex-1 px-2" placeholder={placeholder} disabled={saving} />
        <button onClick={save} disabled={saving} className="p-1 rounded hover:bg-accent/60 text-emerald-500"><Check size={12} /></button>
        <button onClick={() => { setDraft(value); setEditing(false); }} className="p-1 rounded hover:bg-accent/60 text-muted-foreground"><X size={12} /></button>
        {saving && <Loader2 size={12} className="animate-spin text-muted-foreground" />}
      </div>
    );
  }

  return (
    <div className="group flex items-start gap-2 cursor-pointer" onClick={() => setEditing(true)}>
      <p className={cn("text-[12px] flex-1", value ? "text-foreground" : "text-muted-foreground italic")}>
        {value || placeholder || "Click to add..."}
      </p>
      <Pencil size={10} className="text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity mt-0.5 flex-shrink-0" />
    </div>
  );
}

/* ── Editable multi-line textarea ──────────────────────────── */
export function EditableTextarea({
  value, onSave, placeholder, label,
}: {
  value: string; onSave: (v: string) => Promise<void>; placeholder?: string; label?: string;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const [saving, setSaving] = useState(false);
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => { setDraft(value); }, [value]);
  useEffect(() => { if (editing) ref.current?.focus(); }, [editing]);

  const save = useCallback(async () => {
    if (draft === value) { setEditing(false); return; }
    setSaving(true);
    try { await onSave(draft); setEditing(false); } finally { setSaving(false); }
  }, [draft, value, onSave]);

  if (editing) {
    return (
      <div>
        <textarea ref={ref} value={draft} onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Escape") { setDraft(value); setEditing(false); } }}
          className="input-base text-[12px] w-full px-2.5 py-2 min-h-[60px] resize-y" placeholder={placeholder} disabled={saving} />
        <div className="flex items-center gap-1.5 mt-1">
          <button onClick={save} disabled={saving} className="text-[10px] px-2 py-0.5 rounded bg-primary text-primary-foreground font-medium">Save</button>
          <button onClick={() => { setDraft(value); setEditing(false); }} className="text-[10px] px-2 py-0.5 rounded text-muted-foreground hover:text-foreground">Cancel</button>
          {saving && <Loader2 size={10} className="animate-spin text-muted-foreground" />}
        </div>
      </div>
    );
  }

  return (
    <div className="group flex items-start gap-2 cursor-pointer" onClick={() => setEditing(true)}>
      <p className={cn("text-[12px] flex-1 whitespace-pre-wrap", value ? "text-foreground" : "text-muted-foreground italic")}>
        {value || placeholder || "Click to add a description..."}
      </p>
      <Pencil size={10} className="text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity mt-0.5 flex-shrink-0" />
    </div>
  );
}

/* ── Editable tag pills ────────────────────────────────────── */
export function EditableTags({
  tags, onSave, suggestions,
}: {
  tags: string[]; onSave: (tags: string[]) => Promise<void>; suggestions?: string[];
}) {
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const ref = useRef<HTMLInputElement>(null);

  useEffect(() => { if (adding) ref.current?.focus(); }, [adding]);

  async function addTag() {
    const tag = draft.trim().toLowerCase();
    if (!tag || tags.includes(tag)) { setDraft(""); setAdding(false); return; }
    setSaving(true);
    try { await onSave([...tags, tag]); setDraft(""); setAdding(false); } finally { setSaving(false); }
  }

  async function removeTag(tag: string) {
    setSaving(true);
    try { await onSave(tags.filter((t) => t !== tag)); } finally { setSaving(false); }
  }

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {tags.map((tag) => (
        <span key={tag} className="inline-flex items-center gap-1 text-[10px] font-medium px-2 py-0.5 rounded-md group/tag"
          style={{ background: "hsl(var(--primary) / 0.08)", color: "hsl(var(--primary))", border: "1px solid hsl(var(--primary) / 0.12)" }}>
          {tag}
          <button onClick={() => removeTag(tag)} className="opacity-0 group-hover/tag:opacity-100 transition-opacity hover:text-red-400" disabled={saving}>
            <X size={9} />
          </button>
        </span>
      ))}
      {adding ? (
        <div className="flex items-center gap-1">
          <input ref={ref} value={draft} onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") addTag(); if (e.key === "Escape") { setDraft(""); setAdding(false); } }}
            className="input-base h-[22px] text-[10px] w-20 px-1.5" placeholder="tag name" disabled={saving} />
          <button onClick={addTag} className="p-0.5 rounded hover:bg-accent/60 text-emerald-500"><Check size={10} /></button>
          {saving && <Loader2 size={10} className="animate-spin text-muted-foreground" />}
        </div>
      ) : (
        <button onClick={() => setAdding(true)} className="inline-flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-accent/40 transition-colors"
          style={{ border: "1px dashed hsl(var(--border))" }}>
          <Plus size={9} /> Add tag
        </button>
      )}
    </div>
  );
}

/* ── Editable URL ──────────────────────────────────────────── */
export function EditableUrl({
  value, onSave, placeholder,
}: {
  value: string; onSave: (v: string) => Promise<void>; placeholder?: string;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const [saving, setSaving] = useState(false);
  const ref = useRef<HTMLInputElement>(null);

  useEffect(() => { setDraft(value); }, [value]);
  useEffect(() => { if (editing) ref.current?.focus(); }, [editing]);

  const save = useCallback(async () => {
    if (draft === value) { setEditing(false); return; }
    setSaving(true);
    try { await onSave(draft); setEditing(false); } finally { setSaving(false); }
  }, [draft, value, onSave]);

  if (editing) {
    return (
      <div className="flex items-center gap-1.5">
        <input ref={ref} value={draft} onChange={(e) => setDraft(e.target.value)} type="url"
          onKeyDown={(e) => { if (e.key === "Enter") save(); if (e.key === "Escape") { setDraft(value); setEditing(false); } }}
          className="input-base h-[28px] text-[12px] flex-1 px-2" placeholder={placeholder ?? "https://..."} disabled={saving} />
        <button onClick={save} disabled={saving} className="p-1 rounded hover:bg-accent/60 text-emerald-500"><Check size={12} /></button>
        <button onClick={() => { setDraft(value); setEditing(false); }} className="p-1 rounded hover:bg-accent/60 text-muted-foreground"><X size={12} /></button>
      </div>
    );
  }

  return (
    <div className="group flex items-center gap-2 cursor-pointer" onClick={() => setEditing(true)}>
      {value ? (
        <a href={value} target="_blank" rel="noopener noreferrer" onClick={(e) => e.stopPropagation()}
          className="text-[12px] text-primary hover:underline truncate flex items-center gap-1">
          {value} <ExternalLink size={10} />
        </a>
      ) : (
        <span className="text-[12px] text-muted-foreground italic">{placeholder || "Click to add URL..."}</span>
      )}
      <Pencil size={10} className="text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0" />
    </div>
  );
}
