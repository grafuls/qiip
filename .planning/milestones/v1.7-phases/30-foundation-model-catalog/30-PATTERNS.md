# Phase 30: Foundation & Model Catalog - Pattern Map

**Mapped:** 2026-07-28
**Files analyzed:** 8
**Analogs found:** 7 / 8

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `inference_proxy/huggingface/__init__.py` | config | n/a | `inference_proxy/llmfit/__init__.py` | exact |
| `inference_proxy/huggingface/catalog.py` | service | request-response | `inference_proxy/llmfit/runner.py` | role-match |
| `inference_proxy/config/settings.py` | config | n/a | self (add sub-model) | exact |
| `inference_proxy/config/dependencies.py` | provider | n/a | self (add getter) | exact |
| `inference_proxy/api/admin.py` | controller | request-response | self (add endpoint) | exact |
| `inference_proxy/main.py` | config | n/a | self (lifespan wiring) | exact |
| `.env.example` | config | n/a | self (add section) | exact |
| `tests/test_catalog.py` | test | n/a | `tests/llmfit/test_runner.py` | role-match |

## Pattern Assignments

### `inference_proxy/huggingface/__init__.py` (package init)

**Analog:** `inference_proxy/llmfit/__init__.py`

Empty file. All domain packages use empty `__init__.py`.

---

### `inference_proxy/huggingface/catalog.py` (service, request-response)

**Analog:** `inference_proxy/llmfit/runner.py`

**Imports pattern** (lines 1-19):
```python
"""Module docstring describing purpose."""

from __future__ import annotations

import asyncio

import structlog
from pydantic import BaseModel

logger = structlog.get_logger()
```

**Service class pattern** (runner.py lines 24-36):
```python
class LLMFitRunner:
    """Docstring with DIP note."""

    def __init__(
        self, ssh_client: SSHClient, settings: LLMFitSettings | None = None
    ) -> None:
        self._ssh = ssh_client
        self._settings = settings or LLMFitSettings()
```

For `ModelCatalogService`: constructor takes `cache_dir: str`, stores as `self._cache_dir`. Simpler than LLMFitRunner since the only dependency is a path string.

**Sync-to-async wrapping pattern** -- the catalog service should wrap `scan_cache_dir()` the same way SSH commands are wrapped elsewhere in the codebase. Use `asyncio.to_thread()` per D-01:
```python
async def list_models(self) -> list[CatalogEntry]:
    info = await asyncio.to_thread(scan_cache_dir, self._cache_dir)
    return [
        CatalogEntry(repo_id=repo.repo_id)
        for repo in info.repos
        if repo.repo_type == "model"
    ]
```

**Pydantic response model** -- per D-04/D-05, define alongside the service (single file, single responsibility for catalog domain):
```python
class CatalogEntry(BaseModel):
    repo_id: str

class ModelCatalogResponse(BaseModel):
    models: list[CatalogEntry]
```

---

### `inference_proxy/config/settings.py` (modify -- add sub-model)

**Analog:** self

**Sub-model pattern** (lines 122-135, QUADSSettings/LLMFitSettings):
```python
class LLMFitSettings(BaseModel):
    """LLMFit remote execution configuration."""

    binary_path: str = "/usr/local/bin/llmfit"
    timeout: float = 60.0
    allowed_providers: list[str] = []
```

**New sub-model to add:**
```python
class HuggingFaceSettings(BaseModel):
    """HuggingFace Hub configuration."""

    cache_dir: str  # Required, no default (D-03)
    api_token: str | None = None  # Optional, Phase 31
```

**Root wiring pattern** (lines 165-193):
```python
class Settings(BaseSettings):
    # ... existing fields ...
    llmfit: LLMFitSettings = LLMFitSettings()
```

Add: `huggingface: HuggingFaceSettings` -- note: no default since `cache_dir` is required. This means `Settings()` will fail without env var set, which is the D-03 intent.

---

### `inference_proxy/config/dependencies.py` (modify -- add getter)

**Analog:** self

**Dependency getter pattern** (lines 100-103):
```python
def get_llmfit_runner(request: Request) -> LLMFitRunner:
    """Return the LLMFit runner from the current application state."""
    return request.app.state.llmfit_runner  # type: ignore[no-any-return]
```

**New getter to add:**
```python
def get_catalog_service(request: Request) -> ModelCatalogService:
    """Return the model catalog service from the current application state."""
    return request.app.state.catalog_service  # type: ignore[no-any-return]
```

---

### `inference_proxy/api/admin.py` (modify -- add endpoint)

**Analog:** self

**Simple GET endpoint pattern** (lines 99-108, `get_metrics`):
```python
@admin_router.get("/metrics")
async def get_metrics(
    request_metrics: RequestMetrics = Depends(get_request_metrics),
) -> AdminMetricsResponse:
    """Return aggregate request counter data for the operations dashboard."""
    return AdminMetricsResponse(
        total_requests=request_metrics.get_total(),
        per_model=request_metrics.get_per_model(),
        per_node=request_metrics.get_per_node(),
    )
```

