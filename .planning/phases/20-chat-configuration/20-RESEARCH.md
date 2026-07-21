# Phase 20: Chat Configuration - Research

**Researched:** 2026-07-21
**Domain:** Frontend UI (vanilla JS + Jinja2 + CSS)
**Confidence:** HIGH

## Summary

Phase 20 adds a system prompt textarea (collapsible panel) to the chat page and verifies dark/light mode consistency. The entire phase is frontend-only: edits to `chat.html`, `chat.js`, and `chat.css`. No backend changes, no new dependencies, no new routes.

The codebase already has all the patterns needed: localStorage for persistence (theme toggle), CSS custom properties for theming, flexbox layout in the model selector bar, and the `messages` array in `chat.js` where the system prompt gets prepended. The UI spec (`20-UI-SPEC.md`) is fully prescriptive with exact property values.

**Primary recommendation:** Edit three files (`chat.html`, `chat.js`, `chat.css`), reuse existing patterns verbatim. No abstractions, no new dependencies.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Collapsible panel between model selector bar and message area -- textarea slides open/closed below the model bar
- **D-02:** Collapsed by default -- saves vertical space; users expand when needed
- **D-03:** "System Prompt" label + chevron toggle in the model selector bar -- chevron rotates when expanded. Discoverable without cluttering the chat view
- **D-04:** Persist system prompt in localStorage -- survives page refresh and browser restart (same pattern as theme toggle)
- **D-05:** Keep conversation on prompt change -- updated system prompt silently takes effect on the next send. No confirmation dialog, no message clearing
- **D-06:** Placeholder text in textarea -- guide users with something like "You are a helpful assistant..." so they know what to type
- **D-07:** No known visual inconsistencies -- theme toggle already works in chat page. New system prompt panel CSS must use existing theme variables
- **D-08:** Verify theme consistency as part of implementation -- spot-check both modes, no dedicated remediation expected

### Claude's Discretion
- Exact placeholder text wording for system prompt textarea
- CSS styling details for the collapsible panel (padding, transition, border)
- Chevron icon choice (CSS triangle, Unicode character, or SVG)

### Deferred Ideas (OUT OF SCOPE)
None.

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CFG-01 | User can set a system prompt that is sent with every request | Prepend `{role: "system", content: value}` to `messages` array in `streamResponse()` fetch body. Persist via localStorage. |
| CFG-02 | Chat page supports dark/light mode consistent with existing dashboard | All new CSS uses existing `var(--*)` custom properties from dashboard.css. No new color tokens needed. Verify both themes render correctly. |

</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| System prompt UI | Browser / Client | -- | Collapsible panel, textarea, toggle button -- all DOM |
| System prompt persistence | Browser / Client | -- | localStorage read/write, same pattern as theme |
| System prompt injection into API request | Browser / Client | -- | Prepend to messages array in fetch body before POST to /v1/chat/completions |
| Dark/light mode consistency | Browser / Client | -- | CSS custom properties + data-theme attribute, already working |

No backend tier involvement. The proxy receives the messages array (which now includes the system message) and forwards it to vLLM unchanged.

## Standard Stack

No new libraries. All work uses what is already loaded:

| Technology | Already In | Purpose |
|------------|-----------|---------|
| Vanilla JS | chat.js | Toggle logic, localStorage, messages array manipulation |
| CSS custom properties | dashboard.css | Theming (var(--surface), var(--border), etc.) |
| Jinja2 | chat.html | Template for new HTML elements |
| localStorage API | Browser native | System prompt persistence (mirrors theme persistence) |

**Installation:** None required.

## Architecture Patterns

### Files Changed

```
inference_proxy/templates/chat.html   # Add toggle button + collapsible panel HTML
inference_proxy/static/js/chat.js     # Add system prompt logic
inference_proxy/static/css/chat.css   # Add collapsible panel + toggle styles
tests/api/test_chat.py               # Add tests for new HTML elements
```

### Pattern 1: localStorage Persistence (reuse existing)

**What:** Read on load, write on input -- same pattern as theme toggle already in chat.html line 12.
**When to use:** System prompt value.

