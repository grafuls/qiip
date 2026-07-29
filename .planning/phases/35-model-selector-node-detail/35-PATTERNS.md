# Phase 35: Model Selector on Node Detail Page - Pattern Map

**Mapped:** 2026-07-29
**Files analyzed:** 2 (both modifications, no new files)
**Analogs found:** 2 / 2

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `inference_proxy/templates/node_detail.html` | template | request-response | itself (existing `.card` sections) | exact |
| `inference_proxy/static/js/node_detail.js` | client-script | request-response | itself (`loadRecommendations()` catalog fetch, `ACTION_CONFIG.setup.body`) | exact |

## Pattern Assignments

### `inference_proxy/templates/node_detail.html` (template, request-response)

**Analog:** Same file -- existing card sections.

**Card section pattern** (lines 42-64, Node Info card):
```html
<section class="card">
    <h2 class="card-title">Node Info</h2>
    <div class="table-wrap">
        ...
    </div>
</section>
```
New "Setup Configuration" card goes between the Node Info card (ends line 64) and the recommendations-panel card (starts line 66). Same `<section class="card">` wrapper with `<h2 class="card-title">`.

**Insertion point** (between lines 64 and 66):
```html
<!-- after </section> closing Node Info card (line 64) -->
<section class="card" id="setup-config-panel">
    <h2 class="card-title">Setup Configuration</h2>
    <!-- model selector content here -->
</section>
<!-- before <section class="card" id="recommendations-panel"> (line 66) -->
```

**Form input styling reference** -- the `setup-form` CSS (dashboard.css lines 233-276) already styles `select` inputs similarly to text inputs. The native `<select>` should use the same CSS custom properties for theme compatibility:
```css
/* From dashboard.css lines 242-253 -- input styling pattern */
background: var(--bg);
border: 1px solid var(--border-strong);
border-radius: var(--radius);
color: var(--text);
font-size: 0.8125rem;
```

**Muted text pattern** (line 72, recommendations empty state):
```html
<span style="color:var(--muted);font-size:0.875rem">Click Load to fetch model recommendations for this node.</span>
```
Same inline style for the "No models downloaded" empty state message. Note: use `var(--text-light)` -- `--muted` is not defined in the CSS, but the existing code uses `var(--muted)` in inline styles (line 72, 400, 462). Grep confirms it is used but never defined -- the browser falls back. Use `var(--text-light)` for consistency with the CSS variables that are actually defined.

---

### `inference_proxy/static/js/node_detail.js` (client-script, request-response)

**Analog:** Same file -- `loadRecommendations()` catalog fetch (lines 426-442) and `ACTION_CONFIG` body functions (lines 16-50).

**Catalog fetch pattern** (lines 426-434, inside `loadRecommendations`):
```javascript
var catalogSet = new Set();
try {
  var catalogResp = await fetch("/admin/models/catalog");
  if (catalogResp.ok) {
    var catalogData = await catalogResp.json();
    catalogSet = new Set(catalogData.models.map(function (m) { return m.repo_id; }));
  }
} catch (_) { /* catalog unavailable */ }
```
The new `loadCatalog()` function follows this exact shape: fetch `/admin/models/catalog`, parse `catalogData.models` array where each entry has `repo_id`. On failure, degrade gracefully (empty catalog = disable setup).

**API response shape** (confirmed from `inference_proxy/huggingface/catalog.py`):
```
GET /admin/models/catalog -> { models: [{ repo_id: "org/model-name" }, ...] }
```

**ACTION_CONFIG.body function pattern** (lines 17-19, setup action):
```javascript
setup: {
  method: "POST", url: function () { return "/admin/nodes/setup"; },
  body: function (id) { return { hostname: id }; }, confirm: false,
  ...
},
```
Modify `body` to read the selected model from the DOM:
```javascript
body: function (id) {
  var sel = document.getElementById("model-select");
  var model = sel ? sel.value : null;
  return { hostname: id, model: model };
},
```
Same change for `retry` (lines 31-32). The `SetupRequest` model already accepts an optional `model` field (line 67 of `inference_proxy/models/admin.py`).

