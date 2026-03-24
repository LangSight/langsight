"""Adversarial and edge-case tests for the loop detector.

Targets degenerate configs (threshold=1, window_size=1), non-serializable
arguments, Unicode tool names, empty/None inputs, and mixed detection patterns.
"""

from __future__ import annotations

import datetime

from langsight.sdk.loop_detector import (
    LoopDetector,
    LoopDetectorConfig,
    _hash_args,
    _hash_error,
)

# ---------------------------------------------------------------------------
# threshold=1 — every call is a "loop"
# ---------------------------------------------------------------------------


class TestThresholdOne:
    """With threshold=1, every call should be flagged as a repetition
    since the *proposed* call alone meets the threshold (count=0 + 1 >= 1).
    """

    def test_first_call_is_detected_as_loop(self) -> None:
        config = LoopDetectorConfig(threshold=1, window_size=20)
        detector = LoopDetector(config)
        # No history at all, but threshold=1 means: 0 consecutive in history + 1 (proposed) >= 1
        result = detector.check_pre_call("query", {"sql": "SELECT 1"})
        assert result is not None
        assert result.pattern == "repetition"
        assert result.loop_count == 1

    def test_every_subsequent_call_also_detected(self) -> None:
        config = LoopDetectorConfig(threshold=1, window_size=20)
        detector = LoopDetector(config)
        detector.record_call("query", {"sql": "SELECT 1"}, "success", None)
        result = detector.check_pre_call("query", {"sql": "SELECT 2"})
        # Different args => no consecutive match, but still count + 1 = 0 + 1 = 1 >= 1
        assert result is not None
        assert result.loop_count == 1

    def test_different_tool_also_detected(self) -> None:
        config = LoopDetectorConfig(threshold=1, window_size=20)
        detector = LoopDetector(config)
        detector.record_call("query", {"sql": "SELECT 1"}, "success", None)
        result = detector.check_pre_call("list_tables", {})
        assert result is not None
        assert result.tool_name == "list_tables"


# ---------------------------------------------------------------------------
# window_size=1 — minimal window
# ---------------------------------------------------------------------------


class TestWindowSizeOne:
    """With window_size=1, only the most recent call is retained."""

    def test_single_call_in_window(self) -> None:
        config = LoopDetectorConfig(threshold=2, window_size=1)
        detector = LoopDetector(config)
        detector.record_call("query", {"x": 1}, "success", None)
        assert detector.recent_count == 1

    def test_window_overwrite(self) -> None:
        config = LoopDetectorConfig(threshold=2, window_size=1)
        detector = LoopDetector(config)
        detector.record_call("query", {"x": 1}, "success", None)
        detector.record_call("other", {"x": 2}, "success", None)
        assert detector.recent_count == 1  # oldest dropped

    def test_repetition_detectable_with_one_in_window(self) -> None:
        config = LoopDetectorConfig(threshold=2, window_size=1)
        detector = LoopDetector(config)
        detector.record_call("query", {"x": 1}, "success", None)
        result = detector.check_pre_call("query", {"x": 1})
        # 1 in window + 1 proposed = 2 >= threshold=2
        assert result is not None
        assert result.pattern == "repetition"
        assert result.loop_count == 2

    def test_ping_pong_impossible_with_window_one(self) -> None:
        """Ping-pong requires at least 2*(threshold-1) history items."""
        config = LoopDetectorConfig(threshold=2, window_size=1)
        detector = LoopDetector(config)
        detector.record_call("a", {"x": 1}, "success", None)
        # Ping-pong for threshold=2 needs 2*(2-1)=2 items; window only holds 1
        result = detector.check_pre_call("b", {"x": 2})
        # Should not detect ping-pong
        assert result is None or result.pattern != "ping_pong"


# ---------------------------------------------------------------------------
# Large arguments (1MB dict) — hash still works
# ---------------------------------------------------------------------------


