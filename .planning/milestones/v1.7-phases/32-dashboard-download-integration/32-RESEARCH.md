# Phase 32: Dashboard Download Integration - Research

**Researched:** 2026-07-28
**Domain:** Frontend JS (vanilla), DOM manipulation, polling
**Confidence:** HIGH

## Summary

This phase modifies a single file (`inference_proxy/static/js/node_detail.js`) to add download functionality to the existing recommendations table. All backend endpoints already exist and are verified in the codebase. The work is purely client-side: fetch catalog data in parallel with recommendations, cross-reference via a `Set`, add a Download column, and poll for status updates after a download is triggered.

The codebase uses vanilla JS with `createElement`/`innerHTML`, `fetch`, `Promise.all`, and `setInterval` -- no framework, no build step. All CSS classes needed (`badge-complete`, `badge-in-progress`, `badge-failed`, `btn-setup`) already exist in `dashboard.css`.

**Primary recommendation:** Extend `loadRecommendations()` to fetch catalog + downloads in parallel, add a 7th "Download" column, and start a 4s `setInterval` poll after the first download trigger. No new files, no CSS changes, no backend changes.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Client-side merge -- JS fetches both `/admin/nodes/{id}/recommendations` AND `/admin/models/catalog` in parallel, cross-references `repo_id`s via a `Set`. No backend changes needed.
- **D-02:** llmfit model `name` IS the HF `repo_id` -- zero mapping needed between recommendation names and catalog repo_ids.
- **D-03:** Poll GET `/admin/models/downloads` on a 4-second timer after any download is triggered. Update button states in-place via DOM manipulation. Stop polling when no downloads have `status === 'downloading'`. Matches the existing `setInterval` pattern.
- **D-04:** Polling starts only after the first download trigger -- no polling overhead when no downloads are active.
- **D-05:** Three-state button: `[Download]` -> `[Downloading...]` -> `[Downloaded]` / `[Failed -- Retry]`.
- **D-06:** Reuse existing CSS badge classes (`badge-complete`, `badge-in-progress`, `badge-failed`) -- no new CSS needed.
- **D-07:** Single new "Download" column appended at the end of the recommendations table.

### Claude's Discretion
None specified -- implementation details within the locked decisions are open.

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DASH-01 | Download button per recommended model | D-05 three-state button, `btn-setup` class for Download state, verified in CSS |
| DASH-02 | "Already downloaded" badge when model on NFS | D-01 catalog cross-reference via Set, D-02 name=repo_id, catalog response shape verified |
| DASH-03 | Download status visible and auto-updates | D-03 polling at 4s, D-04 lazy start, download status response shape verified |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Download button rendering | Browser / Client | -- | DOM manipulation in vanilla JS |
| Catalog cross-reference | Browser / Client | -- | Set-based lookup, no server join needed |
| Download trigger | Browser / Client | API / Backend | Client sends POST, backend runs download |
| Status polling | Browser / Client | API / Backend | Client polls GET, backend returns statuses |
| Download execution | API / Backend | -- | Already implemented in DownloadService |

## Standard Stack

No new libraries. This phase modifies one existing JS file using existing patterns.

### Existing Assets Used
| Asset | Location | Purpose |
|-------|----------|---------|
| `showToast()` | `node_detail.js` line 3-14 | User feedback on download trigger success/failure |
| `badge-complete` CSS | `dashboard.css` line 331-337 | "Downloaded" badge styling |
| `badge-in-progress` CSS | `dashboard.css` line 354-358 | "Downloading..." badge styling |
| `badge-failed` CSS | `dashboard.css` line 339-343 | "Failed" badge styling |
| `btn-setup` CSS | `dashboard.css` line 392-393 | "Download" button styling |
| `Promise.all` pattern | `node_detail.js` line 143 | Parallel fetch of recommendations + catalog |
| `setInterval` pattern | `node_detail.js` line 378 | Polling model for download status |

## Architecture Patterns

### System Architecture Diagram

