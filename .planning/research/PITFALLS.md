# Domain Pitfalls

**Domain:** SSH-Based Node Provisioning for LLM Inference Gateway
**Researched:** 2026-07-01
**Confidence:** HIGH (verified against codebase architecture, upstream library issues, and production provisioning patterns)

**Scope:** Pitfalls specific to adding SSH-based node setup/teardown to the existing async gateway (v1.2). Prior pitfalls (v1.0 streaming, etcd, load balancing) are in git history.

---

## Critical Pitfalls

Mistakes that cause outages, data loss, or require architectural rework.

### Pitfall 1: Blocking the Event Loop with SSH Operations

**What goes wrong:** SSH operations (connecting, running `setup.sh`, polling `/health`, building containers) take minutes. Running them on the FastAPI event loop freezes all proxy traffic -- health checks stop, streaming responses stall, the dashboard hangs. A single `POST /admin/nodes/setup` call takes down the entire gateway for the duration of the provisioning.

**Why it happens:** The gateway is a single-threaded async application. The existing codebase already uses `threading.Thread` for the etcd watcher and health checker (see `main.py` lines 122-146). An SSH library like AsyncSSH is native async, but its long-running commands (NVIDIA driver install: 2-5 minutes, container build: 1-3 minutes) still monopolize the event loop if the result is awaited in the request handler. Paramiko is worse -- it's fully synchronous and will block the loop directly if called from an `async def` handler.

**Consequences:**
- All proxy traffic (chat completions, streaming) blocks for the duration of setup (5-15 minutes).
- Health checker thread continues but the event loop cannot process its results.
- Dashboard auto-refresh polls timeout, making it look like the gateway crashed.
- Liveness probes fail, orchestrators may restart the gateway mid-provisioning.

**Warning signs:**
- `GET /health` latency spikes to seconds during provisioning.
- Streaming requests timeout while a setup is in progress.
- asyncio slow callback warnings in logs (`Executing <Task ... took X.XXX seconds>`).

**Prevention:**
- Use AsyncSSH (native asyncio) and run provisioning as a background `asyncio.Task`, not in the request handler. The `POST /admin/nodes/setup` endpoint should return 202 Accepted immediately with a task ID, then the provisioning runs asynchronously.
- Set `connect_timeout` on AsyncSSH connections (10-15 seconds) to fail fast on unreachable hosts.
- For CPU-bound parts of SSH output parsing, use `asyncio.to_thread()`.
- Do NOT use Paramiko -- it's synchronous and the open GitHub issue (#2363) confirms no async support is planned. AsyncSSH is the only production-grade async SSH library for Python.

**Detection:** Enable asyncio debug mode in development (`PYTHONASYNCIODEBUG=1`). Any callback taking >100ms is logged. Monitor `/health` response time during provisioning operations.

**Phase:** Architecture must be decided before any SSH code is written. Background task pattern is non-negotiable.

---

### Pitfall 2: Partially Provisioned Servers After Setup Script Failure

**What goes wrong:** `setup.sh` fails at step 5 of 8 (e.g., NVIDIA driver install fails). The server now has packages installed, nouveau blacklisted, initramfs rebuilt -- but no working GPU driver, no CDI config, no NFS mount, no container. The server is in a state that neither the old setup script nor a re-run can cleanly handle.

