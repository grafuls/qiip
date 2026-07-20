# Stack Research

**Domain:** Chatbot playground chat UI (v1.4 milestone)
**Researched:** 2026-07-20
**Confidence:** HIGH
**Scope:** Stack additions for chat playground page with streaming response display, model selection, and in-session conversation history. Existing stack (Python 3.12, FastAPI, httpx, etcd3gw, asyncssh, structlog, Pydantic v2, Jinja2) is validated and NOT re-evaluated here.

## New Python Dependencies for v1.4

**None.**

Zero new runtime or dev dependencies. The backend already exposes every endpoint the chat UI needs.

## Why No New Python Dependencies

The chat playground is a pure frontend feature consuming existing API endpoints:

| Requirement | Existing Endpoint | Notes |
|-------------|-------------------|-------|
| Send chat messages with streaming | `POST /v1/chat/completions` (stream=true) | SSE response, already implemented in `api/routes.py` |
| List available models | `GET /v1/models` | Returns OpenAI-compatible model list, filters to HEALTHY nodes only |
| Serve chat page HTML | Jinja2 + `dashboard_router` pattern | New route in `api/dashboard.py`, same pattern as `/dashboard` and `/dashboard/nodes/{node_id}` |
| Serve JS/CSS assets | `StaticFiles` mount at `/static` | Already configured in `main.py` line 264 |

The backend is done. v1.4 is a frontend-only milestone.

## Frontend Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Vanilla JS (fetch + ReadableStream) | Browser-native | SSE consumption from POST requests | `EventSource` is GET-only and cannot send a request body. `fetch()` with `response.body.getReader()` handles POST-based SSE streaming. ~30 lines of parsing code. No library needed. All modern browsers support `ReadableStream`. |
| marked.js (CDN) | >=18.0 | Markdown-to-HTML rendering | LLM responses contain markdown (code blocks, bold, lists, headers). Without rendering, users see raw ```` ```python ```` markers and `**bold**` text. One `<script>` tag, one function call: `marked.parse(text)`. 98% CommonMark compliant, MIT licensed. |
| CSS custom properties | Browser-native | Chat UI styling | Existing `dashboard.css` defines a full design system (colors, spacing, typography, dark/light themes). The chat page reuses these variables for visual consistency. No new CSS framework. |
| Jinja2 template | >=3.1 (installed) | Chat page HTML shell | Same pattern as `dashboard.html` and `node_detail.html`: Jinja2 renders the HTML shell, JS handles all dynamic behavior. |

### CDN Integration

```html
<!-- marked.js for markdown rendering -->
<script src="https://cdn.jsdelivr.net/npm/marked@18/lib/marked.umd.min.js"></script>
```

Pin to major version (`@18`) for stability while getting patch updates. The UMD build exposes `marked.parse()` globally.

### SSE Parsing from POST (the key pattern)

Browser `EventSource` only supports GET. The chat completions endpoint is POST. The standard approach is `fetch()` + `ReadableStream`:

```javascript
// ponytail: ~30 lines replaces any SSE client library
async function streamChat(messages, model, onToken, onDone, onError) {
  var resp = await fetch("/v1/chat/completions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model: model, messages: messages, stream: true }),
  });
  if (!resp.ok) { onError(await resp.json()); return; }
  var reader = resp.body.getReader();
  var decoder = new TextDecoder();
  var buf = "";
  while (true) {
    var chunk = await reader.read();
    if (chunk.done) break;
    buf += decoder.decode(chunk.value, { stream: true });
    var parts = buf.split("\n\n");
    buf = parts.pop();  // keep incomplete fragment
    for (var i = 0; i < parts.length; i++) {
      var line = parts[i].replace(/^data: /, "");
      if (line === "[DONE]") { onDone(); return; }
      if (line) onToken(JSON.parse(line));
    }
  }
  onDone();
}
```

This matches the SSE format emitted by FastAPI's `EventSourceResponse` in `api/routes.py`. Each event is `data: {json}\n\n`, terminated by `data: [DONE]\n\n`.

### Conversation History (in-session)

A JS array holds the message history. Each user message and assistant response is appended. The full array is sent as `messages` in each request, giving the model conversational context.

```javascript
// ponytail: conversation state is just an array
var conversationHistory = [];
// Push { role: "user", content: "..." } on send
// Push { role: "assistant", content: "..." } after stream completes
// Clear on "New Chat" button click
// Lost on page refresh (requirement: in-session, not persisted)
```

No localStorage, no IndexedDB, no persistence. Requirement explicitly says "in-session, not persisted."

### Model Selection

`fetch('/v1/models')` returns `{ object: "list", data: [{ id: "model-name", ... }] }`. Populate a `<select>` element. Refresh on page load.

## New Files

| File | Purpose | Pattern Source |
|------|---------|---------------|
| `templates/chat.html` | Jinja2 HTML shell for chat page | Same structure as `dashboard.html` |
| `static/js/chat.js` | SSE streaming, message rendering, model selection, conversation state | Same vanilla JS pattern as `dashboard.js` |
| `static/css/chat.css` | Chat-specific layout (message bubbles, input area, model selector) | Uses CSS custom properties from `dashboard.css` |

### Dashboard Route Addition

One new route in `api/dashboard.py`:

```python
@dashboard_router.get("/dashboard/chat", response_class=HTMLResponse)
async def chat_playground(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="chat.html")
```

No new router. No new dependencies. Follows the exact pattern of the existing `dashboard` and `node_detail` routes.

### Navigation

The top-bar nav in all templates needs a link to `/dashboard/chat`. Currently the brand text is the only nav element. Add simple text links:

```html
<nav class="top-bar">
  <div class="brand">...</div>
  <a href="/dashboard">Fleet</a>
  <a href="/dashboard/chat">Chat</a>
  <button class="theme-toggle">...</button>
