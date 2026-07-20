# Architecture: Chatbot Playground (v1.4)

**Domain:** Chat UI integration into existing LLM inference gateway dashboard
**Researched:** 2026-07-20
**Overall confidence:** HIGH

## Decision: Browser-Side SSE Consumer Against Existing Proxy Endpoint

The chat page is a pure frontend addition. The backend already has everything needed: `POST /v1/chat/completions` with `stream: true` returns SSE, and `GET /v1/models` returns available models. No new backend endpoints required.

The only backend change is one new route handler in `dashboard.py` that serves a `chat.html` Jinja2 template, plus a nav link added to the top bar across all templates. The real work is in a new `chat.js` and chat-specific CSS.

**Why not WebSocket?** The proxy speaks SSE (OpenAI protocol). Adding a WebSocket layer between browser and proxy creates a translation hop that must parse SSE and re-emit over WS. The browser can consume SSE directly from `/v1/chat/completions` -- zero backend changes, zero protocol translation.

**Why not `EventSource`?** The browser's `EventSource` API only supports GET requests. The OpenAI chat completions endpoint is POST. Use `fetch()` with `ReadableStream` instead -- native in all modern browsers, no library needed.

## Architecture Overview

```
              +----------------------------------------------------+
              |               FastAPI Gateway                      |
              |                                                    |
              |  +----------+  +-----------+  +------------------+ |
              |  | /v1/*    |  | /admin/*  |  | /dashboard       | |
              |  | (proxy)  |  | (fleet)   |  | /dashboard/chat  | |
              |  +----------+  +-----------+  +------------------+ |
              |       ^                              |             |
              |       |  POST /v1/chat/completions   |             |
              |       |  GET /v1/models              |             |
              |       +------------------------------+             |
              |                                                    |
              |  (No new backend logic. Chat page calls existing   |
              |   /v1/* endpoints directly from browser JS.)       |
              +----------------------------------------------------+
                     |
              Browser (chat.js)
                     |
              +------v-------------------------------------------------+
              |  1. fetch GET /v1/models  -->  populate model selector  |
              |  2. User types message, clicks send                    |
              |  3. fetch POST /v1/chat/completions {stream: true}     |
              |     with full conversation history as messages[]        |
              |  4. ReadableStream reader parses SSE text/event-stream |
              |  5. Extract delta.content from each chunk              |
              |  6. Append tokens to assistant message bubble in DOM   |
              |  7. On [DONE], mark message complete                   |
              +--------------------------------------------------------+
```

## New Components

| Component | Responsibility | Lives In | Communicates With |
|-----------|---------------|----------|-------------------|
| **Chat route** | Serve `chat.html` template | `inference_proxy/api/dashboard.py` (add route) | Jinja2Templates |
| **chat.html** | HTML shell: nav, model selector, message list, input area | `inference_proxy/templates/chat.html` | chat.js, dashboard.css + chat CSS |
| **chat.js** | SSE consumption, conversation state, DOM rendering | `inference_proxy/static/js/chat.js` | `/v1/models`, `/v1/chat/completions` |
| **chat.css** | Chat-specific styles (bubbles, input area, streaming indicator) | `inference_proxy/static/css/chat.css` | dashboard.css (inherits design tokens) |

### Modified Components

| Component | Change | Why |
|-----------|--------|-----|
| `dashboard.py` | Add `GET /dashboard/chat` route | Serves chat template, follows existing pattern |
| `dashboard.html` | Add "Chat" nav link in top-bar | Navigation between fleet and chat pages |
| `node_detail.html` | Add "Chat" nav link in top-bar | Consistent navigation |
| `dashboard.css` | Add nav link styles (`.nav-links`) | Top-bar gets page links between brand and theme toggle |

No changes to: `main.py`, `routes.py`, `admin.py`, `settings.py`, models, or any backend logic.

## Data Flow: User Input to Streamed Response

### Step 1: Page Load -- Fetch Available Models

```
Browser                           Gateway
  |                                  |
  |-- GET /v1/models --------------->|
  |<-- { data: [{id: "meta-llama/..."}] }
  |                                  |
  v                                  |
  Populate <select> with model IDs   |
```

The existing `GET /v1/models` endpoint already returns OpenAI-compatible model list, filtered to only HEALTHY nodes. No change needed.