**New endpoint to add:**
```python
@admin_router.get("/models/catalog")
async def list_catalog(
    catalog: ModelCatalogService = Depends(get_catalog_service),
) -> ModelCatalogResponse:
    """Return HuggingFace models available on NFS storage."""
    models = await catalog.list_models()
    return ModelCatalogResponse(models=models)
```

**Import additions needed:**
```python
from inference_proxy.config.dependencies import get_catalog_service
from inference_proxy.huggingface.catalog import ModelCatalogResponse, ModelCatalogService
```

---

### `inference_proxy/main.py` (modify -- lifespan wiring)

**Analog:** self

**Simple service creation pattern** (lines 167-169, LLMFitRunner):
```python
llmfit_runner = LLMFitRunner(
    ssh_client=ssh_client, settings=resolved_settings.llmfit
)
app.state.llmfit_runner = llmfit_runner
```

**New wiring to add in lifespan:**
```python
# HuggingFace startup config (D-08, D-10)
import os
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
from huggingface_hub.utils import disable_progress_bars
disable_progress_bars()

catalog_service = ModelCatalogService(cache_dir=resolved_settings.huggingface.cache_dir)
app.state.catalog_service = catalog_service
```

Note: D-08/D-10 startup config (env var + disable_progress_bars) should run early in lifespan, before any HF hub usage. Validate cache_dir exists at startup for fail-fast behavior.

---

### `.env.example` (modify -- add section)

**Analog:** self

**Section pattern** (lines 64-68):
```env
# LLMFit (model recommendation via SSH)
# INFERENCE_PROXY_LLMFIT__BINARY_PATH=/usr/local/bin/llmfit
# INFERENCE_PROXY_LLMFIT__TIMEOUT=60.0
```

**New section to add:**
```env
# HuggingFace Hub (model catalog from NFS cache)
INFERENCE_PROXY_HUGGINGFACE__CACHE_DIR=/path/to/nfs/huggingface
# INFERENCE_PROXY_HUGGINGFACE__API_TOKEN=hf_xxxxx
```

`CACHE_DIR` is uncommented (required). `API_TOKEN` is commented (optional, Phase 31).

---

### `tests/test_catalog.py` (test)

**Analog:** `tests/llmfit/test_runner.py`

**Test structure pattern** (lines 1-11, 72-81):
```python
"""Unit tests for ModelCatalogService."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from inference_proxy.huggingface.catalog import CatalogEntry, ModelCatalogService
```

**Fixture pattern** (lines 72-81):
```python
@pytest.fixture
def mock_ssh_client() -> MagicMock:
    client = MagicMock(spec=SSHClient)
    client.run = AsyncMock()
    return client

@pytest.fixture
def runner(mock_ssh_client: MagicMock) -> LLMFitRunner:
    return LLMFitRunner(ssh_client=mock_ssh_client)
```

For catalog tests: mock `scan_cache_dir` via `unittest.mock.patch`, construct `ModelCatalogService` with a temp cache_dir string.

**Test class per scenario pattern** (lines 84-99):
```python
class TestRecommend:
    @pytest.mark.asyncio
    async def test_parses_valid_json(
        self, runner: LLMFitRunner, mock_ssh_client: MagicMock
    ) -> None:
        mock_ssh_client.run.return_value = (FIXTURE_JSON, "", 0)
        result = await runner.recommend("gpu-host-01")
        assert len(result.models) == 2
```

Key test cases for catalog:
- Returns model repos from scan
- Filters out non-model repo types (datasets, spaces)
- Returns empty list for empty cache
- Uses `asyncio.to_thread` (verify via mock)

Test file location: `tests/huggingface/test_catalog.py` (follows `tests/llmfit/` pattern with `__init__.py`).

---

## Shared Patterns

### Structured Logging
**Source:** All service files
**Apply to:** `catalog.py`
```python
import structlog
logger = structlog.get_logger()
```

### Dependency Injection via app.state
**Source:** `inference_proxy/config/dependencies.py` (full file)
**Apply to:** Catalog service wiring
```python
def get_X(request: Request) -> X:
    return request.app.state.x  # type: ignore[no-any-return]
```

### Settings Sub-Model
**Source:** `inference_proxy/config/settings.py` lines 138-143
**Apply to:** HuggingFaceSettings
```python
class XSettings(BaseModel):
    """Docstring."""
    field: type = default
```

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| (none) | | | All files have analogs in the existing codebase |

## Metadata

**Analog search scope:** `inference_proxy/`, `tests/`
**Files scanned:** 7 analog files read
**Pattern extraction date:** 2026-07-28
