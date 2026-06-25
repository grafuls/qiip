"""Integration tests for the graceful shutdown middleware.

Tests cover:
- ShutdownMiddleware rejects requests with 503 when shutting_down is True
- ShutdownMiddleware passes through when shutting_down is False
- /health endpoint returns 200 even during shutdown (per D-12)
- Normal routes return 503 during shutdown
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from inference_proxy.discovery.registry import NodeRegistry
from inference_proxy.models.node import Node, NodeStatus


def _make_node(
    node_id: str = "node-1",
    endpoint: str = "10.0.1.100:8000",
    status: NodeStatus = NodeStatus.HEALTHY,
    model: str = "llama-3",
) -> Node:
    """Create a test node with sensible defaults."""
    return Node(
        node_id=node_id,
        endpoint=endpoint,
        status=status,
        model=model,
    )


class TestShutdownMiddlewareRejects503:
    """Requests to any route return 503 when shutting_down is True."""

    def test_post_returns_503_during_shutdown(
        self,
        app: FastAPI,
        client: TestClient,
        test_registry: NodeRegistry,
    ) -> None:
        """POST /v1/chat/completions returns 503 during shutdown."""
        app.state.shutting_down = True
        test_registry.add(_make_node())

        response = client.post(
            "/v1/chat/completions",
            json={"model": "llama-3", "messages": [{"role": "user", "content": "Hi"}]},
        )

        assert response.status_code == 503
        data = response.json()
        assert data["error"]["code"] == "shutting_down"
        assert data["error"]["type"] == "server_error"

    def test_get_models_returns_503_during_shutdown(
        self,
        app: FastAPI,
        client: TestClient,
    ) -> None:
        """GET /v1/models returns 503 during shutdown."""
        app.state.shutting_down = True

        response = client.get("/v1/models")

        assert response.status_code == 503
        data = response.json()
        assert data["error"]["code"] == "shutting_down"


class TestShutdownMiddlewarePassesThrough:
    """Requests pass through normally when shutting_down is False."""

    def test_health_passes_through(
        self,
        app: FastAPI,
        client: TestClient,
    ) -> None:
        """GET /health returns 200 when not shutting down."""
        app.state.shutting_down = False

        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"


class TestHealthEndpointDuringShutdown:
    """/health returns 200 even during shutdown (per D-12)."""

    def test_health_returns_200_during_shutdown(
        self,
        app: FastAPI,
        client: TestClient,
    ) -> None:
        """GET /health returns 200 even when shutting_down is True."""
        app.state.shutting_down = True

        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"


class TestNormalRequestsDuringShutdown:
    """Non-health routes return 503 during shutdown."""

    def test_text_completions_returns_503(
        self,
        app: FastAPI,
        client: TestClient,
        test_registry: NodeRegistry,
    ) -> None:
        """POST /v1/completions returns 503 during shutdown."""
        app.state.shutting_down = True
        test_registry.add(_make_node())

        response = client.post(
            "/v1/completions",
            json={"model": "llama-3", "prompt": "Hello"},
        )

        assert response.status_code == 503
        data = response.json()
        assert data["error"]["code"] == "shutting_down"

    def test_streaming_returns_503(
        self,
        app: FastAPI,
        client: TestClient,
        test_registry: NodeRegistry,
    ) -> None:
        """POST /v1/chat/completions with stream=true returns 503 during shutdown."""
        app.state.shutting_down = True
        test_registry.add(_make_node())

        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "llama-3",
                "messages": [{"role": "user", "content": "Hi"}],
                "stream": True,
            },
        )

        assert response.status_code == 503
        data = response.json()
        assert data["error"]["code"] == "shutting_down"
