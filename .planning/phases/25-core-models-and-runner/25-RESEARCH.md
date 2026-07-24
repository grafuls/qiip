# Phase 25: Core Models and Runner - Research

**Researched:** 2026-07-24
**Domain:** SSH command execution, Pydantic model design, error handling
**Confidence:** HIGH

## Summary

Phase 25 delivers two things: (1) Pydantic models that parse llmfit's `recommend --json` output into typed Python objects, and (2) an `LLMFitRunner` class that SSHes to a remote host, runs `llmfit recommend --json --force-runtime vllm`, and returns those typed models. No API endpoint, no settings wiring, no dashboard -- just the data layer and execution layer.

The implementation is straightforward because the codebase already has every pattern needed. `SSHClient` wraps asyncssh (DIP); it gets a new `run()` method that uses asyncssh's built-in `conn.run(command, timeout=N)` instead of the streaming `create_process()` path. Pydantic models follow the frozen + `extra="ignore"` pattern established in `models/quads.py` and `models/node.py`. Error hierarchy follows the Redfish pattern: domain-specific base error with typed subclasses.

Zero new dependencies. Everything uses asyncssh (already installed, v2.24.0), Pydantic (already installed), and stdlib `json`.

**Primary recommendation:** Use asyncssh's `conn.run(command, check=True, timeout=N)` for the new `SSHClient.run()` method -- it handles timeout natively (raises `TimeoutError`) and returns `SSHCompletedProcess` with `.stdout`, `.stderr`, `.exit_status`. Wrap in `asyncio.wait_for()` only if `conn.run()`'s timeout proves insufficient (it should not -- it is the documented approach).

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Add a new `run()` method to SSHClient that returns `(stdout, stderr, exit_status)` as a single call. Distinct from existing `run_streaming()` which yields line-by-line for provisioning. Clean separation: streaming for long-running ops, `run()` for capture-all commands.
- **D-02:** `run()` accepts a `timeout` parameter (default 60s) and handles timeout internally via `asyncio.wait_for()`. Consistent with `connect_timeout` already being internal to SSHClient. Raises a typed timeout error when exceeded.
- **D-03:** Exception hierarchy: `LLMFitError` (base) -> `LLMFitTimeoutError`, `LLMFitParseError`. SSH-level errors (`SSHConnectionError`, `RemoteCommandError`) bubble through unchanged -- no wrapping.
- **D-04:** `LLMFitParseError` stores the raw stdout that failed to parse, for debugging. Phase 27 decides whether to expose raw output in API responses or log-only.
- **D-05:** Hardcode `--json --force-runtime vllm` in the runner. No configurable flags in this phase. `--limit`, `--use-case`, `--memory` deferred to Phase 27 (API endpoint adds query params).
- **D-06:** No `LLMFitSettings` in this phase. Runner uses hardcoded defaults: timeout 60s, binary path `/usr/local/bin/llmfit`. Phase 27 adds `LLMFitSettings` to `config/settings.py` when configurability is needed.

### Claude's Discretion

No specific discretion areas -- decisions are comprehensive for this phase's scope.

### Deferred Ideas (OUT OF SCOPE)

None -- discussion stayed within phase scope.

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| EXEC-01 | Gateway can run `llmfit recommend --json` on a remote host via SSH and parse the JSON output | New `SSHClient.run()` method + `LLMFitRunner.recommend()` that invokes it, parses JSON into Pydantic models |
| EXEC-02 | SSH command execution has timeout protection to prevent hangs | `SSHClient.run()` uses asyncssh's `conn.run(timeout=N)` which raises `TimeoutError` on expiry; runner catches and re-raises as `LLMFitTimeoutError` |
| EXEC-03 | Pydantic models validate llmfit JSON output (system hardware info + ranked model list) | `SystemInfo`, `ModelRecommendation`, `LLMFitResult` frozen Pydantic models with `extra="ignore"` |

