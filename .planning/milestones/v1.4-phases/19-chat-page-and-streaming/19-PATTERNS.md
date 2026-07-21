# Phase 19: Chat Page and Streaming - Pattern Map

**Mapped:** 2026-07-20
**Files analyzed:** 7 (4 new, 2 modified, 1 new test)
**Analogs found:** 7 / 7

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `inference_proxy/api/chat.py` | route | request-response | `inference_proxy/api/dashboard.py` | exact |
| `inference_proxy/templates/chat.html` | template | request-response | `inference_proxy/templates/dashboard.html` | exact |
| `inference_proxy/static/js/chat.js` | client-script | streaming | `inference_proxy/static/js/dashboard.js` | role-match |
| `inference_proxy/static/css/chat.css` | stylesheet | n/a | `inference_proxy/static/css/dashboard.css` | role-match |
| `inference_proxy/main.py` (modify) | config | n/a | self | exact |
| `inference_proxy/templates/dashboard.html` (modify) | template | n/a | self | exact |
| `tests/api/test_chat.py` | test | request-response | `tests/api/test_dashboard.py` | exact |

## Pattern Assignments

### `inference_proxy/api/chat.py` (route, request-response)

**Analog:** `inference_proxy/api/dashboard.py`

**Full file pattern** (lines 1-35) -- copy this file almost verbatim, rename router and route:
```python
"""Dashboard route for the operations UI.

Per D-01: Dashboard served at /dashboard, separate from /admin/* JSON API.
Per D-02: Client-side fetch -- HTML shell rendered by Jinja2, JS fetches /admin/nodes.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

chat_router = APIRouter(tags=["chat"])


@chat_router.get("/chat", response_class=HTMLResponse)
async def chat(request: Request) -> HTMLResponse:
    """Render the chat page HTML shell."""
    return templates.TemplateResponse(request=request, name="chat.html")
```

**Key differences from dashboard.py:**
- No `Depends(get_settings)` needed -- chat page has no server-side config to pass (no `poll_interval` equivalent)
- Single route only (`GET /chat`), no sub-routes
- No context dict needed in `TemplateResponse`

---

### `inference_proxy/templates/chat.html` (template, request-response)

**Analog:** `inference_proxy/templates/dashboard.html`

**Head block pattern** (lines 1-12):
```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>QUADS — Node Fleet Dashboard</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=Open+Sans:wght@400;500;600;700&family=Poppins:wght@500;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="{{ url_for('static', path='css/dashboard.css') }}">
    <script>var __t=localStorage.getItem('theme')||'dark';document.documentElement.dataset.theme=__t;</script>
</head>
```

**Nav bar pattern** (lines 14-22):
```html
<nav class="top-bar" aria-label="Primary">
    <div class="brand">
        <span class="brand-icon" aria-hidden="true">Q</span>
        QUADS
        <span class="brand-sep" aria-hidden="true"></span>
        <span class="brand-sub">Inference Proxy</span>
    </div>
    <button class="theme-toggle" onclick="let t=document.documentElement.dataset.theme==='dark'?'light':'dark';document.documentElement.dataset.theme=t;localStorage.setItem('theme',t);this.textContent=t==='dark'?'☀️':'🌙'" aria-label="Toggle theme"><script>document.write(__t==='dark'?'☀️':'🌙')</script></button>
</nav>
```

**Footer + toast pattern** (lines 69-77):
```html
<div id="toast-container"></div>

<footer>
    <p>QUADS Inference Proxy</p>
</footer>

<script src="{{ url_for('static', path='js/dashboard.js') }}"></script>
```

**Key differences from dashboard.html:**
- Load `chat.css` in addition to `dashboard.css` (reuse base styles + theme vars from dashboard.css)
- Add marked.js CDN `<script>` tag before `chat.js`
- Add "Chat" nav link in top-bar (between brand and theme toggle)
- Body content is chat layout (model selector bar, message area, input bar) instead of dashboard table
- Load `chat.js` instead of `dashboard.js` -- but also load a small inline or shared snippet for `showToast()` (see Shared Patterns below)

---

### `inference_proxy/static/js/chat.js` (client-script, streaming)

**Analog:** `inference_proxy/static/js/dashboard.js`

