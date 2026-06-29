"""Unit tests for the thread-safe RequestMetrics counter.

Tests cover record_request, record_node_attempt, get_total, get_per_node,
and get_per_model operations, including copy semantics and model=None handling.
"""

from __future__ import annotations

from inference_proxy.routing.request_metrics import RequestMetrics


class TestRecordRequest:
    """record_request() increments total, per-node, and per-model counts."""

    def test_increments_total_from_zero(self) -> None:
        metrics = RequestMetrics()

        metrics.record_request("node-1", "llama-3")

        assert metrics.get_total() == 1

    def test_increments_per_node_count(self) -> None:
        metrics = RequestMetrics()

        metrics.record_request("node-1", "llama-3")

        assert metrics.get_per_node() == {"node-1": 1}

    def test_increments_per_model_count(self) -> None:
        metrics = RequestMetrics()

        metrics.record_request("node-1", "llama-3")

        assert metrics.get_per_model() == {"llama-3": 1}

    def test_model_none_does_not_add_to_per_model(self) -> None:
        metrics = RequestMetrics()

        metrics.record_request("node-1", None)

        assert metrics.get_per_model() == {}

    def test_called_twice_increments_total_to_two(self) -> None:
        metrics = RequestMetrics()

        metrics.record_request("node-1", "llama-3")
        metrics.record_request("node-2", "llama-3")

        assert metrics.get_total() == 2


class TestRecordNodeAttempt:
    """record_node_attempt() increments per-node count only."""

    def test_increments_per_node_count(self) -> None:
        metrics = RequestMetrics()

        metrics.record_node_attempt("node-1")

        assert metrics.get_per_node() == {"node-1": 1}

    def test_does_not_increment_total(self) -> None:
        metrics = RequestMetrics()

        metrics.record_node_attempt("node-1")

        assert metrics.get_total() == 0

    def test_does_not_add_to_per_model(self) -> None:
        metrics = RequestMetrics()

        metrics.record_node_attempt("node-1")

        assert metrics.get_per_model() == {}


class TestGetTotal:
    """get_total() returns the total request count."""

    def test_returns_zero_for_fresh_instance(self) -> None:
        metrics = RequestMetrics()

        assert metrics.get_total() == 0


class TestGetPerNode:
    """get_per_node() returns a dict of per-node counts."""

    def test_returns_empty_dict_for_fresh_instance(self) -> None:
        metrics = RequestMetrics()

        assert metrics.get_per_node() == {}

    def test_returns_copy(self) -> None:
        metrics = RequestMetrics()
        metrics.record_request("node-1", "llama-3")

        result = metrics.get_per_node()
        result.clear()

        assert metrics.get_per_node() == {"node-1": 1}


class TestGetPerModel:
    """get_per_model() returns a dict of per-model counts."""

    def test_returns_empty_dict_for_fresh_instance(self) -> None:
        metrics = RequestMetrics()

        assert metrics.get_per_model() == {}

    def test_returns_copy(self) -> None:
        metrics = RequestMetrics()
        metrics.record_request("node-1", "llama-3")

        result = metrics.get_per_model()
        result.clear()

        assert metrics.get_per_model() == {"llama-3": 1}