### Step 2: User Sends Message

```javascript
// Conversation state lives in JS memory (array of {role, content} objects)
const messages = [
  { role: "system", content: "You are a helpful assistant." },  // optional
  { role: "user", content: "Hello" },
  { role: "assistant", content: "Hi there!" },  // from previous exchange
  { role: "user", content: "What is 2+2?" },    // new message
];
```

The full conversation history is sent with every request. This is standard OpenAI protocol -- the server is stateless, the client maintains context.

### Step 3: Streaming Request via fetch + ReadableStream

```javascript
const response = await fetch("/v1/chat/completions", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    model: selectedModel,
    messages: messages,
    stream: true,
  }),
});

const reader = response.body.getReader();
const decoder = new TextDecoder();
```

**Why `fetch()` not `EventSource`?** `EventSource` only supports GET. The OpenAI API is POST. `fetch()` with `ReadableStream` is the standard approach used by every chat UI (ChatGPT, Open WebUI, etc.).

### Step 4: Parse SSE Events from ReadableStream

The SSE wire format from vLLM (via the proxy) looks like:

```
data: {"id":"cmpl-...","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"role":"assistant"},"finish_reason":null}]}

data: {"id":"cmpl-...","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":"Hello"},"finish_reason":null}]}

data: {"id":"cmpl-...","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":"!"},"finish_reason":"stop"}]}

data: [DONE]

```

Parser logic (in `chat.js`):

```javascript
// ponytail: minimal SSE parser, handles split chunks across read boundaries
let buffer = "";
while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  buffer += decoder.decode(value, { stream: true });
  const lines = buffer.split("\n");
  buffer = lines.pop();  // keep incomplete line in buffer
  for (const line of lines) {
    if (!line.startsWith("data: ")) continue;
    const data = line.slice(6);
    if (data === "[DONE]") { /* finalize */ return; }
    const chunk = JSON.parse(data);
    const content = chunk.choices?.[0]?.delta?.content;
    if (content) appendToken(content);
  }
}
```

**Edge case: chunk boundaries.** A single `reader.read()` call may return a partial SSE event (the TCP segment can split anywhere). The buffer + split approach handles this correctly -- incomplete lines stay in the buffer until the next read fills them in.

### Step 5: Render Tokens to DOM

Each token is appended to the current assistant message element. No full re-render per token -- just `textContent +=` or `insertAdjacentText`.

```
User message bubble  -->  static, added to DOM on send
Assistant bubble     -->  created on first token, tokens appended incrementally
```

### Step 6: On Completion

When `[DONE]` arrives:
1. Push the completed assistant message `{role: "assistant", content: fullText}` to the conversation array
2. Re-enable the input field
3. Scroll to bottom

## Conversation State Management

**In-memory only.** Per PROJECT.md requirements: "Conversation history (in-session, not persisted)."

```javascript
// ponytail: conversation state is just an array. No store, no framework.
let conversationMessages = [];
let currentModel = null;

function addUserMessage(content) {
  conversationMessages.push({ role: "user", content });
  renderUserBubble(content);
}

function addAssistantMessage(content) {
  conversationMessages.push({ role: "assistant", content });
  // bubble was already rendered token-by-token during streaming
}

function clearConversation() {
  conversationMessages = [];
  // clear DOM
}
```

Model switching should clear the conversation (different models have different context windows and behaviors). Show a confirmation before clearing if there are messages.

## Component Boundaries

### chat.html (Template)

Follows the exact same pattern as `dashboard.html` and `node_detail.html`:
- Same `<head>` block (fonts, CSS links, theme init script)
- Same `<nav class="top-bar">` with brand + nav links + theme toggle
- Page-specific content in `<div class="dashboard">` (reuse the layout class)
- Template variables: none needed (model list fetched via JS, same as dashboard pattern)

```html
<!-- Key structural elements -->
<nav class="top-bar">
  <!-- brand, nav links (Fleet | Chat), theme toggle -->
</nav>
<div class="dashboard">
  <header class="dashboard-header">
    <h1>Chat Playground</h1>
    <div class="header-right">
      <select id="model-select">...</select>
      <button id="clear-btn">Clear</button>
    </div>
  </header>
  <main>
    <div id="chat-messages" class="chat-messages">
      <!-- message bubbles rendered by JS -->
    </div>
    <form id="chat-input-form" class="chat-input-form">
      <textarea id="chat-input" rows="1" placeholder="Type a message..."></textarea>
      <button type="submit" id="send-btn">Send</button>
    </form>
  </main>
</div>
```

