"""Thread-safe per-node circuit breaker and registry.

Tracks consecutive failures per node.  When failures reach the
configured threshold, the breaker trips to OPEN and ``is_open``
returns ``True``.  A single success (``record_success``) or explicit
``reset`` clears the failure count and returns the breaker to CLOSED.

Uses ``threading.Lock`` following the same concurrency pattern as
``ConnectionTracker`` (D-05).

Per D-06: CircuitBreaker trips to OPEN after 3 consecutive failures.
Per D-05: CircuitBreaker and CircuitBreakerRegistry live in
``inference_proxy/resilience/``, separate from the node registry.
Per D-08: Health checker calls ``reset()`` on recovery.
"""

from __future__ import annotations

import threading

import structlog

logger = structlog.get_logger()


class CircuitBreaker:
    """Thread-safe circuit breaker for a single node.

    All public methods acquire ``self._lock`` before accessing
    internal state.

    Args:
        threshold: Number of consecutive failures before the breaker
            trips to OPEN.  Defaults to 3 (per D-06).
    """

    def __init__(self, threshold: int = 3) -> None:
        self._threshold = threshold
        self._failure_count: int = 0
        self._state: str = "closed"
        self._lock = threading.Lock()

    def record_failure(self) -> None:
        """Record a failed request.

        Increments the failure counter.  When the counter reaches
        ``threshold``, the breaker transitions to OPEN.
        """
        with self._lock:
            self._failure_count += 1
            if self._failure_count >= self._threshold and self._state != "open":
                self._state = "open"
                logger.info(
                    "circuit breaker tripped",
                    failure_count=self._failure_count,
                    threshold=self._threshold,
                )

    def record_success(self) -> None:
        """Record a successful request.

        Resets the failure counter to 0 and transitions the breaker
        back to CLOSED.
        """
        with self._lock:
            was_open = self._state == "open"
            self._failure_count = 0
            self._state = "closed"
        if was_open:
            logger.info("circuit breaker closed after success")

    @property
    def is_open(self) -> bool:
        """Return ``True`` when the breaker is in the OPEN state."""
        with self._lock:
            return self._state == "open"

    @property
    def state(self) -> str:
        """Return the current state as a string (``'closed'`` or ``'open'``)."""
        with self._lock:
            return self._state

    def reset(self) -> None:
        """Reset the breaker to CLOSED and clear the failure count.

        Used by the health checker when a node recovers (per D-08).
        Semantically identical to ``record_success``.
        """
        self.record_success()


class CircuitBreakerRegistry:
    """Thread-safe registry of per-node circuit breakers.

    Lazily creates ``CircuitBreaker`` instances keyed by ``node_id``.
    Follows the same dict+lock pattern as ``NodeRegistry``.

    Args:
        threshold: Failure threshold passed to newly created
            ``CircuitBreaker`` instances.  Defaults to 3.
    """

    def __init__(self, threshold: int = 3) -> None:
        self._threshold = threshold
        self._breakers: dict[str, CircuitBreaker] = {}
        self._lock = threading.Lock()

    def get(self, node_id: str) -> CircuitBreaker | None:
        """Return the breaker for *node_id*, or ``None`` if absent."""
        with self._lock:
            return self._breakers.get(node_id)

    def get_or_create(self, node_id: str) -> CircuitBreaker:
        """Return the breaker for *node_id*, creating one if absent."""
        with self._lock:
            breaker = self._breakers.get(node_id)
            if breaker is None:
                breaker = CircuitBreaker(threshold=self._threshold)
                self._breakers[node_id] = breaker
            return breaker

    def reset(self, node_id: str) -> None:
        """Reset the breaker for *node_id*.

        No-op if *node_id* has no breaker.
        """
        with self._lock:
            breaker = self._breakers.get(node_id)
        if breaker is not None:
            breaker.reset()

    def remove(self, node_id: str) -> None:
        """Remove the breaker for *node_id* entirely.

        No-op if *node_id* is not tracked.
        """
        with self._lock:
            self._breakers.pop(node_id, None)
        logger.debug("circuit breaker removed", node_id=node_id)
