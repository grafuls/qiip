# Phase 24: Provisioning Error Diagnostics - Research

**Researched:** 2026-07-22
**Domain:** Provisioning error capture and dashboard display
**Confidence:** HIGH

## Summary

This phase makes provisioning failures visible to operators directly in the fleet dashboard. It touches four layers: the provisioning orchestrator (fix `failed_step` capture), the node model (add `FAILED` enum member), the unified node service (merge error data and map failed-state actions), and the dashboard UI (expandable error sub-row).

The codebase already has nearly all the infrastructure needed. `ProvisioningState` already carries `failed_step` and `error` fields, `TaskStatusResponse` already exposes them via the API, and `node_detail.js` already renders failed-step badges and error text. The main work is: (1) fixing the provisioner to capture the actual step name instead of the exception class name, (2) adding `FAILED` to `NodeStatus` and wiring it through the unified node service, (3) surfacing error fields on `AdminNodeResponse`, and (4) adding the expandable sub-row in `dashboard.js`.

**Primary recommendation:** Track the last active `ProvisioningStep` in a local variable inside `provision()`, use it as `failed_step` in the except block. Add `FAILED` to `NodeStatus`, add error fields to `AdminNodeResponse`, add `"failed"` entry to `_STATE_ACTIONS`, and render a click-to-expand error sub-row in the fleet table.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Add `FAILED = "failed"` to `NodeStatus` enum
- **D-02:** Available actions for failed nodes: `setup` (re-provision) and `teardown` (clean up)
- **D-03:** Track last active `ProvisioningStep` in `provision()` and store actual step name as `failed_step`
- **D-04:** Store full exception/stderr message as `error` with no truncation
- **D-05:** Failed nodes show a "failed" badge in the State column (new `badge-failed` CSS class)
- **D-06:** Clicking the failed badge expands a sub-row showing failed step name and error message
- **D-07:** Sub-row starts collapsed; operator clicks to expand
- **D-08:** Show step name + full error text in sub-row with no truncation

### Claude's Discretion
- How to track "last active step" in `provision()` (local variable, context manager, or other pattern)
- Sub-row HTML/CSS structure and expand/collapse JS implementation
- Whether `AdminNodeResponse` gets `failed_step` and `error` fields, or a nested error object
- How the unified node service merges provisioning task error data into the node response
- `badge-failed` CSS styling (color, border, etc.) -- follow existing badge patterns
- Test structure for the new capture and display behavior

### Deferred Ideas (OUT OF SCOPE)
None
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DIAG-01 | Failed provisioning step name and error details are captured and stored | Fix `failed_step` in provisioner except block (line 280): use tracked step variable instead of `type(exc).__name__`. `ProvisioningState` already has `failed_step` and `error` fields. |
| DIAG-02 | Dashboard displays failure details inline for failed nodes instead of just a state badge | Add `FAILED` to `NodeStatus`, surface error fields on `AdminNodeResponse`, render expandable sub-row in `dashboard.js` when `node.failed_step` exists. |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Error capture (step name + message) | API / Backend | -- | Provisioner is the only place that knows which step failed; capture happens in the except block |
| Failed node state management | API / Backend | -- | `NodeStatus` enum and `_STATE_ACTIONS` are server-side constructs |
| Error data in API response | API / Backend | -- | `AdminNodeResponse` serves `/admin/nodes`; unified node service merges data |
| Error display (expandable sub-row) | Browser / Client | -- | Vanilla JS DOM manipulation in `dashboard.js`; no server rendering needed |
| Error sub-row styling | Browser / Client | -- | CSS classes in `dashboard.css` |

## Standard Stack

No new dependencies. This phase uses only existing stack components. [VERIFIED: codebase inspection]

### Core (already installed)
| Library | Purpose | Relevance |
|---------|---------|-----------|
| FastAPI | HTTP framework | Serves `/admin/nodes` endpoint returning `AdminNodeResponse` |
| Pydantic | Data models | `AdminNodeResponse`, `NodeStatus`, `ProvisioningState` are all Pydantic models |
| etcd3gw | State storage | Provisioning state written to `/provisioning/{hostname}` key |
| structlog | Logging | Error logging in provisioner |

### Development (already installed)
| Library | Purpose | Relevance |
|---------|---------|-----------|
| pytest | Testing | Unit tests for provisioner, unified node service, admin API |
| pytest-asyncio | Async tests | Provisioner tests are async |

