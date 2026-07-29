# Phase 31: Download Service & API - Pattern Map

**Mapped:** 2026-07-28
**Files analyzed:** 8 (1 new, 4 modified, 1 new test, 1 new integration test, 1 modified conftest)
**Analogs found:** 5 / 5 (all files have exact or role-match analogs)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `inference_proxy/huggingface/downloader.py` | service | CRUD + background | `inference_proxy/huggingface/catalog.py` | exact (same package, same asyncio.to_thread pattern) |
| `inference_proxy/models/admin.py` | model | -- | itself (add models to existing file) | exact |
| `inference_proxy/config/dependencies.py` | config/DI | -- | itself (add getter to existing file) | exact |
| `inference_proxy/api/admin.py` | controller | request-response | itself (add endpoints to existing file) | exact |
| `inference_proxy/main.py` | config/wiring | -- | itself (add service creation to lifespan) | exact |
| `tests/huggingface/test_downloader.py` | test | -- | `tests/huggingface/test_catalog.py` | exact |
| `tests/api/test_admin_downloads.py` | test | -- | `tests/conftest.py` + existing admin tests | role-match |
| `tests/conftest.py` | test config | -- | itself (add download service mock) | exact |

## Pattern Assignments

### `inference_proxy/huggingface/downloader.py` (service, CRUD + background)

**Analog:** `inference_proxy/huggingface/catalog.py`

**Imports pattern** (lines 1-14):
```python
"""HuggingFace model catalog service.

Scans a local HuggingFace cache directory (typically NFS-mounted) and
returns the list of cached model repositories.
"""

from __future__ import annotations

import asyncio

import structlog
from huggingface_hub import scan_cache_dir
from pydantic import BaseModel

logger = structlog.get_logger()
```

**Service class pattern** (lines 30-47):
```python
class ModelCatalogService:
    """Lists model repos found in a HuggingFace cache directory.

    Wraps ``scan_cache_dir`` in ``asyncio.to_thread`` so the blocking
    filesystem scan does not stall the event loop.
    """

    def __init__(self, cache_dir: str) -> None:
        self._cache_dir = cache_dir

    async def list_models(self) -> list[CatalogEntry]:
        """Return catalog entries for every *model* repo in the cache."""
        cache_info = await asyncio.to_thread(scan_cache_dir, self._cache_dir)
        return [
            CatalogEntry(repo_id=repo.repo_id)
            for repo in cache_info.repos
            if repo.repo_type == "model"
        ]
```

**Thread-safe dict pattern** (from `inference_proxy/resilience/circuit_breaker.py` lines 93-139):
```python
class CircuitBreakerRegistry:
    def __init__(self, threshold: int = 3) -> None:
        self._threshold = threshold
        self._breakers: dict[str, CircuitBreaker] = {}
        self._lock = threading.Lock()

    def get(self, node_id: str) -> CircuitBreaker | None:
        with self._lock:
            return self._breakers.get(node_id)

    def get_or_create(self, node_id: str) -> CircuitBreaker:
        with self._lock:
            breaker = self._breakers.get(node_id)
            if breaker is None:
                breaker = CircuitBreaker(threshold=self._threshold)
                self._breakers[node_id] = breaker
            return breaker
```

---

### `inference_proxy/models/admin.py` (model, add DownloadRequest + DownloadStatusResponse)

**Analog:** itself -- follow existing Pydantic model pattern

**Pydantic model pattern** (lines 60-67, 119-122):
```python
class SetupRequest(BaseModel):
    """Request body for POST /admin/nodes/setup."""

    model_config = ConfigDict(frozen=True)

    hostname: str
    managed: bool = True
    model: str | None = Field(default=None, max_length=256)


class PowerAction(str, Enum):
    """Redfish power actions matching _ACTION_TARGET_STATE keys in redfish/client.py."""

    On = "On"
    ForceOff = "ForceOff"
    GracefulRestart = "GracefulRestart"
    ForceRestart = "ForceRestart"
```

**Frozen response model pattern** (lines 96-106):
```python
class TaskStatusResponse(BaseModel):
    """Provisioning task status from etcd."""

    model_config = ConfigDict(frozen=True)

    hostname: str
    current_step: str
    started_at: datetime
    updated_at: datetime
    failed_step: str | None = None
    error: str | None = None
```

---

