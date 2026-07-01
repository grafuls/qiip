# Phase 8: Dashboard and Node Fleet - Research

**Researched:** 2026-06-30
**Domain:** Server-rendered HTML dashboard (Jinja2 + vanilla JS + Simple.css)
**Confidence:** HIGH

## Summary

This phase adds a read-only operations dashboard at `/dashboard` served by the existing FastAPI app. The dashboard renders an HTML shell via Jinja2, then JS fetches `/admin/nodes` (already implemented in Phase 7) to populate a node fleet table. Styling comes from Simple.css (CDN) plus a small `dashboard.css` for badge colors.

The technical surface is small: one new dependency (`jinja2`), one template file, one CSS file, one JS file, one new route module, and wiring in `main.py`. All data is already available via `AdminNodeResponse` from Phase 7. No new API endpoints needed.

**Primary recommendation:** Keep this phase tight -- it is essentially 4 new files (template, CSS, JS, route module) plus wiring changes to `main.py` and `pyproject.toml`.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Dashboard served at `/dashboard` -- dedicated path, separate from `/admin/*` JSON API.
- **D-02:** Client-side fetch -- serve an HTML shell, then JS fetches `/admin/nodes` on page load to populate the table. Phase 9 polling reuses the same fetch logic.
- **D-03:** Color badges (pill/badge) next to the status text -- green for healthy, red for unhealthy, yellow for draining.
- **D-04:** Circuit breaker state also gets color badges -- green/closed, red/open, yellow/half-open. Same visual language as node status.
- **D-05:** Use Simple.css classless library for base styling -- semantic HTML gets instant polish with no design effort.
- **D-06:** Load Simple.css from CDN (`<link>` tag). Small override CSS for badges only.

### Claude's Discretion
- Page layout and structure -- Claude decides information hierarchy (summary header vs pure table, page title, etc.)

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DASH-01 | Operator can view a single-page dashboard showing node fleet and request counts | Jinja2 template + JS fetch of `/admin/nodes`; request counts deferred to Phase 9 (METR-02) but node fleet is this phase |
| DASH-03 | Dashboard is served from the same FastAPI app (no separate server) | `Jinja2Templates` + `StaticFiles` mounted in existing `create_app()` |
| NODE-01 | Operator can see all nodes in a table with node_id, endpoint, model, status, active connections, and circuit breaker state | JS fetches `AdminNodeResponse` (6 fields) and renders `<tr>` per node |
| NODE-02 | Node table visually distinguishes healthy, unhealthy, and draining nodes | CSS badge classes per UI-SPEC: `.badge-healthy`, `.badge-unhealthy`, `.badge-draining` |
| TMPL-01 | Dashboard uses Jinja2 templates rendered by FastAPI | `fastapi.templating.Jinja2Templates` with `jinja2>=3.1` dependency |
| TMPL-02 | Dashboard has basic CSS styling (readable, functional) | Simple.css from CDN + `dashboard.css` for badge overrides |

</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **SOLID principles required** -- all new code must follow SRP, OCP, LSP, ISP, DIP.
- **Tech stack**: Python, FastAPI, httpx, etcd3 -- aligns with existing team expertise.
- **No over-abstraction** -- YAGNI applies. No interfaces with single implementations.
- **Dependency injection** -- pass dependencies in via constructor/parameters, not instantiation inside consumers.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| HTML shell rendering | Frontend Server (FastAPI) | -- | Jinja2 renders the template on the server, serves complete HTML |
| Node data fetching | Browser / Client | API / Backend | JS `fetch()` calls existing `/admin/nodes` endpoint |
| Table population | Browser / Client | -- | Vanilla JS builds `<tr>` elements from JSON response |
| Visual styling | CDN / Static | Frontend Server | Simple.css from CDN, `dashboard.css` served via StaticFiles mount |
| Data source | API / Backend | -- | `AdminNodeResponse` already exists from Phase 7 |

## Standard Stack

### Core (new for this phase)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| jinja2 | 3.1.6 | Template engine | FastAPI's built-in template support requires it. Pallets project, 20+ years. [VERIFIED: PyPI registry + slopcheck OK] |

