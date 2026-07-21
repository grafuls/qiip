# Phase 19: Chat Page and Streaming - Research

**Researched:** 2026-07-20
**Domain:** Browser-based chat UI with SSE streaming (Jinja2 + vanilla JS)
**Confidence:** HIGH

## Summary

This phase adds a chat page at `/chat` where users converse with healthy vLLM models via the existing `/v1/chat/completions` streaming endpoint. The entire frontend is vanilla JS + Jinja2 -- no build step, no framework -- matching the established dashboard pattern exactly.

The server-side work is minimal: one new FastAPI router with a single GET endpoint that renders a Jinja2 template. All streaming infrastructure already exists in `routes.py`. The bulk of the work is client-side: SSE consumption via `fetch` + `ReadableStream`, markdown rendering via `marked.js` (CDN), and chat UX (bubbles, auto-scroll, model selector).

**Primary recommendation:** Follow the dashboard pattern exactly -- new `chat_router` in `api/chat.py`, new `chat.html` template, new `chat.js` and `chat.css` static files. No new Python dependencies.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- D-01: Chat bubbles -- user messages aligned right, assistant messages aligned left, with distinct background colors
- D-02: Fixed bottom input bar -- text input + send button pinned to viewport bottom, messages scroll above
- D-03: Shared nav bar with "Chat" link -- add to existing QUADS top bar, chat page served at `/chat`
- D-04: Markdown rendering via marked.js -- use marked.js (CDN or vendored) for assistant responses including code blocks
- D-05: Model dropdown at top of chat area -- fetches from `/v1/models`, always visible above the message area
- D-06: Keep conversation visible on model switch -- messages stay on screen, new messages go to the new model. Full conversation history sent with each request (standard OpenAI chat behavior)
- D-07: Disabled selector with message when no models -- show "No models available" in dropdown, disable send button
- D-08: Streaming tokens appear directly in assistant bubble -- send button disabled during generation
- D-09: Inline error display -- if streaming fails mid-response, show error message inside the assistant bubble. Toast for connection-level errors (reuse `showToast()`)
- D-10: Smart auto-scroll -- auto-scroll to follow new tokens, pause when user scrolls up to read, resume when user scrolls back to bottom
- D-11: `fetch + ReadableStream` for SSE consumption -- POST to `/v1/chat/completions` with `stream: true`, parse SSE events from the readable stream

### Claude's Discretion
- CSS styling details (colors, spacing, fonts) -- follow existing `dashboard.css` conventions
- Exact bubble sizing and padding
- How to load marked.js (CDN vs vendored copy)

### Deferred Ideas (OUT OF SCOPE)
None.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CHAT-01 | User can type a message and send it to a healthy inference endpoint | Router pattern from `dashboard.py`, request body matches `ChatCompletionRequest` model, POST via fetch to `/v1/chat/completions` |
| CHAT-02 | User can see streamed tokens appear in real time as the model responds | `fetch` + `ReadableStream` pattern for SSE consumption; existing server-side `_stream_completion()` emits `data:` lines with `[DONE]` terminator |
| CHAT-03 | User can select which model to chat with from available healthy models | `GET /v1/models` endpoint already returns `{object: "list", data: [{id: "model-name", ...}]}` from healthy nodes |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Chat message rendering | Browser / Client | -- | Pure DOM manipulation, no server involvement |
| SSE stream consumption | Browser / Client | -- | `fetch` + `ReadableStream` runs entirely in browser |
| Markdown rendering | Browser / Client | -- | marked.js runs client-side on received text |
| Model list fetching | Browser / Client | API / Backend | Client fetches from existing `/v1/models` endpoint |
| Message routing to model | API / Backend | -- | Existing `/v1/chat/completions` handles model selection and node routing |
| Chat page serving | Frontend Server (SSR) | -- | Jinja2 template rendered by FastAPI, one GET route |
| Conversation state | Browser / Client | -- | In-memory JS array, no persistence |

## Standard Stack

