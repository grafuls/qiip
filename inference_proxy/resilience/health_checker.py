"""Background health checker thread for vLLM node probing.

Runs in a dedicated ``threading.Thread`` (per D-01) started during
FastAPI lifespan startup.  Probes each registered node's ``/health``
endpoint using synchronous HTTP calls (per D-02) and updates the
``NodeRegistry`` status accordingly.

**Failure tracking** (per D-03): A node is marked UNHEALTHY after
``failure_threshold`` consecutive probe failures.

**Recovery** (per D-04): A node is restored to HEALTHY after 1
successful probe.  On recovery, the circuit breaker for that node
is reset (per D-08).

**Timeout** (per T-05-02): Health probes use a short 5-second timeout
so a slow node cannot block the checker from probing others.

Usage::

    stop_event = threading.Event()
    thread = threading.Thread(
        target=run_health_checker,
        args=(registry, cb_registry, stop_event),
        kwargs={"interval": 30.0, "failure_threshold": 3},
        daemon=True,
    )
    thread.start()

    # On shutdown:
    stop_event.set()
    thread.join(timeout=10)
"""

from __future__ import annotations

import threading

import httpx
import structlog

from inference_proxy.discovery.registry import NodeRegistry
from inference_proxy.models.node import Node, NodeStatus
from inference_proxy.resilience.circuit_breaker import CircuitBreakerRegistry

logger = structlog.get_logger()

_PROBE_TIMEOUT: float = 5.0


def run_health_checker(
    registry: NodeRegistry,
    circuit_breaker_registry: CircuitBreakerRegistry,
    stop_event: threading.Event,
    interval: float = 30.0,
    failure_threshold: int = 3,
) -> None:
    """Probe registered nodes and manage HEALTHY/UNHEALTHY transitions.

    Runs in a dedicated thread.  Stops when *stop_event* is set.

    Args:
        registry: The node registry containing nodes to probe.
        circuit_breaker_registry: Registry of per-node circuit breakers;
            reset on recovery (per D-08).
        stop_event: A ``threading.Event`` signalling graceful shutdown.
        interval: Seconds between probe cycles (default 30).
        failure_threshold: Consecutive failures before marking a node
            UNHEALTHY (default 3, per D-03).
    """
    consecutive_failures: dict[str, int] = {}

    client = httpx.Client(timeout=_PROBE_TIMEOUT)
    try:
        while not stop_event.is_set():
            _probe_all_nodes(
                registry,
                circuit_breaker_registry,
                client,
                consecutive_failures,
                failure_threshold,
            )
            if stop_event.wait(timeout=interval):
                break
    finally:
        client.close()


def _probe_all_nodes(
    registry: NodeRegistry,
    circuit_breaker_registry: CircuitBreakerRegistry,
    client: httpx.Client,
    consecutive_failures: dict[str, int],
    failure_threshold: int,
) -> None:
    """Probe every node in the registry once.

    Separated from the main loop for testability and to honour the
    Single Responsibility Principle: the loop manages timing, this
    function manages probing logic.
    """
    nodes = registry.get_all()
    for node in nodes:
        _probe_node(
            node_id=node.node_id,
            endpoint=node.endpoint,
            current_status=node.status,
            registry=registry,
            circuit_breaker_registry=circuit_breaker_registry,
            client=client,
            consecutive_failures=consecutive_failures,
            failure_threshold=failure_threshold,
            node=node,
        )


def _probe_node(
    *,
    node_id: str,
    endpoint: str,
    current_status: NodeStatus,
    registry: NodeRegistry,
    circuit_breaker_registry: CircuitBreakerRegistry,
    client: httpx.Client,
    consecutive_failures: dict[str, int],
    failure_threshold: int,
    node: Node,
) -> None:
    """Probe a single node and update its status if needed.

    Args:
        node_id: The node's unique identifier.
        endpoint: The node's HTTP endpoint (host:port).
        current_status: The node's current status in the registry.
        registry: The node registry to update on status changes.
        circuit_breaker_registry: Circuit breaker registry for resets.
        client: The synchronous HTTP client for probing.
        consecutive_failures: Mutable dict tracking per-node failure counts.
        failure_threshold: Consecutive failures before marking UNHEALTHY.
        node: The original Node object (used for model_copy).
    """
    try:
        url = f"http://{endpoint}/health"
        response = client.get(url)
        if response.status_code == 200:
            _handle_probe_success(
                node_id=node_id,
                current_status=current_status,
                registry=registry,
                circuit_breaker_registry=circuit_breaker_registry,
                consecutive_failures=consecutive_failures,
                node=node,
            )
        else:
            _handle_probe_failure(
                node_id=node_id,
                current_status=current_status,
                registry=registry,
                consecutive_failures=consecutive_failures,
                failure_threshold=failure_threshold,
                reason=f"non-200 status: {response.status_code}",
                node=node,
            )
    except Exception:
        _handle_probe_failure(
            node_id=node_id,
            current_status=current_status,
            registry=registry,
            consecutive_failures=consecutive_failures,
            failure_threshold=failure_threshold,
            reason="probe exception",
            node=node,
        )
        logger.debug(
            "health probe failed with exception",
            node_id=node_id,
            exc_info=True,
        )


def _handle_probe_success(
    *,
    node_id: str,
    current_status: NodeStatus,
    registry: NodeRegistry,
    circuit_breaker_registry: CircuitBreakerRegistry,
    consecutive_failures: dict[str, int],
    node: Node,
) -> None:
    """Handle a successful health probe for a node."""
    consecutive_failures[node_id] = 0
    if current_status != NodeStatus.HEALTHY:
        updated_node = node.model_copy(update={"status": NodeStatus.HEALTHY})
        registry.add(updated_node)
        circuit_breaker_registry.reset(node_id)
        logger.info(
            "node recovered to healthy",
            node_id=node_id,
            previous_status=str(current_status),
        )
    else:
        logger.debug("health probe succeeded", node_id=node_id)


def _handle_probe_failure(
    *,
    node_id: str,
    current_status: NodeStatus,
    registry: NodeRegistry,
    consecutive_failures: dict[str, int],
    failure_threshold: int,
    reason: str,
    node: Node,
) -> None:
    """Handle a failed health probe for a node."""
    count = consecutive_failures.get(node_id, 0) + 1
    consecutive_failures[node_id] = count
    logger.debug(
        "health probe failed",
        node_id=node_id,
        consecutive_failures=count,
        reason=reason,
    )
    if count >= failure_threshold and current_status == NodeStatus.HEALTHY:
        updated_node = node.model_copy(update={"status": NodeStatus.UNHEALTHY})
        registry.add(updated_node)
        logger.info(
            "node marked unhealthy",
            node_id=node_id,
            consecutive_failures=count,
            threshold=failure_threshold,
        )
