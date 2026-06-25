"""Unit tests for the AdminNodeResponse model.

Tests cover:
- AdminNodeResponse creation with valid fields
- AdminNodeResponse is frozen (immutable)
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from inference_proxy.models.admin import AdminNodeResponse


class TestAdminNodeResponse:
    """AdminNodeResponse model validation and behavior."""

    def test_create_with_valid_fields(self) -> None:
        """AdminNodeResponse accepts node_id, endpoint, model, status as strings."""
        response = AdminNodeResponse(
            node_id="node-1",
            endpoint="10.0.1.100:8000",
            model="llama-3",
            status="healthy",
        )
        assert response.node_id == "node-1"
        assert response.endpoint == "10.0.1.100:8000"
        assert response.model == "llama-3"
        assert response.status == "healthy"

    def test_frozen_rejects_mutation(self) -> None:
        """AdminNodeResponse is immutable -- assigning to a field raises ValidationError."""
        response = AdminNodeResponse(
            node_id="node-1",
            endpoint="10.0.1.100:8000",
            model="llama-3",
            status="healthy",
        )
        with pytest.raises(ValidationError):
            response.status = "unhealthy"  # type: ignore[misc]
