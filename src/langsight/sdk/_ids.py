"""Internal session ID generation — not part of the public API.

All session IDs issued by LangSight use this single function.
Format: uuid4().hex — 32 hex chars, no dashes, URL-safe, no prefix.

Callers (wrap(), set_context(), etc.) call _new_session_id() when no
session_id is supplied. Sub-agents forward the ID they receive from the
orchestrator — they never construct a new one themselves.
"""

from __future__ import annotations

import uuid


def _new_session_id() -> str:
    return uuid.uuid4().hex
