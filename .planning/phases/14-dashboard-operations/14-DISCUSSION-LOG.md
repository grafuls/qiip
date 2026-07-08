# Phase 14: Dashboard Operations - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-08
**Phase:** 14-Dashboard Operations
**Areas discussed:** Setup form placement, Progress display, Teardown button UX

---

## Setup Form Placement

| Option | Description | Selected |
|--------|-------------|----------|
| Inline above table | Simple hostname input + Setup button above the node fleet table. Always visible. | ✓ |
| Collapsible section | Hidden by default behind a toggle button. | |
| You decide | Let Claude pick. | |

**User's choice:** Inline above table
**Notes:** None

### Form Fields

| Option | Description | Selected |
|--------|-------------|----------|
| Hostname only | Single text input. GPU auto-detection happens on remote host. | ✓ |
| Hostname + model override | Optional model dropdown. Would need backend changes. | |
| You decide | Let Claude pick. | |

**User's choice:** Hostname only
**Notes:** None

### Form Submit Behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Disable briefly + flash confirmation | Disable button ~2s, show confirmation, re-enable. | ✓ |
| Stay enabled, show toast/banner | Form stays ready immediately with notification. | |
| You decide | Let Claude pick. | |

**User's choice:** Disable briefly + flash confirmation
**Notes:** None

### Validation

| Option | Description | Selected |
|--------|-------------|----------|
| Basic non-empty check only | Prevent empty submission. Backend handles reachability. | ✓ |
| Hostname regex validation | Check for valid hostname pattern before POST. | |
| You decide | Let Claude pick. | |

**User's choice:** Basic non-empty check only
**Notes:** None

---

## Progress Display

| Option | Description | Selected |
|--------|-------------|----------|
| Separate tasks panel below table | Lists active/recent tasks with hostname, step, elapsed time. | ✓ |
| Inline status column in node table | Add provisioning column to existing table. | |
| Expandable row detail | Click node row to expand provisioning steps. | |
| You decide | Let Claude pick. | |

**User's choice:** Separate tasks panel below table
**Notes:** None

### Step Detail

| Option | Description | Selected |
|--------|-------------|----------|
| Current step + status badge | Hostname, step name, status badge, timestamp per task row. | ✓ |
| Step progress bar | Horizontal progress indicator with all steps. | |
| You decide | Let Claude pick. | |

**User's choice:** Current step + status badge
**Notes:** None

### Task History

| Option | Description | Selected |
|--------|-------------|----------|
| Always visible | All tasks from etcd shown until overwritten by next operation. | ✓ |
| Hide after 5 minutes | Client-side filter hides old tasks. | |
| You decide | Let Claude decide. | |

**User's choice:** Always visible
**Notes:** None

### Poll Interval

| Option | Description | Selected |
|--------|-------------|----------|
| Same poll cycle | Add /admin/provisioning/tasks to existing Promise.all. | ✓ |
| Faster poll during active tasks | 2x frequency when task in-progress. | |
| You decide | Let Claude pick. | |

**User's choice:** Same poll cycle
**Notes:** None

---

## Teardown Button UX

| Option | Description | Selected |
|--------|-------------|----------|
| New Actions column in table | Each row gets a Teardown button. | ✓ |
| Clickable node row | Click row to reveal teardown action. | |
| You decide | Let Claude pick. | |

**User's choice:** New Actions column in table
**Notes:** None

### Confirmation

| Option | Description | Selected |
|--------|-------------|----------|
| Browser confirm() dialog | window.confirm() with teardown message. | ✓ |
| No confirmation | Fires immediately. | |
| Custom inline confirm | Button changes to Confirm/Cancel pair. | |
| You decide | Let Claude pick. | |

**User's choice:** Browser confirm() dialog
**Notes:** None

### Force Teardown

| Option | Description | Selected |
|--------|-------------|----------|
| Not in UI — API-only | Dashboard always does graceful teardown. | ✓ |
| Checkbox next to teardown button | Operator opts in to force. | |
| You decide | Let Claude decide. | |

**User's choice:** Not in UI — API-only
**Notes:** None

### Button State

| Option | Description | Selected |
|--------|-------------|----------|
| Disable during operations | Disabled when PROVISIONING or DRAINING. | ✓ |
| Always enabled, let backend reject | Backend returns 409 Conflict. | |
| You decide | Let Claude pick. | |

**User's choice:** Disable during operations
**Notes:** None

---

## Claude's Discretion

- CSS styling for setup form, tasks panel, and action buttons
- Status badge colors for provisioning steps
- Tasks panel empty state text
- Error display for non-2xx API responses

## Deferred Ideas

None — discussion stayed within phase scope.
