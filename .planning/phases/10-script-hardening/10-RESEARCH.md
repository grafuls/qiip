# Phase 10: Script Hardening - Research

**Researched:** 2026-07-01
**Domain:** Bash shell scripting -- idempotency, fail-fast, timeout handling, container lifecycle
**Confidence:** HIGH

## Summary

Phase 10 hardens two existing bash scripts (`setup.sh` and `start-vllm.sh`) and restructures the container boundary. The current `setup.sh` has zero error handling -- no `set -e`, no idempotency guards, no NFS timeout, and hardcoded values throughout. The current `start-vllm.sh` contains both GPU detection logic and the `vllm serve` exec, which need to be split: GPU detection moves to a new host-side launcher, and the `vllm serve` exec becomes a thin `entrypoint.sh`.

This is a pure shell scripting phase. No Python packages are installed. No new dependencies are added to the gateway. The deliverables are three hardened shell scripts and one updated Containerfile. All patterns use standard POSIX/bash builtins and coreutils (`timeout`, `mountpoint`, `nvidia-smi`).

**Primary recommendation:** Apply `set -euo pipefail` + per-step idempotency guards + structured `[STEP:name:STATUS]` markers to `setup.sh`, split `start-vllm.sh` into host launcher + container entrypoint, use `timeout 30 mount` for NFS, and use `podman run --replace` for container name collisions.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Rename current `start-vllm.sh` to `entrypoint.sh` (thin container entrypoint that runs `vllm serve` with env vars). New `start-vllm.sh` is the host-side launcher that does `podman build` + `podman run -d --replace`.
- **D-02:** `start-vllm.sh` (host launcher) does both `podman build` and `podman run` in one invocation. Rebuilds image each time.
- **D-03:** Container name is model-based (e.g., `vllm-qwen2.5-72b`). Allows future multi-model-per-host. Teardown (Phase 13) targets this name.
- **D-04:** GPU detection and model selection move to the host-side `start-vllm.sh`. Model and params passed to container as env vars. `entrypoint.sh` is a thin wrapper -- no detection logic.
- **D-05:** NFS mount timeout is 30 seconds. If mount fails or times out, `setup.sh` aborts entirely with non-zero exit. No NFS = no model cache = can't serve.
- **D-06:** If NFS is already mounted (`mountpoint -q /srv/hf-cache`), skip the mount step. No remount.
- **D-07:** All hardcoded values become env vars with current values as defaults: `NFS_SERVER`, `NFS_MOUNT_POINT`, `NVIDIA_DRIVER_URL`, `VLLM_PORT`, etc. Scripts work unchanged for Scale/Alias labs.
- **D-08:** NVIDIA driver version is pinned (known-good version as default env var). No auto-detection of latest driver.
- **D-09:** If `nvidia-smi` succeeds (driver already installed), skip the entire driver install block (download, blacklist nouveau, dracut, install). Biggest idempotency win.
- **D-10:** Scripts emit structured step markers for remote progress tracking. Format: `[STEP:name:STATUS]` prefix lines (e.g., `[STEP:nvidia_driver:START]`, `[STEP:nfs_mount:OK]`). Human-readable, easy to grep from asyncssh output.
- **D-11:** `setup.sh` emits 6 step names matching logical blocks: `nvidia_repo`, `system_update`, `nvidia_driver`, `nvidia_cdi`, `nfs_mount`, `firewall`.

### Claude's Discretion
None -- all decisions made by user.

### Deferred Ideas (OUT OF SCOPE)
None.

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SCRIPT-01 | setup.sh exits on first error (set -e) and validates prerequisites before starting | `set -euo pipefail` at script top + step-wrapper function that emits `[STEP:name:FAIL]` and exits non-zero. See Architecture Patterns. |
| SCRIPT-02 | setup.sh steps are idempotent (re-running skips already-completed steps) | Guard each step with a completion check (e.g., `nvidia-smi` success skips driver install, `mountpoint -q` skips NFS mount). See Idempotency Guards pattern. |
| SCRIPT-03 | NFS mount uses timeout options to prevent indefinite hangs | `timeout 30 mount -t nfs ...` wraps the mount call. 30-second ceiling per D-05. See NFS Timeout pattern. |
| SCRIPT-04 | start-vllm.sh runs vLLM container detached (podman run -d) with --replace for name collisions | Host-side `start-vllm.sh` uses `podman run -d --replace --name "$CONTAINER_NAME"`. Container name is model-based per D-03. See Container Lifecycle pattern. |

