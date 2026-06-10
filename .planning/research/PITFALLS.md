# Domain Pitfalls

**Domain:** LLM Inference Gateway (OpenAI-compatible proxy to vLLM backends)
**Researched:** 2026-06-10
**Confidence:** HIGH (verified across multiple production reports, upstream bug trackers, and official docs)

---

## Critical Pitfalls

Mistakes that cause rewrites, production outages, or architectural dead-ends.

### Pitfall 1: Response Buffering Silently Destroys SSE Streaming

**What goes wrong:** The proxy accumulates the entire upstream vLLM response in memory before forwarding any bytes to the client. Streaming degrades to batch behavior -- the user sees nothing for seconds, then gets a burst of text. The proxy appears to "work" in testing with short responses but fails silently under real load with longer generations.

**Why it happens:** Three independent layers conspire:
1. **httpx default behavior:** If you read the response body without using `client.stream()`, httpx downloads the entire response before returning.
2. **FastAPI/Starlette StreamingResponse misuse:** Returning a `StreamingResponse` that wraps a fully-buffered body instead of an async generator that yields chunks as they arrive from upstream.
3. **Downstream NGINX (future phase):** NGINX defaults to `proxy_buffering on` and `proxy_http_version 1.0`. HTTP/1.0 does not support chunked transfer, so NGINX waits for the full response. Even with HTTP/1.1, buffering collects chunks before forwarding.

**Consequences:**
- Time-to-first-token (TTFT) jumps from milliseconds to the full generation time (potentially 30-60 seconds).
- Users perceive the system as 40% slower even when total generation time is identical.
- Long generations hit proxy read timeouts and return 504 before completing.
- Memory spikes under concurrent requests as entire responses are held in proxy memory.

**Warning signs:**
- TTFT in the proxy is significantly higher than TTFT measured directly against vLLM.
- Memory usage on the proxy grows linearly with concurrent streaming requests.
- Clients receive `Content-Type: application/json` instead of `text/event-stream`.

**Prevention:**
- Use `httpx.AsyncClient.stream()` with an async generator that yields chunks immediately.
- Set response `Content-Type` to `text/event-stream; charset=utf-8` for streaming requests.
- Add `X-Accel-Buffering: no` and `Cache-Control: no-cache` response headers to prevent downstream buffering.
- Test TTFT explicitly: measure time from request to first SSE chunk, not just total response time.

**Detection:** Add a TTFT metric (time from request received to first chunk forwarded). If TTFT approaches total generation time, buffering is occurring somewhere in the chain.

**Phase:** Must be correct from the initial streaming implementation. Retrofitting is a rewrite.

---

### Pitfall 2: Connection/Resource Leaks from Unclosed Streaming Responses

**What goes wrong:** When proxying a streaming response from vLLM via httpx, the upstream HTTP connection is held open for the duration of the stream. If the client disconnects mid-stream (closes browser tab, network drop, timeout), the proxy must detect the disconnect and close the upstream connection. Failing to do so leaks connections in httpx's pool until the pool is exhausted.

**Why it happens:**
- httpx streaming responses require explicit `aclose()` or use of `async with client.stream(...)`. If neither is used, the connection stays open in the pool.
- FastAPI's `StreamingResponse` does not automatically propagate client disconnects upstream. The async generator continues running, consuming the vLLM response into the void.
- Creating a new `httpx.AsyncClient` per request (instead of reusing one) causes connection pool thrashing and prevents keepalive reuse.

**Consequences:**
- httpx connection pool fills up (default: 100 max connections, 20 keepalive).
- New requests get `PoolTimeout` exceptions.
- The proxy appears to hang under moderate load -- requests queue waiting for pool slots.
- Memory grows as abandoned response bodies accumulate.

**Warning signs:**
- `PoolTimeout` errors appearing in logs after sustained traffic.
- Proxy handles fewer concurrent requests than expected.
- Connection count to vLLM nodes grows monotonically (never decreases).

