"""Provisioning step and state types for node setup tracking.

ProvisioningStep (D-06): 13-member StrEnum matching the provisioner's
step sequence from PREFLIGHT through COMPLETE/FAILED.

ProvisioningState (D-07, D-08): Frozen Pydantic model capturing the
current provisioning state of a host.  The ``failed_step`` and ``error``
fields are populated when ``current_step`` is FAILED (D-08).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class ProvisioningStep(StrEnum):
    """Steps in the node provisioning sequence (D-06)."""

    PENDING = "pending"
    PREFLIGHT = "preflight"
    NVIDIA_REPO = "nvidia_repo"
    SYSTEM_UPDATE = "system_update"
    NVIDIA_DRIVER = "nvidia_driver"
    NVIDIA_CDI = "nvidia_cdi"
    NFS_MOUNT = "nfs_mount"
    FIREWALL = "firewall"
    STARTING_VLLM = "starting_vllm"
    HEALTH_POLL = "health_poll"
    REGISTERING = "registering"
    DRAINING = "draining"
    STOPPING_CONTAINER = "stopping_container"
    DEREGISTERING = "deregistering"
    TEARDOWN_COMPLETE = "teardown_complete"
    COMPLETE = "complete"
    FAILED = "failed"


class ProvisioningState(BaseModel):
    """Current provisioning state for a host (D-07, D-08).

    Frozen to prevent external mutation; use ``model_copy(update={...})``
    to create modified copies, matching the Node model pattern.
    """

    model_config = ConfigDict(frozen=True)

    hostname: str
    current_step: ProvisioningStep
    started_at: datetime
    updated_at: datetime
    failed_step: str | None = None
    error: str | None = None
