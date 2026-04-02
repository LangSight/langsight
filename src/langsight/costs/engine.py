"""
Cost attribution engine — assigns dollar costs to agent tool calls and LLM usage.

Two cost types:
  1. Token-based (LLM spans): (input_tokens/1M × input_price) + (output_tokens/1M × output_price)
     Requires model_id + token counts on the span + model_pricing DB table.
  2. Call-based (MCP tool spans): cost_per_call from .langsight.yaml rules.

Pricing rules in .langsight.yaml (for call-based):
    costs:
      rules:
        - server: postgres-mcp
          tool: "*"
          cost_per_call: 0.0            # free self-hosted
        - server: "*"
          tool: "*"
          cost_per_call: 0.001          # $0.001 default

Model pricing is managed via the DB (Settings → Model Pricing) and seeded
with current public prices for major providers on first startup.
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
    cost_type: str = "call_based"  # "call_based" | "token_based"
    model_id: str | None = None  # set for token_based entries
    total_input_tokens: int = 0
    total_output_tokens: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "server_name": self.server_name,
            "tool_name": self.tool_name,
            "total_calls": self.total_calls,
            "cost_per_call_usd": self.cost_per_call,
            "total_cost_usd": round(self.total_cost_usd, 6),
            "cost_type": self.cost_type,
            "model_id": self.model_id,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
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


class ModelPricingLookup:
    """Fast in-memory lookup for model token pricing.

    Initialise once per request from the DB list.
    Falls back to $0 for unknown models (logs a warning).
    """

    def __init__(self, pricing_rows: list[Any]) -> None:
        # Index by model_id for O(1) lookup
        self._index: dict[str, Any] = {}
        for row in pricing_rows:
            model_id = row.model_id if hasattr(row, "model_id") else row.get("model_id", "")
            if model_id and (model_id not in self._index):  # keep first (most recent active)
                self._index[model_id] = row

    def cost_for(self, model_id: str, input_tokens: int, output_tokens: int) -> float:
        """Return total cost in USD for given token counts."""
        entry = self._index.get(model_id)
        if entry is None:
            return 0.0
        inp: float = (
            entry.input_per_1m_usd
            if hasattr(entry, "input_per_1m_usd")
            else entry.get("input_per_1m_usd", 0.0)
        )
        out: float = (
            entry.output_per_1m_usd
            if hasattr(entry, "output_per_1m_usd")
            else entry.get("output_per_1m_usd", 0.0)
        )
        return float((input_tokens / 1_000_000 * inp) + (output_tokens / 1_000_000 * out))

    def has_model(self, model_id: str) -> bool:
        return model_id in self._index


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
    model_pricing: ModelPricingLookup | None = None,
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

        # Token-based costing: use model pricing when model_id + tokens available
        row_model_id = str(row.get("model_id") or "").strip()
        raw_input = row.get("input_tokens")
        raw_output = row.get("output_tokens")
        input_tokens = int(raw_input) if raw_input is not None else None
        output_tokens = int(raw_output) if raw_output is not None else None

        use_token_pricing = (
            model_pricing is not None
            and row_model_id
            and model_pricing.has_model(row_model_id)
            and input_tokens is not None
            and output_tokens is not None
        )

        if use_token_pricing and model_pricing:
            # input_tokens / output_tokens come from SUM() in the ClickHouse query —
            # they already represent the total across all calls in this group.
            # cost_for() computes (tokens / 1M) * price, giving the total cost directly.
            # Do NOT multiply by total_calls — that would double-count.
            total_cost_usd = model_pricing.cost_for(
                row_model_id, input_tokens or 0, output_tokens or 0
            )
            cost_per_call = total_cost_usd / max(total_calls, 1)
            cost_type = "token_based"
        else:
            cost_per_call = find_cost_per_call(rules, server_name, tool_name)
            total_cost_usd = total_calls * cost_per_call
            cost_type = "call_based"
            row_model_id = ""
            input_tokens = None
            output_tokens = None

        tool_key = (server_name, tool_name)
        if tool_key not in tool_totals:
            tool_totals[tool_key] = CostEntry(
                server_name=server_name,
                tool_name=tool_name,
                total_calls=0,
                cost_per_call=cost_per_call,
                total_cost_usd=0.0,
                cost_type=cost_type,
                model_id=row_model_id or None,
                total_input_tokens=0,
                total_output_tokens=0,
            )
        tool_totals[tool_key].total_calls += total_calls
        tool_totals[tool_key].total_cost_usd += total_cost_usd
        if input_tokens is not None:
            tool_totals[tool_key].total_input_tokens += input_tokens * total_calls
        if output_tokens is not None:
            tool_totals[tool_key].total_output_tokens += output_tokens * total_calls

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