**Prevention:**
- Always use `async with client.stream(...)` context manager for upstream requests.
- Use a Starlette `BackgroundTask(response.aclose)` to ensure cleanup when the `StreamingResponse` completes or the client disconnects.
- Check `request.is_disconnected()` periodically inside the streaming generator and break out if true.
- Create a single `httpx.AsyncClient` instance (app-scoped, not request-scoped) and tune pool limits: `httpx.Limits(max_connections=200, max_keepalive_connections=40)`.
- Monitor active connections with a gauge metric.

**Detection:** Instrument connection pool utilization. Alert when pool usage exceeds 80% sustained.

**Phase:** Must be correct in the initial proxy implementation. This is structural -- the async generator pattern and client lifecycle must be right from the start.

---

### Pitfall 3: Health Checks That Lie -- vLLM's /health Endpoint Only Checks Process Liveness

**What goes wrong:** The gateway marks a vLLM node as healthy because its `/health` endpoint returns 200, but the node cannot actually serve inference. Requests routed to this node fail or hang.

**Why it happens:** vLLM's `/health` endpoint checks a single boolean (`engine_dead`). It does NOT verify:
- GPU memory is accessible (page faults, illegal memory access leave the process alive but inference broken).
- The model is fully loaded (during startup, `/health` may return 200 before the model weights are in GPU memory).
- KV cache is allocatable (OOM conditions during inference, not at startup).
- CUDA graphs are functional (CUDA errors in `graph.replay()` crash inference but not the process).

This is a documented gap -- vLLM issue #36960 proposes a `/health/ready` endpoint that performs a GPU forward pass, but it is not yet in stable releases.

**Consequences:**
- The gateway routes traffic to nodes that cannot generate tokens.
- Users get 500 errors or infinite hangs from nodes that appear healthy.
- Retry logic sends the request to another broken node in the same failure state.
- Silent GPU failures go undetected for the lifetime of the node.

**Warning signs:**
- Nodes pass health checks but produce 500 errors on inference requests.
- Inference latency on specific nodes degrades dramatically while health checks continue passing.
- `dmesg` on the host shows GPU reset or PCIe errors.

**Prevention:**
- Implement active health probes that go beyond `/health`. Send a lightweight inference request (e.g., a 1-token completion) to verify end-to-end GPU functionality.
- Separate liveness (is the process alive?) from readiness (can it serve inference?). Only route traffic to nodes that pass readiness.
- Track per-node error rates. If a node's error rate exceeds a threshold (e.g., 3 consecutive failures), mark it unhealthy regardless of what `/health` says.
- Include a startup grace period -- do not route traffic to a newly registered node until it passes a readiness probe.

**Detection:** Monitor per-node error rate and latency separately. A healthy node with high error rate or extreme latency is a lying health check.

**Phase:** Health checking design in the initial implementation. The error-rate-based circuit breaker can be a fast-follow, but the readiness probe concept must be in the architecture from day one.

---

### Pitfall 4: Least-Connections Load Balancing Treats Unequal Requests as Equal

**What goes wrong:** The load balancer sends a new request to the node with the fewest active connections, but that node is saturated because its one active connection is generating a 4,000-token response that fully utilizes the GPU. The new request experiences severe latency degradation.

**Why it happens:** LLM inference fundamentally breaks the assumption behind least-connections balancing -- that all connections cost roughly the same. In practice:
- A short classification request (50 output tokens) and a long essay (4,000 output tokens) consume vastly different GPU time and memory.
- The prefill phase (prompt processing) is compute-bound; the decode phase (token generation) is memory-bound. A node in decode phase with a large KV cache has very different capacity than one in prefill.
- GPU utilization metrics are misleading -- a GPU can report 95% utilization with room for dozens more small requests, or report 60% while being memory-bottlenecked.

**Consequences:**
- Severe tail latency (P99) because unlucky requests land on saturated nodes.
- Uneven GPU utilization across the cluster.
- Users experience wildly inconsistent response times.

**Warning signs:**
- High variance in per-request latency (P99/P50 ratio > 5x).
- Some nodes consistently have higher queue depth than others.
- GPU memory utilization varies dramatically across nodes.

