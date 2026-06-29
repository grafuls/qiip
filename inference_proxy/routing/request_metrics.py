"""Thread-safe request counter for proxied inference requests.

Tracks total, per-node, and per-model request counts.  Uses
``dict[str, int]`` protected by ``threading.Lock`` following the
same concurrency pattern as ``ConnectionTracker``.

Per D-01: Count proxied inference requests only.
Per D-02: Track total counts only (simple integers).
Per D-03: ``record_request`` increments total once per client request;
``record_node_attempt`` increments per-node only (for retries).
"""

from __future__ import annotations

import threading

import structlog

logger = structlog.get_logger()


class RequestMetrics:
    """Thread-safe counter of proxied inference requests.

    All public methods acquire ``self._lock`` before accessing
    internal state.  ``get_per_node`` and ``get_per_model`` return
    copies so callers cannot mutate internal state.
    """

    def __init__(self) -> None:
        self._total: int = 0
        self._per_node: dict[str, int] = {}
        self._per_model: dict[str, int] = {}
        self._lock = threading.Lock()

    def record_request(self, node_id: str, model: str | None) -> None:
        """Record a client request routed to *node_id*.

        Increments total by 1, per-node count for *node_id* by 1,
        and per-model count for *model* by 1 (skipped when *model*
        is ``None``).
        """
        with self._lock:
            self._total += 1
            self._per_node[node_id] = self._per_node.get(node_id, 0) + 1
            if model is not None:
                self._per_model[model] = self._per_model.get(model, 0) + 1
        logger.debug("request recorded", node_id=node_id, model=model)

    def record_node_attempt(self, node_id: str) -> None:
        """Record a retry attempt to *node_id*.

        Increments per-node count only -- total and per-model are
        unchanged (per D-03).
        """
        with self._lock:
            self._per_node[node_id] = self._per_node.get(node_id, 0) + 1

    def get_total(self) -> int:
        """Return the total number of client requests recorded."""
        with self._lock:
            return self._total

    def get_per_node(self) -> dict[str, int]:
        """Return a copy of per-node request counts."""
        with self._lock:
            return dict(self._per_node)

    def get_per_model(self) -> dict[str, int]:
        """Return a copy of per-model request counts."""
        with self._lock:
            return dict(self._per_model)
