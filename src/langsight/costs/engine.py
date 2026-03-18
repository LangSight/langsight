"""
Cost attribution engine — assigns dollar costs to MCP tool calls.

Pricing rules are defined in .langsight.yaml:

    costs:
      rules:
        - server: postgres-mcp
          tool: "*"
          cost_per_call: 0.0            # free self-hosted
        - server: openai-mcp
          tool: "chat_completion"
          cost_per_call: 0.005          # $0.005 per call
        - server: "*"
          tool: "*"
          cost_per_call: 0.001          # $0.001 default

The engine multiplies call counts (from ReliabilityEngine) by pricing rules
and groups by server, tool, agent, and session.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from langsight.reliability.engine import ReliabilityEngine


@dataclass
class CostRule:
    """A single pricing rule matching server + tool patterns."""

    server: str = "*"  # glob pattern, e.g. "postgres-mcp" or "*"
    tool: str = "*"  # glob pattern, e.g. "query" or "*"
    cost_per_call: float = 0.001

    def matches(self, server_name: str, tool_name: str) -> bool:
        return fnmatch.fnmatch(server_name, self.server) and fnmatch.fnmatch(tool_name, self.tool)


@dataclass
class CostEntry:
    """Cost breakdown for one server/tool combination."""

    server_name: str
    tool_name: str
    total_calls: int
    cost_per_call: float
    total_cost_usd: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "server_name": self.server_name,
            "tool_name": self.tool_name,
            "total_calls": self.total_calls,
            "cost_per_call_usd": self.cost_per_call,
            "total_cost_usd": round(self.total_cost_usd, 6),
        }


@dataclass
class AgentCostEntry:
    """Cost breakdown aggregated per agent."""

    agent_name: str
    total_calls: int
    total_cost_usd: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_name": self.agent_name,
            "total_calls": self.total_calls,
            "total_cost_usd": round(self.total_cost_usd, 6),
        }


@dataclass
class SessionCostEntry:
    """Cost breakdown aggregated per session."""

    session_id: str
    agent_name: str | None
    total_calls: int
    total_cost_usd: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "agent_name": self.agent_name,
            "total_calls": self.total_calls,
            "total_cost_usd": round(self.total_cost_usd, 6),
        }


class CostEngine:
    """Computes cost attribution from tool call metrics + pricing rules."""

    def __init__(
        self,
        reliability: ReliabilityEngine,
        rules: list[CostRule] | None = None,
    ) -> None:
        self._reliability = reliability
        self._rules = rules or [CostRule()]  # default: $0.001/call for everything

    async def calculate(self, hours: int = 24) -> list[CostEntry]:
        """Calculate costs for all tools in the given time window."""
        metrics = await self._reliability.get_metrics(hours=hours)
        entries: list[CostEntry] = []

        for m in metrics:
            cost_per_call = self._find_cost(m.server_name, m.tool_name)
            entries.append(
                CostEntry(
                    server_name=m.server_name,
                    tool_name=m.tool_name,
                    total_calls=m.total_calls,
                    cost_per_call=cost_per_call,
                    total_cost_usd=m.total_calls * cost_per_call,
                )
            )

        # Sort by total cost descending
        return sorted(entries, key=lambda e: e.total_cost_usd, reverse=True)

    @property
    def total_cost_usd(self) -> float:
        """Synchronous helper — call calculate() first to get entries."""
        return 0.0  # placeholder; use calculate() result

    def _find_cost(self, server_name: str, tool_name: str) -> float:
        """Find the first matching pricing rule for this server + tool."""
        return find_cost_per_call(self._rules, server_name, tool_name)


def find_cost_per_call(
    rules: list[CostRule],
    server_name: str,
    tool_name: str,
) -> float:
    """Find the first matching pricing rule for a server/tool pair."""
    for rule in rules:
        if rule.matches(server_name, tool_name):
            return rule.cost_per_call
    return 0.001


def aggregate_cost_rows(
    rows: list[dict[str, Any]],
    rules: list[CostRule],
) -> tuple[list[CostEntry], list[AgentCostEntry], list[SessionCostEntry]]:
    """Aggregate traced tool-call rows into tool, agent, and session cost views."""
    tool_totals: dict[tuple[str, str], CostEntry] = {}
    agent_totals: dict[str, AgentCostEntry] = {}
    session_totals: dict[tuple[str, str | None], SessionCostEntry] = {}

    for row in rows:
        server_name = str(row["server_name"])
        tool_name = str(row["tool_name"])
        agent_name = str(row.get("agent_name") or "unknown")
        raw_session_id = row.get("session_id")
        session_id = str(raw_session_id) if raw_session_id else None
        total_calls = int(row.get("total_calls") or 0)
        cost_per_call = find_cost_per_call(rules, server_name, tool_name)
        total_cost_usd = total_calls * cost_per_call

        tool_key = (server_name, tool_name)
        if tool_key not in tool_totals:
            tool_totals[tool_key] = CostEntry(
                server_name=server_name,
                tool_name=tool_name,
                total_calls=0,
                cost_per_call=cost_per_call,
                total_cost_usd=0.0,
            )
        tool_totals[tool_key].total_calls += total_calls
        tool_totals[tool_key].total_cost_usd += total_cost_usd

        if agent_name not in agent_totals:
            agent_totals[agent_name] = AgentCostEntry(
                agent_name=agent_name,
                total_calls=0,
                total_cost_usd=0.0,
            )
        agent_totals[agent_name].total_calls += total_calls
        agent_totals[agent_name].total_cost_usd += total_cost_usd

        if session_id:
            session_key = (session_id, row.get("agent_name"))
            if session_key not in session_totals:
                session_totals[session_key] = SessionCostEntry(
                    session_id=session_id,
                    agent_name=row.get("agent_name"),
                    total_calls=0,
                    total_cost_usd=0.0,
                )
            session_totals[session_key].total_calls += total_calls
            session_totals[session_key].total_cost_usd += total_cost_usd

    by_tool = sorted(tool_totals.values(), key=lambda entry: entry.total_cost_usd, reverse=True)
    by_agent = sorted(agent_totals.values(), key=lambda entry: entry.total_cost_usd, reverse=True)
    by_session = sorted(
        session_totals.values(),
        key=lambda entry: entry.total_cost_usd,
        reverse=True,
    )
    return by_tool, by_agent, by_session


def load_cost_rules(config_path: Path | None = None) -> list[CostRule]:
    """Load cost rules from .langsight.yaml costs.rules section."""
    search = [
        config_path,
        Path(".langsight.yaml"),
        Path(".langsight.yml"),
        Path("~/.langsight.yaml"),
    ]
    for path in search:
        if path is None:
            continue
        expanded = Path(path).expanduser()
        if expanded.exists():
            try:
                data = yaml.safe_load(expanded.read_text())
                raw_rules = data.get("costs", {}).get("rules", [])
                return [CostRule(**r) for r in raw_rules]
            except Exception:  # noqa: BLE001
                pass
    return [CostRule()]  # default rule
