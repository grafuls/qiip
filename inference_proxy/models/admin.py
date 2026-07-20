"""Admin API response models for operational visibility.

Per METR-03: Each node entry includes identity, health status, active
connections, and circuit breaker state for the operations dashboard.
"""

from __future__ import annotations

from datetime import datetime

import re

from pydantic import BaseModel, ConfigDict, field_validator


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
    state: str = ""
    actions: list[str] = []
    gpu_vendor: str | None = None
    gpu_model: str | None = None
    gpu_count: int | None = None


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

    @field_validator("hostname")
    @classmethod
    def validate_hostname(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > 253:
            raise ValueError("hostname must be 1-253 characters")
        if not re.fullmatch(r"[a-zA-Z0-9]([a-zA-Z0-9\-\.]*[a-zA-Z0-9])?", v):
            raise ValueError("hostname contains invalid characters")
        return v


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


class QUADSStatusResponse(BaseModel):
    """QUADS poller staleness data for the dashboard status indicator."""

    model_config = ConfigDict(frozen=True)

    status: str
    last_sync: datetime | None
    consecutive_failures: int
