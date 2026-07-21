# Phase 20: Chat Configuration - Pattern Map

**Mapped:** 2026-07-21
**Files analyzed:** 4 (3 modified, 1 extended with new tests)
**Analogs found:** 4 / 4

## File Classification

| Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---------------|------|-----------|----------------|---------------|
| `inference_proxy/templates/chat.html` | component | request-response | self (existing file) | exact |
| `inference_proxy/static/js/chat.js` | utility | event-driven | self (existing file) | exact |
| `inference_proxy/static/css/chat.css` | config | -- | self (existing file) | exact |
| `tests/api/test_chat.py` | test | request-response | self (existing file) | exact |

All four files are modifications to existing files. Each file is its own analog -- the patterns to follow are already in the file being edited.

## Pattern Assignments

### `inference_proxy/templates/chat.html` (component, modification)

**Analog:** self -- lines 30-34 (model-selector-bar) and lines 36-43 (message-area)

**Toggle button insertion point** -- add inside `.model-selector-bar` after `#model-select` (line 33):
```html
<div class="model-selector-bar">
    <select id="model-select">
        <option value="">Loading models...</option>
    </select>
    <!-- INSERT toggle button here, before closing div -->
</div>
```

**Panel insertion point** -- add between `.model-selector-bar` (line 34) and `.message-area` (line 36):
```html
        </div>
        <!-- model-selector-bar ends above -->

        <!-- INSERT collapsible panel div here -->

        <div class="message-area" id="message-area" role="log" aria-live="polite">
```

**Existing pattern: inline script for localStorage** (line 12):
```html
<script>var __t=localStorage.getItem('theme')||'dark';document.documentElement.dataset.theme=__t;</script>
```
System prompt localStorage restore should happen in `chat.js` DOMContentLoaded, not as an inline script, since it depends on DOM elements.

---

### `inference_proxy/static/js/chat.js` (utility, event-driven, modification)

**Analog:** self

**Variable declaration pattern** (lines 17-24) -- add `systemPromptTextarea` and `systemPromptToggle` to this block:
```javascript
var messages = [];
var messageArea;
var messageAreaInner;
var emptyState;
var chatInput;
var sendBtn;
var modelSelect;
var streaming = false;
```

**DOMContentLoaded element binding pattern** (lines 191-198) -- add system prompt element binding here:
```javascript
document.addEventListener("DOMContentLoaded", function () {
  messageArea = document.getElementById("message-area");
  messageAreaInner = messageArea.querySelector(".message-area-inner");
  emptyState = document.getElementById("empty-state");
  chatInput = document.getElementById("chat-input");
  sendBtn = document.getElementById("send-btn");
  modelSelect = document.getElementById("model-select");
  // ADD: system prompt element binding + localStorage restore + event listeners
```

**Event listener pattern** (lines 201-214) -- follow existing click/keydown/input pattern:
```javascript
  sendBtn.addEventListener("click", sendMessage);

  chatInput.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  chatInput.addEventListener("input", function () {
    this.style.height = "auto";
    this.style.height = this.scrollHeight + "px";
  });
```

**Fetch body construction** (lines 66-70) -- modify messages to prepend system prompt:
```javascript
      body: JSON.stringify({
        model: modelSelect.value,
        messages: messages,
        stream: true,
      }),
```
Replace `messages` with a copy that has system prompt prepended (if non-empty). Do NOT mutate the `messages` array.

---

### `inference_proxy/static/css/chat.css` (config, modification)

**Analog:** self

**Surface/border pattern** -- reuse from `.model-selector-bar` (lines 34-41):
```css
.model-selector-bar {
  height: 48px;
  padding: 0 32px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
}
```
System prompt panel uses identical `background: var(--surface)` and `border-bottom: 1px solid var(--border)`.

