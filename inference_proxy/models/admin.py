"""Admin API response models for operational visibility.

Per D-07: Each node entry contains exactly node_id, endpoint, model,
and status fields -- no operational data (connection counts, circuit
breaker state).
Per D-08: Response is a flat node list with no top-level summary stats;
empty registry returns empty list.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class AdminNodeResponse(BaseModel):
    """Admin API response for a single registered node.

    Fields are the string representations of core node identity and
    health status.  The ``status`` field is ``str`` (not ``NodeStatus``
    enum) because the response serializes the enum's value.
    """

    model_config = ConfigDict(frozen=True)

    node_id: str
    endpoint: str
    model: str
    status: str