## Package Legitimacy Audit

No new packages required. All work uses existing dependencies. No audit needed.

## Architecture Patterns

### System Architecture Diagram

```
                   +-------------------+
                   |  provision()      |
                   |  except block     |
                   |  (fix failed_step)|
                   +--------+----------+
                            |
                   _update_state(FAILED, failed_step=step_var, error=str(exc))
                            |
                            v
                   +-------------------+
                   |  etcd             |
                   |  /provisioning/   |
                   |  {hostname}       |
                   +--------+----------+
                            |
              +-------------+-------------+
              |                           |
              v                           v
    +-------------------+       +-------------------+
    | /admin/nodes      |       | /admin/            |
    | (list_nodes)      |       | provisioning/tasks |
    | UnifiedNodeService|       | (list_tasks)       |
    | merges error data |       | (existing, works)  |
    +--------+----------+       +-------------------+
             |
             v
    +-------------------+
    | dashboard.js      |
    | refreshDashboard()|
    | renders sub-row   |
    | if node.failed_   |
    | step exists       |
    +-------------------+
```

### Pattern 1: Local Variable Step Tracking (recommended for D-03)

**What:** Track the last active step in a local variable inside `provision()`, update it before each await, use it in the except block.

**When to use:** When you need to know "which step was active when the exception fired" and the step progression is linear.

**Why this over alternatives:**
- Context manager adds ceremony for a simple linear flow [ASSUMED]
- Local variable is the simplest thing that works -- one line per step, one read in the except block

**Example:**
```python
# Source: codebase pattern analysis
async def provision(self, hostname: str, *, managed: bool = True) -> None:
    ...
    try:
        current_step = "uploading_scripts"
        await self._update_state(hostname, ProvisioningStep.UPLOADING_SCRIPTS)
        await self._upload_scripts(hostname)

        current_step = "setup"  # or track from step markers
        await self._run_setup(hostname)

        current_step = "starting_vllm"
        await self._update_state(hostname, ProvisioningStep.STARTING_VLLM)
        model = await self._run_start_vllm(hostname)

        current_step = "health_poll"
        await self._update_state(hostname, ProvisioningStep.HEALTH_POLL)
        await self._poll_health(hostname)

        current_step = "registering"
        await self._update_state(hostname, ProvisioningStep.REGISTERING)
        await self._register_node(hostname, model, managed=managed)

        await self._update_state(hostname, ProvisioningStep.COMPLETE)
    except (RemoteCommandError, SSHConnectionError, ProvisioningError) as exc:
        await self._update_state(
            hostname, ProvisioningStep.FAILED,
            failed_step=current_step, error=str(exc),
        )
        raise ProvisioningError(str(exc)) from exc
```

### Pattern 2: AdminNodeResponse Error Fields (flat fields, not nested object)

**What:** Add optional `failed_step: str | None` and `error: str | None` to `AdminNodeResponse`.

**Why flat over nested:** Follows the existing pattern -- `TaskStatusResponse` already uses flat `failed_step` and `error` fields. The dashboard JS already reads `task.failed_step` and `task.error` in `node_detail.js`. Keeping the same shape minimizes JS changes. [VERIFIED: codebase inspection]

**Example:**
```python
# Source: inference_proxy/models/admin.py existing pattern
class AdminNodeResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    # ... existing fields ...
    failed_step: str | None = None
    error: str | None = None
```

### Pattern 3: Unified Node Service Error Merge

**What:** `_from_etcd()` needs to populate `failed_step` and `error` on `AdminNodeResponse` for failed nodes. The data lives in the provisioning task etcd entry (`/provisioning/{hostname}`), not in the node entry (`/nodes/{hostname}`).

**Two approaches:**

1. **Read provisioning task data in UnifiedNodeService** -- requires passing the provisioner or a task lookup function to the service. Adds a dependency.

2. **Set NodeStatus to FAILED in the provisioner when writing the node key** -- then the node entry in etcd carries the failed status, and `_from_etcd()` can read `node.status == FAILED`. But the error details still live in `/provisioning/`. So we'd need to also write error fields to the node entry, or pass task data alongside.

**Recommended approach:** The provisioner already writes the node as `PROVISIONING` to `/nodes/{hostname}` before setup begins (line 252-262). On failure, it should update that node entry to `FAILED` status. For error details, the simplest path is to have `UnifiedNodeService` accept an optional task map (hostname -> task data) and merge it. The admin API's `list_nodes` endpoint can fetch provisioning tasks alongside nodes and pass the map. [ASSUMED]

