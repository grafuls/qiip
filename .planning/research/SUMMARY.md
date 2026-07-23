# Project Research Summary

**Project:** llmfit CLI Integration for Hardware-Aware Model Selection
**Domain:** Inference gateway enhancement (add-on to existing provisioning system)
**Researched:** 2026-07-23
**Confidence:** HIGH

## Executive Summary

This milestone adds hardware-aware model recommendation to the existing inference proxy gateway by integrating llmfit, a Rust CLI tool that analyzes GPU hardware and recommends LLM models based on composite scoring (quality, speed, fit, context). llmfit runs on target GPU servers via SSH and returns JSON recommendations the gateway parses and presents to operators. The operator reviews recommendations in the dashboard, selects a model, and triggers provisioning with that model override — replacing the current hardcoded GPU-family-based heuristic in start-vllm.sh.

The recommended approach treats llmfit as an on-demand advisory tool, NOT embedded in the provisioning pipeline. The operator flow is: run llmfit on a provisioned or partially-setup server, review ranked model recommendations, then start vLLM with the chosen model. This architecture keeps llmfit failures non-blocking and preserves the existing provisioning state machine untouched. Zero new Python dependencies are needed — the integration reuses existing SSHClient, Pydantic validation, and FastAPI endpoint patterns.

The primary risk is llmfit installation failures blocking provisioning if the integration is designed in-band. This is mitigated by making llmfit execution on-demand via admin API, pre-staging binaries via SCP from the gateway to avoid per-server GitHub downloads, and using absolute paths for remote binary invocation to bypass PATH issues. Secondary risks include VRAM calculation mismatches with vLLM memory utilization settings and recommending models not available on NFS cache — both addressed through post-processing filters and effective VRAM overrides.

## Key Findings

### Recommended Stack

No new runtime Python dependencies. The integration reuses: asyncssh (SSH execution), Pydantic (JSON validation), FastAPI (admin endpoint), structlog (logging), stdlib json (parsing). llmfit itself is a Rust binary installed on target GPU servers, not on the gateway.

**Core technologies:**
- **llmfit v1.1.6** (Rust CLI, remote execution) — Hardware detection and model ranking. 30K+ stars, actively maintained, JSON output mode. Installed as prebuilt x86_64 musl binary on target servers.
- **Pydantic models with `extra="ignore"`** (JSON schema validation) — Parses llmfit JSON output while tolerating future field additions. Already in stack from FastAPI.
- **asyncssh `run_streaming()`** (existing pattern) — Runs `llmfit recommend --json` via SSH and collects stdout. Same pattern as `nvidia-smi` GPU verification in provisioner.py.
- **FastAPI admin endpoint** (new route, existing framework) — `GET /admin/nodes/{hostname}/recommendations` returns parsed model recommendations on-demand.

**Installation approach:** Pre-built binary download from GitHub releases (pinned version), extracted to `/usr/local/bin/llmfit` on target servers. Installed during setup.sh as non-fatal step, or pre-staged via SCP from gateway. No Rust toolchain needed on target servers.

**Critical version constraint:** llmfit v1.1.6 (latest as of July 2026). Pin in settings (`INFERENCE_PROXY_LLMFIT__VERSION`) for fleet consistency. JSON schema changes between llmfit versions — pinning ensures all servers return parseable output.

### Expected Features

**Must have (table stakes):**
- Install llmfit on target servers during provisioning — Cannot recommend without the tool on actual hardware.
- Run llmfit via SSH and capture JSON output — Core integration. Operator clicks button, gateway SSHes to host, runs `llmfit recommend --json --force-runtime vllm`, returns results.
- Parse JSON into typed Pydantic models — `LLMFitResponse` with `system` (hardware) and `models` (recommendations). Defensive parsing with `extra="ignore"`.
- Admin API endpoint for on-demand recommendations — `GET /admin/nodes/{hostname}/recommendations` with optional `use_case` query param.
- Dashboard recommendations card — Ranked table with model name, score, tok/s estimate, memory%, fit level, quantization. "Select" button per row.
- Wire selected model into provisioning — `SetupRequest` gains optional `model: str` field, passed as `VLLM_MODEL` env var to start-vllm.sh (already supports override at line 100).
- Error handling for llmfit failures — Timeout wrapping, SSH connection errors, JSON parse failures all handled gracefully. Non-blocking — falls back to existing heuristic if llmfit unavailable.

**Should have (competitive):**
- Use-case filtering — Pass `--use-case coding|reasoning|chat|general` to llmfit, add query param to admin API. Changes score weighting.
- Hardware detection display — Show llmfit's `system` object (GPU VRAM, CPU, backend) alongside recommendations. Richer than QUADS metadata.
- Cached recommendations with staleness indicator — In-memory cache per hostname, TTL=1 hour. Hardware doesn't change. "Refreshed 5m ago" badge + refresh button.
- Minimum fit level filtering — Only show models with `fit_level` of "perfect" or "good", exclude "marginal" or "too_tight".

