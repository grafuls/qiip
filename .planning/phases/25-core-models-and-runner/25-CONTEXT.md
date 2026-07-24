# Phase 25: Core Models and Runner - Context

**Gathered:** 2026-07-24
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase delivers Pydantic models for llmfit JSON output and an SSH-based runner that executes `llmfit recommend --json` on remote hosts with timeout protection. No API endpoint, no settings wiring, no dashboard — just the typed models and the execution layer.

</domain>

<decisions>
## Implementation Decisions

### SSH Execution Method
- **D-01:** Add a new `run()` method to SSHClient that returns `(stdout, stderr, exit_status)` as a single call. Distinct from existing `run_streaming()` which yields line-by-line for provisioning. Clean separation: streaming for long-running ops, `run()` for capture-all commands.
- **D-02:** `run()` accepts a `timeout` parameter (default 60s) and handles timeout internally via `asyncio.wait_for()`. Consistent with `connect_timeout` already being internal to SSHClient. Raises a typed timeout error when exceeded.

### Error Handling
- **D-03:** Exception hierarchy: `LLMFitError` (base) → `LLMFitTimeoutError`, `LLMFitParseError`. SSH-level errors (`SSHConnectionError`, `RemoteCommandError`) bubble through unchanged — no wrapping.
- **D-04:** `LLMFitParseError` stores the raw stdout that failed to parse, for debugging. Phase 27 decides whether to expose raw output in API responses or log-only.

### llmfit Command Flags
- **D-05:** Hardcode `--json --force-runtime vllm` in the runner. No configurable flags in this phase. `--limit`, `--use-case`, `--memory` deferred to Phase 27 (API endpoint adds query params).
- **D-06:** No `LLMFitSettings` in this phase. Runner uses hardcoded defaults: timeout 60s, binary path `/usr/local/bin/llmfit`. Phase 27 adds `LLMFitSettings` to `config/settings.py` when configurability is needed.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Existing SSH Pattern
- `inference_proxy/provisioning/ssh_client.py` — SSHClient with `run_streaming()`, typed errors (`SSHConnectionError`, `RemoteCommandError`). New `run()` method goes here.

### Existing Models Pattern
- `inference_proxy/models/node.py` — Node Pydantic model pattern (frozen, validators)
- `inference_proxy/models/admin.py` — Admin response models pattern
- `inference_proxy/models/quads.py` — External API response parsing with Pydantic

### Settings Pattern
- `inference_proxy/config/settings.py` — Nested BaseModel settings. NOT modified in this phase but relevant for Phase 27.

### llmfit Reference
- `.planning/research/SUMMARY.md` — llmfit integration research with JSON schema, pitfalls, architecture approach
- `.planning/research/FEATURES.md` — Expected features and llmfit CLI flags
- `.planning/research/PITFALLS.md` — Critical pitfalls (#2: no timeout, #3: unstable JSON, #4: no GPU detection)

### Requirements
- `.planning/REQUIREMENTS.md` — EXEC-01, EXEC-02, EXEC-03 map to this phase

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `SSHClient` (`inference_proxy/provisioning/ssh_client.py`): Sole asyncssh consumer. Add `run()` method here — follows DIP, all SSH goes through this wrapper.
- `SSHConnectionError`, `RemoteCommandError`: Existing typed errors that LLMFitRunner callers already handle.

### Established Patterns
- Pydantic models with `extra="ignore"` for forward compatibility (research recommendation, aligns with quads.py pattern)
- DI via constructor injection: `LLMFitRunner.__init__(ssh_client: SSHClient)` — same as provisioner receiving SSHClient
- Models in `inference_proxy/models/` as separate files per domain

### Integration Points
- `SSHClient` gets a new `run()` method (modifies existing file)
- New `inference_proxy/models/llmfit.py` for Pydantic models
- New `inference_proxy/llmfit/runner.py` for LLMFitRunner (or `inference_proxy/services/llmfit_runner.py` — follow existing service placement)

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches. Research prescribes `extra="ignore"` on all models and absolute binary path for remote execution.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 25-Core Models and Runner*
*Context gathered: 2026-07-24*