</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| SSH command execution | API / Backend | -- | SSHClient is a backend service; `run()` executes on the gateway, connects to remote hosts |
| llmfit JSON parsing | API / Backend | -- | Pure data transformation, no client/browser involvement |
| Pydantic model definitions | API / Backend | -- | Data validation layer consumed by backend services |
| Timeout protection | API / Backend | -- | asyncssh + asyncio handle timeout server-side |
| Error hierarchy | API / Backend | -- | Domain errors consumed by future API layer (Phase 27) |

## Standard Stack

### Core (already installed -- zero additions)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| asyncssh | 2.24.0 | SSH execution | Already the sole SSH library; `conn.run()` provides capture-all + timeout natively [VERIFIED: pip freeze] |
| pydantic | >=2.10 | Model validation | Already in stack; frozen models with `extra="ignore"` is the established pattern [VERIFIED: pyproject.toml] |
| structlog | >=26.1.0 | Logging | Already in stack; used by SSHClient for connection logging [VERIFIED: pyproject.toml] |
| json (stdlib) | -- | JSON parsing | stdlib; no external parser needed for llmfit output [VERIFIED: stdlib] |

### Supporting (none)

No new dependencies. This phase adds zero packages to pyproject.toml.

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| asyncssh `conn.run()` | `create_process()` + manual `asyncio.wait_for()` | `conn.run()` handles timeout natively and returns a clean result object; `create_process()` is for streaming which `run_streaming()` already covers |
| `asyncio.wait_for()` wrapping `conn.run()` | `conn.run(timeout=N)` alone | D-02 specifies `asyncio.wait_for()`. However, `conn.run(timeout=N)` achieves the same effect natively. Implement per D-02 using `asyncio.wait_for()` as the timeout mechanism, since that is the locked decision. |

**Installation:** None required. All dependencies already installed.

## Architecture Patterns

### System Architecture Diagram

```
Caller (future Phase 27 endpoint)
       |
       v
LLMFitRunner.recommend(hostname)
       |
       |  1. Build command string:
       |     "/usr/local/bin/llmfit recommend --json --force-runtime vllm"
       |
       v
SSHClient.run(host, command, timeout=60)
       |
       |  2. asyncssh.connect() -> conn.run(command, timeout=60)
       |     Returns SSHCompletedProcess(stdout, stderr, exit_status)
       |
       |  3. On timeout -> asyncio.TimeoutError
       |     On auth/connect fail -> SSHConnectionError
       |     On non-zero exit -> RemoteCommandError
       |
       v
Raw stdout string (JSON)
       |
       |  4. json.loads(stdout)
       |     On parse failure -> LLMFitParseError(raw_output=stdout)
       |
       v
LLMFitResult(system=SystemInfo, models=[ModelRecommendation, ...])
       |
       |  5. Pydantic validation with extra="ignore"
       |     On validation failure -> LLMFitParseError(raw_output=stdout)
       |
       v
Typed Pydantic model returned to caller
```

### Recommended Project Structure

```
inference_proxy/
  models/
    llmfit.py            # SystemInfo, ModelRecommendation, LLMFitResult
  llmfit/
    __init__.py
    errors.py            # LLMFitError, LLMFitTimeoutError, LLMFitParseError
    runner.py            # LLMFitRunner class
  provisioning/
    ssh_client.py        # MODIFIED: add run() method
```

New files: 4 (models/llmfit.py, llmfit/__init__.py, llmfit/errors.py, llmfit/runner.py)
Modified files: 1 (provisioning/ssh_client.py)

### Pattern 1: SSHClient.run() -- capture-all command execution

**What:** New method on existing `SSHClient` that runs a command and returns all output at once, complementing `run_streaming()` which yields line-by-line.

**When to use:** Short-lived commands where you need the complete output (e.g., `llmfit recommend --json`, future one-shot commands). Not for long-running provisioning scripts.