</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Host setup (drivers, NFS, firewall) | Host OS (bash) | -- | `setup.sh` runs directly on bare metal via sudo |
| GPU detection + model selection | Host OS (bash) | -- | `start-vllm.sh` (host launcher) queries `nvidia-smi` on the host |
| Container build + launch | Host OS (bash) | Container runtime (podman) | Host launcher invokes `podman build` and `podman run` |
| vLLM process execution | Container (entrypoint.sh) | -- | Thin entrypoint receives env vars, runs `vllm serve` |
| Progress reporting | Host OS (bash) | Gateway (Phase 11 consumer) | `[STEP:name:STATUS]` markers on stdout, parsed by asyncssh in Phase 11 |

## Architecture Patterns

### System Architecture Diagram

```
Remote Host (via SSH in Phase 11)
==================================

  setup.sh (run once or idempotently)
    |
    +--> [STEP:nvidia_repo:START] --> add NVIDIA repo --> [OK/FAIL]
    +--> [STEP:system_update:START] --> dnf update --> [OK/FAIL]
    +--> [STEP:nvidia_driver:START] --> nvidia-smi? skip : install --> [OK/FAIL]
    +--> [STEP:nvidia_cdi:START] --> nvidia-ctk cdi generate --> [OK/FAIL]
    +--> [STEP:nfs_mount:START] --> mountpoint? skip : timeout 30 mount --> [OK/FAIL]
    +--> [STEP:firewall:START] --> iptables rule --> [OK/FAIL]

  start-vllm.sh (host launcher)
    |
    +--> detect_gpu_info (nvidia-smi)
    +--> configure_vllm_params (model selection)
    +--> podman build -t vllm-inference .
    +--> podman run -d --replace --name vllm-<model-slug> \
           -e VLLM_MODEL=... -e VLLM_PORT=... \
           vllm-inference
           |
           +--> entrypoint.sh (inside container)
                  |
                  +--> exec vllm serve $VLLM_MODEL --host 0.0.0.0 ...
```

### File Deliverables

| File | Role | Changes |
|------|------|---------|
| `auto-vllm-container/setup.sh` | Host setup | Add `set -euo pipefail`, idempotency guards, step markers, env var defaults, NFS timeout |
| `auto-vllm-container/start-vllm.sh` | Host launcher (NEW role) | GPU detection + model selection + `podman build` + `podman run -d --replace` |
| `auto-vllm-container/entrypoint.sh` | Container entrypoint (NEW file) | Thin wrapper: receives env vars, runs `exec vllm serve` |
| `auto-vllm-container/Containerfile` | Container definition | Change `COPY ./start-vllm.sh` to `COPY ./entrypoint.sh`, update ENTRYPOINT |

### Pattern 1: Fail-Fast with Step Markers

**What:** Wrap each logical step in a function that emits `[STEP:name:STATUS]` markers and aborts on failure.
**When to use:** Every step in `setup.sh`.

```bash
# [ASSUMED] -- standard bash pattern, not library-specific
#!/bin/bash
set -euo pipefail

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

# Usage:
step nvidia_repo install_nvidia_repo
step system_update run_system_update
# ... etc
```

**Why this works:** `set -e` catches unexpected failures. The `step` wrapper catches expected failures and emits structured output. The `if "$@"` pattern runs the command in a context where `set -e` does NOT apply (the `if` disables errexit for its condition), so we get explicit control over the exit behavior.

### Pattern 2: Idempotency Guards

**What:** Check completion state before executing each step. Skip if already done.
**When to use:** Every step that has a detectable completion state.