**Alternative (simpler):** Don't merge at the service layer. Instead, have the provisioner write `failed_step` and `error` directly into the node's etcd entry (extend the `Node` model with optional error fields), so `_from_etcd()` gets them for free. This avoids the task-lookup dependency entirely but means the `Node` model carries error-related fields. [ASSUMED]

**Simplest option:** The provisioner already updates `/provisioning/{hostname}` with error data AND writes `/nodes/{hostname}` with `PROVISIONING` status. On failure, update `/nodes/{hostname}` to `FAILED`. Then have `UnifiedNodeService` receive a provisioning task map to enrich `AdminNodeResponse` with `failed_step`/`error`. The admin endpoint already calls `list_tasks_raw()` in a separate endpoint -- merging the two calls in `list_nodes` is straightforward.

### Anti-Patterns to Avoid
- **Storing error details in the Node model:** The `Node` model is the domain model for routing decisions. Adding error fields to it conflates operational diagnostics with routing state. Keep error data in `ProvisioningState` where it already lives. [ASSUMED]
- **Truncating error messages:** D-08 explicitly requires no truncation. Don't add `max_length` validators or CSS text overflow on the error display.
- **Using exception class name as step name:** This is the current bug (line 280: `failed_step=type(exc).__name__`). The exception class name tells you nothing about which provisioning step failed.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Expandable row | Custom accordion component | `<tr>` with `display: none/table-row` toggle | HTML tables support adjacent rows; toggling display is 3 lines of JS. Already proven in node_detail.js. |
| Failed badge styling | New CSS classes from scratch | Extend existing `badge-failed` class | `badge-failed` already exists in `dashboard.css` line 318-320 with correct danger colors. Just add `cursor: pointer` for clickable variant. |
| Error data transport | New API endpoint | Existing `/admin/nodes` response with added fields | One endpoint, one fetch, all data in one place. |

## Common Pitfalls

### Pitfall 1: Node Not Updated to FAILED in etcd
**What goes wrong:** The provisioner writes `/provisioning/{hostname}` with `FAILED` status but never updates `/nodes/{hostname}`. The unified node service reads from the node registry (which reads `/nodes/`), so the node stays as `PROVISIONING` in the fleet view.
**Why it happens:** The current code writes the PROVISIONING node entry but doesn't update it on failure.
**How to avoid:** In the provisioner's except block, also update the node entry in etcd to `FAILED` status (or deregister it). Then the watcher/registry picks it up.
**Warning signs:** Node shows "provisioning" badge forever after a failure.

### Pitfall 2: `_STATE_ACTIONS` Missing "failed" Entry
**What goes wrong:** Failed nodes render with no action buttons in the dashboard.
**Why it happens:** `_STATE_ACTIONS` dict in `unified_nodes.py` doesn't have a `"failed"` key.
**How to avoid:** Add `"failed": ["setup", "teardown"]` to the dict (D-02).
**Warning signs:** Failed node row has empty Actions column.

### Pitfall 3: Sub-row colspan Mismatch
**What goes wrong:** Error sub-row doesn't span the full table width.
**Why it happens:** The fleet table has 7 columns. If `colspan` is wrong, the sub-row layout breaks.
**How to avoid:** Use `colspan="7"` matching the existing table header count (verified: `dashboard.html` line 54-62).
**Warning signs:** Error detail box is narrow or misaligned.

### Pitfall 4: Stale `pending_hosts` After Failure
**What goes wrong:** After a provisioning failure, the hostname stays in `pending_hosts`, blocking re-provisioning via the "setup" action.
**Why it happens:** The `_provision_and_cleanup()` wrapper in `admin.py` line 131-135 already discards from `pending_hosts` in a `finally` block. This is NOT a problem -- just noting it's already handled.
**How to avoid:** No action needed; already correct.

### Pitfall 5: Error Sub-row Persists After Re-provision
**What goes wrong:** Operator clicks "Setup" on a failed node, but the error sub-row from the previous failure stays visible until the next dashboard refresh.
**Why it happens:** `refreshDashboard()` rebuilds the entire tbody, so this is naturally handled on the next poll cycle.
**How to avoid:** No action needed; the auto-refresh (every `POLL_INTERVAL_MS`) clears stale sub-rows.

## Code Examples