### Core (already installed -- zero new Python dependencies)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | >=0.135 | Chat route handler | Already in use for dashboard and API routes [VERIFIED: pyproject.toml] |
| Jinja2 | >=3.1 | Template rendering | Already in use for dashboard.html, node_detail.html [VERIFIED: pyproject.toml] |

### Client-Side (loaded via CDN -- zero install)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| marked.js | 18.0.6 | Markdown-to-HTML rendering | CDN-loaded via `<script>` tag, no build step [VERIFIED: cdn.jsdelivr.net confirmed v18.0.6] |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| marked.js CDN | Vendored copy | CDN is simpler, vendored avoids external dependency. CDN is fine for internal network tool |
| marked.js | markdown-it | marked is lighter, simpler API. markdown-it is more extensible but overkill here |
| DOMPurify | Nothing | Marked does not sanitize output. DOMPurify adds XSS protection. However: this is an internal-network-only tool where users type their own messages and assistant responses come from the proxy's own vLLM backends. XSS risk is negligible. Skip DOMPurify for now |
| fetch+ReadableStream | EventSource | EventSource is GET-only, cannot POST. Chat completions require POST with JSON body |

**Installation:**
```bash
# No installation needed. Zero new dependencies.
# marked.js loaded via CDN <script> tag in chat.html
```

## Architecture Patterns

### System Architecture Diagram

```
Browser (chat.js)
  |
  |-- GET /chat -----------------> FastAPI chat_router --> Jinja2 chat.html
  |
  |-- GET /v1/models ------------> FastAPI router ------> NodeRegistry (healthy models)
  |                                                        |
  |-- POST /v1/chat/completions -> FastAPI router ------> NodeSelector --> vLLM backend
  |   (stream: true)               |                                        |
  |                                 |<--- SSE data: lines <----- httpx-sse -+
  |<--- ReadableStream chunks <-----+
  |
  +-- marked.parse(content) --> innerHTML (assistant bubble)
```

### Recommended Project Structure
```
inference_proxy/
  api/
    chat.py              # NEW: chat_router with GET /chat
  templates/
    chat.html            # NEW: Jinja2 template (nav bar + chat layout)
  static/
    css/
      chat.css           # NEW: chat-specific styles
    js/
      chat.js            # NEW: SSE consumer, DOM manipulation, marked.js usage
tests/
  api/
    test_chat.py         # NEW: chat route tests (mirrors test_dashboard.py pattern)
```

### Pattern 1: FastAPI Router + Jinja2 Template (existing pattern)
**What:** Single-file router module with GET handler returning `TemplateResponse`
**When to use:** Every new HTML page in this project
**Example:**
```python
# Source: inference_proxy/api/dashboard.py (existing code)
from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

chat_router = APIRouter(tags=["chat"])

@chat_router.get("/chat", response_class=HTMLResponse)
async def chat(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="chat.html")
```
[VERIFIED: this exact pattern is used in `dashboard.py` lines 1-35]

### Pattern 2: SSE Consumption via fetch + ReadableStream
**What:** POST with `stream: true`, read response body incrementally, parse `data:` lines
**When to use:** Consuming streaming chat completions from the proxy
**Example:**
```javascript
// Source: standard fetch+ReadableStream SSE pattern
// [CITED: developer.mozilla.org/en-US/docs/Web/API/ReadableStream]
async function streamChat(messages, model) {
  const response = await fetch('/v1/chat/completions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model, messages, stream: true }),
  });
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const lines = buffer.split('\n');
    buffer = lines.pop(); // keep incomplete line

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      const data = line.slice(6);
      if (data === '[DONE]') return;
      const chunk = JSON.parse(data);
      const content = chunk.choices?.[0]?.delta?.content;
      if (content) appendToAssistantBubble(content);
    }
  }
}
```

