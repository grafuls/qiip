"""Admin API for operational visibility into the gateway.

Per D-05: Endpoints under /admin namespace, separate from /v1 proxy API.
Per D-06: Separate APIRouter in api/admin.py with prefix="/admin".
Per METR-03: Node entries include identity, health, active connections,
and circuit breaker state for the operations dashboard.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException

from inference_proxy.config.dependencies import (
    get_provisioner,
    get_quads_client,
    get_quads_poller,
    get_registry,
    get_request_metrics,
    get_unified_node_service,
)
from inference_proxy.discovery.registry import NodeRegistry
from inference_proxy.models.admin import (
    AdminMetricsResponse,
    AdminNodeResponse,
    QUADSStatusResponse,
    SetupRequest,
    SetupResponse,
    TaskStatusResponse,
    TeardownResponse,
)
from inference_proxy.provisioning.provisioner import NodeProvisioner
from inference_proxy.quads.client import (
    QUADSClient,
    QUADSConnectionError,
    canonical_hostname,
)
from inference_proxy.quads.poller import QUADSPoller
from inference_proxy.routing.request_metrics import RequestMetrics
from inference_proxy.services.unified_nodes import UnifiedNodeService

admin_router = APIRouter(prefix="/admin", tags=["admin"])

# D-08: module-level set to prevent duplicate setup requests
pending_hosts: set[str] = set()


@admin_router.get("/nodes")
async def list_nodes(
    service: UnifiedNodeService = Depends(get_unified_node_service),
) -> list[AdminNodeResponse]:
    """Return unified node list merging QUADS hosts with etcd nodes."""
    return service.get_unified_nodes()


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
    quads_client: QUADSClient | None = Depends(get_quads_client),
) -> SetupResponse:
    """Trigger provisioning of a new node (runs in background).

    Includes dedup guard (D-08) and live QUADS re-validation (D-10/D-11).
    """
    hostname = canonical_hostname(body.hostname)

    # D-08: dedup guard
    if hostname in pending_hosts:
        raise HTTPException(
            status_code=409,
            detail=f"Setup already in progress for '{hostname}'",
        )

    # Add before any await to close TOCTOU window (CR-01)
    pending_hosts.add(hostname)

    # D-10/D-11: live QUADS re-validation (skip for unmanaged nodes)
    try:
        if body.managed and quads_client is not None:
            try:
                available = await quads_client.get_available()
            except QUADSConnectionError as exc:
                raise HTTPException(
                    status_code=503, detail="QUADS unavailable"
                ) from exc
            if hostname not in available:
                raise HTTPException(
                    status_code=400,
                    detail=f"Host '{hostname}' is not available in QUADS",
                )
    except Exception:
        pending_hosts.discard(hostname)
        raise

    async def _provision_and_cleanup() -> None:
        try:
            await provisioner.provision(hostname, managed=body.managed)
        finally:
            pending_hosts.discard(hostname)

    try:
        provisioner.fire_background(_provision_and_cleanup())
    except Exception:
        pending_hosts.discard(hostname)
        raise
    return SetupResponse(task_id=hostname)


@admin_router.get("/provisioning/tasks")
async def list_provisioning_tasks(
    provisioner: NodeProvisioner = Depends(get_provisioner),
) -> list[TaskStatusResponse]:
    """Return status of all provisioning/teardown operations from etcd."""
    results = await provisioner.list_tasks_raw()
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


@admin_router.get("/quads/status")
async def get_quads_status(
    poller: QUADSPoller | None = Depends(get_quads_poller),
) -> QUADSStatusResponse:
    """Return QUADS poller staleness for the dashboard status indicator."""
    if poller is None:
        return QUADSStatusResponse(
            status="unavailable", last_sync=None, consecutive_failures=0
        )
    if poller.last_sync is None or poller.consecutive_failures >= 3:
        status = "unavailable"
    elif poller.consecutive_failures >= 1:
        status = "stale"
    else:
        status = "connected"
    return QUADSStatusResponse(
        status=status,
        last_sync=poller.last_sync,
        consecutive_failures=poller.consecutive_failures,
    )
