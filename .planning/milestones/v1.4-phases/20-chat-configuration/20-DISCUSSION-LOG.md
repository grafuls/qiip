# Phase 20: Chat Configuration - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-21
**Phase:** 20-Chat Configuration
**Areas discussed:** System prompt placement, System prompt behavior, Dark mode gaps

---

## System Prompt Placement

### Where should the system prompt editor live?

| Option | Description | Selected |
|--------|-------------|----------|
| Collapsible panel | Textarea between model selector bar and messages. Visible by default, can be collapsed. | ✓ |
| Settings icon + modal | Gear icon next to model dropdown opens a modal with the textarea. | |
| Inline in model bar | Extend model selector bar with a small text input. | |

**User's choice:** Collapsible panel
**Notes:** None

### Should the panel start expanded or collapsed?

| Option | Description | Selected |
|--------|-------------|----------|
| Collapsed by default | Saves vertical space. Users expand when needed. | ✓ |
| Expanded by default | Makes the feature discoverable with placeholder text. | |
| You decide | Let Claude pick. | |

**User's choice:** Collapsed by default
**Notes:** None

### How should the collapse toggle look?

| Option | Description | Selected |
|--------|-------------|----------|
| Label + chevron | "System Prompt ▸" text label next to model dropdown, chevron rotates when expanded. | ✓ |
| Icon only | Small icon button next to model dropdown. Compact but less discoverable. | |
| You decide | Let Claude pick. | |

**User's choice:** Label + chevron
**Notes:** None

---

## System Prompt Behavior

### Should the system prompt persist across page refreshes?

| Option | Description | Selected |
|--------|-------------|----------|
| localStorage | Survives page refresh and browser restart. Same pattern as theme toggle. | ✓ |
| JS variable only | Cleared on page refresh, consistent with conversation history. | |
| You decide | Let Claude pick. | |

**User's choice:** localStorage
**Notes:** None

### What happens to conversation when system prompt changes mid-conversation?

| Option | Description | Selected |
|--------|-------------|----------|
| Keep conversation, apply to next request | Messages stay visible. Updated prompt takes effect on next send. | ✓ |
| Warn and clear conversation | Confirmation dialog, then wipe messages. | |
| You decide | Let Claude pick. | |

**User's choice:** Keep conversation, apply to next request
**Notes:** None

### Should the textarea have placeholder text?

| Option | Description | Selected |
|--------|-------------|----------|
| Placeholder text | Show hint like "You are a helpful assistant..." | ✓ |
| Empty, no placeholder | Blank textarea. | |
| You decide | Let Claude pick. | |

**User's choice:** Placeholder text
**Notes:** None

---

## Dark Mode Gaps

### Any visual inconsistencies to fix?

| Option | Description | Selected |
|--------|-------------|----------|
| Just verify, no known issues | Theme toggle works. Ensure new panel follows theme variables. | ✓ |
| I've seen issues | Specific problems to flag. | |
| Ensure new UI matches | No known issues, standard requirement for new CSS. | |

**User's choice:** Just verify, no known issues
**Notes:** Chat page already uses dashboard.css variables and same theme toggle pattern. New system prompt panel must use existing theme variables.

---

## Claude's Discretion

- Exact placeholder text wording for system prompt textarea
- CSS styling details for the collapsible panel (padding, transition, border)
- Chevron icon choice (CSS triangle, Unicode character, or SVG)

## Deferred Ideas

None — discussion stayed within phase scope.
