---
phase: 20-chat-configuration
plan: 01
subsystem: chat-ui
tags: [system-prompt, localStorage, collapsible-panel, theming]
dependency_graph:
  requires: []
  provides: [system-prompt-configuration, theme-consistent-chat-panel]
  affects: [chat.html, chat.js, chat.css, test_chat.py]
tech_stack:
  added: []
  patterns: [collapsible-panel-via-max-height, localStorage-persistence, payload-copy-on-send]
key_files:
  created: []
  modified:
    - inference_proxy/templates/chat.html
    - inference_proxy/static/js/chat.js
    - inference_proxy/static/css/chat.css
    - tests/api/test_chat.py
decisions:
  - "System prompt prepended via messages.slice() + unshift at send time -- never mutates conversation array"
  - "CSS-only chevron (border triangle) -- no icon library needed"
  - "All new styles use var(--*) tokens only -- zero hardcoded colors for themed elements"
metrics:
  duration: 191s
  completed: 2026-07-21
  tasks_completed: 2
  tasks_total: 2
  tests_added: 7
  tests_total: 451
---

# Phase 20 Plan 01: System Prompt Configuration Summary

System prompt collapsible panel with toggle button, localStorage persistence, and payload injection into chat completions requests using theme variables only.

## Task Completion

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add system prompt HTML, CSS, and test assertions | ed9d486 | chat.html, chat.css, test_chat.py |
| 2 | Wire toggle behavior, localStorage persistence, message injection | bd87e47 | chat.js |

## Changes Made

### Task 1: HTML + CSS + Tests
- Added toggle button with `aria-expanded`, `aria-controls` inside `.model-selector-bar`
- Added collapsible panel div between model selector and message area
- Added textarea with `aria-label`, placeholder, 3-row default
- CSS: toggle button, chevron rotation, panel max-height transition, textarea matching `#chat-input` styles
- Responsive: panel padding reduces at 768px breakpoint
- Reduced motion: transitions disabled for panel, chevron, toggle
- 7 new test methods in `TestChatSystemPrompt` class

### Task 2: JavaScript Wiring
- `systemPromptTextarea` and `systemPromptToggle` variables added to declaration block
- DOMContentLoaded: bind elements, restore from localStorage, attach click/input listeners
- Toggle click: flip `aria-expanded`, toggle `expanded` class on panel
- Input listener: save to `localStorage.setItem("systemPrompt", ...)`
- `streamResponse()`: build `payloadMessages` via `messages.slice()`, conditionally `unshift` system message -- original `messages` array never mutated

## Deviations from Plan

None -- plan executed exactly as written.

## Verification

- `uv run pytest tests/api/test_chat.py -x -v` -- 23 passed (7 new)
- `uv run pytest` -- 451 passed, 0 failures
- Manual verification: toggle, persistence, message injection, theme consistency (deferred to human-verify)

## Self-Check: PASSED

- All 4 modified files exist on disk
- Commit ed9d486 found in git log
- Commit bd87e47 found in git log