### Existing: How `node_detail.js` renders error data (reference pattern)
```javascript
// Source: inference_proxy/static/js/node_detail.js lines 164-176
if (task.failed_step) {
  var fb = document.createElement("span");
  fb.className = "badge badge-failed";
  fb.textContent = "failed at " + task.failed_step;
  tdStatus.appendChild(fb);
}
var tdErr = document.createElement("td");
if (task.error) {
  tdErr.className = "error-text";
  tdErr.textContent = task.error;
} else {
  tdErr.textContent = "—";
}
```

### Existing: Badge CSS classes (already includes badge-failed)
```css
/* Source: inference_proxy/static/css/dashboard.css lines 318-320 */
.badge-unhealthy,
.badge-open,
.badge-failed {
  background: var(--danger-bg);
  color: var(--danger);
}
```

### Existing: `_STATE_ACTIONS` dispatch (add "failed" entry here)
```python
# Source: inference_proxy/services/unified_nodes.py lines 21-27
_STATE_ACTIONS: dict[str, list[str]] = {
    "available": ["setup"],
    "healthy": ["teardown"],
    "unhealthy": ["teardown", "retry"],
    "provisioning": ["cancel"],
    "draining": ["force_teardown"],
    # Add: "failed": ["setup", "teardown"],
}
```

### New: Expandable sub-row in dashboard.js (UI spec contract)
```javascript
// Source: 24-UI-SPEC.md component inventory
// After appending the main node row:
if (node.state === "failed" && (node.failed_step || node.error)) {
  // Make badge clickable
  stateBadge.style.cursor = "pointer";
  stateBadge.setAttribute("role", "button");
  stateBadge.setAttribute("tabindex", "0");
  stateBadge.setAttribute("aria-expanded", "false");

  var subRow = document.createElement("tr");
  subRow.className = "error-subrow";
  subRow.style.display = "none";

  var subTd = document.createElement("td");
  subTd.colSpan = 7;

  var detail = document.createElement("div");
  detail.className = "error-detail";

  if (node.failed_step) {
    var stepBadge = document.createElement("span");
    stepBadge.className = "badge badge-failed";
    stepBadge.textContent = "failed at " + node.failed_step;
    detail.appendChild(stepBadge);
  }

  if (node.error) {
    var pre = document.createElement("pre");
    pre.className = "error-message";
    pre.textContent = node.error;
    detail.appendChild(pre);
  }

  subTd.appendChild(detail);
  subRow.appendChild(subTd);

  function toggleSubRow() {
    var visible = subRow.style.display !== "none";
    subRow.style.display = visible ? "none" : "table-row";
    stateBadge.setAttribute("aria-expanded", String(!visible));
  }
  stateBadge.addEventListener("click", toggleSubRow);
  stateBadge.addEventListener("keydown", function(e) {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggleSubRow(); }
  });

  tbody.appendChild(subRow);
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `type(exc).__name__` as failed_step | Track actual ProvisioningStep name in local variable | This phase | Operators see "uploading_scripts" instead of "RemoteCommandError" |
| Error details only in `/admin/provisioning/tasks` endpoint | Error details inline on fleet dashboard | This phase | No need to navigate to node detail page to see what failed |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Local variable is the simplest step-tracking pattern (vs context manager) | Architecture Patterns - Pattern 1 | Low -- context manager works too, just more code |
| A2 | Flat fields on AdminNodeResponse preferred over nested error object | Architecture Patterns - Pattern 2 | Low -- nested object works but changes JS access pattern |
| A3 | UnifiedNodeService should receive a task map to merge error data | Architecture Patterns - Pattern 3 | Medium -- alternative is extending Node model with error fields |
| A4 | Adding error fields to Node model conflates routing and diagnostics | Anti-Patterns | Medium -- it would work but violates SRP |

## Open Questions

1. **How does UnifiedNodeService get provisioning error data?**
   - What we know: Error data lives in `/provisioning/{hostname}` (ProvisioningState). Node data lives in `/nodes/{hostname}` (Node). The unified service currently only reads from the node registry.
   - What's unclear: Should the admin `list_nodes` endpoint fetch both and pass a task map? Or should the provisioner update the node entry with error fields?
   - Recommendation: Have `list_nodes` fetch provisioning tasks and pass a `dict[str, TaskStatusResponse]` to `UnifiedNodeService.get_unified_nodes()`. This keeps the Node model clean and the provisioner unchanged (beyond the step-tracking fix). The overhead is one extra etcd prefix read per dashboard poll -- negligible.

2. **Should the provisioner update `/nodes/{hostname}` to FAILED status on failure?**
   - What we know: Currently the node stays as `PROVISIONING` in etcd after a failure. The provisioning state (`/provisioning/`) is set to FAILED, but the node entry (`/nodes/`) is not updated.
   - What's unclear: Whether to update the node entry or have the unified service infer "failed" from the provisioning task state.
   - Recommendation: Update the node entry to `FAILED` in the provisioner's except block. This makes the state visible to the registry watcher and the unified service without special merging logic. The watcher will pick up the `FAILED` status and the `_from_etcd()` method will map it naturally.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 1.4 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/ -x -q` |
