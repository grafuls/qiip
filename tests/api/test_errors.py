"""Unit tests for the proxy error mapping functions.

Tests cover mapping of httpx exception types to OpenAI-compatible error
responses and the no-nodes-available helper.
"""

from __future__ import annotations

import httpx

from inference_proxy.api.errors import map_proxy_error, no_nodes_error


class TestMapProxyError:
    """map_proxy_error maps exceptions to (status_code, ErrorResponse) tuples."""

    def test_connect_error_returns_502(self) -> None:
        exc = httpx.ConnectError("Connection refused")

        status, response = map_proxy_error(exc)

        assert status == 502
        assert response.error.type == "upstream_error"
        assert response.error.code == "backend_unavailable"
        assert "connect" in response.error.message.lower()

    def test_timeout_returns_504(self) -> None:
        exc = httpx.ReadTimeout("read timed out")

        status, response = map_proxy_error(exc)

        assert status == 504
        assert response.error.type == "upstream_error"
        assert response.error.code == "backend_timeout"
        assert "timed out" in response.error.message.lower()

    def test_http_status_error_returns_upstream_status(self) -> None:
        mock_request = httpx.Request("POST", "http://node1:8000/v1/chat/completions")
        mock_response = httpx.Response(
            status_code=422,
            text="Unprocessable Entity",
            request=mock_request,
        )
        exc = httpx.HTTPStatusError(
            "422 Unprocessable Entity",
            request=mock_request,
            response=mock_response,
        )

        status, response = map_proxy_error(exc)

        assert status == 422
        assert response.error.type == "upstream_error"
        assert response.error.code == "422"
        assert "Unprocessable Entity" in response.error.message

    def test_generic_exception_returns_500(self) -> None:
        exc = RuntimeError("something went wrong")

        status, response = map_proxy_error(exc)

        assert status == 500
        assert response.error.type == "server_error"
        assert response.error.code == "internal_error"
        assert "internal" in response.error.message.lower()


class TestNoNodesError:
    """no_nodes_error returns a 503 with no_nodes code."""

    def test_returns_503(self) -> None:
        status, response = no_nodes_error()

        assert status == 503
        assert response.error.code == "no_nodes"
        assert "No inference nodes available" in response.error.message
        assert response.error.type == "server_error"
