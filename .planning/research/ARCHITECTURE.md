# Architecture: llmfit Integration (v1.6)

**Domain:** LLM hardware-model fitting within existing inference gateway provisioning
**Researched:** 2026-07-23
**Confidence:** HIGH

## Executive Decision

llmfit is a standalone on-demand operation, NOT embedded in the provisioning state machine. The operator flow is: run llmfit on a reachable server, review recommendations, then provision with a chosen model. This keeps the existing provisioning pipeline untouched and adds llmfit as a parallel capability.

## Why On-Demand, Not Inline

The requirements state "Operator reviews recommendations and selects which model to deploy." This is a human-in-the-loop decision. Embedding it in the automated provisioning pipeline would mean either:
- Blocking provisioning until a human picks a model (breaks the async fire-and-forget pattern)
- Auto-selecting a model (removes the human decision the requirements call for)

Neither works. llmfit runs separately: the operator clicks "Get Recommendations" on a server, reviews results, then clicks "Setup" with a model override. Two independent actions, not one pipeline.

## When llmfit Can Run

llmfit needs `nvidia-smi` to detect GPU VRAM on NVIDIA systems (the target hardware). This means:
- **After setup.sh** has installed NVIDIA drivers -- works on any provisioned or partially set-up server
- **On already-running servers** -- works on any server where GPU drivers exist
- **NOT on bare/available QUADS hosts** that lack drivers (unless `--memory` override is used)

The `--memory` flag lets llmfit run even without `nvidia-smi` by manually specifying VRAM, but running llmfit remotely via SSH on a provisioned host is the primary path because it detects actual hardware.

## Architecture Overview

```
Operator clicks "Recommendations" on a node row
        |
        v
  Admin API: GET /admin/nodes/{hostname}/recommendations
        |
        v
  Check in-memory cache (hostname -> recommendations + timestamp)
        |
   [cache hit & fresh]          [cache miss or stale]
        |                              |
        v                              v
  Return cached results      SSH to host: "llmfit recommend --json --limit N --force-runtime vllm"
                                       |
                                       v
                              Parse JSON stdout -> Pydantic models
                                       |
                                       v
                              Store in cache, return to operator
```

## Component Boundaries

| Component | Responsibility | New/Modified | Communicates With |
|-----------|---------------|--------------|-------------------|
| `llmfit/runner.py` | SSH exec of llmfit CLI, JSON parsing, cache | **NEW** | SSHClient |
| `models/llmfit.py` | Pydantic models for llmfit JSON response | **NEW** | runner, admin API |
| `api/admin.py` | New endpoint: `GET /admin/nodes/{hostname}/recommendations` | **MODIFIED** (add 1 route) | LLMFitRunner via dependency |
| `config/settings.py` | `LLMFitSettings` nested config | **MODIFIED** (add 1 sub-model) | Settings root |
| `config/dependencies.py` | `get_llmfit_runner` dependency provider | **MODIFIED** (add 1 function) | app.state |
| `main.py` | Wire LLMFitRunner in lifespan | **MODIFIED** (add ~5 lines) | LLMFitRunner |
| `auto-vllm/setup.sh` | Add llmfit install step | **MODIFIED** (add ~8 lines) | Remote host |
| Dashboard templates + JS | Recommendations button/modal per node | **MODIFIED** | Admin API |

### What Does NOT Change

- `provisioning/provisioner.py` -- no new ProvisioningStep, no changes to provision() flow
- `provisioning/state.py` -- no new enum members
- `discovery/*` -- no etcd schema changes
- `models/node.py` -- no Node model changes
- `proxy/*`, `routing/*`, `resilience/*` -- untouched

## New Components Detail

### 1. `inference_proxy/llmfit/runner.py`

Single class. Runs `llmfit recommend --json` over SSH, parses output, caches results.

