# Phase 24: Provisioning Error Diagnostics - Context

**Gathered:** 2026-07-22
**Status:** Ready for planning

<domain>
## Phase Boundary

Make provisioning failures visible to operators directly in the fleet dashboard. Capture the exact provisioning step where failure occurred and display failure details inline, so operators can diagnose problems without checking logs.

</domain>

<decisions>
## Implementation Decisions

### Failed Node State
- **D-01:** Add `FAILED = "failed"` to `NodeStatus` enum — when provisioning fails, update the node's status in etcd to FAILED so the fleet badge reflects the actual state
- **D-02:** Available actions for failed nodes: `setup` (re-provision from scratch) and `teardown` (clean up failed registration) — reuses existing action types, no new action needed

### Error Capture
- **D-03:** Track the last active `ProvisioningStep` in `provision()` and store the actual step name as `failed_step` (e.g., "uploading_scripts", "nvidia_driver") instead of the exception class name ("RemoteCommandError")
- **D-04:** Store the full exception/stderr message as `error` — no truncation at capture time

### Dashboard Error Display
- **D-05:** Failed nodes show a "failed" badge in the State column (new `badge-failed` CSS class)
- **D-06:** Clicking the failed badge expands a sub-row below the node row showing the failed step name and full error message
- **D-07:** Sub-row starts collapsed — operator clicks to expand (keeps fleet view clean when multiple nodes are failed)
- **D-08:** Show step name + full error text in the sub-row with no truncation — operators get all detail in one place

### Claude's Discretion
- How to track "last active step" in `provision()` (local variable, context manager, or other pattern)
- Sub-row HTML/CSS structure and expand/collapse JS implementation
- Whether `AdminNodeResponse` gets `failed_step` and `error` fields, or a nested error object
- How the unified node service merges provisioning task error data into the node response
- `badge-failed` CSS styling (color, border, etc.) — follow existing badge patterns
- Test structure for the new capture and display behavior

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Provisioning (primary modification target)
- `inference_proxy/provisioning/provisioner.py` — NodeProvisioner with `provision()` method; fix `failed_step` capture in the except block (currently uses `type(exc).__name__`)
- `inference_proxy/provisioning/state.py` — ProvisioningState model with `failed_step` and `error` fields; ProvisioningStep enum

### Node Model
- `inference_proxy/models/node.py` — NodeStatus enum; add FAILED member
- `inference_proxy/models/admin.py` — AdminNodeResponse (add error fields), TaskStatusResponse (already has error fields)

### Unified Node Service
- `inference_proxy/services/unified_nodes.py` — UnifiedNodeService and `_STATE_ACTIONS` dict; add "failed" state with setup/teardown actions; merge error data into AdminNodeResponse

### Dashboard (UI modification target)
- `inference_proxy/static/js/dashboard.js` — Fleet view rendering; add expandable sub-row for failed nodes
- `inference_proxy/static/css/dashboard.css` — Badge styles; add `badge-failed` class
- `inference_proxy/templates/dashboard.html` — Main fleet template

### Existing Error Display (pattern reference)
- `inference_proxy/static/js/node_detail.js` — Already renders `failed_step` and `error` from provisioning tasks; reference for sub-row rendering approach
- `inference_proxy/templates/node_detail.html` — Provisioning Tasks table with Error column

### Admin API
- `inference_proxy/api/admin.py` — `list_provisioning_tasks` endpoint already returns TaskStatusResponse with error fields; `list_nodes` returns AdminNodeResponse which needs error fields added

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `ProvisioningState.failed_step` and `.error` — already captured and stored in etcd; need to fix step name accuracy
- `TaskStatusResponse` — already exposes `failed_step` and `error` from the `/admin/provisioning/tasks` endpoint
- `node_detail.js` error rendering — existing pattern for displaying `failed_step` badge and `error` text in a table
- `_STATE_ACTIONS` dispatch dict — add `"failed": ["setup", "teardown"]` entry
- `badge-*` CSS classes — existing pattern for state-based badge styling (badge-healthy, badge-unhealthy, badge-in-progress, badge-complete)

### Established Patterns
- Data-driven `ACTION_CONFIG` in dashboard.js — single dispatch map for all node actions
- `_STATE_ACTIONS` in unified_nodes.py — state-to-actions mapping
- Frozen Pydantic models for API responses
- `_update_state()` best-effort writes to etcd for dashboard visibility

### Integration Points
- `NodeStatus` enum — add FAILED member
- `_STATE_ACTIONS` dict — add "failed" entry
- `provision()` except block — fix failed_step to use actual step name
- `AdminNodeResponse` — add optional `failed_step` and `error` fields
- `UnifiedNodeService._from_node()` — populate error fields from provisioning task data
- `dashboard.js` node rendering loop — add expandable sub-row for failed nodes

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches following the dashboard's existing patterns.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 24-provisioning-error-diagnostics*
*Context gathered: 2026-07-22*
