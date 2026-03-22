"""Adversarial and edge-case tests for v0.3 prevention exceptions.

Covers: exception pickling, repr/str formatting, catching via parent class,
boundary values, and unusual string inputs.
"""

from __future__ import annotations

import pickle

import pytest

from langsight.exceptions import (
    BudgetExceededError,
    CircuitBreakerOpenError,
    LangSightError,
    LoopDetectedError,
)


# ---------------------------------------------------------------------------
# LoopDetectedError edge cases
# ---------------------------------------------------------------------------


class TestLoopDetectedErrorEdgeCases:
    def test_empty_tool_name(self) -> None:
        err = LoopDetectedError("", 3, "abc", "repetition")
        assert err.tool_name == ""
        assert "''" in str(err)

    def test_zero_loop_count(self) -> None:
        err = LoopDetectedError("query", 0, "abc", "repetition")
        assert err.loop_count == 0
        assert "0" in str(err)

    def test_negative_loop_count(self) -> None:
        err = LoopDetectedError("query", -1, "abc", "repetition")
        assert err.loop_count == -1

    def test_empty_args_hash(self) -> None:
        err = LoopDetectedError("query", 3, "", "repetition")
        assert err.args_hash == ""

    def test_unicode_tool_name(self) -> None:
        err = LoopDetectedError("", 3, "abc", "repetition", "sess-1")
        assert err.tool_name == ""
        assert "" in str(err)

    def test_all_patterns(self) -> None:
        for pattern in ("repetition", "ping_pong", "retry_without_progress"):
            err = LoopDetectedError("query", 3, "abc", pattern)
            assert err.pattern == pattern
            assert pattern in str(err)

    def test_catchable_as_langsight_error(self) -> None:
        with pytest.raises(LangSightError):
            raise LoopDetectedError("query", 3, "abc", "repetition")

    def test_catchable_as_exception(self) -> None:
        with pytest.raises(Exception):
            raise LoopDetectedError("query", 3, "abc", "repetition")

    def test_pickle_roundtrip(self) -> None:
        """FIXED: __reduce__ implemented so exceptions survive pickle/unpickle.
        Required for multiprocessing and concurrent.futures.ProcessPoolExecutor."""
        err = LoopDetectedError("query", 3, "abc123", "ping_pong", "sess-1")
        pickled = pickle.dumps(err)
        restored = pickle.loads(pickled)
        assert restored.tool_name == err.tool_name
        assert restored.loop_count == err.loop_count
        assert restored.args_hash == err.args_hash
        assert restored.pattern == err.pattern
        assert restored.session_id == err.session_id
        assert str(restored) == str(err)

    def test_very_long_tool_name(self) -> None:
        long_name = "x" * 10_000
        err = LoopDetectedError(long_name, 3, "abc", "repetition")
        assert err.tool_name == long_name
        assert len(str(err)) > 10_000


# ---------------------------------------------------------------------------
# BudgetExceededError edge cases
# ---------------------------------------------------------------------------


class TestBudgetExceededErrorEdgeCases:
    def test_zero_limit_value(self) -> None:
        err = BudgetExceededError("max_steps", 0.0, 1.0)
        assert err.limit_value == 0.0
        assert "0.0" in str(err)

    def test_negative_actual_value(self) -> None:
        """Defensive: should not happen but should not crash."""
        err = BudgetExceededError("max_cost_usd", 1.0, -0.5)
        assert err.actual_value == -0.5

    def test_very_large_values(self) -> None:
        err = BudgetExceededError("max_cost_usd", 1e18, 1e18 + 1)
        assert err.limit_value == 1e18

    def test_float_precision_in_message(self) -> None:
        err = BudgetExceededError("max_cost_usd", 1.0, 1.03)
        msg = str(err)
        assert "1.03" in msg

    def test_all_limit_types(self) -> None:
        for limit_type in ("max_steps", "max_cost_usd", "max_wall_time_s"):
            err = BudgetExceededError(limit_type, 10.0, 11.0)
            assert err.limit_type == limit_type
            assert limit_type in str(err)

    def test_catchable_as_langsight_error(self) -> None:
        with pytest.raises(LangSightError):
            raise BudgetExceededError("max_steps", 10.0, 11.0)

    def test_pickle_roundtrip(self) -> None:
        """FIXED: __reduce__ implemented so exceptions survive pickle/unpickle."""
        err = BudgetExceededError("max_cost_usd", 1.0, 1.5, "sess-42")
        pickled = pickle.dumps(err)
        restored = pickle.loads(pickled)
        assert restored.limit_type == err.limit_type
        assert restored.limit_value == err.limit_value
        assert restored.actual_value == err.actual_value
        assert restored.session_id == err.session_id
        assert str(restored) == str(err)

    def test_equal_limit_and_actual(self) -> None:
        """When actual == limit, the error should still be valid."""
        err = BudgetExceededError("max_steps", 10.0, 10.0)
        assert err.limit_value == err.actual_value