```python
class LLMFitError(Exception):
    """Raised when llmfit execution fails."""
    def __init__(self, hostname: str, reason: str) -> None:
        self.hostname = hostname
        self.reason = reason
        super().__init__(f"llmfit on {hostname}: {reason}")


class LLMFitRunner:
    """Runs llmfit on remote hosts via SSH and parses recommendations.

    Reuses the existing SSHClient (DIP, same pattern as NodeProvisioner).
    In-memory cache with TTL -- hardware does not change between calls.
    """

    def __init__(
        self,
        ssh_client: SSHClient,
        settings: LLMFitSettings,
    ) -> None:
        self._ssh = ssh_client
        self._settings = settings
        self._cache: dict[str, tuple[float, LLMFitResponse]] = {}
        # ponytail: dict cache, upgrade to LRU if memory matters at >100 hosts

    async def get_recommendations(
        self,
        hostname: str,
        *,
        use_case: str | None = None,
    ) -> LLMFitResponse:
        """Return model recommendations for hostname, cached by TTL."""
        cache_key = f"{hostname}:{use_case or 'all'}"
        now = asyncio.get_running_loop().time()

        cached = self._cache.get(cache_key)
        if cached and (now - cached[0]) < self._settings.cache_ttl:
            return cached[1]

        cmd = self._build_command(use_case=use_case)
        stdout = await self._run_remote(hostname, cmd)
        response = self._parse_response(hostname, stdout)
        self._cache[cache_key] = (now, response)
        return response

    def _build_command(self, *, use_case: str | None = None) -> str:
        parts = [
            "llmfit", "recommend", "--json",
            "--limit", str(self._settings.recommend_limit),
        ]
        if self._settings.default_runtime:
            parts.extend(["--force-runtime", self._settings.default_runtime])
        if use_case:
            parts.extend(["--use-case", use_case])
        return " ".join(parts)

    async def _run_remote(self, hostname: str, command: str) -> str:
        lines: list[str] = []
        async for stream, line in self._ssh.run_streaming(hostname, command):
            if stream == "stdout":
                lines.append(line)
        return "\n".join(lines)

    @staticmethod
    def _parse_response(hostname: str, raw: str) -> LLMFitResponse:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LLMFitError(hostname, f"invalid JSON: {exc}") from exc
        try:
            return LLMFitResponse.model_validate(data)
        except ValidationError as exc:
            raise LLMFitError(hostname, f"unexpected response shape: {exc}") from exc
```

Key behaviors:
- Reuses existing SSHClient via constructor injection (same DIP pattern as provisioner)
- Cache keyed by `hostname:use_case` with configurable TTL (default 1 hour)
- `--force-runtime vllm` because this system deploys vLLM, not ollama/llama.cpp
- `SSHConnectionError` and `RemoteCommandError` propagate naturally from SSHClient -- the runner only catches JSON/validation failures

### 2. `inference_proxy/models/llmfit.py`

Pydantic models for the llmfit JSON response. Uses `extra="ignore"` so we don't break when llmfit adds new fields. We only model what we display.

```python
class ScoreComponents(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    quality: float = 0.0
    speed: float = 0.0
    fit: float = 0.0
    context: float = 0.0


class ModelRecommendation(BaseModel):
    """A single model recommendation from llmfit."""
    model_config = ConfigDict(frozen=True, extra="ignore")

    name: str                          # e.g. "Qwen/Qwen2.5-Coder-7B-Instruct"
    provider: str                      # e.g. "Qwen"
    parameter_count: str               # e.g. "7B"
    params_b: float                    # e.g. 7.0
    fit_level: str                     # perfect | good | marginal | too_tight
    fit_label: str                     # "Perfect" | "Good" | ...
    score: float                       # composite ranking score
    score_components: ScoreComponents
    run_mode: str                      # gpu | moe | cpu_gpu | cpu
    best_quant: str                    # e.g. "Q5_K_M"
    memory_required_gb: float
    memory_available_gb: float
    utilization_pct: float
    estimated_tps: float | None = None
    use_case: str = ""
    context_length: int = 0
    usable_context: int = 0
    license: str = ""


class HardwareInfo(BaseModel):
    """Detected hardware from llmfit's system envelope."""
    model_config = ConfigDict(frozen=True, extra="ignore")
    # Populated from llmfit's "system" object -- exact fields TBD
    # from running llmfit on real hardware. extra="ignore" handles unknowns.


class LLMFitResponse(BaseModel):
    """Top-level response from llmfit recommend --json."""
    model_config = ConfigDict(frozen=True, extra="ignore")

    system: HardwareInfo
    models: list[ModelRecommendation]
    total_models: int = 0
    returned_models: int = 0
```

