"""Admin API response models for operational visibility.

Per METR-03: Each node entry includes identity, health status, active
connections, and circuit breaker state for the operations dashboard.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AdminNodeResponse(BaseModel):
    """Admin API response for a single registered node.

    Includes node identity, health status, and operational state
    (active connections, circuit breaker).  The ``status`` field is
    ``str`` (not ``NodeStatus`` enum) because the response serializes
    the enum's value.
    """

    model_config = ConfigDict(frozen=True)

    node_id: str
    endpoint: str
    model: str
    status: str
    active_connections: int
    circuit_breaker_state: str


class AdminMetricsResponse(BaseModel):
    """Admin API response for aggregate request metrics.

    Serves the ``/admin/metrics`` endpoint with total and per-dimension
    request counts.
    """

    model_config = ConfigDict(frozen=True)

    total_requests: int
    per_model: dict[str, int]
    per_node: dict[str, int]


class SetupRequest(BaseModel):
    """Request body for POST /admin/nodes/setup."""

    model_config = ConfigDict(frozen=True)

    hostname: str


class SetupResponse(BaseModel):
    """Response body for POST /admin/nodes/setup (202)."""

    model_config = ConfigDict(frozen=True)

    task_id: str


class TeardownResponse(BaseModel):
    """Response body for DELETE /admin/nodes/{id} (202)."""

    model_config = ConfigDict(frozen=True)

    task_id: str


class TaskStatusResponse(BaseModel):
    """Provisioning task status from etcd."""

    model_config = ConfigDict(frozen=True)

    hostname: str
    current_step: str
    started_at: datetime
    updated_at: datetime
    failed_step: str | None = None
    error: str | None = None
