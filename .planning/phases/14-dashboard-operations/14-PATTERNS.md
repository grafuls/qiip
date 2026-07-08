# Phase 14: Dashboard Operations - Pattern Map

**Mapped:** 2026-07-08
**Files analyzed:** 4 (all modifications to existing files)
**Analogs found:** 4 / 4

## File Classification

| Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---------------|------|-----------|----------------|---------------|
| `inference_proxy/templates/dashboard.html` | template | request-response | itself (current 41 lines) | exact-self |
| `inference_proxy/static/js/dashboard.js` | component | request-response + polling | itself (current 82 lines) | exact-self |
| `inference_proxy/static/css/dashboard.css` | config | N/A | itself (current 43 lines) | exact-self |
| `tests/api/test_dashboard.py` | test | N/A | itself (current 142 lines) | exact-self |

All four are extend-in-place. No new files.

## Pattern Assignments

### `inference_proxy/templates/dashboard.html` (template, extend)

**Analog:** itself

**HTML structure pattern** (lines 16-31) -- table lives inside `<main>`, Jinja2 only handles static shell:
```html
<main>
    <table>
        <thead>
            <tr>
                <th scope="col">Node ID</th>
                <!-- ... 6 more columns ... -->
            </tr>
        </thead>
        <tbody id="node-table-body">
            <tr><td colspan="7">Loading node data...</td></tr>
        </tbody>
    </table>
    <p id="last-updated"></p>
    <p id="poll-warning"></p>
</main>
```

**Script injection pattern** (lines 38-39) -- config vars injected before JS:
```html
<script>const POLL_INTERVAL_MS = {{ poll_interval * 1000 }};</script>
<script src="{{ url_for('static', path='js/dashboard.js') }}"></script>
```

**Modification points:**
1. Add setup form section above `<table>` (D-01). Simple.css auto-styles `<form>`, `<input>`, `<button>`.
2. Add `<th scope="col">Actions</th>` as 8th column header (D-09).
3. Update `colspan="7"` to `colspan="8"` in loading row (pitfall 3).
4. Add tasks panel `<section>` with `<table>` below the node table (D-05).

---

### `inference_proxy/static/js/dashboard.js` (component, extend)

**Analog:** itself

**Promise.all fetch pattern** (lines 8-11) -- extend with tasks endpoint:
```javascript
const [nodesResp, metricsResp] = await Promise.all([
  fetch("/admin/nodes"),
  fetch("/admin/metrics"),
]);
```

**Per-response error check pattern** (lines 12-13):
```javascript
if (!nodesResp.ok) throw new Error(`HTTP ${nodesResp.status}`);
if (!metricsResp.ok) throw new Error(`HTTP ${metricsResp.status}`);
```

**DOM row building pattern** (lines 30-66) -- createElement + textContent + appendChild:
```javascript
const tr = document.createElement("tr");

const tdId = document.createElement("td");
tdId.textContent = node.node_id;
tr.appendChild(tdId);
```

**Badge pattern** (lines 44-48) -- `badge badge-{value}` class convention:
```javascript
const statusBadge = document.createElement("span");
statusBadge.className = `badge badge-${node.status}`;
statusBadge.textContent = node.status;
tdStatus.appendChild(statusBadge);
```

**Empty state pattern** (lines 21-24) -- innerHTML for colspan message:
```javascript
if (nodes.length === 0) {
  countEl.textContent = "0 nodes registered";
  tbody.innerHTML =
    '<tr><td colspan="7">No nodes registered</td></tr>';
```

**Error catch pattern** (lines 73-76) -- warning element text swap:
```javascript
} catch (err) {
  warningEl.textContent = "Update failed -- retrying...";
  warningEl.className = "poll-warning";
}
```

**Init pattern** (lines 79-82) -- DOMContentLoaded + setInterval:
```javascript
document.addEventListener("DOMContentLoaded", function () {
  refreshDashboard();
  setInterval(refreshDashboard, POLL_INTERVAL_MS);
});
```

**Modification points:**
1. Add `fetch("/admin/provisioning/tasks")` to Promise.all, destructure as `tasksResp` (D-08).
2. Add `if (!tasksResp.ok)` check -- but degrade gracefully for tasks panel without failing node table (pitfall 4).
3. Add Actions column cell with teardown button per node row (D-09), disable when `node.status` is `provisioning` or `draining` (D-12).
4. Add teardown click handler: `window.confirm()` guard (D-10), `fetch DELETE /admin/nodes/{id}`, disable button on success (pitfall 2).
5. Add setup form submit handler in DOMContentLoaded: non-empty validation (D-04), `fetch POST /admin/nodes/setup` (D-01), disable + flash + setTimeout re-enable (D-03).
6. Add `renderTasks(tasks)` function using same createElement + badge pattern for tasks panel (D-05, D-06).

