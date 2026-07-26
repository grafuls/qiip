# Phase 28: Model Selection - Context

**Gathered:** 2026-07-26
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase wires operator-selected model into provisioning. `SetupRequest` gains an optional `model` field; when set, the provisioner passes it as the `VLLM_MODEL` environment variable to `start-vllm.sh`, overriding the GPU-based auto-detection. No dashboard UI, no model validation against llmfit or NFS, no new API endpoints — just threading the model choice through the existing provisioning flow.

</domain>

<decisions>
## Implementation Decisions

### Env Var Passing
- **D-01:** Pass `VLLM_MODEL` by prepending to the SSH command string: `VLLM_MODEL=<model> bash auto-vllm/start-vllm.sh`. No changes to `SSHClient` interface. Use `shlex.quote()` to sanitize the model string against shell injection.
- **D-02:** Only prepend `VLLM_MODEL` when the model field is set (not None/empty). When omitted, `start-vllm.sh` falls through to its existing GPU-based auto-detection logic at line 102.

### Claude's Discretion
- **Model validation:** Basic Pydantic validation on `SetupRequest.model` (optional `str | None`, reasonable length limit). No format validation or NFS/llmfit cross-check — vLLM validates model availability at startup, and failures flow through the existing `ProvisioningError` path.
- **Provisioner signature:** Thread `model` through `provision()` → `_run_start_vllm()`. Add `model: str | None = None` parameter to both methods. Existing callers (teardown, etc.) are unaffected.
- **Admin endpoint:** `setup_node()` passes `body.model` to `provisioner.provision()`. Single-line change.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Provisioning Flow
- `inference_proxy/api/admin.py` — `setup_node()` endpoint at line 111: receives `SetupRequest`, calls `provisioner.provision()`. Thread `body.model` through here.
- `inference_proxy/provisioning/provisioner.py` — `provision()` at line 230, `_run_start_vllm()` at line 365. These methods gain the `model` parameter.
- `inference_proxy/provisioning/ssh_client.py` — `SSHClient.run_streaming()` at line 70. NOT modified — command string changes only.

### Request Model
- `inference_proxy/models/admin.py` — `SetupRequest` at line 60. Add optional `model` field here.

### Shell Script
- `auto-vllm/start-vllm.sh` — Line 102: `MODEL="${VLLM_MODEL:-$MODEL}"`. Already supports the env var override. NOT modified in this phase.

### Requirements
- `.planning/REQUIREMENTS.md` — SEL-01 (optional model field), SEL-02 (VLLM_MODEL env var).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `SetupRequest` (`inference_proxy/models/admin.py`): Frozen Pydantic model with hostname validator. Add `model: str | None = None` field.
- `VLLM_MODEL` support in `start-vllm.sh`: Already reads the env var — zero shell script changes needed.
- Existing `_run_start_vllm()` command-string construction: Currently hardcoded `"bash auto-vllm/start-vllm.sh"`, conditionally prepend env var.

### Established Patterns
- `provisioner.provision(hostname, managed=body.managed)` call pattern — add `model=body.model` kwarg.
- `shlex.quote()` used elsewhere for shell safety — apply to model string.

### Integration Points
- `inference_proxy/models/admin.py` — New field on `SetupRequest`
- `inference_proxy/provisioning/provisioner.py` — `provision()` and `_run_start_vllm()` signatures
- `inference_proxy/api/admin.py` — `setup_node()` passes model to provisioner

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches. Follow existing provisioning patterns.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 28-Model Selection*
*Context gathered: 2026-07-26*