**Implementation notes:**
- asyncssh's `conn.run()` returns `SSHCompletedProcess` with `.stdout` (str), `.stderr` (str), `.exit_status` (int) [VERIFIED: asyncssh docstring inspection]
- `conn.run(check=True)` raises `asyncssh.ProcessError` on non-zero exit -- but the codebase raises its own `RemoteCommandError` instead, so use `check=False` and check manually for consistency with `run_streaming()` [VERIFIED: ssh_client.py lines 102-106]
- Timeout: D-02 says `asyncio.wait_for()`. asyncssh `conn.run(timeout=N)` also works natively. Use `asyncio.wait_for()` per the locked decision; catch `asyncio.TimeoutError` in the runner and raise `LLMFitTimeoutError`.

**Example:**
```python
# Source: asyncssh docs + existing ssh_client.py pattern
async def run(
    self, host: str, command: str, timeout: float = 60.0,
) -> tuple[str, str, int]:
    """Run command, return (stdout, stderr, exit_status)."""
    try:
        async with asyncssh.connect(
            host,
            username=self._username,
            client_keys=[str(self._key_path)],
            known_hosts=None,
            connect_timeout=self._connect_timeout,
        ) as conn:
            result = await asyncio.wait_for(
                conn.run(command),
                timeout=timeout,
            )
            if result.exit_status is not None and result.exit_status != 0:
                raise RemoteCommandError(
                    host, command, result.exit_status,
                    stderr=result.stderr or "",
                )
            return (
                result.stdout or "",
                result.stderr or "",
                result.exit_status if result.exit_status is not None else 0,
            )
    except asyncssh.PermissionDenied as exc:
        raise SSHConnectionError(host, f"authentication failed: {exc}") from exc
    except asyncssh.DisconnectError as exc:
        raise SSHConnectionError(host, f"disconnected: {exc.reason}") from exc
    except OSError as exc:
        raise SSHConnectionError(host, str(exc)) from exc
    # Note: asyncio.TimeoutError is NOT caught here -- it bubbles up
    # to the caller (LLMFitRunner) which converts it to LLMFitTimeoutError
```

### Pattern 2: Pydantic models with extra="ignore"

**What:** Frozen Pydantic models that parse llmfit JSON, tolerating unknown fields for forward compatibility.

**When to use:** Parsing external tool output where the schema may add fields across versions.

**Example:**
```python
# Source: existing models/quads.py pattern + llmfit JSON schema from FEATURES.md
from pydantic import BaseModel, ConfigDict

class SystemInfo(BaseModel):
    """Hardware info detected by llmfit."""
    model_config = ConfigDict(frozen=True, extra="ignore")

    has_gpu: bool
    gpu_vram_gb: float = 0.0
    gpu_name: str = ""  # not in schema -- use cpu_name as fallback field name
    cpu_name: str = ""
    total_ram_gb: float = 0.0
    backend: str = ""

class ModelRecommendation(BaseModel):
    """A single model recommendation from llmfit."""
    model_config = ConfigDict(frozen=True, extra="ignore")

    name: str
    score: float = 0.0
    fit_level: str = ""
    estimated_tps: float = 0.0
    memory_required_gb: float = 0.0
    provider: str = ""
    best_quant: str = ""
    run_mode: str = ""
    params_b: float = 0.0
    context_length: int = 0
    utilization_pct: float = 0.0
    category: str = ""
    runtime: str = ""

class LLMFitResult(BaseModel):
    """Top-level parsed result from llmfit recommend --json."""
    model_config = ConfigDict(frozen=True, extra="ignore")

    system: SystemInfo
    models: list[ModelRecommendation]
```

### Pattern 3: Domain error hierarchy

**What:** Base error class with typed subclasses, following the Redfish pattern.