class TestLargeArguments:
    def test_hash_large_dict(self) -> None:
        large_args = {"key_" + str(i): "x" * 1000 for i in range(1000)}
        h = _hash_args(large_args)
        assert isinstance(h, str)
        assert len(h) == 16  # sha256 hex[:16]

    def test_detection_with_large_args(self) -> None:
        large_args = {"data": "A" * 1_000_000}
        config = LoopDetectorConfig(threshold=2, window_size=5)
        detector = LoopDetector(config)
        detector.record_call("upload", large_args, "success", None)
        result = detector.check_pre_call("upload", large_args)
        assert result is not None
        assert result.pattern == "repetition"

    def test_large_args_deterministic(self) -> None:
        large_args = {"payload": list(range(10_000))}
        h1 = _hash_args(large_args)
        h2 = _hash_args(large_args)
        assert h1 == h2


# ---------------------------------------------------------------------------
# Non-serializable argument types (datetime, bytes, sets)
# ---------------------------------------------------------------------------


class TestNonSerializableArguments:
    """_hash_args uses json.dumps(default=str) as a fallback, so
    non-JSON-serializable types should still produce a deterministic hash.
    """

    def test_datetime_in_args(self) -> None:
        dt = datetime.datetime(2025, 6, 15, 12, 0, 0, tzinfo=datetime.UTC)
        args = {"timestamp": dt, "value": 42}
        h = _hash_args(args)
        assert isinstance(h, str)
        assert len(h) == 16

    def test_datetime_args_deterministic(self) -> None:
        dt = datetime.datetime(2025, 6, 15, 12, 0, 0, tzinfo=datetime.UTC)
        args = {"timestamp": dt}
        assert _hash_args(args) == _hash_args(args)

    def test_bytes_in_args(self) -> None:
        args = {"data": b"binary content"}
        h = _hash_args(args)
        assert isinstance(h, str)
        assert len(h) == 16

    def test_set_in_args(self) -> None:
        """Sets are not JSON-serializable but default=str should handle them."""
        args = {"tags": {1, 2, 3}}
        h = _hash_args(args)
        assert isinstance(h, str)

    def test_nested_non_serializable(self) -> None:
        args = {
            "obj": {
                "inner_dt": datetime.datetime.now(datetime.UTC),
                "inner_bytes": b"\x00\x01",
            }
        }
        h = _hash_args(args)
        assert isinstance(h, str)
        assert len(h) == 16

    def test_detection_with_non_serializable_args(self) -> None:
        """Non-serializable args should still allow loop detection to work."""
        dt = datetime.datetime(2025, 6, 15, tzinfo=datetime.UTC)
        args = {"when": dt, "what": "test"}
        config = LoopDetectorConfig(threshold=2, window_size=5)
        detector = LoopDetector(config)
        detector.record_call("schedule", args, "success", None)
        result = detector.check_pre_call("schedule", args)
        assert result is not None
        assert result.pattern == "repetition"


# ---------------------------------------------------------------------------
# Unicode tool names and arguments
# ---------------------------------------------------------------------------


class TestUnicodeToolNames:
    def test_unicode_tool_name(self) -> None:
        config = LoopDetectorConfig(threshold=2, window_size=10)
        detector = LoopDetector(config)
        detector.record_call("", {"key": "value"}, "success", None)
        result = detector.check_pre_call("", {"key": "value"})
        assert result is not None
        assert result.tool_name == ""
        assert result.pattern == "repetition"

    def test_emoji_in_tool_name(self) -> None:
        config = LoopDetectorConfig(threshold=2, window_size=10)
        detector = LoopDetector(config)
        detector.record_call("send_message", {"msg": "hello"}, "success", None)
        result = detector.check_pre_call("send_message", {"msg": "hello"})
        assert result is not None

    def test_unicode_in_arguments(self) -> None:
        args = {"greeting": "Hej, jag heter Anders", "emoji": ""}
        h = _hash_args(args)
        assert isinstance(h, str)
        assert len(h) == 16


# ---------------------------------------------------------------------------
# Empty tool name
# ---------------------------------------------------------------------------


class TestEmptyToolName:
    def test_empty_string_tool_name(self) -> None:
        config = LoopDetectorConfig(threshold=2, window_size=10)
        detector = LoopDetector(config)
        detector.record_call("", {"x": 1}, "success", None)
        result = detector.check_pre_call("", {"x": 1})
        assert result is not None
        assert result.tool_name == ""

    def test_empty_tool_name_does_not_confuse_other_tools(self) -> None:
        config = LoopDetectorConfig(threshold=3, window_size=10)
        detector = LoopDetector(config)
        detector.record_call("", {}, "success", None)
        detector.record_call("", {}, "success", None)
        detector.record_call("real_tool", {"x": 1}, "success", None)
        # "real_tool" should not trigger — chain was broken
        result = detector.check_pre_call("real_tool", {"x": 1})
        assert result is None


