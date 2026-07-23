# Stack Research

**Domain:** llmfit CLI integration for hardware-aware model recommendations (v1.6 milestone)
**Researched:** 2026-07-23
**Confidence:** HIGH
**Scope:** Stack additions for integrating the llmfit Rust CLI tool into node provisioning. llmfit is installed on and runs on target GPU servers, not the gateway. The gateway runs llmfit via SSH and parses JSON output. Existing stack (Python 3.12, FastAPI, httpx, etcd3gw, asyncssh, structlog, Pydantic v2, Jinja2) is validated and NOT re-evaluated here.

## New Python Dependencies for v1.6

**None.**

Zero new runtime or dev dependencies. The entire integration is: run a command over SSH, parse JSON output with stdlib `json`, validate with Pydantic.

## Why No New Python Dependencies

### llmfit Is a Remote CLI Tool, Not a Python Library

llmfit is a Rust binary that runs on the target GPU server, not on the gateway. The integration pattern is identical to the existing `nvidia-smi` GPU verification in `provisioner.py`:

1. SSH to host (asyncssh -- already installed)
2. Run command (`llmfit recommend --json --limit 10`)
3. Capture stdout (existing `SSHClient.run_streaming()` or `_ssh_run_command()`)
4. Parse JSON (stdlib `json.loads()`)
5. Validate with Pydantic model (Pydantic -- already installed)
6. Return via FastAPI endpoint (FastAPI -- already installed)

Every piece of this chain already exists in the codebase.

### llmfit Installation on Target Servers

llmfit must be installed on target GPU servers during provisioning. The installation is a shell command executed via SSH, not a Python dependency.

**Recommended installation method:** Pre-built binary download from GitHub releases.

```bash
curl -fsSL https://github.com/AlexsJones/llmfit/releases/download/v1.1.6/llmfit-v1.1.6-x86_64-unknown-linux-gnu.tar.gz \
  | tar xz -C /usr/local/bin/
```

**Why pre-built binary over other options:**

| Method | Verdict | Reason |
|--------|---------|--------|
| Pre-built binary (GitHub release) | **USE** | Single curl+tar, no dependencies, ~5 seconds, pinnable version |
| `curl -fsSL llmfit.axjns.dev/install.sh \| sh` | REJECT | Runs unaudited remote script as root. Fine interactively, wrong for automated provisioning. |
| `cargo install llmfit` | REJECT | Requires Rust toolchain on target servers. Compilation takes minutes. Adding a build toolchain to GPU inference nodes is waste. |
| `brew install llmfit` | REJECT | Homebrew on RHEL/Fedora lab servers is non-standard. Adds package manager complexity. |
| `uv tool install llmfit` (Python wrapper) | REJECT | llmfit has a Python shim on PyPI but it just wraps the Rust binary. Adds uv/pip dependency on target nodes. The gateway has uv; the target GPU nodes should not need it. |
| Podman/Docker container | REJECT | llmfit needs to detect host hardware (GPU, RAM, CPU). Container isolation may hide GPUs unless CDI/device passthrough is configured. Bare-metal binary is simpler and more reliable. |

**Version pinning:** Hardcode the version in the provisioning script or settings. llmfit is actively developed (v1.1.6 released 2026-07-21, 30K+ GitHub stars). Pin to a known-good version and bump deliberately.

### llmfit JSON Output Schema

llmfit `recommend --json` produces a well-structured JSON envelope. The fields we need for model recommendation:

**Envelope:**

| Field | Type | Purpose |
|-------|------|---------|
| `system` | object | Detected hardware (GPU VRAM, RAM, CPU) |
| `total_models` | int | Total models matching |
| `returned_models` | int | Count returned |
| `models` | array | Ranked model recommendations |

**Per-model fields we consume:**

| Field | Type | Example | Purpose |
|-------|------|---------|---------|
| `name` | string | `"Qwen/Qwen2.5-Coder-7B-Instruct"` | Full HuggingFace model ID |
| `parameter_count` | string | `"7B"` | Human display |
| `params_b` | float | `7.0` | Numeric params for sorting |
| `fit_level` | string | `"good"` | `perfect`, `good`, `marginal`, `too_tight` |
| `score` | float | `86.5` | Composite ranking score |
| `score_components` | object | `{quality, speed, fit, context}` | Score breakdown |
| `estimated_tps` | float | `42.5` | Estimated tokens/second |
| `memory_required_gb` | float | `5.8` | VRAM needed |
| `memory_available_gb` | float | `12.0` | VRAM detected |
| `utilization_pct` | float | `48.3` | Memory utilization |
| `best_quant` | string | `"Q5_K_M"` | Recommended quantization |
| `context_length` | int | `32768` | Native context window |
| `use_case` | string | `"Coding"` | Category |
| `runtime` | string | `"llamacpp"` | Recommended runtime |
| `license` | string | `"apache-2.0"` | License info |
| `supports_tp` | array | `[1, 2, 4]` | Tensor parallelism degrees |
| `disk_size_gb` | float | `5.1` | On-disk size at best_quant |

