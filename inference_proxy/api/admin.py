"""Admin API for operational visibility into the gateway.

Per D-05: Endpoints under /admin namespace, separate from /v1 proxy API.
Per D-06: Separate APIRouter in api/admin.py with prefix="/admin".
Per D-07: Core fields only (node_id, endpoint, model, status).
Per D-08: Flat node list response, no summary stats.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from inference_proxy.config.dependencies import get_registry
from inference_proxy.discovery.registry import NodeRegistry
from inference_proxy.models.admin import AdminNodeResponse

admin_router = APIRouter(prefix="/admin", tags=["admin"])


@admin_router.get("/nodes")
async def list_nodes(
    registry: NodeRegistry = Depends(get_registry),
) -> list[AdminNodeResponse]:
    """Return all registered nodes with their models and health status.

    Returns a flat JSON array of nodes.  Each node contains only
    node_id, endpoint, model, and status (per DISC-04).  Nodes of
    all statuses (HEALTHY, UNHEALTHY, DRAINING) appear in the response.
    """
    nodes = registry.get_all()
    return [
        AdminNodeResponse(
            node_id=n.node_id,
            endpoint=n.endpoint,
            model=n.model,
            status=n.status.value,
        )
        for n in nodes
    ]