**Prevention:**
- For v1, least-connections is a reasonable starting point -- it is better than round-robin and straightforward to implement. However, the load balancer interface must be designed for extensibility (Strategy pattern) so it can be replaced without modifying the routing logic.
- Track and expose per-node metrics: active connections, recent error rate, average latency. These inform a future upgrade to weighted or queue-depth-aware balancing.
- Consider adding request-level weighting as a v2 enhancement: estimate request cost from `max_tokens` parameter and factor it into routing.

**Detection:** Monitor P99/P50 latency ratio across nodes. A ratio above 5x suggests the balancer is making poor decisions.

**Phase:** Least-connections is acceptable for MVP. Design the load balancer as a pluggable strategy from the start so it can be replaced in a later phase. Do NOT hardwire the algorithm into the routing path.

---

### Pitfall 5: Retry Logic That Silently Duplicates Work or Amplifies Failures

**What goes wrong:** When a request to a vLLM node fails (timeout, 500, connection reset), the gateway retries on another node. This sounds simple but has multiple failure modes:

1. **Retry during streaming:** The first node sent partial SSE chunks before failing. The client has already received partial output. Retrying on another node generates a completely different response from the beginning, but the client sees it appended to the partial output -- producing garbled results.

2. **Retry storm under load:** When a node becomes slow (not dead), requests pile up and timeout. Each timeout triggers a retry to other nodes, doubling the load on the remaining healthy nodes. This cascading effect can take down the entire cluster.

3. **Retry on non-idempotent operations:** If the upstream vLLM call triggers side effects (tool calls, function calling), retrying produces duplicate side effects.

**Why it happens:**
- Teams implement retry logic without distinguishing between "pre-stream" failures (connection refused, immediate 500) and "mid-stream" failures (connection dropped after partial response).
- No retry budget limits how many retries the system generates in aggregate.
- Roughly 40% of cascading failures in distributed systems trace back to retry logic, and LLM workloads are at the worst end because every retry replays a multi-thousand-token request.

**Consequences:**
- Garbled responses from mid-stream retry.
- Cascading failure from retry amplification.
- Wasted GPU compute (each retry costs the same as the original request).
- Potential duplicate side effects from function-calling requests.

**Warning signs:**
- Total request volume across vLLM nodes exceeds client request volume by more than 10-15%.
- Multiple nodes go unhealthy simultaneously during load spikes.
- Client reports of garbled or duplicated output.

**Prevention:**
- Only retry on pre-stream failures (connection error, immediate HTTP error before any SSE chunks are sent). Never retry a request that has already started streaming to the client.
- Implement a retry budget: cap retries at a percentage of base traffic (5-15%). When the budget is exhausted, fail fast.
- Use per-node circuit breakers: after N consecutive failures to a node, stop routing to it for a cooldown period. Do not rely solely on health checks.
- Distinguish retriable errors (502, 503, 504, connection timeout) from non-retriable errors (400, 422 -- client errors that will fail on any node).

**Detection:** Track retry rate as a percentage of total requests. Alert when it exceeds 10%.

**Phase:** Retry logic is part of the initial proxy implementation, but the circuit breaker and retry budget should be implemented alongside it, not deferred.

---

## Moderate Pitfalls

Mistakes that cause significant debugging time, degraded performance, or technical debt.

### Pitfall 6: etcd Watch Reconnection Failures Cause Stale Node Registry

**What goes wrong:** The gateway connects to etcd and sets up a watch on the node registry prefix. The watch works initially, but after a network hiccup, etcd restart, or lease expiration, the watch silently dies. The gateway continues operating with a stale view of available nodes -- routing to nodes that no longer exist or missing newly registered nodes.

**Why it happens:**
- The `python-etcd3` library (kragniz/python-etcd3) has known issues with gRPC connection recovery. It does not automatically reconnect watches after connection loss.
- Mixing async FastAPI code with `python-etcd3`'s synchronous gRPC calls can cause hangs due to `init_grpc_aio()` conflicts.
- etcd lease keepalives can expire during network partitions, causing node registrations to disappear. The gateway must handle this gracefully.

**Warning signs:**
- Gateway continues routing to nodes that were deregistered minutes ago.
- New nodes do not receive traffic despite being registered in etcd.
- gRPC `UNAVAILABLE` or `UNAUTHENTICATED` errors in logs.

