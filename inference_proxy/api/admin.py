"""Admin API for operational visibility into the gateway.

Per D-05: Endpoints under /admin namespace, separate from /v1 proxy API.
Per D-06: Separate APIRouter in api/admin.py with prefix="/admin".
Per METR-03: Node entries include identity, health, active connections,
and circuit breaker state for the operations dashboard.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from inference_proxy.config.dependencies import (
    get_circuit_breaker_registry,
    get_node_selector,
    get_registry,
    get_request_metrics,
)
from inference_proxy.discovery.registry import NodeRegistry
from inference_proxy.models.admin import AdminMetricsResponse, AdminNodeResponse
from inference_proxy.resilience.circuit_breaker import CircuitBreakerRegistry
from inference_proxy.routing.node_selector import NodeSelector
from inference_proxy.routing.request_metrics import RequestMetrics

admin_router = APIRouter(prefix="/admin", tags=["admin"])


@admin_router.get("/nodes")
async def list_nodes(
    registry: NodeRegistry = Depends(get_registry),
    node_selector: NodeSelector = Depends(get_node_selector),
    cb_registry: CircuitBreakerRegistry = Depends(get_circuit_breaker_registry),
) -> list[AdminNodeResponse]:
    """Return all registered nodes with identity, health, and operational state.

    Returns a flat JSON array of nodes.  Nodes of all statuses
    (HEALTHY, UNHEALTHY, DRAINING) appear in the response.
    """
    nodes = registry.get_all()
    tracker = node_selector.tracker
    return [
        AdminNodeResponse(
            node_id=n.node_id,
            endpoint=n.endpoint,
            model=n.model,
            status=n.status.value,
            active_connections=tracker.get(n.node_id),
            circuit_breaker_state=cb_registry.get_or_create(n.node_id).state,
        )
        for n in nodes
    ]


@admin_router.get("/metrics")
async def get_metrics(
    request_metrics: RequestMetrics = Depends(get_request_metrics),
) -> AdminMetricsResponse:
    """Return aggregate request counter data for the operations dashboard."""
    return AdminMetricsResponse(
        total_requests=request_metrics.get_total(),
        per_model=request_metrics.get_per_model(),
        per_node=request_metrics.get_per_node(),
    )
