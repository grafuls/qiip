---
phase: 19-chat-page-and-streaming
plan: 02
subsystem: chat-ui
tags: [chat, streaming, sse, javascript, markdown]
dependency_graph:
  requires: [chat-router, chat-template, chat-styles]
  provides: [chat-interaction, sse-streaming, model-selector-logic]
  affects: []
tech_stack:
  added: []
  patterns: [fetch-readablestream-sse, marked-markdown, vanilla-js-dom]
key_files:
  created: []
  modified:
    - inference_proxy/static/js/chat.js
decisions:
  - "Duplicated showToast from dashboard.js (~12 lines) rather than extracting shared module -- too small to justify"
  - "marked.parse called on every token -- acceptable perf for typical response lengths per research assumption A3"
  - "No DOMPurify -- internal tool, assistant content from own vLLM backends only (threat model T-19-03)"
metrics:
  duration: 95s
  completed: "2026-07-20T15:33:54Z"
  tests_added: 0
  tests_total: 444
---

# Phase 19 Plan 02: Chat Page Interaction Logic Summary

SSE streaming chat via fetch + ReadableStream, model selector from /v1/models, markdown rendering with marked.parse, smart auto-scroll, and inline error handling -- all wired to the DOM shell from Plan 01.

## What Was Built

1. **SSE streaming** (`chat.js`): POST to /v1/chat/completions with stream:true, consume via response.body.getReader() + TextDecoder, parse SSE data: lines with buffer for incomplete chunks, handle [DONE] terminator.

2. **Model selector**: Fetches GET /v1/models on DOMContentLoaded, populates dropdown with model IDs. Empty list shows "No models available" and disables send button.

3. **Message display**: User bubbles use textContent (safe), assistant bubbles use marked.parse innerHTML for markdown. Streaming cursor (CSS ::after animation) appended during generation.

4. **Input handling**: Enter sends, Shift+Enter inserts newline, textarea auto-grows up to 200px max-height. Send button and input disabled during streaming.

5. **Smart auto-scroll**: isNearBottom check with 40px threshold before each content append -- follows new tokens but pauses when user scrolls up.

6. **Error handling**: SSE error events displayed inline in assistant bubble with bubble-error class. Network/connection failures trigger showToast. Both re-enable input controls.

7. **Conversation history**: Messages array accumulates user and assistant messages, full array sent with each request per OpenAI chat completions contract.

## Task Commits

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Implement chat.js with SSE streaming, model selector, and full interaction | 39558b8 | inference_proxy/static/js/chat.js |

## Deviations from Plan

None -- plan executed exactly as written.

## Known Stubs

None -- all functionality wired end-to-end.

## Verification

- `grep` verification: fetch v1/chat/completions, marked.parse, getReader, showToast -- all present
- `uv run pytest tests/api/test_chat.py -x -v` -- 16/16 passed (existing tests still green)