### `inference_proxy/config/dependencies.py` (config/DI, add get_download_service)

**Analog:** itself -- follow existing getter pattern

**DI getter pattern** (lines 102-104):
```python
def get_catalog_service(request: Request) -> ModelCatalogService:
    """Return the model catalog service from the current application state."""
    return request.app.state.catalog_service  # type: ignore[no-any-return]
```

---

### `inference_proxy/api/admin.py` (controller, add POST + GET endpoints)

**Analog:** itself -- follow existing endpoint patterns

**GET endpoint pattern** (lines 113-119, catalog endpoint -- closest analog for GET /admin/models/downloads):
```python
@admin_router.get("/models/catalog")
async def list_catalog(
    catalog: ModelCatalogService = Depends(get_catalog_service),
) -> ModelCatalogResponse:
    """Return the list of models available in the HuggingFace NFS cache."""
    models = await catalog.list_models()
    return ModelCatalogResponse(models=models)
```

**POST 202 endpoint pattern** (lines 122-173, setup_node -- closest analog for POST /admin/models/download):
```python
@admin_router.post("/nodes/setup", status_code=202)
async def setup_node(
    body: SetupRequest,
    provisioner: NodeProvisioner = Depends(get_provisioner),
    quads_client: QUADSClient | None = Depends(get_quads_client),
) -> SetupResponse:
    """Trigger provisioning of a new node (runs in background)."""
    # ... validation, dedup, fire-and-forget ...
    return SetupResponse(task_id=hostname)
```

---

### `inference_proxy/main.py` (config/wiring, add download service to lifespan)

**Analog:** itself -- follow catalog service creation pattern

**Service creation in lifespan** (lines 181-189):
```python
        # Model catalog from NFS-mounted HuggingFace cache
        cache_path = Path(resolved_settings.huggingface.cache_dir)
        if not cache_path.is_dir():
            raise RuntimeError(
                f"HuggingFace cache directory does not exist: {cache_path}"
            )
        catalog_service = ModelCatalogService(
            cache_dir=resolved_settings.huggingface.cache_dir
        )
        app.state.catalog_service = catalog_service
```

---

### `tests/huggingface/test_downloader.py` (test)

**Analog:** `tests/huggingface/test_catalog.py`

**Test file structure** (lines 1-63):
```python
"""Unit tests for ModelCatalogService."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from inference_proxy.huggingface.catalog import CatalogEntry, ModelCatalogService


class TestListModels:
    @pytest.mark.asyncio
    @patch("inference_proxy.huggingface.catalog.scan_cache_dir")
    async def test_returns_model_repos(self, mock_scan: MagicMock) -> None:
        mock_scan.return_value = _mock_cache_info([...])
        svc = ModelCatalogService(cache_dir="/data/hf")
        result = await svc.list_models()
        assert len(result) == 2
        mock_scan.assert_called_once_with("/data/hf")
```

---

### `tests/conftest.py` (test config, add download service mock)

**Analog:** itself -- follow existing mock pattern

**Mock service injection pattern** (lines 158-161):
```python
    mock_catalog = MagicMock()
    mock_catalog.list_models = AsyncMock(return_value=[])
    application.state.catalog_service = mock_catalog
    application.dependency_overrides[get_catalog_service] = lambda: mock_catalog
```

---

## Shared Patterns

### Structured Logging
**Source:** every service file
**Apply to:** `downloader.py`
```python
import structlog

logger = structlog.get_logger()
```

### `from __future__ import annotations`
**Source:** every source file in the project
**Apply to:** all new files

### `ConfigDict(frozen=True)`
**Source:** `inference_proxy/models/admin.py` -- every Pydantic model
**Apply to:** all new Pydantic models (DownloadRequest, DownloadStatusResponse)

### `asyncio.to_thread` for blocking HF calls
**Source:** `inference_proxy/huggingface/catalog.py` line 42
**Apply to:** `downloader.py` -- wrap `snapshot_download` the same way

### DI via `request.app.state`
**Source:** `inference_proxy/config/dependencies.py` lines 102-104
**Apply to:** new `get_download_service()` getter

## No Analog Found

None -- all files have exact analogs in the codebase.

## Metadata

**Analog search scope:** `inference_proxy/`, `tests/`
**Files scanned:** 6 analog files
**Pattern extraction date:** 2026-07-28
