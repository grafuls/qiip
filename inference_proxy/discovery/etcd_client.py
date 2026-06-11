"""Thin wrapper around etcd3gw providing typed node operations.

This module is the **sole consumer** of ``etcd3gw`` in the codebase,
following the Dependency Inversion Principle (DIP): all other modules
depend on this wrapper rather than importing ``etcd3gw`` directly.

Per D-13: Encapsulates connection configuration and provides typed
methods for node operations.
Per D-14: Created from ``EtcdSettings`` (endpoints, node_prefix).
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from etcd3gw.client import Etcd3Client

from inference_proxy.config.settings import EtcdSettings


class EtcdClient:
    """Wrapper around ``etcd3gw.Etcd3Client`` for node discovery.

    Parses the first endpoint URL from ``EtcdSettings`` to extract
    host, port, and protocol for the underlying etcd HTTP gateway
    client.

    Attributes:
        prefix: The configured node key prefix (e.g., ``/nodes/``).
    """

    def __init__(self, settings: EtcdSettings) -> None:
        parsed = urlparse(settings.endpoints[0])
        self._client = Etcd3Client(
            host=parsed.hostname or "localhost",
            port=parsed.port or 2379,
            protocol=parsed.scheme or "http",
        )
        self._prefix = settings.node_prefix

    @property
    def prefix(self) -> str:
        """Return the configured node key prefix."""
        return self._prefix

    def get_prefix(self) -> list[tuple[bytes, dict[str, Any]]]:
        """Fetch all key-value pairs under the configured node prefix.

        Returns:
            A list of ``(value_bytes, metadata_dict)`` tuples where
            ``metadata_dict`` contains the key under ``metadata["key"]``.
        """
        return self._client.get_prefix(self._prefix)  # type: ignore[no-any-return]

    def watch_prefix(self) -> tuple[Any, Any]:
        """Start watching for changes under the configured node prefix.

        Returns:
            A tuple of ``(events_iterator, cancel_fn)``.  The iterator
            blocks on an internal ``queue.Queue`` and yields event dicts.
            Call ``cancel_fn()`` to stop the watch.
        """
        return self._client.watch_prefix(self._prefix)  # type: ignore[no-any-return]
