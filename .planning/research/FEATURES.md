# Feature Landscape

**Domain:** LLM model recommendation integration (llmfit CLI) into GPU server provisioning gateway
**Researched:** 2026-07-23

## Existing Infrastructure (Already Built)

The provisioning system provides the foundation these features plug into:

| Component | What It Does | New Features Build On |
|-----------|-------------|----------------------|
| `NodeProvisioner` | 16-step state machine with SSH orchestration, step markers, background tasks | llmfit runs as new SSH command; new provisioning step for install |
| `SSHClient` | asyncssh wrapper with `run_streaming()` and `upload()` | Executes `llmfit recommend --json` on remote hosts |
| `setup.sh` | Provisioning script with `[STEP:name:START/OK/FAIL]` markers | New `llmfit_install` step added at end |
| `start-vllm.sh` | GPU detection + hardcoded model selection via case/switch | `VLLM_MODEL` env var override already exists (line 100); llmfit replaces the heuristic |
| Admin API (`/admin/`) | Operational endpoints with FastAPI dependency injection | New recommendation endpoint follows same pattern |
| Node detail page | Shows provisioning tasks, live logs, node info table | Gains "Model Recommendations" card |
| `AdminNodeResponse` | Frozen Pydantic model with GPU info, state, actions | Extended with recommendation data or served separately |
| `ProvisioningStep` enum | StrEnum covering setup + teardown lifecycle | New `LLMFIT_INSTALL` step |
| `QUADSHost` model | GPU vendor/model/count from QUADS inventory | llmfit `system` object provides richer hardware detail (VRAM GB, bandwidth, backend) |

## Table Stakes

Features operators expect. Missing = the llmfit integration feels incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Install llmfit on target servers during provisioning | Can't recommend models without the tool on the hardware | Low | `curl -fsSL https://llmfit.axjns.dev/install.sh \| sh` -- single line in setup.sh, new `[STEP:llmfit_install:START/OK/FAIL]` marker. Add `LLMFIT_INSTALL` to `ProvisioningStep` enum. Prebuilt binary, no Rust toolchain needed on targets. |
| Run llmfit via SSH and capture JSON output | Core value -- hardware-aware model scoring on actual server hardware | Med | `llmfit recommend --json --use-case general -n 10` via `SSHClient.run_streaming()`. Collect stdout lines, join, parse as JSON. The `--json` flag is the default for `recommend` but explicit is safer. Expect 5-15s execution time (hardware detection + scoring). |
| Parse llmfit JSON into typed Pydantic models | Gateway needs structured data for API responses and dashboard rendering | Med | Two models: `LLMFitSystemInfo` (hardware: `gpu_vram_gb`, `gpu_name`, `cpu_name`, `total_ram_gb`, `backend`, `has_gpu`) and `LLMFitModelRecommendation` (per-model: `name`, `provider`, `score`, `estimated_tps`, `best_quant`, `memory_required_gb`, `utilization_pct`, `fit_level`, `run_mode`, `context_length`, `params_b`, `category`). Schema is stable at v1.1.6. |
| Admin API endpoint for model recommendations | Operators need to query recommendations without SSH terminal access | Med | `GET /admin/nodes/{hostname}/recommendations` -- runs llmfit via SSH on the target, returns parsed JSON. Response includes both `system` (hardware) and `models` (recommendations). Depends on SSHClient (exists), Pydantic models (new). |
| Operator selects model before vLLM deployment | The whole point -- informed model choice replaces hardcoded heuristic | Med | `start-vllm.sh` already supports `VLLM_MODEL` env var override. `SetupRequest` gains optional `model: str \| None` field. When set, provisioner passes `VLLM_MODEL={model}` as env var to the remote `start-vllm.sh`. |
| Dashboard shows recommendations for a node | Operators work from the dashboard -- model selection must live there | Med | Node detail page (`node_detail.html`) gains a "Model Recommendations" card. Fetches from admin API. Shows ranked table: model name, score, tok/s est, memory%, fit level, quantization. Select button per row. |
| Error handling for llmfit failures | llmfit may fail (no GPU detected, binary install failed, SSH timeout) -- must not block provisioning | Low | Treat llmfit as best-effort. If `recommend` fails, log warning, fall back to existing GPU-based heuristic in start-vllm.sh. Recommendations are advisory, not blocking. The install step in setup.sh should not `exit 1` on failure -- use a non-fatal step wrapper. |

## Differentiators