### Pattern 3: Smart Auto-Scroll
**What:** Auto-scroll during streaming, pause when user scrolls up, resume at bottom
**When to use:** Any chat UI with streaming content
**Example:**
```javascript
// ponytail: threshold-based auto-scroll, no IntersectionObserver needed
function isNearBottom(el, threshold = 40) {
  return el.scrollHeight - el.scrollTop - el.clientHeight < threshold;
}

// Check before appending content
const wasAtBottom = isNearBottom(messageArea);
// ... append content ...
if (wasAtBottom) messageArea.scrollTop = messageArea.scrollHeight;
```
[ASSUMED -- standard pattern, widely used in chat UIs]

### Anti-Patterns to Avoid
- **EventSource for POST requests:** `EventSource` only supports GET. The chat completions endpoint requires POST with a JSON body. Use `fetch` + `ReadableStream` instead.
- **innerHTML without markdown parsing:** Raw text in bubbles won't render code blocks or formatting. Always pass assistant content through `marked.parse()`.
- **Re-parsing entire message on each token:** Don't call `marked.parse()` on the full accumulated text for every single token -- it's wasteful. Instead, accumulate raw text, parse once on completion or at debounced intervals during streaming.
- **Blocking the main thread with large markdown:** `marked.parse()` is synchronous. For very long responses, this is fine (marked is fast), but don't wrap it in a requestAnimationFrame loop unnecessarily.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Markdown rendering | Custom parser | marked.js v18.0.6 via CDN | Markdown spec is complex (tables, code blocks, nested lists). marked.js handles all of it |
| SSE line parsing | Custom event parser | ~20-line split-on-newline parser | SSE format is trivial (`data: ` prefix + `\n\n` separator). A library is overkill for POST-based SSE |
| Toast notifications | New toast system | Existing `showToast()` from dashboard.js | Already built, already styled |
| Theme support | New theme toggle | Existing `[data-theme]` CSS vars | Already built in dashboard.css |

**Key insight:** The only external dependency is marked.js via CDN `<script>` tag. Everything else reuses existing infrastructure or is trivially hand-written.

## Common Pitfalls

### Pitfall 1: SSE Buffer Splitting on Chunk Boundaries
**What goes wrong:** A `ReadableStream` chunk may split a `data:` line mid-way. Parsing lines without buffering drops partial data.
**Why it happens:** The browser delivers chunks at arbitrary byte boundaries, not SSE event boundaries.
**How to avoid:** Always buffer incomplete lines. Split on `\n`, keep the last element (potentially incomplete) as the next buffer.
**Warning signs:** Occasional missing tokens or JSON parse errors in the console.

### Pitfall 2: Markdown Re-render Flicker During Streaming
**What goes wrong:** Calling `marked.parse()` on every token causes the bubble innerHTML to flash/reflow.
**Why it happens:** Each `innerHTML` assignment destroys and recreates DOM nodes.
**How to avoid:** During streaming, append raw text to a text node. On stream complete (or at debounced intervals), do a final `marked.parse()` render. Alternatively, set `innerHTML` on each token but accept the reflow -- for short messages this is imperceptible.
**Warning signs:** Visible flicker on code blocks, cursor jumping in scrolled content.

### Pitfall 3: Auto-scroll Fights User Scroll
**What goes wrong:** User scrolls up to read earlier messages, but new tokens force scroll to bottom.
**Why it happens:** Unconditional `scrollTop = scrollHeight` after every append.
**How to avoid:** Check `isNearBottom()` before appending. Only auto-scroll if user was already at/near bottom.
**Warning signs:** User reports "page jumps" while reading during streaming.

### Pitfall 4: Conversation History Grows Unbounded
**What goes wrong:** Full `messages` array sent with every request. After many exchanges, the request payload exceeds vLLM's context window.
**Why it happens:** OpenAI chat API expects full history in each request. No truncation means unbounded growth.
**How to avoid:** For Phase 19, this is acceptable (session-only, users will refresh). Document as known limitation. Future: add token counting and truncation.
**Warning signs:** 400/413 errors from vLLM after long conversations.

