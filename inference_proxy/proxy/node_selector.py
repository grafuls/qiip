"""Simple node selection for Phase 3 (first available healthy node).

This is a pure function module following the same pattern as
``inference_proxy.discovery.serializer``.  Phase 4 will replace the
selection strategy with a more sophisticated approach (e.g.,
least-connections routing) without modifying callers -- only the
implementation of ``select_node`` changes.
"""

from __future__ import annotations

import structlog

from inference_proxy.discovery.registry import NodeRegistry
from inference_proxy.models.node import Node, NodeStatus

logger = structlog.get_logger()


def select_node(registry: NodeRegistry) -> Node | None:
    """Return the first healthy node from the registry, or ``None``.

    Filters all registered nodes to those with ``NodeStatus.HEALTHY``
    and returns the first match.  Returns ``None`` when no healthy
    nodes are available.

    Args:
        registry: The node registry to select from.

    Returns:
        A healthy ``Node`` or ``None`` if none are available.
    """
    nodes = registry.get_all()
    healthy = [n for n in nodes if n.status == NodeStatus.HEALTHY]

    if not healthy:
        logger.warning("no healthy nodes available", total_nodes=len(nodes))
        return None

    selected = healthy[0]
    logger.debug(
        "selected node",
        node_id=selected.node_id,
        endpoint=selected.endpoint,
        healthy_count=len(healthy),
    )
    return selected
