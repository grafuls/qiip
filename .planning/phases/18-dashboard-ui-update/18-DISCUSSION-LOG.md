# Phase 18: Dashboard UI Update - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-17
**Phase:** 18-Dashboard UI Update
**Areas discussed:** Table column layout, Manual hostname fallback, Action button styling

---

## Table Column Layout

### Column handling for mixed node states

| Option | Description | Selected |
|--------|-------------|----------|
| Keep current columns + add GPU | Add GPU columns (vendor, model). Available nodes show empty cells for endpoint/model/connections/CB. Simple, uniform table. | ✓ |
| Two-tier grouping | Group rows by state (Available, Provisioned, Active). Each group could show only relevant columns via visual separation. | |
| Minimal + expandable row | Show core columns (Hostname, State, GPU, Actions) for all rows. Click to expand and see endpoint/model/connections/CB details for active nodes. | |

**User's choice:** Keep current columns + add GPU
**Notes:** Recommended option. Straightforward approach.

### GPU column placement

| Option | Description | Selected |
|--------|-------------|----------|
| After Node ID | Hostname → GPU Vendor → GPU Model → Endpoint → ... Groups identity + hardware together. | ✓ |
| Before Actions (end) | ...Circuit Breaker → Requests → GPU → Actions. Keeps existing column order intact, appends GPU. | |
| Single GPU column | Merge vendor+model into one "GPU" column (e.g. "NVIDIA A100"). Saves horizontal space. | |

**User's choice:** After Node ID
**Notes:** Groups identity and hardware information together.

### Empty cell treatment

| Option | Description | Selected |
|--------|-------------|----------|
| Em-dash (—) | Show — in empty cells. Consistent with the existing task table pattern. | ✓ |
| You decide | Claude picks the best visual treatment for empty cells. | |

**User's choice:** Em-dash (—)
**Notes:** Follows existing dashboard convention.

### Status vs State column

| Option | Description | Selected |
|--------|-------------|----------|
| Replace Status with State | Single column showing the unified state from Phase 17. Cleaner. | ✓ |
| Keep both columns | Status shows raw etcd status, State shows computed unified state. More data but redundant. | |

**User's choice:** Replace Status with State
**Notes:** Eliminates redundancy since Phase 17's unified state supersedes raw etcd status.

---

## Manual Hostname Fallback

### Placement

| Option | Description | Selected |
|--------|-------------|----------|
| Below the table header | A small "+ Manual setup" link below the Node Fleet card title that expands an inline input row. | ✓ |
| Footer of the table | A collapsible row at the bottom of the node table. | |
| Keep as separate card | Same card as today but collapsed by default with a toggle. | |

**User's choice:** Below the table header
**Notes:** Keeps it contextual with the node list.

### Expand/collapse mechanism

| Option | Description | Selected |
|--------|-------------|----------|
| Simple toggle link | Text link "+ Manual setup" that toggles visibility with vanilla JS display toggle. | ✓ |
| Disclosure triangle | HTML details/summary element. Native browser behavior, zero JS for toggle. | |
| You decide | Claude picks the simplest mechanism. | |

**User's choice:** Simple toggle link
**Notes:** Consistent with vanilla JS approach used throughout the dashboard.

---

## Action Button Styling

### Visual treatment per action type

| Option | Description | Selected |
|--------|-------------|----------|
| Color-coded by intent | Setup = blue/accent, Teardown = red, Retry = amber, Cancel/Force = red. Matches existing badge conventions. | ✓ |
| Uniform outline buttons | All actions use the same button style. Rely on label text. Simpler CSS. | |
| You decide | Claude picks styling that fits the existing dark theme. | |

**User's choice:** Color-coded by intent
**Notes:** Leverages existing color system from badge CSS.

### Confirmation dialogs

| Option | Description | Selected |
|--------|-------------|----------|
| Teardown and Force Teardown only | Only the most destructive actions. Setup, Retry, Cancel fire without confirmation. | |
| All destructive actions | Teardown, Force Teardown, and Cancel all require confirm(). More cautious. | ✓ |
| None — button disable is enough | No confirmation dialogs. Buttons disable after click. Faster workflow. | |

**User's choice:** All destructive actions
**Notes:** User prefers a cautious approach — Teardown, Force Teardown, and Cancel all require window.confirm().

### Multi-action layout

| Option | Description | Selected |
|--------|-------------|----------|
| Side by side | Buttons render inline next to each other in the Actions cell. | |
| Primary + dropdown | Most common action is a button, secondary actions in a small dropdown/menu. | ✓ |
| You decide | Claude picks based on max simultaneous actions (currently 2). | |

**User's choice:** Primary + dropdown
**Notes:** Saves horizontal space. Primary action = first item in the actions list from the API.

---

## Claude's Discretion

- QUADS status indicator wording and badge design (user did not select this area for discussion)
- Staleness thresholds and QUADS status endpoint design
- Dropdown/menu implementation for secondary actions
- CSS class naming for new button variants
- Wiring inline Setup buttons to existing POST /admin/nodes/setup

## Deferred Ideas

None — discussion stayed within phase scope.