# ---------------------------------------------------------------------------
# None arguments throughout
# ---------------------------------------------------------------------------


class TestNoneArguments:
    def test_none_args_repetition(self) -> None:
        config = LoopDetectorConfig(threshold=2, window_size=10)
        detector = LoopDetector(config)
        detector.record_call("query", None, "success", None)
        result = detector.check_pre_call("query", None)
        assert result is not None
        assert result.pattern == "repetition"
        assert result.args_hash == "empty"

    def test_none_and_empty_dict_are_equivalent(self) -> None:
        """Both None and {} should produce the same "empty" hash."""
        assert _hash_args(None) == _hash_args({})

    def test_none_args_do_not_match_non_empty_args(self) -> None:
        config = LoopDetectorConfig(threshold=2, window_size=10)
        detector = LoopDetector(config)
        detector.record_call("query", None, "success", None)
        result = detector.check_pre_call("query", {"sql": "SELECT 1"})
        assert result is None  # different hashes, no repetition


# ---------------------------------------------------------------------------
# Mixed patterns: partial ping-pong followed by repetition
# ---------------------------------------------------------------------------


class TestMixedPatterns:
    def test_partial_ping_pong_then_repetition(self) -> None:
        """Start an A-B alternation but then switch to pure repetition."""
        config = LoopDetectorConfig(threshold=3, window_size=20)
        detector = LoopDetector(config)
        # A, B, A, B (partial ping-pong)
        detector.record_call("tool_a", {"x": 1}, "success", None)
        detector.record_call("tool_b", {"x": 2}, "success", None)
        detector.record_call("tool_a", {"x": 1}, "success", None)
        detector.record_call("tool_b", {"x": 2}, "success", None)
        # Now switch to pure repetition: C, C, C
        detector.record_call("tool_c", {"x": 3}, "success", None)
        detector.record_call("tool_c", {"x": 3}, "success", None)
        result = detector.check_pre_call("tool_c", {"x": 3})
        assert result is not None
        assert result.pattern == "repetition"
        assert result.tool_name == "tool_c"

    def test_retry_errors_then_repetition_succeeds(self) -> None:
        """Errors with same tool, then success repetition. Repetition should win."""
        config = LoopDetectorConfig(threshold=3, window_size=20)
        detector = LoopDetector(config)
        # 2 errors (below threshold for retry_without_progress)
        detector.record_call("query", {"sql": "A"}, "error", "timeout")
        # Then switch to successful repetition with same tool+args
        detector.record_call("query", {"sql": "B"}, "success", None)
        detector.record_call("query", {"sql": "B"}, "success", None)
        result = detector.check_pre_call("query", {"sql": "B"})
        assert result is not None
        assert result.pattern == "repetition"

    def test_ping_pong_detected_at_exact_threshold(self) -> None:
        """Verify ping-pong fires when history has exactly 2*(threshold-1) items."""
        config = LoopDetectorConfig(threshold=2, window_size=20)
        detector = LoopDetector(config)
        # threshold=2 => need 2*(2-1)=2 items in history: [A, B], proposed=A
        detector.record_call("a", {"x": 1}, "success", None)
        detector.record_call("b", {"x": 2}, "success", None)
        result = detector.check_pre_call("a", {"x": 1})
        assert result is not None
        assert result.pattern == "ping_pong"

    def test_ping_pong_not_detected_when_last_matches_proposed(self) -> None:
        """If the last call matches the proposed call, it is repetition not ping-pong."""
        config = LoopDetectorConfig(threshold=3, window_size=20)
        detector = LoopDetector(config)
        detector.record_call("a", {"x": 1}, "success", None)
        detector.record_call("b", {"x": 2}, "success", None)
        detector.record_call("a", {"x": 1}, "success", None)
        detector.record_call("a", {"x": 1}, "success", None)  # last == proposed
        result = detector.check_pre_call("a", {"x": 1})
        # Last record is same as proposed => _check_ping_pong returns None
        # But repetition should fire: 2 consecutive + 1 proposed = 3 >= threshold
        assert result is not None
        assert result.pattern == "repetition"


