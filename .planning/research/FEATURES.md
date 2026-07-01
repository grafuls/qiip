# Feature Landscape

**Domain:** SSH-based GPU node provisioning and teardown for vLLM inference gateway
**Researched:** 2026-07-01
**Context:** v1.2 milestone for QUADS LLM Inference Proxy. Existing gateway has OpenAI proxy, etcd discovery, load balancing, circuit breaker, health checks, admin API, and operations dashboard. This research covers adding SSH-based node setup/teardown from the gateway itself.

## Setup Pipeline (What the Existing Scripts Do)

The existing `auto-vllm-container/` directory defines a concrete, already-validated provisioning pipeline. Any SSH-based automation must execute these steps remotely:

1. **NVIDIA repo setup** -- `curl` NVIDIA container toolkit repo into yum repos
2. **System update** -- `dnf -y update`
3. **Dependency install** -- kernel-devel, kernel-headers, nvidia-container-toolkit, podman, nfs-utils, wget
4. **Blacklist nouveau** -- write modprobe blacklist, rebuild initramfs, unload nouveau
5. **NVIDIA driver install** -- download and run `.run` installer (580.126.09) with DKMS
6. **CDI generation** -- `nvidia-ctk cdi generate` for Podman GPU access
7. **NFS mount** -- mount shared Hugging Face cache from NFS server
8. **Firewall** -- open port 8000 via iptables
9. **Container build** -- `podman build -t auto-vllm -f Containerfile .`
10. **Container start** -- `podman run` with GPU passthrough, NFS volume mount, network=host
11. **Health poll** -- wait for `curl http://{host}:8000/health` to return 200
12. **etcd registration** -- register node with endpoint, model info, capabilities

Steps 1-8 are `setup.sh`. Steps 9-10 are manual (README). Steps 11-12 are gateway-side.

## Table Stakes