**Why it happens:** Looking at the actual `setup.sh`:
1. `curl ... | sudo tee ...` -- NVIDIA repo (can fail: DNS, network)
2. `sudo dnf -y update` -- system update (can fail: disk space, broken deps)
3. `sudo dnf -y install ...` -- packages including `kernel-devel-$(uname -r)` (can fail: kernel mismatch after update in step 2)
4. `echo 'blacklist nouveau' | sudo tee ...` -- blacklist (unlikely to fail)
5. `sudo dracut --force` -- initramfs rebuild (can fail: disk space)
6. `sudo modprobe -r nouveau` -- remove module (can fail: module in use)
7. NVIDIA driver `.run` installer (can fail: kernel mismatch, existing driver, gcc missing)
8. `nvidia-ctk cdi generate` (can fail: driver not loaded)
9. NFS mount (can fail: network, server down, path doesn't exist)
10. iptables rules (can fail: iptables not installed, rules conflict)

The script has no `set -e`, no error checking, no idempotency guards. Every `dnf install` is NOT idempotent if packages were partially installed. The NVIDIA `.run` installer will refuse to run if a previous partial install exists. `dracut --force` after a `dnf update` that changed the kernel but before reboot creates a mismatch.

**Consequences:**
- Server is unusable for inference AND unusable for its original purpose.
- Manual SSH into the server to diagnose and clean up.
- Re-running setup.sh makes things worse (double-installs, conflicting drivers).
- The gateway reports the setup "failed" but has no idea what state the server is in.

**Prevention:**
- Make each step idempotent: check if the package is already installed before installing, check if nouveau is already blacklisted before writing the conf, check if the NVIDIA driver is already loaded before running the installer.
- Add `set -euo pipefail` to the script (it's already in `start-vllm.sh` but missing from `setup.sh`).
- Track setup progress in a state file on the remote host (e.g., `/var/lib/vllm-setup/state`). Each step writes its completion. On re-run, skip completed steps.
- Implement a corresponding `cleanup.sh` that reverses each step. On setup failure, offer a "retry" (re-run from failed step) or "abort" (run cleanup) option.
- The gateway must store per-host provisioning state: `PENDING`, `SETUP_IN_PROGRESS`, `SETUP_FAILED(step=N)`, `READY`, `TEARDOWN_IN_PROGRESS`, `TORN_DOWN`.
- Validate prerequisites before starting: check SSH connectivity, check disk space, check kernel version, check if GPU hardware is present (`lspci | grep NVIDIA`).

**Detection:** Each step in the script should emit structured output (e.g., `STEP:nvidia-driver:OK` or `STEP:nvidia-driver:FAIL:exit_code=1`) that the gateway parses to track progress.

**Phase:** Setup script refactoring should be the FIRST phase of v1.2. Building SSH integration on top of the current non-idempotent `setup.sh` is building on sand.

---

### Pitfall 3: Race Condition Between Provisioning, Health Checker, and etcd Watcher

**What goes wrong:** Setup completes, the node is registered in etcd, the etcd watcher picks it up and adds it to the `NodeRegistry`. The health checker immediately probes it -- but vLLM is still loading the model (30-120 seconds for large models). The health checker marks it UNHEALTHY after 3 failed probes (90 seconds at 30-second intervals). When vLLM finally starts responding, the circuit breaker may already be tripped.

Worse scenario: teardown is initiated for a node. The gateway sends `podman stop` via SSH, then removes the node from etcd. But between the etcd removal event and the watcher processing it, the health checker is probing the dying node, getting errors, and tripping the circuit breaker for a node that's about to be removed anyway.

**Why it happens:** Three independent systems interact with no coordination:
1. **Provisioning** (new in v1.2): SSH-driven setup that registers the node in etcd at the end.
2. **etcd watcher** (existing, `discovery/watcher.py`): Background thread that updates `NodeRegistry` on etcd changes.
3. **Health checker** (existing, `resilience/health_checker.py`): Background thread that probes all nodes in the registry every 30 seconds.

The health checker (line 74 of `health_checker.py`) iterates `registry.get_all()` on every cycle. There's no concept of "this node is still being provisioned, skip it" or "this node is being torn down, skip it."

**Consequences:**
- Newly provisioned nodes are immediately marked UNHEALTHY and may never recover if the circuit breaker trips.
- Teardown races produce spurious error logs and stale circuit breaker state.
- Operators see confusing dashboard state: node shows as UNHEALTHY right after supposedly successful setup.

**Prevention:**
- Add a `PROVISIONING` status to `NodeStatus` enum. Nodes in `PROVISIONING` state are in the registry (visible on dashboard) but skipped by the health checker and node selector.
- Register the node in etcd with `PROVISIONING` status BEFORE starting setup. Update to `HEALTHY` only after the gateway's own health probe succeeds post-setup. This way the watcher sees the node but the health checker and router ignore it.
- For teardown: mark the node as `DRAINING` (already exists in `NodeStatus`) first, wait for in-flight connections to finish, THEN stop the container and remove from etcd. The existing `registry.drain()` method already supports this.
- Add a startup grace period to the health checker: skip probing any node whose `last_heartbeat` is None (never been probed) for the first N seconds after it appears.

**Detection:** Log provisioning state transitions with timestamps. Alert if a node stays in `PROVISIONING` for more than a configurable maximum (e.g., 20 minutes).

**Phase:** Must be addressed in the same phase as the SSH integration. Cannot be deferred -- the race exists from the moment the first node is provisioned.

---

### Pitfall 4: SSH Disconnection During Long-Running Operations Leaves Orphaned Processes

**What goes wrong:** The NVIDIA driver installation takes 3+ minutes. Mid-install, the SSH connection drops (network hiccup, gateway restart, operator cancels the setup). The `NVIDIA-Linux-x86_64-*.run` installer continues running on the remote host as an orphaned process. When SSH reconnects and tries to re-run setup, the installer is still running, holding locks on kernel modules.

Similarly: `podman build` is running, SSH drops, the build continues consuming resources. The gateway has no idea whether the build succeeded, failed, or is still running.

**Why it happens:**
- SSH channels deliver SIGHUP to the remote process when the connection drops, BUT sudo-invoked processes and processes that have changed their process group may not receive it.
- The `.run` installer spawns subprocesses (compiler, linker, DKMS) that may survive the parent.
- `podman build` runs in its own namespace and is not killed by SSH disconnect.
- AsyncSSH's `conn.run()` timeout only applies to data received from the channel, not to the underlying process on the remote host. If the connection drops, `conn.run()` raises `ConnectionLost` but the remote process keeps running.

**Consequences:**
- Orphaned NVIDIA installer holding kernel module locks, preventing re-run.
- Orphaned `podman build` consuming CPU and disk I/O.
- Gateway reports "setup failed" but the setup may actually complete successfully on the remote host, leaving the gateway state out of sync.
- Multiple orphaned processes from repeated setup attempts.

**Prevention:**
- Run long commands inside `tmux` or `screen` on the remote host. The gateway creates a named session (`tmux new-session -d -s vllm-setup`), runs the command inside it, and monitors the session. On SSH reconnect, the gateway re-attaches to the same session to check status.
- Alternative (simpler): use `nohup command > /var/log/vllm-setup.log 2>&1 &` with a PID file. On SSH reconnect, check if the PID is still running and tail the log.
- Write a wrapper script on the remote host that:
  1. Writes its PID to a known location.
  2. Runs the setup steps.
  3. Writes success/failure status to a state file.
  4. The gateway polls the state file via SSH, not the command's stdout.
- Before starting setup, check for orphaned processes from previous attempts: `pgrep -f 'NVIDIA-Linux'`, `podman ps --filter name=vllm`.
- Implement a "cancel setup" action that SSHs in and kills known setup processes.

**Detection:** Before any setup operation, run a pre-flight check: `pgrep -f 'NVIDIA|podman build|dracut'` to detect orphans from a previous run.

**Phase:** Core SSH integration. The nohup+PID file pattern is simpler than tmux and sufficient for non-interactive scripts. Use it.

---

## Moderate Pitfalls

Mistakes that cause significant debugging time or operational headaches.

### Pitfall 5: Not Cleaning Up on Teardown Failure

**What goes wrong:** Teardown is supposed to: stop the vLLM container, remove it, deregister from etcd. The container stop succeeds, but the etcd deregistration fails (etcd is down). Now the container is stopped but the node is still in the registry. The health checker marks it UNHEALTHY, and the dashboard shows a dead node that cannot be set up (container remnants) or torn down (already partially torn down).

Reverse scenario: etcd deregistration succeeds but `podman stop` fails (container is stuck, OOM, GPU process hung). The node disappears from the registry but the container keeps running, consuming GPU resources. The server appears "idle" to QUADS but is still running inference workloads.

**Why it happens:** Teardown is treated as an atomic operation when it's actually a multi-step process that can fail at any point. Each step has different failure modes and different rollback actions.

**Consequences:**
- Ghost nodes in etcd that no longer correspond to running containers.
- Zombie containers consuming GPU memory that nobody knows about.
- The server is "lost" -- neither the gateway nor QUADS tracks it correctly.
- Manual intervention required to reconcile state.

**Prevention:**
- Define teardown as a sequence with explicit error handling per step:
  1. Mark node as DRAINING in registry (prevents new traffic).
  2. Wait for in-flight connections to finish (or timeout).
  3. Stop container via SSH (`podman stop --time 30 vllm`).
  4. Remove container via SSH (`podman rm vllm`).
  5. Deregister from etcd.
  6. Mark teardown complete.
- If step 3 fails, force-kill: `podman kill vllm`, then `podman rm -f vllm`.
- If step 5 fails, retry with backoff. If etcd is truly down, log the orphaned registration and add a reconciliation sweep that cleans up stale etcd entries on the next successful etcd connection.
- Always deregister from etcd LAST (after container is confirmed stopped). This way, if teardown fails, the health checker will detect the dead node and mark it UNHEALTHY, which is the correct state.
- Store teardown state: `TEARDOWN_IN_PROGRESS`, `TEARDOWN_FAILED(step=N)`, `TORN_DOWN`.

**Detection:** Periodic reconciliation: SSH into hosts that are registered in etcd and verify the container is actually running. Flag mismatches.

**Phase:** Teardown implementation. Define the state machine before writing the code.

---

### Pitfall 6: SSH Key Exposure Through Logs, Error Messages, or Configuration

**What goes wrong:** The SSH private key path, passphrase, or key material appears in:
- Structured logs (structlog renders all bound variables by default).
- FastAPI error responses (unhandled exceptions include local variables).
- pydantic-settings `.env` file that gets committed to git.
- Dashboard UI error messages shown to operators.

**Why it happens:** The gateway uses structlog with context binding. If SSH connection parameters are bound to the logger context (a natural pattern: `log.bind(host=host, key_path=key_path)`), the key path appears in every subsequent log line. Worse, if the key content is ever loaded into a variable and an unhandled exception occurs, FastAPI's default error handler may include it in the traceback.

The existing `Settings` class uses `env_file=".env"`. Adding SSH key paths or passphrases to `.env` creates a risk of committing secrets to git.

**Consequences:**
- SSH key paths leaked in logs visible to anyone with log access.
- Key material in crash dumps or error tracking systems.
- `.env` committed to git exposes credentials to anyone with repo access.

**Prevention:**
- Never bind key material or passphrases to structlog context. Bind only the key fingerprint or a key identifier.
- Use Pydantic's `SecretStr` type for any SSH-related secrets in settings. `SecretStr` redacts the value in `repr()` and logging.
- Add `.env` to `.gitignore` (verify it's already there).
- Configure a custom FastAPI exception handler that strips sensitive variables from error responses.
- Store SSH key paths in settings, not key contents. Load keys only when establishing a connection, never cache key material in app state.
- The PROJECT.md already specifies "Pre-configured SSH keys (operator ensures ~/.ssh access)" -- lean into this. The gateway should read `~/.ssh/id_ed25519` by default, configurable via `INFERENCE_PROXY_SSH__KEY_PATH`. No key material in env vars.

**Detection:** Grep logs for patterns matching key paths or key material. Add a CI check that `.env` is not tracked in git.

**Phase:** Settings and configuration phase, before any SSH code. Get the security model right first.

---

### Pitfall 7: NFS Mount Failure Hangs Setup Indefinitely

**What goes wrong:** `setup.sh` runs `sudo mount -t nfs -o vers=3 rdu-storage02.scalelab.redhat.com:/mnt/SATA/scratch/grafuls/hf-cache /srv/hf-cache`. If the NFS server is down, unreachable, or the export path doesn't exist, this command hangs indefinitely with the default `hard` mount option. The SSH channel stays open, the gateway thinks setup is still in progress, and the remote host is stuck in a mount syscall.

**Why it happens:** NFS `hard` mount (the default) retries indefinitely. The `mount` command will not return until the NFS server responds or the process is killed. This is by design for production NFS mounts (prevent data loss), but it's catastrophic for automated provisioning where you need fast failure.

Looking at the actual `setup.sh` mount command: `sudo mount -t nfs -o vers=3 ...` -- no `soft`, no `timeo`, no `retrans` options. This is a hard mount with default timeouts.

**Consequences:**
- Setup hangs indefinitely on NFS failure.
- The SSH command timeout (if set) kills the SSH channel but the mount process on the remote host continues retrying.
- The server is stuck in an uninterruptible mount state.
- Cannot SSH back in to fix it because `df` commands will also hang (NFS state is kernel-level).

**Prevention:**
- Use `soft` mount with explicit timeouts for provisioning: `sudo mount -t nfs -o vers=3,soft,timeo=100,retrans=3 ...`. This fails after ~30 seconds instead of hanging forever.
- Better: check NFS server reachability BEFORE attempting the mount: `timeout 10 nc -zv rdu-storage02.scalelab.redhat.com 2049`.
- Add a prerequisite check step that validates NFS server availability before the full setup begins.
- If using `hard` mount for production reliability, do the mount in a subshell with `timeout`: `timeout 60 sudo mount -t nfs ...`.
- After mount, verify it actually works: `timeout 10 ls /srv/hf-cache/` or `timeout 10 stat /srv/hf-cache/`.

**Detection:** SSH command timeout will catch this if set correctly. But the remote host may need manual recovery (`umount -f -l /srv/hf-cache`).

**Phase:** Setup script hardening. Fix this before automating SSH setup.

---

### Pitfall 8: GPU Driver Installation Failure Modes Are Not Recoverable by Re-Run

**What goes wrong:** The NVIDIA `.run` installer fails partway through. Common failure modes:
1. **Kernel header mismatch:** `dnf update` in step 2 installed a new kernel, but the running kernel is still the old one. `kernel-devel-$(uname -r)` installs headers for the old kernel. The driver compiles against old headers, DKMS fails on reboot.
2. **Existing driver conflict:** A previous partial install left NVIDIA kernel modules loaded. The installer cannot replace loaded modules.
3. **GCC version mismatch:** The kernel was compiled with a different GCC than what's installed. DKMS build fails.
4. **Secure Boot:** The server has Secure Boot enabled. Unsigned NVIDIA modules fail to load.

After any of these failures, re-running setup.sh compounds the problem because:
- `dnf update` may change the kernel again.
- The partial NVIDIA install leaves state in `/usr/lib/modules/`, `/usr/src/`, and `/var/lib/dkms/`.
- `dracut --force` may have already been run, so the initramfs includes the nouveau blacklist but no NVIDIA driver.

**Consequences:**
- Server boots without GPU drivers. `nvidia-smi` fails. CDI generation fails. Container cannot access GPUs.
- `start-vllm.sh` calls `nvidia-smi` in `detect_gpu_info()` and will fail immediately.
- Manual recovery requires SSH, driver removal, reboot, clean reinstall.

**Prevention:**
- Check prerequisites before driver install: `uname -r` matches available kernel-devel, GCC is correct version, no existing NVIDIA modules loaded (`lsmod | grep nvidia`).
- If kernel was updated by `dnf update`, REBOOT before installing the driver. This is a hard requirement that the current `setup.sh` ignores.
- Use `--uninstall` before reinstalling: `sudo sh NVIDIA-Linux-x86_64-*.run --uninstall` if a previous installation exists.
- Check for Secure Boot: `mokutil --sb-state`. If enabled, either disable it or sign the modules (complex).
- Split driver installation into a separate step with its own verification: after install, verify `nvidia-smi` works. If not, the step failed regardless of exit code.
- Consider using `dnf install nvidia-driver` from the NVIDIA repo instead of the `.run` installer. Package manager handles kernel updates and DKMS automatically.

**Detection:** After driver install, always run `nvidia-smi` and check exit code. After CDI generation, verify `/etc/cdi/nvidia.yaml` exists and is non-empty.

**Phase:** Setup script hardening. The reboot-after-kernel-update requirement means setup may need to be a multi-phase process: phase 1 (packages + kernel update + reboot), phase 2 (driver install + container setup).

---

### Pitfall 9: Concurrent Setup/Teardown Operations on the Same Host

**What goes wrong:** An operator clicks "Setup" for host-01, it starts running. The operator doesn't see progress (dashboard lag), clicks "Setup" again. Now two SSH sessions are running setup.sh on the same host simultaneously. Both try to install packages, blacklist modules, install drivers -- interleaving operations that were never designed to be concurrent.

Or: operator starts setup, it's slow, they click "Teardown" to cancel. Now setup and teardown are racing on the same host.

**Why it happens:** The `POST /admin/nodes/setup` endpoint has no lock or deduplication. If provisioning runs as a background task (as recommended in Pitfall 1), the endpoint will happily accept multiple requests for the same host.

**Consequences:**
- Corrupted package state from concurrent `dnf` operations.
- Driver install race: two `.run` installers fighting over the same files.
- One operation succeeds, the other fails with confusing errors.
- Host ends up in an unknown state.

**Prevention:**
- Maintain a per-host lock in the gateway. Before starting setup or teardown, check if an operation is already in progress for that host. Return 409 Conflict if so.
- Use an in-memory `dict[str, asyncio.Lock]` keyed by hostname. This is sufficient because the gateway is a single process.
- Store operation state per host: `{host: {operation: "setup", started_at: datetime, task_id: str}}`. Expose this state on the dashboard and admin API.
- The lock should cover the entire operation lifecycle, not just the SSH command. It should be released only when the operation completes (success or failure).
- Consider a remote-side lock too: write a lock file on the host (e.g., `/var/lock/vllm-setup.lock`) at the start of setup.sh, remove on completion. Check for this lock before starting.

**Detection:** Log all operation start/complete/fail events with host identifier. Alert on concurrent operations for the same host.

**Phase:** Must be in the first implementation of the setup/teardown endpoints. Not a future enhancement.

---

## Minor Pitfalls

Issues that cause debugging annoyance or operational friction.

### Pitfall 10: Container Name Collisions on Setup Re-Run

**What goes wrong:** Setup runs `podman build` and `podman run` with a container name (e.g., `vllm`). If a previous setup left a stopped container with the same name, `podman run --name vllm` fails with "container name already in use." If a previous setup left a running container, same error.

**Prevention:**
- Before `podman run`, always: `podman stop vllm 2>/dev/null; podman rm vllm 2>/dev/null` (ignore errors if container doesn't exist).
- Use `podman run --replace --name vllm` (Podman 4.0+) which replaces any existing container with the same name.
- Alternatively, use unique container names per setup attempt (e.g., `vllm-$(date +%s)`) but then you need to track which container name is active.

**Phase:** Setup script. Simple fix, do it when hardening the script.

---

### Pitfall 11: SSH Known Hosts Verification Blocks Automated Connections

**What goes wrong:** AsyncSSH (or any SSH library) prompts for host key verification on first connection. In an automated context, this blocks indefinitely or raises `HostKeyNotVerifiable`. Lab servers get reinstalled frequently, changing their host keys, causing "host key changed" errors that block all subsequent connections.

**Prevention:**
- For internal lab infrastructure, use `known_hosts=None` in AsyncSSH to disable host key verification. This is acceptable for internal networks (stated constraint: "Internal network only, no external-facing endpoints in v1").
- Do NOT use `known_hosts=None` if the network is untrusted. For internal lab use, the risk is acceptable and the alternative (maintaining a known_hosts file for frequently-reinstalled lab servers) is operationally painful.
- Document this as a deliberate security trade-off with a comment: `# ponytail: known_hosts=None acceptable for internal lab network. Add verification if network boundary changes.`

**Phase:** Initial SSH integration.

---

### Pitfall 12: Setup Logs Lost When SSH Session Ends or Gateway Restarts

**What goes wrong:** Setup script output is streamed over the SSH channel to the gateway. The gateway stores it in memory to show on the dashboard. If the gateway restarts during setup, all setup logs are lost. The operator has no idea what step the setup reached or why it failed.

**Prevention:**
- Redirect setup script output to a log file on the remote host: `setup.sh > /var/log/vllm-setup.log 2>&1`. The gateway can tail this file via SSH at any time.
- Store setup status and progress in a structured state file on the remote host (see Pitfall 2).
- On the gateway side, persist operation history to a simple JSON file or SQLite if needed. For v1.2, in-memory with log file on remote host is sufficient.
- The gateway should be able to "reconnect" to an in-progress setup by checking the remote state file and log.

**Phase:** Setup implementation. Log to remote file from day one.

---

### Pitfall 13: `start-vllm.sh` Uses `exec` Which Prevents Status Reporting

**What goes wrong:** `start-vllm.sh` line 123 uses `exec vllm serve ...`, which replaces the shell process with the vLLM process. This means:
- The SSH channel stays open as long as vLLM runs (could be days/weeks).
- No exit code is returned until vLLM exits.
- The gateway cannot get a "started successfully" signal because the command never "finishes."

**Why it happens:** `exec` is correct for production (PID 1, signal handling) but wrong for automated provisioning where you need to: start the server, verify it's healthy, then disconnect SSH.

**Prevention:**
- Run vLLM via `podman run -d` (detached mode) instead of exec'ing into it.
- After `podman run -d`, poll `http://host:8000/health` from the gateway (not via SSH) until it returns 200 or a timeout is reached.
- The container's own entry point can still use `exec vllm serve ...` -- the detached mode means SSH doesn't need to stay connected.
- Do NOT try to parse vLLM's stdout for "ready" messages. Use the health endpoint.

**Phase:** Container launch approach. Must be decided before building the SSH integration.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| SSH library choice | Event loop blocking (#1) | Use AsyncSSH, return 202 + background task |
| Setup script hardening | Partial state (#2), NFS hang (#7), driver failure (#8) | Idempotent steps, `set -e`, timeout on NFS, prerequisite checks |
| Provisioning state machine | Health checker race (#3), concurrent ops (#9) | Add PROVISIONING status, per-host locks, state tracking |
| SSH connection management | Disconnect orphans (#4), known hosts (#11) | nohup + PID file, known_hosts=None for lab |
| Teardown implementation | Cleanup failure (#5), container collisions (#10) | Multi-step with per-step error handling, force-remove |
| Security | Key exposure (#6) | SecretStr, no keys in logs, key path not content |
| Container launch | exec blocks SSH (#13) | podman run -d, poll /health from gateway |
| Observability | Lost logs (#12) | Log to remote file, structured state file |

---

## Sources

- [AsyncSSH documentation](https://asyncssh.readthedocs.io/en/latest/) -- async SSH library for Python
- [AsyncSSH timeout issue #626](https://github.com/ronf/asyncssh/issues/626) -- `conn.run()` timeout does not always apply
- [AsyncSSH connection lost issue #220](https://github.com/ronf/asyncssh/issues/220) -- `asyncio.run` causes ConnectionLost
- [Paramiko async support issue #2363](https://github.com/paramiko/paramiko/issues/2363) -- no async support planned
- [Podman zombie processes issue #19909](https://github.com/containers/podman/issues/19909) -- zombie containers with `podman system service`
- [Podman container cleanup docs](https://docs.podman.io/en/v4.4/markdown/podman-container-cleanup.1.html) -- cleanup after daemon-mode exit
- [Terraform remote-exec provisioner pitfalls](https://spacelift.io/blog/terraform-remote-exec) -- idempotency and partial state
- [SSH provisioning corruption on interruption](https://discuss.hashicorp.com/t/provisioning-terraform-via-ssh-can-result-in-corrupted-files-if-there-is-an-interruption-backup-not-working/8060) -- file corruption on SSH kill
- [NFS hard vs soft mounts](https://access.redhat.com/solutions/28211) -- mount hangs with hard option
- [NFS stale handle auto-remount](https://techresolve.blog/2026/03/02/monitor-nfs-mount-stale-handles-and-auto-remount/) -- detection and recovery
- [Python asyncio event loop blocking](https://docs.python.org/3/library/asyncio-dev.html) -- debug mode for slow callbacks
- [SSH key management best practices](https://www.jumpserver.com/blog/ssh-key-management-best-practices) -- enterprise key security
- [NVIDIA driver troubleshooting](https://forums.developer.nvidia.com/t/nvidia-smi-has-failed-because-it-couldnt-communicate-with-the-nvidia-driver/197141) -- driver communication failure after updates
