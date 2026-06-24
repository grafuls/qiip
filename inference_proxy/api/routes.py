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

import json
from typing import Any, AsyncGenerator

import structlog
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from fastapi.sse import EventSourceResponse, format_sse_event
from httpx_sse import aconnect_sse

from inference_proxy.api.errors import (
    map_proxy_error,
    model_not_found_error,
    model_unavailable_error,
    no_nodes_error,
)
from inference_proxy.config.dependencies import get_node_selector, get_proxy_client
from inference_proxy.models.node import NodeStatus
from inference_proxy.models.openai import ChatCompletionRequest, CompletionRequest
from inference_proxy.proxy.client import ProxyClient
from inference_proxy.routing.node_selector import NodeSelector

logger = structlog.get_logger()

router = APIRouter()


def _select_error(
    model: str | None,
    node_selector: NodeSelector,
) -> tuple[int, Any]:
    """Return the appropriate error when node selection fails.

    Distinguishes between:
    - 503 no_nodes: no nodes registered at all
    - 404 model_not_found: nodes exist but none (any status) serve the model
    - 503 model_unavailable: nodes serve the model but all are draining/unhealthy
    """
    all_nodes = node_selector._registry.get_all()
    if not all_nodes:
        return no_nodes_error()
    if model and not node_selector.has_model(model):
        return model_not_found_error(model)
    if model and node_selector.has_model(model):
        return model_unavailable_error(model)
    return no_nodes_error()


async def _proxy_non_streaming(
    endpoint_path: str,
    body: dict[str, Any],
    node_selector: NodeSelector,
    proxy: ProxyClient,
) -> JSONResponse:
    """Forward a non-streaming request to a vLLM backend and return JSON."""
    model = body.get("model")
    node = node_selector.select(model=model)
    if node is None:
        status, error_resp = _select_error(model, node_selector)
        return JSONResponse(content=error_resp.model_dump(), status_code=status)

    url = f"http://{node.endpoint}{endpoint_path}"

    try:
        response = await proxy.forward("POST", url, body)
        try:
            content = response.json()
        except (json.JSONDecodeError, ValueError):
            content = {"raw": response.text}
        return JSONResponse(content=content, status_code=response.status_code)
    except Exception as exc:
        status, error_resp = map_proxy_error(exc)
        return JSONResponse(content=error_resp.model_dump(), status_code=status)


@router.post("/v1/chat/completions", response_model=None)
async def chat_completions(
    request: ChatCompletionRequest,
    node_selector: NodeSelector = Depends(get_node_selector),
    proxy: ProxyClient = Depends(get_proxy_client),
) -> JSONResponse | EventSourceResponse:
    """Proxy a chat completion request to a vLLM backend.

    When ``stream`` is true, returns an SSE stream of token chunks.
    Otherwise, returns the full JSON response from the backend.
    """
    body = request.model_dump(exclude_none=True)
    if request.stream:
        return await _stream_completion(
            endpoint_path="/v1/chat/completions",
            body=body,
            node_selector=node_selector,
            proxy=proxy,
        )
    return await _proxy_non_streaming("/v1/chat/completions", body, node_selector, proxy)


@router.post("/v1/completions", response_model=None)
async def text_completions(
    request: CompletionRequest,
    node_selector: NodeSelector = Depends(get_node_selector),
    proxy: ProxyClient = Depends(get_proxy_client),
) -> JSONResponse | EventSourceResponse:
    """Proxy a text completion request to a vLLM backend.

    When ``stream`` is true, returns an SSE stream of token chunks.
    Otherwise, returns the full JSON response from the backend.
    """
    body = request.model_dump(exclude_none=True)
    if request.stream:
        return await _stream_completion(
            endpoint_path="/v1/completions",
            body=body,
            node_selector=node_selector,
            proxy=proxy,
        )
    return await _proxy_non_streaming("/v1/completions", body, node_selector, proxy)


@router.get("/v1/models")
async def list_models(
    node_selector: NodeSelector = Depends(get_node_selector),
) -> JSONResponse:
    """Return an OpenAI-compatible list of available models.

    Aggregates model names from all healthy registered nodes,
    deduplicating by model name.  DRAINING nodes are excluded so
    clients only see models that can accept new requests.
    """
    nodes = node_selector._registry.get_all()
    models_seen: dict[str, dict[str, str | int]] = {}

    for node in nodes:
        if node.status != NodeStatus.HEALTHY:
            continue
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
    body: dict[str, Any],
    node_selector: NodeSelector,
    proxy: ProxyClient,
) -> JSONResponse | EventSourceResponse:
    """Stream SSE events from a vLLM backend to the client.

    Consumes upstream SSE events via ``httpx-sse`` and re-emits them
    using FastAPI's ``EventSourceResponse``.

    Uses ``format_sse_event(data_str=...)`` to avoid double JSON encoding
    (upstream data is already JSON-serialised by vLLM).
    """
    model = body.get("model")
    node = node_selector.select(model=model)
    if node is None:
        status, error_resp = _select_error(model, node_selector)
        return JSONResponse(content=error_resp.model_dump(), status_code=status)

    url = f"http://{node.endpoint}{endpoint_path}"

    async def event_generator() -> AsyncGenerator[bytes, None]:
        try:
            async with aconnect_sse(
                proxy.client, "POST", url, json=body
            ) as event_source:
                event_source.response.raise_for_status()
                async for sse in event_source.aiter_sse():
                    if sse.data == "[DONE]":
                        yield format_sse_event(data_str="[DONE]")
                        return
                    yield format_sse_event(data_str=sse.data)
        except Exception as exc:
            logger.error("streaming proxy error", error=str(exc), url=url)
            _, error_resp = map_proxy_error(exc)
            error_json = json.dumps(error_resp.model_dump())
            yield format_sse_event(data_str=error_json)
            yield format_sse_event(data_str="[DONE]")

    return EventSourceResponse(event_generator())
