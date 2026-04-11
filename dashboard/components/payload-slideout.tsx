"use client";

import { useState, useEffect, useCallback } from "react";
import { X, Copy, Check, WrapText, FileText, Code2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { MarkdownContentFull } from "@/components/markdown-content";

interface PayloadTab {
  label: string;
  json: string | null;
}

export interface PayloadSlideoutProps {
  open: boolean;
  onClose: () => void;
  title: string;
  tabs: PayloadTab[];
}

/**
 * Detects if content is likely JSON (starts with { or [).
 */
function isLikelyJson(text: string): boolean {
  const trimmed = text.trim();
  return (trimmed.startsWith("{") || trimmed.startsWith("[")) && trimmed.length > 2;
}

export function PayloadSlideout({ open, onClose, title, tabs }: PayloadSlideoutProps) {
  const [activeTab, setActiveTab] = useState(0);
  const [wordWrap, setWordWrap] = useState(true);
  const [copied, setCopied] = useState(false);
  const [viewMode, setViewMode] = useState<"markdown" | "raw">("markdown");

  useEffect(() => { if (open) { setActiveTab(0); setCopied(false); setViewMode("markdown"); } }, [open]);

  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  const raw = tabs[activeTab]?.json ?? "";
  let formatted = raw;
  try { formatted = JSON.stringify(JSON.parse(raw), null, 2); } catch { /* keep raw */ }
  const lines = formatted.split("\n");

  // Determine if content is text (markdown-renderable) vs JSON
  const isJson = isLikelyJson(raw);
  const showMarkdown = viewMode === "markdown" && !isJson;

  const handleCopy = useCallback(async () => {
    await navigator.clipboard.writeText(formatted);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [formatted]);

  if (!open) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/30 backdrop-blur-sm"
        onClick={onClose}
        style={{ animation: "fadeIn 0.15s ease" }}
      />
      {/* Panel */}
      <div
        className="fixed top-0 right-0 bottom-0 z-50 flex flex-col"
        style={{
          width: "50%",
          minWidth: 400,
          maxWidth: 800,
          background: "hsl(var(--card))",
          borderLeft: "1px solid hsl(var(--border))",
          boxShadow: "-4px 0 24px rgba(0,0,0,0.15)",
          animation: "slideInRight 0.2s ease",
        }}
      >
        {/* Header */}
        <div
          className="flex items-center justify-between px-4 py-3 border-b flex-shrink-0"
          style={{ borderColor: "hsl(var(--border))", background: "hsl(var(--card-raised))" }}
        >
          <span className="text-[13px] font-semibold text-foreground truncate">{title}</span>
          <div className="flex items-center gap-1.5">
            {/* Markdown / Raw toggle — only for non-JSON content */}
            {!isJson && (
              <div className="flex items-center rounded-md overflow-hidden mr-1" style={{ border: "1px solid hsl(var(--border))" }}>
                <button
                  onClick={() => setViewMode("markdown")}
                  className={cn(
                    "p-1.5 transition-colors flex items-center gap-1 text-[10px] font-medium",
                    viewMode === "markdown"
                      ? "bg-primary/10 text-primary"
                      : "text-muted-foreground hover:text-foreground hover:bg-accent/40",
                  )}
                  title="Rendered markdown"
                >
                  <FileText size={12} />
                  <span>Markdown</span>
                </button>
                <button
                  onClick={() => setViewMode("raw")}
                  className={cn(
                    "p-1.5 transition-colors flex items-center gap-1 text-[10px] font-medium",
                    viewMode === "raw"
                      ? "bg-primary/10 text-primary"
                      : "text-muted-foreground hover:text-foreground hover:bg-accent/40",
                  )}
                  title="Raw text"
                >
                  <Code2 size={12} />
                  <span>Raw</span>
                </button>
              </div>
            )}
            {!showMarkdown && (
              <button
                onClick={() => setWordWrap((w) => !w)}
                className={cn("p-1.5 rounded hover:bg-accent/60 transition-colors", wordWrap ? "text-primary" : "text-muted-foreground")}
                title="Toggle word wrap"
              >
                <WrapText size={14} />
              </button>
            )}
            <button onClick={handleCopy} className="p-1.5 rounded text-muted-foreground hover:text-foreground hover:bg-accent/60 transition-colors" title="Copy">
              {copied ? <Check size={14} className="text-emerald-500" /> : <Copy size={14} />}
            </button>
            <button onClick={onClose} className="p-1.5 rounded text-muted-foreground hover:text-foreground hover:bg-accent/60 transition-colors" title="Close (Esc)">
              <X size={14} />
            </button>
          </div>
        </div>

        {/* Tabs */}
        {tabs.length > 1 && (
          <div className="flex border-b flex-shrink-0 px-4" style={{ borderColor: "hsl(var(--border))" }}>
            {tabs.map((tab, i) => (
              <button
                key={tab.label}
                onClick={() => setActiveTab(i)}
                className={cn(
                  "px-3 py-2 text-[12px] font-medium border-b-2 -mb-px transition-colors",
                  i === activeTab
                    ? "border-primary text-foreground"
                    : "border-transparent text-muted-foreground hover:text-foreground",
                )}
              >
                {tab.label}
              </button>
            ))}
          </div>
        )}

        {/* Content */}
        <div className="flex-1 overflow-auto">
          {raw ? (
            showMarkdown ? (
              /* Markdown rendered view */
              <MarkdownContentFull content={raw} wordWrap={wordWrap} />
            ) : (
              /* Raw / JSON code view */
              <div className="flex min-h-full">
                {/* Line numbers */}
                <div
                  className="flex-shrink-0 px-3 py-3 text-right select-none border-r"
                  style={{
                    borderColor: "hsl(var(--border))",
                    background: "hsl(var(--muted))",
                    fontFamily: "var(--font-geist-mono)",
                    fontSize: 11,
                    lineHeight: "1.6",
                    color: "hsl(var(--muted-foreground))",
                  }}
                >
                  {lines.map((_, i) => <div key={i}>{i + 1}</div>)}
                </div>
                {/* Code */}
                <pre
                  className="flex-1 p-3"
                  style={{
                    fontFamily: "var(--font-geist-mono)",
                    fontSize: 12,
                    lineHeight: "1.6",
                    color: "hsl(var(--foreground))",
                    whiteSpace: wordWrap ? "pre-wrap" : "pre",
                    wordBreak: wordWrap ? "break-all" : "normal",
                    overflowX: wordWrap ? "hidden" : "auto",
                  }}
                >
                  {formatted}
                </pre>
              </div>
            )
          ) : (
            <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
              No data
            </div>
          )}
        </div>
      </div>
    </>
  );
}
