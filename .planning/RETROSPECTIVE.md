# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v1.1 — Web UI

**Shipped:** 2026-07-01
**Phases:** 3 | **Plans:** 5

### What Was Built
- Thread-safe request metrics (per-node, per-model, total) with enriched admin API
- Jinja2 operations dashboard with node fleet table and Simple.css styling
- JS polling auto-refresh with configurable interval and per-node request counts

### What Worked
- Jinja2 + vanilla JS kept the stack simple — no build step, no Node.js toolchain
- TDD pattern from v1.0 carried forward cleanly (265 tests, all green)
- Small milestone scope (3 phases, 3 days) kept focus tight
- Existing admin API provided clean data layer for dashboard to consume

### What Was Inefficient
- Phase 08 visual verification required manual human check — automated tests covered structure but not visual rendering
- gsd-sdk `milestone.complete` extracted deviations as accomplishments — needed manual fix

### Patterns Established
- Jinja2 template + static CSS/JS pattern for server-rendered UI pages
- `DashboardSettings` sub-model pattern for feature-specific config
- Inline `<script>` for injecting server config into client JS (poll interval)

### Key Lessons
1. Visual verification gaps are unavoidable for UI work — budget for them explicitly in the phase plan
2. In-memory counters are fine for v1 ops dashboards — don't over-engineer persistence before there's a need

---

## Milestone: v1.7 — HuggingFace Integration

**Shipped:** 2026-07-29
**Phases:** 3 | **Plans:** 5

### What Was Built
- HuggingFace settings with SecretStr token and NFS cache dir configuration
- ModelCatalogService scanning HF cache with admin API endpoint
- DownloadService with thread-safe status tracking and semaphore-gated background downloads
- Dashboard download column with catalog cross-reference, optimistic UI, lazy polling

### What Worked
- llmfit model names being HF repo IDs eliminated mapping complexity — zero transformation needed
- Independent try/catch per fetch (catalog, downloads, recommendations) prevented cascade failures
- Optimistic UI pattern (immediate badge swap on download click) gave instant feedback without waiting for server
- 2-day execution for 3 phases — tight scope and clear requirements kept velocity high

### What Was Inefficient
- Phase 32 DASH requirements were left unchecked in REQUIREMENTS.md traceability despite code being complete — caught at milestone close
- XSS vectors found in code review after Phase 32 execution — security review should run before marking phase complete

### Patterns Established
- asyncio.to_thread wrapper for sync HF library calls (same pattern as etcd3gw)
- Module-level cache Set shared between initial load and poll updater for download state
- Lazy polling with single-timer guard — starts on user action, auto-stops when idle

### Key Lessons
1. When reusing a sync library in an async app, the thread pool pattern (asyncio.to_thread + ThreadPoolExecutor) is now proven across two subsystems (etcd, HF)
2. Dashboard features that poll should use lazy polling (start on trigger, stop when idle) rather than always-on intervals
3. Security review needs to run as part of phase execution, not as a post-hoc catch-up

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Phases | Plans | Key Change |
|-----------|--------|-------|------------|
| v1.0 MVP | 6 | 13 | Established TDD, circuit breaker, structured logging patterns |
| v1.1 Web UI | 3 | 5 | Added frontend (Jinja2+JS), first UI verification gap |
| v1.7 HuggingFace | 3 | 5 | HF downloads integrated into dashboard, 2-day execution |

### Cumulative Quality

| Milestone | Tests | LOC | New Dependencies |
|-----------|-------|-----|------------------|
| v1.0 | 226 | 6,830 | FastAPI, httpx, etcd3gw, structlog, pydantic-settings |
| v1.1 | 265 | 7,618 | jinja2 |
| v1.7 | 568 | 16,237 | huggingface-hub |

### Top Lessons (Verified Across Milestones)

1. Small, focused phases (2-3 plans each) execute faster than large ones
2. TDD catches integration issues early — wiring DI fixtures before new tests prevents cascading failures