Features that add operational polish. Not expected, but valued.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Use-case filtering in recommendation request | Different workloads need different models (coding vs chat vs reasoning) | Low | Pass through to CLI: `--use-case coding\|reasoning\|chat\|general\|multimodal\|embedding`. Add optional `use_case` query param to admin API endpoint. llmfit adjusts composite score weights per use case (e.g., Chat=35% speed vs Reasoning=55% quality). |
| Minimum fit level filtering | Operators only want "perfect" or "good" fits, not marginal | Low | Pass `--min-fit perfect\|good\|marginal` to llmfit CLI. Add optional `min_fit` query param to admin endpoint. |
| Hardware detection display | Operators want to see detected VRAM, GPU name, CPU, backend before choosing a model | Low | The `system` object in llmfit JSON output already contains `gpu_vram_gb`, `cpu_name`, `total_ram_gb`, `backend`, `has_gpu`. Display as hardware summary card in dashboard alongside recommendations. Richer than current QUADS `gpu_vendor`/`gpu_model`/`gpu_count`. |
| Cached recommendations with staleness indicator | Avoid re-running llmfit on every page load -- hardware doesn't change between reboots | Med | Store last llmfit result per hostname in memory (dict keyed by hostname). Show "refreshed 5m ago" badge. "Refresh" button re-runs via SSH. No persistence needed -- gateway restart clears cache, acceptable since hardware is static. |
| Fleet-wide model compatibility matrix | Operators managing 10+ servers want "which servers can run Model X?" | Med | New endpoint: `GET /admin/recommendations/summary` -- aggregates cached recommendations across all nodes with llmfit data. Groups by model name, shows which hosts can run it and at what fit level. Requires cached per-host recommendations. |
| Recommendation count limit control | Control how many models to show (top 5 vs top 20) | Low | Pass `-n {limit}` to llmfit CLI. Add optional `limit` query param to admin endpoint. Default 10. |

## Anti-Features

Features to explicitly NOT build.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Auto-deploy best model without operator confirmation | Operators need to validate model choice against team needs (specific model versions, licensing, org policy). Automated selection removes human judgment from a critical decision. | Show ranked recommendations, let operator click "Deploy with this model". The operator is the decision-maker. |
| Custom scoring engine replacing llmfit | llmfit implements bandwidth-based speed estimation, dynamic quantization selection (Q8_0 down to Q2_K), MoE-aware memory calculation, 157+ model catalog, community benchmark data. Reimplementing this is months of work for worse results. | Use llmfit as-is. Parse its JSON output. Trust its scoring. |
| Persistent recommendation history database | Adds storage dependency (SQLite/PostgreSQL) for data that's ephemeral -- hardware profile is constant per server, model catalog changes with llmfit version updates. | In-memory cache per hostname. Cleared on gateway restart. |
| llmfit REST API server (`llmfit serve`) on each node | Running a long-lived llmfit HTTP server on every GPU node adds process management, port conflicts (8787 default), monitoring burden, firewall rules. | Run `llmfit recommend --json` on demand via SSH. One command, one result, no daemon to manage. |
| Model downloading/pulling from gateway | Pulling model weights (10-100GB) through the gateway is wrong -- models live on NFS shared storage (`/srv/hf-cache`). | Ensure selected model exists on NFS. If not, show error "model not available on NFS storage". Model weight management is a separate concern. |
| Support for non-vLLM runtimes from llmfit output | The gateway exclusively manages vLLM nodes. llmfit supports Ollama, llama.cpp, MLX, LM Studio runtimes but only vLLM matters here. | Ignore `runtime` field in llmfit output. The model `name` and fit analysis are what matter -- vLLM serves HuggingFace model IDs regardless. |
| Building a web TUI mirroring llmfit's interactive mode | The TUI is for humans at a terminal. The gateway is a programmatic consumer. | Use `recommend --json` only. The dashboard provides the visual interface. |
| llmfit version pinning or update management | llmfit is installed once during setup.sh. Version updates across fleet nodes is ops tooling, not gateway responsibility. | Install latest via curl script. If version matters later, pin in setup.sh URL. |

## Feature Dependencies

```
Install llmfit (setup.sh step)
        |
        v
Run llmfit via SSH (SSHClient.run_streaming)
        |
        v
Parse JSON into Pydantic models (LLMFitSystemInfo, LLMFitModelRecommendation)
        |
        v
Admin API endpoint (GET /admin/nodes/{hostname}/recommendations)
        |
        v
Dashboard recommendations card (node_detail.html)
        |
        v
Operator selects model --> SetupRequest.model field --> VLLM_MODEL env var --> start-vllm.sh
```

Orthogonal (no ordering dependency on each other, but all depend on admin API existing):
- Use-case filtering: additive `--use-case` flag and query param
- Min-fit filtering: additive `--min-fit` flag and query param
- Limit control: additive `-n` flag and query param
- Hardware detection display: comes free with llmfit JSON `system` object
- Cached recommendations: wraps around the SSH execution layer
- Fleet summary: depends on cached per-host data existing

## MVP Recommendation

Prioritize in this order -- each step is independently testable:

1. **Pydantic models for llmfit JSON output** -- `LLMFitSystemInfo` and `LLMFitModelRecommendation` matching the documented schema. These are pure data models, no dependencies.
2. **Install llmfit during setup.sh** -- new step in provisioning script, new `LLMFIT_INSTALL` value in `ProvisioningStep` enum.
3. **SSH-based llmfit execution** -- new method (on NodeProvisioner or a dedicated service class) that runs `llmfit recommend --json` via SSH and returns parsed Pydantic models.
4. **Admin API endpoint** -- `GET /admin/nodes/{hostname}/recommendations` returning typed response with system info + model list.
5. **Dashboard recommendations card** -- table in node_detail.html with ranked models, hardware summary, select button.
6. **Wire selected model into provisioning** -- `SetupRequest` gains optional `model` field, provisioner passes as `VLLM_MODEL` env var to `start-vllm.sh`.

Defer:
- **Fleet-wide matrix**: useful but not v1.6 core -- requires all nodes to have cached recommendations.
- **Cached recommendations**: start without caching (run llmfit per request). Add if 5-15s SSH round-trip becomes a UX problem.
- **Use-case / min-fit / limit filtering**: trivial extensions after core flow works. One query param each.

## llmfit JSON Schema Reference

The `recommend --json` output (v1.1.6, HIGH confidence -- verified via official docs at alexsjones-llmfit.mintlify.app):

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
    }
  ]
}
```

### Scoring Dimensions (composite 0-100)

| Dimension | What It Measures | General | Coding | Reasoning | Chat | Embedding |
|-----------|-----------------|---------|--------|-----------|------|-----------|
| Quality | Parameter count + quantization precision | 45% | 50% | 55% | 40% | 30% |
| Speed | Memory-bandwidth tok/s estimate (55% efficiency factor) | 30% | 20% | 15% | 35% | 40% |
| Fit | Memory budget vs model size at best quantization | 15% | 15% | 15% | 15% | 20% |
| Context | Context window capacity given hardware | 10% | 15% | 15% | 10% | 10% |

### Fit Levels

| Level | Meaning | Default included |
|-------|---------|-----------------|
| perfect | Fits with headroom | Yes |
| good | Fits, limited headroom | Yes |
| marginal | Barely fits, may swap | Yes (default floor) |
| too_tight | Does not fit | No (excluded by default) |

### Dynamic Quantization

llmfit walks Q8_0 -> Q6_K -> Q5_K_M -> Q5_0 -> Q4_K_M -> Q4_0 -> Q3_K_M -> Q2_K, picking the highest quality that fits available VRAM. If nothing fits at full context, retries at half context.

### Installation on Target Servers

Recommended: `curl -fsSL https://llmfit.axjns.dev/install.sh | sh` -- downloads prebuilt x86_64 binary to `/usr/local/bin/llmfit`. No Rust toolchain needed. Works on headless RHEL/Fedora servers.

Alternative: `pip install llmfit` / `uv tool install llmfit` (Python wrapper on PyPI, v0.9.28).

### What This Replaces

The current `start-vllm.sh` `configure_vllm_params()` function uses a `case "$GPU_MODEL"` switch with 5 branches:

| GPU Match | Hardcoded Model | VRAM Logic |
|-----------|----------------|------------|
| H100/A100 | Qwen2.5-72B or 32B | Total VRAM thresholds (240GB, 160GB) |
| T4 | Qwen2.5-3B or 7B | Single GPU VRAM <= 16GB check |
| V100 | Qwen2.5-32B or 14B | Total VRAM >= 64GB check |
| RTX/GeForce | Qwen2.5-14B or 7B | Single GPU VRAM >= 24GB check |
| Default | Qwen2.5-7B | Conservative fallback |

Problems with current approach:
- Only covers 4 GPU families (misses A10, L40, MI250, etc.)
- Only recommends Qwen2.5 models (no Llama, Mistral, DeepSeek, etc.)
- No memory-fit analysis beyond raw VRAM thresholds
- No quantization awareness (always serves full precision)
- No speed estimation
- No composite scoring

llmfit provides: 157+ models, 30+ providers, dynamic quantization, bandwidth-based speed estimation, MoE support, multi-GPU awareness, composite score across 4 dimensions.

## Sources

- [llmfit GitHub](https://github.com/AlexsJones/llmfit) -- v1.1.6, 30.5k stars, MIT license
- [llmfit Documentation](https://alexsjones-llmfit.mintlify.app/) -- official docs
- [llmfit recommend command reference](https://alexsjones-llmfit.mintlify.app/api/commands/recommend) -- JSON schema, all flags
- [llmfit scoring system](https://alexsjones-llmfit.mintlify.app/concepts/how-it-works) -- dimension weights, quantization algorithm
- [llmfit REST API guide](https://alexsjones-llmfit.mintlify.app/guides/rest-api) -- serve endpoints (not used, but documented)
- [llmfit installation](https://alexsjones-llmfit.mintlify.app/installation) -- all install methods
- [llmfit PyPI](https://pypi.org/project/llmfit/0.9.28/) -- Python package
- [llmfit crates.io](https://crates.io/crates/llmfit) -- Rust crate
- [llmfit.org](https://www.llmfit.org/) -- official website
