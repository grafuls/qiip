# Phase 10: Script Hardening - Pattern Map

**Mapped:** 2026-07-01
**Files analyzed:** 4
**Analogs found:** 3 / 4

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `auto-vllm-container/setup.sh` | config | batch | `auto-vllm-container/setup.sh` (current, unhardened) | self-modify |
| `auto-vllm-container/start-vllm.sh` | utility | batch | `auto-vllm-container/start-vllm.sh` (current, container entrypoint) | self-modify |
| `auto-vllm-container/entrypoint.sh` | config | request-response | `auto-vllm-container/start-vllm.sh` (lines 108-132, `run_vllm_server`) | exact |
| `auto-vllm-container/Containerfile` | config | batch | `auto-vllm-container/Containerfile` (current) | self-modify |

## Pattern Assignments

### `auto-vllm-container/setup.sh` (config, batch -- MODIFY)

**Analog:** itself (current version has zero error handling; hardening adds patterns from `start-vllm.sh`)

**Shell header pattern** -- borrow from `start-vllm.sh` (lines 1-2):
```bash
#!/bin/bash
set -euo pipefail
```

**Env var default pattern** -- borrow from `start-vllm.sh` (line 5):
```bash
VLLM_PORT="${VLLM_PORT:-8000}"
```
Apply to all hardcoded values in `setup.sh`: `NFS_SERVER`, `NFS_MOUNT_POINT`, `NVIDIA_DRIVER_VERSION`, `NVIDIA_DRIVER_URL`, `VLLM_PORT`.

**Function-per-step pattern** -- borrow from `start-vllm.sh` (lines 8-14, 17-105, 108-132):
Each logical block is a named function (`detect_gpu_info`, `configure_vllm_params`, `run_vllm_server`). Apply the same structure: one function per step in `setup.sh` (`install_nvidia_repo`, `run_system_update`, `install_nvidia_driver`, `generate_nvidia_cdi`, `mount_nfs_cache`, `configure_firewall`).

**Main execution pattern** -- borrow from `start-vllm.sh` (lines 135-141):
```bash
main() {
    detect_gpu_info
    configure_vllm_params
    run_vllm_server
}

main
```
Replace with `step` wrapper calls instead of direct function calls (see Shared Patterns below).

**Current hardcoded values to extract** (from `setup.sh` lines 18-19, 27):
```bash
# Line 18-19: driver version and URL
wget https://us.download.nvidia.com/tesla/580.126.09/NVIDIA-Linux-x86_64-580.126.09.run
# Line 27: NFS server and mount point
sudo mount -t nfs -o vers=3 rdu-storage02.scalelab.redhat.com:/mnt/SATA/scratch/grafuls/hf-cache /srv/hf-cache
# Line 30: port
sudo iptables -I INPUT -p tcp --dport 8000 -j ACCEPT
```

---

### `auto-vllm-container/start-vllm.sh` (utility, batch -- REWRITE)

**Analog:** itself (current version). GPU detection and model selection logic stays; `run_vllm_server` function is replaced by `podman build` + `podman run`.

**Keep from current file** (lines 8-105):
- `detect_gpu_info()` function (lines 8-14) -- unchanged
- `configure_vllm_params()` function (lines 17-105) -- unchanged, including the env var override block at lines 100-104

**Env var override pattern** to keep (lines 100-104):
```bash
MODEL="${VLLM_MODEL:-$MODEL}"
TENSOR_PARALLEL="${VLLM_TENSOR_PARALLEL:-$TENSOR_PARALLEL}"
GPU_MEM_UTIL="${VLLM_GPU_MEM_UTIL:-$GPU_MEM_UTIL}"
MAX_MODEL_LEN="${VLLM_MAX_MODEL_LEN:-$MAX_MODEL_LEN}"
```

**Replace `run_vllm_server()`** (lines 108-132) with container lifecycle:
- `podman build -t vllm-inference .`
- `podman run -d --replace --name "$CONTAINER_NAME" ...`
- Container name derived from model slug per D-03

---

### `auto-vllm-container/entrypoint.sh` (config, request-response -- NEW)