| Full suite command | `uv run pytest tests/ -v` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DIAG-01a | `provision()` captures actual step name (not exception class) in `failed_step` | unit | `uv run pytest tests/provisioning/test_provisioner.py -x -k failed_step` | Partial (test_failed_state exists but doesn't verify step name accuracy) |
| DIAG-01b | `teardown()` captures "teardown" as `failed_step` | unit | `uv run pytest tests/provisioning/test_provisioner.py -x -k teardown_failure` | Yes (test_ssh_failure_sets_failed_state) |
| DIAG-02a | `NodeStatus.FAILED` enum member exists | unit | `uv run pytest tests/models/test_node.py -x` | Wave 0 |
| DIAG-02b | `AdminNodeResponse` includes `failed_step` and `error` fields | unit | `uv run pytest tests/models/test_admin.py -x` | Wave 0 |
| DIAG-02c | `_STATE_ACTIONS["failed"]` returns `["setup", "teardown"]` | unit | `uv run pytest tests/services/test_unified_nodes.py -x -k failed` | Wave 0 |
| DIAG-02d | UnifiedNodeService returns error fields for failed nodes | unit | `uv run pytest tests/services/test_unified_nodes.py -x -k failed` | Wave 0 |
| DIAG-02e | Dashboard JS renders sub-row for failed nodes | manual-only | Visual inspection | N/A |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/ -x -q`
- **Per wave merge:** `uv run pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/provisioning/test_provisioner.py` -- add test verifying `failed_step` contains actual step name (e.g., "uploading_scripts") not exception class name
- [ ] `tests/models/test_node.py` -- add test for `NodeStatus.FAILED` member
- [ ] `tests/models/test_admin.py` -- add test for `AdminNodeResponse` with `failed_step` and `error`
- [ ] `tests/services/test_unified_nodes.py` -- add tests for failed node state, actions, and error field population

## Security Domain

No new security concerns for this phase. All changes are to internal admin endpoints on an internal-only network. No new input parsing (error strings are captured from internal exceptions, not user input). No new authentication or authorization changes.

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | unchanged |
| V3 Session Management | no | unchanged |
| V4 Access Control | no | unchanged |
| V5 Input Validation | no | error strings are from internal exceptions, not external input |
| V6 Cryptography | no | unchanged |

## Sources

### Primary (HIGH confidence)
- Codebase inspection: `provisioner.py` lines 277-282 (current bug: `type(exc).__name__`)
- Codebase inspection: `state.py` (ProvisioningState already has failed_step/error)
- Codebase inspection: `node.py` (NodeStatus enum, missing FAILED)
- Codebase inspection: `admin.py` (AdminNodeResponse, TaskStatusResponse)
- Codebase inspection: `unified_nodes.py` (_STATE_ACTIONS dict)
- Codebase inspection: `dashboard.js` (fleet table rendering loop)
- Codebase inspection: `dashboard.css` (badge-failed class already exists)
- Codebase inspection: `node_detail.js` (error rendering pattern)
- Phase artifact: `24-CONTEXT.md` (locked decisions D-01 through D-08)
- Phase artifact: `24-UI-SPEC.md` (sub-row HTML/CSS/JS contract)

### Secondary (MEDIUM confidence)
- None needed -- all findings from direct codebase inspection

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, all existing
- Architecture: HIGH -- all modification points identified and verified in codebase
- Pitfalls: HIGH -- verified against existing code flow
- UI patterns: HIGH -- existing badge-failed CSS and node_detail.js error rendering confirmed

**Research date:** 2026-07-22
**Valid until:** 2026-08-22 (stable -- internal codebase, no external API changes)
