# Phase 28: Model Selection - Research

**Researched:** 2026-07-26
**Domain:** Threading an optional model parameter through the existing provisioning flow
**Confidence:** HIGH

## Summary

This phase adds an optional `model` field to `SetupRequest` and threads it through `provision()` -> `_run_start_vllm()` so the provisioner prepends `VLLM_MODEL=<value>` to the SSH command string. The shell script `start-vllm.sh` already reads `VLLM_MODEL` at line 102 (`MODEL="${VLLM_MODEL:-$MODEL}"`) -- zero shell changes needed.

The change touches three files (model, provisioner, admin endpoint) with roughly 10 lines of actual logic. No new dependencies. The main risk is shell injection via the model string, mitigated by `shlex.quote()` (stdlib).

**Primary recommendation:** Add `model: str | None = None` to `SetupRequest`, thread it through `provision()` and `_run_start_vllm()`, prepend `VLLM_MODEL=<quoted_value>` to the SSH command when set. Test the three behaviors: field accepted, env var prepended, omission falls through to auto-detect.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Pass `VLLM_MODEL` by prepending to the SSH command string: `VLLM_MODEL=<model> bash auto-vllm/start-vllm.sh`. No changes to `SSHClient` interface. Use `shlex.quote()` to sanitize the model string against shell injection.
- **D-02:** Only prepend `VLLM_MODEL` when the model field is set (not None/empty). When omitted, `start-vllm.sh` falls through to its existing GPU-based auto-detection logic at line 102.

### Claude's Discretion
- **Model validation:** Basic Pydantic validation on `SetupRequest.model` (optional `str | None`, reasonable length limit). No format validation or NFS/llmfit cross-check -- vLLM validates model availability at startup, and failures flow through the existing `ProvisioningError` path.
- **Provisioner signature:** Thread `model` through `provision()` -> `_run_start_vllm()`. Add `model: str | None = None` parameter to both methods. Existing callers (teardown, etc.) are unaffected.
- **Admin endpoint:** `setup_node()` passes `body.model` to `provisioner.provision()`. Single-line change.

### Deferred Ideas (OUT OF SCOPE)
None.

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SEL-01 | SetupRequest accepts optional model field for operator-selected model | Add `model: str \| None = None` to the frozen Pydantic model in `inference_proxy/models/admin.py`. Follows existing pattern (see `managed: bool = True` on same class). |
| SEL-02 | Provisioner passes `VLLM_MODEL` env var to `start-vllm.sh` when model is specified | Conditionally prepend `VLLM_MODEL={shlex.quote(model)}` to the command string in `_run_start_vllm()`. Shell script already reads this env var at line 102. |

</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Model field on request | API / Backend | -- | Pydantic model + endpoint handler |
| Env var injection | API / Backend | -- | Provisioner constructs the SSH command string |
| Model auto-detection fallback | Remote host (shell) | -- | `start-vllm.sh` handles this; unchanged |

## Architecture Patterns

### Data Flow

```
POST /admin/nodes/setup {"hostname":"gpu01", "model":"Qwen/Qwen2.5-72B-Instruct"}
  |
  v
setup_node() in api/admin.py
  |-- body.model -> provisioner.provision(hostname, managed=body.managed, model=body.model)
  v
NodeProvisioner.provision()
  |-- passes model to _run_start_vllm(hostname, model=model)
  v
NodeProvisioner._run_start_vllm()
  |-- if model: command = f"VLLM_MODEL={shlex.quote(model)} bash auto-vllm/start-vllm.sh"
  |-- else:     command = "bash auto-vllm/start-vllm.sh"
  v
SSHClient.run_streaming(hostname, command)  # interface UNCHANGED
  v
start-vllm.sh reads MODEL="${VLLM_MODEL:-$MODEL}" at line 102
```

### Pattern: Conditional env var prepend

**What:** When an optional parameter needs to reach a shell script, prepend it as an env var on the command string rather than modifying the SSH client interface or writing config files. [VERIFIED: existing codebase pattern -- `_run_start_vllm` already constructs a command string]

**Example:**
```python
import shlex

async def _run_start_vllm(self, hostname: str, *, model: str | None = None) -> str:
    command = "bash auto-vllm/start-vllm.sh"
    if model:
        command = f"VLLM_MODEL={shlex.quote(model)} {command}"
    # ... rest unchanged
```

### Anti-Patterns to Avoid
- **Modifying SSHClient interface:** The SSH client is a transport layer. Model selection is provisioning logic -- keep it in the command string construction. [VERIFIED: CONTEXT.md D-01 locks this]
- **Modifying start-vllm.sh:** The script already supports `VLLM_MODEL`. Touching it is unnecessary churn. [VERIFIED: line 102 of start-vllm.sh]
- **Format-validating model names:** Model names have no stable format (e.g., `Qwen/Qwen2.5-72B-Instruct`, `meta-llama/Llama-3.3-70B-Instruct`). vLLM validates at startup. Adding regex validation here creates a maintenance burden with zero safety gain. [ASSUMED]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Shell argument escaping | Manual string escaping | `shlex.quote()` (stdlib) | Handles all edge cases -- quotes, spaces, semicolons, backticks. Battle-tested. |
| Model name validation | Custom regex validator | Pydantic `str` with `max_length` | vLLM does the real validation at runtime. Length limit prevents abuse. |

## Common Pitfalls

### Pitfall 1: Shell injection via model string
**What goes wrong:** Model string like `; rm -rf /` injected into SSH command without sanitization.
**Why it happens:** Naive f-string interpolation into a shell command.
**How to avoid:** `shlex.quote()` on the model string before interpolation. This is locked in D-01.
**Warning signs:** Any command construction using f-strings with user input and no quoting.

