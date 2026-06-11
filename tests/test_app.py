"""Smoke tests for the FastAPI application."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_health_endpoint(client: TestClient) -> None:
    """GET /health returns 200 with JSON containing 'status' key."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] == "ok"


def test_app_is_fastapi_instance(app: FastAPI) -> None:
    """The app fixture yields a FastAPI instance."""
    assert isinstance(app, FastAPI)


def test_subpackages_importable() -> None:
    """All six sub-packages under inference_proxy are importable."""
    import inference_proxy.api
    import inference_proxy.config
    import inference_proxy.discovery
    import inference_proxy.models
    import inference_proxy.resilience
    import inference_proxy.routing

    # Verify they are actual modules (not None or error objects)
    assert inference_proxy.config is not None
    assert inference_proxy.models is not None
    assert inference_proxy.api is not None
    assert inference_proxy.discovery is not None
    assert inference_proxy.routing is not None
    assert inference_proxy.resilience is not None