```
User clicks "Load" button
         |
         v
loadRecommendations()
         |
    Promise.all([
      GET /admin/nodes/{id}/recommendations  -->  { hostname, system, models[] }
      GET /admin/models/catalog              -->  { models: [{repo_id}] }
    ])
         |
         v
   Build catalogSet = new Set(catalog.models.map(m => m.repo_id))
         |
         v
   For each recommendation model:
     catalogSet.has(model.name)?
       YES --> render "Downloaded" badge (badge-complete)
       NO  --> render "Download" button (btn-setup)
         |
         v
   User clicks "Download" button
         |
         v
   POST /admin/models/download {repo_id: model.name}
         |  202 response
         v
   Set button to "Downloading..." (badge-in-progress, disabled)
   Start 4s poll (if not already running)
         |
         v
   setInterval @ 4s:
     GET /admin/models/downloads --> [{repo_id, status, ...}]
         |
         v
   For each download status:
     Find matching cell in table by data-repo-id
     Update button state:
       "downloading" --> "Downloading..." (badge-in-progress)
       "complete"    --> "Downloaded" (badge-complete)
       "failed"      --> "Failed -- Retry" (badge-failed, clickable)
         |
         v
   No downloads with status==="downloading"?
     YES --> clearInterval, stop polling
```

### Pattern 1: Parallel Fetch with Cross-Reference
**What:** Fetch recommendations and catalog in a single `Promise.all`, then build a `Set` for O(1) lookup.
**When to use:** When rendering the recommendations table.
**Example:**
```javascript
// Source: existing pattern in node_detail.js line 143
var [recsResp, catalogResp] = await Promise.all([
  fetch("/admin/nodes/" + encodeURIComponent(NODE_ID) + "/recommendations"),
  fetch("/admin/models/catalog")
]);
var recsData = await recsResp.json();
var catalogData = await catalogResp.json();
var catalogSet = new Set(catalogData.models.map(function(m) { return m.repo_id; }));
// Then for each model: catalogSet.has(model.name)
```

### Pattern 2: Lazy Polling with Auto-Stop
**What:** Start a `setInterval` only after the first download trigger. Stop when no downloads are active.
**When to use:** After any download button is clicked.
**Example:**
```javascript
// Source: matches existing setInterval pattern at node_detail.js line 378
var downloadPollTimer = null;

function startDownloadPolling() {
  if (downloadPollTimer) return; // already polling
  downloadPollTimer = setInterval(pollDownloadStatuses, 4000);
}

async function pollDownloadStatuses() {
  var resp = await fetch("/admin/models/downloads");
  var downloads = await resp.json();
  // Update DOM cells...
  var anyActive = downloads.some(function(d) { return d.status === "downloading"; });
  if (!anyActive) {
    clearInterval(downloadPollTimer);
    downloadPollTimer = null;
  }
}
```

### Pattern 3: Data Attribute for Cell Lookup
**What:** Tag each Download cell with `data-repo-id` so the poll updater can find it without re-rendering the whole table.
**When to use:** When building table rows and when updating from poll results.
**Example:**
```javascript
// Build phase: tag the cell
var tdDl = document.createElement("td");
tdDl.dataset.repoId = m.name;

// Poll update phase: find the cell
var cells = document.querySelectorAll("td[data-repo-id]");
for (var i = 0; i < cells.length; i++) {
  var repoId = cells[i].dataset.repoId;
  var dl = downloadMap[repoId];
  if (dl) { /* update cell content based on dl.status */ }
}
```

### Anti-Patterns to Avoid
- **Re-rendering the whole table on poll:** The table is built by `loadRecommendations()` which triggers SSH+llmfit on the remote host. The poll updater must only update the Download column cells, never re-call `loadRecommendations()`.
- **Starting poll on page load:** D-04 explicitly says polling starts only after first download trigger. No wasted requests.
- **Using innerHTML for button creation in the Download column:** The Download button needs an event listener. Use `createElement` + `addEventListener` (matches existing pattern in `createActionsDropdown`).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| CSS badge styles | New CSS classes | Existing `badge-complete`, `badge-in-progress`, `badge-failed` | Already defined, tested, themed for light/dark |
| Button styling | New button CSS | Existing `btn-setup` class | Matches visual language of other action buttons |
| Toast notifications | Custom alert | Existing `showToast()` | Already handles success/error with auto-dismiss |
| Polling mechanism | Custom event system | `setInterval` / `clearInterval` | Same pattern used for node status refresh |

## Common Pitfalls

### Pitfall 1: Catalog Fetch Failure Blocking Recommendations
**What goes wrong:** If `/admin/models/catalog` returns an error, the entire `loadRecommendations` fails and no table is shown.
**Why it happens:** Naive `Promise.all` rejects on first failure.
**How to avoid:** Fetch catalog separately and gracefully degrade -- if catalog fails, render all models with Download buttons (assume not downloaded). The recommendations data is the primary content.
**Warning signs:** Error toast but no table visible.