**Prevention:**
- Consider using `etcd3-py` (Revolution1/etcd3-py) instead of `python-etcd3` -- it uses HTTP/JSON gateway instead of native gRPC, avoiding the async/sync gRPC conflict entirely. Its async client uses aiohttp, which is compatible with FastAPI's event loop.
- Implement a periodic full-sync fallback: regardless of watch state, re-read the full node list from etcd every 30-60 seconds. The watch provides real-time updates; the periodic sync provides consistency.
- Add watch health monitoring: if no events (including keepalives) arrive within a threshold, assume the watch is dead and re-establish it.
- Pin `grpcio` and `urllib3` versions in requirements to avoid known compatibility regressions.

**Detection:** Log watch connection state changes. Alert when the last watch event is older than the sync interval.

**Phase:** etcd integration phase. The periodic full-sync fallback is essential from day one -- do not ship watch-only discovery.

---

### Pitfall 7: Timeouts Set Too Short (or Not Set At All) for LLM Workloads

**What goes wrong:** Default HTTP timeouts (30-60 seconds) kill legitimate long-running inference requests. Conversely, no timeout at all allows broken connections to consume resources forever.

**Why it happens:** LLM inference has a uniquely wide latency distribution:
- A short completion might return in 1-2 seconds.
- A long generation (4,000+ tokens) can legitimately take 60-120 seconds.
- Model loading on cold start can take minutes.
- The prefill phase for very long prompts can take 10-30 seconds before the first token.

httpx's default timeouts (`connect=5s, read=5s, write=5s, pool=5s`) are far too aggressive for LLM workloads. But `timeout=None` (no timeout) means a hung vLLM node ties up a connection forever.

**Warning signs:**
- Legitimate long generations returning 504 or `ReadTimeout`.
- Connections to unresponsive nodes staying open for minutes.
- Inconsistent timeout behavior between non-streaming and streaming requests.

**Prevention:**
- Set differentiated timeouts:
  - Connect timeout: 5-10 seconds (fail fast if the node is unreachable).
  - Read timeout for non-streaming: 120-300 seconds (long enough for large generations).
  - Read timeout for streaming: apply to time-between-chunks, not total response time. If no chunk arrives in 30 seconds, the node is likely hung.
- Use httpx's granular timeout configuration: `httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=30.0)` as a baseline, with streaming requests using a custom per-chunk timeout in the async generator.
- Implement a total request deadline (e.g., 10 minutes) as a safety net against infinite streams.

**Detection:** Track timeout errors by type (connect vs. read vs. pool). High connect timeouts indicate unreachable nodes; high read timeouts indicate either too-short timeouts or hung nodes.

**Phase:** Initial proxy implementation. Timeout configuration must be thoughtful from the start -- defaults are wrong for this workload.

---

### Pitfall 8: Closing the SSE Stream on `finish_reason` Instead of `[DONE]`

**What goes wrong:** The proxy stops reading the upstream SSE stream when it encounters a chunk with `finish_reason: stop`, but vLLM sends usage data (token counts) in a separate trailing chunk after the `finish_reason` chunk. This usage data is silently dropped.

**Why it happens:** The OpenAI streaming protocol sends a sequence: content chunks, then a chunk with `finish_reason: stop`, then (optionally) a chunk with usage data and empty choices, then `data: [DONE]`. Many proxy implementations treat `finish_reason` as the signal to close, but the canonical end-of-stream marker is `data: [DONE]`.

**Consequences:**
- Usage data (prompt tokens, completion tokens) is lost from streaming responses.
- Clients that depend on usage data for cost tracking or rate limiting get null values.
- Subtle data inconsistency between streaming and non-streaming responses.

**Warning signs:**
- `usage` field is null in streaming responses but populated in non-streaming responses.
- Token counting discrepancies between proxy metrics and client-side metrics.

**Prevention:**
- Continue reading the SSE stream until `data: [DONE]` is received, not until `finish_reason` appears.
- Parse and forward all chunks between the first chunk and `[DONE]`, including trailing usage chunks.
- Test streaming responses specifically for the presence of usage data.

**Detection:** Compare `usage` fields between streaming and non-streaming responses to the same prompt.

**Phase:** Initial streaming implementation. This is a protocol-level detail that must be correct from the start.

