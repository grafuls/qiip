# Phase 11: SSH Provisioning - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-01
**Phase:** 11-ssh-provisioning
**Areas discussed:** SSH key & connection config, Remote output handling, Health poll & registration, Module structure

---

## SSH Key & Connection Config

| Option | Description | Selected |
|--------|-------------|----------|
| Single key path in settings | One SSH_KEY_PATH setting (default ~/.ssh/id_rsa). All hosts use the same key. | ✓ |
| SSH agent forwarding | Use the running ssh-agent (SSH_AUTH_SOCK). No key path config needed. | |
| You decide | Let Claude pick the simplest approach. | |

**User's choice:** Single key path in settings

| Option | Description | Selected |
|--------|-------------|----------|
| Single username in settings | One SSH_USERNAME setting. All hosts use the same user. | ✓ |
| Per-host username at setup time | Caller passes username along with hostname. | |
| You decide | Let Claude pick. | |

**User's choice:** Single username in settings

| Option | Description | Selected |
|--------|-------------|----------|
| Disable known_hosts check | asyncssh known_hosts=None. Lab servers get reimaged frequently. | ✓ |
| Accept on first connect | Trust-on-first-use (TOFU). Accept and cache on first SSH. | |
| You decide | Let Claude pick. | |

**User's choice:** Disable known_hosts check

| Option | Description | Selected |
|--------|-------------|----------|
| Setting with sensible default | SSH_CONNECT_TIMEOUT in settings, default 10s. | ✓ |
| Hardcoded 10s | No config needed — YAGNI. | |
| You decide | Let Claude pick. | |

**User's choice:** Setting with sensible default

---

## Remote Output Handling

| Option | Description | Selected |
|--------|-------------|----------|
| Stream and parse real-time | Read stdout line-by-line as it arrives. Parse markers in real-time. | ✓ |
| Buffer then parse | Wait for command to finish, then scan for markers. | |
| You decide | Let Claude pick. | |

**User's choice:** Stream and parse real-time

| Option | Description | Selected |
|--------|-------------|----------|
| Keep last N lines in memory | Store last ~200 lines. Available via future API. | |
| Log only | All output to structlog. No in-memory storage. | ✓ |
| You decide | Let Claude pick. | |

**User's choice:** Log only

| Option | Description | Selected |
|--------|-------------|----------|
| Merge with stdout | Combine into one stream. | |
| Separate streams | Parse stdout for markers, log stderr at warning level. | ✓ |
| You decide | Let Claude pick. | |

**User's choice:** Separate streams

| Option | Description | Selected |
|--------|-------------|----------|
| No cleanup on failure | Let failed state sit. setup.sh is idempotent. | |
| Log failure, note for operator | Log which step failed and suggest operator action. | ✓ |
| You decide | Let Claude pick. | |

**User's choice:** Log failure, note for operator

---

## Health Poll & Registration

| Option | Description | Selected |
|--------|-------------|----------|
| 10 minutes default, configurable | HEALTH_POLL_TIMEOUT setting, default 600s. | ✓ |
| 5 minutes hardcoded | Keep it simple. | |
| You decide | Let Claude pick. | |

**User's choice:** 10 minutes default, configurable

| Option | Description | Selected |
|--------|-------------|----------|
| httpx from gateway | Gateway makes HTTP requests to remote host's vLLM port. | ✓ |
| curl via SSH | Run curl on remote host via SSH connection. | |
| You decide | Let Claude pick. | |

**User's choice:** httpx from gateway

| Option | Description | Selected |
|--------|-------------|----------|
| Hostname-based | node_id = hostname. Natural, predictable, unique per host. | ✓ |
| Hostname + model | node_id = 'hostname:model'. Supports multi-model-per-host. | |
| You decide | Let Claude pick. | |

**User's choice:** Hostname-based

| Option | Description | Selected |
|--------|-------------|----------|
| Match existing Node model | Write JSON matching Node model fields. Consistent with watcher. | ✓ |
| Minimal — endpoint + model | Just endpoint and model. Let health checker fill rest. | |
| You decide | Let Claude pick. | |

**User's choice:** Match existing Node model

---

## Module Structure

| Option | Description | Selected |
|--------|-------------|----------|
| New provisioning package | inference_proxy/provisioning/ — separate concern. | ✓ |
| Extend discovery package | Add to inference_proxy/discovery/. | |
| You decide | Let Claude pick. | |

**User's choice:** New provisioning package

| Option | Description | Selected |
|--------|-------------|----------|
| Thin SSH wrapper class | SSHClient class wrapping asyncssh (like EtcdClient). Testable. | ✓ |
| Inline in provisioner | Provisioner calls asyncssh directly. Fewer files. | |
| You decide | Let Claude pick. | |

**User's choice:** Thin SSH wrapper class

| Option | Description | Selected |
|--------|-------------|----------|
| No interface, concrete class | One NodeProvisioner class. YAGNI. | ✓ |
| Protocol with SSH implementation | Define Provisioner protocol, implement SSHProvisioner. DIP. | |
| You decide | Let Claude balance SOLID vs YAGNI. | |

**User's choice:** No interface, concrete class

| Option | Description | Selected |
|--------|-------------|----------|
| SSHSettings sub-model | New SSHSettings(BaseModel) with key_path, username, connect_timeout. | ✓ |
| ProvisioningSettings | Broader settings including SSH + health poll + future params. | |
| You decide | Let Claude pick. | |

**User's choice:** SSHSettings sub-model

| Option | Description | Selected |
|--------|-------------|----------|
| On SSHSettings | health_poll_timeout and health_poll_interval on SSHSettings. | |
| Separate ProvisioningSettings | New ProvisioningSettings sub-model for health poll params. | ✓ |
| You decide | Let Claude pick. | |

**User's choice:** Separate ProvisioningSettings

---

## Claude's Discretion

None — user made all decisions directly.

## Deferred Ideas

None — discussion stayed within phase scope.