---

### `inference_proxy/static/css/dashboard.css` (config, extend)

**Analog:** itself

**Badge class convention** (lines 16-33) -- grouped by color, comma-separated selectors:
```css
.badge-healthy,
.badge-closed {
  background-color: #16a34a;
  color: #fff;
}

.badge-unhealthy,
.badge-open {
  background-color: #dc2626;
  color: #fff;
}

.badge-draining,
.badge-half_open,
.badge-unknown {
  background-color: #ca8a04;
  color: #fff;
}
```

**Modification points:**
1. Add `.badge-complete, .badge-teardown_complete` to the green group (reuse `#16a34a`).
2. Add `.badge-failed` to the red group (reuse `#dc2626`).
3. Add `.badge-in-progress` (blue, e.g., `#2563eb`) for all non-terminal provisioning steps. JS maps non-terminal steps to this single class.
4. Add `.badge-provisioning` to amber/blue group for node status badge (already covered by `.badge-unknown` amber group or new blue).
5. Minimal styles for setup form flash message, tasks panel, and teardown button if Simple.css defaults need overrides.

---

### `tests/api/test_dashboard.py` (test, extend)

**Analog:** itself

**Test class organization** -- one class per concern:
```python
class TestDashboardRoute:
    """GET /dashboard returns 200 HTML from the same app (DASH-01, DASH-03, TMPL-01)."""

    def test_dashboard_returns_200(self, client: TestClient) -> None:
        """GET /dashboard returns status code 200."""
        response = client.get("/dashboard")
        assert response.status_code == 200
```

**HTML content assertion pattern** (lines 71-83) -- check for string presence in response.text:
```python
def test_contains_all_seven_column_headers(self, client: TestClient) -> None:
    """HTML contains all 7 th elements for the node table."""
    response = client.get("/dashboard")
    headers = [
        "Node ID",
        "Endpoint",
        "Model",
        "Status",
        "Active Connections",
        "Circuit Breaker",
        "Requests",
    ]
    for header in headers:
        assert header in response.text, f"Missing column header: {header}"
```

**CSS file assertion pattern** (lines 123-141) -- read CSS file directly, check class presence:
```python
class TestDashboardBadgeCSS:
    _css_path = (
        Path(__file__).resolve().parent.parent.parent
        / "inference_proxy"
        / "static"
        / "css"
        / "dashboard.css"
    )

    def test_badge_css_contains_all_status_classes(self) -> None:
        css = self._css_path.read_text()
        for cls in (".badge-healthy", ".badge-unhealthy", ".badge-draining"):
            assert cls in css, f"Missing CSS class: {cls}"
```

**Modification points:**
1. Update `test_contains_all_seven_column_headers` to assert 8 columns including "Actions" (D-09).
2. Add test class for setup form: assert `id="setup-form"` (or equivalent) and hostname input present in HTML (DASH-01).
3. Add test class for tasks panel: assert tasks panel section present in HTML (DASH-03).
4. Add provisioning badge CSS tests: assert `.badge-complete`, `.badge-failed`, `.badge-in-progress` exist in dashboard.css.

## Shared Patterns

### XSS Prevention
**Source:** `inference_proxy/static/js/dashboard.js` lines 33, 37, 40, 47, 52, 58, 63
**Apply to:** All new DOM-building code (tasks panel rows, setup form flash message)
```javascript
// Always textContent, never innerHTML for user-provided values
tdId.textContent = node.node_id;
statusBadge.textContent = node.status;
```

### Badge Classification Logic
**Source:** `inference_proxy/provisioning/state.py` lines 19-38 (ProvisioningStep enum)
**Apply to:** Tasks panel rendering in dashboard.js
```javascript
// ponytail: three CSS classes cover all 17 enum values
const terminalGreen = ["complete", "teardown_complete"];
const terminalRed = ["failed"];
// Everything else -> "in-progress"
function stepBadgeClass(step) {
  if (terminalGreen.includes(step)) return "badge-complete";
  if (terminalRed.includes(step)) return "badge-failed";
  return "badge-in-progress";
}
```

### Teardown Disable Statuses
**Source:** `inference_proxy/models/node.py` lines 24-25 (NodeStatus.DRAINING, PROVISIONING)
**Apply to:** Actions column cell in node row builder
```javascript
const disableStatuses = ["provisioning", "draining"];
button.disabled = disableStatuses.includes(node.status);
```

## No Analog Found

None. All four files are extensions of existing files with established patterns.

## Metadata

**Analog search scope:** `inference_proxy/templates/`, `inference_proxy/static/`, `tests/api/`, `inference_proxy/models/`, `inference_proxy/provisioning/`
**Files scanned:** 7 (3 dashboard files + test file + 3 model/enum files for response shapes)
**Pattern extraction date:** 2026-07-08