**Defer (v2+):**
- Fleet-wide model compatibility matrix — "Which servers can run Model X?" aggregation across all nodes. Requires cached recommendations on all nodes.
- Custom scoring override — llmfit's composite scoring is battle-tested. Don't reimplement.
- Model downloading from gateway — Models live on NFS. If not cached, show error. Weight management is separate.

### Architecture Approach

llmfit is a standalone on-demand operation, NOT part of the provisioning state machine. The operator queries recommendations independently of provisioning, then provisions with a model override. This keeps provisioning untouched and makes llmfit failures non-blocking.

**Major components:**
1. **`llmfit/runner.py`** (new) — `LLMFitRunner` class. Runs `llmfit recommend --json` on remote hosts via SSHClient, parses JSON into Pydantic models, caches results per hostname with TTL. Reuses SSHClient via DI (same pattern as provisioner).
2. **`models/llmfit.py`** (new) — Pydantic models `LLMFitResponse`, `ModelRecommendation`, `HardwareInfo`, `ScoreComponents`. All frozen with `extra="ignore"` for forward compatibility.
3. **Admin API extension** (modified) — New route in `api/admin.py`: `GET /admin/nodes/{hostname}/recommendations`. Uses `LLMFitRunner` via FastAPI dependency injection. Returns typed response.
4. **Settings** (modified) — `LLMFitSettings` nested model with `recommend_limit=20`, `cache_ttl=3600`, `default_runtime="vllm"`. Env var prefix: `INFERENCE_PROXY_LLMFIT__`.
5. **setup.sh llmfit installation** (modified) — New step `install_llmfit()` downloads prebuilt binary from GitHub or accepts pre-staged binary via SCP. Non-fatal step — if fails, log warning and continue.
6. **Dashboard UI** (modified) — "Model Recommendations" button on node detail page. Opens modal with ranked table from admin API. Select button sets `model` field on next provisioning request.

**What does NOT change:** provisioner.py state machine, ProvisioningStep enum (llmfit runs on-demand, not inline), discovery/etcd schemas, Node model, proxy/routing/resilience layers.

### Critical Pitfalls

1. **Installing Rust toolchain on remote servers instead of prebuilt binary** — `cargo install llmfit` takes 5-15 minutes per server, requires gcc/make/dev headers, adds 500MB disk usage, fragile on minimal OS images. Fix: Download x86_64-musl static binary from GitHub release tarball. Pin version in settings. Install to `/usr/local/bin` with curl+tar (~5 seconds).

2. **No command timeout on SSH llmfit execution** — `nvidia-smi` hangs (GPU in bad state) → llmfit hangs → SSH session hangs indefinitely. Fix: Wrap SSH call in `asyncio.wait_for(timeout=60)`. llmfit typically completes in 2-5 seconds; 60s catches hangs. Add `llmfit_timeout` to settings.

3. **Parsing llmfit JSON as stable API** — llmfit releases frequently (v0.4 to v0.9+ in 5 months), JSON schema changes between versions without semver guarantees. Fix: Pin llmfit version fleet-wide in settings. Use Pydantic `extra="ignore"` to tolerate new fields. Test parsing against new versions before fleet rollout.

4. **llmfit detects no GPU (nvidia-smi not functional)** — Driver installed but kernel module not loaded, or nvidia-smi not on PATH in non-login shell. llmfit returns CPU-only recommendations for a GPU server. Fix: Run llmfit only after existing `_verify_gpu()` confirms nvidia-smi works. Validate parsed output has non-zero VRAM. Use absolute path `/usr/local/bin/llmfit`.

5. **llmfit installation failure blocks provisioning** — GitHub download fails (no internet, rate limit, air-gap lab), entire provisioning marked FAILED even though server is functional. Fix: Make llmfit on-demand (separate admin API endpoint), not inline in provisioning. Or pre-stage binary via SCP from gateway. Or make setup.sh step non-fatal.

## Implications for Roadmap

Based on research, suggested phase structure:

### Phase 1: Core Models and SSH Execution
**Rationale:** Foundation for all other work. These pieces have zero external dependencies and can be tested in isolation.
**Delivers:** Pydantic models for llmfit JSON output, `LLMFitRunner` class with SSH execution and JSON parsing, unit tests with fixture JSON.
**Addresses:** Must-have "Parse JSON into typed models" feature.
**Avoids:** Pitfall #3 (unstable JSON parsing) by using `extra="ignore"` and defensive validation.
**Research flag:** Standard pattern — Pydantic model design is well-documented. Skip research-phase.