**Toast reuse pattern** (lines 3-14) -- `showToast()` lives in dashboard.js. Options: (a) duplicate the function in chat.js, (b) extract to shared.js, (c) inline in chat.html. Simplest: duplicate the ~12-line function. It is small enough that DRY is not worth a new file.
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

**Fetch + error handling pattern** (lines 72-92):
```javascript
async function handleAction(action, nodeId) {
  const config = ACTION_CONFIG[action];
  if (!config) return;
  if (config.confirm && !window.confirm(config.confirmMsg(nodeId))) return;
  const options = { method: config.method };
  if (config.body) {
    options.headers = { "Content-Type": "application/json" };
    options.body = JSON.stringify(config.body(nodeId));
  }
  try {
    const resp = await fetch(config.url(nodeId), options);
    if (resp.ok) {
      showToast(config.successMsg(nodeId), "success");
    } else {
      const data = await resp.json().catch(() => ({ detail: `HTTP ${resp.status}` }));
      showToast(data.detail || `HTTP ${resp.status}`, "error");
    }
  } catch (err) {
    showToast(`${config.label} failed: ${err.message}`, "error");
  }
}
```

**DOMContentLoaded init pattern** (lines 258-260):
```javascript
document.addEventListener("DOMContentLoaded", function () {
  refreshDashboard();
  setInterval(refreshDashboard, POLL_INTERVAL_MS);
});
```

**Key differences from dashboard.js:**
- No `ACTION_CONFIG` data-driven dispatch -- chat.js has a single action (send message)
- New: SSE streaming via `fetch` + `ReadableStream` (no existing analog in codebase -- use RESEARCH.md Pattern 2)
- New: `marked.parse()` for markdown rendering (external lib loaded via CDN)
- New: auto-scroll logic (see RESEARCH.md Pattern 3)
- New: model selector population from `GET /v1/models`

---

### `inference_proxy/static/css/chat.css` (stylesheet, n/a)

**Analog:** `inference_proxy/static/css/dashboard.css`

**CSS custom properties** (lines 1-22) -- already defined in dashboard.css, do NOT redeclare. chat.css extends them:
```css
:root {
  --primary: #3B82F6;
  --surface: #FFFFFF;
  --bg: #F3F4F6;
  --text: #111827;
  --border: #E5E7EB;
  --border-strong: #D1D5DB;
  --radius: 0.5rem;
  --radius-lg: 0.75rem;
  /* ... etc -- all already in dashboard.css */
}
```

**Responsive pattern** (lines 478-484):
```css
@media (max-width: 768px) {
  .dashboard { padding: 1rem; }
  .dashboard-header { flex-direction: column; gap: 0.5rem; }
  .header-right { text-align: left; }
  .top-bar { padding: 0 1rem; }
  h1 { font-size: 1.25rem; }
}
```

**Reduced motion pattern** (lines 486-491):
```css
@media (prefers-reduced-motion: reduce) {
  .toast { transition: none; }
  td button { transition: none; }
}
```

**Key differences from dashboard.css:**
- chat.css only contains chat-specific rules (bubbles, message area, input bar, model selector, markdown code blocks)
- All base styles (body, top-bar, toast, theme vars) come from dashboard.css which is also loaded on chat page
- Follow the same `@media` breakpoint (768px) and `prefers-reduced-motion` patterns

---

### `inference_proxy/main.py` (modify -- mount chat_router)

**Router mounting pattern** (lines 259-264):
```python
application.include_router(router)
application.include_router(admin_router)
application.include_router(dashboard_router)
# Add here:
# application.include_router(chat_router)

static_dir = Path(__file__).resolve().parent / "static"
application.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
```

**Import pattern** (lines 29):
```python
from inference_proxy.api.dashboard import dashboard_router
# Add:
# from inference_proxy.api.chat import chat_router
```

---

### `inference_proxy/templates/dashboard.html` (modify -- add Chat nav link)

**Nav bar** (lines 14-22) -- add a "Chat" link between the brand section and the theme toggle button. The nav bar currently has no links, only brand + theme toggle. Add a link element styled consistently.

---

### `tests/api/test_chat.py` (test, request-response)

