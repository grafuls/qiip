# Phase 12: Provisioning Robustness - Context

**Gathered:** 2026-07-02
**Status:** Ready for planning

<domain>
## Phase Boundary

Setup operations validate preconditions, report step-by-step progress, and coordinate with the health checker. Pre-flight checks verify SSH reachability, GPU presence, and disk space before committing to setup. A fine-grained state machine tracks each provisioning step in etcd. A new PROVISIONING node status prevents the health checker from marking nodes unhealthy during setup. No admin API (Phase 13), no dashboard UI (Phase 14).

</domain>

<decisions>
## Implementation Decisions

### Pre-flight Checks
- **D-01:** Two-stage validation: TCP connect to SSH port first (fast network probe catches unreachable hosts without key exchange overhead), then SSH in to run diagnostic commands (nvidia-smi, df).
- **D-02:** Minimum 20 GB free disk space required before starting setup.
- **D-03:** Collect all pre-flight failures before aborting — report everything wrong at once so operators fix all issues in one pass instead of fix-retry-fix-retry.
- **D-04:** Pre-flight is a separate public method `provisioner.preflight(hostname)` that operators can call independently for dry-run validation. `provision()` also calls it internally before setup.

### State Machine
- **D-05:** Provisioning state is etcd-backed. Written to a separate etcd key prefix (e.g., `/provisioning/`). Survives gateway restarts, queryable by admin API (Phase 13) and dashboard (Phase 14).
- **D-06:** Fine-grained states mapping 1:1 to step markers: PENDING → PREFLIGHT → each of 6 setup steps (nvidia_repo, system_update, nvidia_driver, nvidia_cdi, nfs_mount, firewall) → STARTING_VLLM → HEALTH_POLL → REGISTERING → COMPLETE/FAILED.
- **D-07:** Separate `ProvisioningState(BaseModel)` Pydantic model in the provisioning package. Not on the Node model — Node is frozen and shared across routing/health/proxy. Separate etcd key prefix keeps concerns clean.
- **D-08:** FAILED state includes both `failed_step` (step name) and `error` (message string). Operators see what and why without checking logs.

### Health Checker Coordination
- **D-09:** Add `NodeStatus.PROVISIONING` to the enum. Register node in etcd with PROVISIONING status before setup starts. Health checker skips nodes with this status.
- **D-10:** Node transitions from PROVISIONING to HEALTHY after `_poll_health` succeeds (200 OK from vLLM). Clean handoff — health checker takes over from there.
- **D-11:** On provisioning failure, node stays in etcd with a FAILED-equivalent status (visible to dashboard). Not removed — operators need to see what failed and re-trigger.

### Claude's Discretion
- None — all decisions made by user.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Provisioning Code (Phase 11 output — what gets extended)
- `inference_proxy/provisioning/provisioner.py` — NodeProvisioner with provision(), _run_setup(), _run_start_vllm(), _poll_health(), _register_node()
- `inference_proxy/provisioning/ssh_client.py` — SSHClient wrapper (sole asyncssh consumer), SSHConnectionError, RemoteCommandError
- `inference_proxy/config/settings.py` — SSHSettings, ProvisioningSettings sub-models on root Settings

### Health Checker (integration point for PROV-07)
- `inference_proxy/resilience/health_checker.py` — Probes all nodes, marks UNHEALTHY after consecutive failures. Must skip PROVISIONING nodes.
- `inference_proxy/models/node.py` — NodeStatus enum (add PROVISIONING), Node model (frozen)

### etcd Integration
- `inference_proxy/discovery/etcd_client.py` — EtcdClient with get_prefix(), watch_prefix(), put()
- `inference_proxy/discovery/serializer.py` — node_to_etcd() serialization

### Scripts (what pre-flight validates readiness for)
- `auto-vllm-container/setup.sh` — Hardened setup with [STEP:name:STATUS] markers, 6 step names
- `auto-vllm-container/start-vllm.sh` — Host-side launcher

### Project Context
- `.planning/ROADMAP.md` — Phase 12 success criteria and requirements mapping
- `.planning/REQUIREMENTS.md` — PROV-05, PROV-06, PROV-07 requirement definitions
- `.planning/phases/11-ssh-provisioning/11-CONTEXT.md` — Phase 11 decisions (SSH config, provisioner design, health poll)
- `.planning/phases/10-script-hardening/10-CONTEXT.md` — Phase 10 decisions (step marker format, script structure)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `NodeProvisioner` — existing provisioner to extend with preflight() and state tracking
- `EtcdClient.put()` — already used for node registration, reuse for provisioning state writes
- `STEP_PATTERN` regex in provisioner.py — already parses [STEP:name:STATUS] markers from stdout, state machine updates plug into this existing parsing
- `ProvisioningSettings` — extend with pre-flight thresholds (min_disk_gb)

### Established Patterns
- Package-per-domain: provisioning state model goes in `provisioning/` package
- DIP: SSHClient wraps asyncssh, EtcdClient wraps etcd3gw — state writes go through EtcdClient
- Frozen Pydantic models for domain objects — ProvisioningState follows this pattern
- `asyncio.to_thread()` for sync etcd3gw calls — state writes use same pattern

### Integration Points
- `NodeStatus` enum — add PROVISIONING variant, health checker must handle it
- `health_checker._probe_node()` — add guard to skip nodes with status=PROVISIONING
- `NodeProvisioner.provision()` — insert preflight() call before _run_setup(), add state tracking around each step
- etcd `/provisioning/` prefix — new key namespace for provisioning state (separate from `/nodes/`)

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

*Phase: 12-Provisioning Robustness*
*Context gathered: 2026-07-02*
