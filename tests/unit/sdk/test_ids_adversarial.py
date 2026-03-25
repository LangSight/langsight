"""
Adversarial tests for _new_session_id().

Security invariants:
- Every call returns exactly 32 lowercase hex characters (uuid4().hex format)
- No dashes, no prefix, never empty
- 10 000 consecutive calls produce 10 000 distinct values (collision-free at scale)
- The function is not a constant — it generates a fresh ID each call, so two
  successive calls never return the same string
"""

from __future__ import annotations

import re

import pytest

from langsight.sdk._ids import _new_session_id

pytestmark = pytest.mark.security

_HEX_RE = re.compile(r"^[0-9a-f]{32}$")

_CALL_COUNT = 10_000


class TestSessionIdFormat:
    """Every ID must be exactly 32 lowercase hex chars — no dashes, no prefix, not empty."""

    def test_returns_string(self) -> None:
        assert isinstance(_new_session_id(), str)

    def test_length_is_32(self) -> None:
        for _ in range(20):
            assert len(_new_session_id()) == 32

    def test_no_dashes(self) -> None:
        for _ in range(20):
            assert "-" not in _new_session_id()

    def test_no_prefix(self) -> None:
        """IDs must not carry an application-specific prefix."""
        for _ in range(20):
            raw = _new_session_id()
            # hex string starts immediately — no letter-word prefix like "sid-" or "ls_"
            assert _HEX_RE.match(raw), f"ID {raw!r} is not pure 32-char lowercase hex"

    def test_only_lowercase_hex_chars(self) -> None:
        for _ in range(100):
            raw = _new_session_id()
            assert _HEX_RE.match(raw), f"ID contains non-hex or uppercase chars: {raw!r}"

    def test_never_empty_string(self) -> None:
        for _ in range(20):
            assert _new_session_id() != ""

    def test_never_none(self) -> None:
        for _ in range(20):
            assert _new_session_id() is not None

    def test_not_all_zeros(self) -> None:
        """A constant all-zero string would indicate a broken UUID source."""
        for _ in range(20):
            assert _new_session_id() != "0" * 32

    def test_not_all_same_character(self) -> None:
        """Sanity check — a degenerate RNG returning repeated chars should fail."""
        for _ in range(50):
            raw = _new_session_id()
            assert len(set(raw)) > 1, f"All characters are identical: {raw!r}"


class TestSessionIdUniqueness:
    """Two successive calls must never return the same value; 10k calls must be collision-free."""

    def test_two_successive_calls_differ(self) -> None:
        """The function is not a constant — each call generates a fresh UUID4."""
        first = _new_session_id()
        second = _new_session_id()
        assert first != second, "Two successive calls returned the same session ID"

    def test_ten_calls_all_unique(self) -> None:
        ids = [_new_session_id() for _ in range(10)]
        assert len(set(ids)) == 10, "Collision detected in 10 consecutive calls"

    def test_ten_thousand_calls_no_collision(self) -> None:
        """10 000 IDs with no repeats — verifies uuid4 entropy is wired correctly.

        If _new_session_id() were a counter, timestamp, or seeded RNG with a
        short period, this test would catch it.
        """
        ids = [_new_session_id() for _ in range(_CALL_COUNT)]
        unique = set(ids)
        collision_count = _CALL_COUNT - len(unique)
        assert collision_count == 0, (
            f"{collision_count} collision(s) found in {_CALL_COUNT} generated IDs"
        )

    def test_ids_are_not_sequential(self) -> None:
        """Sequential IDs (e.g. 0, 1, 2 ...) are predictable and insecure.

        Checks that converting pairs of IDs to integers and diffing them
        does not reveal a constant stride — which would indicate a counter.
        """
        ids = [_new_session_id() for _ in range(10)]
        as_ints = [int(i, 16) for i in ids]
        diffs = [abs(as_ints[n + 1] - as_ints[n]) for n in range(len(as_ints) - 1)]
        # All diffs equal means a counter — extremely unlikely for uuid4
        assert len(set(diffs)) > 1, "IDs appear to be sequential (constant diff)"
