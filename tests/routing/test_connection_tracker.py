"""Unit tests for the thread-safe ConnectionTracker.

Tests cover increment, decrement, get, get_all, and remove operations,
including edge cases like decrement floor at zero and unknown node defaults.
"""

from __future__ import annotations

from inference_proxy.routing.connection_tracker import ConnectionTracker


class TestIncrement:
    """increment() increases the connection count for a node."""

    def test_increment_sets_count_to_one(self) -> None:
        tracker = ConnectionTracker()

        tracker.increment("node-1")

        assert tracker.get("node-1") == 1

    def test_increment_twice_sets_count_to_two(self) -> None:
        tracker = ConnectionTracker()

        tracker.increment("node-1")
        tracker.increment("node-1")

        assert tracker.get("node-1") == 2


class TestDecrement:
    """decrement() decreases the connection count for a node."""

    def test_decrement_after_increment_returns_zero(self) -> None:
        tracker = ConnectionTracker()
        tracker.increment("node-1")

        tracker.decrement("node-1")

        assert tracker.get("node-1") == 0

    def test_decrement_does_not_go_below_zero(self) -> None:
        tracker = ConnectionTracker()

        tracker.decrement("nonexistent")

        assert tracker.get("nonexistent") == 0


class TestGet:
    """get() returns the current connection count for a node."""

    def test_get_unknown_node_returns_zero(self) -> None:
        tracker = ConnectionTracker()

        assert tracker.get("unknown") == 0


class TestGetAll:
    """get_all() returns a dict of all tracked node counts."""

    def test_get_all_returns_tracked_counts(self) -> None:
        tracker = ConnectionTracker()
        tracker.increment("node-1")
        tracker.increment("node-1")
        tracker.increment("node-2")

        result = tracker.get_all()

        assert result == {"node-1": 2, "node-2": 1}

    def test_get_all_returns_copy(self) -> None:
        tracker = ConnectionTracker()
        tracker.increment("node-1")

        result = tracker.get_all()
        result.clear()

        assert tracker.get("node-1") == 1


class TestRemove:
    """remove() clears a node's counter entirely."""

    def test_remove_clears_counter(self) -> None:
        tracker = ConnectionTracker()
        tracker.increment("node-1")
        tracker.increment("node-1")

        tracker.remove("node-1")

        assert tracker.get("node-1") == 0

    def test_remove_nonexistent_is_silent(self) -> None:
        tracker = ConnectionTracker()

        tracker.remove("nonexistent")  # should not raise
