"""FastAPI application factory and entry point.

Usage::

    # Development server
    uv run uvicorn inference_proxy.main:app --host 0.0.0.0 --port 8000

    # Programmatic access (tests)
    from inference_proxy.main import create_app
    app = create_app()
"""

from __future__ import annotations

import threading
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from inference_proxy.config.dependencies import get_settings
from inference_proxy.config.logging import configure_logging
from inference_proxy.discovery.etcd_client import EtcdClient
from inference_proxy.discovery.registry import NodeRegistry
from inference_proxy.discovery.serializer import node_from_etcd
from inference_proxy.discovery.watcher import run_watcher

logger = structlog.get_logger()


def _initial_load(etcd_client: EtcdClient, registry: NodeRegistry) -> None:
    """Fetch all nodes from etcd and populate the registry.

    Per D-05: synchronous initial fetch is acceptable during startup.
    Per D-09: if etcd is unavailable, start with an empty registry and
    log a warning -- the gateway remains responsive but routing will
    fail until nodes appear via the watch thread.

    Args:
        etcd_client: The etcd client wrapper.
        registry: The node registry to populate.
    """
    try:
        results = etcd_client.get_prefix()
        count = 0
        for value_bytes, metadata in results:
            key = metadata["key"]
            if isinstance(key, bytes):
                key = key.decode("utf-8")
            node = node_from_etcd(key, value_bytes, etcd_client.prefix)
            if node is not None:
                registry.add(node)
                count += 1
        logger.info("initial node load complete", node_count=count)
    except Exception:
        logger.warning(
            "etcd unavailable at startup, starting with empty registry",
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: logging, service discovery, and shutdown.

    Startup:
        1. Configure structured logging
        2. Create etcd client and node registry
        3. Fetch initial node list from etcd (per D-05)
        4. Start watch thread for real-time updates (per D-03)
        5. Store registry in ``app.state`` for dependency injection (per D-07)

    Shutdown:
        1. Signal the watch thread to stop via ``threading.Event`` (per D-10)
        2. Join the watch thread with timeout
    """
    configure_logging()

    settings = get_settings()
    etcd_client = EtcdClient(settings.etcd)
    registry = NodeRegistry()

    _initial_load(etcd_client, registry)

    stop_event = threading.Event()
    watch_thread = threading.Thread(
        target=run_watcher,
        args=(etcd_client, registry, stop_event),
        daemon=True,
    )
    watch_thread.start()

    app.state.registry = registry

    yield

    stop_event.set()
    watch_thread.join(timeout=10)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance.

    Returns:
        A fully configured FastAPI application with registered routes.
    """
    application = FastAPI(
        title="QUADS LLM Inference Proxy",
        version="0.1.0",
        lifespan=lifespan,
    )

    @application.get("/health")
    async def health() -> JSONResponse:
        """Return gateway health status."""
        return JSONResponse(content={"status": "ok"})

    return application


app = create_app()
