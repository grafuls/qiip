# Phase 21: Redfish Client & Configuration - Pattern Map

**Mapped:** 2026-07-21
**Files analyzed:** 8 new/modified files
**Analogs found:** 8 / 8

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `inference_proxy/redfish/__init__.py` | config | -- | `inference_proxy/quads/__init__.py` | exact |
| `inference_proxy/redfish/client.py` | service | request-response | `inference_proxy/quads/client.py` | exact |
| `inference_proxy/redfish/errors.py` | utility | transform | `inference_proxy/api/errors.py` | role-match |
| `inference_proxy/config/settings.py` (modify) | config | -- | self (`QUADSSettings` block) | exact |
| `inference_proxy/config/dependencies.py` (modify) | config | -- | self (`get_quads_client`) | exact |
| `inference_proxy/main.py` (modify) | config | -- | self (QUADS lifespan block) | exact |
| `tests/redfish/__init__.py` | test | -- | `tests/quads/__init__.py` | exact |
| `tests/redfish/test_client.py` | test | request-response | `tests/quads/test_client.py` | exact |

## Pattern Assignments

### `inference_proxy/redfish/__init__.py` (config, package init)

**Analog:** `inference_proxy/quads/__init__.py`

Empty file. No content needed.

---

### `inference_proxy/redfish/client.py` (service, request-response)

**Analog:** `inference_proxy/quads/client.py`

**Imports pattern** (lines 1-9):
```python
from __future__ import annotations

from typing import Any

import httpx
import structlog

logger = structlog.get_logger()
```

**Exception class pattern** (lines 24-25):
```python
class QUADSConnectionError(Exception):
    """Raised when the QUADS API is unreachable or returns an error."""
```

**Constructor injection pattern** (lines 33-43):
```python
class QUADSClient:
    """Async client for the QUADS REST API.

    Args:
        http_client: A pre-built httpx.AsyncClient (lifecycle managed externally).
        base_url: QUADS server base URL (e.g. ``https://quads.example.com``).
    """

    def __init__(self, http_client: httpx.AsyncClient, base_url: str) -> None:
        self._client = http_client
        self._base_url = base_url.rstrip("/")
```

**Core GET + error wrapping pattern** (lines 90-98):
```python
async def _get(self, path: str, params: dict[str, str] | None = None) -> Any:
    """GET a JSON endpoint, wrapping errors in QUADSConnectionError."""
    url = f"{self._base_url}{path}"
    try:
        resp = await self._client.get(url, params=params)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise QUADSConnectionError(str(exc)) from exc
    return resp.json()
```

---

### `inference_proxy/redfish/errors.py` (utility, transform)

**Analog:** `inference_proxy/api/errors.py`

**Error mapping pattern** (lines 18-71):
```python
def map_proxy_error(exc: Exception) -> tuple[int, ErrorResponse]:
    if isinstance(exc, httpx.ConnectError):
        # ...
    if isinstance(exc, httpx.TimeoutException):
        # ...
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        response_text = exc.response.text
        safe_message = response_text[:200] if response_text else ""
        # ...
```

Key patterns to copy: isinstance dispatch, `:200` truncation for safe messages, structured return.

---

### `inference_proxy/config/settings.py` (modify -- add RedfishSettings)

**Analog:** `QUADSSettings` block in same file (lines 120-133)

**Sub-model pattern:**
```python
class QUADSSettings(BaseModel):
    """QUADS API configuration.

    When ``base_url`` is ``None`` (the default), QUADS features are
    disabled (D-10).  Setting it via ``INFERENCE_PROXY_QUADS__BASE_URL``
    activates the QUADS integration.
    """

    base_url: str | None = None
    timeout: float = 10.0
    poll_interval: int = 300
    verify_ssl: bool = True
    schedule_check_interval: int = 300
    schedule_lookahead_hours: int = 24
```

**Root registration pattern** (line 161):
```python
    quads: QUADSSettings = QUADSSettings()
```

Add `redfish: RedfishSettings = RedfishSettings()` following the same pattern. Import `SecretStr` from pydantic for the password field.

---

### `inference_proxy/config/dependencies.py` (modify -- add get_redfish_client)

**Analog:** `get_quads_client` in same file (lines 95-97)

**Provider pattern:**
```python
def get_quads_client(request: Request) -> QUADSClient | None:
    """Return the QUADS client, or None when QUADS is not configured (D-10)."""
    return request.app.state.quads_client  # type: ignore[no-any-return]
```

---

### `inference_proxy/main.py` (modify -- add Redfish lifespan block)

**Analog:** QUADS lifespan block in same file (lines 172-201)

**Optional feature creation pattern:**
```python
if resolved_settings.quads.base_url is not None:
    quads_http = httpx.AsyncClient(
        timeout=httpx.Timeout(resolved_settings.quads.timeout),
        verify=resolved_settings.quads.verify_ssl,
    )
    quads_client = QUADSClient(
        quads_http, resolved_settings.quads.base_url
    )
    app.state.quads_client = quads_client
    # ...
else:
    app.state.quads_client = None
    # ...
    quads_http = None
```

**Shutdown cleanup pattern** (lines 234-235):
```python
if quads_http is not None:
    await quads_http.aclose()
```