### Pitfall 2: Empty string vs None
**What goes wrong:** `model=""` treated as truthy, prepending `VLLM_MODEL=''` which overrides auto-detection with an empty model name, causing vLLM to fail.
**Why it happens:** Python treats `""` as falsy, but Pydantic may coerce `null` to `""` depending on config.
**How to avoid:** Use `str | None = None` (not `str = ""`). The truthiness check `if model:` correctly handles both `None` and `""`. Pydantic with `frozen=True` and no custom validator won't coerce null to empty string.
**Warning signs:** Tests should cover both `model=None` and `model=""` cases.

### Pitfall 3: Forgetting to thread model through provision() to _run_start_vllm()
**What goes wrong:** Field added to SetupRequest and endpoint, but `provision()` doesn't accept or forward it.
**Why it happens:** Two-hop parameter passing is easy to forget one hop.
**How to avoid:** Thread it explicitly: `provision(hostname, managed=..., model=body.model)` -> `_run_start_vllm(hostname, model=model)`.
**Warning signs:** Test that verifies the command string includes `VLLM_MODEL` when model is set.

## Code Examples

### SetupRequest with model field
```python
# Source: inference_proxy/models/admin.py (existing pattern)
class SetupRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    hostname: str
    managed: bool = True
    model: str | None = None  # SEL-01

    @field_validator("hostname")
    @classmethod
    def validate_hostname(cls, v: str) -> str:
        # ... existing validator unchanged
```

### Provisioner method signatures
```python
# Source: inference_proxy/provisioning/provisioner.py
async def provision(self, hostname: str, *, managed: bool = True, model: str | None = None) -> None:
    # ... existing code, thread model to _run_start_vllm:
    model_name = await self._run_start_vllm(hostname, model=model)

async def _run_start_vllm(self, hostname: str, *, model: str | None = None) -> str:
    command = "bash auto-vllm/start-vllm.sh"
    if model:
        command = f"VLLM_MODEL={shlex.quote(model)} {command}"
    # ... rest of existing streaming/parsing logic unchanged
```

### Admin endpoint change
```python
# Source: inference_proxy/api/admin.py line ~153
await provisioner.provision(hostname, managed=body.managed, model=body.model)
```

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 1.4 |
| Config file | pyproject.toml |
| Quick run command | `python -m pytest tests/provisioning/test_provisioner.py tests/models/test_admin.py tests/api/test_admin.py -x -q` |
| Full suite command | `python -m pytest tests/ -x -q` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SEL-01 | SetupRequest accepts optional model field (None default, str when set) | unit | `python -m pytest tests/models/test_admin.py -x -q` | Exists, needs new tests |
| SEL-01 | POST /admin/nodes/setup accepts model in body | integration | `python -m pytest tests/api/test_admin.py -x -q` | Exists, needs new tests |
| SEL-02 | _run_start_vllm prepends VLLM_MODEL env var when model is set | unit | `python -m pytest tests/provisioning/test_provisioner.py -x -q` | Exists, needs new tests |
| SEL-02 | _run_start_vllm omits VLLM_MODEL when model is None | unit | `python -m pytest tests/provisioning/test_provisioner.py -x -q` | Exists, needs new tests |
| SEL-02 | shlex.quote() sanitizes model string | unit | `python -m pytest tests/provisioning/test_provisioner.py -x -q` | Needs new test |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/provisioning/test_provisioner.py tests/models/test_admin.py tests/api/test_admin.py -x -q`
- **Per wave merge:** `python -m pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
None -- existing test files cover all three modules. New test cases go into existing files.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | -- |
| V3 Session Management | no | -- |
| V4 Access Control | no | Internal admin API, no change to access model |
| V5 Input Validation | yes | `shlex.quote()` for shell injection; Pydantic `str \| None` with implicit max_length |
| V6 Cryptography | no | -- |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Shell injection via model string | Tampering | `shlex.quote()` (stdlib) -- D-01 locks this |
| Oversized model string DoS | Denial of Service | Pydantic `max_length` on the field (e.g., 256 chars) |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Model names have no stable format that could be regex-validated | Anti-Patterns | Low -- worst case is vLLM rejects the model at startup, which already produces a ProvisioningError |
| A2 | 256-char max_length is sufficient for all model identifiers | Security Domain | Low -- HuggingFace model IDs are org/name format, well under 256 |

## Open Questions

None. This phase is fully scoped by CONTEXT.md decisions and the existing codebase.

## Sources

### Primary (HIGH confidence)
- `inference_proxy/models/admin.py` -- SetupRequest class at line 60, existing `managed: bool = True` pattern
- `inference_proxy/provisioning/provisioner.py` -- `provision()` at line 229, `_run_start_vllm()` at line 365
- `inference_proxy/api/admin.py` -- `setup_node()` at line 111, call to `provisioner.provision()` at line 153
- `auto-vllm/start-vllm.sh` -- `VLLM_MODEL` env var read at line 102
- Python stdlib `shlex.quote()` -- [VERIFIED: stdlib]

### Secondary (MEDIUM confidence)
- None needed -- all changes are within existing codebase patterns.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, all stdlib + existing Pydantic
- Architecture: HIGH -- three-line parameter threading through existing call chain
- Pitfalls: HIGH -- shell injection is the only real risk, mitigated by locked decision D-01

**Research date:** 2026-07-26
**Valid until:** indefinite (no external dependency changes)