**Schema source:** The field names come from llmfit's [API.md](https://github.com/AlexsJones/llmfit/blob/main/API.md) which documents the REST API response format. The CLI `--json` output uses the same structure (per API.md: "CLI-only legacy overload" uses human strings for some label fields). The `extra="ignore"` config ensures forward compatibility.

**Note:** The `HardwareInfo` model is intentionally sparse. The exact fields from llmfit's `system` envelope should be filled in after running `llmfit recommend --json` on actual lab hardware. Using `extra="ignore"` means missing or unexpected fields won't cause parse failures.

### 3. Admin API Endpoint

One new route in `api/admin.py`:

```python
@admin_router.get("/nodes/{hostname}/recommendations")
async def get_recommendations(
    hostname: str,
    use_case: str | None = None,
    llmfit_runner: LLMFitRunner = Depends(get_llmfit_runner),
) -> LLMFitResponse:
    """Return llmfit model recommendations for a node's hardware."""
    hostname = _validated_hostname(hostname)
    try:
        return await llmfit_runner.get_recommendations(
            hostname, use_case=use_case,
        )
    except LLMFitError as exc:
        raise HTTPException(status_code=502, detail=exc.reason) from exc
    except (SSHConnectionError, RemoteCommandError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
```

Query params:
- `use_case` (optional): `general`, `coding`, `reasoning`, `chat`, `multimodal`, `embedding`
- No `limit` param exposed -- use the configured default from settings

Error mapping follows the Redfish pattern: domain errors -> 502 (bad gateway to backend tool).

### 4. Settings

```python
class LLMFitSettings(BaseModel):
    """llmfit CLI configuration."""
    recommend_limit: int = 20
    cache_ttl: int = 3600           # 1 hour -- hardware doesn't change
    install_command: str = "curl -fsSL https://llmfit.axjns.dev/install.sh | sh"
    default_runtime: str = "vllm"   # --force-runtime flag value
```

Added to `Settings` root as `llmfit: LLMFitSettings = LLMFitSettings()`.

Env vars: `INFERENCE_PROXY_LLMFIT__RECOMMEND_LIMIT`, `INFERENCE_PROXY_LLMFIT__CACHE_TTL`, etc.

### 5. setup.sh Change

Add llmfit installation after vllm_install, before firewall:

```bash
install_llmfit() {
    if command -v llmfit &>/dev/null; then
        echo "llmfit already installed, skipping"
        return 0
    fi
    curl -fsSL https://llmfit.axjns.dev/install.sh | sh
}

step llmfit_install install_llmfit
```

This adds a `llmfit_install` step marker that the provisioner already handles. The `STEP_PATTERN` regex in provisioner.py matches arbitrary step names (`\w+`). Unknown step names are logged at info level but do not need a ProvisioningStep enum member -- the provisioner only calls `_update_state` for known steps and silently ignores unknowns (line 339-341 in provisioner.py: `except ValueError: pass`).

### 6. Dependency Provider

```python
# In config/dependencies.py
def get_llmfit_runner(request: Request) -> LLMFitRunner:
    """Return the LLMFit runner from app state."""
    return request.app.state.llmfit_runner  # type: ignore[no-any-return]
```

### 7. Lifespan Wiring (main.py)

```python
# After ssh_client creation, before provisioner creation:
from inference_proxy.llmfit.runner import LLMFitRunner

llmfit_runner = LLMFitRunner(ssh_client, resolved_settings.llmfit)
app.state.llmfit_runner = llmfit_runner
```

No shutdown cleanup needed -- LLMFitRunner holds no connections or threads. The SSH connections are per-call.

## Data Flow

### Happy Path: GET /admin/nodes/{hostname}/recommendations

```
1. Admin API validates hostname via _validated_hostname()
2. LLMFitRunner.get_recommendations() called
3. Cache check: key = "{hostname}:{use_case}", compare age vs TTL
4. Cache miss -> SSH to hostname
5. SSHClient.run_streaming(hostname, "llmfit recommend --json --limit 20 --force-runtime vllm")
6. Collect stdout lines (stderr from SSHClient raises RemoteCommandError on non-zero exit)
7. json.loads(stdout) -> dict
8. LLMFitResponse.model_validate(data) with extra="ignore"
9. Store in cache: {key: (now, response)}
10. Return LLMFitResponse (FastAPI serializes to JSON automatically)
```

