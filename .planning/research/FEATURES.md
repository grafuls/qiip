# Feature Landscape

**Domain:** LLM Inference Gateway / Proxy (self-hosted, vLLM backends, internal network)
**Researched:** 2026-06-10
**Context:** QUADS LLM Inference Proxy -- routes OpenAI-compatible requests to vLLM nodes on idle GPU servers, using etcd for service discovery. Internal network only for v1.

## Table Stakes

Features users expect from any LLM inference gateway. Missing any of these and the product feels broken or unusable.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **OpenAI-compatible API surface** | Every LLM client SDK speaks OpenAI format. Clients expect `/v1/chat/completions`, `/v1/completions`, `/v1/models`, and health endpoints. Without this, no existing tooling works. | Medium | Must handle both streaming and non-streaming request/response formats. The `/v1/models` endpoint must aggregate models from all registered vLLM nodes. |
| **SSE streaming proxy** | Token-by-token streaming is the default UX for chat completions. Users expect `"stream": true` to work. Without it, clients stare at a spinner for 10-30 seconds. | Medium | Must set `Content-Type: text/event-stream`, `Cache-Control: no-cache`, `X-Accel-Buffering: no`. Must correctly proxy the `[DONE]` sentinel. Buffering anywhere in the chain destroys the experience. httpx `aiter_lines()` or `aiter_bytes()` for pass-through. |
| **Health checking of backends** | vLLM nodes on repurposed lab servers will go down (server reclaimed by QUADS, GPU OOM, container crash). Without active health checks, requests route to dead nodes. | Low | vLLM exposes `/health` returning HTTP 200 when model is loaded. Poll periodically (e.g., every 10-30s). Mark unhealthy after N consecutive failures, re-check at longer intervals. |
| **Automatic retry on failure** | When a vLLM node fails mid-request (or returns 5xx), the client should not have to manually retry. The gateway should transparently re-issue to another healthy node. | Medium | Only retry on server errors (5xx, connection refused, timeout) -- never on 4xx (bad request). Non-streaming retries are straightforward. Streaming retries are harder: once tokens have been sent, you cannot restart transparently. Retry only on connection-phase failures for streaming. |
| **Load balancing** | With multiple vLLM nodes, requests must be distributed. Without load balancing, one node is overloaded while others idle. | Low-Medium | Least-connections is the right default for inference (variable request duration). Round-robin is naive but functional. Random is worse. Weighted variants can account for GPU capability differences. |
| **Service discovery** | Nodes come and go as QUADS provisions/reclaims servers. Hardcoded backend lists break immediately. The gateway must learn about new nodes and forget removed ones dynamically. | Medium | etcd is the chosen registry. Use etcd watch for real-time updates (new node registered, node deregistered). Nodes should register with endpoint URL, model name, and capabilities. |
| **Graceful error responses** | When all backends are down or a request is malformed, the gateway must return proper OpenAI-format error JSON (`{"error": {"message": ..., "type": ..., "code": ...}}`). | Low | Clients using OpenAI SDKs parse these structured errors. Raw 500s or HTML error pages break client code. |
| **Request timeout handling** | LLM inference can take seconds to minutes. The gateway must have configurable timeouts and not hang indefinitely on unresponsive backends. | Low | Set connect timeout (short, ~5s) and read timeout (longer, ~120-300s for large generations). Return 504 Gateway Timeout in OpenAI error format. |

## Differentiators

Features that set the product apart or provide significant operational value. Not strictly required for a working proxy, but high-value additions.

