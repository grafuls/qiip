"""Admin API for operational visibility into the gateway.

Per D-05: Endpoints under /admin namespace, separate from /v1 proxy API.
Per D-06: Separate APIRouter in api/admin.py with prefix="/admin".
Per METR-03: Node entries include identity, health, active connections,
and circuit breaker state for the operations dashboard.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException

from inference_proxy.config.dependencies import (
    get_circuit_breaker_registry,
    get_node_selector,
    get_provisioner,
    get_registry,
    get_request_metrics,
)
from inference_proxy.discovery.registry import NodeRegistry
from inference_proxy.models.admin import (
    AdminMetricsResponse,
    AdminNodeResponse,
    SetupRequest,
    SetupResponse,
    TaskStatusResponse,
    TeardownResponse,
)
from inference_proxy.provisioning.provisioner import NodeProvisioner
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
            circuit_breaker_state=(breaker.state if (breaker := cb_registry.get(n.node_id)) is not None else "closed"),
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


@admin_router.post("/nodes/setup", status_code=202)
async def setup_node(
    body: SetupRequest,
    provisioner: NodeProvisioner = Depends(get_provisioner),
) -> SetupResponse:
    """Trigger provisioning of a new node (runs in background)."""
    provisioner.fire_background(provisioner.provision(body.hostname))
    return SetupResponse(task_id=body.hostname)


@admin_router.get("/provisioning/tasks")
async def list_provisioning_tasks(
    provisioner: NodeProvisioner = Depends(get_provisioner),
) -> list[TaskStatusResponse]:
    """Return status of all provisioning/teardown operations from etcd."""
    results = await asyncio.to_thread(
        provisioner._etcd_client.get_prefix, "/provisioning/"
    )
    tasks: list[TaskStatusResponse] = []
    for value_bytes, _metadata in results:
        data = json.loads(value_bytes)
        tasks.append(TaskStatusResponse(**data))
    return tasks


@admin_router.delete("/nodes/{node_id}", status_code=202)
async def teardown_node(
    node_id: str,
    force: bool = False,
    registry: NodeRegistry = Depends(get_registry),
    provisioner: NodeProvisioner = Depends(get_provisioner),
) -> TeardownResponse:
    """Trigger teardown of a node (runs in background)."""
    if registry.get(node_id) is None:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found")
    provisioner.fire_background(provisioner.teardown(node_id, force=force))
    return TeardownResponse(task_id=node_id)
