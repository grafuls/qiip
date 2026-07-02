# Phase 12: Provisioning Robustness - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-02
**Phase:** 12-provisioning-robustness
**Areas discussed:** Pre-flight checks, State machine, Health checker coordination

---

## Pre-flight Checks

### How should pre-flight checks run?

| Option | Description | Selected |
|--------|-------------|----------|
| All over SSH | SSH in, run nvidia-smi, df, etc. Simple — one connection. | |
| Ping/port first, then SSH | Network probe (TCP connect to SSH port) before full SSH session. | ✓ |
| You decide | Claude picks the laziest approach | |

**User's choice:** Ping/port first, then SSH

### Minimum disk space threshold?

| Option | Description | Selected |
|--------|-------------|----------|
| 10 GB | Covers NVIDIA driver install + container image build | |
| 20 GB | More headroom — covers driver + container image + some model cache staging | ✓ |
| 50 GB | Conservative — includes room for model downloads | |
| You decide | Claude picks based on what setup.sh downloads | |

**User's choice:** 20 GB

### Failure collection strategy?

| Option | Description | Selected |
|--------|-------------|----------|
| Collect all, then abort | Run all checks, report everything wrong at once | ✓ |
| Fail fast on first | Stop at the first failure | |
| You decide | Claude picks based on operator workflows | |

**User's choice:** Collect all, then abort

### Separate method or internal only?

| Option | Description | Selected |
|--------|-------------|----------|
| Separate method | provisioner.preflight(hostname) — operators can dry-run | ✓ |
| Internal only | Pre-flight runs inside provision() automatically | |
| You decide | Claude picks the laziest option | |

**User's choice:** Separate method

---

## State Machine

### Where should provisioning state live?

| Option | Description | Selected |
|--------|-------------|----------|
| In-memory only | Lost on restart. Simplest. | |
| etcd-backed | Survives restarts, queryable externally | ✓ |
| You decide | Claude picks based on downstream needs | |

**User's choice:** etcd-backed

### State granularity?

| Option | Description | Selected |
|--------|-------------|----------|
| Coarse (5 states) | PENDING → PREFLIGHT → SETUP → STARTING → COMPLETE/FAILED | |
| Fine-grained (per step) | Maps 1:1 to step markers, 12+ states | ✓ |
| You decide | Claude picks based on dashboard needs | |

**User's choice:** Fine-grained (per step)

### Separate model or extend Node?

| Option | Description | Selected |
|--------|-------------|----------|
| Separate model | ProvisioningState(BaseModel), separate etcd prefix | ✓ |
| Extend Node | Add provisioning fields to Node model | |
| You decide | Claude picks based on SRP | |

**User's choice:** Separate model

### Error field for FAILED state?

| Option | Description | Selected |
|--------|-------------|----------|
| Step name + error msg | failed_step + error message string | ✓ |
| Step name only | Just the step name, check logs for details | |
| You decide | Claude picks based on admin API needs | |

**User's choice:** Step name + error msg

---

## Health Checker Coordination

### How should health checker know to skip provisioning nodes?

| Option | Description | Selected |
|--------|-------------|----------|
| Add PROVISIONING status | New NodeStatus.PROVISIONING enum value | ✓ |
| Separate exclusion list | Health checker maintains skip set | |
| You decide | Claude picks based on existing code | |

**User's choice:** Add PROVISIONING status

### When to transition PROVISIONING → HEALTHY?

| Option | Description | Selected |
|--------|-------------|----------|
| After health poll succeeds | Node stays PROVISIONING until 200 OK from vLLM | ✓ |
| After etcd registration | Slightly later, ensures etcd write succeeded | |
| You decide | Claude picks based on provisioner flow | |

**User's choice:** After health poll succeeds

### On failure — stay or remove?

| Option | Description | Selected |
|--------|-------------|----------|
| Stay as FAILED | Node visible in etcd with failed status | ✓ |
| Remove on failure | Delete provisioning etcd key on failure | |
| You decide | Claude picks based on operator visibility | |

**User's choice:** Stay as FAILED

---

## Claude's Discretion

None — all decisions made by user.

## Deferred Ideas

None — discussion stayed within phase scope.