```bash
# [ASSUMED] -- standard bash patterns
install_nvidia_driver() {
    if nvidia-smi &>/dev/null; then
        echo "NVIDIA driver already installed, skipping"
        return 0
    fi
    # ... download and install driver
}

mount_nfs_cache() {
    local mount_point="${NFS_MOUNT_POINT:-/srv/hf-cache}"
    if mountpoint -q "$mount_point"; then
        echo "NFS already mounted at $mount_point, skipping"
        return 0
    fi
    mkdir -p "$mount_point"
    timeout 30 mount -t nfs -o vers=3 "${NFS_SERVER}" "$mount_point"
}
```

| Step | Guard Condition | Skip When |
|------|----------------|-----------|
| nvidia_repo | `test -f /etc/yum.repos.d/nvidia-container-toolkit.repo` | Repo file exists |
| system_update | None (always runs -- dnf update is idempotent) | Never skipped |
| nvidia_driver | `nvidia-smi` exits 0 (D-09) | Driver already installed |
| nvidia_cdi | `test -f /etc/cdi/nvidia.yaml` | CDI descriptor exists |
| nfs_mount | `mountpoint -q $NFS_MOUNT_POINT` (D-06) | Already mounted |
| firewall | `iptables -C INPUT -p tcp --dport $VLLM_PORT -j ACCEPT 2>/dev/null` | Rule already exists |

### Pattern 3: NFS Timeout

**What:** Wrap the NFS mount in `timeout 30` to enforce the 30-second ceiling (D-05).
**When to use:** The `nfs_mount` step.

```bash
# [VERIFIED: coreutils timeout, mount.nfs confirmed on host]
mount_nfs_cache() {
    local mount_point="${NFS_MOUNT_POINT:-/srv/hf-cache}"
    local nfs_server="${NFS_SERVER:-rdu-storage02.scalelab.redhat.com:/mnt/SATA/scratch/grafuls/hf-cache}"

    if mountpoint -q "$mount_point"; then
        echo "NFS already mounted at $mount_point, skipping"
        return 0
    fi

    mkdir -p "$mount_point"
    # timeout sends SIGTERM after 30s, SIGKILL after 35s
    timeout --kill-after=5 30 \
        mount -t nfs -o vers=3,soft,timeo=100,retrans=2 "$nfs_server" "$mount_point"
}
```

Two layers of defense:
1. `timeout 30` -- kills the mount process if it hangs (handles unresponsive server, DNS resolution hang, etc.)
2. `soft,timeo=100,retrans=2` -- NFS client-side options: `timeo=100` is 10 seconds (in deciseconds) per attempt, `retrans=2` is 2 retries. `soft` returns EIO on timeout instead of hanging forever. Belt and suspenders.

### Pattern 4: Container Lifecycle (--replace)

**What:** Use `podman run --replace` so a container with the same name is stopped/removed before the new one starts.
**When to use:** `start-vllm.sh` host launcher.

```bash
# [VERIFIED: podman 5.8.3 --replace flag confirmed on host]
CONTAINER_NAME="vllm-$(echo "$MODEL" | tr '/' '-' | tr '[:upper:]' '[:lower:]' | sed 's/.*\///')"
# e.g., Qwen/Qwen2.5-72B-Instruct -> vllm-qwen2.5-72b-instruct

podman run -d --replace \
    --name "$CONTAINER_NAME" \
    --device nvidia.com/gpu=all \
    -v /srv/hf-cache:/root/.cache/huggingface:ro \
    -p "${VLLM_PORT:-8000}:8000" \
    -e VLLM_MODEL="$MODEL" \
    -e VLLM_PORT=8000 \
    -e VLLM_TENSOR_PARALLEL="$TENSOR_PARALLEL" \
    -e VLLM_GPU_MEM_UTIL="$GPU_MEM_UTIL" \
    -e VLLM_MAX_MODEL_LEN="$MAX_MODEL_LEN" \
    -e VLLM_MAX_BATCHED_TOKENS="$MAX_BATCHED_TOKENS" \
    -e VLLM_EXTRA_ARGS="$EXTRA_ARGS" \
    vllm-inference
```

### Pattern 5: Thin Container Entrypoint

**What:** `entrypoint.sh` receives all config via env vars and runs `exec vllm serve`.
**When to use:** Inside the container (replaces current `start-vllm.sh` behavior).

