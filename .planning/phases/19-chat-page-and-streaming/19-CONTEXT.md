# Phase 19: Chat Page and Streaming - Context

**Gathered:** 2026-07-20
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver a browser-based chat page where users can converse with any healthy inference model through the existing proxy. The page allows typing messages, streaming token-by-token responses in real time, and selecting which model to talk to. Conversation history lives in-session only (cleared on page refresh).

</domain>

<decisions>
## Implementation Decisions

### Message Display
- **D-01:** Chat bubbles — user messages aligned right, assistant messages aligned left, with distinct background colors
- **D-02:** Fixed bottom input bar — text input + send button pinned to viewport bottom, messages scroll above
- **D-03:** Shared nav bar with "Chat" link — add to existing QUADS top bar, chat page served at `/chat`
- **D-04:** Markdown rendering via marked.js — use marked.js (CDN or vendored) for assistant responses including code blocks. This pulls forward the "Markdown rendering" future requirement from REQUIREMENTS.md

### Model Selector
- **D-05:** Model dropdown at top of chat area — fetches from `/v1/models`, always visible above the message area
- **D-06:** Keep conversation visible on model switch — messages stay on screen, new messages go to the new model. Full conversation history sent with each request (standard OpenAI chat behavior)
- **D-07:** Disabled selector with message when no models — show "No models available" in dropdown, disable send button

### Streaming UX
- **D-08:** Streaming tokens appear directly in assistant bubble — send button disabled during generation
- **D-09:** Inline error display — if streaming fails mid-response, show error message inside the assistant bubble. Toast for connection-level errors (reuse `showToast()`)
- **D-10:** Smart auto-scroll — auto-scroll to follow new tokens, pause when user scrolls up to read, resume when user scrolls back to bottom
- **D-11:** `fetch + ReadableStream` for SSE consumption — POST to `/v1/chat/completions` with `stream: true`, parse SSE events from the readable stream

### Claude's Discretion
- CSS styling details (colors, spacing, fonts) — follow existing `dashboard.css` conventions
- Exact bubble sizing and padding
- How to load marked.js (CDN vs vendored copy)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Existing API Endpoints
- `inference_proxy/api/routes.py` — OpenAI-compatible proxy routes including `/v1/chat/completions` (streaming + non-streaming) and `/v1/models`
- `inference_proxy/models/openai.py` — `ChatCompletionRequest` Pydantic model defining the request schema

### Dashboard Patterns
- `inference_proxy/api/dashboard.py` — Jinja2 template rendering pattern (FastAPI route → HTMLResponse)
- `inference_proxy/templates/dashboard.html` — Existing HTML template with nav bar, theme toggle, and page structure
- `inference_proxy/static/js/dashboard.js` — Vanilla JS patterns: `showToast()`, `ACTION_CONFIG` data-driven dispatch, fetch API usage
- `inference_proxy/static/css/dashboard.css` — Existing CSS with dark/light theme support via `[data-theme]`

### Application Wiring
- `inference_proxy/main.py` — Router mounting (`include_router`), static files mount, lifespan setup

### Requirements
- `.planning/REQUIREMENTS.md` — CHAT-01, CHAT-02, CHAT-03 requirements and out-of-scope boundaries

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `showToast(message, type)` in `dashboard.js` — toast notification utility for errors/success
- Theme toggle in nav bar — dark/light mode already wired with `localStorage` persistence
- `Jinja2Templates` instance in `dashboard.py` — shared template directory at `inference_proxy/templates/`
- `EventSourceResponse` + `format_sse_event` in `routes.py` — SSE streaming already implemented server-side

### Established Patterns
- **Jinja2 + vanilla JS:** No build step, no framework. HTML shell from Jinja2, JS fetches data from API endpoints
- **Router per domain:** `dashboard_router`, `admin_router`, `router` — each in its own module, mounted in `main.py`
- **Static files:** CSS in `static/css/`, JS in `static/js/`, served via FastAPI `StaticFiles` mount at `/static`
- **Data-driven dispatch:** `ACTION_CONFIG` pattern in `dashboard.js` — single object maps actions to their config

### Integration Points
- `main.py:create_app()` — mount new `chat_router` via `application.include_router()`
- Dashboard nav bar in `dashboard.html` — add "Chat" link (also add to new `chat.html` template for consistency)
- `/v1/chat/completions` — existing POST endpoint accepts `stream: true` and returns SSE events
- `/v1/models` — existing GET endpoint returns available healthy models

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

*Phase: 19-Chat Page and Streaming*
*Context gathered: 2026-07-20*