### Pitfall 5: Stale Model List
**What goes wrong:** Models become unhealthy after page load, but dropdown still shows them.
**Why it happens:** Model list fetched once on page load, never refreshed.
**How to avoid:** Re-fetch `/v1/models` on each send attempt, or on a timer. Simplest: fetch before each request (latency is negligible for an internal tool).
**Warning signs:** "Model not found" errors when selecting a model that went unhealthy.

### Pitfall 6: Nav Bar Duplication
**What goes wrong:** Nav bar HTML duplicated between `dashboard.html` and `chat.html` diverges over time.
**Why it happens:** Jinja2 supports template inheritance but the existing templates don't use it.
**How to avoid:** Accept the duplication for now (only 2-3 templates). The nav bar is ~10 lines. Extract to `{% include %}` or `{% extends %}` later if template count grows.
**Warning signs:** "Chat" link missing from one page but present on another.

## Code Examples

### SSE Event Format from Existing Server
```
data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","created":1234567890,"model":"meta-llama/Llama-3-8B","choices":[{"index":0,"delta":{"content":"Hello"},"finish_reason":null}]}

data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","created":1234567890,"model":"meta-llama/Llama-3-8B","choices":[{"index":0,"delta":{"content":" world"},"finish_reason":null}]}

data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","created":1234567890,"model":"meta-llama/Llama-3-8B","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: [DONE]
```
[VERIFIED: matches `_stream_completion()` in `routes.py` lines 343-407 -- `format_sse_event(data_str=sse.data)` re-emits upstream data, and `format_sse_event(data_str="[DONE]")` terminates]

### Error Event in SSE Stream
```
data: {"error":{"message":"Connection error: ...","type":"proxy_error","param":null,"code":"connection_error"}}

data: [DONE]
```
[VERIFIED: `routes.py` lines 398-401 -- on exception, emits `map_proxy_error()` result as JSON then `[DONE]`]

### /v1/models Response Format
```json
{
  "object": "list",
  "data": [
    {"id": "meta-llama/Llama-3-8B", "object": "model", "created": 0, "owned_by": "vllm"},
    {"id": "mistralai/Mistral-7B", "object": "model", "created": 0, "owned_by": "vllm"}
  ]
}
```
[VERIFIED: `routes.py` lines 311-340 -- `list_models()` returns exactly this structure from healthy nodes]

### marked.js CDN Usage
```html
<!-- UMD script tag -- exposes global `marked` object -->
<script src="https://cdn.jsdelivr.net/npm/marked@18/lib/marked.umd.min.js"></script>
<script>
  // marked.parse() converts markdown string to HTML string
  const html = marked.parse('**bold** and `code`');
  element.innerHTML = html;
</script>
```
[VERIFIED: marked.js docs at marked.js.org confirm UMD global exposes `marked.parse()`]

### Router Mounting in main.py
```python
# Source: inference_proxy/main.py lines 259-264
application.include_router(router)           # /v1/* API routes
application.include_router(admin_router)     # /admin/* routes
application.include_router(dashboard_router) # /dashboard route
# Add: application.include_router(chat_router) # /chat route
```
[VERIFIED: `main.py` lines 259-261]

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `EventSource` for SSE | `fetch` + `ReadableStream` | ~2022 | EventSource is GET-only. Modern AI chat UIs all use fetch for POST+stream |
| `marked.sanitize` option | External sanitizer (DOMPurify) | marked v1.0 (2021) | Built-in sanitize was removed. Use DOMPurify if XSS is a concern |
| `sse-starlette` | FastAPI built-in `EventSourceResponse` | FastAPI 0.135 | Server-side already uses built-in SSE. No action needed |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | DOMPurify is unnecessary for internal-network-only tool where users type their own messages | Standard Stack / Alternatives | LOW -- if the tool becomes external-facing, add DOMPurify. Trivial to add later: wrap `marked.parse()` output in `DOMPurify.sanitize()` |
| A2 | Smart auto-scroll with 40px threshold is the right UX | Code Examples | LOW -- threshold is trivially adjustable |
| A3 | Re-rendering full markdown on each token is acceptable for typical response lengths | Pitfalls | LOW -- marked.js benchmarks at thousands of ops/sec. Only matters for extremely long responses |