```bash
# [ASSUMED] -- straightforward exec wrapper
#!/bin/bash
set -euo pipefail

exec vllm serve "${VLLM_MODEL}" \
    --host 0.0.0.0 \
    --port "${VLLM_PORT:-8000}" \
    --tensor-parallel-size "${VLLM_TENSOR_PARALLEL:-1}" \
    --gpu-memory-utilization "${VLLM_GPU_MEM_UTIL:-0.90}" \
    --max-model-len "${VLLM_MAX_MODEL_LEN:-32768}" \
    --max-num-batched-tokens "${VLLM_MAX_BATCHED_TOKENS:-32768}" \
    ${VLLM_EXTRA_ARGS:-}
```

### Pattern 6: Env Var Defaults (D-07)

**What:** All hardcoded values become env vars with current values as defaults.

```bash
# [ASSUMED] -- standard bash parameter expansion
# setup.sh top section
NFS_SERVER="${NFS_SERVER:-rdu-storage02.scalelab.redhat.com:/mnt/SATA/scratch/grafuls/hf-cache}"
NFS_MOUNT_POINT="${NFS_MOUNT_POINT:-/srv/hf-cache}"
NVIDIA_DRIVER_VERSION="${NVIDIA_DRIVER_VERSION:-580.126.09}"
NVIDIA_DRIVER_URL="${NVIDIA_DRIVER_URL:-https://us.download.nvidia.com/tesla/${NVIDIA_DRIVER_VERSION}/NVIDIA-Linux-x86_64-${NVIDIA_DRIVER_VERSION}.run}"
VLLM_PORT="${VLLM_PORT:-8000}"
```

### Anti-Patterns to Avoid

- **Testing `$?` after a command under `set -e`:** If you write `command; if [ $? -ne 0 ]`, the script exits at `command` before reaching the `if`. Use `if command; then` or `command || handle_error` instead.
- **Using `set -e` inside the `step()` function body for the command:** The `if "$@"` pattern correctly disables errexit for the command being tested. Do NOT use `"$@" || ...` inside a function that also has a trap -- it gets confusing. The `if/else` is clearest.
- **Quoting `${VLLM_EXTRA_ARGS}`:** This var may contain multiple space-separated flags. Use `${VLLM_EXTRA_ARGS:-}` unquoted so word splitting applies correctly. This is one of the rare cases where unquoted expansion is intentional.
- **Forgetting `--kill-after` on `timeout`:** Without `--kill-after`, a process that ignores SIGTERM will hang forever. Always pair `timeout` with `--kill-after=5`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| NFS hang prevention | Custom polling loop | `timeout 30 mount` + NFS `soft,timeo` options | coreutils `timeout` handles SIGTERM/SIGKILL correctly; NFS `soft` option is kernel-level |
| Container replacement | Manual `podman stop && podman rm && podman run` | `podman run --replace` | Atomic operation, handles race conditions, built into podman |
| Idempotent mount check | `grep /proc/mounts` parsing | `mountpoint -q` | Purpose-built tool, handles edge cases (bind mounts, stale mounts) |
| Idempotent iptables | Parse iptables-save output | `iptables -C` (check rule exists) | Returns 0/1 cleanly, no parsing needed |

## Common Pitfalls

### Pitfall 1: `set -e` in Command Substitution

**What goes wrong:** `set -e` does NOT apply inside `$()` command substitutions in some bash versions. A failing command inside `$(...)` silently produces empty output.
**Why it happens:** POSIX spec allows this behavior; bash historically didn't propagate errexit into subshells in `$()`.
**How to avoid:** For critical command substitutions, assign to a variable and check: `local result; result=$(cmd) || { echo "failed"; exit 1; }`.
**Warning signs:** Empty variables where you expected a value.

### Pitfall 2: `set -u` and Optional Env Vars

**What goes wrong:** `set -u` (nounset) causes the script to exit if any variable is unbound. `${EXTRA_ARGS}` without a default will kill the script.
**Why it happens:** EXTRA_ARGS is only set for some GPU types (T4, RTX, unknown).
**How to avoid:** Always provide a default: `${EXTRA_ARGS:-}`. The `:-` syntax returns empty string if unset.
**Warning signs:** `unbound variable` errors in scripts that worked before adding `set -u`.