```javascript
// Source: existing pattern in chat.html line 12 and 26
// Read on load:
var savedPrompt = localStorage.getItem('systemPrompt') || '';
systemPromptTextarea.value = savedPrompt;

// Write on input:
systemPromptTextarea.addEventListener('input', function () {
  localStorage.setItem('systemPrompt', this.value);
});
```

### Pattern 2: System Prompt Injection into Messages

**What:** Prepend system message to the messages array in the fetch body, not to the persistent `messages` array.
**When to use:** Every streamResponse() call.

```javascript
// Source: chat.js streamResponse() line 63-70
// Build payload messages: system prompt (if set) + conversation messages
var payloadMessages = messages.slice(); // copy
var sp = systemPromptTextarea.value.trim();
if (sp) {
  payloadMessages.unshift({ role: "system", content: sp });
}
// Use payloadMessages in fetch body instead of messages
```

**Critical:** Do NOT push the system message into the persistent `messages` array. It must be prepended at send time only, so changing the prompt mid-conversation takes effect on the next send (D-05) without duplicating system messages.

### Pattern 3: Collapsible Panel via max-height

**What:** CSS transition on max-height for smooth expand/collapse.
**When to use:** System prompt panel toggle.

```css
/* Source: standard CSS collapsible pattern, matches UI spec */
.system-prompt-panel {
  max-height: 0;
  overflow: hidden;
  transition: max-height 0.2s ease, padding 0.2s ease;
  padding: 0 32px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
}

.system-prompt-panel.expanded {
  max-height: 300px; /* generous ceiling for textarea + padding */
  padding: 16px 32px;
}
```

### Pattern 4: CSS Border Triangle Chevron

**What:** Pure CSS chevron using border trick, rotated via transform.
**When to use:** Toggle button indicator.

```css
.chevron {
  display: inline-block;
  width: 0;
  height: 0;
  border-left: 5px solid transparent;
  border-right: 5px solid transparent;
  border-top: 5px solid currentColor;
  margin-left: 4px;
  transition: transform 0.2s ease;
}

.system-prompt-toggle[aria-expanded="true"] .chevron {
  transform: rotate(180deg);
}
```

### Anti-Patterns to Avoid
- **Pushing system message into `messages` array:** Creates duplicates on every send. Prepend at send time only.
- **Using display:none for collapse animation:** No transition possible. Use max-height instead.
- **Adding new CSS color values:** All colors must use existing `var(--*)` tokens. No hex/rgb literals for themed elements.
- **Separate dark mode overrides for new elements:** If you only use `var(--*)` tokens, dark mode works automatically. No `[data-theme="dark"]` selectors needed for the new panel.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Persistence | Custom state manager | localStorage.getItem/setItem | Already used for theme, one line each |
| Collapsible panel | JS height calculation | CSS max-height transition | Simpler, no JS measurement needed |
| Chevron icon | SVG file / icon library | CSS border triangle | Zero dependencies, 5 lines of CSS |

## Common Pitfalls

### Pitfall 1: System Prompt Duplication
**What goes wrong:** System message gets pushed into `messages` array and accumulates with each send.
**Why it happens:** Treating system prompt like a user message instead of a per-request prefix.
**How to avoid:** Build `payloadMessages` as a copy with system message prepended. Never mutate `messages` for system prompt.
**Warning signs:** Multiple `{role: "system"}` entries in network tab request payload.

### Pitfall 2: Collapsed Panel Still Takes Space
**What goes wrong:** Panel has `padding` or `border` even when collapsed, creating a visible gap.
**Why it happens:** Setting `max-height: 0` but leaving padding/border unchanged.
**How to avoid:** Transition padding to 0 when collapsed. Use `border-bottom` only on `.expanded` state or set `border-bottom-color: transparent` when collapsed.
**Warning signs:** Thin line or gap visible between model selector bar and message area.

