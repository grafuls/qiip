# Phase 9: Live Metrics and Auto-Refresh - Research

**Researched:** 2026-07-01
**Domain:** Vanilla JS polling, Jinja2 template variables, pydantic-settings
**Confidence:** HIGH

## Summary

This phase adds a "Requests" column to the existing dashboard node table and a `setInterval`-based polling loop that re-fetches `/admin/nodes` and `/admin/metrics` in parallel. No new dependencies are needed -- everything uses vanilla JS `fetch`, existing Jinja2 template injection, and the established pydantic-settings sub-model pattern.

The work touches 5 existing files (settings.py, dashboard.py, dashboard.html, dashboard.js, dashboard.css) and their corresponding tests. The `/admin/metrics` endpoint already returns `per_node: dict[str, int]` keyed by `node_id`, so the JS just needs to join that data with the node table rows.

**Primary recommendation:** Extend `loadNodes()` to parallel-fetch `/admin/metrics`, add a `setInterval` wrapper, inject `poll_interval` from settings via Jinja2 template variable.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Per-node request counts appear as a new column ("Requests") in the existing node fleet table. No separate metrics section.
- **D-02:** No aggregate total or per-model counts shown on the dashboard -- just per-node in the table.
- **D-03:** Polling interval is a backend env var (`INFERENCE_PROXY_DASHBOARD__POLL_INTERVAL`) injected into the Jinja2 template as a JS variable. No UI control on the page.
- **D-04:** Default polling interval is 10 seconds.
- **D-05:** Each poll cycle fetches both `/admin/nodes` and `/admin/metrics` in parallel (two fetches). Existing endpoints stay unchanged -- no new fields on `AdminNodeResponse`.
- **D-06:** Dashboard shows a "Last updated: HH:MM:SS" timestamp that updates on each successful poll.
- **D-07:** On poll failure, keep the last successful data on screen and show a subtle warning (e.g. "Update failed -- retrying...") that clears on next success.

### Claude's Discretion
- Where to place the "Last updated" text (header, footer, or near the table)
- Exact warning text and styling for poll failure state
- Whether to add the new setting to DashboardSettings sub-model or extend an existing settings group

### Deferred Ideas (OUT OF SCOPE)
None

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| METR-02 | Operator can see request counts on the dashboard, broken down by node | New "Requests" column in node table, populated from `/admin/metrics` `per_node` dict joined by `node_id` |
| DASH-02 | Dashboard auto-refreshes via JS polling at a configurable interval | `setInterval` calling a combined refresh function, interval from `INFERENCE_PROXY_DASHBOARD__POLL_INTERVAL` env var via pydantic-settings |

</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Per-node request counts | Browser (JS) | API (already built) | `/admin/metrics` endpoint exists; JS fetches and renders the column |
| Polling loop | Browser (JS) | -- | `setInterval` is purely client-side |
| Poll interval config | Frontend Server (Jinja2) | API (pydantic-settings) | Backend setting injected into template as JS variable |
| Last-updated timestamp | Browser (JS) | -- | Client-side `Date` formatting |
| Poll failure UX | Browser (JS) | -- | DOM manipulation on fetch error |

## Standard Stack

No new packages. Everything uses existing dependencies.

| Library | Already Installed | Purpose in This Phase |
|---------|-------------------|----------------------|
| pydantic-settings | Yes (>=2.14) | Add `DashboardSettings` sub-model with `poll_interval: int = 10` |
| Jinja2 | Yes (>=3.1) | Inject `poll_interval` into template context |
| Vanilla JS (fetch API) | N/A (browser built-in) | Parallel fetch of `/admin/nodes` + `/admin/metrics`, DOM updates |

**Installation:** None required.

## Architecture Patterns

### System Architecture Diagram

```
Browser (dashboard.html)
    |
    |  DOMContentLoaded
    v
dashboard.js
    |
    +-- refreshDashboard()
    |       |
    |       +-- Promise.all([
    |       |       fetch("/admin/nodes"),
    |       |       fetch("/admin/metrics")
    |       |   ])
    |       |
    |       +-- Join: per_node[node.node_id] -> "Requests" column
    |       +-- Update "Last updated" timestamp
    |       +-- On error: show warning, keep stale data
    |
    +-- setInterval(refreshDashboard, POLL_INTERVAL_MS)
            ^
            |
            Jinja2 injects: const POLL_INTERVAL_MS = {{ poll_interval * 1000 }};
            ^
            |
            settings.py: DashboardSettings.poll_interval (from env)
```

### Pattern 1: Parallel Fetch with Join

**What:** `Promise.all` fetches both endpoints simultaneously, then joins data by `node_id` key.
**When to use:** Every poll cycle.