---

### Pitfall 9: OpenAI API Compatibility Gaps That Break Standard SDKs

**What goes wrong:** The proxy implements the "happy path" of the OpenAI API but misses edge cases that standard SDKs depend on. Clients using the official `openai` Python/JS SDK encounter subtle failures.

**Why it happens:** The OpenAI API contract is larger than it appears:
- The `/v1/models` endpoint must return a specific schema (`ListModelsResponse` with `data` array of `Model` objects).
- Error responses must follow OpenAI's error format (`{"error": {"message": "...", "type": "...", "code": "..."}}`) -- not FastAPI's default validation error format.
- Streaming responses must include `id`, `object`, `created`, `model` fields on every chunk, not just the first.
- The `stream_options` parameter (e.g., `include_usage`) must be honored.
- Headers like `openai-processing-ms` are expected by some SDK versions for telemetry.

**Consequences:**
- Standard OpenAI SDKs fail with cryptic parsing errors.
- Clients must add proxy-specific workarounds, defeating the purpose of OpenAI compatibility.
- Switching clients between the proxy and direct OpenAI is not seamless.

**Warning signs:**
- SDK-generated requests fail but curl requests succeed.
- Clients report "unexpected response format" errors.
- Streaming works but error responses crash the SDK.

**Prevention:**
- Test against the official `openai` Python SDK (not just curl/httpx). Use it as the integration test client.
- Implement OpenAI-format error responses at the FastAPI exception handler level.
- Verify every response field against the OpenAI API reference, including streaming chunk structure.
- Forward vLLM's response headers and body as-is whenever possible, rather than reconstructing responses in the proxy. The proxy should be transparent, not transformative.

**Detection:** Integration tests using the official `openai` SDK for all supported endpoints.

**Phase:** Initial API implementation. The error format and response schema must be correct from day one. Edge cases (like `stream_options`) can follow.

---

## Minor Pitfalls

Issues that cause annoyance, minor bugs, or suboptimal performance.

### Pitfall 10: Single-Threaded etcd Operations Blocking the Async Event Loop

**What goes wrong:** The `python-etcd3` library uses synchronous gRPC calls. Calling these from an async FastAPI route handler blocks the entire event loop, freezing all concurrent request handling.

**Prevention:**
- Use `etcd3-py` (which has a native async client via aiohttp) OR run `python-etcd3` calls in a thread executor via `asyncio.to_thread()` or `loop.run_in_executor()`.
- Never call synchronous etcd operations directly from an async route handler or background task.

**Phase:** etcd integration. Architectural choice that must be made at the start.

---

### Pitfall 11: Not Handling vLLM Model Variants Across Nodes

**What goes wrong:** Different vLLM nodes may serve different models (or different quantizations of the same model). The proxy routes a request for "llama-3-70b" to a node running "llama-3-70b-awq" (a quantized variant), producing subtly different outputs.

