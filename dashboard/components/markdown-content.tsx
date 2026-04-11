"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/utils";

/**
 * Detects whether a string is likely JSON (starts with { or [).
 * If so, we render it as formatted code; otherwise as markdown.
 */
function isLikelyJson(text: string): boolean {
  const trimmed = text.trim();
  return (trimmed.startsWith("{") || trimmed.startsWith("[")) && trimmed.length > 2;
}

interface MarkdownContentProps {
  content: string;
  /** Max lines to clamp (CSS line-clamp). Omit for no clamp. */
  clamp?: number;
  /** Additional className */
  className?: string;
  /** Font size class (default: text-[12px]) */
  fontSize?: string;
}

/**
 * Renders LLM text content as markdown. Falls back to <pre> for JSON.
 * Styled to match the dashboard dark theme.
 */
export function MarkdownContent({
  content,
  clamp,
  className,
  fontSize = "text-[12px]",
}: MarkdownContentProps) {
  if (!content) return null;

  // JSON content — render as formatted code
  if (isLikelyJson(content)) {
    let formatted = content;
    try {
      formatted = JSON.stringify(JSON.parse(content), null, 2);
    } catch {
      /* keep raw */
    }
    return (
      <pre
        className={cn(
          fontSize,
          "text-foreground rounded-lg p-3 whitespace-pre-wrap break-all leading-relaxed overflow-y-auto",
          clamp && `line-clamp-${clamp}`,
          className,
        )}
        style={{
          fontFamily: "var(--font-geist-mono)",
          background: "hsl(var(--muted))",
          border: "1px solid hsl(var(--border))",
        }}
      >
        {formatted}
      </pre>
    );
  }

  // Markdown content
  return (
    <div
      className={cn(
        "markdown-content",
        fontSize,
        "text-foreground rounded-lg px-3 py-2.5 leading-relaxed overflow-y-auto",
        clamp && "overflow-hidden",
        className,
      )}
      style={{
        background: "hsl(var(--muted))",
        ...(clamp
          ? {
              display: "-webkit-box",
              WebkitLineClamp: clamp,
              WebkitBoxOrient: "vertical" as const,
              overflow: "hidden",
            }
          : {}),
      }}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => (
            <p className="mb-2 last:mb-0">{children}</p>
          ),
          h1: ({ children }) => (
            <h1 className="text-sm font-bold mb-2 mt-3 first:mt-0">{children}</h1>
          ),
          h2: ({ children }) => (
            <h2 className="text-[13px] font-bold mb-1.5 mt-2.5 first:mt-0">{children}</h2>
          ),
          h3: ({ children }) => (
            <h3 className="text-[12px] font-semibold mb-1 mt-2 first:mt-0">{children}</h3>
          ),
          ul: ({ children }) => (
            <ul className="list-disc pl-4 mb-2 space-y-0.5">{children}</ul>
          ),
          ol: ({ children }) => (
            <ol className="list-decimal pl-4 mb-2 space-y-0.5">{children}</ol>
          ),
          li: ({ children }) => <li className="leading-relaxed">{children}</li>,
          code: ({ className: codeClassName, children, ...props }) => {
            const isInline = !codeClassName;
            if (isInline) {
              return (
                <code
                  className="px-1 py-0.5 rounded text-[11px] font-medium"
                  style={{
                    fontFamily: "var(--font-geist-mono)",
                    background: "hsl(var(--border))",
                    color: "hsl(var(--primary))",
                  }}
                  {...props}
                >
                  {children}
                </code>
              );
            }
            return (
              <code
                className={cn("block text-[11px] rounded-md p-2 my-1.5 overflow-x-auto", codeClassName)}
                style={{
                  fontFamily: "var(--font-geist-mono)",
                  background: "hsl(var(--background))",
                  border: "1px solid hsl(var(--border))",
                }}
                {...props}
              >
                {children}
              </code>
            );
          },
          pre: ({ children }) => <div className="my-1.5">{children}</div>,
          blockquote: ({ children }) => (
            <blockquote
              className="pl-3 my-2 italic text-muted-foreground"
              style={{ borderLeft: "2px solid hsl(var(--border))" }}
            >
              {children}
            </blockquote>
          ),
          strong: ({ children }) => (
            <strong className="font-semibold">{children}</strong>
          ),
          a: ({ href, children }) => (
            <a
              href={href}
              className="text-primary hover:underline"
              target="_blank"
              rel="noopener noreferrer"
            >
              {children}
            </a>
          ),
          table: ({ children }) => (
            <div className="overflow-x-auto my-2">
              <table className="w-full text-[11px] border-collapse">{children}</table>
            </div>
          ),
          th: ({ children }) => (
            <th
              className="text-left px-2 py-1 font-semibold text-muted-foreground"
              style={{
                borderBottom: "1px solid hsl(var(--border))",
                background: "hsl(var(--background))",
              }}
            >
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td
              className="px-2 py-1"
              style={{ borderBottom: "1px solid hsl(var(--border) / 0.5)" }}
            >
              {children}
            </td>
          ),
          hr: () => (
            <hr className="my-3" style={{ borderColor: "hsl(var(--border))" }} />
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

/**
 * Full-size markdown renderer for the PayloadSlideout.
 * No clamp, larger line height, optional word wrap.
 */
export function MarkdownContentFull({
  content,
  wordWrap = true,
}: {
  content: string;
  wordWrap?: boolean;
}) {
  if (!content) return null;

  // JSON — render as code with line numbers handled by parent
  if (isLikelyJson(content)) {
    return null; // Signal parent to use its own JSON renderer
  }

  return (
    <div
      className="markdown-content-full flex-1 p-4 text-[12px] text-foreground leading-[1.7] overflow-auto"
      style={{
        wordBreak: wordWrap ? "break-word" : "normal",
        overflowWrap: wordWrap ? "break-word" : "normal",
      }}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => <p className="mb-3 last:mb-0">{children}</p>,
          h1: ({ children }) => (
            <h1 className="text-base font-bold mb-3 mt-4 first:mt-0 pb-1" style={{ borderBottom: "1px solid hsl(var(--border))" }}>{children}</h1>
          ),
          h2: ({ children }) => (
            <h2 className="text-sm font-bold mb-2 mt-3 first:mt-0">{children}</h2>
          ),
          h3: ({ children }) => (
            <h3 className="text-[13px] font-semibold mb-1.5 mt-2.5 first:mt-0">{children}</h3>
          ),
          ul: ({ children }) => (
            <ul className="list-disc pl-5 mb-3 space-y-1">{children}</ul>
          ),
          ol: ({ children }) => (
            <ol className="list-decimal pl-5 mb-3 space-y-1">{children}</ol>
          ),
          li: ({ children }) => <li className="leading-relaxed">{children}</li>,
          code: ({ className: codeClassName, children, ...props }) => {
            const isInline = !codeClassName;
            if (isInline) {
              return (
                <code
                  className="px-1.5 py-0.5 rounded text-[11px] font-medium"
                  style={{
                    fontFamily: "var(--font-geist-mono)",
                    background: "hsl(var(--border))",
                    color: "hsl(var(--primary))",
                  }}
                  {...props}
                >
                  {children}
                </code>
              );
            }
            return (
              <code
                className={cn("block text-[11px] rounded-lg p-3 my-2 overflow-x-auto", codeClassName)}
                style={{
                  fontFamily: "var(--font-geist-mono)",
                  background: "hsl(var(--background))",
                  border: "1px solid hsl(var(--border))",
                  lineHeight: "1.6",
                }}
                {...props}
              >
                {children}
              </code>
            );
          },
          pre: ({ children }) => <div className="my-2">{children}</div>,
          blockquote: ({ children }) => (
            <blockquote
              className="pl-4 my-3 italic text-muted-foreground"
              style={{ borderLeft: "3px solid hsl(var(--primary) / 0.3)" }}
            >
              {children}
            </blockquote>
          ),
          strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
          a: ({ href, children }) => (
            <a href={href} className="text-primary hover:underline" target="_blank" rel="noopener noreferrer">{children}</a>
          ),
          table: ({ children }) => (
            <div className="overflow-x-auto my-3 rounded-lg" style={{ border: "1px solid hsl(var(--border))" }}>
              <table className="w-full text-[11px] border-collapse">{children}</table>
            </div>
          ),
          th: ({ children }) => (
            <th className="text-left px-3 py-1.5 font-semibold text-muted-foreground" style={{ borderBottom: "1px solid hsl(var(--border))", background: "hsl(var(--muted))" }}>{children}</th>
          ),
          td: ({ children }) => (
            <td className="px-3 py-1.5" style={{ borderBottom: "1px solid hsl(var(--border) / 0.5)" }}>{children}</td>
          ),
          hr: () => <hr className="my-4" style={{ borderColor: "hsl(var(--border))" }} />,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
