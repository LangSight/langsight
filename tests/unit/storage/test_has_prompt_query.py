"""Unit tests for the has_prompt field returned by ClickHouseBackend.get_agent_sessions.

The ClickHouse client is mocked — no running ClickHouse instance needed.
The has_prompt column is position 14 in the cols list defined in get_agent_sessions.
Tests verify True/False/missing-column scenarios.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from langsight.storage.clickhouse import ClickHouseBackend


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_COLS = [
    "session_id",
    "agent_name",
    "first_call_at",
    "last_call_at",
    "tool_calls",
    "failed_calls",
    "total_latency_ms",
    "servers_used",
    "duration_ms",
    "health_tag",
    "total_input_tokens",
    "total_output_tokens",
    "model_id",
    "agents_used",
    "has_prompt",  # index 14
]


def _make_row(has_prompt_value: object = True) -> tuple:
    """Return a minimal result_row with every column populated."""
    return (
        "sess-abc",       # session_id
        "support-agent",  # agent_name
        "2026-04-01T10:00:00",  # first_call_at
        "2026-04-01T10:00:05",  # last_call_at
        5,                # tool_calls
        1,                # failed_calls
        680.0,            # total_latency_ms
        ["jira-mcp"],     # servers_used
        5000.0,           # duration_ms
        None,             # health_tag
        100,              # total_input_tokens
        200,              # total_output_tokens
        "claude-3-5-sonnet-20241022",  # model_id
        ["support-agent"],  # agents_used
        has_prompt_value,  # has_prompt (index 14)
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_client() -> MagicMock:
    client = MagicMock()
    client.command = AsyncMock()
    client.insert = AsyncMock()
    client.close = AsyncMock()

    mock_result = MagicMock()
    mock_result.result_rows = []
    client.query = AsyncMock(return_value=mock_result)
    return client


@pytest.fixture
def backend(mock_client: MagicMock) -> ClickHouseBackend:
    return ClickHouseBackend(mock_client)


# ---------------------------------------------------------------------------
# TestHasPromptField
# ---------------------------------------------------------------------------


class TestHasPromptField:
    """Verify has_prompt is correctly mapped from ClickHouse result rows."""

    @pytest.mark.asyncio
    async def test_has_prompt_true_when_session_span_present(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        """Row where has_prompt is truthy (1 or True) → returned dict has has_prompt=True."""
        mock_client.query.return_value.result_rows = [_make_row(has_prompt_value=True)]
        rows = await backend.get_agent_sessions()
        assert len(rows) == 1
        assert rows[0]["has_prompt"] is True

    @pytest.mark.asyncio
    async def test_has_prompt_true_from_integer_one(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        """ClickHouse countIf(...) > 0 returns an integer — 1 must map to True."""
        mock_client.query.return_value.result_rows = [_make_row(has_prompt_value=1)]
        rows = await backend.get_agent_sessions()
        assert bool(rows[0]["has_prompt"]) is True

    @pytest.mark.asyncio
    async def test_has_prompt_false_when_no_session_span(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        """Row where has_prompt is falsy (0 or False) → returned dict has has_prompt=False."""
        mock_client.query.return_value.result_rows = [_make_row(has_prompt_value=False)]
        rows = await backend.get_agent_sessions()
        assert len(rows) == 1
        assert bool(rows[0]["has_prompt"]) is False

    @pytest.mark.asyncio
    async def test_has_prompt_false_from_integer_zero(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        """countIf(...) > 0 returning 0 must map to a falsy has_prompt."""
        mock_client.query.return_value.result_rows = [_make_row(has_prompt_value=0)]
        rows = await backend.get_agent_sessions()
        assert bool(rows[0]["has_prompt"]) is False

    @pytest.mark.asyncio
    async def test_has_prompt_defaults_false_when_column_missing(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        """Older rows without has_prompt column produce has_prompt=False via .get() fallback.

        The storage layer uses dict(zip(cols, row, strict=False)) which stops
        at the shorter of cols and row, so a short row simply omits the key.
        The API then uses r.get("has_prompt", False) to default gracefully.
        """
        # Build a row that is missing the last column (has_prompt)
        short_row = _make_row(has_prompt_value=True)[:-1]  # drop has_prompt
        mock_client.query.return_value.result_rows = [short_row]
        rows = await backend.get_agent_sessions()
        assert len(rows) == 1
        # Key should be absent (zip(strict=False) stops at shorter sequence)
        assert rows[0].get("has_prompt", False) is False

    @pytest.mark.asyncio
    async def test_multiple_sessions_have_independent_has_prompt(
        self, backend: ClickHouseBackend, mock_client: MagicMock
    ) -> None:
        """Each session row gets its own has_prompt value — no cross-contamination."""
        mock_client.query.return_value.result_rows = [
            _make_row(has_prompt_value=True),
            _make_row(has_prompt_value=False),
        ]
        rows = await backend.get_agent_sessions()
        assert len(rows) == 2
        assert bool(rows[0]["has_prompt"]) is True
        assert bool(rows[1]["has_prompt"]) is False