# ---------------------------------------------------------------------------
# _hash_error edge cases
# ---------------------------------------------------------------------------


class TestHashError:
    def test_none_error_returns_none(self) -> None:
        assert _hash_error(None) is None

    def test_empty_string_error_returns_none(self) -> None:
        assert _hash_error("") is None

    def test_non_empty_error_returns_hash(self) -> None:
        h = _hash_error("connection refused")
        assert h is not None
        assert isinstance(h, str)
        assert len(h) == 16

    def test_same_error_same_hash(self) -> None:
        h1 = _hash_error("timeout after 5s")
        h2 = _hash_error("timeout after 5s")
        assert h1 == h2

    def test_different_error_different_hash(self) -> None:
        h1 = _hash_error("error A")
        h2 = _hash_error("error B")
        assert h1 != h2


# ---------------------------------------------------------------------------
# retry_without_progress edge cases
# ---------------------------------------------------------------------------


class TestRetryWithoutProgressEdgeCases:
    def test_requires_at_least_one_recorded_error(self) -> None:
        """retry_without_progress needs count >= 1 in history
        so that count+1 >= threshold and count >= 1.
        """
        config = LoopDetectorConfig(threshold=2, window_size=20)
        detector = LoopDetector(config)
        # No history => count=0, 0+1=1 >= 2? No, and count < 1 check fails
        result = detector.check_pre_call("query", {"x": 1})
        assert result is None

    def test_single_error_at_threshold_two(self) -> None:
        """With threshold=2 and one recorded error: count=1, 1+1=2 >= 2 and 1 >= 1."""
        config = LoopDetectorConfig(threshold=2, window_size=20)
        detector = LoopDetector(config)
        detector.record_call("query", {"sql": "A"}, "error", "timeout")
        result = detector.check_pre_call("query", {"sql": "B"})
        assert result is not None
        assert result.pattern == "retry_without_progress"

    def test_success_status_does_not_count(self) -> None:
        """A success call breaks the retry chain even with the same tool name."""
        config = LoopDetectorConfig(threshold=3, window_size=20)
        detector = LoopDetector(config)
        detector.record_call("query", {"sql": "A"}, "error", "timeout")
        detector.record_call("query", {"sql": "B"}, "success", None)
        detector.record_call("query", {"sql": "C"}, "error", "timeout")
        result = detector.check_pre_call("query", {"sql": "D"})
        # Only 1 consecutive error at tail, 1+1=2 < 3
        assert result is None

    def test_error_with_no_error_message_does_not_count(self) -> None:
        """An error-status call with None error_hash should not match."""
        config = LoopDetectorConfig(threshold=2, window_size=20)
        detector = LoopDetector(config)
        detector.record_call("query", {"sql": "A"}, "error", None)
        result = detector.check_pre_call("query", {"sql": "B"})
        # error_hash is None => the record loop's condition fails
        assert result is None


# ---------------------------------------------------------------------------
# Window overflow behavior
# ---------------------------------------------------------------------------


class TestWindowOverflow:
    """When more calls are recorded than window_size, oldest are dropped."""

    def test_old_repetitions_forgotten(self) -> None:
        config = LoopDetectorConfig(threshold=3, window_size=3)
        detector = LoopDetector(config)
        # Fill with matching calls
        detector.record_call("q", {"x": 1}, "success", None)
        detector.record_call("q", {"x": 1}, "success", None)
        # Window: [q, q]. Now add a different call to push one out
        detector.record_call("other", {}, "success", None)
        # Window: [q, other] — only 0 consecutive "q" at tail
        result = detector.check_pre_call("q", {"x": 1})
        assert result is None

    def test_window_filled_exactly(self) -> None:
        config = LoopDetectorConfig(threshold=3, window_size=3)
        detector = LoopDetector(config)
        detector.record_call("q", {"x": 1}, "success", None)
        detector.record_call("q", {"x": 1}, "success", None)
        detector.record_call("q", {"x": 1}, "success", None)
        assert detector.recent_count == 3
        # 3 in window + 1 proposed = 4 >= 3
        result = detector.check_pre_call("q", {"x": 1})
        assert result is not None
        assert result.loop_count == 4