# ---------------------------------------------------------------------------
# CircuitBreakerOpenError edge cases
# ---------------------------------------------------------------------------


class TestCircuitBreakerOpenErrorEdgeCases:
    def test_zero_cooldown(self) -> None:
        err = CircuitBreakerOpenError("srv", 0.0)
        assert err.cooldown_remaining_s == 0.0
        assert "0.0" in str(err)

    def test_negative_cooldown(self) -> None:
        """Should not happen but should not crash."""
        err = CircuitBreakerOpenError("srv", -5.0)
        assert err.cooldown_remaining_s == -5.0

    def test_very_large_cooldown(self) -> None:
        err = CircuitBreakerOpenError("srv", 1e10)
        assert err.cooldown_remaining_s == 1e10

    def test_empty_server_name(self) -> None:
        err = CircuitBreakerOpenError("", 10.0)
        assert err.server_name == ""
        assert "''" in str(err)

    def test_unicode_server_name(self) -> None:
        err = CircuitBreakerOpenError("", 10.0)
        assert err.server_name == ""

    def test_catchable_as_langsight_error(self) -> None:
        with pytest.raises(LangSightError):
            raise CircuitBreakerOpenError("srv", 10.0)

    def test_pickle_roundtrip(self) -> None:
        """FIXED: __reduce__ implemented so exceptions survive pickle/unpickle."""
        err = CircuitBreakerOpenError("my-server", 42.5)
        pickled = pickle.dumps(err)
        restored = pickle.loads(pickled)
        assert restored.server_name == err.server_name
        assert restored.cooldown_remaining_s == err.cooldown_remaining_s
        assert str(restored) == str(err)

    def test_message_formatting(self) -> None:
        err = CircuitBreakerOpenError("pg-mcp", 59.9)
        msg = str(err)
        assert "pg-mcp" in msg
        assert "59.9" in msg
        assert "cooldown" in msg.lower() or "remaining" in msg.lower()


# ---------------------------------------------------------------------------
# Cross-exception tests
# ---------------------------------------------------------------------------


class TestCrossExceptionBehavior:
    def test_all_prevention_errors_are_langsight_errors(self) -> None:
        errors = [
            LoopDetectedError("q", 3, "h", "rep"),
            BudgetExceededError("max_steps", 10, 11),
            CircuitBreakerOpenError("srv", 5.0),
        ]
        for err in errors:
            assert isinstance(err, LangSightError)

    def test_prevention_errors_are_not_each_other(self) -> None:
        """Verify no accidental inheritance between prevention errors."""
        loop = LoopDetectedError("q", 3, "h", "rep")
        budget = BudgetExceededError("max_steps", 10, 11)
        cb = CircuitBreakerOpenError("srv", 5.0)

        assert not isinstance(loop, type(budget))
        assert not isinstance(loop, type(cb))
        assert not isinstance(budget, type(cb))

    def test_catching_specific_before_generic(self) -> None:
        """Specific exceptions should be catchable before the base class."""
        try:
            raise LoopDetectedError("q", 3, "h", "rep")
        except LoopDetectedError:
            pass  # correctly caught specific
        except LangSightError:
            pytest.fail("Should have been caught by LoopDetectedError handler")

    def test_str_and_repr_do_not_raise(self) -> None:
        """str() and repr() should never raise on any prevention error."""
        errors = [
            LoopDetectedError("q", 3, "h", "rep", "sess"),
            BudgetExceededError("max_steps", 10, 11, "sess"),
            CircuitBreakerOpenError("srv", 5.0),
        ]
        for err in errors:
            assert isinstance(str(err), str)
            assert isinstance(repr(err), str)