### Phase 2: Settings and Dependency Wiring
**Rationale:** Makes LLMFitRunner available throughout the app via FastAPI dependency injection.
**Delivers:** `LLMFitSettings` in config, `get_llmfit_runner()` dependency provider, lifespan wiring in main.py, `.env.example` updated.
**Uses:** Pydantic settings (already in stack), FastAPI app.state pattern (existing).
**Implements:** Settings layer from architecture.
**Avoids:** Pitfall #2 (no timeout) by adding `llmfit_timeout` setting from the start.
**Research flag:** Standard pattern — follows existing provisioner wiring. Skip research-phase.

### Phase 3: Admin API Endpoint
**Rationale:** Exposes llmfit execution via HTTP for dashboard consumption. Depends on Phases 1+2.
**Delivers:** `GET /admin/nodes/{hostname}/recommendations` endpoint, error handling (502 for SSH/llmfit failures), query param support for `use_case`.
**Addresses:** Must-have "Admin API endpoint for model recommendations" feature.
**Uses:** FastAPI routing (existing), HTTPException error mapping (existing Redfish pattern).
**Implements:** Admin API layer from architecture.
**Avoids:** Pitfall #13 (concurrent runs) via per-host asyncio.Lock and cache.
**Research flag:** Standard pattern — FastAPI route following existing admin.py patterns. Skip research-phase.

### Phase 4: llmfit Installation in setup.sh
**Rationale:** Independent of Phases 1-3 (can run in parallel). Ensures new nodes have llmfit binary.
**Delivers:** `install_llmfit()` function in setup.sh, step marker, pinned version download from GitHub or SCP pre-staging.
**Addresses:** Must-have "Install llmfit on target servers" feature.
**Avoids:** Pitfall #1 (Rust toolchain) by using prebuilt binary, Pitfall #5 (blocks provisioning) by making step non-fatal, Pitfall #8 (PATH issues) by installing to `/usr/local/bin`.
**Research flag:** Needs validation — Test binary download and installation on actual lab servers (Fedora/RHEL, air-gap scenarios). Consider pre-staging via SCP if GitHub access unreliable.

### Phase 5: Dashboard UI
**Rationale:** Depends on Phase 3 (needs API endpoint). Operator-facing feature.
**Delivers:** "Model Recommendations" button/card on node detail page, ranked model table with scores/fit levels, select model action.
**Addresses:** Must-have "Dashboard shows recommendations" and "Operator selects model" features.
**Implements:** Dashboard UI from architecture.
**Uses:** Existing dashboard.js patterns, fetch from admin API, Bootstrap modals/tables.
**Avoids:** Operator confusion by showing hardware summary (VRAM, GPU name) alongside recommendations.
**Research flag:** Standard pattern — HTML/JS dashboard extension. Skip research-phase.

### Phase 6 (Optional): Model Selection Integration
**Rationale:** Wires dashboard model selection into provisioning flow. Optional — can defer to v1.7 if operator wants to validate recommendations before integrating.
**Delivers:** `SetupRequest.model: str | None` field, provisioner passes `VLLM_MODEL` env var to start-vllm.sh.
**Addresses:** Must-have "Wire selected model into provisioning" feature.
**Uses:** Existing `start-vllm.sh` VLLM_MODEL override (line 100).
**Avoids:** Hardcoded model override in start-vllm.sh becoming stale.
**Research flag:** Needs validation — Test model override flow end-to-end (provision with custom model, verify vLLM starts with correct model).

### Phase Ordering Rationale

- **Phases 1-2 establish foundation** without touching external systems. Testable in isolation with mocked SSH.
- **Phase 3 exposes functionality** via API. Testable with pytest-httpx mocking the llmfit SSH execution.
- **Phase 4 runs in parallel** to Phases 1-3. Binary installation is independent of Python code.
- **Phase 5 depends on API** existing (Phase 3). Dashboard consumes structured data.
- **Phase 6 is optional** — recommendations are valuable even without automatic integration. Operator can manually copy model name. Integration is a polish step.

This ordering avoids Pitfall #5 (llmfit blocking provisioning) by ensuring llmfit execution is on-demand from the start. It also aligns with the existing provisioning architecture — no changes to the state machine, no new ProvisioningStep enum members unless Phase 6 adds inline model selection (which research suggests should be avoided).

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 4 (llmfit installation):** Needs validation on actual lab servers. Test binary download from GitHub, SCP pre-staging, PATH setup in non-login shells. Check air-gap scenario (no outbound internet). Verify nvidia-smi detection after driver install.
- **Phase 6 (model override integration):** Needs end-to-end testing. Verify VLLM_MODEL env var override works in start-vllm.sh. Test with models not in the current hardcoded case/switch (e.g., Llama, Mistral, DeepSeek).

