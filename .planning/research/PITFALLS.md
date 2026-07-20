# Domain Pitfalls

**Domain:** Chatbot Playground Chat UI for OpenAI-Compatible Inference Proxy
**Researched:** 2026-07-20
**Confidence:** HIGH (verified against existing codebase SSE implementation, OpenAI API contract, and real-world streaming UI failure patterns)

**Scope:** Pitfalls specific to adding a chat playground page (v1.4) to the existing Jinja2 + vanilla JS dashboard. Prior pitfalls (v1.0-v1.3) are in git history.

---

## Critical Pitfalls

Mistakes that cause broken streaming, data loss, or require rework of the chat UI foundation.

### Pitfall 1: Using EventSource Instead of fetch + ReadableStream

**What goes wrong:** The browser's native `EventSource` API only supports GET requests. The OpenAI chat completions endpoint (`POST /v1/chat/completions`) requires a POST with a JSON body containing `messages`, `model`, and `stream: true`. EventSource cannot send a request body or custom headers, and is limited to GET. A developer sees "SSE" and reaches for EventSource -- it connects, the server returns 405 Method Not Allowed (or ignores the missing body), and nothing works.

The existing proxy already handles SSE correctly server-side (routes.py lines 343-407 using `aconnect_sse` + `EventSourceResponse`). The trap is on the browser side.

**Why it happens:** EventSource is the "obvious" SSE API. Tutorials and MDN docs show it for GET-based SSE streams. The OpenAI API is POST-based SSE, which EventSource cannot handle.

**Consequences:**
- Complete failure to stream -- no tokens appear.
- Developers may try workarounds (encoding the request in the URL, switching to WebSocket) that are unnecessary.
- Time wasted on the wrong approach before discovering fetch + ReadableStream.

**Prevention:**
- Use `fetch()` with `response.body.getReader()` and a `TextDecoder`. This is the only browser-native approach that supports POST + SSE.
- Do NOT add `@microsoft/fetch-event-source` or any npm dependency. This project has zero npm dependencies and no build step (validated decision from v1.1). The fetch + reader pattern is ~30 lines of vanilla JS.
- The pattern:
  ```javascript
  const response = await fetch('/v1/chat/completions', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({model, messages, stream: true}),
    signal: abortController.signal,
  });
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  // read loop with line buffering (see Pitfall 2)
  ```

**Detection:** If the chat page makes a GET request to `/v1/chat/completions`, EventSource is being used incorrectly.

**Phase:** First phase -- streaming foundation. This is the most fundamental decision in the chat UI.

---

### Pitfall 2: Not Buffering Incomplete SSE Lines from ReadableStream Chunks

**What goes wrong:** Each `reader.read()` call returns a `Uint8Array` chunk from the network. These chunks do NOT align with SSE line boundaries. A single chunk may contain:
- Multiple complete SSE events (`data: {...}\n\ndata: {...}\n\n`)
- A partial line that continues in the next chunk (`data: {"id":"chatcmpl-abc","choices":[{"delta":{"con` ... next chunk: `tent":"hello"}}]}\n\n`)
- Multiple events plus a partial line

If the code naively splits on `\n` and tries `JSON.parse()` on each piece, it throws `SyntaxError: Unexpected end of JSON input` on partial lines. The token is lost and never displayed.

This is the most frequently reported bug in hand-rolled SSE clients. The existing proxy handles this correctly server-side (httpx-sse does the buffering), but the browser-side consumer must do it too.

**Why it happens:** Network chunking is invisible in local development. On localhost, chunks typically arrive as complete SSE events because there is no network fragmentation. The bug only manifests over real networks with latency, where TCP segments split SSE events at arbitrary byte boundaries.

**Consequences:**
- Tokens silently dropped in production but not in development.
- `JSON.parse` errors in the console that are transient and hard to reproduce.
- Partial responses displayed to the user (missing words/sentences).