### Error Cases

| Error | Source | HTTP Status | Detail |
|-------|--------|-------------|--------|
| SSH unreachable | SSHConnectionError | 502 | "SSH connection to {host} failed: ..." |
| llmfit not installed | RemoteCommandError (exit 127) | 502 | "Command 'llmfit ...' on {host} exited with status 127" |
| llmfit exits non-zero | RemoteCommandError | 502 | "Command 'llmfit ...' on {host} exited with status {N}" |
| JSON parse error | LLMFitError | 502 | "invalid JSON: ..." |
| Pydantic validation error | LLMFitError | 502 | "unexpected response shape: ..." |
| No GPUs detected | llmfit returns CPU-only results | 200 | Normal response with run_mode="cpu" models |
| Invalid hostname | HTTPException from validator | 400 | "Invalid hostname" |

All backend errors use 502 (bad gateway). This matches the Redfish error pattern.

### Cache Behavior

- **Key:** `{hostname}:{use_case or 'all'}` -- different use_case filters get separate cache entries
- **TTL:** Default 3600s (1 hour). Hardware doesn't change. llmfit's model DB only updates with new llmfit releases.
- **Invalidation:** TTL-only. No explicit invalidation endpoint (YAGNI). Gateway restart clears cache.
- **Memory:** ~50KB per cached response (20 model recommendations). At 100 hosts = 5MB. Negligible.
- **Concurrency:** No lock. Worst case: two concurrent requests for the same host both SSH and parse. Second write overwrites first. Both get correct data. Not worth a lock.

## Patterns to Follow

### Pattern: SSH Client Reuse (Provisioner Precedent)

llmfit follows the exact same pattern as `provisioner._ssh_run_command()`: inject SSHClient, call run_streaming(), collect output.

### Pattern: Dependency Provider via app.state (All Services)

Create in lifespan, store in app.state, expose via dependency function. Same as provisioner, redfish_client, quads_client.

### Pattern: Error Wrapping (Redfish Precedent)

Typed domain error (`LLMFitError`) with hostname + reason. Route handler maps to HTTPException(502). Same shape as `RedfishError`.

### Pattern: Extra="ignore" for External JSON (Forward Compatibility)

llmfit is actively developed (21k+ stars, frequent releases). The JSON schema will evolve. `extra="ignore"` in Pydantic means we parse what we need and ignore new fields without breaking.

## Anti-Patterns to Avoid

### Anti-Pattern: Embedding in ProvisioningStep Enum

**What:** Adding `LLMFIT_SCAN` to ProvisioningStep and running it inline during `provision()`.
**Why bad:** The requirements specify human-in-the-loop model selection. Inline execution either blocks provisioning (waiting for operator choice) or forces auto-selection (bypasses operator review). It also couples llmfit availability to provisioning success -- if llmfit fails, provisioning fails.
**Instead:** Keep llmfit as an independent on-demand operation. Provisioning continues to work exactly as before.

### Anti-Pattern: Storing Recommendations in etcd

**What:** Writing llmfit results to etcd under `/llmfit/{hostname}`.
**Why bad:** Recommendations are ephemeral read-only data. They don't need persistence across gateway restarts. etcd is for service registry state, not cached CLI output. Adding keys to etcd increases watch traffic for no benefit.
**Instead:** In-memory dict cache with TTL. Gateway restart = cold cache = next request re-runs llmfit (~3 seconds).

### Anti-Pattern: Running llmfit on the Gateway Host

**What:** Installing llmfit on the gateway and using `--memory` override based on QUADS GPU metadata.
**Why bad:** The gateway doesn't have the target GPU hardware. QUADS metadata gives GPU model name but not exact VRAM (different SKUs of the same GPU model can have different VRAM). Running on the target host gives accurate detection. The `--memory` path is a fallback, not the primary mode.
**Instead:** SSH to the target host where llmfit detects real hardware via nvidia-smi.

### Anti-Pattern: Creating a New Provisioning Flow

