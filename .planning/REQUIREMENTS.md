# Requirements: v1.4 Chatbot Playground

## Chat Core

- [x] **CHAT-01**: User can type a message and send it to a healthy inference endpoint
- [x] **CHAT-02**: User can see streamed tokens appear in real time as the model responds
- [x] **CHAT-03**: User can select which model to chat with from available healthy models

## Configuration

- [x] **CFG-01**: User can set a system prompt that is sent with every request
- [x] **CFG-02**: Chat page supports dark/light mode consistent with existing dashboard

## Future Requirements

- Stop generation button (AbortController)
- Auto-scroll during streaming
- New conversation button
- Keyboard submit (Enter to send, Shift+Enter for newline)
- Temperature slider
- Max tokens control
- Markdown rendering (marked.js)
- Code block styling
- Copy message / copy code block buttons
- Regenerate response

## Out of Scope

- **Persistent conversation storage** — in-session only, cleared on page refresh
- **Authentication** — internal network only (v1 constraint)
- **File/image upload** — text-only; add when multimodal models deployed
- **Tool calling UI** — raw JSON visible in response suffices
- **Conversation branching** — linear conversation only
- **Prompt templates / library** — system prompt textarea covers it
- **WebSocket transport** — SSE via fetch+ReadableStream is correct for unidirectional streaming

## Traceability

| Requirement | Phase | Plan | Status |
|-------------|-------|------|--------|
| CHAT-01 | 19 | — | Pending |
| CHAT-02 | 19 | — | Pending |
| CHAT-03 | 19 | — | Pending |
| CFG-01 | 20 | — | Pending |
| CFG-02 | 20 | — | Pending |
