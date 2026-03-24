"""Thread-local pending tool calls — links wrap_llm() spans to wrap() spans.

When ``wrap_llm()`` processes an LLM response containing function_calls, it
registers each tool_call span_id here.  When ``wrap()`` → ``call_tool()``
executes the actual MCP call, it claims the pending entry as its
``parent_span_id``, creating a connected lineage::

    LLM agent span
      └── list_low_stock  (LLM intent, from wrap_llm)
           └── inventory/list_low_stock  (MCP execution, from wrap)

Thread-safe via ``threading.local()`` — each thread has its own dict.
Entries are consumed on claim (FIFO per tool name).
"""

from __future__ import annotations

import threading
from collections import defaultdict

_local = threading.local()


def _get_pending() -> dict[str, list[str]]:
    if not hasattr(_local, "pending"):
        _local.pending: dict[str, list[str]] = defaultdict(list)
    return _local.pending


def register_pending_tool(tool_name: str, span_id: str) -> None:
    """Called by wrap_llm() after emitting a function_call span."""
    _get_pending()[tool_name].append(span_id)


def claim_pending_tool(tool_name: str) -> str | None:
    """Called by wrap() call_tool() to find its parent span. FIFO order."""
    queue = _get_pending().get(tool_name)
    if queue:
        return queue.pop(0)
    return None