**ACTION_CONFIG.retry.body pattern** (lines 31-32):
```javascript
retry: {
  method: "POST", url: function () { return "/admin/nodes/setup"; },
  body: function (id) { return { hostname: id }; }, confirm: false,
  ...
},
```
Identical to setup -- same modification needed.

**DOMContentLoaded pattern** (lines 629-633):
```javascript
document.addEventListener("DOMContentLoaded", function () {
  refreshDetail();
  refreshPowerState();
  setInterval(refreshDetail, POLL_INTERVAL_MS);
});
```
Add `loadCatalog();` call here. Per D-04, fetch catalog once on page load (no polling).

**Disabling actions based on state** -- `createActionsDropdown` (lines 78-126):
```javascript
function createActionsDropdown(nodeId, enabledActions) {
  ...
  var enabled = enabledActions.indexOf(action) !== -1;
  btn.disabled = !enabled;
  ...
}
```
The `enabledActions` array comes from `node.actions` (line 181):
```javascript
tdAc.appendChild(createActionsDropdown(node.node_id, node.actions || []));
```
To disable setup when catalog is empty: filter "setup" from `node.actions` before passing to `createActionsDropdown`. This happens in `refreshDetail()` at line 181. Use a module-level flag (e.g., `catalogModels`) set by `loadCatalog()`, then filter in `refreshDetail`:
```javascript
var actions = node.actions || [];
if (catalogModels !== null && catalogModels.length === 0) {
  actions = actions.filter(function (a) { return a !== "setup"; });
}
```

**Module-level state pattern** (lines 293-295, existing catalog cache):
```javascript
var catalogSetCache = new Set();
var downloadPollTimer = null;
```
Same pattern for the new catalog model list -- a module-level variable populated once by `loadCatalog()`.

**Function scope pattern**: All functions are declared at module top level -- no IIFE, no module system. `loadCatalog` must follow the same convention.

**Select population pattern** -- no existing `<select>` in this file, but the DOM creation pattern is consistent throughout (lines 160-184):
```javascript
var el = document.createElement("td");
el.textContent = node.gpu_vendor || "---";
```
For the `<select>`:
```javascript
var select = document.getElementById("model-select");
select.textContent = ""; // clear existing options
for (var i = 0; i < models.length; i++) {
  var opt = document.createElement("option");
  opt.value = models[i].repo_id;
  opt.textContent = models[i].repo_id;
  select.appendChild(opt);
}
```

---

## Shared Patterns

### Fetch + Silent Degradation
**Source:** `inference_proxy/static/js/node_detail.js` lines 426-434
**Apply to:** `loadCatalog()` function

Catalog fetch failures degrade silently -- no toast, just leave the selector in empty state (which disables setup). Same pattern as the catalog fetch inside `loadRecommendations()`.

### CSS Custom Properties for Theme
**Source:** `inference_proxy/static/css/dashboard.css` lines 1-43
**Apply to:** Inline styles on the `<select>` element

Use `var(--bg)`, `var(--border-strong)`, `var(--text)`, `var(--radius)` for theme-compatible styling. The `setup-form input[type="text"]` styles (lines 242-253) are the closest reference for form input appearance.

### Card Structure
**Source:** `inference_proxy/templates/node_detail.html` lines 42-64
**Apply to:** New Setup Configuration card

`<section class="card" id="...">` with `<h2 class="card-title">Title</h2>` followed by content.

## No Analog Found

None -- both files modify existing code with patterns already present in those files.

## Metadata

**Analog search scope:** `inference_proxy/templates/`, `inference_proxy/static/js/`, `inference_proxy/static/css/`, `inference_proxy/api/`, `inference_proxy/models/`, `inference_proxy/huggingface/`
**Files scanned:** 6
**Pattern extraction date:** 2026-07-29