</nav>
```

## Alternatives Considered

| Recommended | Alternative | Why Not |
|-------------|-------------|---------|
| Vanilla JS fetch + ReadableStream | EventSource API | EventSource is GET-only. Chat completions is POST. Cannot send request body. |
| Vanilla JS fetch + ReadableStream | fetch-event-source (npm) | Adds npm/build step to a project that has none. The manual parser is ~30 lines. |
| marked.js via CDN | No markdown rendering (plain text) | LLM output with raw markdown markers (`**bold**`, ``` ``` ```) is ugly and confusing. The one `<script>` tag is worth it. |
| marked.js via CDN | markdown-it via CDN | markdown-it is ~100KB vs marked's ~40KB. Both work. marked is faster and has wider CDN adoption. |
| marked.js via CDN | Bundled/vendored marked.js | CDN is simpler (no file to maintain). Vendoring is fine too if CDN access is a concern on the internal network -- download the UMD file to `/static/vendor/`. |
| CSS custom properties (existing) | Tailwind CSS | Adding Tailwind to a project with an established CSS design system is churn. The existing custom properties cover colors, spacing, typography, and dark mode. |
| In-memory JS array | localStorage persistence | Requirement says "in-session, not persisted." localStorage would persist across tabs/refreshes, which is explicitly out of scope. |
| Single chat.css file | Inline styles or extending dashboard.css | Separate file keeps chat-specific styles isolated. dashboard.css has the shared design system; chat.css has the chat layout. SRP for stylesheets. |

## What NOT to Add

| Technology | Why Not |
|------------|---------|
| React / Vue / Svelte | Existing pattern is vanilla JS + Jinja2. Adding a frontend framework for one chat page is massive scope creep. The dashboard, node detail page, and chat page are all the same pattern. |
| npm / webpack / vite | No build step exists in this project. Adding one for marked.js (available via CDN) is unjustified. |
| highlight.js / Prism.js | Syntax highlighting in code blocks is nice but not required for a playground. Defer until requested. If added later, one more CDN `<script>` tag. |
| WebSocket | SSE via fetch handles the unidirectional streaming. WebSocket adds bidirectional complexity for a request-response pattern. The proxy endpoint is SSE, not WebSocket. |
| DOMPurify | XSS protection for rendered markdown. Internal network only, no auth, no external access. Mention as future consideration if gateway ever becomes external-facing. |
| Any state management library | Conversation history is one array. No Zustand, no Redux, no signals. |
| Server-side chat session storage | Requirement is "in-session, not persisted." No database, no file, no Redis. |
| tenacity (retry on chat requests) | If the streaming request fails, show the error. User can retry manually. Auto-retry mid-conversation is confusing UX. |
| AbortController polyfill | Native in all browsers since 2017. Use `AbortController` directly to cancel in-flight streaming requests (e.g., when user clicks "Stop generating"). |

