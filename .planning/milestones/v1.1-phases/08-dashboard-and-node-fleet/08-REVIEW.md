---
phase: 08-dashboard-and-node-fleet
reviewed: 2026-07-01T00:00:00Z
depth: standard
files_reviewed: 6
files_reviewed_list:
  - inference_proxy/api/dashboard.py
  - inference_proxy/main.py
  - inference_proxy/static/css/dashboard.css
  - inference_proxy/static/js/dashboard.js
  - inference_proxy/templates/dashboard.html
  - tests/api/test_dashboard.py
findings:
  critical: 1
  warning: 2
  info: 1
  total: 4
status: issues_found
---

# Phase 8: Code Review Report

**Reviewed:** 2026-07-01
**Depth:** standard
**Files Reviewed:** 6
**Status:** issues_found

## Summary

The dashboard phase adds an operations UI at `/dashboard` that renders a Jinja2 HTML shell with client-side JS fetching `/admin/nodes`. The implementation is lean and structurally sound. However, the JS uses `innerHTML` with unsanitized data from the API, creating a stored XSS vector. Additionally, the CSS is missing a badge class for the `unknown` node status, which is the default `NodeStatus` enum value and will appear for any newly registered node that hasn't been health-checked yet.

## Critical Issues

### CR-01: Stored XSS via innerHTML with unsanitized node data

**File:** `inference_proxy/static/js/dashboard.js:36,44`
**Issue:** Lines 36 and 44 inject API response fields directly into `innerHTML`:

```javascript
tdStatus.innerHTML = `<span class="badge badge-${node.status}">${node.status}</span>`;
tdCb.innerHTML = `<span class="badge badge-${node.circuit_breaker_state}">${node.circuit_breaker_state}</span>`;
```

The `node.status` and `node.circuit_breaker_state` values originate from etcd data (parsed by `node_from_etcd` in `serializer.py` line 44, which reads arbitrary JSON from etcd). If a compromised or misconfigured etcd entry contains a value like `healthy"><img src=x onerror=alert(1)>`, it will execute in the operator's browser. The `node_id`, `endpoint`, and `model` fields are safely set via `textContent`, but these two fields bypass that protection.

Even on an internal network, this is a security boundary violation: etcd data is an external trust boundary, and the dashboard renders it in an operator's authenticated browser session.

**Fix:** Use `textContent` for the text and `createElement` for the badge span, matching the pattern already used for other columns:

```javascript
const tdStatus = document.createElement("td");
const statusBadge = document.createElement("span");
statusBadge.className = `badge badge-${node.status}`;
statusBadge.textContent = node.status;
tdStatus.appendChild(statusBadge);
tr.appendChild(tdStatus);

const tdCb = document.createElement("td");
const cbBadge = document.createElement("span");
cbBadge.className = `badge badge-${node.circuit_breaker_state}`;
cbBadge.textContent = node.circuit_breaker_state;
tdCb.appendChild(cbBadge);
tr.appendChild(tdCb);
```

Note: Setting `className` with unsanitized data is not exploitable (CSS class names cannot execute scripts), but if you want belt-and-suspenders, validate status against an allowlist before using it in the class name.

## Warnings

### WR-01: Missing CSS class for `unknown` node status

**File:** `inference_proxy/static/css/dashboard.css`
**Issue:** `NodeStatus` (in `models/node.py:26`) has four values: `healthy`, `unhealthy`, `draining`, and `unknown`. The `unknown` status is the **default** (`models/node.py:59`), so any newly registered node that hasn't been health-checked yet will have `status: "unknown"`. The dashboard CSS defines `.badge-healthy`, `.badge-unhealthy`, and `.badge-draining` but has no `.badge-unknown` class. Nodes with `unknown` status will render as an unstyled badge (no background color, no text color), making them visually indistinguishable from plain text.

**Fix:** Add a `.badge-unknown` class with a neutral color:

```css
.badge-unknown {
  background-color: #6b7280;
  color: #fff;
}
```

### WR-02: Dead CSS class `.badge-half_open` -- circuit breaker never enters half-open state

**File:** `inference_proxy/static/css/dashboard.css:28-30`
**Issue:** The CSS defines `.badge-half_open` but the `CircuitBreaker` class (in `resilience/circuit_breaker.py`) only has two states: `"closed"` and `"open"`. The `_state` field is a plain string set to either `"closed"` (lines 40, 67) or `"open"` (line 52) -- there is no `"half_open"` transition anywhere. The admin endpoint in `admin.py:48` passes `breaker.state` directly, so `"half_open"` can never appear. This dead CSS class gives operators a false impression that half-open is a possible state, and the test at `tests/api/test_dashboard.py:110` asserts its presence, enshrining the phantom state.

**Fix:** Either remove `.badge-half_open` from the CSS and the corresponding test assertion, or implement half-open state in the circuit breaker. If half-open is planned for a future phase, add a comment noting it's a forward declaration.

## Info

### IN-01: Test reads CSS file directly from filesystem instead of via the app

**File:** `tests/api/test_dashboard.py:93-99`
**Issue:** `TestDashboardBadgeCSS` constructs a filesystem path to `dashboard.css` and reads it with `Path.read_text()`. This means the test would pass even if the static file mount were misconfigured and the CSS were not actually served by the app. The other test classes correctly use the `client` fixture to verify behavior through the app.

**Fix:** Fetch the CSS via the test client to verify it's actually served:

```python
def test_badge_css_contains_all_status_classes(self, client: TestClient) -> None:
    response = client.get("/static/css/dashboard.css")
    assert response.status_code == 200
    css = response.text
    for cls in (".badge-healthy", ".badge-unhealthy", ".badge-draining"):
        assert cls in css, f"Missing CSS class: {cls}"
```

---

_Reviewed: 2026-07-01_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