### Tier 1 Differentiators (High Value, Consider for Early Phases)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Circuit breaker per backend** | Prevents cascading failures. When a node starts failing (>50% error rate in sliding window), stop sending it traffic immediately instead of waiting for health checks. Three states: Closed (normal), Open (fast-fail), Half-Open (probe with limited traffic). | Medium | Without this, a dying node that returns errors slowly (not timeout, but 500s) will eat retries and degrade the whole cluster. PyBreaker or a simple custom implementation. |
| **Model-aware routing** | Route requests to the specific vLLM node(s) hosting the requested model. Essential once multiple models are served across the cluster. | Medium | etcd registration should include model name. Router matches request's `model` field to nodes serving that model. Return 404-style error if no node serves the requested model. |
| **Connection draining on node removal** | When a vLLM node is being reclaimed by QUADS, finish in-flight requests before removing it from the pool. Prevents mid-generation failures. | Medium | Requires a "draining" state: stop routing new requests, wait for active connections to complete (with timeout), then remove. Needs coordination with etcd deregistration. |
| **Request/response logging** | Structured logs of every proxied request (model, latency, tokens, status code, backend used). Essential for debugging, capacity planning, and understanding usage patterns. | Low-Medium | Log metadata only by default (no prompt/response content for privacy). Use structured logging (JSON). Include: timestamp, model, backend_node, latency_ms, status_code, stream (bool), tokens_used (if available from vLLM response). |
| **Prometheus metrics** | Expose `/metrics` endpoint with request count, latency histograms, error rates, per-backend health, active connections. Powers Grafana dashboards and alerting. | Medium | Key metrics: `requests_total` (by model, status, backend), `request_duration_seconds` (histogram), `active_connections` (gauge, per backend -- feeds least-connections), `backend_health` (gauge), `backend_pool_size` (gauge). Use prometheus_client library. |

### Tier 2 Differentiators (Valuable, Consider for Later Phases)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Token usage tracking** | Track input/output tokens per request. vLLM returns usage in the response body. Aggregate for capacity planning and cost attribution (GPU-hours). | Low-Medium | vLLM includes `usage` object in completions responses. Parse and aggregate. For streaming, usage appears in the final SSE frame before `[DONE]`. Store in-memory counters or emit to metrics. |
| **Rate limiting** | Prevent a single client/team from monopolizing GPU capacity. Token-based rate limiting (tokens-per-minute) is more appropriate than request-count limiting for LLM workloads. | Medium | Not needed for v1 (internal, small user base), but becomes important as usage grows. Can be per-API-key, per-IP, or per-header. Token-based limiting requires parsing the response to count tokens used. |
| **Request queuing with backpressure** | When all backends are at capacity, queue requests instead of immediately failing. Return 429 when queue is full. | High | Adds complexity (queue management, ordering, timeouts, memory pressure). For v1, failing fast with a clear error is simpler and more predictable. Consider when GPU utilization is consistently high. |
| **Admin API** | Endpoints to inspect gateway state: list backends, their health status, active connections, manually add/remove backends. | Low-Medium | Useful for operations. Could be as simple as `GET /admin/backends` returning the current backend pool state. Separate from the OpenAI-compatible API surface. |
| **Configuration hot-reload** | Change routing rules, timeouts, or other config without restarting the gateway. | Medium | Watch a config file or etcd keys for changes. Reload without dropping connections. Reduces operational friction. |
| **Weighted load balancing** | Assign weights to backends based on GPU capability (e.g., A100 vs V100). Route proportionally more traffic to faster nodes. | Low | Extension of least-connections. Weights from etcd metadata. Simple multiplier on the connection count comparison. |
| **Multi-model aggregation for /v1/models** | Aggregate model listings from all vLLM backends into a single coherent response, deduplicating models served by multiple nodes. | Low | Query each backend's `/v1/models` or use etcd model metadata. Merge and deduplicate. Cache with short TTL. |