## Integration Points with Existing App

### Template Structure (matching existing pattern)

All three pages share the same HTML skeleton:
1. `<head>` with fonts, CSS, theme script
2. `<nav class="top-bar">` with brand and theme toggle
3. `<div class="dashboard">` wrapper with `<header>` and `<main>`
4. `<div id="toast-container">` for notifications
5. `<footer>`
6. Page-specific JS at bottom

`chat.html` follows this exactly. The `showToast()` function is duplicated across `dashboard.js` and `node_detail.js` already -- the chat page duplicates it again (or a future refactor extracts it to a shared `common.js`; not this milestone's problem).

### CSS Design System Reuse

Chat-specific CSS (`chat.css`) imports no frameworks. It uses CSS custom properties already defined in `dashboard.css`:

- `--surface`, `--bg`, `--text`, `--text-light` for container/text colors
- `--primary`, `--border`, `--radius` for interactive elements
- `--shadow-sm`, `--shadow-md` for elevation
- `[data-theme="dark"]` overrides for dark mode (automatic, same mechanism)
- Font families: Open Sans (body), IBM Plex Mono (code/monospace), Poppins (headings)

Both `dashboard.css` and `chat.css` are loaded on the chat page.

### API Contract

The chat page consumes the OpenAI-compatible API as a regular client:

```
POST /v1/chat/completions
Content-Type: application/json

{
  "model": "meta-llama/Llama-3.1-8B-Instruct",
  "messages": [
    {"role": "user", "content": "Hello"}
  ],
  "stream": true
}
```

Response: SSE stream of `ChatCompletionChunk` objects (defined in `models/openai.py`), terminated by `data: [DONE]`.

The chat page is just another client of the proxy. No special backend treatment needed.

## Installation

```bash
# No new dependencies
# Existing pyproject.toml already has everything needed
```

## Key Version Constraints

No new version constraints. All existing constraints from v1.3 remain valid.

| Existing Dependency | Minimum | Still Valid | Chat Page Relevance |
|---------------------|---------|-------------|---------------------|
| FastAPI >= 0.135 | Built-in EventSourceResponse | Yes | Backend SSE endpoint already uses this |
| Jinja2 >= 3.1 | Template rendering | Yes | New `chat.html` template |
| Pydantic >= 2.10 | ChatCompletionRequest model | Yes | Request validation on existing endpoint |

| CDN Dependency | Version | Purpose |
|----------------|---------|---------|
| marked.js | @18 (latest major) | Markdown rendering of LLM responses. Pin to major for stability. |

## Sources

- MDN ReadableStream: https://developer.mozilla.org/en-US/docs/Web/API/Streams_API/Using_readable_streams -- verified fetch + getReader() pattern for POST SSE
- SSE from POST via fetch: https://www.web-developpeur.com/en/blog/sse-fetch-readable-stream-api-key -- confirmed EventSource is GET-only, fetch+ReadableStream is standard approach
- marked.js official docs: https://marked.js.org/ -- latest v18.0.6, CDN via jsDelivr
- marked.js CDN: https://www.jsdelivr.com/package/npm/marked -- UMD build at `/lib/marked.umd.js`
- Existing codebase: `api/routes.py` -- SSE format uses `format_sse_event(data_str=...)`, emits `data: {json}\n\n`
- Existing codebase: `api/dashboard.py` -- template rendering pattern with Jinja2Templates
- Existing codebase: `models/openai.py` -- ChatCompletionChunk model defines the SSE event shape

---
*Stack research for: chatbot playground chat UI (v1.4)*
*Researched: 2026-07-20*
