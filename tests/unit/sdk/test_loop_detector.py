from __future__ import annotations

import pytest

from langsight.sdk.loop_detector import (
    LoopDetection,
    LoopDetector,
    LoopDetectorConfig,
    _hash_args,
)


@pytest.fixture
def config() -> LoopDetectorConfig:
    return LoopDetectorConfig(threshold=3, window_size=20)


@pytest.fixture
def detector(config: LoopDetectorConfig) -> LoopDetector:
    return LoopDetector(config)


class TestHashArgs:
    def test_none_returns_empty(self) -> None:
        assert _hash_args(None) == "empty"

    def test_empty_dict_returns_empty(self) -> None:
        assert _hash_args({}) == "empty"

    def test_deterministic(self) -> None:
        args = {"sql": "SELECT 1", "limit": 10}
        assert _hash_args(args) == _hash_args(args)

    def test_order_independent(self) -> None:
        a = {"b": 2, "a": 1}
        b = {"a": 1, "b": 2}
        assert _hash_args(a) == _hash_args(b)

    def test_different_args_different_hash(self) -> None:
        assert _hash_args({"x": 1}) != _hash_args({"x": 2})


class TestRepetitionDetection:
    def test_no_history_no_detection(self, detector: LoopDetector) -> None:
        result = detector.check_pre_call("query", {"sql": "SELECT 1"})
        assert result is None

    def test_below_threshold_no_detection(self, detector: LoopDetector) -> None:
        # Record 1 call, check for 2nd — threshold is 3, so no detection
        detector.record_call("query", {"sql": "SELECT 1"}, "success", None)
        result = detector.check_pre_call("query", {"sql": "SELECT 1"})
        assert result is None

    def test_at_threshold_detects_loop(self, detector: LoopDetector) -> None:
        args = {"sql": "SELECT 1"}
        # Record 2 calls, check for 3rd — threshold reached
        detector.record_call("query", args, "success", None)
        detector.record_call("query", args, "success", None)
        result = detector.check_pre_call("query", args)
        assert result is not None
        assert result.pattern == "repetition"
        assert result.loop_count == 3
        assert result.tool_name == "query"

    def test_different_tool_breaks_chain(self, detector: LoopDetector) -> None:
        args = {"sql": "SELECT 1"}
        detector.record_call("query", args, "success", None)
        detector.record_call("list_tables", {}, "success", None)
        detector.record_call("query", args, "success", None)
        result = detector.check_pre_call("query", args)
        # Only 1 consecutive at tail + proposed = 2, below threshold
        assert result is None

    def test_different_args_breaks_chain(self, detector: LoopDetector) -> None:
        detector.record_call("query", {"sql": "SELECT 1"}, "success", None)
        detector.record_call("query", {"sql": "SELECT 2"}, "success", None)
        detector.record_call("query", {"sql": "SELECT 1"}, "success", None)
        result = detector.check_pre_call("query", {"sql": "SELECT 1"})
        assert result is None


class TestPingPongDetection:
    def test_alternating_pattern_detected(self, detector: LoopDetector) -> None:
        # threshold=3: need A,B,A,B,A pattern (5 calls = 2*3-1)
        a_args = {"tool": "a"}
        b_args = {"tool": "b"}
        detector.record_call("tool_a", a_args, "success", None)
        detector.record_call("tool_b", b_args, "success", None)
        detector.record_call("tool_a", a_args, "success", None)
        detector.record_call("tool_b", b_args, "success", None)
        result = detector.check_pre_call("tool_a", a_args)
        assert result is not None
        assert result.pattern == "ping_pong"

    def test_non_alternating_not_detected(self, detector: LoopDetector) -> None:
        detector.record_call("tool_a", {"x": 1}, "success", None)
        detector.record_call("tool_b", {"x": 2}, "success", None)
        detector.record_call("tool_a", {"x": 1}, "success", None)
        detector.record_call("tool_c", {"x": 3}, "success", None)
        result = detector.check_pre_call("tool_a", {"x": 1})
        assert result is None

    def test_too_few_calls_not_detected(self, detector: LoopDetector) -> None:
        detector.record_call("tool_a", {"x": 1}, "success", None)
        detector.record_call("tool_b", {"x": 2}, "success", None)
        result = detector.check_pre_call("tool_a", {"x": 1})
        assert result is None


class TestRetryWithoutProgress:
    def test_same_error_repeated_detected(self, detector: LoopDetector) -> None:
        """Same tool, different args each time, same error → retry-without-progress."""
        err = "connection refused"
        # Varying args so repetition detection doesn't fire
        detector.record_call("query", {"sql": "SELECT 1"}, "error", err)
        detector.record_call("query", {"sql": "SELECT 2"}, "error", err)
        result = detector.check_pre_call("query", {"sql": "SELECT 3"})
        assert result is not None
        assert result.pattern == "retry_without_progress"
        assert result.loop_count == 3

    def test_different_errors_not_detected(self, detector: LoopDetector) -> None:
        """Different error messages break the retry chain."""
        detector.record_call("query", {"sql": "SELECT 1"}, "error", "error A")
        detector.record_call("query", {"sql": "SELECT 2"}, "error", "error B")
        result = detector.check_pre_call("query", {"sql": "SELECT 3"})
        assert result is None

    def test_success_between_errors_breaks_chain(
        self, detector: LoopDetector
    ) -> None:
        """A successful call in between resets the retry chain."""
        err = "timeout"
        detector.record_call("query", {"sql": "SELECT 1"}, "error", err)
        detector.record_call("query", {"sql": "SELECT 2"}, "success", None)
        detector.record_call("query", {"sql": "SELECT 3"}, "error", err)
        result = detector.check_pre_call("query", {"sql": "SELECT 4"})
        assert result is None


class TestWindowSliding:
    def test_old_calls_drop_off(self) -> None:
        config = LoopDetectorConfig(threshold=3, window_size=3)
        detector = LoopDetector(config)
        args = {"sql": "SELECT 1"}
        # Fill window with non-matching calls
        detector.record_call("other", {}, "success", None)
        detector.record_call("other", {}, "success", None)
        detector.record_call("other", {}, "success", None)
        # Now record matching calls — oldest "other" drops off each time
        detector.record_call("query", args, "success", None)
        detector.record_call("query", args, "success", None)
        # Window is now: [other, query, query] — proposed query = 3 consecutive? No.
        # Actually window is [other, query, query], tail check: 2 consecutive + 1 proposed = 3
        result = detector.check_pre_call("query", args)
        assert result is not None

    def test_recent_count(self, detector: LoopDetector) -> None:
        assert detector.recent_count == 0
        detector.record_call("query", {"sql": "X"}, "success", None)
        assert detector.recent_count == 1


class TestPriorityOrder:
    def test_repetition_detected_before_retry(
        self, detector: LoopDetector
    ) -> None:
        """When both repetition and retry patterns match, repetition wins."""
        err = "timeout"
        args = {"sql": "X"}
        detector.record_call("query", args, "error", err)
        detector.record_call("query", args, "error", err)
        result = detector.check_pre_call("query", args)
        # Both repetition and retry match — repetition is checked first
        assert result is not None
        assert result.pattern == "repetition"