**Fields we can ignore:** `gguf_sources`, `ollama_name`, `verify_command`, `measured_tps`, `estimate_basis`, `installed`, `capability_ids`, `notes`. These are relevant for local llama.cpp/Ollama use cases, not for vLLM serving.

**Important context:** llmfit's default recommendations are oriented toward local inference runtimes (llama.cpp, MLX, Ollama). For vLLM serving, the hardware detection (GPU count, VRAM per GPU, total VRAM) is the primary value. The model rankings may not perfectly match vLLM's memory requirements since vLLM uses different quantization and tensor parallelism strategies. The `--force-runtime vllm` flag exists and should be used.

### Pydantic Models for llmfit Output

Define Pydantic models to validate llmfit JSON output. This is pure Pydantic (already installed), no new libraries:

```python
class LLMFitScoreComponents(BaseModel):
    quality: float
    speed: float
    fit: float
    context: float

class LLMFitModelRecommendation(BaseModel):
    name: str
    parameter_count: str
    params_b: float
    fit_level: str  # perfect, good, marginal, too_tight
    score: float
    score_components: LLMFitScoreComponents
    estimated_tps: float
    memory_required_gb: float
    memory_available_gb: float
    utilization_pct: float
    best_quant: str
    context_length: int
    use_case: str
    runtime: str
    license: str
    supports_tp: list[int] = []
    disk_size_gb: float = 0.0

class LLMFitResponse(BaseModel):
    total_models: int
    returned_models: int
    models: list[LLMFitModelRecommendation]
```

Use `model_config = ConfigDict(extra="ignore")` so new fields llmfit adds in future versions do not break parsing.

## Integration Points with Existing App

### SSH Execution (Existing Pattern)

The `SSHClient._ssh_run_command()` helper already collects stdout from a remote command into a string. llmfit integration follows the exact same pattern as `_verify_gpu()` in `provisioner.py`:

```python
# Existing pattern in provisioner.py:
gpu_output = await self._ssh_run_command(hostname, "nvidia-smi ...")

# llmfit follows same pattern:
llmfit_output = await self._ssh_run_command(hostname, "llmfit recommend --json --limit 10 --force-runtime vllm")
```

### llmfit Installation During Provisioning

llmfit installation should be a step in `setup.sh` or a separate script uploaded during provisioning. It runs after system setup but can run before or after NVIDIA driver installation (llmfit detects GPUs but does not require drivers to be installed for hardware inventory -- it reads PCI device info).

However, for accurate model recommendations including VRAM detection, llmfit should run **after** NVIDIA drivers are installed so it can detect GPU memory via `nvidia-smi` or NVML.

### Admin API Extension

New endpoint following existing patterns:

```
GET /admin/nodes/{hostname}/recommendations -> LLMFitRecommendationsResponse
```

This endpoint SSHes to the host, runs llmfit, parses output, and returns recommendations. It is an on-demand operation (operator clicks a button), not part of the provisioning sequence.

### Provisioning Flow Change

The provisioning flow does NOT change for v1.6. llmfit recommendations are a **pre-provisioning** step: the operator checks recommendations, picks a model, then starts provisioning with that model. The `provision()` method's sequence stays the same.

### ProvisioningStep Enum

No new enum values needed. llmfit runs outside the provisioning state machine -- it is an advisory query, not a provisioning step.

### Settings

Minimal new config:

```python
class LLMFitSettings(BaseModel):
    """llmfit CLI configuration."""
    version: str = "v1.1.6"  # pinned version for binary download
    binary_path: str = "/usr/local/bin/llmfit"  # install location on target
    recommend_limit: int = 10  # --limit flag
    install_timeout: int = 60  # seconds for download+install
```

Env var: `INFERENCE_PROXY_LLMFIT__VERSION`, `INFERENCE_PROXY_LLMFIT__RECOMMEND_LIMIT`, etc.

## Alternatives Considered

