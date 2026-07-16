"""Unified node list service — merges QUADS hosts with etcd nodes.

Stub for TDD RED phase. Implementation in GREEN.
"""

from __future__ import annotations

from inference_proxy.discovery.registry import NodeRegistry
from inference_proxy.models.admin import AdminNodeResponse
from inference_proxy.quads.poller import QUADSPoller
from inference_proxy.resilience.circuit_breaker import CircuitBreakerRegistry
from inference_proxy.routing.connection_tracker import ConnectionTracker


class UnifiedNodeService:
    """Merges QUADS hosts with etcd nodes into a unified view (D-01)."""

    def __init__(
        self,
        registry: NodeRegistry,
        poller: QUADSPoller | None,
        cb_registry: CircuitBreakerRegistry,
        tracker: ConnectionTracker,
    ) -> None:
        self._registry = registry
        self._poller = poller
        self._cb_registry = cb_registry
        self._tracker = tracker

    def get_unified_nodes(self) -> list[AdminNodeResponse]:
        raise NotImplementedError