**Prevention:**
- Maintain a `buffer` string across `reader.read()` calls. Append each decoded chunk to the buffer. Split on `\n\n` (SSE event boundary). Only process complete events. Keep the remainder in the buffer for the next chunk.
- The line parser must:
  1. Append decoded text to buffer
  2. Split buffer on `\n\n`
  3. Process all complete events (all splits except the last)
  4. Retain the last split as the new buffer (it may be incomplete)
  5. For each complete event, strip the `data: ` prefix and handle `[DONE]`
- Test with artificial chunking: split a known SSE response at every possible byte offset and verify the parser reconstructs correctly.

**Detection:** Search for `JSON.parse` calls that are not guarded by a try/catch, or `split('\n')` without a buffer variable.

**Phase:** First phase -- streaming foundation. The line buffer is part of the SSE reader, not a separate feature.

---

### Pitfall 3: Mid-Stream Errors Indistinguishable from Normal Completion

**What goes wrong:** When the upstream vLLM node crashes, times out, or the network drops mid-stream, the SSE connection closes. From the browser's perspective, `reader.read()` returns `{done: true}` -- the exact same signal as a successful stream completion. The UI shows a partial response with no indication that it is incomplete.

The existing proxy handles this by emitting an error event as SSE data before `[DONE]` (routes.py lines 393-401), but only when the proxy itself catches the exception. If the TCP connection drops between proxy and browser, no error event arrives -- the reader just finishes.

**Why it happens:** HTTP streaming has no built-in "stream completed successfully" vs "stream terminated abnormally" distinction at the transport level. The `[DONE]` sentinel in the SSE data is the application-level signal, but it is never sent if the connection drops.

**Consequences:**
- User sees a partial response and thinks it is complete.
- No retry offered because the UI does not know the stream failed.
- If the error occurs early (e.g., first token), the user sees an empty assistant message with no explanation.

**Prevention:**
- Track whether `[DONE]` was received. When `reader.read()` returns `{done: true}` without a prior `[DONE]` event, treat it as an error: show "Response interrupted -- click to retry" on the partial message.
- Also check for error events in the SSE data. The proxy sends error responses as JSON in the SSE data field (routes.py line 400). Parse each `data:` line and check for the `error` key before extracting `choices[0].delta.content`.
- For the empty-response case (stream closes before any tokens): show a clear error message, not an empty bubble.
- When `response.ok` is false (non-200 status before streaming starts), read the response body as JSON (it will be an OpenAI error response, not SSE) and display the error message. The proxy returns JSON errors for 404/503/502 before streaming starts.

**Detection:** Test by killing a vLLM container mid-response and verifying the UI shows an error indicator on the partial message.

**Phase:** First phase -- streaming foundation. The `[DONE]` check is part of the SSE reader loop, not a bolt-on.

---

### Pitfall 4: No AbortController -- Cannot Cancel In-Flight Requests

**What goes wrong:** The user sends a message, the model starts streaming a long response, and the user wants to stop it (wrong model selected, bad prompt, just want to try again). Without an `AbortController`, there is no way to cancel the in-flight fetch. The stream continues consuming tokens (and network bandwidth) invisibly. The user sends another message while the first is still streaming, causing overlapping responses that corrupt the conversation display.

Worse: if the user navigates away from the chat page and back, the old fetch is still running in the background, holding a connection to the proxy, consuming a connection slot in the httpx pool (main.py line 209: `max_connections` limit).

**Why it happens:** `AbortController` is not required for fetch to work. It is an optional parameter (`signal`) that developers skip in the initial implementation and forget to add later.

**Consequences:**
- No "Stop generating" button possible.
- Orphaned streams waste backend resources (the vLLM node continues generating tokens nobody reads).
- Connection pool exhaustion if users rapidly navigate away and back.
- Race conditions when sending a new message while the previous response is still streaming.

**Prevention:**
- Create a new `AbortController` for each chat request. Store it in a module-level variable (e.g., `let currentController = null`). Before sending a new request, abort the previous one: `if (currentController) currentController.abort()`.
- Pass `signal: currentController.signal` to the `fetch()` call.
- Add a "Stop generating" button that calls `currentController.abort()` and transitions the UI from "streaming" to "stopped" state. The partial response is kept and marked as incomplete.
- On abort, the fetch rejects with `AbortError`. Catch it specifically and do NOT treat it as a stream error: `catch (err) { if (err.name === 'AbortError') return; /* user cancelled */ }`.
- Do NOT reuse an aborted controller. Once `abort()` is called, the signal is permanently aborted. Create a fresh controller for each request.

