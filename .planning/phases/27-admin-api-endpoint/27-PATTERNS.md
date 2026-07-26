# Phase 27: Admin API Endpoint - Pattern Map

**Mapped:** 2026-07-26
**Files analyzed:** 6 new/modified files
**Analogs found:** 6 / 6

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `inference_proxy/api/admin.py` (modify) | controller | request-response | `inference_proxy/api/admin.py` lines 237-267 (Redfish power endpoints) | exact |
| `inference_proxy/models/admin.py` (modify) | model | N/A | `inference_proxy/models/admin.py` line 133-139 (`PowerStateResponse`) | exact |
| `inference_proxy/config/dependencies.py` (modify) | provider | N/A | `inference_proxy/config/dependencies.py` lines 101-103 (`get_redfish_client`) | exact |
| `inference_proxy/config/settings.py` (modify) | config | N/A | `inference_proxy/config/settings.py` lines 95-103 (`SSHSettings`) | exact |
| `inference_proxy/main.py` (modify) | bootstrap | N/A | `inference_proxy/main.py` lines 164-188 (Redfish init block) | exact |
| `tests/api/test_admin.py` (modify) | test | N/A | `tests/api/test_admin.py` lines 611-738 (`TestGetPowerState`, `TestExecutePowerAction`) | exact |
| `tests/conftest.py` (modify) | test-fixture | N/A | `tests/conftest.py` lines 139-143 (mock_provisioner wiring) | exact |
| `.env.example` (modify) | config | N/A | `.env.example` lines 64-74 (Redfish section) | exact |

## Pattern Assignments

### `inference_proxy/api/admin.py` (controller, request-response) -- MODIFY

**Analog:** Same file, Redfish power GET endpoint (lines 237-250)

**Imports to add** (following existing import blocks, lines 9-51):
```python
# Add to existing imports from inference_proxy.config.dependencies:
from inference_proxy.config.dependencies import get_llmfit_runner

# New imports:
from fastapi.responses import JSONResponse
from inference_proxy.llmfit.errors import LLMFitParseError, LLMFitTimeoutError
from inference_proxy.llmfit.runner import LLMFitRunner
from inference_proxy.models.admin import RecommendationResponse
from inference_proxy.provisioning.ssh_client import RemoteCommandError, SSHConnectionError
```
Note: `JSONResponse` is already imported in `main.py` but not in `admin.py`. Add it here for the typed error responses per D-02.

**Core endpoint pattern** (lines 237-250 -- Redfish GET power state):
```python
@admin_router.get("/nodes/{hostname}/power")
async def get_power_state(
    hostname: str,
    redfish: RedfishClient | None = Depends(get_redfish_client),
) -> PowerStateResponse:
    """Query current power state of a node's BMC (PWR-04)."""
    if redfish is None:
        raise HTTPException(status_code=503, detail="Redfish not configured")
    hostname = _validated_hostname(hostname)
    try:
        state = await redfish.get_power_state(hostname)
    except RedfishError as exc:
        raise HTTPException(status_code=502, detail=exc.human_message) from exc
    return PowerStateResponse(hostname=hostname, power_state=state)
```
New endpoint follows this pattern but: (1) no `None` check needed (runner always exists), (2) catches multiple exception types, (3) returns `JSONResponse` for errors instead of `HTTPException` to support `error_type` field per D-02.

**Hostname validation** (lines 65-70):
```python
def _validated_hostname(hostname: str) -> str:
    """Normalize and validate a hostname path parameter."""
    hostname = canonical_hostname(hostname)
    if not hostname or len(hostname) > 253 or not _HOSTNAME_RE.fullmatch(hostname):
        raise HTTPException(status_code=400, detail="Invalid hostname")
    return hostname
```
Reuse directly -- no modification needed.

---

### `inference_proxy/models/admin.py` (model) -- MODIFY

**Analog:** `PowerStateResponse` (lines 133-139)

**Response model pattern**:
```python
class PowerStateResponse(BaseModel):
    """Response body for power state endpoints (D-05)."""

    model_config = ConfigDict(frozen=True)

    hostname: str
    power_state: str
```
New `RecommendationResponse` follows identical structure: `ConfigDict(frozen=True)`, typed fields. Fields: `hostname: str`, `system: SystemInfo`, `models: list[ModelRecommendation]`.

**Existing imports** (lines 1-14):
```python
from __future__ import annotations

from datetime import datetime
from enum import Enum

import re

from pydantic import BaseModel, ConfigDict, field_validator
```
Add imports for `SystemInfo` and `ModelRecommendation` from `inference_proxy.models.llmfit`.

---

### `inference_proxy/config/dependencies.py` (provider) -- MODIFY

**Analog:** `get_redfish_client` (lines 101-103)

**DI provider pattern**:
```python
def get_redfish_client(request: Request) -> RedfishClient | None:
    """Return the Redfish client, or None when Redfish is not configured."""
    return request.app.state.redfish_client  # type: ignore[no-any-return]
```
New `get_llmfit_runner` follows the same pattern. Return type is `LLMFitRunner` (not `| None` -- runner is always created when SSH is configured, which is always in this codebase).

**Import to add**:
```python
from inference_proxy.llmfit.runner import LLMFitRunner
```

---

### `inference_proxy/config/settings.py` (config) -- MODIFY

**Analog:** `SSHSettings` (lines 95-103)

**Settings sub-model pattern**:
```python
class SSHSettings(BaseModel):
    """SSH connection configuration (D-16).

    All hosts use the same key and username per D-01, D-02.
    """

    key_path: Path = Path("~/.ssh/id_rsa").expanduser()  # D-01
    username: str = "root"  # D-02
    connect_timeout: int = 10  # D-04
```

