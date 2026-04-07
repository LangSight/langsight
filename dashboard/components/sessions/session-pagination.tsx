"use client";

import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from "lucide-react";
import { cn } from "@/lib/utils";

interface SessionPaginationProps {
  page: number;
  totalPages: number;
  totalItems: number;
  pageSize: number;
  onPage: (p: number) => void;
}

export function SessionPagination({ page, totalPages, totalItems, pageSize, onPage }: SessionPaginationProps) {
  if (totalItems === 0) return null;

  const pages: (number | "...")[] = [];
  if (totalPages <= 7) {
    for (let i = 0; i < totalPages; i++) pages.push(i);
  } else {
    pages.push(0);
    if (page > 2) pages.push("...");
    for (let i = Math.max(1, page - 1); i <= Math.min(totalPages - 2, page + 1); i++) pages.push(i);
    if (page < totalPages - 3) pages.push("...");
    pages.push(totalPages - 1);
  }

  return (
    <div
      className="flex items-center justify-between px-4 py-2 border-t text-[10px] text-muted-foreground"
      style={{ borderColor: "hsl(var(--border))" }}
    >
      <span>
        {page * pageSize + 1}–{Math.min((page + 1) * pageSize, totalItems)} of {totalItems}
      </span>
      <div className="flex items-center gap-px">
        <button onClick={() => onPage(0)} disabled={page === 0} className="p-1 rounded hover:bg-accent disabled:opacity-30 transition-colors">
          <ChevronsLeft size={10} />
        </button>
        <button onClick={() => onPage(Math.max(0, page - 1))} disabled={page === 0} className="p-1 rounded hover:bg-accent disabled:opacity-30 transition-colors">
          <ChevronLeft size={10} />
        </button>
        {pages.map((p, idx) =>
          p === "..." ? (
            <span key={`ellipsis-${idx}`} className="px-1 text-muted-foreground">…</span>
          ) : (
            <button
              key={p}
              onClick={() => onPage(p)}
              className={cn(
                "min-w-[20px] h-[20px] rounded text-[9px] font-medium tabular-nums transition-colors",
                page === p ? "bg-primary text-primary-foreground" : "hover:bg-accent text-muted-foreground"
              )}
            >
              {p + 1}
            </button>
          )
        )}
        <button onClick={() => onPage(Math.min(totalPages - 1, page + 1))} disabled={page >= totalPages - 1} className="p-1 rounded hover:bg-accent disabled:opacity-30 transition-colors">
          <ChevronRight size={10} />
        </button>
        <button onClick={() => onPage(totalPages - 1)} disabled={page >= totalPages - 1} className="p-1 rounded hover:bg-accent disabled:opacity-30 transition-colors">
          <ChevronsRight size={10} />
        </button>
      </div>
    </div>
  );
}