The Redfish block follows this same if/else + cleanup pattern, but uses `httpx.BasicAuth` and `verify=False`.

---

### `tests/redfish/__init__.py` (test, package init)

**Analog:** `tests/quads/__init__.py`

Empty file.

---

### `tests/redfish/test_client.py` (test, request-response)

**Analog:** `tests/quads/test_client.py`

**Imports pattern** (lines 1-13):
```python
from __future__ import annotations

import httpx
import pytest
from pytest_httpx import HTTPXMock

from inference_proxy.quads.client import (
    QUADSClient,
    QUADSConnectionError,
    canonical_hostname,
)
```

**Test class + httpx_mock pattern** (lines 61-72):
```python
class TestGetHosts:
    async def test_filters_to_gpu_only(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(
            url=f"{QUADS_URL}/api/v3/hosts",
            json=[_gpu_host("gpu01"), _cpu_host("cpu01")],
        )
        async with httpx.AsyncClient() as client:
            quads = QUADSClient(client, QUADS_URL)
            hosts = await quads.get_hosts()

        assert len(hosts) == 1
```

**Error test pattern** (lines 164-176):
```python
class TestConnectionError:
    async def test_get_hosts_raises_on_network_error(
        self, httpx_mock: HTTPXMock
    ) -> None:
        httpx_mock.add_exception(
            httpx.ConnectError("connection refused"),
            url=f"{QUADS_URL}/api/v3/hosts",
        )
        async with httpx.AsyncClient() as client:
            quads = QUADSClient(client, QUADS_URL)
            with pytest.raises(QUADSConnectionError):
                await quads.get_hosts()
```

Key patterns: `async def test_*`, `HTTPXMock` fixture injection, `httpx_mock.add_response(url=..., json=...)`, construct client inside `async with httpx.AsyncClient()`, `httpx_mock.add_exception` for error paths.

---

### `tests/config/test_settings.py` (modify -- add RedfishSettings tests)

**Analog:** `TestDefaultQUADSSettings` and `TestEnvVarOverrideQUADS*` in same file (lines 160-192)

**Default test pattern:**
```python
class TestDefaultQUADSSettings:
    def test_base_url_is_none(self) -> None:
        settings = Settings(_env_file=None)
        assert settings.quads.base_url is None

    def test_timeout_is_10(self) -> None:
        settings = Settings(_env_file=None)
        assert settings.quads.timeout == 10.0
```

**Env var override test pattern:**
```python
class TestEnvVarOverrideQUADSBaseUrl:
    def test_env_var_override_quads_base_url(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("INFERENCE_PROXY_QUADS__BASE_URL", "http://quads.example.com")
        settings = Settings(_env_file=None)
        assert settings.quads.base_url == "http://quads.example.com"
```

**IsNotBaseSettings test pattern:**
```python
class TestQUADSSettingsIsNotBaseSettings:
    def test_quads_settings_is_base_model_not_base_settings(self) -> None:
        assert not issubclass(QUADSSettings, BaseSettings)
        assert issubclass(QUADSSettings, BaseModel)
```

---

## Shared Patterns

### Constructor Dependency Injection
**Source:** `inference_proxy/quads/client.py` lines 41-43
**Apply to:** `inference_proxy/redfish/client.py`
```python
def __init__(self, http_client: httpx.AsyncClient, base_url: str) -> None:
    self._client = http_client
    self._base_url = base_url.rstrip("/")
```

### Optional Feature via None Settings
**Source:** `inference_proxy/config/settings.py` lines 120-133, `inference_proxy/main.py` lines 172-201
**Apply to:** `RedfishSettings`, `main.py` lifespan
```python
# Settings: None field = feature disabled
base_url: str | None = None

# Lifespan: if not None, create client
if resolved_settings.quads.base_url is not None:
    # create client...
else:
    app.state.quads_client = None
```

### Error Wrapping with Typed Exception
**Source:** `inference_proxy/quads/client.py` lines 90-98
**Apply to:** `inference_proxy/redfish/client.py`
```python
try:
    resp = await self._client.get(url, params=params)
    resp.raise_for_status()
except httpx.HTTPError as exc:
    raise QUADSConnectionError(str(exc)) from exc
```
For Redfish: replace `str(exc)` with `_extract_error_message(exc)` for DIAG-03 human-readable mapping.

### Test Setup with pytest-httpx
**Source:** `tests/quads/test_client.py` lines 62-72
**Apply to:** `tests/redfish/test_client.py`
```python
async def test_something(self, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url="...", json={...})
    async with httpx.AsyncClient() as client:
        svc = SomeClient(client, ...)
        result = await svc.some_method()
    assert result == expected
```

### conftest.py Integration
**Source:** `tests/conftest.py` lines 115-119
**Apply to:** `tests/conftest.py` (modify to add redfish_client override)
```python
application.state.quads_client = None
application.dependency_overrides[get_quads_client] = lambda: None
```
Add equivalent for `redfish_client` and `get_redfish_client`.

---

## No Analog Found

None. All files have exact or role-match analogs in the existing codebase.

## Metadata

**Analog search scope:** `inference_proxy/`, `tests/`
**Files scanned:** 8 analogs read
**Pattern extraction date:** 2026-07-21