**What:** Splitting provisioning into "setup phase" and "start phase" with llmfit/model selection in between.
**Why bad:** Over-engineers the current flow. The existing provisioning works end-to-end with auto-detected models. llmfit is an optional advisory tool -- operators who don't use it should see no change. Adding model override to SetupRequest (a future enhancement) is simpler than restructuring the pipeline.
**Instead:** llmfit is independent. Setup request optionally gains a `model` field later if needed.

## File Layout

```
inference_proxy/
    llmfit/
        __init__.py              # NEW
        runner.py                # NEW: LLMFitRunner (SSH + JSON parse + cache)
    models/
        llmfit.py                # NEW: LLMFitResponse, ModelRecommendation, etc.
    config/
        settings.py              # MODIFY: add LLMFitSettings sub-model
        dependencies.py          # MODIFY: add get_llmfit_runner()
    api/
        admin.py                 # MODIFY: add GET /admin/nodes/{hostname}/recommendations
    main.py                      # MODIFY: wire LLMFitRunner in lifespan (~5 lines)
    auto-vllm/
        setup.sh                 # MODIFY: add llmfit_install step (~8 lines)
    templates/
        dashboard.html           # MODIFY: add recommendations button/modal
    static/js/
        dashboard.js             # MODIFY: add recommendations action + UI

tests/
    llmfit/
        __init__.py              # NEW
        test_runner.py           # NEW: mock SSH, fixture JSON, verify parse + cache
    api/
        test_admin.py            # MODIFY: test recommendations endpoint
```

New files: 4 production + 2 test.
Modified files: 5 production + 1 test.

## Build Order (Suggested Phases)

Dependencies flow top-down. Each phase is independently testable.

### Phase 1: Pydantic Models + LLMFitRunner + Tests

Files: `models/llmfit.py`, `llmfit/__init__.py`, `llmfit/runner.py`, `tests/llmfit/test_runner.py`
Dependencies: SSHClient (exists)
Tests: Mock SSHClient, feed fixture JSON from llmfit API.md schema, verify parsing + cache TTL behavior
**Deliverable:** Core logic exists and is tested. Nothing wired into the app yet.

### Phase 2: Settings + Dependency Wiring

Files: `config/settings.py` (add LLMFitSettings), `config/dependencies.py` (add getter), `main.py` (wire in lifespan), `.env.example` (add llmfit settings)
Dependencies: Phase 1
**Deliverable:** LLMFitRunner is created at startup and available via Depends().

### Phase 3: Admin API Endpoint + Tests

Files: `api/admin.py` (add 1 route), `tests/api/test_admin.py` (add recommendation tests)
Dependencies: Phase 2
**Deliverable:** `GET /admin/nodes/{hostname}/recommendations` returns llmfit data.

### Phase 4: setup.sh llmfit Installation

Files: `auto-vllm/setup.sh` (add llmfit_install step)
Dependencies: None (independent of phases 1-3, can run in parallel)
**Deliverable:** New nodes get llmfit installed during provisioning setup.

### Phase 5: Dashboard UI

Files: `templates/dashboard.html`, `static/js/dashboard.js`
Dependencies: Phase 3 (needs the API endpoint)
**Deliverable:** "Recommendations" button per node opens a modal/panel with ranked model list, fit levels, scores, memory requirements.

## Sources

- [llmfit GitHub](https://github.com/AlexsJones/llmfit) -- tool overview, installation methods (HIGH confidence)
- [llmfit API.md (JSON schema)](https://github.com/AlexsJones/llmfit/blob/main/API.md) -- response field definitions (HIGH confidence)
- [llmfit CLI reference](https://github.com/AlexsJones/llmfit/blob/main/docs/cli.md) -- subcommands, flags, use-case values (HIGH confidence)
- [llmfit platform support](https://github.com/AlexsJones/llmfit/blob/main/docs/platform-support.md) -- Linux GPU detection requirements (HIGH confidence)
- [llmfit install script](https://llmfit.axjns.dev/install.sh) -- quick binary install (MEDIUM confidence)
- Existing codebase: provisioner.py, ssh_client.py, admin.py, settings.py, dependencies.py, main.py (HIGH confidence)