### Already Installed (no changes)
| Library | Version | Purpose | Status |
|---------|---------|---------|--------|
| FastAPI | 0.136.3 | HTTP framework | Already provides `Jinja2Templates` and `StaticFiles` -- just needs jinja2 installed |
| Starlette | 1.2.1 | ASGI toolkit | Provides `Jinja2Templates` class and `StaticFiles` (FastAPI re-exports both) |

### Frontend (no npm/build step)
| Asset | Source | Purpose | Why |
|-------|--------|---------|-----|
| Simple.css | CDN: `cdn.simplecss.org/simple.css` | Classless CSS framework | Per D-05/D-06. ~10KB, styles semantic HTML automatically. MIT licensed. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Simple.css CDN | Vendored Simple.css | CDN avoids managing the file; vendored avoids external dependency. CDN is the locked decision (D-06). |
| Jinja2 templates | Raw HTMLResponse strings | Jinja2 is the locked decision (TMPL-01). Templates are cleaner for multi-line HTML. |
| Client-side fetch | Server-side rendering of node data | Client-side is the locked decision (D-02). Enables Phase 9 polling reuse. |

**Installation:**
```bash
uv add jinja2>=3.1
```

**Version verification:**
```
jinja2 3.1.6 -- verified via `pip index versions jinja2` on 2026-06-30
```

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| jinja2 | PyPI | 17+ yrs | Billions cumulative | github.com/pallets/jinja | [OK] | Approved |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
Browser                          FastAPI App
  |                                  |
  | GET /dashboard                   |
  |--------------------------------->|
  |    Jinja2 renders dashboard.html |
  |<---------------------------------|
  |                                  |
  | GET /static/css/dashboard.css    |
  |--------------------------------->|
  |    StaticFiles serves file       |
  |<---------------------------------|
  |                                  |
  | GET /static/js/dashboard.js      |
  |--------------------------------->|
  |    StaticFiles serves file       |
  |<---------------------------------|
  |                                  |
  | JS: fetch("/admin/nodes")       |
  |--------------------------------->|
  |    admin_router returns JSON     |
  |<---------------------------------|
  |                                  |
  | JS populates <tbody> with rows   |
  |                                  |
```

### Recommended Project Structure
```
inference_proxy/
  api/
    admin.py           # Existing -- /admin/nodes endpoint (Phase 7)
    dashboard.py       # NEW -- /dashboard route, Jinja2 rendering
  templates/
    dashboard.html     # NEW -- Jinja2 template (HTML shell)
  static/
    css/
      dashboard.css    # NEW -- Badge styles (~35 lines, per UI-SPEC)
    js/
      dashboard.js     # NEW -- Fetch + table population (~40 lines)
  main.py              # MODIFIED -- mount StaticFiles, register dashboard router
```

### Pattern 1: FastAPI Jinja2 Template Route
**What:** A route handler that renders a Jinja2 template and returns HTML.
**When to use:** Server-rendered pages in a FastAPI app.
**Example:**
```python
# Source: https://fastapi.tiangolo.com/advanced/templates/
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

dashboard_router = APIRouter(tags=["dashboard"])

