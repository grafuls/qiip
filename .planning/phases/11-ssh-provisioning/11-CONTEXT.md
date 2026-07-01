# Phase 11: SSH Provisioning - Context

**Gathered:** 2026-07-01
**Status:** Ready for planning

<domain>
## Phase Boundary

Gateway can connect to a remote host over SSH and execute the full provisioning sequence end-to-end: run setup.sh (NVIDIA drivers, NFS, container toolkit), build and start a vLLM container with GPU auto-detection, poll the remote /health endpoint until healthy, then register the node in etcd. This phase delivers the core provisioning logic — no pre-flight checks (Phase 12), no admin API (Phase 13), no dashboard UI (Phase 14).

</domain>

<decisions>
## Implementation Decisions

### SSH Key & Connection Config
- **D-01:** Single SSH key path in settings (`SSH_KEY_PATH`, default `~/.ssh/id_rsa`). All hosts use the same key. Matches "operator ensures ~/.ssh access" from PROJECT.md.
- **D-02:** Single SSH username in settings (`SSH_USERNAME`). All hosts use the same user. Typical for lab servers with shared root access.
- **D-03:** Disable known_hosts verification (`known_hosts=None` in asyncssh). Lab servers get reimaged frequently — host keys change. Internal network only.
- **D-04:** SSH connect timeout configurable via settings, default 10 seconds.

### Remote Output Handling
- **D-05:** Stream stdout line-by-line in real-time via asyncssh. Parse `[STEP:name:STATUS]` markers as they arrive. Enables live progress tracking during setup.sh execution (10+ min).
- **D-06:** Log-only output — all remote output goes to structlog. No in-memory storage of command output. Operators check logs for troubleshooting.
- **D-07:** Separate stderr from stdout. Parse stdout for step markers, log stderr separately at warning level.
- **D-08:** No cleanup on remote host when setup.sh fails. Log which step failed and suggest operator action. setup.sh is idempotent (Phase 10), so re-running retries from the failure point.

### Health Poll & Registration
- **D-09:** Health poll timeout defaults to 10 minutes (600s), configurable via settings. Covers large models like 72B that take several minutes to load.
- **D-10:** Poll from gateway using httpx (same HTTP client the proxy already uses). Direct HTTP to remote host's vLLM port (e.g., `http://host:8000/health`).
- **D-11:** node_id derived from hostname (e.g., `f16-h01-000-r750.rdu2.scalelab.redhat.com`). Natural, predictable, unique per host, matches QUADS naming. Re-provisioning same host updates same etcd key.
- **D-12:** Registration data matches existing Node model fields: node_id, endpoint (host:port), status=healthy, model name, capabilities. Written to etcd, watcher propagates to NodeRegistry.

### Module Structure
- **D-13:** New `inference_proxy/provisioning/` package. Separate concern from proxy/discovery/resilience. Matches existing package-per-domain pattern.
- **D-14:** Thin `SSHClient` wrapper class around asyncssh (mirrors `EtcdClient` wrapping etcd3gw). Handles connection, key auth, command execution. Provisioner depends on SSHClient, not asyncssh directly. Follows DIP.
- **D-15:** Concrete `NodeProvisioner` class, no protocol/interface. SSH is the only provisioning method — add interface if/when a second backend appears. YAGNI.
- **D-16:** `SSHSettings(BaseModel)` sub-model on root Settings: `key_path`, `username`, `connect_timeout`. Follows existing pattern (EtcdSettings, GatewaySettings).
- **D-17:** Separate `ProvisioningSettings(BaseModel)` sub-model for health poll params: `health_poll_timeout` (default 600s), `health_poll_interval`. SSHSettings stays SSH-only.

### Claude's Discretion
- None — all decisions made by user.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Scripts (Phase 10 output — what gets executed remotely)
- `auto-vllm-container/setup.sh` — Hardened setup script with `[STEP:name:STATUS]` markers, idempotent steps, env var defaults
- `auto-vllm-container/start-vllm.sh` — Host-side launcher: `podman build` + `podman run -d --replace`, GPU detection, model-based container naming
- `auto-vllm-container/entrypoint.sh` — Thin container entrypoint (runs `vllm serve`)
- `auto-vllm-container/Containerfile` — Container build definition

### Existing Code (integration points)
- `inference_proxy/discovery/etcd_client.py` — EtcdClient wrapper (needs `put` method for registration)
- `inference_proxy/discovery/serializer.py` — Node serialization for etcd (registration must match this format)
- `inference_proxy/models/node.py` — Node model with NodeStatus enum (registration data must match)
- `inference_proxy/config/settings.py` — Settings pattern to follow for SSHSettings and ProvisioningSettings

### Project Context
- `.planning/ROADMAP.md` — Phase 11 success criteria and requirements mapping
- `.planning/REQUIREMENTS.md` — PROV-01 through PROV-04 requirement definitions
- `.planning/phases/10-script-hardening/10-CONTEXT.md` — Phase 10 decisions (step marker format, script structure, container naming)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `EtcdClient` pattern — thin wrapper class that encapsulates a third-party library. SSHClient should mirror this pattern for asyncssh.
- `NodeSerializer` — existing serialization for Node objects to/from etcd JSON. Registration must write data in this format.
- `Settings` structure — pydantic `BaseModel` sub-configs on root `BaseSettings`. New SSHSettings and ProvisioningSettings follow this pattern.

### Established Patterns
- Package-per-domain: `discovery/`, `proxy/`, `resilience/`, `routing/` — new `provisioning/` follows this
- DIP: `EtcdClient` is the sole consumer of `etcd3gw`. SSHClient should be the sole consumer of `asyncssh`.
- Frozen Pydantic models for domain objects (Node, NodeCapabilities)
- structlog for all logging

### Integration Points
- `EtcdClient.put()` — new method needed to write node registration data to etcd
- `NodeRegistry` — receives new node via etcd watcher (write to etcd, watcher propagates — never mutate registry directly)
- `Settings` — add `SSHSettings` and `ProvisioningSettings` sub-models
- `asyncssh` — new dependency to add to pyproject.toml

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

*Phase: 11-SSH Provisioning*
*Context gathered: 2026-07-01*