### chat.js (JavaScript Module)

Responsibilities:
1. Fetch model list on load, populate selector
2. Manage conversation array (in-memory)
3. Handle form submission (send message)
4. Execute streaming fetch to `/v1/chat/completions`
5. Parse SSE events, render tokens
6. Handle errors (network, model unavailable, proxy errors)
7. Auto-resize textarea, scroll management
8. Abort in-flight request on new send or clear

**Does NOT duplicate:** `showToast()` -- the chat page can include its own minimal version or inline it. The dashboard's toast is in `dashboard.js` (not a shared module), and the chat page has different toast needs (error display during streaming). Keep it self-contained rather than extracting a shared module for two toast call sites.

### chat.css (Styles)

Imports design tokens from `dashboard.css` (CSS custom properties are inherited). Chat-specific styles:

```css
/* Chat-specific layout -- uses existing --surface, --border, --text tokens */
.chat-messages { /* scrollable message area */ }
.chat-bubble { /* message bubble base */ }
.chat-bubble-user { /* right-aligned, primary background */ }
.chat-bubble-assistant { /* left-aligned, surface background */ }
.chat-input-form { /* sticky bottom input bar */ }
.chat-streaming { /* pulsing cursor indicator during streaming */ }
```

The chat page links BOTH `dashboard.css` (for tokens, top-bar, card, toast styles) and `chat.css` (for chat-specific layout).

## Navigation Update

The top-bar currently has brand + theme toggle with no page navigation. Adding a chat page requires nav links.

```html
<!-- Updated top-bar pattern (all three templates) -->
<nav class="top-bar" aria-label="Primary">
  <div class="brand">...</div>
  <div class="nav-links">
    <a href="/dashboard" class="nav-link">Fleet</a>
    <a href="/dashboard/chat" class="nav-link">Chat</a>
  </div>
  <button class="theme-toggle">...</button>
</nav>
```

Active state via template variable or URL check in JS. Keep it simple -- CSS class on current page link or check `location.pathname` in the inline script.

## Error Handling

| Error | Detection | User-Visible Behavior |
|-------|-----------|----------------------|
| No models available | `GET /v1/models` returns empty `data[]` | Model selector shows "No models available", send disabled |
| Model goes unhealthy mid-conversation | `POST /v1/chat/completions` returns 503 | Error message in chat area, model selector refreshes |
| Network error during streaming | `reader.read()` throws | Error message appended to assistant bubble, retry possible |
| SSE error event from proxy | `data` contains error JSON (proxy wraps backend errors) | Parse error, display in chat as error bubble |
| Request aborted (user clicked stop/clear) | `AbortController.abort()` | Clean up partial response, re-enable input |

### AbortController for In-Flight Requests

```javascript
let currentAbortController = null;

async function sendMessage(content) {
  if (currentAbortController) currentAbortController.abort();
  currentAbortController = new AbortController();

  const response = await fetch("/v1/chat/completions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model: currentModel, messages: conversationMessages, stream: true }),
    signal: currentAbortController.signal,
  });
  // ... stream processing
}
```

This handles: stop button, clear conversation while streaming, switching models while streaming.

## Patterns to Follow

### Pattern 1: Same Template/JS/CSS Split as Dashboard

**What:** Jinja2 renders HTML shell, JS fetches data and renders dynamically.
**Why:** Proven in v1.1-v1.3 across dashboard and node_detail. No build step, no framework.
**Apply to:** Chat page uses the same structure.

### Pattern 2: Vanilla `fetch()` for API Calls

**What:** Direct `fetch()` calls to `/v1/*` endpoints, same-origin.
**Why:** No CORS issues (same origin). No API key needed (internal network, no auth in v1). Already established in `dashboard.js`.

### Pattern 3: CSS Custom Properties for Theming

**What:** All colors reference `--primary`, `--surface`, `--text`, etc.
**Why:** Dark/light mode toggle already works via `[data-theme]`. Chat CSS inherits this automatically.