### Pitfall 3: `nvidia-smi` Exit Code Nuance

**What goes wrong:** `nvidia-smi` can exit 0 even with a stale/broken driver (returns GPU info but driver is half-installed).
**Why it happens:** The binary exists but the kernel module is corrupt or version-mismatched.
**How to avoid:** For the idempotency guard (D-09), `nvidia-smi` success is good enough -- if the driver is truly broken, the container will fail later and the operator will re-run setup. Over-validating here adds complexity without value.
**Warning signs:** Container fails to start with CUDA errors despite `nvidia-smi` succeeding.

### Pitfall 4: `podman build` Caching vs `--replace`

**What goes wrong:** `podman build` reuses cached layers. If `entrypoint.sh` changed but the `COPY` layer is cached, the old entrypoint runs.
**Why it happens:** Podman uses layer caching by default. File content changes invalidate the cache, but timestamp-only changes may not.
**How to avoid:** The current approach (rebuild each time per D-02) is correct. If builds become slow, add `--no-cache` or use `--layers=false`. For now, default layer caching is fine since the Containerfile is small.
**Warning signs:** Container behavior doesn't match script changes.

### Pitfall 5: NFS `soft` Mount Data Integrity

**What goes wrong:** `soft` mounts return EIO on timeout, which can corrupt reads mid-transfer.
**Why it happens:** The client gives up and returns an error to the application.
**How to avoid:** For this use case (read-only model cache), `soft` is acceptable -- a timeout means the server is unreachable and we want to fail fast, not hang. The models are read atomically by vLLM at startup. If the mount fails mid-operation, vLLM will crash and restart.
**Warning signs:** EIO errors in vLLM logs when NFS server is flaky.

## Code Examples

### Complete setup.sh Structure

```bash
#!/bin/bash
# Source: pattern synthesis from D-01 through D-11
set -euo pipefail

# --- Configurable defaults (D-07) ---
NFS_SERVER="${NFS_SERVER:-rdu-storage02.scalelab.redhat.com:/mnt/SATA/scratch/grafuls/hf-cache}"
NFS_MOUNT_POINT="${NFS_MOUNT_POINT:-/srv/hf-cache}"
NVIDIA_DRIVER_VERSION="${NVIDIA_DRIVER_VERSION:-580.126.09}"
NVIDIA_DRIVER_URL="${NVIDIA_DRIVER_URL:-https://us.download.nvidia.com/tesla/${NVIDIA_DRIVER_VERSION}/NVIDIA-Linux-x86_64-${NVIDIA_DRIVER_VERSION}.run}"
VLLM_PORT="${VLLM_PORT:-8000}"

# --- Step wrapper (D-10) ---
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

# --- Step functions (D-09, D-06 idempotency) ---

install_nvidia_repo() {
    if [ -f /etc/yum.repos.d/nvidia-container-toolkit.repo ]; then
        echo "NVIDIA repo already configured, skipping"
        return 0
    fi
    curl -fsSL https://nvidia.github.io/libnvidia-container/stable/rpm/nvidia-container-toolkit.repo \
        | sudo tee /etc/yum.repos.d/nvidia-container-toolkit.repo > /dev/null
}

run_system_update() {
    sudo dnf -y update
    sudo dnf -y install kernel-devel-"$(uname -r)" kernel-headers-"$(uname -r)" \
        nvidia-container-toolkit podman-plugins wget podman nfs-utils
}

install_nvidia_driver() {
    if nvidia-smi &>/dev/null; then
        echo "NVIDIA driver already installed, skipping"
        return 0
    fi
    echo 'blacklist nouveau' | sudo tee /etc/modprobe.d/blacklist-nouveau.conf
    sudo dracut --force
    sudo modprobe -r nouveau 2>/dev/null || true
    wget -q "${NVIDIA_DRIVER_URL}" -O "/tmp/NVIDIA-driver.run"
    chmod +x /tmp/NVIDIA-driver.run
    sudo sh /tmp/NVIDIA-driver.run --dkms --no-x-check --no-nouveau-check --ui=none --no-questions
    rm -f /tmp/NVIDIA-driver.run
}

generate_nvidia_cdi() {
    if [ -f /etc/cdi/nvidia.yaml ]; then
        echo "NVIDIA CDI descriptor already exists, skipping"
        return 0
    fi
    sudo nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml
}

mount_nfs_cache() {
    if mountpoint -q "${NFS_MOUNT_POINT}"; then
        echo "NFS already mounted at ${NFS_MOUNT_POINT}, skipping"
        return 0
    fi
    mkdir -p "${NFS_MOUNT_POINT}"
    timeout --kill-after=5 30 \
        mount -t nfs -o vers=3,soft,timeo=100,retrans=2 "${NFS_SERVER}" "${NFS_MOUNT_POINT}"
}

configure_firewall() {
    if sudo iptables -C INPUT -p tcp --dport "${VLLM_PORT}" -j ACCEPT 2>/dev/null; then
        echo "Firewall rule already exists for port ${VLLM_PORT}, skipping"
        return 0
    fi
    sudo iptables -I INPUT -p tcp --dport "${VLLM_PORT}" -j ACCEPT
    sudo iptables-save | sudo tee /etc/sysconfig/iptables > /dev/null
    sudo systemctl restart iptables
}

# --- Main (D-11: 6 step names) ---
step nvidia_repo install_nvidia_repo
step system_update run_system_update
step nvidia_driver install_nvidia_driver
step nvidia_cdi generate_nvidia_cdi
step nfs_mount mount_nfs_cache
step firewall configure_firewall

echo "Setup complete"
```