Features that MUST exist for v1.2 to be usable. Without these, operators fall back to SSH-ing manually.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **SSH connection to remote host** | The entire provisioning model requires executing commands on bare-metal GPU servers. Operators expect to provide a hostname and have the gateway connect. | Low | Use asyncssh (asyncio-native). Authenticate via pre-configured SSH keys (`~/.ssh/`). No password auth -- keys are standard in QUADS labs. |
| **Run setup.sh remotely** | The existing setup script handles driver install, toolkit setup, NFS mount, firewall. Operators expect to not rewrite this. | Medium | Upload or pipe `setup.sh` to remote host, execute via SSH. Script is idempotent-ish (dnf handles already-installed, but driver re-install and initramfs rebuild will re-run). Must handle sudo (NOPASSWD expected on lab servers). |
| **Container image build** | The vLLM container must be built on the target host from the Containerfile. | Low | `podman build -t auto-vllm -f Containerfile .` on remote host. Requires uploading `Containerfile` and `start-vllm.sh` first. |
| **Container start with GPU passthrough** | The vLLM container must run with `--device nvidia.com/gpu=all`, NFS mount, and host networking. | Low | Fixed `podman run` command from README. GPU auto-detection happens inside the container via `start-vllm.sh`. |
| **Health poll after start** | vLLM takes 30s-5min to load a model (depends on model size and GPU). The gateway must poll `/health` until it succeeds before declaring the node ready. | Low | Poll `http://{host}:8000/health` with backoff. Timeout after configurable max wait (default: 10 min for large models on slow hardware). |
| **etcd registration after health** | Once the node is healthy, register it in etcd with endpoint, model, and capabilities so the existing discovery system picks it up. | Low | Use existing `node_to_etcd()` serializer and `EtcdClient`. The etcd watcher will propagate the new node to the registry automatically. |
| **Node teardown (container stop)** | Operators need to decommission a node: stop the container, remove it from the pool. | Low | SSH to host, `podman stop auto-vllm`. Or if the gateway already has the host info, it can do this remotely. |
| **etcd deregistration on teardown** | Remove the node key from etcd so the watcher drops it from the registry. | Low | Delete the etcd key. Existing watcher handles propagation. |
| **Setup status tracking** | Setup takes 5-30 minutes (driver install is slow). Operators need to know what step is running and whether it succeeded or failed. | Medium | State machine: PENDING -> CONNECTING -> SETUP_RUNNING -> BUILDING -> STARTING -> HEALTH_CHECK -> REGISTERING -> COMPLETE (or FAILED at any step). Store in-memory per-host. |
| **Admin API for setup/teardown** | `POST /admin/nodes/setup` and `DELETE /admin/nodes/{id}` so operators (and the dashboard) can trigger provisioning. | Low | FastAPI endpoints on the existing admin router. Setup is async (returns immediately with a task ID, operator polls for status). Teardown can be synchronous (fast). |
| **Setup error reporting** | When setup fails (SSH unreachable, driver install fails, container won't start), the operator must see what went wrong and at which step. | Medium | Capture stderr/stdout from each SSH command. Store the failing step and error output. Return via status API. |

## Differentiators

Features that add operational value but are not strictly required for v1.2 to work.

### Tier 1 (High Value for v1.2)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Step-by-step progress via dashboard** | Operators see "Installing NVIDIA driver..." or "Building container..." in the dashboard UI instead of a blank spinner. Much better UX than "setup in progress." | Medium | Dashboard polls a status endpoint that returns current step + output tail. Reuse existing polling pattern (vanilla JS `setInterval`). |
| **Pre-flight validation** | Before starting the full setup, check: SSH reachable? GPUs detected (`lspci`)? Enough disk space? Prevents wasting 10 minutes on a doomed setup. | Low | Run quick SSH commands before committing to the full pipeline. Fail fast with a clear error. |
| **Connection draining before teardown** | Before stopping the container, drain active connections (stop routing new requests, wait for in-flight to finish). Already partially implemented in v1.0 (`registry.drain()`). | Low | Call `registry.drain(node_id)`, wait for `active_connections == 0` (with timeout), then proceed with container stop + deregistration. |
| **Setup log capture** | Store full stdout/stderr from each step. Operators can view the complete setup log for debugging. | Low | Append SSH output to an in-memory buffer per setup task. Expose via `GET /admin/nodes/setup/{task_id}/log`. Cap buffer size (last 1000 lines). |

### Tier 2 (Nice-to-Have, Consider for v1.3+)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Parallel multi-node setup** | Set up 3-5 nodes at once when a batch of servers becomes idle. | Low | Each setup is already async. Just allow multiple concurrent setup tasks. Limit concurrency to avoid overwhelming the gateway. |
| **Setup profiles / presets** | Different model/GPU combinations as named profiles ("h100-72b", "t4-3b") instead of always auto-detecting. | Low | The existing `start-vllm.sh` already auto-detects. Presets would override env vars (`VLLM_MODEL`, `VLLM_TENSOR_PARALLEL`). YAGNI until auto-detection proves insufficient. |
| **Setup history** | Persistent record of past setup/teardown operations for audit trail. | Medium | Requires persistence (etcd keys, SQLite, or file). In-memory only for v1.2. |
| **Container image caching** | Skip `podman build` if the image already exists on the target host. | Low | `podman image exists auto-vllm && echo "cached" || podman build ...`. Saves 1-3 minutes per setup. |

## Anti-Features

Features to deliberately NOT build for v1.2.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| **Full orchestration / auto-scaling** | PROJECT.md explicitly defers this. v1.2 is operator-triggered setup/teardown, not automatic. Auto-scaling requires QUADS API integration, capacity planning, scheduling logic. Completely different system. | Operator clicks "setup" or "teardown" in dashboard. Auto-scaling is a future milestone. |
| **NVIDIA driver management / version selection** | The setup.sh pins a specific driver version (580.126.09). Managing multiple driver versions, upgrades, and compatibility matrices is an ops nightmare. | Pin the driver version in setup.sh. Update the script when a new driver is validated. |
| **Model download / management** | Models live on NFS (`/srv/hf-cache`). The gateway should not download or manage models. | NFS mount is handled by setup.sh. Model selection is handled by `start-vllm.sh` auto-detection. |
| **WebSocket-based live streaming of setup output** | Adding WebSocket support to the dashboard for real-time log streaming adds frontend and backend complexity. The existing polling pattern works fine. | Poll `GET /admin/nodes/setup/{task_id}/log` on the same interval as dashboard auto-refresh. Good enough for an ops tool. |
| **SSH key management** | Generating, distributing, or rotating SSH keys is an operational concern outside the gateway. | Operators ensure `~/.ssh/` has the right keys before using setup. Document the requirement. |
| **Persistent setup state (database)** | Adding a database dependency for setup state tracking is overkill. Setup state is ephemeral -- if the gateway restarts, operators re-trigger setup. | In-memory dict of active/recent setup tasks. Cleared on restart. |
| **Agent on target hosts** | Installing a daemon/agent on each GPU server defeats the purpose of SSH-based agentless provisioning. | SSH for everything. The target hosts need only SSHD (already running on all QUADS servers). |

## Feature Dependencies

```
SSH Connection
  --> Pre-flight Validation (quick SSH commands)
  --> Run setup.sh (long SSH command)
      --> Container Build (SSH: podman build)
          --> Container Start (SSH: podman run)
              --> Health Poll (HTTP from gateway to node:8000/health)
                  --> etcd Registration (gateway writes to etcd)
                      --> Node appears in registry (etcd watcher picks it up)

Teardown:
  Connection Draining (registry.drain())
    --> Container Stop (SSH: podman stop)
        --> etcd Deregistration (gateway deletes etcd key)
            --> Node removed from registry (etcd watcher picks it up)

Setup State Machine:
  PENDING -> CONNECTING -> VALIDATING -> SETUP_RUNNING -> BUILDING
    -> STARTING -> HEALTH_CHECK -> REGISTERING -> COMPLETE
  (any step) -> FAILED

Admin API (POST /admin/nodes/setup) -> triggers setup pipeline (async)
Admin API (GET /admin/nodes/setup/{id}) -> returns setup state + progress
Admin API (DELETE /admin/nodes/{id}) -> triggers teardown pipeline
Dashboard -> polls admin API for status display
```

## Failure Modes (GPU Server Specific)

These are the things that go wrong during SSH-based GPU server provisioning. Each maps to a setup step.

| Step | Failure Mode | Likelihood | Detection | Recovery |
|------|-------------|------------|-----------|----------|
| SSH connect | Host unreachable, key rejected, timeout | Medium | asyncssh raises `ConnectionRefused`, `PermissionDenied`, `TimeoutError` | Pre-flight check. Report to operator. |
| dnf update | Network issues, repo unavailable, disk full | Low | Non-zero exit code from SSH command | Retry. Check disk space in pre-flight. |
| NVIDIA driver install | Kernel headers mismatch, Secure Boot enabled, nouveau still loaded, download fails | **High** | Non-zero exit code, specific error strings in stderr | This is the most fragile step. Kernel mismatch requires exact `kernel-devel-$(uname -r)` which may not be in repos for older kernels. Secure Boot must be disabled in BIOS (cannot fix via SSH). nouveau blacklist + dracut may require reboot. |
| nvidia-ctk CDI generate | Driver not loaded, nvidia-smi fails | Medium | Non-zero exit code | Usually means driver install failed silently. Check `nvidia-smi` output. |
| NFS mount | NFS server unreachable, export not available, stale mount | Medium | `mount` command fails or hangs | Check NFS server accessibility in pre-flight. Use mount timeout. |
| podman build | Network issues pulling base image, disk full | Low-Medium | Non-zero exit code | Retry. First pull of `vllm/vllm-openai:v0.8.5` is ~15GB. Ensure disk space. |
| podman run | GPU device not available, port 8000 already in use, OOM | Medium | Container exits immediately, `podman ps` shows no running container | Check CDI config, check port availability, check GPU memory. |
| Health poll timeout | vLLM fails to load model (OOM, model not on NFS, corrupted weights) | Medium | `/health` never returns 200 within timeout | Check container logs (`podman logs auto-vllm`). Model too large for available GPU memory is the most common cause. |
| etcd registration | etcd unreachable | Low | Exception from etcd3gw | Retry. If etcd is down, the entire gateway has bigger problems. |

## MVP Recommendation for v1.2

**Must have (ship-blocking):**
1. SSH connection via asyncssh with key auth
2. Remote execution of setup.sh (upload + run)
3. Remote container build + start
4. Health poll from gateway until node is ready
5. etcd registration (using existing serializer)
6. Setup state machine (in-memory, per-task)
7. `POST /admin/nodes/setup` -- trigger setup, return task ID
8. `GET /admin/nodes/setup/{task_id}` -- poll setup status
9. `DELETE /admin/nodes/{id}` -- teardown (stop container + deregister)
10. Error capture and reporting per step
11. Dashboard buttons for setup/teardown

**Should have (high value, low risk):**
1. Pre-flight validation (SSH reachable, GPU present, disk space)
2. Connection draining before teardown
3. Dashboard step-by-step progress display
4. Setup log capture (last N lines of output)

**Defer:**
- Parallel multi-node setup: each setup is already async, just run multiple
- Retry individual steps: add when operators actually ask for it
- Setup history/audit: in-memory is fine for now
- Container image caching: minor optimization, add when setup time is a complaint

## Sources

- [AsyncSSH documentation](https://asyncssh.readthedocs.io/) -- async SSH client for Python, line-by-line output streaming
- [NVIDIA Container Toolkit troubleshooting](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/troubleshooting.html) -- GPU access failures in containers
- Existing codebase: `auto-vllm-container/setup.sh`, `start-vllm.sh`, `Containerfile` -- the actual provisioning scripts this feature automates
