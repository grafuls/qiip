# Phase 32: Dashboard Download Integration - Pattern Map

**Mapped:** 2026-07-28
**Files analyzed:** 1 (modify only)
**Analogs found:** 1 / 1

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `inference_proxy/static/js/node_detail.js` | component | request-response + polling | itself (self-modify) | exact |

Single file change. Every pattern lives in the file being modified.

## Pattern Assignments

### `inference_proxy/static/js/node_detail.js` (component, request-response + polling)

**Analog:** Same file — all patterns below are from `node_detail.js` itself.

**Parallel fetch pattern** (lines 143-147):
```javascript
var [nodesResp, metricsResp, tasksResp] = await Promise.all([
  fetch("/admin/nodes"),
  fetch("/admin/metrics"),
  fetch("/admin/provisioning/tasks"),
]);
```
Use this to add catalog + downloads fetch inside `loadRecommendations()`:
- `fetch("/admin/models/catalog")` returns `{ models: [{ repo_id }] }`
- `fetch("/admin/models/downloads")` returns `[{ repo_id, status, error }]`

**Table building via innerHTML concatenation** (lines 338-356):
```javascript
var FIT_BADGE = { perfect: "badge-complete", good: "badge-in-progress", marginal: "badge-failed" };
var table = document.createElement("div");
table.className = "table-wrap";
var html = "<table><thead><tr>" +
  "<th>Model</th><th>Category</th><th>Score</th><th>Fit</th><th>Est. tok/s</th><th>Memory</th>" +
  "</tr></thead><tbody>";
for (var i = 0; i < data.models.length; i++) {
  var m = data.models[i];
  var badgeCls = FIT_BADGE[m.fit_level] || "badge-in-progress";
  html += "<tr>" +
    "<td>" + m.name + "</td>" +
    "<td>" + (m.category || "—") + "</td>" +
    "<td>" + m.score.toFixed(1) + "%</td>" +
    "<td><span class=\"badge " + badgeCls + "\">" + m.fit_level + "</span></td>" +
    "<td>" + m.estimated_tps.toFixed(1) + "</td>" +
    "<td>" + m.memory_required_gb.toFixed(1) + " GB</td>" +
    "</tr>";
}
html += "</tbody></table>";
table.innerHTML = html;
content.textContent = "";
content.appendChild(table);
```
Add `<th>Download</th>` to header. Add a `<td>` per row with button/badge based on download state.

**Async button with disabled state** (lines 103-106 in createActionsDropdown):
```javascript
btn.addEventListener("click", async function () {
  btn.disabled = true;
  menu.classList.remove("open");
  try { await handleAction(action, nodeId); } finally { btn.disabled = false; }
});
```
Same pattern for download button: disable on click, POST, re-enable or switch to badge on success.

**Action fetch pattern** (lines 52-76):
```javascript
async function handleAction(action, nodeId) {
  var config = ACTION_CONFIG[action];
  if (!config) return;
  if (config.confirm && !window.confirm(config.confirmMsg(nodeId))) return;
  var options = { method: config.method };
  if (config.body) {
    options.headers = { "Content-Type": "application/json" };
    options.body = JSON.stringify(config.body(nodeId));
  }
  try {
    var resp = await fetch(config.url(nodeId), options);
    if (resp.ok) {
      showToast(config.successMsg(nodeId), "success");
    } else {
      var data = await resp.json().catch(function () { return { detail: "HTTP " + resp.status }; });
      showToast(data.detail || "HTTP " + resp.status, "error");
    }
  } catch (err) {
    showToast(config.label + " failed: " + err.message, "error");
  }
}
```
Download trigger calls `POST /admin/models/download` with `{ repo_id: modelName }`.

**Toast notification** (lines 3-14):
```javascript
function showToast(message, type) {
  var container = document.getElementById("toast-container");
  var toast = document.createElement("div");
  toast.className = "toast toast-" + (type || "info");
  toast.textContent = message;
  container.appendChild(toast);
  requestAnimationFrame(function () { toast.classList.add("toast-visible"); });
  setTimeout(function () {
    toast.classList.remove("toast-visible");
    setTimeout(function () { toast.remove(); }, 300);
  }, 4000);
}
```

**Polling pattern** (lines 376-379):
```javascript
document.addEventListener("DOMContentLoaded", function () {
  refreshDetail();
  setInterval(refreshDetail, POLL_INTERVAL_MS);
});
```
Download polling uses the same `setInterval` but starts only after first download trigger (D-04) and stops when no downloads have `status === "downloading"`.

**Badge class mapping** (line 335 + CSS lines 331-358):
```javascript
var FIT_BADGE = { perfect: "badge-complete", good: "badge-in-progress", marginal: "badge-failed" };
```
Download state mapping follows the same pattern:
- `"complete"` -> `badge-complete` (green)
- `"downloading"` -> `badge-in-progress` (blue)
- `"failed"` -> `badge-failed` (red)

**Error response handling** (lines 308-316):
```javascript
var err = await resp.json().catch(function () { return { detail: "HTTP " + resp.status }; });
showToast(msgs[err.error_type] || err.detail || "Failed to load recommendations", "error");
```

## Shared Patterns

### Badge CSS Classes
**Source:** `inference_proxy/static/css/dashboard.css` lines 319-358
**Apply to:** Download column cells

Existing classes cover all three download states with no new CSS:
- `badge badge-complete` — green, for downloaded models
- `badge badge-in-progress` — blue, for downloading
- `badge badge-failed` — red, for failed downloads

### Button CSS
**Source:** `inference_proxy/static/css/dashboard.css` lines 392-393
**Apply to:** Download button (not-yet-downloaded state)
```css
.btn-setup { color: var(--primary); border-color: var(--primary); }
.btn-setup:hover:not(:disabled) { background: var(--primary); color: #fff; border-color: var(--primary); }
```

### API Response Shapes
**Source:** `inference_proxy/models/admin.py` lines 153-170, `inference_proxy/huggingface/catalog.py` lines 18-27

POST `/admin/models/download` body: `{ "repo_id": "..." }` -> returns `{ repo_id, status, started_at, completed_at, error }`
GET `/admin/models/downloads` -> returns `[{ repo_id, status, started_at, completed_at, error }]`
GET `/admin/models/catalog` -> returns `{ models: [{ repo_id }] }`

`status` is one of: `"downloading"`, `"complete"`, `"failed"`

## No Analog Found

None. All patterns exist within the file being modified.

## Metadata

**Analog search scope:** `inference_proxy/static/js/`, `inference_proxy/static/css/`, `inference_proxy/templates/`, `inference_proxy/api/`, `inference_proxy/models/`
**Files scanned:** 6
**Pattern extraction date:** 2026-07-28
