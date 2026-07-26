# Phase 29: Dashboard Recommendations - Context

**Gathered:** 2026-07-26
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase adds a recommendations card to the existing node detail page (`node_detail.html`). The card displays a hardware summary (GPU name, VRAM, backend) and a ranked model table fetched from the existing `GET /admin/nodes/{hostname}/recommendations` endpoint (Phase 27). No new API endpoints, no new Python code — purely frontend (Jinja2 template + vanilla JS).

</domain>

<decisions>
## Implementation Decisions

### Table Columns
- **D-01:** Show exactly 5 columns matching DASH-01 spec: model name, score, fit level, estimated tok/s, memory required.
- **D-02:** Score displayed as percentage (multiply by 100, e.g. "85%"), not raw float.
- **D-03:** Fit level rendered as colored badge reusing existing badge pattern: `badge-complete` for "perfect", `badge-in-progress` for "good", `badge-failed` for "marginal".
- **D-04:** Memory column shows value with 1 decimal and "GB" suffix (e.g. "14.2 GB").

### Claude's Discretion
- **Loading trigger:** Claude decides whether to load recommendations automatically on page load or behind a button. Consider that each load triggers an SSH+llmfit call on the remote host.
- **Error display:** Claude decides how to show llmfit failures (timeout, SSH error, parse error). The API returns `error_type` field (Phase 27 D-02) — use it for differentiated messaging.
- **Card placement:** Claude decides where the recommendations card sits on the node detail page relative to existing sections (Node Info, Provisioning Tasks, Live Logs).
- **Empty state:** Claude decides what to show when no recommendations are available (node not SSH-reachable, llmfit not installed, etc.).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Node Detail Page (existing)
- `inference_proxy/templates/node_detail.html` — Current node detail template with card sections for Node Info, Provisioning Tasks, Live Logs. New recommendations card goes here.
- `inference_proxy/static/js/node_detail.js` — Existing JS with `refreshDetail()` polling loop, `ACTION_CONFIG` dispatch, toast notifications, SSE log viewer. Recommendations fetch/render logic goes here.
- `inference_proxy/static/css/dashboard.css` — Shared CSS with card, badge, table-wrap, toast styles. Reuse existing classes.

### Recommendations API (Phase 27)
- `inference_proxy/api/admin.py` line 279 — `GET /admin/nodes/{hostname}/recommendations` endpoint. Returns `LLMFitResult` on success, structured error with `error_type` on failure (HTTP 502).
- `inference_proxy/models/llmfit.py` — `LLMFitResult` (system + models), `SystemInfo` (gpu_name, gpu_vram_gb, backend), `ModelRecommendation` (name, score, fit_level, estimated_tps, memory_required_gb + 8 more fields).

### Requirements
- `.planning/REQUIREMENTS.md` — DASH-01 (ranked model table), DASH-02 (hardware summary).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- Card section pattern (`<section class="card">`) — used for Node Info, Provisioning Tasks, Live Logs. Recommendations card follows same structure.
- Badge classes (`badge-complete`, `badge-in-progress`, `badge-failed`) — map directly to fit levels.
- `showToast()` function in `node_detail.js` — reuse for error notifications.
- `table-wrap` class — responsive table container used in all existing tables.
- `NODE_ID` global variable — already set in template, use for API calls.

### Established Patterns
- Vanilla fetch + DOM manipulation (no framework) — `node_detail.js` line 1 comment confirms this is deliberate.
- `ACTION_CONFIG` data-driven dispatch — not directly relevant but shows the coding style.
- Polling via `setInterval(refreshDetail, POLL_INTERVAL_MS)` — recommendations should NOT auto-refresh (each call triggers remote SSH).

### Integration Points
- `inference_proxy/templates/node_detail.html` — Add new `<section class="card">` block
- `inference_proxy/static/js/node_detail.js` — Add fetch + render function for recommendations

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches. Follow existing node detail page patterns.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 29-Dashboard Recommendations*
*Context gathered: 2026-07-26*
