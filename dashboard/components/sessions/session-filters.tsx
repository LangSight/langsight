"use client";

import { Filter, Search } from "lucide-react";
import { cn } from "@/lib/utils";

export type StatusFilter = "all" | "clean" | "failed";

interface SessionFiltersProps {
  search: string;
  onSearch: (v: string) => void;
  statusFilter: StatusFilter;
  onStatus: (v: StatusFilter) => void;
  agentFilter: string;
  onAgent: (v: string) => void;
  healthTagFilter: string;
  onHealthTag: (v: string) => void;
  agentNames: string[];
  countAll: number;
  countClean: number;
  countFailed: number;
}

export function SessionFilters({
  search, onSearch,
  statusFilter, onStatus,
  agentFilter, onAgent,
  healthTagFilter, onHealthTag,
  agentNames,
  countAll, countClean, countFailed,
}: SessionFiltersProps) {
  return (
    <div className="flex flex-wrap items-center gap-2.5 mt-3">
      <div className="relative flex-1 min-w-[180px] max-w-sm">
        <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
        <input
          type="search"
          aria-label="Search sessions"
          value={search}
          onChange={(e) => onSearch(e.target.value)}
          placeholder="Search session ID, agent, server..."
          className="input-base pl-8 h-[34px] text-[13px]"
        />
      </div>

      <div className="flex items-center gap-1.5" role="group" aria-label="Session status filter">
        {([
          ["all",    "All",    countAll],
          ["clean",  "Clean",  countClean],
          ["failed", "Failed", countFailed],
        ] as const).map(([key, label, count]) => (
          <button
            key={key}
            aria-pressed={statusFilter === key}
            onClick={() => onStatus(key)}
            className={cn(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-all",
              statusFilter === key
                ? "bg-primary/10 border-primary/30 text-primary"
                : "bg-card border-border text-muted-foreground hover:bg-accent hover:text-foreground"
            )}
          >
            {label}
            <span
              className={cn(
                "text-[10px] px-1.5 py-0.5 rounded-full min-w-[18px] text-center tabular-nums",
                statusFilter === key ? "bg-primary/15 text-primary" : "bg-muted text-muted-foreground"
              )}
              aria-label={`${count} sessions`}
            >
              {count}
            </span>
          </button>
        ))}
      </div>

      {agentNames.length > 1 && (
        <div className="flex items-center gap-1.5">
          <Filter size={13} className="text-muted-foreground" aria-hidden="true" />
          <label htmlFor="agent-filter" className="sr-only">Filter by agent</label>
          <select
            id="agent-filter"
            value={agentFilter}
            onChange={(e) => onAgent(e.target.value)}
            className="text-xs rounded-lg px-2 py-1.5 border border-border bg-card text-foreground outline-none h-[34px]"
          >
            <option value="all">All agents</option>
            {agentNames.map((name) => (
              <option key={name} value={name}>{name}</option>
            ))}
          </select>
        </div>
      )}

      <div className="flex items-center gap-1.5">
        <label htmlFor="health-tag-filter" className="sr-only">Filter by health tag</label>
        <select
          id="health-tag-filter"
          value={healthTagFilter}
          onChange={(e) => onHealthTag(e.target.value)}
          className="text-xs rounded-lg px-2 py-1.5 border border-border bg-card text-foreground outline-none h-[34px]"
        >
          <option value="all">All health tags</option>
          <option value="success">Success</option>
          <option value="success_with_fallback">Fallback</option>
          <option value="loop_detected">Loop</option>
          <option value="budget_exceeded">Budget</option>
          <option value="tool_failure">Failure</option>
          <option value="circuit_breaker_open">Circuit Open</option>
          <option value="timeout">Timeout</option>
          <option value="schema_drift">Schema Drift</option>
          <option value="incomplete">Incomplete</option>
        </select>
      </div>
    </div>
  );
}
