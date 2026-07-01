# Phase 9: Live Metrics and Auto-Refresh - Pattern Map

**Mapped:** 2026-07-01
**Files analyzed:** 5 (all modifications to existing files)
**Analogs found:** 5 / 5

## File Classification

| Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---------------|------|-----------|----------------|---------------|
| `inference_proxy/config/settings.py` | config | N/A | Self (existing sub-models) | exact |
| `inference_proxy/api/dashboard.py` | controller | request-response | `inference_proxy/api/admin.py` (DI pattern) | exact |
| `inference_proxy/templates/dashboard.html` | component | N/A | Self (existing table structure) | exact |
| `inference_proxy/static/js/dashboard.js` | component | request-response | Self (`loadNodes()` pattern) | exact |
| `inference_proxy/static/css/dashboard.css` | component | N/A | Self (existing badge pattern) | exact |

Tests extending:

| Test File | Analog |
|-----------|--------|
| `tests/config/test_settings.py` | Self (existing default + env override tests) |
| `tests/api/test_dashboard.py` | Self (existing HTML content assertion tests) |

## Pattern Assignments

### `inference_proxy/config/settings.py` (config)

**Analog:** Self -- follow existing sub-model pattern.

**Sub-model pattern** (lines 12-17, representative example):
```python
class GatewaySettings(BaseModel):
    """Gateway server configuration."""

    host: str = "0.0.0.0"
    port: int = 8080
    graceful_shutdown_timeout: int = 30
```

**Registration on root Settings** (lines 103-108):
```python
class Settings(BaseSettings):
    ...
    gateway: GatewaySettings = GatewaySettings()
    etcd: EtcdSettings = EtcdSettings()
    routing: RoutingSettings = RoutingSettings()
    proxy: ProxySettings = ProxySettings()
    resilience: ResilienceSettings = ResilienceSettings()
    logging: LoggingSettings = LoggingSettings()
```

**What to add:** A `DashboardSettings(BaseModel)` class with `poll_interval: int = 10` and register it as `dashboard: DashboardSettings = DashboardSettings()` on the root `Settings` class. Follow the exact docstring + field pattern above.

---

### `inference_proxy/api/dashboard.py` (controller, request-response)

**Analog:** `inference_proxy/api/admin.py` for DI injection pattern; self for template rendering.

**Current route** (lines 20-24):
```python
@dashboard_router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    """Render the operations dashboard HTML shell."""
    return templates.TemplateResponse(request=request, name="dashboard.html")
```

**DI pattern from admin.py** (lines 11-18, 28-33):
```python
from inference_proxy.config.dependencies import (
    get_circuit_breaker_registry,
    get_node_selector,
    get_registry,
    get_request_metrics,
)
...
@admin_router.get("/nodes")
async def list_nodes(
    registry: NodeRegistry = Depends(get_registry),
    ...
) -> list[AdminNodeResponse]:
```

**What to change:** Add `Depends(get_settings)` to the dashboard route signature, pass `settings.dashboard.poll_interval` into the template context dict. Import `Depends` from fastapi and `get_settings` from `inference_proxy.config.dependencies`.

---

### `inference_proxy/templates/dashboard.html` (component)

**Analog:** Self -- extend the existing table structure.

**Current thead** (lines 17-26):
```html
<table>
    <thead>
        <tr>
            <th scope="col">Node ID</th>
            <th scope="col">Endpoint</th>
            <th scope="col">Model</th>
            <th scope="col">Status</th>
            <th scope="col">Active Connections</th>
            <th scope="col">Circuit Breaker</th>
        </tr>
    </thead>
    <tbody id="node-table-body">
        <tr><td colspan="6">Loading node data...</td></tr>
    </tbody>
</table>
```

**Script inclusion** (line 35):
```html
<script src="{{ url_for('static', path='js/dashboard.js') }}"></script>
```

**What to change:**
1. Add `<th scope="col">Requests</th>` column header after Circuit Breaker.
2. Update `colspan="6"` to `colspan="7"` on the loading row.
3. Add a `<script>const POLL_INTERVAL_MS = {{ poll_interval * 1000 }};</script>` block before the dashboard.js script tag.
4. Add a "Last updated" element (near header or table) and a warning element for poll failures.