**Example:**
```python
# Source: inference_proxy/redfish/errors.py pattern

class LLMFitError(Exception):
    """Base error for llmfit operations."""

class LLMFitTimeoutError(LLMFitError):
    """Raised when llmfit execution exceeds timeout."""
    def __init__(self, host: str, timeout: float) -> None:
        self.host = host
        self.timeout = timeout
        super().__init__(
            f"llmfit timed out after {timeout}s on {host}"
        )

class LLMFitParseError(LLMFitError):
    """Raised when llmfit output cannot be parsed."""
    def __init__(self, reason: str, raw_output: str) -> None:
        self.reason = reason
        self.raw_output = raw_output  # D-04: stored for debugging
        super().__init__(f"Failed to parse llmfit output: {reason}")
```

### Pattern 4: LLMFitRunner with DI

**What:** Runner class that takes `SSHClient` via constructor injection (same as `NodeProvisioner`).

**Example:**
```python
# Source: existing provisioner.py DI pattern
class LLMFitRunner:
    _BINARY = "/usr/local/bin/llmfit"  # D-06: hardcoded this phase
    _TIMEOUT = 60.0  # D-06: hardcoded this phase
    _COMMAND = f"{_BINARY} recommend --json --force-runtime vllm"  # D-05

    def __init__(self, ssh_client: SSHClient) -> None:
        self._ssh = ssh_client

    async def recommend(self, hostname: str) -> LLMFitResult:
        """Run llmfit on hostname, return parsed result."""
        try:
            stdout, stderr, _ = await self._ssh.run(
                hostname, self._COMMAND, timeout=self._TIMEOUT,
            )
        except asyncio.TimeoutError:
            raise LLMFitTimeoutError(hostname, self._TIMEOUT)

        if not stdout.strip():
            raise LLMFitParseError("empty output", raw_output=stdout)

        try:
            data = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise LLMFitParseError(str(exc), raw_output=stdout) from exc

        try:
            return LLMFitResult.model_validate(data)
        except ValidationError as exc:
            raise LLMFitParseError(str(exc), raw_output=stdout) from exc
```

### Anti-Patterns to Avoid

- **Wrapping SSH errors in LLMFitError:** D-03 says SSH errors bubble through unchanged. Do not catch `SSHConnectionError` or `RemoteCommandError` in the runner.
- **Adding LLMFitSettings in this phase:** D-06 explicitly defers settings to Phase 27. Hardcode the binary path and timeout as class constants.
- **Parsing JSON field-by-field with dict access:** Use Pydantic model_validate, not manual `data["system"]["gpu_vram_gb"]`. Pydantic gives typed validation and `extra="ignore"` for free.
- **Creating an abstract runner interface:** Only one implementation exists. YAGNI. The concrete class with SSHClient injection is sufficient for testing (mock SSHClient).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| SSH command timeout | Manual timer + process kill | asyncssh `conn.run(timeout=N)` or `asyncio.wait_for()` | asyncssh handles channel teardown on timeout; manual kill is error-prone with remote processes |
| JSON schema validation | Manual dict key checking | Pydantic `model_validate()` with `extra="ignore"` | Handles missing fields (defaults), extra fields (ignored), type coercion, and nested validation |
| SSH connection management | Raw asyncssh calls | Existing `SSHClient` wrapper | DIP -- all SSH goes through wrapper; connection params, error translation, and logging are centralized |

## Common Pitfalls

### Pitfall 1: asyncio.TimeoutError not caught by runner

**What goes wrong:** `SSHClient.run()` raises `asyncio.TimeoutError` which is a `BaseException` subclass in some Python versions. The runner's `except Exception` block misses it.
**Why it happens:** `TimeoutError` is a subclass of `OSError` in Python 3.12+ (and also of `BaseException` indirectly). However, `asyncio.TimeoutError` IS caught by `except Exception` in Python 3.12+.
**How to avoid:** Catch `asyncio.TimeoutError` explicitly before any `except Exception` block. In the runner, catch it and convert to `LLMFitTimeoutError`.
**Warning signs:** Tests pass but production timeouts produce unhandled exceptions instead of `LLMFitTimeoutError`.

### Pitfall 2: llmfit returns valid JSON but wrong structure