```javascript
// ponytail: two fetches, one join, no framework
async function refreshDashboard() {
  try {
    const [nodesResp, metricsResp] = await Promise.all([
      fetch("/admin/nodes"),
      fetch("/admin/metrics"),
    ]);
    if (!nodesResp.ok || !metricsResp.ok) throw new Error("fetch failed");
    const nodes = await nodesResp.json();
    const metrics = await metricsResp.json();

    renderTable(nodes, metrics.per_node);
    updateTimestamp();
    clearWarning();
  } catch (err) {
    showWarning();
  }
}
```

### Pattern 2: Jinja2 Template Variable Injection

**What:** Backend injects poll interval as a JS constant via Jinja2.
**When to use:** Page load.

```html
<!-- In dashboard.html, before dashboard.js script tag -->
<script>
  const POLL_INTERVAL_MS = {{ poll_interval * 1000 }};
</script>
```

```python
# In dashboard.py route handler
@dashboard_router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={"poll_interval": settings.dashboard.poll_interval},
    )
```

### Pattern 3: pydantic-settings Sub-Model

**What:** New `DashboardSettings` sub-model following the established pattern (see `GatewaySettings`, `EtcdSettings`, etc.).
**When to use:** Adding the poll interval config.

```python
# In settings.py
class DashboardSettings(BaseModel):
    """Dashboard UI configuration."""
    poll_interval: int = 10  # seconds

# In Settings root class
class Settings(BaseSettings):
    ...
    dashboard: DashboardSettings = DashboardSettings()
```

Env var: `INFERENCE_PROXY_DASHBOARD__POLL_INTERVAL=10` [VERIFIED: existing pattern in settings.py uses `env_nested_delimiter="__"` with `env_prefix="INFERENCE_PROXY_"`]

### Anti-Patterns to Avoid
- **Modifying `AdminNodeResponse` to include request counts:** D-05 explicitly says no new fields on `AdminNodeResponse`. The JS joins the two responses client-side.
- **Using `requestAnimationFrame` or websockets:** D-03 specifies `setInterval` polling via env var. WebSocket/SSE is explicitly out of scope in REQUIREMENTS.md.
- **Clearing the table on poll failure:** D-07 says keep stale data visible, show warning only.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Parallel HTTP fetches | Custom promise chaining | `Promise.all` | Browser built-in, handles both resolve/reject |
| Time formatting | Manual string formatting | `Date.toLocaleTimeString()` | Handles locale, zero-padding |
| Periodic execution | `setTimeout` chain | `setInterval` | Simpler for fixed-interval polling; `setTimeout` chain only needed if you want to wait for the previous call to finish (not required here per D-05) |

## Common Pitfalls

### Pitfall 1: colspan Mismatch
**What goes wrong:** Adding a column to `<thead>` but forgetting to update the `colspan` on the loading/empty/error `<td>` elements.
**Why it happens:** The loading row uses `colspan="6"` -- adding a 7th column means it needs `colspan="7"`.
**How to avoid:** Search for all `colspan` values in both `dashboard.html` and `dashboard.js` and update them.
**Warning signs:** Loading/error messages don't span the full table width.

### Pitfall 2: Node ID Mismatch Between Endpoints
**What goes wrong:** `/admin/nodes` returns `node_id` field; `/admin/metrics` returns `per_node` dict keyed by node_id. If a node has no requests yet, its key won't exist in `per_node`.
**Why it happens:** `RequestMetrics._per_node` only has entries for nodes that have received requests.
**How to avoid:** Default to `0` when looking up: `metrics.per_node[node.node_id] || 0`
**Warning signs:** "undefined" showing in the Requests column.

### Pitfall 3: setInterval Drift / Stacking
**What goes wrong:** If a poll takes longer than the interval, requests stack up.
**Why it happens:** `setInterval` fires regardless of whether the previous call finished.
**How to avoid:** For a 10-second interval this is extremely unlikely to matter (the fetch takes <100ms on an internal network). Not worth adding complexity for. If it ever matters, switch to `setTimeout` chain.
**Warning signs:** Multiple concurrent requests visible in browser dev tools.

### Pitfall 4: Injected JS Variable Missing
**What goes wrong:** If the template variable isn't passed, Jinja2 renders `{{ poll_interval * 1000 }}` as empty or errors.
**Why it happens:** Route handler doesn't pass the context variable.
**How to avoid:** The route handler test should verify the template receives the variable. Jinja2 `UndefinedError` will surface immediately.
**Warning signs:** Polling doesn't start; JS console shows `POLL_INTERVAL_MS is not defined`.

## Code Examples

### Combined Refresh Function (full pattern)