**Analog:** `tests/api/test_dashboard.py`

**Route test pattern** (lines 19-39):
```python
class TestDashboardRoute:
    """GET /dashboard returns 200 HTML from the same app (DASH-01, DASH-03, TMPL-01)."""

    def test_dashboard_returns_200(self, client: TestClient) -> None:
        """GET /dashboard returns status code 200."""
        response = client.get("/dashboard")
        assert response.status_code == 200

    def test_dashboard_returns_html(self, client: TestClient) -> None:
        """Response content-type contains text/html."""
        response = client.get("/dashboard")
        assert "text/html" in response.headers["content-type"]
```

**Template content test pattern** (lines 42-66):
```python
class TestDashboardTemplate:
    """Dashboard HTML includes expected asset references (TMPL-01, TMPL-02)."""

    def test_contains_google_fonts_link(self, client: TestClient) -> None:
        """HTML contains Google Fonts link for Open Sans, Poppins, IBM Plex Mono."""
        response = client.get("/dashboard")
        assert "fonts.googleapis.com" in response.text

    def test_contains_dashboard_css_link(self, client: TestClient) -> None:
        """HTML contains link to dashboard.css."""
        response = client.get("/dashboard")
        assert "dashboard.css" in response.text

    def test_contains_dashboard_js_script(self, client: TestClient) -> None:
        """HTML contains script tag for dashboard.js."""
        response = client.get("/dashboard")
        assert "dashboard.js" in response.text
```

**Fixture dependency** -- uses `client` fixture from `tests/conftest.py` (line 153):
```python
@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Return a TestClient bound to the test app."""
    return TestClient(app)
```

**Key test assertions for chat page:**
- `GET /chat` returns 200 with `text/html`
- HTML contains `chat.css`, `chat.js`, `marked` script references
- HTML contains model selector element, message area, textarea, send button
- HTML contains `role="log"` and `aria-live="polite"` accessibility attributes

---

## Shared Patterns

### Theme Support (CSS Custom Properties)
**Source:** `inference_proxy/static/css/dashboard.css` lines 1-43
**Apply to:** `chat.css` (inherits vars), `chat.html` (loads dashboard.css first)

All color values use `var(--name)` tokens. Dark theme values set under `[data-theme="dark"]`. Chat page loads `dashboard.css` to get these for free.

### Toast Notifications
**Source:** `inference_proxy/static/js/dashboard.js` lines 3-14
**Apply to:** `chat.js`

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
Toast CSS classes (`.toast`, `.toast-success`, `.toast-error`) already in `dashboard.css`. Chat page gets them by loading `dashboard.css`.

### Nav Bar
**Source:** `inference_proxy/templates/dashboard.html` lines 14-22
**Apply to:** `chat.html` (copy nav bar), `dashboard.html` (add Chat link)

Both templates must have the "Chat" link in the nav bar for consistency.

### Jinja2 Static File References
**Source:** `inference_proxy/templates/dashboard.html` lines 10, 76
**Apply to:** `chat.html`

```html
<link rel="stylesheet" href="{{ url_for('static', path='css/chat.css') }}">
<script src="{{ url_for('static', path='js/chat.js') }}"></script>
```

### Test Fixture Chain
**Source:** `tests/conftest.py` lines 98-155
**Apply to:** `tests/api/test_chat.py`

Tests use the `client` fixture which depends on `app` fixture. The `app` fixture creates a real FastAPI app with mocked dependencies. No additional fixtures needed for chat route tests -- the existing chain works as-is since `chat_router` is mounted in `create_app()`.

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| (none) | -- | -- | All files have analogs |

**SSE streaming consumption** in `chat.js` has no existing client-side analog in this codebase (server-side SSE exists in `routes.py` but client-side is new). Use RESEARCH.md Pattern 2 (`fetch` + `ReadableStream`) for this.

**Markdown rendering** via `marked.js` is entirely new to this codebase. Use RESEARCH.md CDN example for loading.

---

## Metadata

**Analog search scope:** `inference_proxy/api/`, `inference_proxy/templates/`, `inference_proxy/static/`, `tests/api/`
**Files scanned:** 8 analog files read
**Pattern extraction date:** 2026-07-20
