# Phase 18: Dashboard UI Update - Pattern Map

**Mapped:** 2026-07-17
**Files analyzed:** 7 (all modifications of existing files)
**Analogs found:** 7 / 7

## File Classification

| Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---------------|------|-----------|----------------|---------------|
| `inference_proxy/api/admin.py` | controller | request-response | itself (existing endpoints) | exact |
| `inference_proxy/models/admin.py` | model | n/a | itself (existing Pydantic models) | exact |
| `inference_proxy/templates/dashboard.html` | template | n/a | itself (existing Jinja2 template) | exact |
| `inference_proxy/static/js/dashboard.js` | component | event-driven | itself (existing vanilla JS) | exact |
| `inference_proxy/static/css/dashboard.css` | config | n/a | itself (existing CSS) | exact |
| `tests/api/test_admin.py` | test | n/a | itself (existing admin tests) | exact |
| `tests/api/test_dashboard.py` | test | n/a | itself (existing dashboard tests) | exact |

## Pattern Assignments

### `inference_proxy/api/admin.py` (controller, request-response)

**Analog:** itself -- add one new GET endpoint following existing endpoint pattern.

**Imports pattern** (lines 1-40): Add `get_quads_poller` to the dependencies import and `QUADSStatusResponse` to the models import. Both modules already imported, just add new names.

```python
# existing import block (lines 16-20) -- add get_quads_poller:
from inference_proxy.config.dependencies import (
    get_provisioner,
    get_quads_client,
    get_quads_poller,       # <-- add
    get_registry,
    get_request_metrics,
    get_unified_node_service,
)

# existing model import block (lines 24-31) -- add QUADSStatusResponse:
from inference_proxy.models.admin import (
    AdminMetricsResponse,
    AdminNodeResponse,
    QUADSStatusResponse,   # <-- add
    SetupRequest,
    SetupResponse,
    TaskStatusResponse,
    TeardownResponse,
)

# also need QUADSPoller type for the Depends annotation:
from inference_proxy.quads.poller import QUADSPoller
```

**Core endpoint pattern** (lines 47-64) -- follow the `get_metrics` endpoint structure (simple GET, single dependency, return model):

```python
# Pattern from GET /admin/metrics (lines 55-64):
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

# New endpoint follows same shape:
# @admin_router.get("/quads/status")
# async def quads_status(
#     poller: QUADSPoller | None = Depends(get_quads_poller),
# ) -> QUADSStatusResponse:
```

**Dependency injection pattern**: `get_quads_poller` already exists in `dependencies.py` (line 100-105), returns `QUADSPoller | None`. No new dependency provider needed.

---

### `inference_proxy/models/admin.py` (model)

**Analog:** itself -- add one new Pydantic model following existing model pattern.

**Core model pattern** (lines 38-50) -- every model uses `ConfigDict(frozen=True)`:

```python
# Pattern from AdminMetricsResponse (lines 38-50):
class AdminMetricsResponse(BaseModel):
    """Admin API response for aggregate request metrics."""

    model_config = ConfigDict(frozen=True)

    total_requests: int
    per_model: dict[str, int]
    per_node: dict[str, int]
```

**Imports already present** (lines 9-10): `datetime` and `BaseModel, ConfigDict` already imported.

**New model follows same shape:**

```python
class QUADSStatusResponse(BaseModel):
    """QUADS poller staleness data for the dashboard status indicator."""

    model_config = ConfigDict(frozen=True)

    status: str   # "connected" | "stale" | "unavailable"
    last_sync: datetime | None
    consecutive_failures: int
```

---

### `inference_proxy/templates/dashboard.html` (template)

**Analog:** itself.

**Table header pattern** (lines 36-48) -- `<th scope="col">` elements inside `<thead>`:

```html
<!-- Current: 8 columns (lines 37-46) -->
<th scope="col">Node ID</th>
<th scope="col">Endpoint</th>
<th scope="col">Model</th>
<th scope="col">Status</th>
<th scope="col">Active Connections</th>
<th scope="col">Circuit Breaker</th>
<th scope="col">Requests</th>
<th scope="col">Actions</th>

<!-- New: 10 columns. Insert GPU Vendor + GPU Model after Node ID, replace Status with State -->
```

**Colspan pattern** (line 49): `<td colspan="8">` -- must update to `colspan="10"`.

**Setup form card pattern** (lines 24-30) -- the standalone "Provision Node" card to be removed and replaced with inline toggle inside the "Node Fleet" card:

```html
<!-- Current standalone card (lines 24-30) -- REMOVE this entire section -->
<section class="card">
    <h2 class="card-title">Provision Node</h2>
    <form id="setup-form" method="post" class="setup-form">
        <input type="text" id="setup-hostname" placeholder="Enter hostname" required>
        <button type="submit" id="setup-btn">Setup</button>
    </form>
</section>
```