**Detection:** If there is no `AbortController` in the chat JS, or if sending a second message while the first streams causes garbled output.

**Phase:** First phase -- streaming foundation. The controller is created alongside the fetch call.

---

### Pitfall 5: Unbounded DOM Growth on Long Conversations

**What goes wrong:** Every message (user + assistant) is appended to the DOM as a new element. In a long conversation (50+ exchanges), the DOM grows to hundreds of elements, each potentially containing rendered markdown with code blocks, lists, and inline formatting. The page becomes sluggish: scrolling lags, token appending during streaming causes visible jank, and memory usage climbs.

This is the exact problem ChatGPT's web UI suffers from -- documented in multiple reports of 1-4GB RAM consumption on long conversations, with the root cause being unbounded DOM node accumulation without virtualization.

This project uses vanilla JS (no React virtual DOM, no framework), which is actually an advantage here -- no framework state overhead. But without explicit management, DOM growth is still the bottleneck.

**Why it happens:** Chat UIs are append-only by nature. Nobody removes old messages. Each new assistant response adds DOM nodes during streaming (one append per token), then the final rendered markdown replaces them. But the old messages stay forever.

**Consequences:**
- Page becomes sluggish after 30-50 message exchanges.
- Token streaming visibly slows down as `textContent` or `innerHTML` appends trigger layout recalculation on a growing DOM.
- Memory climbs linearly with conversation length.
- In extreme cases (100+ messages with code blocks), the tab crashes.

**Prevention:**
- For v1.4 scope (in-session, not persisted), this is moderate risk. Users are unlikely to have 100+ exchanges in a playground session. But the ceiling should be documented.
- Cap displayed messages at a reasonable limit (e.g., last 100 messages visible). Older messages are removed from the DOM but kept in the JS conversation array. A "Load earlier messages" button re-renders them if needed.
- During streaming, append tokens to a single pre-allocated element's `textContent` (not `innerHTML`). Do not create a new DOM node per token. Only render markdown after the stream completes.
- Use `DocumentFragment` for batch DOM operations, consistent with the existing dashboard pattern.
- `// ponytail: DOM cap at 100 messages, virtualize if users hit it`

**Detection:** Open DevTools, send 50+ messages, watch the DOM node count and memory usage in the Performance tab.

**Phase:** Second phase (polish). The initial implementation can be append-only with the cap as a follow-up if performance is observed to degrade.

---

## Moderate Pitfalls

Mistakes that cause significant UX degradation or debugging time.

### Pitfall 6: Proxy/Middleware Buffering Kills Token-by-Token Streaming

**What goes wrong:** The response streams correctly from vLLM to the proxy (httpx-sse handles this), and the proxy emits SSE events correctly (EventSourceResponse flushes per event). But an intermediate layer buffers the response, causing tokens to arrive in bursts rather than one-by-one.

Specific risks in this codebase:
- The `RequestLoggingMiddleware` (middleware.py) uses `BaseHTTPMiddleware`, which wraps the response. For streaming responses, BaseHTTPMiddleware has a known issue where it reads the entire response body before forwarding -- but in FastAPI's implementation, `EventSourceResponse` is an `AsyncGenerator` that is NOT fully consumed by BaseHTTPMiddleware. However, the middleware does add latency to the first byte.
- If NGINX is placed in front (noted as future work in PROJECT.md), its default `proxy_buffering on` setting will buffer the entire SSE stream and deliver it as one chunk. The fix is `proxy_buffering off` or `X-Accel-Buffering: no` header.
- The browser itself may buffer if `Cache-Control` headers allow caching of the SSE response.

**Why it happens:** Buffering is the default behavior at every network layer. SSE requires explicit opt-out of buffering at each layer. Missing it at any single layer defeats streaming end-to-end.