@dashboard_router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="dashboard.html")
```
[CITED: fastapi.tiangolo.com/advanced/templates/]

### Pattern 2: StaticFiles Mount
**What:** Serve CSS/JS files from a directory.
**When to use:** Any FastAPI app serving static assets.
**Example:**
```python
# Source: https://fastapi.tiangolo.com/advanced/templates/
from pathlib import Path
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
```
[CITED: fastapi.tiangolo.com/advanced/templates/]

### Pattern 3: Vanilla JS Fetch + DOM Population
**What:** Fetch JSON from an API, build table rows.
**When to use:** Client-side data loading without a framework.
**Example:**
```javascript
// ponytail: no framework, no build step -- vanilla fetch + DOM manipulation
async function loadNodes() {
    const tbody = document.getElementById("node-table-body");
    try {
        const response = await fetch("/admin/nodes");
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const nodes = await response.json();
        if (nodes.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6">No nodes registered</td></tr>';
            return;
        }
        tbody.innerHTML = nodes.map(node => `
            <tr>
                <td>${node.node_id}</td>
                <td>${node.endpoint}</td>
                <td>${node.model}</td>
                <td><span class="badge badge-${node.status}">${node.status}</span></td>
                <td>${node.active_connections}</td>
                <td><span class="badge badge-${node.circuit_breaker_state}">${node.circuit_breaker_state}</span></td>
            </tr>
        `).join("");
    } catch (err) {
        tbody.innerHTML = '<tr><td colspan="6">Failed to load node data.</td></tr>';
    }
}
document.addEventListener("DOMContentLoaded", loadNodes);
```
[ASSUMED -- standard vanilla JS pattern]

### Anti-Patterns to Avoid
- **Jinja2 rendering node data server-side:** The template should render an empty shell. Node data comes via JS fetch (per D-02). This enables Phase 9 polling reuse without a full page reload.
- **Putting dashboard route in admin.py:** Dashboard is a separate concern from the JSON admin API. Use a dedicated `dashboard.py` router module (SRP).
- **Hardcoding the template path as a string literal:** Use `Path(__file__).parent.parent / "templates"` relative to the module, not a string like `"inference_proxy/templates"`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTML templating | String concatenation in Python | `Jinja2Templates` | Autoescaping, template inheritance, `url_for()` helper |
| CSS styling | Custom CSS from scratch | Simple.css (CDN) | 10KB classless framework styles semantic HTML automatically |
| Static file serving | Custom route handlers for CSS/JS | `StaticFiles` mount | Built into Starlette, handles content types, caching headers |
| XSS protection | Manual escaping | Jinja2 autoescape (enabled by default for .html) | Jinja2 autoescapes `.html` files by default via `select_autoescape()` |

## Common Pitfalls

### Pitfall 1: StaticFiles mount order vs route order
**What goes wrong:** If `app.mount("/static", ...)` is called before `app.include_router(dashboard_router)`, static files work fine. But if you mount at `/` or a path that shadows routes, routes stop working.
**Why it happens:** `app.mount()` creates a sub-application that catches all requests under that path.
**How to avoid:** Mount static files at `/static` (not `/`). Call `app.mount()` in `create_app()` after route registration.
**Warning signs:** 404s on dashboard route, or static files returning HTML.

### Pitfall 2: Template directory path resolution
**What goes wrong:** `Jinja2Templates(directory="templates")` resolves relative to the CWD, not the package directory. Works in dev, breaks in production.
**Why it happens:** Python relative paths depend on where `uvicorn` is launched from.
**How to avoid:** Use `Path(__file__).resolve().parent.parent / "templates"` (or equivalent) to resolve relative to the source file.
**Warning signs:** `TemplateNotFound` errors in production but not in dev.

### Pitfall 3: Missing `request` parameter in route handler
**What goes wrong:** `Jinja2Templates.TemplateResponse()` requires a `Request` object. Forgetting to declare it as a parameter causes a runtime error.
**Why it happens:** Easy to forget since JSON API routes don't need `Request`.
**How to avoid:** Always declare `request: Request` in template-rendering route handlers.
**Warning signs:** `TypeError` at request time.

### Pitfall 4: XSS via innerHTML in JS
**What goes wrong:** Using `innerHTML` with unsanitized data from the API could allow XSS if node data contains script tags.
**Why it happens:** `AdminNodeResponse` fields are strings that could theoretically contain HTML.
**How to avoid:** The node data comes from etcd (internal, trusted source). For defense in depth, use `textContent` for string fields, or sanitize. Since this is an internal-only dashboard (per project constraints), the risk is LOW.
**Warning signs:** Node IDs or endpoints containing `<script>` tags (unlikely from etcd).

### Pitfall 5: Jinja2 not installed
**What goes wrong:** `from fastapi.templating import Jinja2Templates` raises `ImportError` if jinja2 is not in the venv.
**Why it happens:** jinja2 is not a core FastAPI dependency -- it's optional.
**How to avoid:** Add `jinja2>=3.1` to `pyproject.toml` dependencies. Verified it's not currently installed in the venv.
**Warning signs:** `ImportError: jinja2 must be installed to use Jinja2Templates`.

## Code Examples

### Dashboard Route Module (`api/dashboard.py`)
```python
# Source: https://fastapi.tiangolo.com/advanced/templates/
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