**What goes wrong:** llmfit exits 0 and returns JSON, but the top-level keys are not `system` and `models` (e.g., an error message as JSON, or a different llmfit subcommand's output).
**Why it happens:** CLI tools can return well-formed JSON for error cases (e.g., `{"error": "no GPU detected"}`).
**How to avoid:** Pydantic validation catches this -- `system` is a required field in `LLMFitResult`, so missing it triggers `ValidationError` which becomes `LLMFitParseError`.
**Warning signs:** `LLMFitParseError` with a valid JSON `raw_output` that clearly is not a recommendation response.

### Pitfall 3: SSH error handling diverges from run_streaming()

**What goes wrong:** The new `run()` method handles asyncssh exceptions differently from `run_streaming()`, leading to inconsistent error types for the same SSH failures.
**Why it happens:** Copy-paste errors or forgetting one of the three exception types (PermissionDenied, DisconnectError, OSError).
**How to avoid:** The `run()` method must have the same `except` block structure as `run_streaming()` (lines 107-116 of ssh_client.py). Test the same error scenarios for both methods.
**Warning signs:** `asyncssh.PermissionDenied` leaking through as an unhandled exception from `run()` while `run_streaming()` wraps it correctly.

### Pitfall 4: Non-zero exit status from llmfit not handled

**What goes wrong:** llmfit exits with status 1 (e.g., nvidia-smi failed, no models found). `SSHClient.run()` raises `RemoteCommandError`. The caller gets a confusing SSH error instead of an llmfit-specific error.
**Why it happens:** D-03 says SSH errors bubble through unchanged. This is correct -- `RemoteCommandError` already includes the command, exit status, and stderr. The caller (future Phase 27 endpoint) maps it to an HTTP response.
**How to avoid:** Do not wrap `RemoteCommandError` in `LLMFitError`. The error already contains all diagnostic info. Document this in the runner's docstring: "Raises RemoteCommandError if llmfit exits non-zero."
**Warning signs:** Developer adds a `try/except RemoteCommandError` in the runner that re-wraps it as `LLMFitError` -- this violates D-03.

## Code Examples

### llmfit JSON fixture for tests

```json
{
  "system": {
    "total_ram_gb": 64.0,
    "available_ram_gb": 58.24,
    "cpu_cores": 16,
    "cpu_name": "AMD EPYC 7742",
    "has_gpu": true,
    "gpu_vram_gb": 80.0,
    "unified_memory": false,
    "backend": "CUDA"
  },
  "models": [
    {
      "name": "llama-3.3-70b",
      "provider": "Meta",
      "parameter_count": "70B",
      "params_b": 70.0,
      "context_length": 131072,
      "use_case": "general",
      "category": "General",
      "release_date": "2024-12-06",
      "fit_level": "perfect",
      "run_mode": "gpu",
      "score": 95.2,
      "estimated_tps": 42.5,
      "runtime": "vLLM",
      "best_quant": "4bit",
      "memory_required_gb": 43.68,
      "utilization_pct": 68.2
    },
    {
      "name": "qwen-2.5-72b-instruct",
      "provider": "Alibaba",
      "parameter_count": "72B",
      "params_b": 72.0,
      "context_length": 131072,
      "use_case": "general",
      "category": "General",
      "release_date": "2025-01-15",
      "fit_level": "good",
      "run_mode": "gpu",
      "score": 88.7,
      "estimated_tps": 38.1,
      "runtime": "vLLM",
      "best_quant": "4bit",
      "memory_required_gb": 45.2,
      "utilization_pct": 72.5
    }
  ]
}
```

Source: llmfit JSON schema from `.planning/research/FEATURES.md` lines 112-146 [CITED: project research FEATURES.md]

### Test pattern: mocking SSHClient.run() for LLMFitRunner

```python
# Source: existing tests/provisioning/test_ssh_client.py pattern
from unittest.mock import AsyncMock, MagicMock

@pytest.fixture
def mock_ssh_client() -> MagicMock:
    client = MagicMock(spec=SSHClient)
    client.run = AsyncMock()
    return client

@pytest.fixture
def runner(mock_ssh_client: MagicMock) -> LLMFitRunner:
    return LLMFitRunner(ssh_client=mock_ssh_client)

async def test_recommend_parses_json(
    runner: LLMFitRunner, mock_ssh_client: MagicMock
) -> None:
    mock_ssh_client.run.return_value = (FIXTURE_JSON, "", 0)
    result = await runner.recommend("gpu-host-01")
    assert result.system.has_gpu is True
    assert len(result.models) == 2
    assert result.models[0].name == "llama-3.3-70b"

async def test_recommend_timeout_raises(
    runner: LLMFitRunner, mock_ssh_client: MagicMock
) -> None:
    mock_ssh_client.run.side_effect = asyncio.TimeoutError()
    with pytest.raises(LLMFitTimeoutError) as exc_info:
        await runner.recommend("gpu-host-01")
    assert exc_info.value.host == "gpu-host-01"

async def test_recommend_invalid_json_raises(
    runner: LLMFitRunner, mock_ssh_client: MagicMock
) -> None:
    mock_ssh_client.run.return_value = ("not json", "", 0)
    with pytest.raises(LLMFitParseError) as exc_info:
        await runner.recommend("gpu-host-01")
    assert exc_info.value.raw_output == "not json"
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| asyncssh `create_process()` + manual timeout | asyncssh `conn.run(timeout=N)` | asyncssh 2.x | Built-in timeout support; no need for `asyncio.wait_for()` unless wrapping for consistency |
| Pydantic v1 `class Config` | Pydantic v2 `model_config = ConfigDict(...)` | Pydantic 2.0 (2023) | v2 syntax required; v1 compat mode deprecated |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | llmfit JSON schema has `system` and `models` top-level keys at v1.1.6 | Code Examples | Models fail to validate; fix by adjusting field names. Low risk -- schema documented in official API.md and verified in project research. |
| A2 | `gpu_name` is not a field in llmfit's `system` object (only `cpu_name` exists) | Pattern 2 | If llmfit does include `gpu_name`, the field works due to default value. `extra="ignore"` handles either case. |
| A3 | asyncssh `conn.run()` returns stdout as `str` (not `bytes`) by default | Pattern 1 | If bytes, need `.decode()`. asyncssh docs say str is default encoding="utf-8". |

## Open Questions

1. **asyncio.TimeoutError vs conn.run(timeout=N)**
   - What we know: D-02 locks `asyncio.wait_for()` as the timeout mechanism. asyncssh `conn.run()` also accepts `timeout=N` natively.
   - What's unclear: Whether to use both (belt and suspenders) or just `asyncio.wait_for()` per D-02.
   - Recommendation: Use `asyncio.wait_for()` only, per D-02. Do not pass `timeout` to `conn.run()` to avoid double-timeout complexity. The `asyncio.wait_for()` cancels the coroutine, which tears down the SSH channel via asyncssh's cleanup.

2. **SystemInfo field name for GPU**
   - What we know: llmfit schema shows `gpu_vram_gb` but no `gpu_name` field. The GPU name might be derivable from other fields or not present.
   - What's unclear: Whether llmfit includes GPU name/model in the system object.
   - Recommendation: Include `gpu_name: str = ""` with a default. `extra="ignore"` handles missing fields. If llmfit adds it later, Pydantic picks it up. If not, it defaults to empty string. Phase 27 can cross-reference with QUADS `gpu_model` data.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 1.4 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `pytest tests/models/test_llmfit.py tests/llmfit/ -x` |
| Full suite command | `pytest` |

### Phase Requirements -> Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| EXEC-01 | Runner SSHes to host, runs llmfit, returns parsed models | unit | `pytest tests/llmfit/test_runner.py::TestRecommend -x` | Wave 0 |
| EXEC-01 | SSHClient.run() executes command and returns output | unit | `pytest tests/provisioning/test_ssh_client.py::TestSSHClientRun -x` | Wave 0 |
| EXEC-02 | Timeout raises LLMFitTimeoutError | unit | `pytest tests/llmfit/test_runner.py::TestRecommendTimeout -x` | Wave 0 |
| EXEC-03 | Pydantic models parse valid llmfit JSON | unit | `pytest tests/models/test_llmfit.py::TestLLMFitResult -x` | Wave 0 |
| EXEC-03 | Invalid JSON raises LLMFitParseError | unit | `pytest tests/llmfit/test_runner.py::TestRecommendParseError -x` | Wave 0 |
| EXEC-03 | Missing required fields raise LLMFitParseError | unit | `pytest tests/models/test_llmfit.py::TestModelValidation -x` | Wave 0 |
| EXEC-03 | Extra fields ignored (forward compat) | unit | `pytest tests/models/test_llmfit.py::TestExtraFieldsIgnored -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/models/test_llmfit.py tests/llmfit/ -x`
- **Per wave merge:** `pytest`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/models/test_llmfit.py` -- covers EXEC-03 (model parsing, validation, extra fields)
- [ ] `tests/llmfit/__init__.py` -- package init
- [ ] `tests/llmfit/test_runner.py` -- covers EXEC-01, EXEC-02 (runner execution, timeout, parse errors)
- [ ] `tests/provisioning/test_ssh_client.py` -- extend existing file with `TestSSHClientRun` class for new `run()` method

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | SSH auth handled by existing SSHClient (key-based) |
| V3 Session Management | no | No sessions in this phase |
| V4 Access Control | no | No API endpoint in this phase |
| V5 Input Validation | yes | Pydantic model_validate on external JSON input (llmfit output) |
| V6 Cryptography | no | No crypto operations |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Malicious llmfit JSON output (compromised binary) | Tampering | Pydantic strict validation; `extra="ignore"` drops unexpected fields; frozen models prevent mutation after parse |
| Command injection via hostname | Tampering | hostname is used as SSH host argument to asyncssh, not interpolated into shell commands. asyncssh handles escaping. |
| Timeout denial of service | Denial of Service | 60s timeout prevents indefinite hangs per EXEC-02 |

## Project Constraints (from CLAUDE.md)

- **SOLID principles required** -- LLMFitRunner uses DI (SSHClient injected via constructor). Error hierarchy uses proper inheritance. Models are single-responsibility (one file for data models, one for errors, one for runner).
- **Tech stack**: Python, FastAPI, asyncssh, Pydantic -- no new dependencies allowed for v1.6.
- **Env var sync**: Not applicable this phase (no settings, no .env changes).
- **GSD workflow**: All changes go through GSD execution.

## Sources

### Primary (HIGH confidence)
- asyncssh `conn.run()` docstring -- timeout parameter, SSHCompletedProcess return type, check parameter [VERIFIED: runtime inspection of asyncssh 2.24.0]
- Existing `ssh_client.py` -- error handling pattern, connection parameters, run_streaming() implementation [VERIFIED: codebase read]
- Existing `models/quads.py`, `models/node.py` -- Pydantic model patterns (frozen, ConfigDict) [VERIFIED: codebase read]
- Existing `redfish/errors.py` -- error hierarchy pattern [VERIFIED: codebase read]
- llmfit JSON schema from `.planning/research/FEATURES.md` -- field names, types, structure [CITED: project research files]

### Secondary (MEDIUM confidence)
- llmfit official documentation -- JSON schema details, CLI flags [CITED: alexsjones-llmfit.mintlify.app]
- asyncssh GitHub issues #626, #411 -- timeout behavior details [CITED: github.com/ronf/asyncssh]

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- zero new dependencies, all patterns exist in codebase
- Architecture: HIGH -- follows existing SSHClient, Pydantic model, and error hierarchy patterns exactly
- Pitfalls: HIGH -- verified against existing code, asyncssh docs, and project research PITFALLS.md

**Research date:** 2026-07-24
**Valid until:** 2026-08-24 (stable -- no external dependency changes)