**Prevention:**
- Store model metadata (exact model name, quantization, context length) in the etcd registration.
- Route requests to nodes whose registered model exactly matches the requested model in the API call.
- Return a clear error (matching OpenAI's format) when no node serves the requested model, rather than falling back to a different model.

**Phase:** Service discovery and routing implementation.

---

### Pitfall 12: No Graceful Shutdown -- Killing In-Flight Streams

**What goes wrong:** When the proxy process restarts or deploys, active streaming connections are abruptly terminated. Clients receive incomplete responses with no indication of why.

**Prevention:**
- Implement graceful shutdown: stop accepting new connections, wait for in-flight streams to complete (up to a deadline), then shut down.
- Use FastAPI's `on_event("shutdown")` or lifespan context manager to coordinate.
- Signal the load balancer (if any) to stop routing before draining connections.

**Phase:** Deployment and operations phase, but the shutdown hook should be wired in during initial implementation.

---

### Pitfall 13: Ignoring Backpressure from Slow Clients

**What goes wrong:** A slow client (poor network, overwhelmed browser) cannot consume SSE chunks as fast as vLLM generates them. Without backpressure, the proxy buffers the unconsumed chunks in memory, growing unboundedly.

**Prevention:**
- Starlette's `StreamingResponse` respects TCP backpressure by default -- when the client's TCP receive window fills, the `send()` coroutine blocks, which slows the upstream read. Verify this behavior is preserved by not adding intermediate unbounded buffers.
- If using `asyncio.Queue` for decoupling, always set a `maxsize` to bound memory usage.
- Monitor per-connection buffer sizes.

**Phase:** Streaming implementation. The default Starlette behavior is correct -- the pitfall is in accidentally defeating it with unbounded queues or intermediate buffers.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Proxy core (streaming) | Buffering destroys SSE (#1), resource leaks (#2), stream termination (#8) | Use `client.stream()`, `BackgroundTask(r.aclose)`, read until `[DONE]` |
| etcd integration | Watch reconnection (#6), sync blocking async (#10) | Periodic full-sync fallback, use async-compatible etcd client |
| Load balancing | Least-connections ignores request cost (#4) | Design balancer as pluggable strategy; track per-node metrics for future upgrade |
| Health checking | vLLM `/health` lies (#3) | Implement readiness probes with lightweight inference test |
| Retry/failover | Mid-stream retry garbles output (#5), retry storms (#5) | Only retry pre-stream failures, implement retry budget and circuit breakers |
| OpenAI compatibility | SDK-breaking response formats (#9) | Test with official `openai` SDK, not just curl |
| Timeouts | Defaults too short for LLM (#7) | Differentiated timeouts: connect (fast), read (long), per-chunk for streaming |
| Deployment | Killing in-flight streams (#12) | Graceful shutdown with drain period |

---

## Sources

- [vLLM /health/ready proposal (Issue #36960)](https://github.com/vllm-project/vllm/issues/36960) -- GPU health verification gap
- [vLLM Troubleshooting Docs](https://docs.vllm.ai/en/latest/usage/troubleshooting/) -- OOM and CUDA failure modes
- [vLLM-Ascend streaming Content-Type bug (PR #6985)](https://github.com/vllm-project/vllm-ascend/pull/6985) -- incorrect media type in proxy
- [LiteLLM streaming usage loss (Issue #25389)](https://github.com/BerriAI/litellm/issues/25389) -- usage data dropped on finish_reason
- [NGINX Reverse Proxy for Ollama/vLLM](https://www.getpagespeed.com/server-setup/nginx-reverse-proxy-ollama-vllm) -- buffering/timeout pitfalls
- [HTTPX Resource Limits](https://www.python-httpx.org/advanced/resource-limits/) -- connection pool configuration
- [HTTPX Async Support](https://www.python-httpx.org/async/) -- streaming response lifecycle
- [python-etcd3 reconnection issue (#580)](https://github.com/kragniz/python-etcd3/issues/580) -- no auto-reconnect
- [python-etcd3 ConnectionFailedError (#1467)](https://github.com/kragniz/python-etcd3/issues/1467) -- gRPC version incompatibilities
- [gRPC init_grpc_aio() hangs sync calls (#22733)](https://github.com/grpc/grpc/issues/22733) -- async/sync gRPC conflict
- [Tail-Tolerant Retry Policy for LLM Gateways](https://tianpan.co/blog/2026-05-02-tail-tolerant-retry-policy-llm-gateway-latency-cliff) -- retry amplification
- [Idempotency in LLM Pipelines](https://tianpan.co/blog/2026-04-20-idempotency-llm-pipelines) -- duplicate generation risks
- [DigitalOcean: Load Balancing and Scaling LLM Serving](https://www.digitalocean.com/blog/load-balancing-scaling-llm-serving) -- why least-connections falls short
- [Making Your Load Balancer LLM-Aware](https://blog.doubleword.ai/behind-the-stack-ep-4-making-your-load-balancer-llm-aware) -- token-aware routing
- [llama.cpp SSE headers fix (PR #20872)](https://github.com/ggml-org/llama.cpp/pull/20872) -- reverse proxy SSE buffering
- [Streaming LLM Responses (Redis)](https://redis.io/blog/streaming-llm-responses/) -- backpressure and buffering
- [FastAPI SSE Documentation](https://fastapi.tiangolo.com/tutorial/server-sent-events/) -- built-in SSE support