```javascript
// Source: Established pattern in dashboard.js (loadNodes)
async function refreshDashboard() {
  const tbody = document.getElementById("node-table-body");
  const countEl = document.getElementById("node-count");

  try {
    const [nodesResp, metricsResp] = await Promise.all([
      fetch("/admin/nodes"),
      fetch("/admin/metrics"),
    ]);
    if (!nodesResp.ok || !metricsResp.ok) throw new Error("fetch failed");
    const nodes = await nodesResp.json();
    const metrics = await metricsResp.json();
    const perNode = metrics.per_node || {};

    if (nodes.length === 0) {
      countEl.textContent = "0 nodes registered";
      tbody.innerHTML = '<tr><td colspan="7">No nodes registered</td></tr>';
      updateTimestamp();
      clearWarning();
      return;
    }

    countEl.textContent = `${nodes.length} nodes registered`;
    tbody.innerHTML = "";

    for (const node of nodes) {
      const tr = document.createElement("tr");
      // ... existing 6 columns ...

      const tdReqs = document.createElement("td");
      tdReqs.textContent = perNode[node.node_id] || 0;
      tr.appendChild(tdReqs);

      tbody.appendChild(tr);
    }

    updateTimestamp();
    clearWarning();
  } catch (err) {
    showWarning();
    // ponytail: keep stale data, don't clear table (D-07)
  }
}
```

### Settings Sub-Model

```python
# Source: Existing pattern in inference_proxy/config/settings.py
class DashboardSettings(BaseModel):
    """Dashboard UI configuration."""
    poll_interval: int = 10
```

### Template Variable Injection

```python
# Source: Existing pattern in inference_proxy/api/dashboard.py
@dashboard_router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={"poll_interval": settings.dashboard.poll_interval},
    )
```

## State of the Art

No changes relevant to this phase. Vanilla JS `fetch` + `setInterval` is the correct tool for a simple ops dashboard polling at 10-second intervals. The project explicitly rejected WebSocket/SSE in REQUIREMENTS.md "Out of Scope."

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 1.4 |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/api/test_dashboard.py tests/config/test_settings.py -x` |
| Full suite command | `uv run pytest` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| METR-02 | Dashboard HTML contains "Requests" column header | unit | `uv run pytest tests/api/test_dashboard.py -x -k requests` | Extends existing |
| METR-02 | `/admin/metrics` per_node data available for JS join | unit | `uv run pytest tests/api/test_admin.py -x -k metrics` | Exists (passes) |
| DASH-02 | Dashboard HTML contains poll interval JS variable | unit | `uv run pytest tests/api/test_dashboard.py -x -k poll` | New test |
| DASH-02 | DashboardSettings.poll_interval defaults to 10 | unit | `uv run pytest tests/config/test_settings.py -x -k dashboard` | New test |
| DASH-02 | Dashboard route passes poll_interval to template context | unit | `uv run pytest tests/api/test_dashboard.py -x -k poll` | New test |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/api/test_dashboard.py tests/config/test_settings.py -x`
- **Per wave merge:** `uv run pytest`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
None -- existing test infrastructure covers all phase requirements. Tests extend `tests/api/test_dashboard.py` and `tests/config/test_settings.py`.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | Internal network only, no auth (per project constraints) |
| V3 Session Management | No | Stateless page |
| V4 Access Control | No | Read-only dashboard |
| V5 Input Validation | Yes (minimal) | Poll interval validated as `int` by Pydantic; JS only reads it, never sends user input |
| V6 Cryptography | No | No secrets involved |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| XSS via Jinja2 template variable | Tampering | Jinja2 auto-escapes by default; `poll_interval` is an `int` injected in a `<script>` block -- use `{{ poll_interval \| int }}` or ensure Pydantic validates it as `int` (already does) |
| Polling as timing oracle | Information Disclosure | N/A -- internal network only, counters are intentionally public on the admin dashboard |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| -- | -- | -- | -- |

**All claims in this research were verified against the existing codebase. No assumptions needed.**

## Open Questions

None. This phase is fully constrained by CONTEXT.md decisions and the existing codebase provides all the patterns needed.

## Sources

### Primary (HIGH confidence)
- `inference_proxy/static/js/dashboard.js` -- existing fetch + DOM pattern (lines 1-63)
- `inference_proxy/config/settings.py` -- pydantic-settings sub-model pattern (lines 1-108)
- `inference_proxy/api/dashboard.py` -- route handler pattern (lines 1-25)
- `inference_proxy/api/admin.py` -- `/admin/metrics` endpoint returning `per_node` dict (lines 54-63)
- `inference_proxy/routing/request_metrics.py` -- `get_per_node()` returns `dict[str, int]` (line 64)
- `inference_proxy/templates/dashboard.html` -- current table structure with 6 columns (lines 16-29)
- `tests/conftest.py` -- test fixture patterns (lines 1-126)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new packages, all patterns exist in codebase
- Architecture: HIGH -- vanilla JS polling is well-understood, all integration points identified
- Pitfalls: HIGH -- colspan mismatch and missing-key defaults are the only real gotchas

**Research date:** 2026-07-01
**Valid until:** indefinite -- vanilla JS and pydantic-settings are stable
