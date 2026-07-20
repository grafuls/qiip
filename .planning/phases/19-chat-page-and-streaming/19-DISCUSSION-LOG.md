# Phase 19: Chat Page and Streaming - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-20
**Phase:** 19-Chat Page and Streaming
**Areas discussed:** Message display style, Model selector behavior, Streaming UX

---

## Message Display Style

### Layout
| Option | Description | Selected |
|--------|-------------|----------|
| Chat bubbles | Aligned left (assistant) and right (user) with background colors. Standard chat app feel. | ✓ |
| Full-width blocks | Each message takes full width with a role label. Like ChatGPT's layout. | |
| You decide | Claude picks the best fit for a Jinja2 + vanilla JS ops tool. | |

**User's choice:** Chat bubbles
**Notes:** None

### Input Position
| Option | Description | Selected |
|--------|-------------|----------|
| Fixed bottom bar | Input + send button pinned to viewport bottom. Messages scroll above. | ✓ |
| Inline at end of messages | Input sits after the last message and scrolls with content. | |
| You decide | Claude picks based on bubble layout choice. | |

**User's choice:** Fixed bottom bar
**Notes:** None

### Navigation
| Option | Description | Selected |
|--------|-------------|----------|
| Shared nav with Chat link | Add 'Chat' link to existing QUADS top bar. Chat page at /chat. | ✓ |
| Standalone page, no shared nav | Chat page has its own minimal header. | |
| You decide | Claude picks based on dashboard patterns. | |

**User's choice:** Shared nav with Chat link
**Notes:** None

### Code Blocks
| Option | Description | Selected |
|--------|-------------|----------|
| Plain monospace styling | Wrap code in pre/code with monospace font. No syntax highlighting library. | |
| Render with marked.js | Use marked.js for markdown rendering including code blocks. Listed as future requirement. | ✓ |
| Raw text only | No markdown rendering. Show raw text including markdown syntax. | |

**User's choice:** Render with marked.js
**Notes:** Pulls forward "Markdown rendering (marked.js)" from Future Requirements in REQUIREMENTS.md

---

## Model Selector Behavior

### Placement
| Option | Description | Selected |
|--------|-------------|----------|
| Top of chat area | Dropdown above message area, always visible. Fetches from /v1/models. | ✓ |
| Inside the input bar | Compact selector next to text input at bottom. Saves space but cramped. | |
| You decide | Claude picks based on layout decisions. | |

**User's choice:** Top of chat area
**Notes:** None

### Model Switch Behavior
| Option | Description | Selected |
|--------|-------------|----------|
| Keep conversation visible | Messages stay on screen, new messages go to new model. No data loss. | ✓ |
| Clear conversation on switch | Switching models starts a fresh chat. Clear context separation. | |
| You decide | Claude picks the simpler approach. | |

**User's choice:** Keep conversation visible
**Notes:** None

### Conversation Context
| Option | Description | Selected |
|--------|-------------|----------|
| Send full history | Each request includes all prior messages. Standard OpenAI chat behavior. | ✓ |
| Send only latest message | Each message is independent. Simpler but not a real chat. | |

**User's choice:** Send full history
**Notes:** None

### Empty State
| Option | Description | Selected |
|--------|-------------|----------|
| Disabled selector with message | Show 'No models available' in dropdown. Disable send button. | ✓ |
| Redirect to dashboard | If no models, redirect user to dashboard to set up nodes. | |
| You decide | Claude picks simplest approach. | |

**User's choice:** Disabled selector with message
**Notes:** None

---

## Streaming UX

### Loading State
| Option | Description | Selected |
|--------|-------------|----------|
| Streaming tokens + disabled input | Tokens appear in real-time in assistant bubble. Send button disabled. | ✓ |
| Typing indicator then streaming | Show 'thinking...' briefly before tokens start, then stream. | |
| You decide | Claude picks standard streaming pattern. | |

**User's choice:** Streaming tokens + disabled input
**Notes:** None

### Error Display
| Option | Description | Selected |
|--------|-------------|----------|
| Inline error in message bubble | If streaming fails, show error inside assistant bubble. Toast for connection errors. | ✓ |
| Toast notification only | Show toast popup for all errors. Reuses showToast(). | |
| You decide | Claude picks best UX for chat errors. | |

**User's choice:** Inline error in message bubble
**Notes:** None

### Auto-scroll
| Option | Description | Selected |
|--------|-------------|----------|
| Auto-scroll, pause on scroll-up | Auto-scroll to follow tokens. Pause when user scrolls up. Resume at bottom. | ✓ |
| Always auto-scroll | Always pin to bottom. User can't read earlier messages during generation. | |
| No auto-scroll | User manually scrolls. Simplest. | |

**User's choice:** Auto-scroll, pause on scroll-up
**Notes:** None

### SSE Client
| Option | Description | Selected |
|--------|-------------|----------|
| fetch + ReadableStream | POST and consume SSE via fetch. Works with POST. Scoped in REQUIREMENTS.md. | ✓ |
| You decide | Claude picks approach aligned with REQUIREMENTS.md. | |

**User's choice:** fetch + ReadableStream
**Notes:** Already decided in REQUIREMENTS.md Out of Scope section

---

## Claude's Discretion

- CSS styling details (colors, spacing, fonts) — follow existing dashboard.css conventions
- Exact bubble sizing and padding
- How to load marked.js (CDN vs vendored copy)

## Deferred Ideas

None — discussion stayed within phase scope.
