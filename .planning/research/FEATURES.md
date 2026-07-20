# Feature Landscape

**Domain:** Chatbot playground UI for an OpenAI-compatible inference proxy
**Researched:** 2026-07-20

## Existing Infrastructure (Already Built)

The proxy already provides everything the chat page needs on the backend:

| Endpoint | What It Does | Chat Page Uses It For |
|----------|-------------|----------------------|
| `POST /v1/chat/completions` | Proxies chat requests to vLLM with retry, circuit breaker, streaming SSE | Sending messages, receiving streamed tokens |
| `GET /v1/models` | Returns deduplicated healthy model list (OpenAI format) | Populating model selector dropdown |
| `GET /dashboard` | Jinja2 HTML shell + vanilla JS | Pattern to follow for chat page |

**No new proxy/API endpoints required.** The chat page is a pure frontend addition that calls existing APIs. The only backend change is a new route to serve the chat page HTML template (same pattern as `dashboard.py`).

## Table Stakes

Features users expect from any LLM chat playground. Missing any of these and it feels broken.

| Feature | Why Expected | Complexity | Depends On |
|---------|-------------|------------|------------|
| Message input with send button | Core interaction -- user types, hits send, sees response | Low | Nothing |
| Streaming token display | Every chat UI streams tokens; batch-only feels frozen | Medium | `fetch` + `ReadableStream` parsing SSE from `/v1/chat/completions` |
| Model selector dropdown | Multiple models served across fleet; user needs to pick one | Low | `GET /v1/models` (already exists) |
| User/assistant message bubbles | Visual distinction between who said what; standard chat layout | Low | Nothing |
| Stop generation button | Abort a bad/long response mid-stream; saves time and inference cost | Low | `AbortController` on the fetch call |
| Auto-scroll during streaming | New tokens should scroll into view; user should not have to chase the output | Low | Scroll-to-bottom on token append |
| In-session conversation history | Messages persist within the browser tab; clearing requires explicit action | Low | JavaScript array of `{role, content}` objects |
| System prompt field | Configure model persona/behavior; every playground has this | Low | Prepend `{role: "system", content: ...}` to messages array |
| Dark/light mode | Dashboard already has it; inconsistency would look broken | Low | Reuse existing CSS variables and theme toggle |
| Error display | Show connection failures, model unavailable, timeouts clearly in the chat flow | Low | Catch fetch errors, render as error message bubble |
| New conversation button | Clear messages and start fresh | Low | Reset messages array, clear DOM |
| Keyboard submit (Enter to send) | Universal expectation; Shift+Enter for newlines | Low | Keydown handler on textarea |

## Differentiators

Features that add polish. Not expected from an internal ops tool, but valuable if cheap to build.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Markdown rendering in responses | LLMs output markdown (headers, lists, bold, code blocks); raw text looks bad | Low | marked.js via CDN -- single `<script>` tag, zero build step. Sanitization not critical on internal network with trusted model output. |
| Code block styling | Models frequently output code; monospace + background makes it readable | Low | CSS only if using marked.js (it outputs `<pre><code>`) |
| Copy message button | Copy a response to clipboard without manual selection | Low | `navigator.clipboard.writeText()` on click |
| Temperature slider | Most-used generation parameter; lets user trade creativity vs determinism | Low | HTML `<input type="range">`, send as `temperature` in request body |
| Max tokens control | Prevent runaway generation; useful for quick tests | Low | HTML number input, send as `max_tokens` |
| Regenerate response | Retry last assistant message with same prompt; common when output is unsatisfying | Low | Re-send last messages array, replace last assistant message |
| Copy code block button | Per-code-block copy button inside rendered markdown | Medium | Post-render DOM walk to inject copy buttons on `<pre>` elements |
| Responsive layout | Usable on tablet/phone for engineers on the go | Low | CSS media queries (same pattern as dashboard) |

## Anti-Features

Features to explicitly NOT build. Each one is a complexity trap for an internal ops playground.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Persistent conversation storage (DB) | Adds backend complexity (schema, migrations, auth). PROJECT.md says "in-session, not persisted". | In-memory JS array, cleared on page refresh. Users who need transcripts can copy. |
| User authentication | Internal network only (v1 constraint). Auth adds middleware, session management, login UI. | No auth. Same as rest of dashboard. |
| Conversation branching / tree | Complex UI (carousel, tree navigation). Overkill for a testing playground. | Simple linear conversation. Regenerate overwrites last response. |
| Multi-turn regeneration carousel | ChatGPT-style variant carousel requires versioned message storage and carousel UI. | Single regenerate: re-run, replace last assistant message. |
| Syntax highlighting library (Prism.js, highlight.js) | Extra dependency for a secondary feature. Code blocks are readable with just monospace + background. | CSS-only code block styling on `<pre><code>` elements. Add highlight.js later only if users ask. |
| File/image upload | vLLM text models don't consume images (unless multimodal). Adds file handling complexity. | Text-only input. Add when multimodal models are deployed. |
| Tool calling / function calling UI | vLLM tool support varies. Complex UI for rendering tool calls and results. | Not in scope. Raw JSON in response is visible enough for debugging. |
| Prompt templates / prompt library | Management UI, storage, CRUD. Over-engineering for a playground. | System prompt textarea. Users paste their own prompts. |
| Export conversation (JSON/PDF) | Niche need, adds download logic and formatting. | Copy button per message covers 90% of the need. |
| WebSocket transport | SSE already works for server-to-client streaming. WebSocket adds connection management complexity for zero benefit. | `fetch` + `ReadableStream` for SSE consumption. |
| Streaming markdown re-parse debouncing | Only matters at very high token rates with very long messages. Vanilla DOM append is fast enough for vLLM output rates. | Render markdown on completion; append raw text during streaming. Simpler, no flicker. |
| Multiple concurrent conversations / tabs | UI for managing conversation list, switching, naming. Way beyond a playground. | One conversation at a time. New conversation button resets. |
| Message editing (edit a previous user message) | Requires re-running from edit point, conversation branching logic. | Type a new message. Regenerate covers the "last message was wrong" case. |