### Tier 3 Differentiators (Future / Nice-to-Have)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Semantic caching** | Cache responses for semantically similar prompts. Can reduce GPU load significantly for repeated queries. | High | Requires embedding computation, vector similarity search, cache invalidation strategy. Overkill for v1. Consider if usage patterns show high prompt repetition. |
| **A/B testing / canary routing** | Route a percentage of traffic to a new model version for comparison. | Medium | Weighted routing to different model versions. Requires tagging responses with variant info. Useful for model evaluation. |
| **Virtual API keys** | Issue per-team/per-project API keys that map to budgets and rate limits. | Medium | Requires key storage (DB or etcd), validation middleware, per-key metrics. Not needed on internal network v1 but essential for multi-team usage. |
| **Cost attribution** | Track GPU-hours consumed per team/project. Map token usage to compute cost. | Medium | Requires virtual keys (or another identity mechanism) + token tracking + cost model. Valuable for chargeback in shared infrastructure. |
| **Guardrails (input/output validation)** | Block prompt injection, PII leakage, or enforce output format compliance. | High | Requires content analysis (regex or ML-based). Adds latency. Important for external-facing deployments but overkill for internal v1. |
| **OpenTelemetry tracing** | Distributed tracing across gateway and backends. Trace a request from client through gateway to specific vLLM node. | Medium | Propagate trace context headers. Export spans to Jaeger/Tempo. More useful in complex multi-service architectures. |

## Anti-Features

