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

## Cross-Milestone Trends

### Process Evolution

| Milestone | Phases | Plans | Key Change |
|-----------|--------|-------|------------|
| v1.0 MVP | 6 | 13 | Established TDD, circuit breaker, structured logging patterns |
| v1.1 Web UI | 3 | 5 | Added frontend (Jinja2+JS), first UI verification gap |

### Cumulative Quality

| Milestone | Tests | LOC | New Dependencies |
|-----------|-------|-----|------------------|
| v1.0 | 226 | 6,830 | FastAPI, httpx, etcd3gw, structlog, pydantic-settings |
| v1.1 | 265 | 7,618 | jinja2 |

### Top Lessons (Verified Across Milestones)

1. Small, focused phases (2-3 plans each) execute faster than large ones
2. TDD catches integration issues early — wiring DI fixtures before new tests prevents cascading failures