**Textarea styling pattern** -- reuse from `#chat-input` (lines 145-168):
```css
#chat-input {
  flex: 1;
  min-height: 40px;
  max-height: 200px;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius);
  padding: 0.5rem 0.75rem;
  font-family: 'Open Sans', sans-serif;
  font-size: 0.875rem;
  line-height: 1.5;
  color: var(--text);
  background: var(--bg);
  resize: none;
  outline: none;
}

#chat-input:focus {
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.15);
}

#chat-input::placeholder {
  color: var(--disabled);
}
```
System prompt textarea copies this pattern exactly (except `resize: vertical` instead of `resize: none`).

**Transition pattern** -- reuse from `#send-btn` and `.nav-link` (lines 182, 24):
```css
transition: background 0.15s;
transition: color 0.15s, background 0.15s;
```

**Responsive breakpoint pattern** (lines 229-245):
```css
@media (max-width: 768px) {
  .model-selector-bar {
    padding: 0 16px;
  }
  .input-bar {
    padding: 16px;
  }
}
```
System prompt panel padding should also reduce to 16px at this breakpoint.

**Reduced motion pattern** (lines 248-260):
```css
@media (prefers-reduced-motion: reduce) {
  .streaming-cursor::after {
    animation: none;
  }
  #send-btn {
    transition: none;
  }
  .nav-link {
    transition: none;
  }
}
```
Add system prompt panel and chevron transitions to this block.

---

### `tests/api/test_chat.py` (test, modification)

**Analog:** self

**Test class pattern** (lines 37-91, `TestChatTemplate`):
```python
class TestChatTemplate:
    """Chat HTML includes expected assets and elements (CHAT-01, CHAT-02, CHAT-03)."""

    def test_contains_model_select(self, client: TestClient) -> None:
        """HTML contains select element with id='model-select' (CHAT-03)."""
        response = client.get("/chat")
        assert 'id="model-select"' in response.text
```
New tests follow identical pattern: `client.get("/chat")` then `assert 'string' in response.text`.

**Fixture pattern** -- `client` fixture from `tests/conftest.py` (line 153):
```python
@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Return a TestClient bound to the test app."""
    return TestClient(app)
```
No new fixtures needed. Existing `client` fixture provides everything.

**Import pattern** (lines 1-13):
```python
from __future__ import annotations

from fastapi.testclient import TestClient
```

---

## Shared Patterns

### localStorage Persistence
**Source:** `inference_proxy/templates/chat.html` line 12, `inference_proxy/static/js/chat.js` DOMContentLoaded
**Apply to:** System prompt value persistence in `chat.js`
```javascript
// Read: localStorage.getItem('theme')
// Write: localStorage.setItem('theme', t)
// System prompt follows same key pattern: 'systemPrompt'
```

### CSS Custom Properties for Theming
**Source:** `inference_proxy/static/css/dashboard.css` lines 1-43
**Apply to:** All new CSS in `chat.css`
```css
/* Light mode (default) */
--surface: #FFFFFF;
--bg: #F3F4F6;
--text: #111827;
--text-light: #6B7280;
--border: #E5E7EB;
--border-strong: #D1D5DB;
--disabled: #9CA3AF;
--radius: 0.5rem;

/* Dark mode auto-applied via [data-theme="dark"] */
/* No new [data-theme="dark"] selectors needed if only var(--*) tokens are used */
```

### Test Assertion Pattern
**Source:** `tests/api/test_chat.py` lines 37-91
**Apply to:** New test methods for system prompt elements
```python
def test_contains_THING(self, client: TestClient) -> None:
    """HTML contains THING."""
    response = client.get("/chat")
    assert 'expected-string' in response.text
```

## No Analog Found

None. All files are modifications to existing files with established patterns.

## Metadata

**Analog search scope:** `inference_proxy/templates/`, `inference_proxy/static/`, `tests/api/`
**Files scanned:** 5 (chat.html, chat.js, chat.css, dashboard.css, test_chat.py)
**Pattern extraction date:** 2026-07-21
