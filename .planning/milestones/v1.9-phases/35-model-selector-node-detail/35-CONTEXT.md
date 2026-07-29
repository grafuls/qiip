# Phase 35: Model Selector on Node Detail Page - Context

**Gathered:** 2026-07-29
**Status:** Ready for planning

<domain>
## Phase Boundary

Add a model selector card to the node detail page. A "Setup Configuration" card shows a dropdown populated from the model catalog (downloaded models on NFS). When the operator clicks Setup in the existing Actions dropdown, it reads the selected model from this card and sends it in SetupRequest.model. Setup is disabled when no models are downloaded.

</domain>

<decisions>
## Implementation Decisions

### Model Selector Placement
- **D-01:** New "Setup Configuration" card section between Node Info and Model Recommendations cards. Contains a model dropdown and a "No models downloaded" message when catalog is empty.

### Setup Flow Integration
- **D-02:** The card is a model selector only — no separate Setup button. When the user clicks Setup in the existing Actions dropdown, it reads the selected model from the card's dropdown and includes it in the POST /admin/nodes/setup request body as `model`.
- **D-03:** The existing Actions dropdown setup action and retry action are modified to read the selected model from the card. The dropdown itself stays unchanged visually.

### Catalog Fetch Timing
- **D-04:** Fetch GET /admin/models/catalog on page load (in DOMContentLoaded), regardless of node state. The dropdown is populated once on load.

### Empty State (MDL-03)
- **D-05:** When catalog is empty (no models downloaded), the model selector card shows a "No models downloaded" message. The Setup action in the Actions dropdown is disabled (removed from the enabled actions list).
- **D-06:** When catalog has models, the first model in the list is pre-selected in the dropdown. Setup action works normally.

### Dropdown Styling
- **D-07:** Use a native `<select>` element — no custom dropdown. Matches the project's vanilla JS approach. Style with existing CSS custom properties for theme compatibility.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Model Catalog API (already built in v1.7)
- `inference_proxy/api/admin.py` lines 117-123 — GET /admin/models/catalog endpoint
- `inference_proxy/huggingface/catalog.py` — CatalogEntry (repo_id), ModelCatalogResponse, ModelCatalogService

### Node Detail Page (modify target)
- `inference_proxy/templates/node_detail.html` — Jinja2 template with card sections
- `inference_proxy/static/js/node_detail.js` — ACTION_CONFIG, handleAction(), createActionsDropdown(), refreshDetail()

### Setup API (already built)
- `inference_proxy/models/admin.py` lines 60-78 — SetupRequest with optional model field
- `inference_proxy/api/admin.py` lines 147-189 — POST /admin/nodes/setup endpoint

### Styling
- `inference_proxy/static/css/dashboard.css` — .card, .card-title, btn-* classes, CSS custom properties

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `ACTION_CONFIG.setup.body` — currently returns `{ hostname: id, managed: node.managed !== false }`, needs to add `model` field
- `ACTION_CONFIG.retry.body` — same pattern, also needs model field
- `handleAction(action, nodeId)` — dispatches setup/teardown/retry/cancel via ACTION_CONFIG
- `createActionsDropdown(nodeId, enabledActions)` — renders Actions dropdown from enabled action list
- `refreshDetail()` — fetches node state, creates dropdown with `node.actions` list
- `showToast(message, type)` — success/error notifications
- `NODE_ID` global — hostname from Jinja2 template variable

### Established Patterns
- Vanilla JS DOM manipulation (createElement, appendChild)
- `fetch()` with try/catch for API calls
- Native `<select>` not yet used but consistent with vanilla approach
- Card sections with `.card` class and `.card-title` header

### Integration Points
- Template: new card section after Node Info card (line 64), before recommendations-panel
- JS: fetch catalog in DOMContentLoaded, populate `<select>`, modify ACTION_CONFIG.setup.body and retry.body to include selected model
- JS: disable setup action when catalog is empty — filter "setup" from enabledActions in refreshDetail when no models

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches matching existing page patterns.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 35-Model Selector on Node Detail Page*
*Context gathered: 2026-07-29*
