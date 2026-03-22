"""
Loop detector — detects agent loops before they burn tokens and time.

Detection patterns:
  1. Repetition:             same tool + same args repeated N times
  2. Ping-pong:              alternating between two tool+args pairs
  3. Retry-without-progress: same tool + same error repeated N times
"""

from __future__ import annotations

import hashlib
import json
from collections import deque
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal

import structlog
from pydantic import BaseModel

logger = structlog.get_logger()


class LoopAction(StrEnum):
    WARN = "warn"
    TERMINATE = "terminate"


class LoopDetectorConfig(BaseModel, frozen=True):
    """Immutable loop detector configuration."""

    threshold: int = 3
    action: LoopAction = LoopAction.TERMINATE
    window_size: int = 20


@dataclass(frozen=True)
class LoopDetection:
    """Result when a loop pattern is detected."""

    pattern: Literal["repetition", "ping_pong", "retry_without_progress"]
    tool_name: str
    loop_count: int
    args_hash: str


@dataclass(frozen=True)
class _CallRecord:
    """Internal record of a completed tool call."""

    tool_name: str
    args_hash: str
    status: str
    error_hash: str | None


def _hash_args(arguments: dict[str, Any] | None) -> str:
    """Deterministic hash of tool arguments for comparison."""
    if not arguments:
        return "empty"
    try:
        canonical = json.dumps(arguments, sort_keys=True, default=str)
    except (TypeError, ValueError):
        canonical = str(arguments)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def _hash_error(error: str | None) -> str | None:
    """Hash an error message for comparison (ignoring timestamps etc.)."""
    if not error:
        return None
    return hashlib.sha256(error.encode()).hexdigest()[:16]


class LoopDetector:
    """Per-session loop detection engine.

    Maintains a sliding window of recent tool calls and checks for
    repetitive patterns before each new call.
    """

    def __init__(self, config: LoopDetectorConfig) -> None:
        self._config = config
        self._recent: deque[_CallRecord] = deque(maxlen=config.window_size)

    @property
    def recent_count(self) -> int:
        return len(self._recent)

    def check_pre_call(
        self, tool_name: str, arguments: dict[str, Any] | None
    ) -> LoopDetection | None:
        """Pre-call check: would this call create a loop?

        Returns a LoopDetection if a pattern is found, None otherwise.
        """
        args_hash = _hash_args(arguments)

        # Check repetition: same tool+args repeated at tail of window
        detection = self._check_repetition(tool_name, args_hash)
        if detection:
            return detection

        # Check ping-pong: alternating between two tool+args pairs
        detection = self._check_ping_pong(tool_name, args_hash)
        if detection:
            return detection

        # Check retry-without-progress: same tool+error at tail
        detection = self._check_retry_without_progress(tool_name, args_hash)
        if detection:
            return detection

        return None

    def record_call(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None,
        status: str,
        error: str | None,
    ) -> None:
        """Post-call: record the completed call in the sliding window."""
        self._recent.append(
            _CallRecord(
                tool_name=tool_name,
                args_hash=_hash_args(arguments),
                status=status,
                error_hash=_hash_error(error),
            )
        )

    def _check_repetition(
        self, tool_name: str, args_hash: str
    ) -> LoopDetection | None:
        """Count consecutive identical calls at the tail of the window."""
        count = 0
        for record in reversed(self._recent):
            if record.tool_name == tool_name and record.args_hash == args_hash:
                count += 1
            else:
                break

        # +1 because the proposed call would be the next repetition
        if count + 1 >= self._config.threshold:
            return LoopDetection(
                pattern="repetition",
                tool_name=tool_name,
                loop_count=count + 1,
                args_hash=args_hash,
            )
        return None

    def _check_ping_pong(
        self, tool_name: str, args_hash: str
    ) -> LoopDetection | None:
        """Detect alternating A→B→A→B→A pattern.

        For threshold=3: history must be [A,B,A,B] and proposed is A.
        That's 2*(threshold-1) = 4 calls in history, plus the proposed call.
        """
        min_history = 2 * (self._config.threshold - 1)
        if len(self._recent) < min_history:
            return None

        tail = list(self._recent)[-min_history:]
        proposed_key = (tool_name, args_hash)

        # Last call must differ from proposed (it's the "other" in the pair)
        other_key = (tail[-1].tool_name, tail[-1].args_hash)
        if other_key == proposed_key:
            return None

        # Check alternating pattern from oldest to newest:
        # even indices = proposed_key, odd indices = other_key
        for i, record in enumerate(tail):
            record_key = (record.tool_name, record.args_hash)
            expected_key = proposed_key if i % 2 == 0 else other_key
            if record_key != expected_key:
                return None

        return LoopDetection(
            pattern="ping_pong",
            tool_name=tool_name,
            loop_count=self._config.threshold,
            args_hash=args_hash,
        )

    def _check_retry_without_progress(
        self, tool_name: str, args_hash: str
    ) -> LoopDetection | None:
        """Detect same tool failing with the same error repeatedly."""
        # Count consecutive errors with same tool+error at tail
        count = 0
        error_hash: str | None = None
        for record in reversed(self._recent):
            if (
                record.tool_name == tool_name
                and record.status != "success"
                and record.error_hash is not None
            ):
                if error_hash is None:
                    error_hash = record.error_hash
                if record.error_hash == error_hash:
                    count += 1
                else:
                    break
            else:
                break

        # +1 because this proposed retry would be the next attempt
        if count + 1 >= self._config.threshold and count >= 1:
            return LoopDetection(
                pattern="retry_without_progress",
                tool_name=tool_name,
                loop_count=count + 1,
                args_hash=args_hash,
            )
        return None