**Analog:** `auto-vllm-container/start-vllm.sh` lines 123-131 (the `exec vllm serve` block)

**Core pattern to extract** (lines 123-131):
```bash
  exec vllm serve ${MODEL} \
  --host 0.0.0.0 \
  --port ${VLLM_PORT} \
  --tensor-parallel-size ${TENSOR_PARALLEL} \
  --gpu-memory-utilization ${GPU_MEM_UTIL} \
  --max-model-len ${MAX_MODEL_LEN} \
  --max-num-batched-tokens ${MAX_BATCHED_TOKENS} \
  ${EXTRA_ARGS}
```

Modify to read all values from env vars with defaults (no detection logic). Add `set -euo pipefail` header.

---

### `auto-vllm-container/Containerfile` (config, batch -- MODIFY)

**Analog:** itself (current version)

**Current COPY + ENTRYPOINT pattern** (lines 13-20):
```dockerfile
# Copy a startup script that uses the env vars
COPY ./start-vllm.sh /start-vllm.sh
RUN chmod +x /start-vllm.sh

# Expose the default OpenAI-compatible port
EXPOSE 8000

# Override base image ENTRYPOINT so our script runs (base uses ENTRYPOINT for vLLM)
ENTRYPOINT ["/start-vllm.sh"]
```

Change to:
- `COPY ./entrypoint.sh /entrypoint.sh`
- `RUN chmod +x /entrypoint.sh`
- `ENTRYPOINT ["/entrypoint.sh"]`

---

## Shared Patterns

### Step Marker Wrapper (NEW -- no existing analog)
**Apply to:** `setup.sh` only
**Source:** RESEARCH.md Pattern 1

```bash
step() {
    local name="$1"; shift
    echo "[STEP:${name}:START]"
    if "$@"; then
        echo "[STEP:${name}:OK]"
    else
        echo "[STEP:${name}:FAIL]"
        exit 1
    fi
}
```

Note: The `if "$@"` pattern is critical -- it disables `set -e` for the condition, allowing the wrapper to emit `FAIL` before exiting instead of exiting silently.

### Idempotency Guard Pattern (NEW -- no existing analog)
**Apply to:** `setup.sh` step functions
**Source:** RESEARCH.md Pattern 2

```bash
# Guard at top of each step function, return 0 to skip
some_step() {
    if <completion-check>; then
        echo "<description> already done, skipping"
        return 0
    fi
    # ... actual work
}
```

Guards per step:
| Step | Guard |
|------|-------|
| `nvidia_repo` | `test -f /etc/yum.repos.d/nvidia-container-toolkit.repo` |
| `system_update` | None (always runs) |
| `nvidia_driver` | `nvidia-smi &>/dev/null` |
| `nvidia_cdi` | `test -f /etc/cdi/nvidia.yaml` |
| `nfs_mount` | `mountpoint -q "$NFS_MOUNT_POINT"` |
| `firewall` | `sudo iptables -C INPUT -p tcp --dport "$VLLM_PORT" -j ACCEPT 2>/dev/null` |

### Env Var Default Pattern (EXISTING)
**Source:** `auto-vllm-container/start-vllm.sh` line 5
**Apply to:** `setup.sh` (all hardcoded values), `entrypoint.sh` (all vllm params)

```bash
VARIABLE="${ENV_VAR:-default_value}"
```

### Shell Safety Header (EXISTING)
**Source:** `auto-vllm-container/start-vllm.sh` lines 1-2
**Apply to:** All three shell scripts

```bash
#!/bin/bash
set -euo pipefail
```

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| (step marker wrapper) | utility pattern | event-driven | New pattern -- no structured output exists in current scripts |
| (idempotency guards) | utility pattern | batch | New pattern -- current `setup.sh` has zero guards |

These patterns are fully specified in RESEARCH.md (Patterns 1 and 2) and do not require codebase analogs -- they are standard bash idioms.

## Metadata

**Analog search scope:** `auto-vllm-container/` (the 3 files being modified are their own analogs)
**Files scanned:** 3
**Pattern extraction date:** 2026-07-01
