"""
tests/security/test_lru_dos_protection.py

Adversarial tests for the _LRUSet cache used in traces.py.

Security invariants proved by this file:

  1. OOM protection — an attacker flooding the cache with unique keys can never
     cause it to grow beyond _LRU_MAX entries.  Unbounded growth would exhaust
     process memory in long-running deployments.

  2. Legitimate-entry eviction order — flooding must not evict entries that were
     recently added by legitimate ingestion paths; the LRU policy evicts the
     OLDEST entry, so the N most-recently-added keys always survive.

  3. Correctness at boundary (maxsize=1) — the simplest possible cache validates
     that only the newest entry survives after every add().

  4. Concurrent-ish safety — interleaved add/contains on a single _LRUSet must
     not corrupt the underlying dict (no KeyError, no silent size overflow).
"""

from __future__ import annotations

import random
import threading

import pytest

pytestmark = [pytest.mark.security, pytest.mark.regression]


# ---------------------------------------------------------------------------
# Import the class under test.
# The import lives inside each test so that import failures surface clearly.
# ---------------------------------------------------------------------------


def _get_lru_set(maxsize: int = 2000):
    """Import and instantiate _LRUSet from traces router."""
    from langsight.api.routers.traces import _LRUSet

    return _LRUSet(maxsize)


# ---------------------------------------------------------------------------
# 1. OOM protection
# ---------------------------------------------------------------------------


class TestOomProtection:
    """Invariant: _LRUSet never exceeds maxsize entries regardless of input volume."""

    def test_100k_unique_keys_do_not_exceed_maxsize(self) -> None:
        """Flooding with 100 000 unique keys must not grow the set past 2000."""
        lru = _get_lru_set(2000)
        for i in range(100_000):
            lru.add(f"attacker-key-{i}")

        # Access the internal dict length — if the invariant holds, size <= maxsize.
        internal_size = len(lru._d)
        assert internal_size <= 2000, (
            f"_LRUSet grew to {internal_size} entries after 100k adds — "
            "memory exhaustion attack would succeed"
        )

    def test_size_does_not_exceed_maxsize_with_repeating_keys(self) -> None:
        """Adding the same small set of keys repeatedly must stay bounded."""
        lru = _get_lru_set(500)
        for i in range(10_000):
            lru.add(f"key-{i % 10}")  # only 10 unique keys, cycling

        assert len(lru._d) <= 500

    def test_size_never_exceeds_maxsize_during_mixed_add_discard(self) -> None:
        """add() and discard() interleaved must keep size at or below maxsize."""
        lru = _get_lru_set(100)
        for i in range(5_000):
            lru.add(f"key-{i}")
            if i % 3 == 0:
                lru.discard(f"key-{i - 1}")
            assert len(lru._d) <= 100, (
                f"Size exceeded maxsize at iteration {i}: {len(lru._d)}"
            )

    def test_exact_maxsize_boundary_is_honoured(self) -> None:
        """After adding exactly maxsize+1 unique keys, size equals maxsize."""
        maxsize = 50
        lru = _get_lru_set(maxsize)
        for i in range(maxsize + 1):
            lru.add(f"k{i}")
        assert len(lru._d) == maxsize


# ---------------------------------------------------------------------------
# 2. Legitimate-entry eviction order
# ---------------------------------------------------------------------------


class TestLegitimateEntryEviction:
    """Invariant: the last N keys added are always findable after an attacker flood."""

    def test_last_5_legitimate_keys_survive_flood(self) -> None:
        """The 5 most-recently-added legitimate keys must remain present after
        an attacker floods the cache with 10 000 unique keys.

        The LRU policy evicts the oldest entry, so keys added AFTER the flood
        will always be the newest and therefore must never be evicted.
        """
        lru = _get_lru_set(2000)

        # Attacker floods first
        for i in range(10_000):
            lru.add(f"attacker-{i}")

        # Legitimate code writes 5 entries after the flood
        legitimate_keys = [f"legit-{i}" for i in range(5)]
        for key in legitimate_keys:
            lru.add(key)

        for key in legitimate_keys:
            assert key in lru, (
                f"Legitimate key '{key}' was evicted — attacker could prevent "
                "agent metadata from being cached after the flood"
            )

    def test_entries_added_immediately_before_flood_may_be_evicted(self) -> None:
        """Entries added BEFORE a flood that saturates the cache CAN be evicted —
        this is expected LRU behaviour, not a security failure.  The test documents
        this explicitly so reviewers understand the boundary.
        """
        lru = _get_lru_set(10)  # tiny cache to make the effect obvious

        # Legitimate key added first
        lru.add("early-key")
        assert "early-key" in lru

        # Flood with more unique keys than maxsize
        for i in range(20):
            lru.add(f"later-key-{i}")

        # early-key is expected to be gone — this is the LRU contract
        # We assert this so the test catches any regression where eviction stops
        assert "early-key" not in lru, (
            "early-key should have been evicted by LRU — if it is still present, "
            "the eviction logic may have stopped working"
        )

    def test_move_to_end_on_contains_prevents_eviction(self) -> None:
        """Accessing a key via 'in' operator should move it to most-recently-used,
        preventing its eviction even when the cache is near-full.
        """
        lru = _get_lru_set(5)
        for i in range(5):
            lru.add(f"k{i}")

        # Access k0 — this moves it to end (most-recently-used)
        assert "k0" in lru  # __contains__ moves k0 to end

        # Now add one more unique key — this must evict k1 (oldest after k0 moved)
        lru.add("new-key")

        # k0 must still be present (it was recently accessed)
        assert "k0" in lru, "Accessed key was incorrectly evicted before stale keys"

        # k1 must be gone (it became the oldest after k0 moved to end)
        assert "k1" not in lru, "Expected k1 to be evicted (oldest after k0 moved)"