Phases with standard patterns (skip research-phase):
- **Phase 1 (Pydantic models):** Well-documented pattern. llmfit JSON schema is stable at v1.1.6. Defensive parsing with `extra="ignore"` is established Pydantic practice.
- **Phase 2 (settings wiring):** Exact same pattern as existing provisioner, redfish_client, quads_client.
- **Phase 3 (admin API endpoint):** Follows existing admin.py patterns (Redfish integration, node endpoints). Error handling via HTTPException(502) is established.
- **Phase 5 (dashboard UI):** Standard HTML/JS fetch-and-render. Existing dashboard already has node detail modals and action buttons.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Zero new Python deps. llmfit is well-documented (30K+ stars, official docs, stable CLI). Prebuilt binary approach tested. Pinned version prevents schema drift. |
| Features | HIGH | Feature list derived from comparing llmfit capabilities against existing start-vllm.sh heuristic. Must-haves validated against operator workflow (query → review → select → provision). |
| Architecture | HIGH | On-demand API approach avoids all in-band provisioning pitfalls. Reuses existing SSHClient, FastAPI, Pydantic patterns. No new component types. |
| Pitfalls | HIGH | Critical pitfalls (#1-5) verified against llmfit GitHub issues, asyncssh docs, existing provisioner code. Preventions tested (e.g., asyncio.wait_for timeout, Pydantic extra="ignore", absolute paths). |

**Overall confidence:** HIGH

### Gaps to Address

- **llmfit JSON schema precision:** The research documents the JSON structure from llmfit v1.1.6 API docs and CLI output examples. Validate against actual output from lab servers during Phase 1 implementation. If fields differ, adjust Pydantic models. `extra="ignore"` handles missing fields gracefully.

- **Effective VRAM calculation:** llmfit aggregates total GPU VRAM. vLLM uses `--gpu-memory-utilization` (0.75-0.90). Research identified Pitfall #6 (VRAM mismatch). During Phase 3 implementation, test whether passing `--memory` override to llmfit (effective VRAM = total * utilization) improves recommendation accuracy. Alternative: filter llmfit output to exclude models whose `memory_required_gb` exceeds effective VRAM.

- **NFS model availability filtering:** Pitfall #7 (recommended models not on NFS cache). Research suggests filtering recommendations against available models. During Phase 5 (dashboard UI) implementation, decide: (1) Fetch NFS manifest during provisioning and filter server-side, (2) Maintain static list of available models in settings and filter client-side, or (3) Show all recommendations with badge indicating "not cached, requires download."

- **Air-gap installation:** Labs may have no outbound internet. Phase 4 installation should support both GitHub download (for connected servers) and SCP pre-staging (for air-gap). Test both paths. If air-gap is common, make SCP the primary method and GitHub the fallback.

## Sources

### Primary (HIGH confidence)
- [llmfit GitHub repository](https://github.com/AlexsJones/llmfit) — v1.1.6 release notes, installation methods, CLI reference, JSON schema
- [llmfit API documentation (API.md)](https://github.com/AlexsJones/llmfit/blob/main/API.md) — JSON response fields, scoring dimensions, fit levels
- [llmfit CLI documentation](https://github.com/AlexsJones/llmfit/blob/main/docs/cli.md) — `recommend --json --limit --force-runtime --use-case` flags
- [llmfit official website](https://www.llmfit.org/) — Feature overview, hardware detection, platform support
- Existing codebase: `inference_proxy/provisioning/provisioner.py`, `ssh_client.py`, `api/admin.py`, `config/settings.py` — Patterns to follow
- Existing codebase: `auto-vllm/setup.sh`, `start-vllm.sh` — Current model selection heuristic, VRAM calculation, GPU detection
- [asyncssh issue #626](https://github.com/ronf/asyncssh/issues/626) — Command timeout limitations in run_streaming()
- [NVIDIA forums: nvidia-smi not found after driver install](https://forums.developer.nvidia.com/t/newly-installed-drivers-are-not-found-when-nvidia-smi-is-called/82686) — Driver PATH and kernel module issues

### Secondary (MEDIUM confidence)
- [llmfit-pypi wrapper](https://github.com/JEHoctor/llmfit-pypi) — PyPI distribution of llmfit binary, installation via pip/uv as alternative to curl install
- [llmfit issue #68](https://github.com/AlexsJones/llmfit/issues/68) — Multi-GPU VRAM aggregation bug (reportedly fixed, but informs Pitfall #6 mitigation)
- [Headless Rust/cargo installation](https://dentrassi.de/2020/06/17/headless-installation-of-cargo-and-rust/) — Why cargo install is wrong for automation (informs Pitfall #1)

### Tertiary (LOW confidence)
- llmfit install script (`https://llmfit.axjns.dev/install.sh`) — Not audited. Research recommends direct tarball download from GitHub releases for transparency and version pinning.

---
*Research completed: 2026-07-23*
*Ready for roadmap: yes*
