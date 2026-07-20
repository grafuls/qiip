# Milestones

## v1.3 QUADS Integration (Shipped: 2026-07-20)

**Phases completed:** 4 phases, 5 plans, 2 tasks

**Key accomplishments:**

- HTML template (dashboard.html):

---

## v1.2 Node Setup — SHIPPED 2026-07-08

**Phases:** 5 | **Plans:** 9 | **Tests:** 338 | **LOC:** 9,635 (Python + HTML/CSS/JS)
**Timeline:** 2026-07-01 to 2026-07-08 (7 days)
**Commits:** 16 feat commits

### Key Accomplishments

1. Hardened setup.sh and start-vllm.sh for idempotent, fail-fast automated execution
2. SSH provisioning via asyncssh — remote setup, container build, GPU auto-detection, health poll, etcd registration
3. Pre-flight validation (SSH, GPU, disk), state machine tracking (16-step ProvisioningStep), health checker coordination
4. Teardown lifecycle with graceful drain and force modes, etcd deregistration
5. Admin REST API — POST /admin/nodes/setup, GET /admin/provisioning/tasks, DELETE /admin/nodes/{id}
6. Dashboard operations UI — setup form, teardown buttons, provisioning tasks panel with step badges

### Known Deferred Items

- 2 verification gaps from v1.0 still open (Phases 3, 6 — require live vLLM/etcd)

**Archive:** [v1.2-ROADMAP.md](milestones/v1.2-ROADMAP.md) | [v1.2-REQUIREMENTS.md](milestones/v1.2-REQUIREMENTS.md)

---

## v1.1 Web UI — SHIPPED 2026-07-01

**Phases:** 3 | **Plans:** 5 | **Tests:** 265 | **LOC:** 7,618 (Python + HTML/CSS/JS)
**Timeline:** 2026-06-29 to 2026-07-01 (3 days)
**Commits:** 9 code commits (5 feat, 2 fix, 1 test)

### Key Accomplishments

1. Thread-safe request metrics tracking (per-node, per-model, total) with enriched admin API
2. Jinja2-rendered operations dashboard with node fleet table and Simple.css styling
3. Per-node request count display with JS polling auto-refresh at configurable interval
4. Badge-based visual distinction for node health and circuit breaker states

### Known Deferred Items

- 1 verification gap from v1.0 still open (Phases 3, 6 — require live vLLM/etcd)

**Archive:** [v1.1-ROADMAP.md](milestones/v1.1-ROADMAP.md) | [v1.1-REQUIREMENTS.md](milestones/v1.1-REQUIREMENTS.md)

---

## v1.0 MVP — SHIPPED 2026-06-25

**Phases:** 6 | **Plans:** 13 | **Tests:** 226 | **LOC:** 6,830 Python
**Timeline:** 2026-06-02 to 2026-06-25 (23 days)
**Commits:** 132 (20 feat, 18 test)

### Key Accomplishments

1. OpenAI-compatible API proxy with chat/text completions, model listing, and health endpoint
2. etcd-based service discovery with real-time watch updates and reconnection
3. SSE streaming for token-by-token responses with proper `[DONE]` termination
4. Least-connections load balancing with model-aware routing and drain coordination
5. Resilience layer: health checks, retry with failover, circuit breaker, graceful shutdown
6. Structured request logging and admin node status API for operational visibility

### Known Deferred Items

- 2 verification gaps requiring live vLLM/etcd testing (Phases 3, 6)

**Archive:** [v1.0-ROADMAP.md](milestones/v1.0-ROADMAP.md) | [v1.0-REQUIREMENTS.md](milestones/v1.0-REQUIREMENTS.md)