# ---------------------------------------------------------------------------
# 3. maxsize=1 boundary correctness
# ---------------------------------------------------------------------------


class TestMaxsizeOne:
    """Invariant: with maxsize=1, only the most recently added key is ever present."""

    def test_add_a_then_b_keeps_only_b(self) -> None:
        """add(A) then add(B) → only B must be present."""
        lru = _get_lru_set(1)
        lru.add("A")
        lru.add("B")

        assert "B" in lru, "Most-recently-added key B must be present"
        assert "A" not in lru, (
            "Old key A must have been evicted — maxsize=1 means only one entry"
        )
        assert len(lru._d) == 1

    def test_sequence_of_ten_adds_leaves_only_last(self) -> None:
        lru = _get_lru_set(1)
        for i in range(10):
            lru.add(f"key-{i}")

        assert "key-9" in lru
        assert len(lru._d) == 1
        # Verify all previous keys are gone
        for i in range(9):
            assert f"key-{i}" not in lru, f"key-{i} should have been evicted"

    def test_re_adding_same_key_to_maxsize_1_is_idempotent(self) -> None:
        lru = _get_lru_set(1)
        lru.add("same")
        lru.add("same")  # should not evict itself
        assert "same" in lru
        assert len(lru._d) == 1

    def test_discard_leaves_empty_cache(self) -> None:
        lru = _get_lru_set(1)
        lru.add("only-key")
        lru.discard("only-key")
        assert "only-key" not in lru
        assert len(lru._d) == 0


# ---------------------------------------------------------------------------
# 4. Concurrent simulation — structural integrity
# ---------------------------------------------------------------------------


class TestConcurrentSafety:
    """Invariant: interleaved add/contains from multiple threads must never
    corrupt the internal OrderedDict (no KeyError, no size overflow).

    CPython's GIL means the OrderedDict operations are effectively atomic at
    the bytecode level, so we are testing for logic errors rather than true
    data races.  The goal is to confirm that no combination of add/contains
    produces a KeyError or exceeds maxsize.
    """

    def test_interleaved_add_contains_no_keyerror(self) -> None:
        """Two threads doing concurrent add/contains must not raise KeyError."""
        lru = _get_lru_set(100)
        errors: list[Exception] = []

        def writer() -> None:
            for i in range(1_000):
                try:
                    lru.add(f"w-{i}")
                except Exception as exc:  # noqa: BLE001
                    errors.append(exc)

        def reader() -> None:
            for i in range(1_000):
                try:
                    _ = f"w-{i}" in lru
                except Exception as exc:  # noqa: BLE001
                    errors.append(exc)

        t1 = threading.Thread(target=writer)
        t2 = threading.Thread(target=reader)
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        assert not errors, (
            f"Concurrent add/contains raised exceptions: {errors}\n"
            "This indicates a structural corruption in _LRUSet"
        )

    def test_size_never_overflows_under_concurrent_adds(self) -> None:
        """Two writer threads must not collectively push the cache past maxsize."""
        maxsize = 200
        lru = _get_lru_set(maxsize)
        size_violations: list[int] = []

        def writer(prefix: str) -> None:
            for i in range(500):
                lru.add(f"{prefix}-{i}")
                current = len(lru._d)
                if current > maxsize:
                    size_violations.append(current)

        t1 = threading.Thread(target=writer, args=("alpha",))
        t2 = threading.Thread(target=writer, args=("beta",))
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        # Under CPython's GIL this must always hold.
        # A violation here would indicate a real bug in _LRUSet.add().
        assert not size_violations, (
            f"_LRUSet exceeded maxsize {maxsize} during concurrent writes: "
            f"observed sizes {size_violations[:5]}"
        )

    def test_random_interleaved_ops_no_structural_corruption(self) -> None:
        """Random mix of add, contains, and discard must not raise any exception."""
        lru = _get_lru_set(50)
        rng = random.Random(42)  # deterministic seed
        keys = [f"k{i}" for i in range(20)]
        errors: list[Exception] = []

        def worker() -> None:
            for _ in range(2_000):
                key = rng.choice(keys)
                op = rng.choice(["add", "contains", "discard"])
                try:
                    if op == "add":
                        lru.add(key)
                    elif op == "contains":
                        _ = key in lru
                    else:
                        lru.discard(key)
                except Exception as exc:  # noqa: BLE001
                    errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        assert not errors, (
            f"Random interleaved ops raised exceptions: {errors[:3]}"
        )
        assert len(lru._d) <= 50, (
            f"Cache exceeded maxsize after random ops: {len(lru._d)}"
        )