**Consequences:**
- Tokens arrive in bursts (e.g., 30 tokens every 2 seconds instead of 1 token every 60ms).
- The "typing effect" that makes chat UIs feel responsive is lost.
- Users think the system is slow because they stare at nothing between bursts.

**Prevention:**
- FastAPI's `EventSourceResponse` already sets appropriate headers (`Content-Type: text/event-stream`, `Cache-Control: no-cache`). Verify these are not overridden by middleware.
- Add `X-Accel-Buffering: no` header to SSE responses proactively (even before NGINX is deployed). It is harmless without NGINX and prevents the problem when NGINX is added.
- Test streaming behavior through the full stack, not just direct to the proxy. Use browser DevTools Network tab to observe individual SSE events arriving (EventStream tab in Chrome).
- Do NOT add response caching middleware to SSE routes.

**Detection:** Open Chrome DevTools > Network > click the streaming request > EventStream tab. Tokens should appear one-by-one with sub-second intervals. If they appear in bursts, something is buffering.

**Phase:** First phase -- verify during streaming implementation. A one-line header addition prevents future problems.

---

### Pitfall 7: Model Selector Shows Models That Disappear Mid-Conversation

**What goes wrong:** The model selector fetches available models from `GET /v1/models` (routes.py lines 311-340), which returns models from HEALTHY nodes only. The user selects a model, types several messages, and mid-conversation the underlying node goes UNHEALTHY (circuit breaker trips, node torn down, schedule enforcer removes it). The selected model disappears from `/v1/models`. The next message send fails with a 404 or 503.

The UX failure cascade:
1. Model disappears from the selector dropdown (if it refreshes periodically).
2. User's next message fails with an opaque error.
3. User does not understand why their conversation broke.
4. If the selector auto-selects a different model, the conversation context is wrong for the new model (different tokenizer, different behavior).

**Why it happens:** In this system, models come and go dynamically -- nodes are provisioned and torn down, circuit breakers trip and recover, schedule enforcers remove nodes on QUADS schedule boundaries. This is fundamentally different from OpenAI's API where models are static.

**Consequences:**
- Conversation breaks mid-session with no clear recovery path.
- User frustration: "it was working 30 seconds ago."
- If the selector silently switches models, the conversation quality degrades without explanation.

**Prevention:**
- The selected model is a conversation-level setting, not a global setting. Once a conversation starts with a model, that model is locked for that conversation. The selector is only active when starting a new conversation.
- When the selected model becomes unavailable mid-conversation, show a clear inline warning: "Model X is currently unavailable. Your conversation is paused. [Retry] [Switch model (starts new conversation)]". Do not silently switch.
- The model selector should show model availability status, not just names. A model served by 3 healthy nodes is more reliable than one served by 1 node. Consider showing "(2 nodes)" next to each model name.
- Refresh the model list on a reasonable interval (e.g., every 30 seconds, not every message send). Show stale indicators if the list has not refreshed.
- Do NOT auto-refresh the model selector while a stream is active. The selector should be disabled during streaming.

**Detection:** Tear down a node while a conversation is active and verify the UI handles it gracefully.

**Phase:** Model selector phase. The "lock model per conversation" decision affects state management.

---

### Pitfall 8: Sending the Entire Conversation History Exceeds the Model's Context Window

**What goes wrong:** The OpenAI chat completions API expects the full conversation history in the `messages` array on every request. The browser accumulates messages and sends them all. After 20-30 exchanges with a model that has a 4K or 8K context window, the request payload exceeds the context limit. vLLM returns a 400 error with a message about exceeding max tokens.

The user sees: a confusing error after a long, productive conversation with no warning that they were approaching the limit.

**Why it happens:** The playground sends the raw conversation array without tracking token count. There is no client-side token counting, and the server (vLLM) only validates after receiving the full request.

**Consequences:**
- Abrupt conversation failure after extended use.
- Error message from vLLM is technical (mentions token counts, context length) -- not user-friendly.
- User loses the conversation context because there is no way to trim and continue.