**Header area pattern** (lines 17-19) -- add QUADS status element in `.header-right`:

```html
<!-- Current header-right (lines 17-19) -->
<div class="header-right">
    <p id="last-updated"></p>
    <p id="poll-warning"></p>
</div>
<!-- Add: <span id="quads-status"></span> alongside -->
```

---

### `inference_proxy/static/js/dashboard.js` (component, event-driven)

**Analog:** itself.

**DOM construction pattern** (lines 128-175) -- `createElement` + `textContent` + `appendChild` for each cell:

```javascript
// Pattern from refreshDashboard node row rendering (lines 128-175):
const tdId = document.createElement("td");
tdId.textContent = node.node_id;
tr.appendChild(tdId);

// Badge cell pattern (lines 143-148):
const tdStatus = document.createElement("td");
const statusBadge = document.createElement("span");
statusBadge.className = `badge badge-${node.status}`;
statusBadge.textContent = node.status;
tdStatus.appendChild(statusBadge);
tr.appendChild(tdStatus);
```

**Action handler pattern** (lines 83-97) -- `handleTeardown` with confirm + fetch + toast:

```javascript
// Pattern from handleTeardown (lines 83-97):
async function handleTeardown(nodeId) {
  if (!window.confirm(`Teardown node ${nodeId}? ...`)) {
    return;
  }
  try {
    const resp = await fetch(`/admin/nodes/${nodeId}`, { method: "DELETE" });
    if (resp.ok) {
      showToast(`Teardown started for ${nodeId}`, "success");
    } else {
      showToast(`Teardown failed: HTTP ${resp.status}`, "error");
    }
  } catch (err) {
    showToast(`Teardown failed: ${err.message}`, "error");
  }
}
```

**Button disable-on-click pattern** (lines 170-173):

```javascript
teardownBtn.addEventListener("click", function () {
  teardownBtn.disabled = true;
  handleTeardown(node.node_id);
});
```

**Setup form handler pattern** (lines 196-223) -- fetch POST with JSON body + toast:

```javascript
const resp = await fetch("/admin/nodes/setup", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ hostname }),
});
```

**Promise.all polling pattern** (lines 105-109):

```javascript
const [nodesResp, metricsResp, tasksResp] = await Promise.all([
  fetch("/admin/nodes"),
  fetch("/admin/metrics"),
  fetch("/admin/provisioning/tasks"),
]);
// Add fetch("/admin/quads/status") to this array
```

**Empty state colspan pattern** (line 123): `colspan="8"` -- must update to `colspan="10"`.

---

### `inference_proxy/static/css/dashboard.css` (config)

**Analog:** itself.

**Badge class pattern** (lines 144-170) -- grouped by color family:

```css
/* Green family (lines 144-150): */
.badge-healthy,
.badge-closed,
.badge-complete,
.badge-teardown_complete {
  background: rgba(34, 197, 94, 0.15);
  color: #4ade80;
}

/* Red family (lines 152-156): */
.badge-unhealthy,
.badge-open,
.badge-failed {
  background: rgba(239, 68, 68, 0.15);
  color: #f87171;
}

/* Yellow family (lines 158-163): */
.badge-draining,
.badge-half_open,
.badge-unknown {
  background: rgba(234, 179, 8, 0.15);
  color: #fbbf24;
}

/* Blue family (lines 165-169): */
.badge-in-progress,
.badge-provisioning {
  background: rgba(59, 130, 246, 0.15);
  color: #60a5fa;
}
```

**Table button pattern** (lines 119-131) -- outline style with hover fill:

```css
td button {
  padding: 0.3rem 0.6rem;
  background: transparent;
  color: #f87171;
  border: 1px solid #f87171;
  border-radius: 0.375rem;
  font-size: 0.75rem;
  cursor: pointer;
  transition: all 0.15s;
}

td button:hover:not(:disabled) { background: #f87171; color: #fff; }
td button:disabled { opacity: 0.3; cursor: not-allowed; }
```

**New classes needed:**
- `.badge-available` -- add to blue family group
- `.btn-setup`, `.btn-teardown`, `.btn-retry`, `.btn-cancel`, `.btn-force-teardown` -- color variants overriding `td button` defaults
- `.action-group` -- flex container for primary button + caret
- `.action-menu` -- absolutely positioned dropdown for secondary actions

---

### `tests/api/test_admin.py` (test)

**Analog:** itself -- add a new test class for QUADS status endpoint.

**Test class pattern** (lines 216-229) -- class per endpoint, descriptive docstrings:

```python
class TestAdminMetrics:
    """GET /admin/metrics returns aggregate request counter data."""

    def test_metrics_returns_200(self, client: TestClient) -> None:
        """The metrics endpoint returns 200."""
        response = client.get("/admin/metrics")
        assert response.status_code == 200

    def test_metrics_empty_by_default(self, client: TestClient) -> None:
        """Fresh metrics returns zeroed counters."""
        response = client.get("/admin/metrics")
        data = response.json()
        assert data == {"total_requests": 0, "per_model": {}, "per_node": {}}
```

**Dependency override pattern** (lines 466-474) -- override via `app.dependency_overrides`:

```python
def test_returns_503_on_quads_connection_error(
    self,
    app: FastAPI,
    client: TestClient,
    mock_provisioner: MagicMock,
) -> None:
    mock_quads = AsyncMock()
    mock_quads.get_available.side_effect = QUADSConnectionError("timeout")
    app.dependency_overrides[get_quads_client] = lambda: mock_quads
```

**Fixture access pattern**: Tests use `client`, `app`, `test_registry`, `mock_provisioner` fixtures from `tests/conftest.py`.

---

### `tests/api/test_dashboard.py` (test)

**Analog:** itself -- update existing test classes.

**Column header assertion pattern** (lines 70-84):

```python
class TestDashboardTableStructure:
    def test_contains_all_eight_column_headers(self, client: TestClient) -> None:
        response = client.get("/dashboard")
        headers = [
            "Node ID", "Endpoint", "Model", "Status",
            "Active Connections", "Circuit Breaker", "Requests", "Actions",
        ]
        for header in headers:
            assert header in response.text, f"Missing column header: {header}"
```

**Setup form assertion pattern** (lines 151-167):

```python
class TestSetupForm:
    def test_contains_setup_form(self, client: TestClient) -> None:
        response = client.get("/dashboard")
        assert 'id="setup-form"' in response.text
```

**CSS file assertion pattern** (lines 121-148):

```python
class TestDashboardBadgeCSS:
    _css_path = (
        Path(__file__).resolve().parent.parent.parent
        / "inference_proxy" / "static" / "css" / "dashboard.css"
    )

    def test_badge_css_contains_all_status_classes(self) -> None:
        css = self._css_path.read_text()
        for cls in (".badge-healthy", ".badge-unhealthy", ".badge-draining"):
            assert cls in css, f"Missing CSS class: {cls}"
```

---

## Shared Patterns

### Toast Notifications
**Source:** `inference_proxy/static/js/dashboard.js` lines 3-14
**Apply to:** All new action handlers (setup, teardown, retry, cancel, force_teardown)
```javascript
function showToast(message, type) {
  const container = document.getElementById("toast-container");
  const toast = document.createElement("div");
  toast.className = "toast toast-" + (type || "info");
  toast.textContent = message;
  container.appendChild(toast);
  requestAnimationFrame(() => toast.classList.add("toast-visible"));
  setTimeout(() => {
    toast.classList.remove("toast-visible");
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}
```

### Confirmation Dialog
**Source:** `inference_proxy/static/js/dashboard.js` line 84
**Apply to:** Teardown, Force Teardown, Cancel action buttons
```javascript
if (!window.confirm(`Teardown node ${nodeId}? This will drain connections and stop the container.`)) {
  return;
}
```

### XSS Prevention
**Source:** `inference_proxy/static/js/dashboard.js` (throughout)
**Apply to:** All new DOM text insertion
```javascript
// ALWAYS use textContent, NEVER innerHTML for dynamic data
tdId.textContent = node.node_id;
```

### Pydantic Model Convention
**Source:** `inference_proxy/models/admin.py` (all models)
**Apply to:** New `QUADSStatusResponse` model
```python
model_config = ConfigDict(frozen=True)
```

### FastAPI Dependency Injection
**Source:** `inference_proxy/config/dependencies.py` lines 100-105
**Apply to:** New QUADS status endpoint
```python
def get_quads_poller(request: Request) -> QUADSPoller | None:
    """Return the QUADS poller, or None when QUADS is not configured."""
    return request.app.state.quads_poller
```

### Test Fixture Wiring
**Source:** `tests/conftest.py` lines 115-120
**Apply to:** New QUADS status tests (poller defaults to None)
```python
application.state.quads_poller = None
application.dependency_overrides[get_quads_poller] = lambda: None
```

## No Analog Found

No files without analogs. Every file is a modification of an existing file with established patterns.

## Metadata

**Analog search scope:** `inference_proxy/`, `tests/`
**Files scanned:** 7 (all self-analogs -- modifications only)
**Pattern extraction date:** 2026-07-17
