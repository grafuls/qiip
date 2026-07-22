# Phase 22: Power Management Endpoints - Pattern Map

**Mapped:** 2026-07-22
**Files analyzed:** 3 (modified)
**Analogs found:** 3 / 3

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `inference_proxy/api/admin.py` | controller | request-response | `inference_proxy/api/admin.py` (self -- `setup_node`, `get_quads_status`) | exact |
| `inference_proxy/models/admin.py` | model | request-response | `inference_proxy/models/admin.py` (self -- `SetupRequest`, `QUADSStatusResponse`) | exact |
| `tests/api/test_admin.py` | test | request-response | `tests/api/test_admin.py` (self -- `TestQuadsStatus`, `TestSetupQuadsRevalidation`) | exact |

## Pattern Assignments

### `inference_proxy/api/admin.py` -- add two route handlers (controller, request-response)

**Analog:** Same file, lines 49-170. The `get_quads_status` endpoint (line 150) is the closest structural match: DI injection of an optional dependency, None guard, simple delegation, return model.

**Imports to add** (based on existing import block lines 15-41):
```python
# Add to existing imports from inference_proxy.config.dependencies:
from inference_proxy.config.dependencies import get_redfish_client

# Add to existing imports from inference_proxy.models.admin:
from inference_proxy.models.admin import PowerActionRequest, PowerStateResponse

# New imports:
from inference_proxy.redfish.client import RedfishClient
from inference_proxy.redfish.errors import RedfishError
```

**DI + None guard pattern** (lines 150-156, `get_quads_status`):
```python
@admin_router.get("/quads/status")
async def get_quads_status(
    poller: QUADSPoller | None = Depends(get_quads_poller),
) -> QUADSStatusResponse:
    if poller is None:
        return QUADSStatusResponse(
            status="unavailable", last_sync=None, consecutive_failures=0
        )
```
Power endpoints use the same `X | None = Depends(get_x)` pattern but raise `HTTPException(503)` instead of returning a fallback response (per D-07).

**Hostname normalization pattern** (line 79, `setup_node`):
```python
hostname = canonical_hostname(body.hostname)
```
Power endpoints apply the same call to the path parameter: `hostname = canonical_hostname(hostname)`.

**Error-to-HTTPException pattern** (lines 97-99, `setup_node`):
```python
except QUADSConnectionError as exc:
    raise HTTPException(
        status_code=503, detail="QUADS unavailable"
    ) from exc
```
Power endpoints follow the same shape: `except RedfishError as exc: raise HTTPException(status_code=502, detail=exc.human_message) from exc`.

---

### `inference_proxy/models/admin.py` -- add 3 items: PowerAction enum, PowerActionRequest, PowerStateResponse (model, request-response)

**Analog:** Same file, lines 55-110.

**Frozen model convention** (every model in this file):
```python
model_config = ConfigDict(frozen=True)
```

**Request model with validation** (lines 55-71, `SetupRequest`):
```python
class SetupRequest(BaseModel):
    """Request body for POST /admin/nodes/setup."""

    model_config = ConfigDict(frozen=True)

    hostname: str
    managed: bool = True

    @field_validator("hostname")
    @classmethod
    def validate_hostname(cls, v: str) -> str:
        ...
```
`PowerActionRequest` is simpler -- no custom validator needed because the `PowerAction` str enum handles validation automatically.

**Simple response model** (lines 74-80, `SetupResponse` / lines 103-110, `QUADSStatusResponse`):
```python
class QUADSStatusResponse(BaseModel):
    """QUADS poller staleness data for the dashboard status indicator."""

    model_config = ConfigDict(frozen=True)

    status: str
    last_sync: datetime | None
    consecutive_failures: int
```
`PowerStateResponse` follows the same shape: frozen model, two fields (`hostname: str`, `power_state: str`).

**Import block** (lines 1-13):
```python
from __future__ import annotations

from enum import Enum  # add this

from pydantic import BaseModel, ConfigDict
```

---

### `tests/api/test_admin.py` -- add power endpoint test classes (test, request-response)

**Analog:** Same file. Two key patterns:

**DI override for optional dependency** (lines 469-479, `TestSetupQuadsRevalidation`):
```python
class TestSetupQuadsRevalidation:
    def test_returns_503_on_quads_connection_error(
        self,
        app: FastAPI,
        client: TestClient,
        mock_provisioner: MagicMock,
    ) -> None:
        mock_quads = AsyncMock()
        mock_quads.get_available.side_effect = QUADSConnectionError("timeout")
        app.dependency_overrides[get_quads_client] = lambda: mock_quads

        response = client.post("/admin/nodes/setup", json={"hostname": "gpu01"})
        assert response.status_code == 503
```
Power tests follow the same pattern: create `AsyncMock()` for `RedfishClient`, set return values or side effects, override `get_redfish_client` via `app.dependency_overrides`.

**Default None yields expected error** (lines 539-549, `TestQuadsStatus`):
```python
class TestQuadsStatus:
    def test_unavailable_when_no_poller(self, client: TestClient) -> None:
        """Default fixture has poller=None."""
        data = client.get("/admin/quads/status").json()
        assert data["status"] == "unavailable"
```
The conftest default `get_redfish_client` override returns `None` (line 123 of `tests/conftest.py`), so tests for the 503 case need no extra setup.

**Test class organization** (used throughout):
```python
class TestFeatureName:
    """Docstring explaining what's tested."""

    def test_happy_path(self, app: FastAPI, client: TestClient) -> None:
        ...

    def test_error_case(self, client: TestClient) -> None:
        ...
```

**Conftest DI override** (lines 121-124 of `tests/conftest.py`):
```python
application.dependency_overrides[get_redfish_client] = lambda: None
```
Power tests that need a working client must override this with a mock.

---

## Shared Patterns

### Dependency Injection (Optional Service)
**Source:** `inference_proxy/config/dependencies.py` lines 101-103
**Apply to:** Both power route handlers
```python
def get_redfish_client(request: Request) -> RedfishClient | None:
    """Return the Redfish client, or None when Redfish is not configured."""
    return request.app.state.redfish_client
```
Already exists. No changes needed to `dependencies.py`.

### Hostname Normalization
**Source:** `inference_proxy/quads/client.py` -- `canonical_hostname()` (already imported in `admin.py` line 37)
**Apply to:** Both power route handlers (D-02)

### Error Handling
**Source:** `inference_proxy/redfish/errors.py` lines 13-18
**Apply to:** Both power route handlers
```python
class RedfishError(Exception):
    def __init__(self, human_message: str) -> None:
        self.human_message = human_message
        super().__init__(human_message)
```
Catch `RedfishError`, use `exc.human_message` as HTTPException detail.

## No Analog Found

None -- all files are modifications to existing files with exact self-analogs.

## Metadata

**Analog search scope:** `inference_proxy/api/`, `inference_proxy/models/`, `inference_proxy/config/`, `inference_proxy/redfish/`, `tests/api/`, `tests/`
**Files scanned:** 6 (admin.py, models/admin.py, dependencies.py, redfish/errors.py, test_admin.py, conftest.py)
**Pattern extraction date:** 2026-07-22
