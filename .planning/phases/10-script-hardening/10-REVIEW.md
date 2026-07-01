---
phase: 10-script-hardening
reviewed: 2026-07-01T12:00:00Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - auto-vllm-container/setup.sh
  - auto-vllm-container/entrypoint.sh
  - auto-vllm-container/start-vllm.sh
  - auto-vllm-container/Containerfile
findings:
  critical: 4
  warning: 5
  info: 2
  total: 11
status: issues_found
---

# Phase 10: Code Review Report

**Reviewed:** 2026-07-01T12:00:00Z
**Depth:** standard
**Files Reviewed:** 4
**Status:** issues_found

## Summary

Four shell scripts and a Containerfile implementing automated vLLM container provisioning on GPU servers. The scripts handle NVIDIA driver installation, NFS cache mounting, GPU auto-detection, and container lifecycle. Review found security issues (container runs as root, unvalidated env vars used in shell expansion), correctness bugs (hardcoded paths that drift from configurable values, integer truncation affecting model selection), and missing error handling.

## Critical Issues

### CR-01: Unquoted VLLM_EXTRA_ARGS causes word-splitting and globbing under set -euo pipefail

**File:** `auto-vllm-container/entrypoint.sh:12`
**Issue:** `${VLLM_EXTRA_ARGS:-}` is intentionally unquoted to allow multiple arguments, but this means any value containing glob characters (`*`, `?`, `[`) will be expanded against the filesystem, and arguments containing spaces in values (e.g., `--tokenizer-mode "slow mode"`) will be split incorrectly. Since `VLLM_EXTRA_ARGS` is user-supplied via environment variable, this is both a correctness bug and a minor injection vector -- a malicious env value can cause unintended filesystem interaction via globbing.
**Fix:** Use an array or `eval`-free argument parsing:
```bash
# Option A: disable globbing before expansion
set -f
exec vllm serve "${VLLM_MODEL}" \
    --host 0.0.0.0 \
    --port "${VLLM_PORT:-8000}" \
    --tensor-parallel-size "${VLLM_TENSOR_PARALLEL:-1}" \
    --gpu-memory-utilization "${VLLM_GPU_MEM_UTIL:-0.90}" \
    --max-model-len "${VLLM_MAX_MODEL_LEN:-32768}" \
    --max-num-batched-tokens "${VLLM_MAX_BATCHED_TOKENS:-32768}" \
    ${VLLM_EXTRA_ARGS:-}

# Option B (preferred): use bash array via word splitting with IFS
IFS=' ' read -r -a extra_args <<< "${VLLM_EXTRA_ARGS:-}"
exec vllm serve "${VLLM_MODEL}" \
    --host 0.0.0.0 \
    --port "${VLLM_PORT:-8000}" \
    --tensor-parallel-size "${VLLM_TENSOR_PARALLEL:-1}" \
    --gpu-memory-utilization "${VLLM_GPU_MEM_UTIL:-0.90}" \
    --max-model-len "${VLLM_MAX_MODEL_LEN:-32768}" \
    --max-num-batched-tokens "${VLLM_MAX_BATCHED_TOKENS:-32768}" \
    "${extra_args[@]}"
```

### CR-02: Hardcoded NFS mount path in container volume ignores configurable NFS_MOUNT_POINT