**Root settings wiring** (lines 157-184 -- showing the pattern for adding a new sub-model):
```python
class Settings(BaseSettings):
    ...
    ssh: SSHSettings = SSHSettings()
    provisioning: ProvisioningSettings = ProvisioningSettings()
    ...
    redfish: RedfishSettings = RedfishSettings()
```
Add `llmfit: LLMFitSettings = LLMFitSettings()` to the `Settings` class.

---

### `inference_proxy/main.py` (bootstrap) -- MODIFY

**Analog:** Redfish init block (lines 164-192)

**Lifespan init pattern** (conditional service creation):
```python
        ssh_client = SSHClient(resolved_settings.ssh)

        if resolved_settings.redfish.bmc_username is not None:
            # ... create redfish client ...
            app.state.redfish_client = redfish_client
            logger.info("redfish client initialized")
        else:
            app.state.redfish_client = None
            # ...
```
LLMFitRunner is simpler -- always created (no conditional), placed after `ssh_client` creation:
```python
        ssh_client = SSHClient(resolved_settings.ssh)
        # LLMFitRunner init goes here, right after ssh_client
        app.state.llmfit_runner = LLMFitRunner(ssh_client=ssh_client)
```

**Import to add**:
```python
from inference_proxy.llmfit.runner import LLMFitRunner
```

---

### `tests/api/test_admin.py` (test) -- MODIFY

**Analog:** `TestGetPowerState` (lines 611-650)

**Test class structure for upstream-dependency endpoints**:
```python
class TestGetPowerState:
    """GET /admin/nodes/{hostname}/power returns BMC power state."""

    def test_returns_current_state(
        self, app: FastAPI, client: TestClient
    ) -> None:
        mock_redfish = AsyncMock()
        mock_redfish.get_power_state.return_value = "On"
        app.dependency_overrides[get_redfish_client] = lambda: mock_redfish

        response = client.get("/admin/nodes/gpu01/power")
        assert response.status_code == 200
        assert response.json() == {"hostname": "gpu01", "power_state": "On"}

    def test_returns_502_on_redfish_error(
        self, app: FastAPI, client: TestClient
    ) -> None:
        mock_redfish = AsyncMock()
        mock_redfish.get_power_state.side_effect = RedfishError("BMC unreachable")
        app.dependency_overrides[get_redfish_client] = lambda: mock_redfish

        response = client.get("/admin/nodes/gpu01/power")
        assert response.status_code == 502
        assert "BMC unreachable" in response.json()["detail"]
```
New tests follow this pattern: mock the runner via `app.dependency_overrides[get_llmfit_runner]`, set `return_value` or `side_effect`, assert status code and response body.

---

### `tests/conftest.py` (test-fixture) -- MODIFY

**Analog:** Mock provisioner wiring (lines 139-143)

**Mock service in app fixture pattern**:
```python
    mock_provisioner = MagicMock()
    mock_provisioner._etcd_client = MagicMock()
    mock_provisioner.list_tasks_raw = AsyncMock(return_value=[])
    application.state.provisioner = mock_provisioner
    application.dependency_overrides[get_provisioner] = lambda: mock_provisioner
```
Add `mock_llmfit_runner` with same pattern: `MagicMock(spec=LLMFitRunner)`, `recommend = AsyncMock()`, set on `application.state` and `dependency_overrides`.

**Dedicated fixture pattern** (lines 149-152):
```python
@pytest.fixture
def mock_provisioner(app: FastAPI) -> MagicMock:
    """Return the mock provisioner from the test app."""
    return app.state.provisioner  # type: ignore[no-any-return]
```

---

### `.env.example` (config) -- MODIFY

**Analog:** Redfish section (lines 64-74)

**Commented env var block pattern**:
```
# Redfish BMC (set BMC_USERNAME to enable power management)
# INFERENCE_PROXY_REDFISH__BMC_USERNAME=admin
# INFERENCE_PROXY_REDFISH__BMC_PASSWORD=password
# ...
```
Add similar block for LLMFit settings after Redfish section.

---

## Shared Patterns

### Hostname Validation
**Source:** `inference_proxy/api/admin.py` lines 62-70
**Apply to:** New recommendation endpoint
```python
_HOSTNAME_RE = re.compile(r"[a-zA-Z0-9]([a-zA-Z0-9\-\.]*[a-zA-Z0-9])?")

def _validated_hostname(hostname: str) -> str:
    """Normalize and validate a hostname path parameter."""
    hostname = canonical_hostname(hostname)
    if not hostname or len(hostname) > 253 or not _HOSTNAME_RE.fullmatch(hostname):
        raise HTTPException(status_code=400, detail="Invalid hostname")
    return hostname
```

### Error-to-502 Mapping
**Source:** `inference_proxy/api/admin.py` lines 246-249
**Apply to:** New recommendation endpoint (extended with multiple error types + JSONResponse for `error_type` field)
```python
    try:
        state = await redfish.get_power_state(hostname)
    except RedfishError as exc:
        raise HTTPException(status_code=502, detail=exc.human_message) from exc
```

### structlog Logger
**Source:** `inference_proxy/api/admin.py` line 53
**Apply to:** New endpoint error branches (log raw output per D-01)
```python
logger = structlog.get_logger()
```

### Test DI Override
**Source:** `tests/api/test_admin.py` lines 617-619
**Apply to:** All new recommendation tests
```python
        mock_redfish = AsyncMock()
        mock_redfish.get_power_state.return_value = "On"
        app.dependency_overrides[get_redfish_client] = lambda: mock_redfish
```

## No Analog Found

None -- all files have exact analogs in the existing codebase.

## Metadata

**Analog search scope:** `inference_proxy/`, `tests/`
**Files scanned:** 8
**Pattern extraction date:** 2026-07-26