## Feature Dependencies

```
Model selector dropdown  -->  GET /v1/models (existing endpoint)
Send message              -->  POST /v1/chat/completions (existing endpoint)
Streaming display         -->  fetch + ReadableStream SSE parsing
Stop generation           -->  AbortController (browser native)
Markdown rendering        -->  marked.js (CDN, no build step)
Copy code block           -->  Markdown rendering (needs rendered <pre> elements)
Regenerate                -->  Conversation history (needs message array)
Temperature / max_tokens  -->  Send message (adds fields to request body)
Dark/light mode           -->  Existing CSS variables + theme toggle (already built)
System prompt             -->  Conversation history (prepended as first message)
```

## MVP Recommendation

Build in this order -- each step produces a usable increment:

1. **Chat page shell** -- Jinja2 template, nav link from dashboard, CSS using existing variables
2. **Model selector** -- Fetch `/v1/models`, populate `<select>`
3. **Message send + streaming display** -- `fetch` POST to `/v1/chat/completions` with `stream: true`, parse SSE via `ReadableStream`, append tokens to DOM
4. **Stop generation** -- `AbortController.abort()`, show partial response
5. **System prompt** -- Collapsible textarea, prepend to messages array
6. **Markdown rendering** -- marked.js via CDN, render on response completion (raw text during stream)
7. **Copy / regenerate** -- Action buttons on assistant messages

**Defer:** Temperature/max_tokens controls, copy code block button, responsive polish. Add when the core flow works.

## Implementation Notes

### SSE Consumption Pattern (vanilla JS, no dependencies)

`EventSource` API only supports GET. Chat completions require POST with JSON body. Use `fetch` with streaming:

```javascript
const controller = new AbortController();
const resp = await fetch("/v1/chat/completions", {
  method: "POST",
  headers: {"Content-Type": "application/json"},
  body: JSON.stringify({model, messages, stream: true}),
  signal: controller.signal,
});
const reader = resp.body.getReader();
const decoder = new TextDecoder();
// Parse SSE lines: "data: {...}\n\n" and "data: [DONE]\n\n"
```

This is the standard pattern used by every chat frontend that talks to OpenAI-compatible APIs without a framework.

### Markdown Rendering Strategy

Render markdown only on response completion (when `[DONE]` arrives or stream stops). During streaming, append raw text to a `<span>` with `white-space: pre-wrap`. This avoids:
- Flicker from re-parsing incomplete markdown mid-stream
- Broken rendering from half-open markdown syntax (`**bold` without closing `**`)
- Complexity of streaming-aware markdown parsers

On completion, replace the raw text span with `marked.parse(fullText)`. Single re-render, no debounce needed.

### No New Backend Dependencies

The chat page calls existing endpoints only:
- `GET /v1/models` -- already returns `{object: "list", data: [{id: "model-name", ...}]}`
- `POST /v1/chat/completions` with `stream: true` -- already returns SSE with `data: {choices: [{delta: {content: "token"}}]}` chunks

The only backend addition is one route handler in `dashboard.py` to serve the chat page HTML (identical pattern to existing `/dashboard` and `/dashboard/nodes/{node_id}` routes).

## Sources

- [OpenAI Playground UI](https://platform.openai.com/playground) -- model selector, parameter controls, system prompt pattern
- [HuggingFace Chat UI (GitHub)](https://github.com/huggingface/chat-ui) -- open source reference for streaming chat, dark mode, model switching
- [AI Chat UI Best Practices (TheFrontKit)](https://thefrontkit.com/blogs/ai-chat-ui-best-practices) -- streaming, stop button, markdown rendering
- [Chrome Dev: Render LLM Responses](https://developer.chrome.com/docs/ai/render-llm-responses) -- streaming markdown rendering, debounce, incomplete syntax handling
- [Streaming UI Patterns (The Prompt Bench)](https://thepromptbench.com/ai-product-ux/streaming-ui-patterns-that-dont-break/) -- SSE transport, cancellation, performance
- [MDN: Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events) -- EventSource limitations (GET only)
- [vLLM OpenAI-Compatible Server](https://docs.vllm.ai/en/latest/serving/online_serving/openai_compatible_server/) -- streaming SSE format, chat completions API
- [AI Chat Interface Design (Setproduct)](https://www.setproduct.com/blog/ai-chat-interface-ui-design) -- stop/regenerate/copy patterns, response lifecycle states
- [Shape of AI: Regenerate Pattern](https://www.shapeof.ai/patterns/regenerate) -- overwrite vs branching approaches
- [SSE vs WebSockets for LLM Streaming (Hivenet)](https://www.hivenet.com/post/llm-streaming-sse-websockets) -- SSE is correct for unidirectional token streaming
- [AI Chat UX Patterns (metacto)](https://www.metacto.com/blogs/ai-chat-ux-patterns-production) -- production chat UI patterns, stop/regenerate lifecycle
