# Phase 24: Provisioning Error Diagnostics - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-22
**Phase:** 24-provisioning-error-diagnostics
**Areas discussed:** Failed node visibility, Error display format, Error detail level

---

## Failed Node Visibility

### How should failed provisioning be represented in the node fleet?

| Option | Description | Selected |
|--------|-------------|----------|
| Add FAILED to NodeStatus | New enum member. When provisioning fails, update the node's status in etcd to FAILED. Fleet badge shows 'failed' with distinct styling. Adds actions for failed nodes. | ✓ |
| Derive from provisioning task | Keep NodeStatus as-is. Cross-reference provisioning tasks to detect failure and override the displayed state. No schema change. | |
| You decide | Let Claude pick the cleanest approach. | |

**User's choice:** Add FAILED to NodeStatus
**Notes:** Clean, explicit state representation preferred over derived/computed state.

### What actions should be available for failed nodes?

| Option | Description | Selected |
|--------|-------------|----------|
| Retry + Teardown | Retry re-triggers provisioning. Teardown cleans up. New "retry" action type. | |
| Setup + Teardown | Re-use existing 'setup' action plus teardown to clean up. No new action type. | ✓ |
| You decide | Let Claude pick based on ACTION_CONFIG patterns. | |

**User's choice:** Setup + Teardown
**Notes:** Reuses existing action types — no new concepts needed.

---

## Error Display Format

### How should failure details appear on the main fleet dashboard?

| Option | Description | Selected |
|--------|-------------|----------|
| Inline text after badge | Short error summary in the same State cell after the badge. Compact. | |
| Expandable sub-row | Click the failed badge to expand a detail row below showing step + error. | ✓ |
| Tooltip on hover | Hover over badge for tooltip. Simplest JS but poor mobile support. | |

**User's choice:** Expandable sub-row
**Notes:** Balances detail availability with clean fleet view.

### Should the sub-row expand automatically for failed nodes, or only on click?

| Option | Description | Selected |
|--------|-------------|----------|
| Auto-expand on failed | Always show error sub-row for failed nodes on page load. | |
| Click to expand | Sub-row starts collapsed, operator clicks to see details. | ✓ |
| You decide | Let Claude pick. | |

**User's choice:** Click to expand
**Notes:** Keeps fleet view clean when multiple nodes are failed.

---

## Error Detail Level

### How much error detail should the expandable sub-row show?

| Option | Description | Selected |
|--------|-------------|----------|
| Step name + full error | Complete error message with no truncation. May be multi-line. | ✓ |
| Step name + truncated error | First ~200 chars with 'see node detail' link for full message. | |
| You decide | Let Claude pick. | |

**User's choice:** Step name + full error
**Notes:** Operators get all detail in one place.

### Should the failed step name be the provisioning step or exception type?

| Option | Description | Selected |
|--------|-------------|----------|
| Provisioning step name | Track last active ProvisioningStep, store as failed_step (e.g., "nvidia_driver"). | ✓ |
| You decide | Let Claude figure out the capture approach. | |

**User's choice:** Provisioning step name
**Notes:** Immediately tells operators which step broke.

---

## Claude's Discretion

- How to track "last active step" in provision() (local variable, context manager, etc.)
- Sub-row HTML/CSS structure and expand/collapse JS
- AdminNodeResponse field design for error data
- UnifiedNodeService error data merging approach
- badge-failed CSS styling
- Test structure

## Deferred Ideas

None — discussion stayed within phase scope