**File:** `auto-vllm-container/start-vllm.sh:127`
**Issue:** The `podman run` command hardcodes `-v /srv/hf-cache:/root/.cache/huggingface:ro` but `setup.sh` allows the NFS mount point to be configured via `NFS_MOUNT_POINT` (defaulting to `/srv/hf-cache`). If an operator sets `NFS_MOUNT_POINT=/data/models` in `setup.sh`, the NFS cache will be mounted there, but `start-vllm.sh` will still try to bind-mount `/srv/hf-cache` (which won't exist), causing the container to start with an empty or missing model cache. The vLLM process will then fail to load the model or re-download it (wasting bandwidth and time).
**Fix:**
```bash
NFS_MOUNT_POINT="${NFS_MOUNT_POINT:-/srv/hf-cache}"
# ...
podman run -d --replace \
    --name "$CONTAINER_NAME" \
    --device nvidia.com/gpu=all \
    -v "${NFS_MOUNT_POINT}:/root/.cache/huggingface:ro" \
```

### CR-03: Container runs as root -- no USER directive in Containerfile

**File:** `auto-vllm-container/Containerfile:1-20`
**Issue:** The Containerfile never sets a `USER` directive. The base image `vllm/vllm-openai:v0.8.5` runs as root by default. This means the vLLM inference server process runs as root inside the container. While this is an internal-network deployment, a vulnerability in vLLM or its dependencies could allow container escape with root privileges. The CLAUDE.md project constraints note "Internal network only, no external-facing endpoints in v1" but defense-in-depth still applies -- especially for a service that accepts and processes arbitrary user input (inference requests).
**Fix:** Add a non-root user after the `RUN apt-get` block:
```dockerfile
RUN useradd -m -s /bin/bash vllm
USER vllm
```
Note: The HuggingFace cache volume mount target (`/root/.cache/huggingface`) would also need to change to match the new user's home (e.g., `/home/vllm/.cache/huggingface`), and the volume mount in `start-vllm.sh` line 127 updated accordingly.

### CR-04: Missing VLLM_MODEL validation in entrypoint.sh causes cryptic failure

**File:** `auto-vllm-container/entrypoint.sh:5`
**Issue:** `"${VLLM_MODEL}"` is referenced without a default value. Under `set -u`, if `VLLM_MODEL` is not set, bash produces the error `bash: VLLM_MODEL: unbound variable` and exits. While fail-fast is correct, the error message gives no context about what the operator needs to do. In a containerized deployment where logs may be truncated or hard to access, this wastes debugging time. More critically, the `start-vllm.sh` script always sets this variable (line 129), but if someone runs the container image directly (e.g., `podman run vllm-inference`) without setting it, they get an opaque failure.
**Fix:**
```bash
if [[ -z "${VLLM_MODEL:-}" ]]; then
    echo "FATAL: VLLM_MODEL environment variable is required (e.g., 'Qwen/Qwen2.5-7B-Instruct')" >&2
    exit 1
fi
```

## Warnings

### WR-01: Integer truncation in GPU VRAM calculation can select wrong model

**File:** `auto-vllm-container/start-vllm.sh:10`
**Issue:** `GPU_VRAM_GB=$((GPU_VRAM_MB / 1024))` uses integer division, which truncates. A GPU reporting 16383 MB (just under 16 GB) becomes 15 GB. The T4 branch at line 47 checks `if [ $GPU_VRAM_GB -le 16 ]` -- a T4 with 15360 MB (15 GB after truncation, actually ~15 GB real) would select the 3B model instead of the 7B model. While T4s are consistently 16 GB, other GPUs have non-power-of-two VRAM sizes. The V100 branch checks `$total_vram -ge 64` which with 4x V100-16GB (each reporting ~16127 MB = 15 GB truncated) yields `total_vram=60`, failing the >= 64 check and selecting the 14B model instead of the 32B model.
**Fix:** Round to nearest instead of truncating:
```bash
GPU_VRAM_GB=$(( (GPU_VRAM_MB + 512) / 1024 ))
```

### WR-02: setup.sh mkdir without sudo will fail for system paths

**File:** `auto-vllm-container/setup.sh:67`
**Issue:** `mkdir -p "${NFS_MOUNT_POINT}"` runs without `sudo`, but the default `NFS_MOUNT_POINT` is `/srv/hf-cache`. Creating directories under `/srv` requires root privileges on most Linux systems. The subsequent `mount` command on line 69 also lacks `sudo`. The `mount_nfs_cache` function will fail on unprivileged execution even though every other privileged operation in `setup.sh` correctly uses `sudo`.
**Fix:**
```bash
sudo mkdir -p "${NFS_MOUNT_POINT}"
sudo timeout --kill-after=5 30 \
    mount -t nfs -o vers=3,soft,timeo=100,retrans=2 "${NFS_SERVER}" "${NFS_MOUNT_POINT}"
```

### WR-03: nvidia-smi failure in detect_gpu_info is not handled

**File:** `auto-vllm-container/start-vllm.sh:7-9`
**Issue:** Under `set -e`, if `nvidia-smi` is not installed or the driver is not loaded, lines 7-9 will cause the script to exit with a non-descriptive error. The `detect_gpu_info` function assumes nvidia-smi is available and working but provides no guard or diagnostic message. Since `start-vllm.sh` can be run independently of `setup.sh` (which installs the driver), this is a real failure path.
**Fix:**
```bash
detect_gpu_info() {
    if ! command -v nvidia-smi &>/dev/null; then
        echo "FATAL: nvidia-smi not found. Run setup.sh first or install NVIDIA drivers." >&2
        exit 1
    fi
    if ! nvidia-smi &>/dev/null; then
        echo "FATAL: nvidia-smi failed. NVIDIA driver may not be loaded." >&2
        exit 1
    fi
    GPU_MODEL=$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1 | xargs)
    GPU_COUNT=$(nvidia-smi --list-gpus | wc -l)
    GPU_VRAM_MB=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -1)
    GPU_VRAM_GB=$(( (GPU_VRAM_MB + 512) / 1024 ))
}
```

### WR-04: Firewall rule uses iptables instead of firewalld on modern Fedora/RHEL

**File:** `auto-vllm-container/setup.sh:72-79`
**Issue:** The `configure_firewall` function uses raw `iptables` commands and saves to `/etc/sysconfig/iptables`, then restarts the `iptables` systemd service. Modern RHEL 9+ and Fedora systems use `firewalld` by default. If `firewalld` is running, these iptables rules may be overwritten on the next firewalld reload. Additionally, if the `iptables` service is not installed, `systemctl restart iptables` on line 79 will fail under `set -e`, aborting the entire setup even though the rule was already added. The QUADS lab servers are RHEL/Fedora-based (implied by `dnf` usage on line 35).
**Fix:** Detect the firewall manager:
```bash
configure_firewall() {
    if command -v firewall-cmd &>/dev/null && systemctl is-active --quiet firewalld; then
        if firewall-cmd --query-port="${VLLM_PORT}/tcp" &>/dev/null; then
            echo "Firewall rule already exists for port ${VLLM_PORT}, skipping"
            return 0
        fi
        sudo firewall-cmd --permanent --add-port="${VLLM_PORT}/tcp"
        sudo firewall-cmd --reload
    else
        # fallback to iptables
        if sudo iptables -C INPUT -p tcp --dport "${VLLM_PORT}" -j ACCEPT 2>/dev/null; then
            echo "Firewall rule already exists for port ${VLLM_PORT}, skipping"
            return 0
        fi
        sudo iptables -I INPUT -p tcp --dport "${VLLM_PORT}" -j ACCEPT
    fi
}
```

### WR-05: NFS server hostname and path hardcoded as default value

**File:** `auto-vllm-container/setup.sh:5`
**Issue:** `NFS_SERVER` defaults to `rdu-storage02.scalelab.redhat.com:/mnt/SATA/scratch/grafuls/hf-cache` -- a specific internal hostname with a user-specific path (`grafuls`). This couples the script to one person's storage allocation. Any other operator running `setup.sh` without explicitly setting `NFS_SERVER` will attempt to mount this specific share, which may not exist, may have different permissions, or may expose that user's cached models. This should either have no default (requiring explicit configuration) or use a team-shared path.
**Fix:** Remove the default and require explicit configuration:
```bash
NFS_SERVER="${NFS_SERVER:?FATAL: NFS_SERVER must be set (e.g., storage.lab:./path/to/cache)}"
```

## Info

### IN-01: Containerfile does not pin apt package versions

**File:** `auto-vllm-container/Containerfile:6-9`
**Issue:** `apt-get install -y curl jq procps` installs whatever version is current, meaning builds are not reproducible. A future `curl` or `jq` update could introduce a breaking change or vulnerability. For production containers, pinning versions improves reproducibility.
**Fix:** Pin versions or accept the risk with a comment:
```dockerfile
# ponytail: unpinned -- these are debug tools, not runtime deps
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl jq procps && \
    rm -rf /var/lib/apt/lists/*
```

### IN-02: start-vllm.sh does not clean up container on script failure

**File:** `auto-vllm-container/start-vllm.sh:104-139`
**Issue:** If `podman build` succeeds but `podman run` fails, no cleanup occurs. The `--replace` flag on `podman run` handles re-runs, but a failed build leaves stale image layers. Additionally, the script has no `trap` for cleanup on `SIGINT`/`SIGTERM` during the build phase.
**Fix:** Add a trap for cleanup:
```bash
# ponytail: add when builds are frequent enough that stale layers matter
trap 'echo "Interrupted, cleaning up..."; podman rm -f "$CONTAINER_NAME" 2>/dev/null || true' EXIT
```

---

_Reviewed: 2026-07-01T12:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
