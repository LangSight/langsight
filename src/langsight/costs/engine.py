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
        for rule in self._rules:
            if rule.matches(server_name, tool_name):
                return rule.cost_per_call
        return 0.001  # fallback default


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
