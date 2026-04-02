"""
Unit tests for _LRUSet — the bounded LRU set used in the traces router.

All six behaviours pinned by the task specification:
  1. __contains__ promotes key to MRU on hit
  2. add evicts oldest entry when at capacity
  3. add promotes an existing key (no duplicate)
  4. discard removes key silently
  5. After 2001 add calls on a max-2000 set, only 2000 entries remain
  6. Most-recently-used key is NOT evicted when at capacity
"""

from __future__ import annotations

import pytest

from langsight.api.routers.traces import _LRUSet

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _filled_set(size: int) -> _LRUSet:
    """Return a maxsize=*size* set with keys '0' … str(size-1) added in order."""
    s = _LRUSet(size)
    for i in range(size):
        s.add(str(i))
    return s


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestLRUSetConstruction:
    def test_empty_set_contains_nothing(self) -> None:
        s = _LRUSet(10)
        assert "a" not in s

    def test_maxsize_is_respected(self) -> None:
        s = _filled_set(5)
        # Adding one more should evict the oldest, keeping total at 5
        s.add("new")
        count = sum(1 for k in ["0", "1", "2", "3", "4", "new"] if k in s)
        assert count == 5


# ---------------------------------------------------------------------------
# 1. __contains__ promotes key to MRU on hit
# ---------------------------------------------------------------------------


class TestContainsPromotesToMRU:
    def test_contains_returns_true_for_present_key(self) -> None:
        s = _LRUSet(5)
        s.add("x")
        assert "x" in s

    def test_contains_returns_false_for_absent_key(self) -> None:
        s = _LRUSet(5)
        assert "absent" not in s

    def test_contains_promotes_key_so_it_survives_eviction(self) -> None:
        """After a __contains__ hit the key becomes MRU and must not be evicted next."""
        # Fill a set of size 3 with '0', '1', '2' (oldest → newest)
        s = _LRUSet(3)
        s.add("0")
        s.add("1")
        s.add("2")

        # Access '0' — it should become MRU
        assert "0" in s  # promotes '0' to end

        # Now add '3', which must evict the oldest entry still in order
        # After promotion '0' is newest; order is '1', '2', '0' → oldest is '1'
        s.add("3")

        assert "0" in s, "'0' was promoted to MRU and must survive eviction"
        assert "3" in s, "newly added key must be present"
        assert "1" not in s, "'1' was the oldest after promotion of '0'; must be evicted"

    def test_repeated_contains_keeps_key_alive(self) -> None:
        """Touching the same key repeatedly keeps it alive across many additions."""
        s = _LRUSet(3)
        s.add("anchor")
        for i in range(10):
            s.add(f"filler-{i}")
            _ = "anchor" in s  # keep promoting

        assert "anchor" in s


# ---------------------------------------------------------------------------
# 2. add evicts oldest entry when at capacity
# ---------------------------------------------------------------------------


class TestAddEvictsOldest:
    def test_add_evicts_oldest_when_full(self) -> None:
        s = _LRUSet(3)
        s.add("alpha")  # oldest
        s.add("beta")
        s.add("gamma")  # newest

        s.add("delta")  # should evict 'alpha'

        assert "alpha" not in s
        assert "beta" in s
        assert "gamma" in s
        assert "delta" in s

    def test_size_never_exceeds_maxsize(self) -> None:
        s = _LRUSet(5)
        for i in range(20):
            s.add(str(i))
        present = sum(1 for i in range(20) if str(i) in s)
        assert present == 5

    def test_add_on_empty_set_does_not_evict(self) -> None:
        s = _LRUSet(3)
        s.add("first")
        assert "first" in s

    def test_consecutive_evictions_follow_fifo_order(self) -> None:
        """Keys added earliest are evicted first — FIFO among same-touch-count keys."""
        s = _LRUSet(3)
        s.add("a")
        s.add("b")
        s.add("c")

        s.add("d")  # evict 'a'
        assert "a" not in s

        s.add("e")  # evict 'b'
        assert "b" not in s

        s.add("f")  # evict 'c'
        assert "c" not in s


# ---------------------------------------------------------------------------
# 3. add promotes existing key (no duplicate)
# ---------------------------------------------------------------------------


class TestAddPromotesExisting:
    def test_adding_existing_key_does_not_create_duplicate(self) -> None:
        s = _LRUSet(5)
        s.add("k")
        s.add("k")
        # The key must still be present but count must stay consistent:
        # after a second add it should survive the next eviction pass.
        assert "k" in s

    def test_adding_existing_key_makes_it_mru(self) -> None:
        """Re-adding an existing key must move it to MRU, preventing eviction.

        Set of size 3 filled with '0','1','2' (order oldest→newest).
        Re-adding '0' makes it MRU → order becomes '1','2','0'.
        Adding '3' (4th unique key, triggers eviction) must evict '1' not '0'.
        """
        s = _LRUSet(3)
        s.add("0")   # order: 0
        s.add("1")   # order: 0, 1
        s.add("2")   # order: 0, 1, 2  — set is now full
        s.add("0")   # re-add '0' — now MRU; order: 1, 2, 0

        # Adding '3' triggers eviction of the current oldest, which is '1'
        s.add("3")

        assert "0" in s, "'0' was re-added (MRU) and must survive"
        assert "2" in s, "'2' was not touched and must survive"
        assert "3" in s, "newly added key must be present"
        assert "1" not in s, "'1' is the oldest after '0' was promoted; must be evicted"

    def test_set_stays_at_maxsize_after_re_add(self) -> None:
        s = _LRUSet(3)
        s.add("x")
        s.add("y")
        s.add("z")
        # Re-adding an existing key must not grow the set
        s.add("x")
        count = sum(1 for k in ["x", "y", "z"] if k in s)
        assert count == 3