### Container Name Derivation (D-03)

```bash
# Derive container name from model path
# Qwen/Qwen2.5-72B-Instruct -> vllm-qwen2.5-72b-instruct
derive_container_name() {
    local model="$1"
    local slug
    slug=$(echo "$model" | awk -F'/' '{print $NF}' | tr '[:upper:]' '[:lower:]')
    echo "vllm-${slug}"
}
```

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x (existing) + bash script validation |
| Config file | `pyproject.toml` (existing) |
| Quick run command | `bash -n auto-vllm-container/setup.sh` (syntax check) |
| Full suite command | `pytest tests/ -x` |

### Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SCRIPT-01 | setup.sh exits on first error | manual-only | Cannot unit-test sudo/mount operations locally | N/A |
| SCRIPT-02 | setup.sh steps are idempotent | manual-only | Requires NVIDIA GPU + NFS server | N/A |
| SCRIPT-03 | NFS mount uses timeout | manual-only | Requires NFS infrastructure | N/A |
| SCRIPT-04 | start-vllm.sh uses --replace | manual-only | Requires podman + GPU | N/A |

**Justification for manual-only:** All four requirements operate on bare-metal host state (NVIDIA drivers, NFS mounts, iptables, podman containers). These cannot be unit tested without the actual hardware and network infrastructure. Validation is structural:
1. `bash -n <script>` -- syntax validation (automated)
2. `shellcheck <script>` -- static analysis (automated if shellcheck installed)
3. Code review -- verify patterns match research (human)
4. Live execution on a test host -- functional validation (human/Phase 11)

### Wave 0 Gaps
- [ ] Install `shellcheck` for static analysis: `sudo dnf install ShellCheck` or download binary
- [ ] Run `bash -n` on all scripts as a pre-commit sanity check

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | -- |
| V3 Session Management | no | -- |
| V4 Access Control | no | -- |
| V5 Input Validation | yes | Env var defaults with `${VAR:-default}` pattern; no user-facing input |
| V6 Cryptography | no | -- |

