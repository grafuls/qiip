"""Thread-safe per-node active connection counter.

Tracks the number of in-flight requests to each vLLM node.  The count
is incremented before proxying a request and decremented in a
``finally`` block, ensuring the counter stays accurate even when
requests fail.

Uses ``dict[str, int]`` protected by ``threading.Lock`` following the
same concurrency pattern as ``NodeRegistry`` (D-01).

Per D-01: Connection counts live in a separate structure, not inside
the NodeRegistry.
Per D-02: Counts managed via increment/decrement in route handlers.
"""

from __future__ import annotations

import threading

import structlog

logger = structlog.get_logger()


class ConnectionTracker:
    """Thread-safe counter of active connections per node.

    All public methods acquire ``self._lock`` before accessing the
    internal dictionary.  ``get_all`` returns a copy so callers
    cannot mutate internal state.
    """

    def __init__(self) -> None:
        self._counts: dict[str, int] = {}
        self._lock = threading.Lock()

    def increment(self, node_id: str) -> None:
        """Increment the active connection count for *node_id*."""
        with self._lock:
            self._counts[node_id] = self._counts.get(node_id, 0) + 1
        logger.debug("connection incremented", node_id=node_id)

    def decrement(self, node_id: str) -> None:
        """Decrement the active connection count for *node_id*.

        The count is floored at zero to guard against logic bugs
        where decrement is called without a matching increment.
        """
        with self._lock:
            current = self._counts.get(node_id, 0)
            if current > 0:
                self._counts[node_id] = current - 1
        logger.debug("connection decremented", node_id=node_id)

    def get(self, node_id: str) -> int:
        """Return the active connection count for *node_id*.

        Returns ``0`` for unknown nodes (never incremented or already
        removed).
        """
        with self._lock:
            return self._counts.get(node_id, 0)

    def get_all(self) -> dict[str, int]:
        """Return a copy of all tracked node connection counts."""
        with self._lock:
            return dict(self._counts)

    def remove(self, node_id: str) -> None:
        """Remove *node_id* from the tracker entirely.

        After removal, ``get(node_id)`` returns ``0``.  No-op if
        *node_id* is not tracked.
        """
        with self._lock:
            self._counts.pop(node_id, None)
        logger.debug("connection counter removed", node_id=node_id)