---

### `inference_proxy/static/js/dashboard.js` (component, request-response)

**Analog:** Self -- extend the existing `loadNodes()` pattern.

**Current fetch + DOM pattern** (lines 1-62):
```javascript
async function loadNodes() {
  const tbody = document.getElementById("node-table-body");
  const countEl = document.getElementById("node-count");
  try {
    const response = await fetch("/admin/nodes");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const nodes = await response.json();
    ...
    for (const node of nodes) {
      const tr = document.createElement("tr");
      const tdId = document.createElement("td");
      tdId.textContent = node.node_id;
      tr.appendChild(tdId);
      ...
      tbody.appendChild(tr);
    }
  } catch (err) {
    countEl.textContent = "";
    tbody.innerHTML =
      '<tr><td colspan="6">Failed to load node data...</td></tr>';
  }
}

document.addEventListener("DOMContentLoaded", loadNodes);
```

**What to change:**
1. Replace `loadNodes()` with `refreshDashboard()` that uses `Promise.all([fetch("/admin/nodes"), fetch("/admin/metrics")])`.
2. In the row-building loop, add a `tdReqs` cell: `tdReqs.textContent = perNode[node.node_id] || 0`.
3. Update all `colspan="6"` to `colspan="7"`.
4. On success: call `updateTimestamp()` and `clearWarning()`.
5. On error: call `showWarning()` but do NOT clear the table (D-07).
6. Replace `DOMContentLoaded` listener with: call `refreshDashboard()` once, then `setInterval(refreshDashboard, POLL_INTERVAL_MS)`.

---

### `inference_proxy/static/css/dashboard.css` (component)

**Analog:** Self -- follow existing class pattern.

**Current badge pattern** (lines 6-14):
```css
.badge {
  display: inline-block;
  padding: 4px 8px;
  border-radius: 9999px;
  font-size: 0.875rem;
  font-weight: 600;
  line-height: 1;
  text-transform: lowercase;
  white-space: nowrap;
}
```

**What to add:** Styles for the "Last updated" timestamp text and the poll failure warning indicator. Keep it minimal -- these are simple text elements, not badges.

---

## Shared Patterns

### Settings DI via `get_settings`

**Source:** `inference_proxy/config/dependencies.py` lines 28-31
**Apply to:** `inference_proxy/api/dashboard.py`

```python
from inference_proxy.config.dependencies import get_settings
from inference_proxy.config.settings import Settings

# In route signature:
async def dashboard(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
```

### Test: Default Settings Assertion

**Source:** `tests/config/test_settings.py` lines 18-20
**Apply to:** New `DashboardSettings` default test

```python
class TestDefaultGatewaySettings:
    def test_default_gateway_settings(self) -> None:
        settings = Settings(_env_file=None)
        assert settings.gateway.host == "0.0.0.0"
        assert settings.gateway.port == 8080
```

### Test: Env Var Override

**Source:** `tests/config/test_settings.py` lines 41-44
**Apply to:** New poll interval env var override test

```python
class TestEnvVarOverrideGatewayPort:
    def test_env_var_override_gateway_port(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("INFERENCE_PROXY_GATEWAY__PORT", "9090")
        settings = Settings()
        assert settings.gateway.port == 9090
```

### Test: HTML Content Assertion

**Source:** `tests/api/test_dashboard.py` lines 70-87
**Apply to:** New "Requests" column header test, poll interval JS variable test

```python
class TestDashboardTableStructure:
    def test_contains_all_six_column_headers(self, client: TestClient) -> None:
        response = client.get("/dashboard")
        headers = [
            "Node ID",
            "Endpoint",
            ...
        ]
        for header in headers:
            assert header in response.text, f"Missing column header: {header}"
```

## No Analog Found

None -- all files being modified already exist, and every pattern needed is already established in the codebase.

## Metadata

**Analog search scope:** `inference_proxy/`, `tests/`
**Files scanned:** 8
**Pattern extraction date:** 2026-07-01