### Pitfall 2: Race Between Download Trigger and Poll Update
**What goes wrong:** User clicks Download, POST returns 202, but the next poll happens before the download service registers the status -- button flashes back to "Download" briefly.
**Why it happens:** The POST response already contains the status. The poll may not reflect it yet if timing is tight.
**How to avoid:** Immediately update the button to "Downloading..." on successful POST response (don't wait for poll to confirm). The poll then reinforces/updates the state.
**Warning signs:** Button flickering between states.

### Pitfall 3: Stale Table After Re-Load
**What goes wrong:** User clicks "Reload" to re-fetch recommendations. The new table doesn't reflect current download states.
**Why it happens:** `loadRecommendations()` rebuilds the table from scratch. If no poll is running (all downloads completed), the new table only shows catalog-based "Downloaded" badges -- it misses recently-completed downloads that aren't yet on NFS (download complete but catalog not yet refreshed).
**How to avoid:** When rebuilding the table, also fetch `/admin/models/downloads` alongside catalog. Cross-reference both: `catalogSet.has(name)` OR download status is "complete" means show "Downloaded". This also catches "downloading" and "failed" states.
**Warning signs:** Model shows "Download" button immediately after a successful download when user clicks Reload.

### Pitfall 4: Multiple Timers from Multiple Download Clicks
**What goes wrong:** Each download click starts a new `setInterval`, creating N concurrent poll loops.
**Why it happens:** No guard checking if a timer is already running.
**How to avoid:** Store the timer ID in a module-level variable. Check `if (downloadPollTimer) return;` before creating a new one.
**Warning signs:** Network tab shows multiple simultaneous GET /admin/models/downloads requests every 4 seconds.

### Pitfall 5: Duplicate Download POST on Model Already Downloading
**What goes wrong:** User clicks Download while another tab/session already triggered a download for the same model.
**Why it happens:** The button only knows local state.
**How to avoid:** The backend handles this via D-10 idempotency (returns 200 with existing status instead of 202). The frontend should treat both 200 and 202 as success and switch the button to "Downloading...". No special handling needed beyond accepting both status codes.
**Warning signs:** None -- the backend is already safe. Just don't treat 200 as an error.

## Code Examples

### Verified API Response Shapes

```javascript
// GET /admin/nodes/{hostname}/recommendations
// Source: inference_proxy/models/admin.py:173-180, models/llmfit.py
{
  "hostname": "node01.example.com",
  "system": {
    "has_gpu": true,
    "gpu_vram_gb": 48.0,
    "gpu_name": "NVIDIA A6000",
    "cpu_name": "AMD EPYC 7763",
    "total_ram_gb": 512.0,
    "available_ram_gb": 480.0,
    "cpu_cores": 64,
    "unified_memory": false,
    "backend": "cuda"
  },
  "models": [
    {
      "name": "meta-llama/Meta-Llama-3.1-70B-Instruct",  // THIS is the repo_id (D-02)
      "score": 92.5,
      "fit_level": "perfect",      // "perfect" | "good" | "marginal"
      "estimated_tps": 45.2,
      "memory_required_gb": 38.5,
      "category": "chat",
      "provider": "Meta",
      "best_quant": "AWQ",
      "run_mode": "gpu",
      "params_b": 70.0,
      "context_length": 131072,
      "utilization_pct": 80.2,
      "runtime": "vllm"
    }
  ]
}

// GET /admin/models/catalog
// Source: inference_proxy/huggingface/catalog.py:18-27
{
  "models": [
    { "repo_id": "meta-llama/Meta-Llama-3.1-70B-Instruct" }
  ]
}

// POST /admin/models/download  (body: {"repo_id": "..."})
// Returns 202 for new, 200 for already-in-progress (D-10)
// Source: inference_proxy/models/admin.py:161-170
{
  "repo_id": "meta-llama/Meta-Llama-3.1-70B-Instruct",
  "status": "downloading",       // "downloading" | "complete" | "failed"
  "started_at": "2026-07-28T10:00:00Z",
  "completed_at": null,          // null while downloading
  "error": null                  // null unless failed
}

// GET /admin/models/downloads
// Source: inference_proxy/huggingface/downloader.py:54-57
// Returns: Array of DownloadStatusResponse (same shape as POST response)
[
  {
    "repo_id": "meta-llama/Meta-Llama-3.1-70B-Instruct",
    "status": "downloading",
    "started_at": "2026-07-28T10:00:00Z",
    "completed_at": null,
    "error": null
  }
]
```

[VERIFIED: codebase grep -- all response shapes confirmed from Pydantic models in inference_proxy/models/admin.py, inference_proxy/models/llmfit.py, and inference_proxy/huggingface/catalog.py]

### Three-State Button Rendering Logic

```javascript
// Source: pattern derived from existing badge/button usage in node_detail.js

function renderDownloadCell(td, modelName, catalogSet, downloadMap) {
  td.textContent = "";
  td.dataset.repoId = modelName;

  var dl = downloadMap[modelName];

  if (dl && dl.status === "downloading") {
    // State 2: Download in progress
    var badge = document.createElement("span");
    badge.className = "badge badge-in-progress";
    badge.textContent = "Downloading…";
    td.appendChild(badge);
  } else if (dl && dl.status === "complete" || catalogSet.has(modelName)) {
    // State 3a: Downloaded (via download service OR already on NFS)
    var badge = document.createElement("span");
    badge.className = "badge badge-complete";
    badge.textContent = "Downloaded";
    td.appendChild(badge);
  } else if (dl && dl.status === "failed") {
    // State 3b: Failed -- retry
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "badge badge-failed";
    btn.style.cursor = "pointer";
    btn.textContent = "Failed — Retry";
    btn.addEventListener("click", function() { triggerDownload(modelName, td); });
    td.appendChild(btn);
  } else {
    // State 1: Not downloaded, no download in progress
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn-setup";
    btn.textContent = "Download";
    btn.addEventListener("click", function() { triggerDownload(modelName, td); });
    td.appendChild(btn);
  }
}
```

### Operator Precedence Note

The three-state logic must evaluate in this order:
1. **downloading** -- takes priority (even if catalog has it -- download could be a re-download)
2. **complete OR in catalog** -- model is available
3. **failed** -- last download attempt failed
4. **default** -- not downloaded, show button

This order matters because a model could be both in the catalog (already on NFS) AND have a "failed" download entry from a previous attempt. The catalog presence should win.

## State of the Art

No new approaches needed. Vanilla JS + `fetch` + DOM manipulation is the established pattern in this codebase. The `setInterval` polling pattern is already used for node status refresh.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| -- | -- | -- | -- |

**All claims in this research were verified from the codebase source code -- no user confirmation needed.**

## Open Questions

None. All API shapes, CSS classes, and JS patterns are verified from the codebase.

## Project Constraints (from CLAUDE.md)

- **SOLID principles required** -- not directly applicable to this vanilla JS file (no classes/modules being added), but SRP applies: keep download logic in distinct functions rather than inlining everything in `loadRecommendations()`.
- **Update .env.example when env vars change** -- no env var changes in this phase.
- **GSD workflow enforcement** -- this research is part of the GSD workflow.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio + FastAPI TestClient |
| Config file | `pyproject.toml` (pytest section) |
| Quick run command | `uv run pytest tests/api/test_dashboard.py -x` |
| Full suite command | `uv run pytest` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DASH-01 | Download button rendered in recommendations table | manual | Browser inspection after loading recommendations | N/A -- JS-rendered DOM, no server-side test possible |
| DASH-02 | "Downloaded" badge for models in catalog | manual | Browser inspection with model on NFS | N/A -- JS-rendered DOM |
| DASH-03 | Download status auto-updates without refresh | manual | Trigger download, observe 4s poll cycle | N/A -- requires running download service |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/api/test_dashboard.py -x` (verifies no template regressions)
- **Per wave merge:** `uv run pytest`
- **Phase gate:** Full suite green + manual browser verification of all three DASH requirements

### Wave 0 Gaps
None -- this phase modifies only client-side JS. Existing `test_dashboard.py` covers template structure. The three DASH requirements are inherently manual (JS-rendered DOM with live API interaction).

## Sources

### Primary (HIGH confidence)
- `inference_proxy/static/js/node_detail.js` -- existing JS patterns, `loadRecommendations()`, `showToast()`, `setInterval`
- `inference_proxy/static/css/dashboard.css` -- badge classes, button classes
- `inference_proxy/models/admin.py` -- Pydantic models for all API response shapes
- `inference_proxy/models/llmfit.py` -- `ModelRecommendation` and `SystemInfo` fields
- `inference_proxy/huggingface/catalog.py` -- `CatalogEntry` and `ModelCatalogResponse` shapes
- `inference_proxy/huggingface/downloader.py` -- `DownloadService` idempotency logic (D-10)
- `inference_proxy/api/admin.py` -- endpoint definitions and status codes
- `inference_proxy/templates/node_detail.html` -- HTML structure, `recs-content` container

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new libraries, all existing
- Architecture: HIGH -- all patterns verified from codebase
- Pitfalls: HIGH -- derived from verified code paths and API contracts

**Research date:** 2026-07-28
**Valid until:** indefinite (codebase-sourced, no external dependencies)