dashboard_router = APIRouter(tags=["dashboard"])


@dashboard_router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    """Render the operations dashboard HTML shell."""
    return templates.TemplateResponse(request=request, name="dashboard.html")
```
[CITED: fastapi.tiangolo.com/advanced/templates/]

### Wiring in main.py
```python
# Add to imports:
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from inference_proxy.api.dashboard import dashboard_router

# Add to create_app(), after include_router calls:
application.include_router(dashboard_router)

# Mount static files (after router registration):
static_dir = Path(__file__).resolve().parent / "static"
application.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
```
[CITED: fastapi.tiangolo.com/advanced/templates/]

### Jinja2 Template (`templates/dashboard.html`)
```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Node Fleet Dashboard</title>
    <link rel="stylesheet" href="https://cdn.simplecss.org/simple.css">
    <link rel="stylesheet" href="{{ url_for('static', path='css/dashboard.css') }}">
</head>
<body>
    <header>
        <h1>Node Fleet Dashboard</h1>
        <p id="node-count">Loading node data...</p>
    </header>
    <main>
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
    </main>
    <footer>
        <p>QUADS Inference Proxy</p>
    </footer>
    <script src="{{ url_for('static', path='js/dashboard.js') }}"></script>
</body>
</html>
```
[CITED: 08-UI-SPEC.md page layout and copywriting contracts]

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `TemplateResponse("template.html", {"request": request})` | `TemplateResponse(request=request, name="template.html")` | FastAPI 0.108.0 / Starlette 0.29.0 | `request` is now a keyword arg, not inside context dict |
| `from starlette.templating import Jinja2Templates` | `from fastapi.templating import Jinja2Templates` | Always available | FastAPI re-exports it; either import works |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Simple.css CDN at `cdn.simplecss.org/simple.css` is stable and available | Standard Stack | Dashboard would render unstyled; fallback: vendor the CSS file |
| A2 | Vanilla JS fetch pattern for table population is standard and sufficient | Code Examples | Low risk -- this is basic DOM manipulation |
| A3 | `AdminNodeResponse` status values are lowercase strings matching CSS class names (`healthy`, `unhealthy`, `draining`) | Architecture Patterns | Badge CSS classes would not match; verified via `NodeStatus(StrEnum)` values in `models/node.py` -- they are lowercase |
| A4 | Circuit breaker state strings are `closed`, `open`, `half_open` | Architecture Patterns | Badge CSS classes would not match; verified A3 is correct from test_admin.py assertions |

**Note:** A3 and A4 were verified against codebase (`models/node.py` uses `StrEnum` with lowercase values; `test_admin.py` asserts `"closed"` and `"open"` strings). Confidence is HIGH.

## Open Questions

1. **`url_for('static', ...)` in templates when using TestClient**
   - What we know: `url_for()` requires the StaticFiles mount to be named `"static"`. TestClient should handle this.
   - What's unclear: Whether tests that render the template need the static directory to exist with actual files, or whether they can test just the HTML structure.
   - Recommendation: Create the static directory and files before running template tests. Alternatively, test the `/dashboard` endpoint response for status code and key HTML content (table headers, script tag) without asserting on static file content.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| jinja2 | TMPL-01 (template rendering) | Not in venv | 3.1.6 on PyPI | Must install -- no fallback |
| Simple.css CDN | TMPL-02 (CSS styling) | External | N/A | Vendor the CSS file locally |
| Python 3.12 | Runtime | Yes | 3.12 | -- |
| FastAPI | Framework | Yes | 0.136.3 | -- |
| Starlette | StaticFiles + Jinja2Templates | Yes | 1.2.1 | -- |

**Missing dependencies with no fallback:**
- `jinja2` must be added to `pyproject.toml` and installed

**Missing dependencies with fallback:**
- Simple.css CDN: if CDN is down, dashboard renders unstyled but functional (acceptable for internal tool)

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.0+ with pytest-asyncio 1.4+ |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/api/test_dashboard.py -x -q` |
| Full suite command | `uv run pytest tests/ -x -q` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DASH-01 | GET /dashboard returns 200 with HTML containing node table | integration | `uv run pytest tests/api/test_dashboard.py::test_dashboard_returns_html -x` | No -- Wave 0 |
| DASH-03 | Dashboard served by same FastAPI app (no separate process) | integration | `uv run pytest tests/api/test_dashboard.py::test_dashboard_same_app -x` | No -- Wave 0 |
| NODE-01 | Table headers present for all 6 AdminNodeResponse fields | integration | `uv run pytest tests/api/test_dashboard.py::test_table_headers -x` | No -- Wave 0 |
| NODE-02 | Badge CSS classes exist for healthy/unhealthy/draining | unit | `uv run pytest tests/api/test_dashboard.py::test_badge_classes -x` | No -- Wave 0 |
| TMPL-01 | Response uses Jinja2 template (not raw string) | integration | `uv run pytest tests/api/test_dashboard.py::test_uses_template -x` | No -- Wave 0 |
| TMPL-02 | Response includes CSS link tags | integration | `uv run pytest tests/api/test_dashboard.py::test_css_links -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/api/test_dashboard.py -x -q`
- **Per wave merge:** `uv run pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/api/test_dashboard.py` -- covers DASH-01, DASH-03, NODE-01, NODE-02, TMPL-01, TMPL-02
- [ ] `inference_proxy/templates/` directory -- must exist before template tests run
- [ ] `inference_proxy/static/css/` and `inference_proxy/static/js/` directories -- must exist before StaticFiles mount
- [ ] `jinja2>=3.1` added to pyproject.toml dependencies

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Internal network only, no auth in v1 |
| V3 Session Management | no | Stateless dashboard, no sessions |
| V4 Access Control | no | Read-only dashboard, internal network |
| V5 Input Validation | yes (minimal) | Node data from etcd (trusted); JS should use `textContent` for string fields as defense-in-depth |
| V6 Cryptography | no | No crypto operations in this phase |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| XSS via innerHTML | Tampering | Use `textContent` for untrusted strings; Jinja2 autoescaping for server-rendered content |
| CDN compromise (Simple.css) | Tampering | Low risk for classless CSS (no JS execution); could add SRI hash to `<link>` tag |
| Path traversal via StaticFiles | Information Disclosure | Starlette's `StaticFiles` already prevents directory traversal |

## Sources

### Primary (HIGH confidence)
- FastAPI templates docs: https://fastapi.tiangolo.com/advanced/templates/ -- Jinja2Templates usage, StaticFiles mounting, url_for in templates
- Starlette templates docs: https://www.starlette.io/templates/ -- Jinja2Templates constructor, autoescaping, test client `.template`/`.context` attributes
- PyPI jinja2: 3.1.6 -- verified via `pip index versions jinja2` on 2026-06-30
- Codebase: `inference_proxy/main.py`, `api/admin.py`, `models/admin.py`, `models/node.py` -- verified existing patterns
- 08-UI-SPEC.md -- page layout, badge CSS, copywriting, component inventory

### Secondary (MEDIUM confidence)
- Simple.css: https://simplecss.org/ -- classless CSS framework, MIT licensed, ~10KB

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- jinja2 is the standard Python template engine, verified on PyPI
- Architecture: HIGH -- FastAPI Jinja2 pattern is documented in official docs, codebase patterns are established
- Pitfalls: HIGH -- common FastAPI template pitfalls are well-documented

**Research date:** 2026-06-30
**Valid until:** 2026-07-30 (stable domain, no fast-moving dependencies)
