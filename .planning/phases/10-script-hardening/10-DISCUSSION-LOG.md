# Phase 10: Script Hardening - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-01
**Phase:** 10-script-hardening
**Areas discussed:** Script structure, NFS failure policy, Hardcoded values, Output format

---

## Script Structure

### Host launcher vs container entrypoint

| Option | Description | Selected |
|--------|-------------|----------|
| Add run-container.sh | New host-side script handles podman build + run. start-vllm.sh stays as container entrypoint. | |
| Split start-vllm.sh | Rename current to entrypoint.sh. New start-vllm.sh does podman run on host. Keeps familiar name. | ✓ |
| You decide | Let Claude pick. | |

**User's choice:** Split start-vllm.sh

### Build step

| Option | Description | Selected |
|--------|-------------|----------|
| Build + run together | start-vllm.sh does podman build then podman run. One script, one command. | ✓ |
| Separate build | start-vllm.sh only does podman run. Image built separately. | |
| Build if missing | Checks if image exists, builds only if absent. | |

**User's choice:** Build + run together

### Container name

| Option | Description | Selected |
|--------|-------------|----------|
| Fixed: vllm-server | One container per host, always named vllm-server. | |
| Model-based name | e.g., vllm-qwen2.5-72b. Allows multiple models per host in future. | ✓ |
| You decide | Let Claude pick. | |

**User's choice:** Model-based name

### Model selection location

| Option | Description | Selected |
|--------|-------------|----------|
| Move to host side | GPU detection + model selection in start-vllm.sh (host). Pass MODEL as env var to container. | ✓ |
| Keep in container | Entrypoint still detects GPU and picks model. Host uses generic name. | |
| Probe then launch | Host runs nvidia-smi, picks model, passes both. Duplicates some detection logic. | |

**User's choice:** Move to host side

---

## NFS Failure Policy

### Timeout behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Fail the entire setup | No NFS = no model cache = can't serve. Abort with clear error. | ✓ |
| Warn and continue | Complete setup without NFS. Container start fails separately. | |
| Retry then fail | Retry N times with backoff, then abort. | |

**User's choice:** Fail the entire setup

### Timeout value

| Option | Description | Selected |
|--------|-------------|----------|
| 30 seconds | Quick fail for internal network. | ✓ |
| 60 seconds | More patient, covers temporary congestion. | |
| You decide | Let Claude pick based on NFS best practices. | |

**User's choice:** 30 seconds

### Idempotent mount behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Skip if mounted | Check mountpoint -q. If mounted, skip. | ✓ |
| Always remount | Unmount and remount for fresh options. | |
| Verify options | If mounted, check options match. Remount only if wrong. | |

**User's choice:** Skip if mounted

---

## Hardcoded Values

### Configuration approach

| Option | Description | Selected |
|--------|-------------|----------|
| Env vars with defaults | Each value has env var with current values as defaults. | ✓ |
| Keep hardcoded | Purpose-built for lab environment. Edit script if env changes. | |
| Config file | Source a setup.conf file. Separates config from logic. | |

**User's choice:** Env vars with defaults

### NVIDIA driver versioning

| Option | Description | Selected |
|--------|-------------|----------|
| Pin the version | Known-good version as default. Update manually when tested. | ✓ |
| Auto-detect latest | Query NVIDIA API for latest Tesla driver. | |

**User's choice:** Pin the version

### Driver install idempotency

| Option | Description | Selected |
|--------|-------------|----------|
| Skip if installed | Check nvidia-smi success. Skip entire driver install block. | ✓ |
| Always reinstall | Force reinstall every time for determinism. | |

**User's choice:** Skip if installed

---

## Output Format

### Marker format

| Option | Description | Selected |
|--------|-------------|----------|
| Step markers | Structured prefix lines like [STEP:name:STATUS]. | ✓ |
| Plain output | Normal echo/stderr. Gateway checks exit code only. | |
| You decide | Let Claude pick. | |

**User's choice:** Step markers

### Prefix format

| Option | Description | Selected |
|--------|-------------|----------|
| Prefix lines | [STEP:name:STATUS] format. Human-readable, easy to grep. | ✓ |
| JSON lines | One JSON object per event. Machine-parseable. | |
| You decide | Let Claude pick. | |

**User's choice:** Prefix lines

### Step granularity

| Option | Description | Selected |
|--------|-------------|----------|
| One per major block | 6 steps: nvidia_repo, system_update, nvidia_driver, nvidia_cdi, nfs_mount, firewall. | ✓ |
| Coarser grouping | 3 steps: nvidia_setup, nfs_mount, firewall. | |
| You decide | Let Claude pick. | |

**User's choice:** One per major block

---

## Claude's Discretion

None — user made all decisions directly.

## Deferred Ideas

None — discussion stayed within phase scope.