**Prevention:**
- For v1.4 (playground scope), keep it simple: show a message count indicator ("12/50 messages") and warn when approaching a configurable limit. Do not attempt client-side tokenization -- it requires model-specific tokenizer logic that is out of scope.
- When the server returns a 400 error mentioning context length, catch it specifically and show: "Conversation too long for this model. Start a new conversation or remove earlier messages."
- Add a "Clear conversation" button that resets the message array and the display.
- Consider a "New conversation" button (separate from clear) that resets everything including model selection.
- `// ponytail: message count limit, client-side token counting if users hit it`

**Detection:** Send 30+ long messages to a model with a small context window (e.g., 4K) and verify the error is handled gracefully.

**Phase:** Error handling phase. The message count indicator is part of the conversation state display.

---

### Pitfall 9: Rendering Markdown During Streaming Causes Flicker and Broken Layout

**What goes wrong:** LLM responses contain markdown: bold, italic, code blocks, lists, headers. If the UI renders markdown on every token (re-parsing the entire response through a markdown renderer on each append), two things break:
1. **Flicker:** The DOM is rebuilt on every token (~20-50ms intervals). Code blocks appear and disappear as partial fences (```` ``` ````) are parsed and re-parsed.
2. **Broken layout:** A partial bold marker (`**partial`) is rendered as literal `**partial` then jumps to **partial text** when the closing `**` arrives. Lists partially render, causing layout shifts.

**Why it happens:** Naive approach: `element.innerHTML = markdownToHtml(fullResponseSoFar)` on every token. Works for plain text, breaks for structured markdown.

**Consequences:**
- Visually jarring streaming experience.
- Code blocks flash in and out of existence during streaming.
- Users cannot read the response while it is being generated (the whole point of streaming).

**Prevention:**
- During streaming: append tokens to a `<pre>` or plain text element using `textContent` (not `innerHTML`). This shows raw text without markdown rendering. It is readable and does not flicker.
- After streaming completes (`[DONE]` received): render the full response through a markdown renderer and replace the plain text element with the rendered HTML. This gives a single, clean transition from streaming to rendered.
- If the project wants live markdown rendering during streaming: debounce the render (50-100ms minimum between renders) and only re-render when the buffer has grown by a meaningful amount (e.g., 10+ characters). This reduces flicker dramatically.
- Do NOT add a markdown rendering library for v1.4 unless specifically requested. Plain text streaming is perfectly adequate for a playground. `// ponytail: plain text during stream, markdown render on complete if needed`
- If markdown rendering is added: use a lightweight library (e.g., `marked` via CDN, no build step needed). Do not add it to the project's dependencies -- load it from a `<script>` tag.

**Detection:** Stream a response containing a code block and watch for visual flicker during generation.

**Phase:** Polish phase. Start with plain text streaming, add markdown rendering as a separate step.

---

### Pitfall 10: Race Condition When Sending a New Message Before Previous Stream Completes

**What goes wrong:** User sends message A. The assistant starts streaming a response. User gets impatient and sends message B before the response to A finishes. Now two things can happen:
1. If AbortController is not used (Pitfall 4): two concurrent streams write to the same output element, interleaving tokens from response A and response B.
2. If AbortController IS used but the conversation state is not managed: message B is sent with the conversation history that includes message A but NOT the (partial) response to A. The assistant's context is incomplete.

**Why it happens:** The UI does not enforce a "one request at a time" constraint. The send button remains active during streaming.

**Consequences:**
- Garbled output mixing two responses.
- Conversation history becomes inconsistent -- the assistant's partial response to A is visible in the UI but not included in the messages array sent with B.
- Confusing conversation flow for the user.

**Prevention:**
- Disable the send button and input while a response is streaming. Re-enable when the stream completes (success, error, or abort).
- When the user aborts (Stop button) and immediately sends a new message: include the partial assistant response in the conversation history (mark it as truncated in the messages array, or omit it). The simplest approach: abort the previous stream, discard the partial response from the messages array, and send the new message with the complete history up to the last complete exchange.
- The conversation state should be: `messages` array (complete exchanges only) + `pendingResponse` (the currently streaming response, not yet added to `messages`). When a stream completes, `pendingResponse` is committed to `messages`. When aborted, it is discarded.
- Show a brief transition state between abort and new send: "Stopped. Ready for new message."

**Detection:** Rapidly send multiple messages and verify the output is not garbled.

**Phase:** First phase -- the state model (messages array vs pending response) is foundational.

---

## Minor Pitfalls

Issues that cause minor UX friction or developer confusion.

### Pitfall 11: Chat Page fetch Hits the Proxy's Own OpenAI Endpoints -- Request Logging Noise

**What goes wrong:** The chat page's fetch calls to `/v1/chat/completions` and `/v1/models` go through the `RequestLoggingMiddleware`. Every chat message generates a log entry identical to external API client requests. The operations logs become noisy with playground requests, making it harder to monitor real client traffic.

**Prevention:**
- Accept the noise for v1.4. The middleware logs all requests by design (middleware.py docstring: "Logs ALL requests"). Adding path-based filtering adds complexity for minimal gain.
- If it becomes a problem: add a `source` field to the log (e.g., `playground` vs `api`) based on a custom header or referrer. The chat page fetch can include `X-Source: playground` header, and the middleware can log it.
- `// ponytail: log noise acceptable for playground, filter if ops team complains`

**Phase:** Not a phase concern. Note for post-v1.4 if logging noise becomes an issue.

---

### Pitfall 12: No Visual Feedback Between Send and First Token (Time-to-First-Token Gap)

**What goes wrong:** The user sends a message. The fetch request goes to the proxy, which selects a node, forwards to vLLM, which processes the prompt (loading KV cache, running prefill). This takes 1-10 seconds depending on prompt length and model size. During this gap, the UI shows nothing -- no spinner, no "thinking" indicator. The user thinks the system is broken and sends the message again (triggering Pitfall 10).

**Why it happens:** The first SSE event from vLLM only arrives after prefill completes. The gap between fetch send and first token is invisible to the streaming reader.

**Consequences:**
- User thinks the system is unresponsive.
- Duplicate message sends.
- Poor perceived performance even when actual performance is normal for the model size.

**Prevention:**
- Show a "thinking" indicator (typing dots, spinner) immediately when the send button is pressed. Remove it when the first token arrives.
- The indicator should appear BEFORE the fetch resolves (it is an optimistic UI update, not dependent on the server response).
- If the fetch itself fails (network error, 503), replace the indicator with an error message.
- Set a timeout on the thinking indicator: if no first token arrives within 30 seconds, show "Taking longer than usual..." to set expectations.

**Detection:** Send a message to a large model and observe the gap between send and first token.

**Phase:** First phase -- the thinking indicator is part of the send flow.

---

### Pitfall 13: Chat Page CSS Conflicts with Existing Dashboard Styles

**What goes wrong:** The chat page reuses the dashboard's CSS file (`dashboard.css`) or adds styles to it. Chat-specific styles (message bubbles, input area, streaming indicator) conflict with dashboard table styles. Or the chat page's full-height layout breaks the dashboard's scrolling behavior.

The existing dashboard uses a specific layout: top bar, header, card with table, footer (dashboard.html). The chat page needs a fundamentally different layout: fixed input at bottom, scrollable message area, no table.

**Why it happens:** Both pages share the same base template structure and CSS file. Adding chat styles to the existing CSS creates coupling between unrelated pages.

**Prevention:**
- Create a separate CSS file for the chat page: `static/css/chat.css`. Include both `dashboard.css` (for shared elements: top bar, footer, theme) and `chat.css` (for chat-specific layout).
- Alternatively, extract shared styles (top bar, theme, typography) into a `base.css` and have both `dashboard.css` and `chat.css` import it.
- The chat page should have its own Jinja2 template (`chat.html`), not be embedded in `dashboard.html`.
- Namespace chat styles: `.chat-container`, `.chat-message`, `.chat-input` -- avoid generic class names that could collide.

**Detection:** Add the chat page and verify the dashboard still renders correctly.

**Phase:** First phase -- template and CSS structure. Decide the file organization before writing styles.

---

### Pitfall 14: Conversation State Lost on Page Refresh (Expected but Confusing)

**What goes wrong:** The v1.4 scope says "in-session, not persisted." This means a page refresh wipes the conversation. Users who are accustomed to ChatGPT (which persists conversations) will be surprised. This is not a bug, but it needs to be communicated.

**Why it happens:** Deliberate scope decision. But without UX signaling, users assume persistence.

**Prevention:**
- Show a small notice on the chat page: "Conversations are not saved. Refreshing the page will clear the chat."
- Optionally: store conversation state in `sessionStorage` (survives refresh, cleared on tab close). This is ~5 lines of JS (`JSON.stringify`/`JSON.parse` the messages array) and dramatically improves UX without adding persistence infrastructure. `// ponytail: sessionStorage for refresh survival, real persistence if needed later`
- Do NOT use `localStorage` -- conversations would accumulate across sessions with no cleanup mechanism.

**Detection:** Refresh the page during a conversation and verify the behavior matches expectations.

**Phase:** Polish phase. sessionStorage is a nice-to-have, not a blocker.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| SSE streaming foundation | EventSource misuse (#1), chunk buffering (#2), mid-stream errors (#3), no AbortController (#4) | fetch + ReadableStream, line buffer, [DONE] tracking, AbortController per request |
| Conversation state model | Race on rapid sends (#10), unbounded history (#8) | Disable send during stream, messages vs pendingResponse split, message count indicator |
| Model selector | Dynamic model disappearance (#7) | Lock model per conversation, availability warning, do not auto-switch |
| Response display | Markdown flicker (#9), DOM growth (#5), no TTFT feedback (#12) | Plain text during stream, render on complete, message cap, thinking indicator |
| Proxy integration | Buffering kills streaming (#6), log noise (#11), SSE double-parse | X-Accel-Buffering header, accept log noise, verify browser parses proxy SSE correctly |
| Page structure | CSS conflicts (#13), state loss on refresh (#14) | Separate chat.css, own template, sessionStorage for refresh survival |

---

## Sources

- [Streaming API responses (OpenAI docs)](https://developers.openai.com/api/docs/guides/streaming-responses)
- [How to Stream OpenAI's Completion API Client-Side](https://www.xjavascript.com/blog/how-do-i-stream-openai-s-completion-api/) -- chunk splitting, TextDecoder, JSON parse errors
- [Stream OpenAI Chat Completions in JavaScript (Builder.io)](https://www.builder.io/blog/stream-ai-javascript)
- [Azure/fetch-event-source README](https://github.com/Azure/fetch-event-source/blob/main/README.md) -- EventSource limitations documented
- [SSE incomplete chunks discussion (Open WebUI)](https://github.com/open-webui/open-webui/discussions/13477) -- proxy chunk concatenation bugs
- [Streaming UI Patterns That Don't Break](https://thepromptbench.com/ai-product-ux/streaming-ui-patterns-that-dont-break/) -- debouncing, partial markdown, layout thrash
- [AI Chat UI Best Practices 2026](https://thefrontkit.com/blogs/ai-chat-ui-best-practices) -- buffered markdown rendering
- [ChatGPT memory leak / DOM growth reports](https://www.aiqnahub.com/chatgpt-memory-leak-ram/) -- unbounded DOM accumulation
- [SSE breaking at 2am (error handling)](https://dev.to/abhishek_chatterjee_33b9d/why-sse-for-ai-agents-keeps-breaking-at-2am-55ie) -- mid-stream errors, synthetic done events
- [Web Streams with OpenAI (vanilla JS + AbortController)](https://umaar.com/dev-tips/269-web-streams-openai/)
- [LiteLLM SSE parse bug](https://github.com/BerriAI/litellm/issues/25766) -- double encoding with `data:` prefix
- Existing codebase: `inference_proxy/api/routes.py` (SSE streaming implementation, error-in-stream handling)
- Existing codebase: `inference_proxy/static/js/dashboard.js` (vanilla JS patterns, DocumentFragment, polling)
- Existing codebase: `inference_proxy/api/middleware.py` (BaseHTTPMiddleware streaming behavior)
- Existing codebase: `inference_proxy/models/openai.py` (ChatCompletionRequest, ChatMessage models)
