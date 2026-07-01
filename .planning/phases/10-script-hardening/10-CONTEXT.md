# Phase 10: Script Hardening - Context

**Gathered:** 2026-07-01
**Status:** Ready for planning

<domain>
## Phase Boundary

Harden `setup.sh` and `start-vllm.sh` for safe automated remote execution. Scripts must fail-fast on errors, be idempotent (re-runnable without breaking state), handle NFS mount timeouts, and emit structured step markers for downstream progress tracking. Also restructure the script/container boundary: split container entrypoint from host-side launcher.

</domain>

<decisions>
## Implementation Decisions

### Script Structure
- **D-01:** Rename current `start-vllm.sh` to `entrypoint.sh` (thin container entrypoint that runs `vllm serve` with env vars). New `start-vllm.sh` is the host-side launcher that does `podman build` + `podman run -d --replace`.
- **D-02:** `start-vllm.sh` (host launcher) does both `podman build` and `podman run` in one invocation. Rebuilds image each time.
- **D-03:** Container name is model-based (e.g., `vllm-qwen2.5-72b`). Allows future multi-model-per-host. Teardown (Phase 13) targets this name.
- **D-04:** GPU detection and model selection move to the host-side `start-vllm.sh`. Model and params passed to container as env vars. `entrypoint.sh` is a thin wrapper — no detection logic.

### NFS Failure Policy
- **D-05:** NFS mount timeout is 30 seconds. If mount fails or times out, `setup.sh` aborts entirely with non-zero exit. No NFS = no model cache = can't serve.
- **D-06:** If NFS is already mounted (`mountpoint -q /srv/hf-cache`), skip the mount step. No remount.

### Hardcoded Values
- **D-07:** All hardcoded values become env vars with current values as defaults: `NFS_SERVER`, `NFS_MOUNT_POINT`, `NVIDIA_DRIVER_URL`, `VLLM_PORT`, etc. Scripts work unchanged for Scale/Alias labs.
- **D-08:** NVIDIA driver version is pinned (known-good version as default env var). No auto-detection of latest driver.
- **D-09:** If `nvidia-smi` succeeds (driver already installed), skip the entire driver install block (download, blacklist nouveau, dracut, install). Biggest idempotency win.

### Output Format
- **D-10:** Scripts emit structured step markers for remote progress tracking. Format: `[STEP:name:STATUS]` prefix lines (e.g., `[STEP:nvidia_driver:START]`, `[STEP:nfs_mount:OK]`). Human-readable, easy to grep from asyncssh output.
- **D-11:** `setup.sh` emits 6 step names matching logical blocks: `nvidia_repo`, `system_update`, `nvidia_driver`, `nvidia_cdi`, `nfs_mount`, `firewall`.

### Claude's Discretion
- None — all decisions made by user.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Scripts Being Hardened
- `auto-vllm-container/setup.sh` — Current setup script (no error handling, no idempotency)
- `auto-vllm-container/start-vllm.sh` — Current container entrypoint with GPU detection (will be restructured)
- `auto-vllm-container/Containerfile` — Container build definition (ENTRYPOINT will change to entrypoint.sh)

### Project Context
- `.planning/ROADMAP.md` — Phase 10 success criteria and requirements mapping
- `.planning/REQUIREMENTS.md` — SCRIPT-01 through SCRIPT-04 requirement definitions

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `start-vllm.sh` GPU detection logic (`detect_gpu_info`, `configure_vllm_params`) — moves to host-side launcher, already well-structured with case/esac for GPU models
- `start-vllm.sh` env var override pattern (`MODEL="${VLLM_MODEL:-$MODEL}"`) — reuse this pattern for all configurable values in setup.sh

### Established Patterns
- `set -euo pipefail` already used in `start-vllm.sh` — apply to `setup.sh` as well
- `Containerfile` uses `ENTRYPOINT ["/start-vllm.sh"]` — will change to `["/entrypoint.sh"]`

### Integration Points
- Phase 11 (SSH Provisioning): asyncssh will run `setup.sh` and `start-vllm.sh` remotely, parsing `[STEP:name:STATUS]` markers from stdout
- Phase 12 (Provisioning Robustness): state machine maps to the 6 step names from setup.sh
- Phase 13 (Teardown): targets container by model-based name (e.g., `vllm-qwen2.5-72b`)

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 10-Script Hardening*
*Context gathered: 2026-07-01*
