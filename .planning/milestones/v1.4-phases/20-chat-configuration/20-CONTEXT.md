# Phase 20: Chat Configuration - Context

**Gathered:** 2026-07-21
**Status:** Ready for planning

<domain>
## Phase Boundary

Add system prompt configuration to the chat page and verify dark/light mode consistency. Users can set a custom system prompt that is prepended to every chat request, and the chat page visually matches the dashboard in both themes.

</domain>

<decisions>
## Implementation Decisions

### System Prompt Placement
- **D-01:** Collapsible panel between model selector bar and message area — textarea slides open/closed below the model bar
- **D-02:** Collapsed by default — saves vertical space; users expand when needed
- **D-03:** "System Prompt" label + chevron toggle in the model selector bar — chevron rotates when expanded. Discoverable without cluttering the chat view

### System Prompt Behavior
- **D-04:** Persist system prompt in localStorage — survives page refresh and browser restart (same pattern as theme toggle)
- **D-05:** Keep conversation on prompt change — updated system prompt silently takes effect on the next send. No confirmation dialog, no message clearing
- **D-06:** Placeholder text in textarea — guide users with something like "You are a helpful assistant..." so they know what to type

### Dark/Light Mode
- **D-07:** No known visual inconsistencies — theme toggle already works in chat page (same localStorage + data-theme pattern as dashboard). New system prompt panel CSS must use existing theme variables (var(--surface), var(--border), var(--text), etc.)
- **D-08:** Verify theme consistency as part of implementation — spot-check both modes, no dedicated remediation expected

### Claude's Discretion
- Exact placeholder text wording for system prompt textarea
- CSS styling details for the collapsible panel (padding, transition, border)
- Chevron icon choice (CSS triangle, Unicode character, or SVG)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Chat Page (Phase 19 output)
- `inference_proxy/templates/chat.html` — Current chat page template with model selector bar, message area, input bar, and theme toggle
- `inference_proxy/static/js/chat.js` — Chat logic: messages array, streamResponse(), sendMessage(), loadModels(). System prompt must be prepended to messages array here
- `inference_proxy/static/css/chat.css` — Chat page styles extending dashboard.css variables. New collapsible panel styles go here

### Dashboard Patterns
- `inference_proxy/static/css/dashboard.css` — Theme CSS custom properties (var(--surface), var(--border), var(--text), etc.) and [data-theme] selectors
- `inference_proxy/templates/dashboard.html` — Reference for theme toggle pattern and nav bar structure

### Requirements
- `.planning/REQUIREMENTS.md` — CFG-01 (system prompt), CFG-02 (dark/light mode consistency)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- Theme toggle pattern in `chat.html` line 12 and 26 — localStorage get/set for theme, data-theme attribute on html element
- `showToast(message, type)` in `chat.js` — toast notifications for errors
- CSS custom properties in `dashboard.css` — `--surface`, `--border`, `--text`, `--bg`, `--border-strong`, `--radius` already used throughout chat.css
- `localStorage` already used for theme — system prompt follows same persistence pattern

### Established Patterns
- **Jinja2 + vanilla JS:** No build step, no framework. New UI is HTML elements + JS event listeners
- **CSS variables for theming:** All colors via `var(--*)`, `[data-theme="dark"]` selectors for overrides
- **Model selector bar:** 48px height, flexbox layout — system prompt toggle fits alongside model dropdown

### Integration Points
- `chat.html` model-selector-bar div — add "System Prompt" toggle button here
- `chat.html` between model-selector-bar and message-area — insert collapsible panel div
- `chat.js` streamResponse() line 68 — prepend system prompt message to the messages array sent in fetch body
- `chat.css` — add styles for collapsible panel, toggle button, textarea

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches within the decisions above.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 20-Chat Configuration*
*Context gathered: 2026-07-21*