## Anti-Patterns to Avoid

### Anti-Pattern: Adding a Backend "Chat Session" Layer
**What:** Creating a chat session model, storing conversation server-side, adding session management endpoints.
**Why bad:** Requirements say "in-session, not persisted." The OpenAI protocol is stateless -- client sends full message history. Adding server-side sessions creates state management complexity, memory growth, cleanup concerns.
**Instead:** Conversation array lives in browser JS memory. Page refresh clears it. Done.

### Anti-Pattern: WebSocket Chat Protocol
**What:** Adding a WebSocket endpoint that wraps the SSE proxy.
**Why bad:** Adds a protocol translation layer (SSE -> WS -> browser). Two connection types to maintain. The proxy already speaks SSE perfectly. `fetch()` + `ReadableStream` consumes SSE natively.
**Instead:** Direct `fetch()` POST to `/v1/chat/completions` with stream reader.

### Anti-Pattern: Shared JS Module Extraction
**What:** Extracting `showToast()`, action buttons, etc. into a shared module before the chat page needs them.
**Why bad:** Two pages sharing a toast function is not worth a module system. The dashboard and chat pages have different concerns. Premature extraction creates coupling.
**Instead:** Chat page has its own self-contained `chat.js`. If a third page appears, consider extraction then.

### Anti-Pattern: Markdown Rendering Library
**What:** Adding a markdown parser (marked.js, etc.) for assistant responses.
**Why bad:** Adds a dependency. LLM responses may contain markdown, but rendering plain text is functional and simpler. The requirement is "streaming response display," not "rich text rendering."
**Instead:** Render as plain text with `textContent`. Add markdown rendering later if users request it, and only then evaluate whether `<pre>` blocks for code and basic formatting suffice before pulling in a library.

## File Layout

```
inference_proxy/
    api/
        dashboard.py             # MODIFY: add GET /dashboard/chat route
    templates/
        dashboard.html           # MODIFY: add nav links
        node_detail.html         # MODIFY: add nav links
        chat.html                # NEW: chat page template
    static/
        css/
            dashboard.css        # MODIFY: add .nav-links styles
            chat.css             # NEW: chat-specific styles
        js/
            dashboard.js         # UNCHANGED
            node_detail.js       # UNCHANGED
            chat.js              # NEW: SSE consumer, conversation state, DOM rendering
```

New files: 3 (`chat.html`, `chat.js`, `chat.css`).
Modified files: 3 (`dashboard.py`, `dashboard.html`, `node_detail.html`) + minor CSS additions to `dashboard.css`.

## Build Order (Suggested Phase Structure)

Based on dependency analysis:

1. **Nav links + chat route + empty template** -- Wire `GET /dashboard/chat` in `dashboard.py`, add nav links to all templates, create bare `chat.html` with layout but no functionality. Deployable: clicking "Chat" shows a placeholder page.

2. **Model selector + chat layout** -- Fetch `/v1/models` on page load, populate `<select>`. Build the chat message area and input form HTML/CSS. No streaming yet.

3. **Streaming SSE consumer** -- Implement `fetch()` + `ReadableStream` SSE parsing in `chat.js`. Send messages, parse tokens, render to DOM. This is the core feature.

4. **Polish: error handling, abort, UX** -- AbortController for stop/clear, error display, auto-resize textarea, scroll management, keyboard shortcuts (Enter to send, Shift+Enter for newline), empty state messaging.

Each phase is independently testable and shippable. Phase 3 is the critical path -- phases 1-2 are scaffolding, phase 4 is polish.

## Sources

- Existing codebase: `inference_proxy/` source files - HIGH confidence
- [MDN: ReadableStream](https://developer.mozilla.org/en-US/docs/Web/API/ReadableStream) - HIGH confidence
- [MDN: Using readable streams](https://developer.mozilla.org/en-US/docs/Web/API/Streams_API/Using_readable_streams) - HIGH confidence
- [MDN: AbortController](https://developer.mozilla.org/en-US/docs/Web/API/AbortController) - HIGH confidence
- [OpenAI streaming API docs](https://platform.openai.com/docs/api-reference/streaming) - HIGH confidence
- vLLM OpenAI-compatible SSE format matches OpenAI spec - HIGH confidence (verified in existing `routes.py` SSE handling)
