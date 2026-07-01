# Phase 8: Dashboard and Node Fleet - Pattern Map

**Mapped:** 2026-06-30
**Files analyzed:** 7 (4 new, 2 modified, 1 new test)
**Analogs found:** 4 / 7

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `inference_proxy/api/dashboard.py` | controller | request-response | `inference_proxy/api/admin.py` | role-match |
| `inference_proxy/templates/dashboard.html` | template | render | none | no-analog |
| `inference_proxy/static/css/dashboard.css` | config | render | none (UI-SPEC defines contract) | no-analog |
| `inference_proxy/static/js/dashboard.js` | utility | request-response | none | no-analog |
| `inference_proxy/main.py` | config | wiring | self (existing) | exact |
| `pyproject.toml` | config | dependency | self (existing) | exact |
| `tests/api/test_dashboard.py` | test | request-response | `tests/api/test_admin.py` | exact |

## Pattern Assignments

### `inference_proxy/api/dashboard.py` (controller, request-response)

**Analog:** `inference_proxy/api/admin.py`

**Imports pattern** (lines 1-11):
```python
"""Admin API for operational visibility into the gateway.

Per D-05: Endpoints under /admin namespace, separate from /v1 proxy API.
Per D-06: Separate APIRouter in api/admin.py with prefix="/admin".
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
```

**Router creation pattern** (line 25):
```python
admin_router = APIRouter(prefix="/admin", tags=["admin"])
```

**Route handler pattern** (lines 28-51):
```python
@admin_router.get("/nodes")
async def list_nodes(
    registry: NodeRegistry = Depends(get_registry),
    # ... dependencies via Depends()
) -> list[AdminNodeResponse]:
    """Return all registered nodes..."""
    # ... business logic
```

**Key differences for dashboard.py:**
- No `prefix` needed (single route at `/dashboard`)
- No `Depends()` -- template rendering needs `Request` object, not injected services
- Returns `HTMLResponse` via `Jinja2Templates.TemplateResponse()`, not JSON
- Uses `from fastapi import APIRouter, Request` and `from fastapi.responses import HTMLResponse`

---

### `inference_proxy/main.py` (config, wiring -- MODIFIED)

**Analog:** self -- existing wiring patterns in `main.py`

**Import block pattern** (lines 26-27):
```python
from inference_proxy.api.admin import admin_router
from inference_proxy.api.routes import router
```
Add: `from inference_proxy.api.dashboard import dashboard_router`

**Router registration pattern** (lines 205-206):
```python
application.include_router(router)
application.include_router(admin_router)
```
Add: `application.include_router(dashboard_router)`

**Static files mount** -- new pattern, add after router registration:
```python
from pathlib import Path
from fastapi.staticfiles import StaticFiles

static_dir = Path(__file__).resolve().parent / "static"
application.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
```
Note: `app.mount()` MUST come after `include_router()` calls (see RESEARCH.md Pitfall 1).

---

### `tests/api/test_dashboard.py` (test, request-response)

**Analog:** `tests/api/test_admin.py`

**Imports pattern** (lines 1-6):
```python
from __future__ import annotations

from fastapi.testclient import TestClient
```

**Test class structure** (lines 40-46):
```python
class TestAdminNodesPopulated:
    """GET /admin/nodes with registered nodes returns node data."""

    def test_returns_200_with_two_nodes(
        self,
        client: TestClient,
        test_registry: NodeRegistry,
    ) -> None:
```

**Fixture usage** -- tests use `client: TestClient` fixture from `conftest.py` (line 122-125):
```python
@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Return a TestClient bound to the test app."""
    return TestClient(app)
```

**App fixture** -- `conftest.py` (lines 92-119) creates app with `create_app(settings=test_settings)` and injects test deps via `dependency_overrides`. Dashboard tests need same `client` fixture -- no new fixtures required.

**Assertion pattern** (lines 58-62):
```python
response = client.get("/admin/nodes")

assert response.status_code == 200
data = response.json()
assert len(data) == 2
```

**Dashboard test differences:**
- Assert `response.status_code == 200`
- Assert `"text/html"` in `response.headers["content-type"]`
- Assert key HTML content via `response.text` string checks (table headers, CSS links, script tag)
- No JSON parsing -- response is HTML

---

## Shared Patterns

### Module Docstrings
**Source:** `inference_proxy/api/admin.py` lines 1-7
**Apply to:** `inference_proxy/api/dashboard.py`
```python
"""Dashboard route for the operations UI.

Per D-01: Dashboard served at /dashboard, separate from /admin/* JSON API.
Per D-02: Client-side fetch -- HTML shell rendered by Jinja2, JS fetches /admin/nodes.
"""
```

### `from __future__ import annotations`
**Source:** Every `.py` file in the codebase
**Apply to:** `inference_proxy/api/dashboard.py`, `tests/api/test_dashboard.py`

### Frozen Pydantic Models
**Source:** `inference_proxy/models/admin.py` lines 12-21
**Apply to:** Not applicable this phase -- no new models needed

### Test Organization
**Source:** `tests/api/test_admin.py`
**Apply to:** `tests/api/test_dashboard.py`
- Group related tests in classes with descriptive docstrings
- Use `client: TestClient` fixture (already exists in conftest)
- Type-annotate all test parameters and return `-> None`

---

## No Analog Found

Files with no close match in the codebase (use RESEARCH.md patterns):

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `inference_proxy/templates/dashboard.html` | template | render | First Jinja2 template in the project. Use RESEARCH.md Pattern 1 + UI-SPEC layout contract. |
| `inference_proxy/static/css/dashboard.css` | config | render | First CSS file in the project. Use 08-UI-SPEC.md Badge CSS Contract verbatim. |
| `inference_proxy/static/js/dashboard.js` | utility | request-response | First JS file in the project. Use RESEARCH.md Pattern 3 (vanilla fetch + DOM). |

## Metadata

**Analog search scope:** `inference_proxy/api/`, `inference_proxy/main.py`, `tests/api/`, `tests/conftest.py`
**Files scanned:** 8
**Pattern extraction date:** 2026-06-30
