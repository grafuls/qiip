# Phase 35: Model Selector on Node Detail Page - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-29
**Phase:** 35-model-selector-node-detail
**Areas discussed:** Model selector placement, Setup flow integration, Catalog fetch timing

---

## Model Selector Placement

### Where should the model selector dropdown live?

| Option | Description | Selected |
|--------|-------------|----------|
| New card section | A new "Setup Configuration" card between Node Info and Model Recommendations | ✓ |
| Inside Node Info card | Model dropdown row in existing Node Info table | |
| Header area near power buttons | Dropdown in header alongside power badge | |

**User's choice:** New card section
**Notes:** None

---

## Setup Flow Integration

### How should setup work from the new card?

| Option | Description | Selected |
|--------|-------------|----------|
| Standalone Setup button in card | Card has its own Setup button, dropdown setup unchanged | |
| Replace Actions dropdown setup | Remove setup from dropdown, card is the only setup path | |
| Card selects model, dropdown triggers | Card is just a selector, Actions dropdown reads the selection | ✓ |

**User's choice:** Card selects model, dropdown triggers
**Notes:** None

---

## Catalog Fetch Timing

### When to fetch the catalog?

| Option | Description | Selected |
|--------|-------------|----------|
| On page load (always) | Fetch in DOMContentLoaded alongside other init calls | ✓ |
| On page load if node allows setup | Only fetch when node state is available/failed | |

**User's choice:** On page load (always)
**Notes:** None

---

## Empty State

### When catalog is empty, what gets disabled?

| Option | Description | Selected |
|--------|-------------|----------|
| Disable Setup in Actions dropdown only | Card shows message, Setup disabled in dropdown | ✓ |
| Disable everywhere + show message | Setup removed from dropdown AND card shows prominent message | |

**User's choice:** Disable Setup in Actions dropdown only
**Notes:** None

---

## Claude's Discretion

- **D-07:** Native `<select>` element — not explicitly discussed but follows established vanilla JS pattern. No custom dropdown needed.

## Deferred Ideas

None — discussion stayed within phase scope.
