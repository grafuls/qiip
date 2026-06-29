"""Integration tests for the admin API endpoint.

Tests cover:
- GET /admin/nodes with populated registry returns all nodes
- GET /admin/nodes with empty registry returns empty list
- Each node in the response contains six fields (identity + operational state)
- Nodes with different statuses (HEALTHY, UNHEALTHY, DRAINING) all appear
- The response is a flat JSON array, not wrapped in an object
"""

from __future__ import annotations

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


class TestAdminNodesPopulated:
    """GET /admin/nodes with registered nodes returns node data."""

    def test_returns_200_with_two_nodes(
        self,
        client: TestClient,
        test_registry: NodeRegistry,
    ) -> None:
        """Two registered nodes return 200 with a list of two AdminNodeResponse objects."""
        test_registry.add(_make_node(node_id="node-1", model="llama-3"))
        test_registry.add(
            _make_node(
                node_id="node-2",
                endpoint="10.0.1.101:8000",
                model="mistral-7b",
            )
        )

        response = client.get("/admin/nodes")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    def test_each_node_has_exactly_six_fields(
        self,
        client: TestClient,
        test_registry: NodeRegistry,
    ) -> None:
        """Each node contains identity and operational state fields."""
        test_registry.add(_make_node())

        response = client.get("/admin/nodes")
        data = response.json()

        assert len(data) == 1
        node = data[0]
        assert set(node.keys()) == {
            "node_id",
            "endpoint",
            "model",
            "status",
            "active_connections",
            "circuit_breaker_state",
        }
        assert "last_heartbeat" not in node
        assert "capabilities" not in node

    def test_mixed_statuses_all_appear(
        self,
        client: TestClient,
        test_registry: NodeRegistry,
    ) -> None:
        """Nodes with HEALTHY, UNHEALTHY, and DRAINING statuses all appear."""
        test_registry.add(
            _make_node(node_id="h1", status=NodeStatus.HEALTHY, model="llama-3")
        )
        test_registry.add(
            _make_node(
                node_id="u1",
                endpoint="10.0.1.101:8000",
                status=NodeStatus.UNHEALTHY,
                model="mistral-7b",
            )
        )
        test_registry.add(
            _make_node(
                node_id="d1",
                endpoint="10.0.1.102:8000",
                status=NodeStatus.DRAINING,
                model="codellama",
            )
        )

        response = client.get("/admin/nodes")
        data = response.json()

        assert len(data) == 3
        statuses = {node["status"] for node in data}
        assert statuses == {"healthy", "unhealthy", "draining"}


class TestAdminNodesEmpty:
    """GET /admin/nodes with empty registry returns empty list."""

    def test_empty_registry_returns_empty_list(
        self,
        client: TestClient,
    ) -> None:
        """Empty registry returns 200 with an empty list."""
        response = client.get("/admin/nodes")

        assert response.status_code == 200
        data = response.json()
        assert data == []


class TestAdminNodesResponseShape:
    """GET /admin/nodes returns a flat JSON array."""

    def test_response_is_flat_array(
        self,
        client: TestClient,
        test_registry: NodeRegistry,
    ) -> None:
        """The response is a flat JSON array, not wrapped in an object."""
        test_registry.add(_make_node())

        response = client.get("/admin/nodes")
        data = response.json()

        # Must be a list, not a dict/object wrapper
        assert isinstance(data, list)
        assert len(data) == 1
        assert isinstance(data[0], dict)