# ---------------------------------------------------------------------------
# 4. discard removes key silently
# ---------------------------------------------------------------------------


class TestDiscard:
    def test_discard_removes_present_key(self) -> None:
        s = _LRUSet(5)
        s.add("remove_me")
        s.discard("remove_me")
        assert "remove_me" not in s

    def test_discard_absent_key_does_not_raise(self) -> None:
        s = _LRUSet(5)
        # Must not raise KeyError or any exception
        s.discard("not_there")

    def test_discard_does_not_affect_other_keys(self) -> None:
        s = _LRUSet(5)
        s.add("keep_a")
        s.add("remove_me")
        s.add("keep_b")
        s.discard("remove_me")
        assert "keep_a" in s
        assert "keep_b" in s

    def test_discard_then_re_add(self) -> None:
        s = _LRUSet(5)
        s.add("x")
        s.discard("x")
        assert "x" not in s
        s.add("x")
        assert "x" in s


# ---------------------------------------------------------------------------
# 5. After 2001 adds on a max-2000 set, only 2000 entries remain
# ---------------------------------------------------------------------------


class TestCapacityAt2000:
    @pytest.mark.slow
    def test_exactly_2001_adds_leaves_2000_entries(self) -> None:
        """Spec requirement: after 2001 add calls only 2000 entries remain."""
        s = _LRUSet(2000)
        for i in range(2001):
            s.add(str(i))

        # Verify the internal size matches the cap
        assert len(s._d) == 2000

    @pytest.mark.slow
    def test_entry_0_is_evicted_after_2001_unique_adds(self) -> None:
        """The first key added ('0') must be gone after capacity overflow."""
        s = _LRUSet(2000)
        for i in range(2001):
            s.add(str(i))

        assert "0" not in s, "key '0' must have been evicted as the oldest entry"

    @pytest.mark.slow
    def test_entry_2000_is_retained_after_2001_adds(self) -> None:
        """The 2001st key (index 2000) must still be present."""
        s = _LRUSet(2000)
        for i in range(2001):
            s.add(str(i))

        assert "2000" in s, "the last-added key must always be present"


# ---------------------------------------------------------------------------
# 6. Most-recently-used key is NOT evicted even when at capacity
# ---------------------------------------------------------------------------


class TestMRUKeyNotEvicted:
    def test_mru_key_survives_next_eviction(self) -> None:
        """The most-recently-touched key must survive when capacity is hit."""
        s = _LRUSet(3)
        s.add("old-1")
        s.add("old-2")
        s.add("mru")  # this is the MRU

        # Fill past capacity — 'old-1' should be evicted, not 'mru'
        s.add("new-entry")

        assert "mru" in s, "MRU key must not be evicted"
        assert "old-1" not in s, "'old-1' is the LRU and must be evicted"

    def test_mru_key_survives_multiple_eviction_rounds(self) -> None:
        """If we keep touching the same key it must never be evicted."""
        s = _LRUSet(3)
        s.add("sticky")
        s.add("a")
        s.add("b")

        for round_idx in range(10):
            _ = "sticky" in s  # promote before each eviction
            s.add(f"filler-{round_idx}")

        assert "sticky" in s, "continuously promoted key must never be evicted"

    def test_add_to_mru_position_then_evict_from_lru(self) -> None:
        """verify the internal OrderedDict move_to_end semantics hold."""
        s = _LRUSet(4)
        s.add("a")
        s.add("b")
        s.add("c")
        s.add("d")

        # Promote 'a' to MRU
        s.add("a")

        # Now add 'e' — 'b' should be evicted (new oldest after 'a' moved)
        s.add("e")

        assert "a" in s
        assert "c" in s
        assert "d" in s
        assert "e" in s
        assert "b" not in s


# ---------------------------------------------------------------------------
# Regression: discard on failed registration allows retry
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_discard_after_failed_storage_allows_retry() -> None:
    """Regression: when storage.upsert raises, the key must be discarded so the
    next span batch retries the registration.  Simulates the discard-on-failure
    pattern in the ingest_spans handler (traces.py lines 168-169 / 184-185).
    """
    s = _LRUSet(100)
    cache_key = "proj-1:my-agent"

    # First attempt: add to cache, then simulate failure by discarding
    s.add(cache_key)
    assert cache_key in s

    # Simulate storage failure → discard so it will be retried
    s.discard(cache_key)
    assert cache_key not in s

    # Next batch: key should be re-registered (not skipped by cache hit)
    s.add(cache_key)
    assert cache_key in s
