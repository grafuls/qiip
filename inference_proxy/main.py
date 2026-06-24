"""FastAPI application factory and entry point.

Usage::

    # Development server
    uv run uvicorn inference_proxy.main:app --host 0.0.0.0 --port 8000

    # Programmatic access (tests)
    from inference_proxy.main import create_app
    app = create_app()
"""

from __future__ import annotations

import logging
import threading
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import httpx
import structlog
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from inference_proxy.api.routes import router
from inference_proxy.config.dependencies import get_settings
from inference_proxy.config.logging import configure_logging
from inference_proxy.config.settings import Settings
from inference_proxy.discovery.etcd_client import EtcdClient
from inference_proxy.discovery.registry import NodeRegistry
from inference_proxy.discovery.serializer import node_from_etcd
from inference_proxy.discovery.watcher import run_watcher
from inference_proxy.proxy.client import ProxyClient
from inference_proxy.routing.connection_tracker import ConnectionTracker
from inference_proxy.routing.node_selector import NodeSelector

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
            exc_info=True,
        )


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application instance.

    Args:
        settings: Optional settings instance. When ``None`` (the default),
            settings are loaded from the environment via ``get_settings()``.
            Pass an explicit instance in tests to avoid hitting real
            etcd during lifespan startup.

    Returns:
        A fully configured FastAPI application with registered routes.
    """
    resolved_settings = settings or get_settings()

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
        configure_logging(
            json_output=resolved_settings.logging.json_output,
            log_level=getattr(
                logging, resolved_settings.logging.level.upper(), logging.INFO
            ),
        )
        etcd_client = EtcdClient(resolved_settings.etcd)
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

        connection_tracker = ConnectionTracker()
        node_selector = NodeSelector(registry, connection_tracker)
        app.state.node_selector = node_selector

        http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=resolved_settings.proxy.connect_timeout,
                read=resolved_settings.proxy.read_timeout,
                write=resolved_settings.proxy.write_timeout,
                pool=resolved_settings.proxy.pool_timeout,
            ),
            limits=httpx.Limits(
                max_connections=resolved_settings.proxy.max_connections,
                max_keepalive_connections=resolved_settings.proxy.max_keepalive_connections,
                keepalive_expiry=resolved_settings.proxy.keepalive_expiry,
            ),
        )
        proxy_client = ProxyClient(http_client)
        app.state.proxy_client = proxy_client

        yield

        await http_client.aclose()
        stop_event.set()
        watch_thread.join(timeout=10)

    application = FastAPI(
        title="QUADS LLM Inference Proxy",
        version="0.1.0",
        lifespan=lifespan,
    )

    @application.get("/health")
    async def health() -> JSONResponse:
        """Return gateway health status with registered node count."""
        registry: NodeRegistry = application.state.registry
        return JSONResponse(
            content={
                "status": "ok",
                "nodes_registered": len(registry.get_all()),
            }
        )

    application.include_router(router)

    return application


app = create_app()
