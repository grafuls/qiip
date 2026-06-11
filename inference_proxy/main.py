"""FastAPI application factory and entry point.

Usage::

    # Development server
    uv run uvicorn inference_proxy.main:app --host 0.0.0.0 --port 8000

    # Programmatic access (tests)
    from inference_proxy.main import create_app
    app = create_app()
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from inference_proxy.config.logging import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context manager.

    Handles startup and shutdown hooks.  Future phases will add
    service discovery initialization, health-check tasks, and
    graceful connection draining here.
    """
    configure_logging()
    yield


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
