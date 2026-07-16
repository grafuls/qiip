"""QUADS host domain model.

Represents a GPU host from the QUADS inventory.  Only the fields
needed by the gateway are captured (D-04); extra fields from the
QUADS API response are silently ignored (Pydantic v2 default).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class QUADSHost(BaseModel):
    """A GPU host from the QUADS inventory."""

    model_config = ConfigDict(frozen=True)

    hostname: str
    gpu_vendor: str
    gpu_model: str
    gpu_count: int