Features to deliberately NOT build. These add complexity without proportional value for this project's context.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| **Multi-provider translation** | This is a single-backend-type proxy (vLLM only). Translating between OpenAI/Anthropic/Gemini formats is what LiteLLM and OpenRouter do. We proxy OpenAI-compatible requests to OpenAI-compatible vLLM backends. No translation needed. | Pass through requests as-is. vLLM already speaks OpenAI format. |
| **Built-in web UI / dashboard** | Adds frontend complexity (React/Vue build, serving static files, auth for UI). Grafana + Prometheus does this better with zero custom code. | Expose Prometheus metrics. Use Grafana for dashboards. |
| **User/team management** | Building auth, RBAC, team hierarchies, and user management is a product in itself. Internal network v1 has no auth requirement. | Defer to v2. If needed, use a reverse proxy (NGINX) or API gateway in front for auth. |
| **Model hosting / serving** | The gateway should not manage vLLM containers, download models, or handle GPU allocation. That is the control plane's job (future phase). | Gateway discovers nodes via etcd. Control plane (separate service) manages provisioning. |
| **Database for state** | Adding PostgreSQL or Redis as a dependency for a proxy increases operational complexity. The gateway should be stateless (or near-stateless with etcd). | Use etcd for service discovery (already required). Use in-memory state for connection counts and circuit breaker state. Metrics go to Prometheus. |
| **Plugin / extension system** | Premature abstraction. The codebase is small enough that modifications are direct code changes. A plugin system adds indirection without users to justify it. | Use clean module boundaries (SOLID). Add extension points when a genuine need emerges (Open/Closed Principle). |
| **Geographic / multi-region routing** | This is an internal lab network in a single data center. Multi-region routing adds massive complexity for zero value. | Single deployment. If multi-region is needed later, deploy separate gateway instances per region. |
| **Prompt caching / KV cache routing** | KV cache-aware routing (routing to the node that already has this prompt's KV cache) is a vLLM Router feature built in Rust. Reimplementing this in Python would be slower and less correct. | If KV cache routing is needed, use vLLM Router or contribute to it. Focus the Python gateway on service discovery and reliability. |
| **Billing / payments** | Internal infrastructure tool. No billing needed. | N/A |

## Feature Dependencies

```
Service Discovery (etcd) ──> Health Checking (needs to know which nodes exist)
                         ──> Model-Aware Routing (needs model metadata from etcd)
                         ──> Connection Draining (needs to watch for deregistration)

Health Checking ──> Load Balancing (only route to healthy nodes)
               ──> Circuit Breaker (feeds failure rate data)

Load Balancing ──> Retry on Failure (retry goes to a different node via LB)

OpenAI API Surface ──> SSE Streaming (streaming is part of the API contract)
                   ──> Graceful Error Responses (errors must match OpenAI format)

Prometheus Metrics ──> Token Usage Tracking (tokens feed into metrics)
                   ──> Rate Limiting (metrics inform rate limit tuning)

Virtual API Keys ──> Rate Limiting (per-key limits)
                 ──> Cost Attribution (per-key tracking)
                 ──> Token Usage Tracking (per-key usage)
```

## MVP Recommendation

**Prioritize (Phase 1 -- Core Gateway):**
1. OpenAI-compatible API surface (`/v1/chat/completions`, `/v1/completions`, `/v1/models`, `/health`)
2. SSE streaming proxy (token-by-token pass-through)
3. etcd-based service discovery with watch
4. Health checking of vLLM backends
5. Least-connections load balancing
6. Automatic retry on backend failure (non-streaming and pre-first-token streaming)
7. Graceful OpenAI-format error responses
8. Request timeout handling

**Prioritize (Phase 2 -- Operational Maturity):**
1. Circuit breaker per backend
2. Model-aware routing
3. Prometheus metrics endpoint
4. Structured request/response logging
5. Connection draining on node removal
6. Admin API for inspecting gateway state

**Defer:**
- Rate limiting: Not needed until multi-team usage (v2+ with auth)
- Token usage tracking: Useful but not blocking; add alongside metrics
- Request queuing: Prefer fail-fast over complexity for v1
- Virtual API keys: Requires auth, which is out of scope for v1
- Semantic caching: High complexity, unproven value for this use case
- Guardrails: Internal network, trusted users

## Sources

- [LiteLLM Documentation](https://docs.litellm.ai/docs/simple_proxy) -- OpenAI-compatible proxy features, load balancing, virtual keys, cost tracking
- [Portkey AI Gateway](https://portkey.ai/features/ai-gateway) -- Guardrails, observability, rate limiting patterns
- [Bifrost LLM Gateway](https://github.com/maximhq/bifrost) -- High-performance gateway architecture, semantic caching, zero-config design
- [vLLM Router Blog Post](https://vllm.ai/blog/2025-12-13-vllm-router-release) -- vLLM-specific load balancing (consistent hashing, power-of-two), prefill/decode disaggregation, Prometheus metrics
- [OpenRouter](https://openrouter.ai) -- Managed gateway model, auto-failover, provider marketplace
- [LiteLLM vs OpenRouter Comparison](https://www.merge.dev/blog/litellm-vs-openrouter) -- Feature comparison, latency overhead, cost tradeoffs
- [Portkey vs LiteLLM vs OpenRouter 2026](https://www.pkgpulse.com/guides/portkey-vs-litellm-vs-openrouter-llm-gateway-2026) -- Gateway comparison, feature matrix
- [LLM Gateway Architecture 2026](https://www.digitalapplied.com/blog/llm-gateway-architecture-2026-engineering-reference) -- Five-layer architecture, routing strategies
- [Retries, Fallbacks, and Circuit Breakers in LLM Apps](https://www.getmaxim.ai/articles/retries-fallbacks-and-circuit-breakers-in-llm-apps-a-production-guide/) -- Circuit breaker states, retry semantics, failover chains
- [SSE Streaming for LLM at Scale](https://medium.com/@daniakabani/how-we-used-sse-to-stream-llm-responses-at-scale-fa0d30a6773f) -- Backpressure, connection limits, proxy configuration
- [LLM Audit Logging](https://abliteration.ai/llm-audit-logging) -- Audit trail patterns, structured logging schemas
- [vLLM Router GitHub](https://github.com/vllm-project/router) -- Rust-based router, KV cache-aware routing, service discovery
- [Self-Hosted LLM Gateway Guide](https://lyceum.technology/magazine/llm-api-gateway-self-hosted-guide/) -- Architecture layers, minimal viable gateway features
- [LLM Cost Tracking with Prometheus](https://agentgateway.dev/docs/kubernetes/main/llm/cost-tracking/) -- Token-based metrics, PromQL cost queries
