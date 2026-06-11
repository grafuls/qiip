"""OpenAI-compatible API route handlers for the inference proxy.

Provides FastAPI route handlers for:
- POST /v1/chat/completions (streaming + non-streaming)
- POST /v1/completions (streaming + non-streaming)
- GET /v1/models (aggregated model listing from registry)

Route handlers depend on abstractions (ProxyClient, NodeRegistry) via
dependency injection, following the Dependency Inversion Principle.

Non-streaming requests use ProxyClient.forward() for JSON pass-through.
Streaming requests use httpx-sse for upstream SSE consumption and
FastAPI's EventSourceResponse for downstream re-emission.
"""

from __future__ import annotations

from typing import AsyncGenerator

import structlog
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from fastapi.sse import EventSourceResponse, ServerSentEvent
from httpx_sse import aconnect_sse

from inference_proxy.api.errors import map_proxy_error, no_nodes_error
from inference_proxy.config.dependencies import get_proxy_client, get_registry
from inference_proxy.discovery.registry import NodeRegistry
from inference_proxy.models.openai import ChatCompletionRequest, CompletionRequest
from inference_proxy.proxy.client import ProxyClient
from inference_proxy.proxy.node_selector import select_node

logger = structlog.get_logger()

router = APIRouter()


@router.post("/v1/chat/completions", response_model=None)
async def chat_completions(
    request: ChatCompletionRequest,
    registry: NodeRegistry = Depends(get_registry),
    proxy: ProxyClient = Depends(get_proxy_client),
) -> JSONResponse | EventSourceResponse:
    """Proxy a chat completion request to a vLLM backend.

    When ``stream`` is true, returns an SSE stream of token chunks.
    Otherwise, returns the full JSON response from the backend.
    """
    if request.stream:
        return await _stream_completion(
            endpoint_path="/v1/chat/completions",
            body=request.model_dump(exclude_none=True),
            registry=registry,
            proxy=proxy,
        )

    node = select_node(registry)
    if node is None:
        status, error_resp = no_nodes_error()
        return JSONResponse(content=error_resp.model_dump(), status_code=status)

    url = f"http://{node.endpoint}/v1/chat/completions"
    body = request.model_dump(exclude_none=True)

    try:
        response = await proxy.forward("POST", url, body)
        return JSONResponse(
            content=response.json(),
            status_code=response.status_code,
        )
    except Exception as exc:
        status, error_resp = map_proxy_error(exc)
        return JSONResponse(content=error_resp.model_dump(), status_code=status)


@router.post("/v1/completions", response_model=None)
async def text_completions(
    request: CompletionRequest,
    registry: NodeRegistry = Depends(get_registry),
    proxy: ProxyClient = Depends(get_proxy_client),
) -> JSONResponse | EventSourceResponse:
    """Proxy a text completion request to a vLLM backend.

    When ``stream`` is true, returns an SSE stream of token chunks.
    Otherwise, returns the full JSON response from the backend.
    """
    if request.stream:
        return await _stream_completion(
            endpoint_path="/v1/completions",
            body=request.model_dump(exclude_none=True),
            registry=registry,
            proxy=proxy,
        )

    node = select_node(registry)
    if node is None:
        status, error_resp = no_nodes_error()
        return JSONResponse(content=error_resp.model_dump(), status_code=status)

    url = f"http://{node.endpoint}/v1/completions"
    body = request.model_dump(exclude_none=True)

    try:
        response = await proxy.forward("POST", url, body)
        return JSONResponse(
            content=response.json(),
            status_code=response.status_code,
        )
    except Exception as exc:
        status, error_resp = map_proxy_error(exc)
        return JSONResponse(content=error_resp.model_dump(), status_code=status)


@router.get("/v1/models")
async def list_models(
    registry: NodeRegistry = Depends(get_registry),
) -> JSONResponse:
    """Return an OpenAI-compatible list of available models.

    Aggregates model names from all registered nodes, deduplicating
    by model name.  Returns an empty list when no nodes have models.
    """
    nodes = registry.get_all()
    models_seen: dict[str, dict[str, str | int]] = {}

    for node in nodes:
        if node.model and node.model not in models_seen:
            models_seen[node.model] = {
                "id": node.model,
                "object": "model",
                "created": 0,
                "owned_by": "vllm",
            }

    return JSONResponse(
        content={
            "object": "list",
            "data": list(models_seen.values()),
        }
    )


async def _stream_completion(
    endpoint_path: str,
    body: dict,  # type: ignore[type-arg]
    registry: NodeRegistry,
    proxy: ProxyClient,
) -> JSONResponse | EventSourceResponse:
    """Stream SSE events from a vLLM backend to the client.

    Consumes upstream SSE events via ``httpx-sse`` and re-emits them
    using FastAPI's ``EventSourceResponse``.

    Uses ``ServerSentEvent(raw_data=...)`` to avoid double JSON encoding
    (upstream data is already JSON-serialised by vLLM).

    Args:
        endpoint_path: The vLLM endpoint path (e.g., ``/v1/chat/completions``).
        body: The JSON-serialisable request body.
        registry: The node registry for node selection.
        proxy: The proxy client wrapping httpx.AsyncClient.

    Returns:
        An ``EventSourceResponse`` streaming SSE events, or a ``JSONResponse``
        with an error if no nodes are available.
    """
    node = select_node(registry)
    if node is None:
        status, error_resp = no_nodes_error()
        return JSONResponse(content=error_resp.model_dump(), status_code=status)

    url = f"http://{node.endpoint}{endpoint_path}"

    async def event_generator() -> AsyncGenerator[ServerSentEvent, None]:
        try:
            async with aconnect_sse(
                proxy.client, "POST", url, json=body
            ) as event_source:
                event_source.response.raise_for_status()
                async for sse in event_source.aiter_sse():
                    if sse.data == "[DONE]":
                        yield ServerSentEvent(raw_data="[DONE]")
                        break
                    yield ServerSentEvent(raw_data=sse.data)
        except Exception as exc:
            logger.error(
                "streaming proxy error",
                error=str(exc),
                url=url,
            )

    return EventSourceResponse(event_generator())
