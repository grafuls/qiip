---
phase: 32-dashboard-download-integration
reviewed: 2026-07-29T12:00:00Z
depth: standard
files_reviewed: 1
files_reviewed_list:
  - inference_proxy/static/js/node_detail.js
findings:
  critical: 3
  warning: 2
  info: 1
  total: 6
status: fixed
---

# Phase 32: Code Review Report

**Reviewed:** 2026-07-29
**Depth:** standard
**Files Reviewed:** 1
**Status:** issues_found

## Summary

Single file reviewed: `node_detail.js`. The file adds model download integration (download button, polling, catalog cache) to the node detail dashboard. Most DOM construction uses safe `createElement`/`textContent` patterns, but the recommendations table and hardware summary are built via `innerHTML` with server-sourced strings, creating XSS vectors. A logic bug in error handling passes empty state instead of the cached catalog, causing incorrect UI after network failures.

## Critical Issues

### CR-01: XSS via innerHTML in model recommendation table

**File:** `inference_proxy/static/js/node_detail.js:456-472`
**Issue:** The model table is built as an HTML string interpolating `m.name`, `m.category`, and `m.fit_level` directly from the server JSON response (`/admin/nodes/{hostname}/recommendations`). These values originate from `llmfit recommend --json` output, which parses external model metadata. A model name containing `<img onerror=alert(1)>` or similar would execute in the browser. The rest of the file correctly uses `createElement`/`textContent` for safe DOM construction -- this section is the exception.
**Fix:** Build the table rows with `createElement`/`textContent` the same way the rest of the file does, or at minimum escape all interpolated values:
```javascript
// Replace innerHTML table construction (lines 456-472) with createElement approach:
var tbody = document.createElement("tbody");
for (var i = 0; i < data.models.length; i++) {
  var m = data.models[i];
  var badgeCls = FIT_BADGE[m.fit_level] || "badge-in-progress";
  var row = document.createElement("tr");

  var cells = [m.name, m.category || "—", m.score.toFixed(1) + "%"];
  for (var c = 0; c < cells.length; c++) {
    var td = document.createElement("td");
    td.textContent = cells[c];
    row.appendChild(td);
  }
  // fit_level badge
  var tdFit = document.createElement("td");
  var fitBadge = document.createElement("span");
  fitBadge.className = "badge " + badgeCls;
  fitBadge.textContent = m.fit_level;
  tdFit.appendChild(fitBadge);
  row.appendChild(tdFit);
  // remaining numeric cells
  var tdTps = document.createElement("td"); tdTps.textContent = m.estimated_tps.toFixed(1); row.appendChild(tdTps);
  var tdMem = document.createElement("td"); tdMem.textContent = m.memory_required_gb.toFixed(1) + " GB"; row.appendChild(tdMem);

  tbody.appendChild(row);
}
// Build table with static thead innerHTML (safe -- no user data), append tbody
```

### CR-02: XSS via innerHTML in hardware summary

**File:** `inference_proxy/static/js/node_detail.js:445-447`
**Issue:** `sys.gpu_name` and `sys.backend` are interpolated into `hwSummary.innerHTML`. These values come from the `SystemInfo` Pydantic model which parses `llmfit` output. GPU names are typically benign but the data originates from an external tool parsing system hardware -- the contract does not guarantee HTML-safe values.
**Fix:** Use `textContent` or `createElement` for the dynamic parts:
```javascript
hwSummary.textContent = "";
var parts = [
  ["GPU: ", sys.gpu_name || "Unknown"],
  [" · VRAM: ", sys.gpu_vram_gb.toFixed(1) + " GB"],
  [" · Backend: ", sys.backend || "Unknown"],
];
for (var p = 0; p < parts.length; p++) {
  var label = document.createElement("strong");
  label.textContent = parts[p][0];
  hwSummary.appendChild(label);
  hwSummary.appendChild(document.createTextNode(parts[p][1]));
}
```

### CR-03: XSS via innerHTML with server error detail

**File:** `inference_proxy/static/js/node_detail.js:415`
**Issue:** `err.detail` from the server error response is interpolated into `content.innerHTML`. The backend constructs `detail` strings from SSH error output and llmfit parse failures (see `admin.py:340-354`), which could contain arbitrary text including HTML-like content from the remote process.
**Fix:**
```javascript
content.textContent = "";
var errSpan = document.createElement("span");
errSpan.className = "error-text";
errSpan.textContent = err.detail || "Failed to load";
content.appendChild(errSpan);
```

## Warnings

### WR-01: Catalog cache bypassed on error paths in triggerDownload

**File:** `inference_proxy/static/js/node_detail.js:353,357`
**Issue:** Both the HTTP error (line 353) and network error (line 357) branches call `renderDownloadCell` with `new Set()` instead of the module-level `catalogSetCache`. If a model is already in the catalog (previously downloaded), the cell incorrectly shows "Failed -- Retry" or "Download" instead of "Downloaded" after a transient error. The `renderDownloadCell` function checks `catalogSet.has(modelName)` at line 310, which would correctly show "Downloaded" if the real cache were passed.
**Fix:**
```javascript
// Line 353: replace new Set() with catalogSetCache
renderDownloadCell(td, repoId, catalogSetCache, { [repoId]: { status: "failed" } });

// Line 357: replace new Set() with catalogSetCache
renderDownloadCell(td, repoId, catalogSetCache, {});
```

### WR-02: Always-true conditional guards a block that always runs

**File:** `inference_proxy/static/js/node_detail.js:65`
**Issue:** The condition `action === "setup" || action === "retry" || action === "teardown" || action === "cancel" || action === "force_teardown"` enumerates every key in `ACTION_CONFIG`. Since `handleAction` returns early at line 54 when `action` is not in `ACTION_CONFIG`, this condition is always true when reached. The log-reset block (lines 66-68) runs unconditionally for every action. If a new action is added that should not reset log state, a developer would likely not notice this "selective" check is actually exhaustive and would need to be updated to exclude the new action.
**Fix:** Either remove the condition (since it is always true and the intent is "reset logs after any action"):
```javascript
if (resp.ok) {
  showToast(config.successMsg(nodeId), "success");
  logReceivedAny = false; logStreamDone = false;
  if (logSource) { logSource.close(); logSource = null; }
}
```
Or add a comment documenting the intent if the filter is meant to be selective in the future.

## Info

### IN-01: Silent catch in SSE message handler hides malformed events

**File:** `inference_proxy/static/js/node_detail.js:276`
**Issue:** `catch (_) {}` silently swallows all errors when processing SSE messages, including cases where expected fields like `entry.ts` or `entry.msg` are missing or have unexpected types (e.g., `new Date(undefined).toLocaleTimeString()` returns "Invalid Date" string but does not throw). JSON parse failure of `ev.data` is silently dropped. During development or debugging, this makes it impossible to notice malformed log events from the backend.
**Fix:** At minimum, log the error to the console in a dev-friendly way, or guard expected fields:
```javascript
catch (e) {
  // ponytail: surface parse failures during development
  if (typeof console !== "undefined") console.warn("SSE parse error:", e);
}
```

---

_Reviewed: 2026-07-29_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