### Pitfall 3: localStorage Key Collision
**What goes wrong:** Using a generic key name that could conflict with other apps on the same origin.
**Why it happens:** Keys like "prompt" or "config" are too generic.
**How to avoid:** Use `systemPrompt` -- specific enough, and consistent with existing `theme` key.
**Warning signs:** System prompt value mysteriously changes or disappears.

### Pitfall 4: Textarea Not Accessible
**What goes wrong:** Screen readers cannot associate the textarea with its purpose.
**Why it happens:** Missing label element or aria-label.
**How to avoid:** Add `aria-label="System prompt"` on the textarea, `aria-expanded` and `aria-controls` on the toggle button (per UI spec).
**Warning signs:** Accessibility audit flags unlabeled form control.

## Code Examples

### Complete Toggle Button HTML (from UI spec)
```html
<!-- Inside .model-selector-bar, after #model-select -->
<button class="system-prompt-toggle" aria-expanded="false" aria-controls="system-prompt-panel">
  System Prompt <span class="chevron" aria-hidden="true"></span>
</button>
```

### Complete Panel HTML (from UI spec)
```html
<!-- Between .model-selector-bar and .message-area -->
<div class="system-prompt-panel" id="system-prompt-panel">
  <div class="system-prompt-inner">
    <textarea id="system-prompt" aria-label="System prompt" rows="3"
              placeholder="You are a helpful assistant..."></textarea>
  </div>
</div>
```

### Integration Point in streamResponse()
```javascript
// chat.js streamResponse() -- replace lines 66-69
body: JSON.stringify({
  model: modelSelect.value,
  messages: (function () {
    var sp = document.getElementById('system-prompt').value.trim();
    var m = messages.slice();
    if (sp) m.unshift({ role: "system", content: sp });
    return m;
  })(),
  stream: true,
}),
```

## State of the Art

No relevant changes. This phase uses stable browser APIs (localStorage, CSS transitions, DOM manipulation) that have not changed in years.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| -- | -- | -- | -- |

All claims verified against the existing codebase. No assumptions needed -- this is a pure extension of existing patterns visible in the source files.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x with FastAPI TestClient |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/api/test_chat.py -x` |
| Full suite command | `uv run pytest` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CFG-01 | System prompt textarea present in HTML | unit (HTML assertion) | `uv run pytest tests/api/test_chat.py -x -k system_prompt` | Exists (needs new test methods) |
| CFG-01 | Toggle button present with aria-expanded | unit (HTML assertion) | `uv run pytest tests/api/test_chat.py -x -k toggle` | Exists (needs new test methods) |
| CFG-01 | System prompt panel div present | unit (HTML assertion) | `uv run pytest tests/api/test_chat.py -x -k panel` | Exists (needs new test methods) |
| CFG-02 | Chat CSS uses only var(--*) tokens | manual | Visual spot-check in both themes | Manual only -- CSS color audit |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/api/test_chat.py -x`
- **Per wave merge:** `uv run pytest`
- **Phase gate:** Full suite green before verify

### Wave 0 Gaps
- New test methods in `tests/api/test_chat.py` for: system-prompt textarea, toggle button, panel div, aria attributes

## Security Domain

Not applicable for this phase. All changes are client-side UI for an internal-only tool. No new API endpoints, no new data flows, no authentication changes. The system prompt is passed as a standard OpenAI `messages` array element -- the proxy already handles this payload.

## Sources

### Primary (HIGH confidence)
- `inference_proxy/templates/chat.html` -- current template structure, line-by-line
- `inference_proxy/static/js/chat.js` -- current JS logic, messages array, streamResponse()
- `inference_proxy/static/css/chat.css` -- current styles, CSS variable usage
- `inference_proxy/static/css/dashboard.css` -- theme custom properties, dark mode selectors
- `20-UI-SPEC.md` -- full visual and interaction contract
- `20-CONTEXT.md` -- locked decisions D-01 through D-08
- `tests/api/test_chat.py` -- existing test patterns

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new packages, all existing
- Architecture: HIGH -- three-file edit with line-level integration points identified
- Pitfalls: HIGH -- well-understood browser patterns

**Research date:** 2026-07-21
**Valid until:** No expiry -- stable browser APIs and existing codebase patterns