### Known Threat Patterns for bash scripts on remote hosts

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Command injection via env vars | Tampering | All env vars used in controlled contexts (mount paths, URLs); no `eval` usage |
| Privilege escalation via sudo | Elevation | Scripts already require root/sudo -- this is by design for driver/mount operations |
| NVIDIA driver supply chain | Tampering | Pinned driver version (D-08), HTTPS download URL |
| NFS path traversal | Tampering | Hardcoded mount point with env var override; no user input |

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `docker run` + manual stop/rm | `podman run --replace` | podman 3.x+ | Single atomic command for container replacement |
| `mount -t nfs` with no timeout | `timeout N mount -t nfs -o soft,timeo=X` | Always available | Prevents indefinite hangs |
| Monolithic container entrypoint | Split host launcher + thin entrypoint | Architectural decision (D-01) | Cleaner separation of host vs container concerns |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `if "$@"` disables errexit for its condition in bash 5.x | Pattern 1 | Step failures would exit before emitting `[STEP:name:FAIL]` marker -- wrong marker output |
| A2 | `iptables -C` returns 0 if rule exists, non-zero otherwise | Idempotency Guards | Firewall step would re-add duplicate rules on each run |
| A3 | `nvidia-docker2` package name is correct for the dnf install | Code Examples | Package install would fail; may be `nvidia-container-toolkit` only |
| A4 | vLLM `vllm serve` command syntax accepts all listed flags | Pattern 5 | Container would fail to start |

## Open Questions

1. **nvidia-docker2 vs nvidia-container-toolkit**
   - What we know: Current `setup.sh` installs both `nvidia-container-toolkit` and `nvidia-docker2`. The `nvidia-docker2` package may be Docker-specific and unnecessary with podman.
   - What's unclear: Whether `nvidia-docker2` provides anything needed beyond `nvidia-container-toolkit` for podman-based workflows.
   - Recommendation: During implementation, check if removing `nvidia-docker2` from the install list breaks anything. It's likely unnecessary since podman uses CDI, not the Docker runtime hook.

2. **CDI descriptor regeneration**
   - What we know: D-09 skips driver install if `nvidia-smi` succeeds. The CDI guard checks `test -f /etc/cdi/nvidia.yaml`.
   - What's unclear: If the driver is updated outside this script, the CDI descriptor may be stale.
   - Recommendation: For v1.2, the file-existence check is sufficient. If CDI staleness becomes an issue, regeneration can be forced by deleting the file.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| bash | All scripts | Yes | 5.3.9 | -- |
| podman | Container lifecycle | Yes | 5.8.3 | -- |
| timeout (coreutils) | NFS timeout | Yes | (bundled) | -- |
| mountpoint (util-linux) | Idempotent NFS check | Yes | (bundled) | -- |
| shellcheck | Static analysis | No | -- | `bash -n` for syntax; install with `sudo dnf install ShellCheck` |
| nvidia-smi | GPU detection | No (dev machine) | -- | Expected on target hosts only |
| NFS infrastructure | Model cache | No (dev machine) | -- | Expected on target hosts only |

**Missing dependencies with no fallback:** None (all missing tools are expected to be on target hosts, not the dev machine).

**Missing dependencies with fallback:**
- shellcheck: Install for better static analysis, or use `bash -n` for basic syntax validation.

## Project Constraints (from CLAUDE.md)

- **SOLID principles required** -- not directly applicable to bash scripts, but the step-function pattern follows Single Responsibility (each step function does one thing).
- **Tech stack**: Python, FastAPI -- this phase is bash-only, no Python changes.
- **GSD workflow enforcement** -- follow GSD commands for execution.

## Sources

### Primary (HIGH confidence)
- `auto-vllm-container/setup.sh` -- current script read directly, no error handling present
- `auto-vllm-container/start-vllm.sh` -- current script read directly, has `set -euo pipefail` and GPU detection
- `auto-vllm-container/Containerfile` -- current container definition read directly
- `podman run --replace` -- verified available on host via `podman run --help` (podman 5.8.3)
- `timeout` command -- verified available on host via `timeout --help`
- `mountpoint` command -- verified available on host at `/usr/bin/mountpoint`

### Secondary (MEDIUM confidence)
- NFS mount options (`soft,timeo,retrans`) -- standard NFS client options, verified via `mount.nfs --help`

### Tertiary (LOW confidence)
- `iptables -C` behavior -- [ASSUMED] based on training data, standard iptables feature

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- pure bash, no external packages, all tools verified on host
- Architecture: HIGH -- all decisions locked by user, patterns are straightforward bash
- Pitfalls: HIGH -- well-known bash gotchas, documented in official bash manual

**Research date:** 2026-07-01
**Valid until:** 2026-08-01 (stable -- bash/podman/NFS are mature, slow-moving)
