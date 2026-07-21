---
status: partial
phase: 20-chat-configuration
source: [20-01-VERIFICATION.md]
started: 2026-07-21T16:36:00Z
updated: 2026-07-21T16:36:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. System Prompt Toggle Animation
expected: Panel slides open with smooth transition, chevron rotates 180deg, click again to collapse
result: [pending]

### 2. localStorage Persistence
expected: Type "You are a pirate" in system prompt textarea, refresh page — text persists
result: [pending]

### 3. System Prompt in Network Request
expected: POST /v1/chat/completions includes {role: "system"} as first element in messages array
result: [pending]

### 4. Conversation Persistence on Prompt Change
expected: Changing system prompt mid-conversation doesn't clear message history, next send uses new prompt
result: [pending]

### 5. Visual Theme Consistency (CFG-02)
expected: System prompt UI matches dashboard theme in both dark and light modes
result: [pending]

## Summary

total: 5
passed: 0
issues: 0
pending: 5
skipped: 0
blocked: 0

## Gaps