| Recommended | Alternative | Why Not |
|-------------|-------------|---------|
| Run llmfit CLI via SSH | Build Python hardware detection | llmfit already exists, is well-maintained (30K stars), detects GPU/RAM/CPU accurately, and ranks models. Reimplementing this in Python is months of work for an inferior result. |
| Pre-built binary download | `cargo install` on target | Requires Rust toolchain on GPU servers. Compilation is slow. Binary download is seconds. |
| Pre-built binary download | Install script (`curl \| sh`) | Unaudited remote script in automated provisioning. Pre-built binary is more controlled. |
| `--force-runtime vllm` flag | Default runtime detection | llmfit defaults to llama.cpp/MLX/Ollama. We serve with vLLM. Force the runtime to get relevant recommendations. |
| On-demand SSH execution | Cache recommendations in etcd | Hardware does not change. Cache adds complexity for no benefit -- the operator queries once, picks a model, and provisions. YAGNI. |
| Pydantic model with `extra="ignore"` | Parse raw dict | Pydantic gives type safety and forward compatibility. Already in the stack. Zero cost. |
| `_ssh_run_command()` (existing) | New SSH execution method | The existing helper collects stdout into a string. That is exactly what we need. |

## What NOT to Add

| Technology | Why Not |
|------------|---------|
| Any Python GPU detection library (`gputil`, `pynvml`, `nvidia-ml-py`) | llmfit handles hardware detection on the target server. The gateway never touches GPUs. |
| `subprocess` / local llmfit execution | llmfit must run on the target server to detect that server's hardware, not on the gateway. |
| Model database / SQLite | Recommendations are queried on-demand from live hardware. No persistence needed. |
| Background polling for recommendations | Hardware does not change between queries. On-demand is correct. |
| WebSocket for recommendation streaming | llmfit `recommend --json` returns in ~2 seconds. No streaming needed. HTTP request/response is fine. |
| New HTTP client library | httpx is not involved. This is pure SSH + JSON parsing. |
| Task queue (Celery, etc.) | Running llmfit takes ~2 seconds. An asyncio task or even a synchronous endpoint is fine. No queue needed. |
| Custom model ranking algorithm | llmfit's scoring (quality, speed, fit, context) is well-designed. Use it, do not reinvent it. |
| `requests` library | Not needed. No HTTP calls to external services. SSH only. |

## Installation

```bash
# No new Python dependencies to install on the gateway.
# Existing pyproject.toml already has everything needed.

# On target servers (during provisioning, via SSH):
curl -fsSL https://github.com/AlexsJones/llmfit/releases/download/v1.1.6/llmfit-v1.1.6-x86_64-unknown-linux-gnu.tar.gz \
  | tar xz -C /usr/local/bin/
```

## Key Version Constraints

No new Python version constraints. All existing constraints from v1.5 remain valid.

| Existing Dependency | Minimum | Still Valid | v1.6 Relevance |
|---------------------|---------|-------------|----------------|
| asyncssh >= 2.20 | SSH client | Yes | Runs llmfit on remote hosts, downloads binary |
| Pydantic >= 2.10 | Model validation | Yes | New Pydantic models for llmfit JSON output |
| FastAPI >= 0.135 | HTTP framework | Yes | New admin endpoint for recommendations |
| structlog >= 26.1.0 | Structured logging | Yes | llmfit operation logging |

**External tool version:**

| Tool | Version | Where | Why This Version |
|------|---------|-------|------------------|
| llmfit | v1.1.6 | Target GPU servers (not gateway) | Latest stable release (2026-07-21). Pre-built binaries available for x86_64 linux (gnu and musl). Supports `--json`, `--force-runtime vllm`, `--limit`. |

## Sources

- llmfit GitHub: https://github.com/AlexsJones/llmfit -- v1.1.6 (July 2026), 30K+ stars, Rust CLI
- llmfit README: https://github.com/AlexsJones/llmfit/blob/main/README.md -- installation methods, CLI usage
- llmfit CLI docs: https://github.com/AlexsJones/llmfit/blob/main/docs/cli.md -- `recommend --json --limit --force-runtime --use-case` flags
- llmfit API docs: https://github.com/AlexsJones/llmfit/blob/main/API.md -- full JSON response schema for model recommendations
- llmfit releases: https://github.com/AlexsJones/llmfit/releases/tag/v1.1.6 -- pre-built binaries for linux x86_64 (gnu, musl), aarch64
- Existing codebase: `inference_proxy/provisioning/provisioner.py` -- `_verify_gpu()` and `_ssh_run_command()` patterns to follow
- Existing codebase: `inference_proxy/provisioning/ssh_client.py` -- SSHClient with `run_streaming()` and `upload()`
- Existing codebase: `inference_proxy/api/admin.py` -- admin endpoint patterns
- Existing codebase: `inference_proxy/config/settings.py` -- settings model patterns

---
*Stack research for: llmfit CLI integration for hardware-aware model recommendations (v1.6)*
*Researched: 2026-07-23*
