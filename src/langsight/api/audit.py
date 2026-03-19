"""Shared audit log helper — fire-and-forget persistent audit writes.

All admin mutation endpoints should call ``append_audit()`` alongside their
existing structlog calls. The helper schedules an async DB write via
``storage.append_audit_log()`` without blocking the request.
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any


def append_audit(
    event: str,
    user_id: str | None,
    ip: str | None,
    details: dict[str, Any] | None = None,
    *,
    storage: Any = None,
) -> None:
    """Append an event to the persistent audit log.

    When ``storage`` is provided (a StorageBackend instance), the event is
    written to the ``audit_logs`` table. This is fire-and-forget — it
    schedules an async task rather than blocking the caller.
    """
    fn = getattr(storage, "append_audit_log", None)
    if fn is None or not inspect.iscoroutinefunction(fn):
        return

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(
            fn(
                event,
                user_id or "system",
                ip or "unknown",
                details or {},
            )
        )
    except RuntimeError:
        pass  # No running loop (e.g. called during shutdown) — skip
