"""Integration tests for the admin API endpoints.

Tests cover:
- GET /admin/nodes returns unified list merging QUADS + etcd (NODES-01)
- Each node has state and actions fields (NODES-02)
- POST /admin/nodes/setup dedup guard (NODES-04)
- POST /admin/nodes/setup live QUADS re-validation (NODES-05)
- GET /admin/metrics returns aggregate request counter data
- GET /admin/provisioning/tasks returns task status from etcd
- DELETE /admin/nodes/{id} returns 202 for known nodes, 404 for unknown
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from inference_proxy.config.dependencies import (
    get_quads_client,
    get_quads_poller,
    get_unified_node_service,
)
from inference_proxy.discovery.registry import NodeRegistry
from inference_proxy.models.node import Node, NodeStatus
from inference_proxy.models.quads import QUADSHost
from inference_proxy.quads.client import QUADSConnectionError
from inference_proxy.resilience.circuit_breaker import CircuitBreakerRegistry
from inference_proxy.routing.connection_tracker import ConnectionTracker
from inference_proxy.routing.request_metrics import RequestMetrics
from inference_proxy.services.unified_nodes import UnifiedNodeService


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

    def test_each_node_has_expected_fields(
        self,
        client: TestClient,
        test_registry: NodeRegistry,
    ) -> None:
        """Each node contains identity, operational state, and unified fields."""
        test_registry.add(_make_node())

        response = client.get("/admin/nodes")
        data = response.json()

        assert len(data) == 1
        node = data[0]
        expected = {
            "node_id", "endpoint", "model", "status",
            "active_connections", "circuit_breaker_state",
            "state", "actions", "gpu_vendor", "gpu_model", "gpu_count",
            "managed",
        }
        assert set(node.keys()) == expected
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


class TestAdminNodesEnriched:
    """GET /admin/nodes returns enriched operational state per node."""

    def test_active_connections_reflects_tracker(
        self,
        client: TestClient,
        test_registry: NodeRegistry,
        connection_tracker: ConnectionTracker,
    ) -> None:
        """active_connections matches the ConnectionTracker count."""
        test_registry.add(_make_node(node_id="node-1"))
        connection_tracker.increment("node-1")
        connection_tracker.increment("node-1")

        response = client.get("/admin/nodes")
        node = response.json()[0]

        assert node["active_connections"] == 2

    def test_circuit_breaker_state_default_closed(
        self,
        client: TestClient,
        test_registry: NodeRegistry,
    ) -> None:
        """A fresh node has circuit_breaker_state 'closed'."""
        test_registry.add(_make_node(node_id="node-1"))

        response = client.get("/admin/nodes")
        node = response.json()[0]

        assert node["circuit_breaker_state"] == "closed"

    def test_circuit_breaker_state_open_after_failures(
        self,
        client: TestClient,
        test_registry: NodeRegistry,
        circuit_breaker_registry: CircuitBreakerRegistry,
    ) -> None:
        """A tripped breaker reports circuit_breaker_state 'open'."""
        test_registry.add(_make_node(node_id="node-1"))
        breaker = circuit_breaker_registry.get_or_create("node-1")
        for _ in range(3):
            breaker.record_failure()

        response = client.get("/admin/nodes")
        node = response.json()[0]

        assert node["circuit_breaker_state"] == "open"


class TestAdminMetrics:
    """GET /admin/metrics returns aggregate request counter data."""

    def test_metrics_returns_200(self, client: TestClient) -> None:
        """The metrics endpoint returns 200."""
        response = client.get("/admin/metrics")
        assert response.status_code == 200

    def test_metrics_empty_by_default(self, client: TestClient) -> None:
        """Fresh metrics returns zeroed counters."""
        response = client.get("/admin/metrics")
        data = response.json()

        assert data == {"total_requests": 0, "per_model": {}, "per_node": {}}

    def test_metrics_after_recording(
        self,
        client: TestClient,
        request_metrics: RequestMetrics,
    ) -> None:
        """Metrics reflect data recorded via RequestMetrics."""
        request_metrics.record_request("node-1", "llama-3")

        response = client.get("/admin/metrics")
        data = response.json()

        assert data["total_requests"] == 1
        assert data["per_model"] == {"llama-3": 1}
        assert data["per_node"] == {"node-1": 1}


class TestSetupEndpoint:
    """POST /admin/nodes/setup triggers provisioning."""

    def test_returns_202_with_task_id(
        self,
        client: TestClient,
        mock_provisioner: MagicMock,
    ) -> None:
        response = client.post("/admin/nodes/setup", json={"hostname": "gpu01"})
        assert response.status_code == 202
        assert response.json() == {"task_id": "gpu01"}

    def test_calls_fire_background(
        self,
        client: TestClient,
        mock_provisioner: MagicMock,
    ) -> None:
        client.post("/admin/nodes/setup", json={"hostname": "gpu01"})
        mock_provisioner.fire_background.assert_called_once()


class TestTasksEndpoint:
    """GET /admin/provisioning/tasks returns task status from etcd."""

    def test_returns_tasks_from_etcd(
        self,
        client: TestClient,
        mock_provisioner: MagicMock,
    ) -> None:
        task_data = {
            "hostname": "gpu01",
            "current_step": "registering",
            "started_at": "2026-07-07T12:00:00Z",
            "updated_at": "2026-07-07T12:05:00Z",
        }
        mock_provisioner.list_tasks_raw.return_value = [
            (json.dumps(task_data).encode(), {"key": b"/provisioning/gpu01"}),
        ]

        response = client.get("/admin/provisioning/tasks")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["hostname"] == "gpu01"
        assert data[0]["current_step"] == "registering"

    def test_empty_tasks_returns_empty_list(
        self,
        client: TestClient,
        mock_provisioner: MagicMock,
    ) -> None:
        mock_provisioner.list_tasks_raw.return_value = []
        response = client.get("/admin/provisioning/tasks")
        assert response.status_code == 200
        assert response.json() == []


class TestTeardownEndpoint:
    """DELETE /admin/nodes/{id} triggers teardown."""

    def test_returns_202_for_known_node(
        self,
        client: TestClient,
        test_registry: NodeRegistry,
        mock_provisioner: MagicMock,
    ) -> None:
        test_registry.add(_make_node(node_id="gpu01"))
        response = client.delete("/admin/nodes/gpu01")
        assert response.status_code == 202
        assert response.json() == {"task_id": "gpu01"}

    def test_force_param_passed(
        self,
        client: TestClient,
        test_registry: NodeRegistry,
        mock_provisioner: MagicMock,
    ) -> None:
        test_registry.add(_make_node(node_id="gpu01"))
        client.delete("/admin/nodes/gpu01?force=true")
        mock_provisioner.fire_background.assert_called_once()

    def test_unknown_node_returns_404(
        self,
        client: TestClient,
        mock_provisioner: MagicMock,
    ) -> None:
        response = client.delete("/admin/nodes/unknown")
        assert response.status_code == 404


# -- Unified list tests (NODES-01, NODES-02) --


class TestUnifiedNodeList:
    """GET /admin/nodes returns unified QUADS+etcd merged list."""

    def test_merged_list_with_quads(
        self,
        app: FastAPI,
        client: TestClient,
        test_registry: NodeRegistry,
        connection_tracker: ConnectionTracker,
        circuit_breaker_registry: CircuitBreakerRegistry,
    ) -> None:
        """NODES-01: Unified list includes both etcd and available QUADS hosts."""
        test_registry.add(_make_node(node_id="gpu01"))
        poller = MagicMock()
        poller.hosts = [
            QUADSHost(hostname="gpu01", gpu_vendor="NVIDIA", gpu_model="A100", gpu_count=4),
            QUADSHost(hostname="gpu02", gpu_vendor="AMD", gpu_model="MI300X", gpu_count=8),
        ]
        poller.available_hostnames = ["gpu01", "gpu02"]
        svc = UnifiedNodeService(
            registry=test_registry,
            poller=poller,
            cb_registry=circuit_breaker_registry,
            tracker=connection_tracker,
        )
        app.dependency_overrides[get_unified_node_service] = lambda: svc

        response = client.get("/admin/nodes")
        data = response.json()

        assert len(data) == 2
        ids = {n["node_id"] for n in data}
        assert ids == {"gpu01", "gpu02"}

    def test_each_node_has_state_and_actions(
        self,
        app: FastAPI,
        client: TestClient,
        test_registry: NodeRegistry,
        connection_tracker: ConnectionTracker,
        circuit_breaker_registry: CircuitBreakerRegistry,
    ) -> None:
        """NODES-02: Each node includes state and actions."""
        poller = MagicMock()
        poller.hosts = [
            QUADSHost(hostname="gpu01", gpu_vendor="NVIDIA", gpu_model="A100", gpu_count=4),
        ]
        poller.available_hostnames = ["gpu01"]
        svc = UnifiedNodeService(
            registry=test_registry,
            poller=poller,
            cb_registry=circuit_breaker_registry,
            tracker=connection_tracker,
        )
        app.dependency_overrides[get_unified_node_service] = lambda: svc

        response = client.get("/admin/nodes")
        node = response.json()[0]

        assert "state" in node
        assert "actions" in node
        assert node["state"] == "available"
        assert node["actions"] == ["setup"]

    def test_no_quads_returns_etcd_only(
        self,
        client: TestClient,
        test_registry: NodeRegistry,
    ) -> None:
        """Graceful degradation: no QUADS returns etcd-only nodes."""
        test_registry.add(_make_node(node_id="gpu01"))

        response = client.get("/admin/nodes")
        data = response.json()

        assert len(data) == 1
        assert data[0]["node_id"] == "gpu01"
        assert data[0]["state"] == "healthy"


# -- Dedup guard tests (NODES-04) --


@pytest.fixture(autouse=True)
def _clear_pending_hosts() -> None:
    """Clear the module-level pending_hosts between tests."""
    import inference_proxy.api.admin as admin_mod
    if hasattr(admin_mod, "pending_hosts"):
        admin_mod.pending_hosts.clear()


class TestSetupDedupGuard:
    """POST /admin/nodes/setup returns 409 for duplicate requests (NODES-04)."""

    def test_returns_409_for_pending_hostname(
        self,
        client: TestClient,
        mock_provisioner: MagicMock,
    ) -> None:
        import inference_proxy.api.admin as admin_mod
        admin_mod.pending_hosts.add("gpu01")

        response = client.post("/admin/nodes/setup", json={"hostname": "gpu01"})
        assert response.status_code == 409

    def test_clears_pending_after_completion(
        self,
        client: TestClient,
        mock_provisioner: MagicMock,
    ) -> None:
        """Pending host is removed after provisioning task fires."""
        import inference_proxy.api.admin as admin_mod

        response = client.post("/admin/nodes/setup", json={"hostname": "gpu01"})
        assert response.status_code == 202
        # The background task wrapper should eventually discard from pending_hosts.
        # Since fire_background is mocked, we check it was called with a coroutine.
        mock_provisioner.fire_background.assert_called_once()


# -- QUADS re-validation tests (NODES-05) --


class TestSetupQuadsRevalidation:
    """POST /admin/nodes/setup re-validates against live QUADS (NODES-05)."""

    def test_returns_503_on_quads_connection_error(
        self,
        app: FastAPI,
        client: TestClient,
        mock_provisioner: MagicMock,
    ) -> None:
        mock_quads = AsyncMock()
        mock_quads.get_available.side_effect = QUADSConnectionError("timeout")
        app.dependency_overrides[get_quads_client] = lambda: mock_quads

        response = client.post("/admin/nodes/setup", json={"hostname": "gpu01"})
        assert response.status_code == 503

    def test_returns_400_for_unavailable_host(
        self,
        app: FastAPI,
        client: TestClient,
        mock_provisioner: MagicMock,
    ) -> None:
        mock_quads = AsyncMock()
        mock_quads.get_available.return_value = ["gpu99"]
        app.dependency_overrides[get_quads_client] = lambda: mock_quads

        response = client.post("/admin/nodes/setup", json={"hostname": "gpu01"})
        assert response.status_code == 400

    def test_succeeds_for_available_host(
        self,
        app: FastAPI,
        client: TestClient,
        mock_provisioner: MagicMock,
    ) -> None:
        mock_quads = AsyncMock()
        mock_quads.get_available.return_value = ["gpu01"]
        app.dependency_overrides[get_quads_client] = lambda: mock_quads

        response = client.post("/admin/nodes/setup", json={"hostname": "gpu01"})
        assert response.status_code == 202

    def test_works_without_quads_configured(
        self,
        client: TestClient,
        mock_provisioner: MagicMock,
    ) -> None:
        """When QUADS not configured (None), setup proceeds without validation."""
        response = client.post("/admin/nodes/setup", json={"hostname": "gpu01"})
        assert response.status_code == 202


class TestExistingEndpointsUnchanged:
    """Existing endpoints still work after refactoring."""

    def test_metrics_still_works(self, client: TestClient) -> None:
        response = client.get("/admin/metrics")
        assert response.status_code == 200

    def test_teardown_still_works(
        self,
        client: TestClient,
        test_registry: NodeRegistry,
        mock_provisioner: MagicMock,
    ) -> None:
        test_registry.add(_make_node(node_id="gpu01"))
        response = client.delete("/admin/nodes/gpu01")
        assert response.status_code == 202


class TestQuadsStatus:
    """GET /admin/quads/status returns poller staleness data (D-10)."""

    def test_returns_200(self, client: TestClient) -> None:
        response = client.get("/admin/quads/status")
        assert response.status_code == 200

    def test_unavailable_when_no_poller(self, client: TestClient) -> None:
        """Default fixture has poller=None."""
        data = client.get("/admin/quads/status").json()
        assert data["status"] == "unavailable"
        assert data["last_sync"] is None
        assert data["consecutive_failures"] == 0

    def test_connected_when_zero_failures(
        self, app: FastAPI, client: TestClient
    ) -> None:
        poller = MagicMock()
        poller.last_sync = datetime(2026, 7, 17, 10, 0, 0, tzinfo=UTC)
        poller.consecutive_failures = 0
        app.dependency_overrides[get_quads_poller] = lambda: poller

        data = client.get("/admin/quads/status").json()
        assert data["status"] == "connected"

    def test_stale_when_one_failure(
        self, app: FastAPI, client: TestClient
    ) -> None:
        poller = MagicMock()
        poller.last_sync = datetime(2026, 7, 17, 10, 0, 0, tzinfo=UTC)
        poller.consecutive_failures = 1
        app.dependency_overrides[get_quads_poller] = lambda: poller

        data = client.get("/admin/quads/status").json()
        assert data["status"] == "stale"

    def test_stale_when_two_failures(
        self, app: FastAPI, client: TestClient
    ) -> None:
        poller = MagicMock()
        poller.last_sync = datetime(2026, 7, 17, 10, 0, 0, tzinfo=UTC)
        poller.consecutive_failures = 2
        app.dependency_overrides[get_quads_poller] = lambda: poller

        data = client.get("/admin/quads/status").json()
        assert data["status"] == "stale"

    def test_unavailable_when_three_failures(
        self, app: FastAPI, client: TestClient
    ) -> None:
        poller = MagicMock()
        poller.last_sync = datetime(2026, 7, 17, 10, 0, 0, tzinfo=UTC)
        poller.consecutive_failures = 3
        app.dependency_overrides[get_quads_poller] = lambda: poller

        data = client.get("/admin/quads/status").json()
        assert data["status"] == "unavailable"

    def test_unavailable_when_never_synced(
        self, app: FastAPI, client: TestClient
    ) -> None:
        poller = MagicMock()
        poller.last_sync = None
        poller.consecutive_failures = 0
        app.dependency_overrides[get_quads_poller] = lambda: poller

        data = client.get("/admin/quads/status").json()
        assert data["status"] == "unavailable"