## Open Questions

1. **CDN vs vendored marked.js**
   - What we know: CDN (`cdn.jsdelivr.net`) is the simplest approach. Vendored avoids external network dependency.
   - What's unclear: Whether deployment environment has reliable internet access for CDN.
   - Recommendation: Use CDN (per Claude's Discretion). If deployment is air-gapped, vendor the file into `static/js/vendor/marked.umd.min.js`. The switch is one line in the `<script src>`.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 1.4.x |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/api/test_chat.py -x` |
| Full suite command | `uv run pytest` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CHAT-01 | GET /chat returns 200 HTML | unit | `uv run pytest tests/api/test_chat.py::TestChatRoute -x` | Wave 0 |
| CHAT-01 | HTML contains send button and textarea | unit | `uv run pytest tests/api/test_chat.py::TestChatTemplate -x` | Wave 0 |
| CHAT-02 | HTML loads chat.js (SSE consumer) | unit | `uv run pytest tests/api/test_chat.py::TestChatTemplate -x` | Wave 0 |
| CHAT-03 | HTML contains model selector element | unit | `uv run pytest tests/api/test_chat.py::TestChatTemplate -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/api/test_chat.py -x`
- **Per wave merge:** `uv run pytest`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/api/test_chat.py` -- covers CHAT-01, CHAT-02, CHAT-03 (HTML structure tests mirroring `test_dashboard.py` pattern)

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Internal network only, no auth in v1 |
| V3 Session Management | no | No server-side sessions, conversation is client-side only |
| V4 Access Control | no | No RBAC, internal tool |
| V5 Input Validation | yes | Pydantic `ChatCompletionRequest` validates all fields server-side (already exists) |
| V6 Cryptography | no | No secrets handled in this phase |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| XSS via markdown rendering | Tampering | marked.js output is set via innerHTML. Mitigated by: (1) assistant content comes from own vLLM backends, (2) user content is rendered as text nodes not innerHTML, (3) DOMPurify can be added later if needed |
| Prompt injection via URL params | Tampering | No URL parameters influence prompts. All messages typed by user |

## Sources

### Primary (HIGH confidence)
- `inference_proxy/api/dashboard.py` -- Jinja2 template rendering pattern (verified in codebase)
- `inference_proxy/api/routes.py` -- SSE streaming implementation, `/v1/models` response format (verified in codebase)
- `inference_proxy/models/openai.py` -- `ChatCompletionRequest` model fields (verified in codebase)
- `inference_proxy/main.py` -- Router mounting pattern (verified in codebase)
- `inference_proxy/templates/dashboard.html` -- Nav bar structure, theme toggle (verified in codebase)
- `inference_proxy/static/css/dashboard.css` -- CSS custom properties, theme vars (verified in codebase)
- `inference_proxy/static/js/dashboard.js` -- `showToast()`, fetch patterns (verified in codebase)
- `tests/api/test_dashboard.py` -- Test patterns for HTML route testing (verified in codebase)

### Secondary (MEDIUM confidence)
- [marked.js docs](https://marked.js.org/) -- CDN usage, `marked.parse()` API, security advisory
- [MDN ReadableStream](https://developer.mozilla.org/en-US/docs/Web/API/ReadableStream) -- `fetch` + `getReader()` pattern for SSE
- [vLLM OpenAI-compatible server docs](https://docs.vllm.ai/en/stable/serving/openai_compatible_server/) -- SSE chunk format
- [jsDelivr marked CDN](https://www.jsdelivr.com/package/npm/marked) -- confirmed v18.0.6 available

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- zero new dependencies, all patterns verified in codebase
- Architecture: HIGH -- follows existing dashboard pattern exactly
- Pitfalls: HIGH -- SSE parsing and auto-scroll are well-documented patterns

**Research date:** 2026-07-20
**Valid until:** 2026-08-20 (stable -- no fast-moving dependencies)
