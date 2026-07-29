# Phase 32: Dashboard Download Integration - Context

**Gathered:** 2026-07-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Operators can trigger and monitor model downloads directly from the recommendations table in the node detail page. Adds a Download column to the existing recommendations table with three-state buttons, client-side catalog cross-referencing for "already downloaded" badges, and polling-based status updates.

</domain>

<decisions>
## Implementation Decisions

### Catalog Cross-Reference
- **D-01:** Client-side merge — JS fetches both `/admin/nodes/{id}/recommendations` AND `/admin/models/catalog` in parallel, then cross-references `repo_id`s via a `Set`. No backend changes needed. Both endpoints already exist.
- **D-02:** llmfit model `name` IS the HF `repo_id` (D-09 from Phase 30) — zero mapping needed between recommendation names and catalog repo_ids.

### Download Status Updates
- **D-03:** Poll GET `/admin/models/downloads` on a 4-second timer after any download is triggered. Update button states in-place via DOM manipulation. Stop polling when no downloads have `status === 'downloading'`. Matches the existing `setInterval` pattern used for node data refresh.
- **D-04:** Polling starts only after the first download trigger — no polling overhead when no downloads are active.

### Button State Machine
- **D-05:** Three-state button in a single table cell:
  - **Not downloaded, no download in progress:** `[Download]` — clickable, `btn-setup` style
  - **Download in progress:** `[Downloading...]` — disabled, `badge-in-progress` style
  - **Downloaded (complete or already on NFS):** `[Downloaded]` — non-clickable, `badge-complete` badge
  - **Download failed:** `[Failed — Retry]` — clickable, `badge-failed` style
- **D-06:** Reuse existing CSS badge classes (`badge-complete`, `badge-in-progress`, `badge-failed`) — no new CSS needed beyond possibly a button variant.

### Table Layout
- **D-07:** Single new "Download" column appended at the end of the recommendations table. Columns become: Model, Category, Score, Fit, Est. tok/s, Memory, Download.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Context
- `.planning/PROJECT.md` — project overview, constraints, key decisions
- `.planning/REQUIREMENTS.md` — v1.7 requirements (DASH-01, DASH-02, DASH-03 map to this phase)
- `.planning/ROADMAP.md` — phase 32 success criteria and phase dependencies

### Phase 30 & 31 Decisions (carry forward)
- `.planning/phases/30-foundation-model-catalog/30-CONTEXT.md` — D-09 (repo_id = model name)
- `.planning/phases/31-download-service-api/31-CONTEXT.md` — D-10 (duplicate download idempotency), D-05 (three download states)

### Existing Patterns
- `inference_proxy/templates/node_detail.html` — Jinja2 template with recommendations panel
- `inference_proxy/static/js/node_detail.js` — vanilla JS fetch + DOM manipulation, loadRecommendations(), setInterval polling
- `inference_proxy/static/css/dashboard.css` — badge classes, table styles, btn-setup/btn-teardown styles
- `inference_proxy/api/admin.py` — POST /admin/models/download, GET /admin/models/downloads, GET /admin/models/catalog endpoints

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `loadRecommendations()` in node_detail.js: extend to also fetch catalog and download statuses
- Badge CSS classes: `badge-complete`, `badge-in-progress`, `badge-failed` — direct reuse for download state
- `btn-setup` CSS class for the Download button style
- `showToast()` for success/error feedback on download trigger
- `fetch` + `Promise.all` pattern already used in `refreshDetail()`

### Established Patterns
- Vanilla JS with DOM manipulation — no framework, no build step
- `setInterval` polling for live data (node status, tasks)
- Action buttons with disabled state during async operations (see `handleAction()`)
- Jinja2 server-side template rendering for HTML structure, JS for dynamic content

### Integration Points
- `inference_proxy/static/js/node_detail.js` — modify `loadRecommendations()` to fetch catalog + downloads, add Download column, add download polling
- `inference_proxy/templates/node_detail.html` — add Download column header to recommendations table (or let JS build the full table as it currently does)
- No backend changes needed — all required endpoints exist from phases 30-31

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 32-Dashboard Download Integration*
*Context gathered: 2026-07-28*
