---
phase: 10-script-hardening
plan: 02
status: complete
started: 2026-07-01T18:52:35Z
completed: 2026-07-01T19:05:00Z
---

## Summary

Restructured container boundary: extracted thin `entrypoint.sh` from `start-vllm.sh`, rewrote `start-vllm.sh` as host-side launcher with `podman build` + `podman run -d --replace`, updated `Containerfile` to reference `entrypoint.sh`.

## What Changed

- Created `auto-vllm-container/entrypoint.sh`: 12-line thin wrapper with `exec vllm serve`, all config via env vars (`VLLM_MODEL` required, rest have defaults)
- Rewrote `auto-vllm-container/start-vllm.sh`: kept `detect_gpu_info()` and `configure_vllm_params()`, added `derive_container_name()` (model-based naming like `vllm-qwen2.5-72b-instruct`), replaced `run_vllm_server()` with `build_and_run_container()` using `podman build -t vllm-inference` + `podman run -d --replace`
- Added missing env var overrides for `MAX_BATCHED_TOKENS` and `EXTRA_ARGS` in configure_vllm_params
- Updated `auto-vllm-container/Containerfile`: COPY/ENTRYPOINT now reference `entrypoint.sh`

## Self-Check: PASSED

- `bash -n` syntax validation (all 3 files): PASSED
- `exec vllm serve` in entrypoint.sh only: CONFIRMED
- `podman run -d --replace` in start-vllm.sh: CONFIRMED
- `--device nvidia.com/gpu=all` in start-vllm.sh: CONFIRMED
- NFS volume mount read-only: CONFIRMED
- Containerfile references entrypoint.sh, not start-vllm.sh: CONFIRMED

## Key Files

### Created
- `auto-vllm-container/entrypoint.sh` — Thin container entrypoint

### Modified
- `auto-vllm-container/start-vllm.sh` — Host-side launcher
- `auto-vllm-container/Containerfile` — Container definition

## Deviations

None.
