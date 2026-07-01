# Phase 11: SSH Provisioning - Research

**Researched:** 2026-07-01
**Domain:** SSH remote execution, async process streaming, etcd node registration
**Confidence:** HIGH

## Summary

Phase 11 adds the ability for the gateway to SSH into a remote QUADS lab server, execute the hardened setup.sh and start-vllm.sh scripts from Phase 10, stream their output in real-time parsing `[STEP:name:STATUS]` markers, poll the remote vLLM `/health` endpoint until ready, and register the node in etcd. The entire flow is async using `asyncssh` for SSH and the existing `httpx` async client for health polling.

The codebase already has all the patterns needed: `EtcdClient` as a thin wrapper (DIP model for `SSHClient`), `NodeSerializer` for etcd registration format, frozen Pydantic `Node` model, pydantic-settings sub-model pattern, and `structlog` for all logging. The new `provisioning/` package follows the established package-per-domain convention (`discovery/`, `proxy/`, `resilience/`, `routing/`).

**Primary recommendation:** Add `asyncssh>=2.20` to dependencies, create a thin `SSHClient` wrapper following the `EtcdClient` pattern, a `NodeProvisioner` that orchestrates the full sequence (setup -> container -> health poll -> register), and add `EtcdClient.put()` delegating to the existing `etcd3gw` client's `put(key, value)` method.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Single SSH key path in settings (`SSH_KEY_PATH`, default `~/.ssh/id_rsa`). All hosts use the same key.
- **D-02:** Single SSH username in settings (`SSH_USERNAME`). All hosts use the same user.
- **D-03:** Disable known_hosts verification (`known_hosts=None` in asyncssh). Lab servers get reimaged frequently.
- **D-04:** SSH connect timeout configurable via settings, default 10 seconds.
- **D-05:** Stream stdout line-by-line in real-time via asyncssh. Parse `[STEP:name:STATUS]` markers as they arrive.
- **D-06:** Log-only output -- all remote output goes to structlog. No in-memory storage.
- **D-07:** Separate stderr from stdout. Parse stdout for step markers, log stderr at warning level.
- **D-08:** No cleanup on remote host when setup.sh fails. Log which step failed and suggest operator action.
- **D-09:** Health poll timeout defaults to 10 minutes (600s), configurable.
- **D-10:** Poll from gateway using httpx. Direct HTTP to remote host's vLLM port.
- **D-11:** node_id derived from hostname.
- **D-12:** Registration data matches existing Node model fields. Written to etcd, watcher propagates to NodeRegistry.
- **D-13:** New `inference_proxy/provisioning/` package.
- **D-14:** Thin `SSHClient` wrapper class around asyncssh (mirrors EtcdClient pattern). Follows DIP.
- **D-15:** Concrete `NodeProvisioner` class, no protocol/interface. YAGNI.
- **D-16:** `SSHSettings(BaseModel)` sub-model on root Settings.
- **D-17:** Separate `ProvisioningSettings(BaseModel)` sub-model for health poll params.

### Claude's Discretion
- None -- all decisions made by user.

### Deferred Ideas (OUT OF SCOPE)
- None.

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PROV-01 | Gateway can SSH into a host via asyncssh using pre-configured keys | asyncssh `connect()` with `client_keys`, `username`, `known_hosts=None`, `connect_timeout` params. SSHClient wrapper class. |
| PROV-02 | Gateway runs setup.sh remotely (NVIDIA drivers, NFS, container toolkit) | `create_process()` with `async for line in process.stdout` streaming. Parse `[STEP:name:STATUS]` markers. setup.sh has 6 steps. |
| PROV-03 | Gateway builds and starts vLLM container on remote host with GPU auto-detection | Same SSH execution for start-vllm.sh. Script handles GPU detection, model selection, `podman build` + `podman run -d --replace`. |
| PROV-04 | Gateway polls remote /health endpoint until vLLM is ready, then registers in etcd | httpx `AsyncClient.get()` with retry loop. `EtcdClient.put()` (new method) + `node_to_etcd()` serializer. |

</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| SSH connection management | API / Backend | -- | Gateway process owns the SSH connection lifecycle |
| Remote script execution | API / Backend | -- | Gateway initiates and monitors remote commands |
| Output streaming/parsing | API / Backend | -- | Gateway parses step markers from SSH stdout |
| Health polling | API / Backend | -- | Gateway polls remote vLLM HTTP endpoint |
| Node registration | API / Backend | Database / Storage | Gateway writes to etcd; watcher propagates to in-memory registry |
| Configuration (SSH/provisioning) | API / Backend | -- | pydantic-settings on the gateway process |

## Standard Stack

### Core (new dependency)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| asyncssh | >=2.20, <3.0 | Async SSH client | Native asyncio SSH. 18M monthly PyPI downloads. 1.7k GitHub stars. Pure Python (no C extensions beyond cryptography). Supports key auth, known_hosts bypass, process streaming. [VERIFIED: PyPI registry, slopcheck OK] |

### Already Installed (used by this phase)

| Library | Version | Purpose | How Used |
|---------|---------|---------|----------|
| httpx | >=0.28 | Health polling | `AsyncClient.get(f"http://{host}:{port}/health")` with timeout |
| etcd3gw | >=2.5.0 | Node registration | `Etcd3Client.put(key, value)` -- already available in library, wrapper needs new method |
| structlog | >=26.1.0 | Logging | All remote output + provisioning events logged via structlog |
| pydantic | >=2.10 | Settings models | SSHSettings, ProvisioningSettings sub-models |
| pydantic-settings | >=2.14 | Env config | Root Settings class loads SSH/provisioning config from env |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| asyncssh | paramiko + asyncio.to_thread() | paramiko is sync-only, requires thread wrapping for every call. asyncssh is native asyncio -- cleaner for streaming stdout line-by-line. STATE.md records this decision. |
| asyncssh | fabric | fabric wraps paramiko, adds deploy abstractions we don't need. Heavier dependency. |
| httpx health poll | asyncssh + curl on remote | Adds fragility (curl must be installed). httpx is already in the process and gives us proper status code handling. |

**Installation:**
```bash
uv add "asyncssh>=2.20,<3.0"
```

**Version verification:**
- asyncssh 2.24.0 confirmed on PyPI (latest as of 2026-07-01). Requires Python >=3.10, cryptography >=48.0.1. [VERIFIED: PyPI registry]
- etcd3gw `put(key, value, lease=None) -> bool` confirmed in etcd3gw.client module. [VERIFIED: Python import + help()]

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| asyncssh | PyPI | 12 yrs (since Aug 2014) | 18.4M/month | github.com/ronf/asyncssh | [OK] | Approved |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
Operator triggers provision(hostname)
            |
            v
    +-------------------+
    | NodeProvisioner    |
    | (orchestrator)     |
    +-------------------+
            |
            | 1. connect
            v
    +-------------------+        SSH         +------------------+
    | SSHClient         | -----------------> | Remote Host      |
    | (asyncssh wrapper)|                    |                  |
    +-------------------+                    |  2. setup.sh     |
            |                                |  [STEP:...:OK]   |
            | stdout lines                   |                  |
            | (parsed for markers)           |  3. start-vllm.sh|
            |                                |  (podman build/  |
            |                                |   podman run)    |
            |                                |                  |
            |                                |  4. vLLM serves  |
            |                                |  on :8000        |
    +-------------------+        HTTP        +------------------+
    | httpx AsyncClient | -----------------> | :8000/health     |
    | (health poll)     |   5. poll until    |                  |
    +-------------------+      200 OK        +------------------+
            |
            | 6. register
            v
    +-------------------+
    | EtcdClient.put()  | -----> etcd -----> watcher -----> NodeRegistry
    +-------------------+
```

### Recommended Project Structure

```
inference_proxy/
  provisioning/
    __init__.py          # package marker
    ssh_client.py        # SSHClient wrapper (sole asyncssh consumer)
    provisioner.py       # NodeProvisioner orchestration
  config/
    settings.py          # + SSHSettings, ProvisioningSettings sub-models
  discovery/
    etcd_client.py       # + put() method
```

### Pattern 1: Thin Wrapper (DIP)

**What:** SSHClient wraps asyncssh the same way EtcdClient wraps etcd3gw. No other module imports asyncssh directly.
**When to use:** Always -- this is the established DIP pattern in this codebase.
**Example:**

```python
# Source: mirrors inference_proxy/discovery/etcd_client.py pattern
import asyncssh
import structlog
from inference_proxy.config.settings import SSHSettings

logger = structlog.get_logger()

class SSHClient:
    """Thin wrapper around asyncssh. Sole consumer of asyncssh in the codebase."""

    def __init__(self, settings: SSHSettings) -> None:
        self._settings = settings

    async def run_command(
        self, host: str, command: str
    ) -> AsyncIterator[str]:
        """Connect to host, run command, yield stdout lines."""
        async with asyncssh.connect(
            host,
            username=self._settings.username,
            client_keys=[str(self._settings.key_path)],
            known_hosts=None,  # D-03: lab servers reimaged frequently
            connect_timeout=self._settings.connect_timeout,
        ) as conn:
            async with conn.create_process(command) as process:
                async for line in process.stdout:
                    yield line.rstrip("\n")
                # Check exit status after process completes
                status = process.exit_status
                if status != 0:
                    raise RemoteCommandError(host, command, status)
```
[CITED: asyncssh.readthedocs.io — connect() and create_process() API]

### Pattern 2: Step Marker Parsing

**What:** Parse `[STEP:name:STATUS]` markers from streamed stdout lines.
**When to use:** During setup.sh execution to track provisioning progress.
**Example:**

```python
# Source: auto-vllm-container/setup.sh marker format
import re

_STEP_PATTERN = re.compile(r"\[STEP:(\w+):(START|OK|FAIL)\]")

def parse_step_marker(line: str) -> tuple[str, str] | None:
    """Extract (step_name, status) from a line, or None if no marker."""
    match = _STEP_PATTERN.search(line)
    if match:
        return match.group(1), match.group(2)
    return None
```
[VERIFIED: auto-vllm-container/setup.sh lines 14-18]

### Pattern 3: Health Poll Loop

**What:** Poll remote /health with exponential backoff until 200 OK or timeout.
**When to use:** After start-vllm.sh completes, before etcd registration.
**Example:**

```python
# Source: mirrors resilience/health_checker.py pattern adapted for async
import asyncio
import httpx

async def poll_health(
    client: httpx.AsyncClient,
    url: str,
    timeout: float,
    interval: float,
) -> bool:
    """Poll url until 200 OK. Returns True on success, False on timeout."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        try:
            resp = await client.get(url, timeout=5.0)
            if resp.status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        await asyncio.sleep(interval)
    return False
```
[ASSUMED — adapted from existing health_checker.py pattern]

### Pattern 4: EtcdClient.put() Addition

**What:** Add `put(key, value)` method to existing EtcdClient wrapper.
**When to use:** Node registration after health poll succeeds.
**Example:**

```python
# Add to inference_proxy/discovery/etcd_client.py
def put(self, key: str, value: str | bytes) -> bool:
    """Put a key-value pair into etcd.

    Args:
        key: The full key (e.g., '/nodes/hostname').
        value: The JSON-encoded value bytes.

    Returns:
        True on success.
    """
    return self._client.put(key, value)
```
[VERIFIED: etcd3gw.client.Etcd3Client.put(key, value, lease=None) -> bool confirmed via Python import]

### Anti-Patterns to Avoid

- **Importing asyncssh outside SSHClient:** Violates DIP. Only `ssh_client.py` imports asyncssh.
- **Storing remote output in memory:** D-06 says log-only. No output buffers, no return values carrying full output.
- **Mutating NodeRegistry directly from provisioner:** D-12 says write to etcd, let watcher propagate. The provisioner calls `EtcdClient.put()`, never `NodeRegistry.add()`.
- **Cleaning up remote host on failure:** D-08 explicitly says no cleanup. setup.sh is idempotent.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| SSH connection/auth | Raw socket + SSH protocol | asyncssh.connect() | SSH protocol is complex (key exchange, channel mux, etc.) |
| SSH key loading | Manual key file parsing | asyncssh client_keys parameter | Handles RSA, Ed25519, ECDSA, encrypted keys |
| etcd put | Raw HTTP to etcd gateway | etcd3gw Etcd3Client.put() | Handles base64 encoding, API versioning |
| Node serialization | Manual JSON construction | node_to_etcd() from serializer.py | Already handles node_id exclusion, mode="json" |

**Key insight:** This phase wires existing building blocks together. The only new library is asyncssh; everything else (httpx, etcd3gw, Node model, serializer) already exists.

## Common Pitfalls

### Pitfall 1: asyncssh Default Known Hosts Check

**What goes wrong:** asyncssh checks `~/.ssh/known_hosts` by default. Lab servers get reimaged and change host keys, causing `HostKeyNotVerifiable` errors.
**Why it happens:** asyncssh defaults to verifying host keys (good security practice).
**How to avoid:** Set `known_hosts=None` in `asyncssh.connect()` per D-03.
**Warning signs:** `asyncssh.HostKeyNotVerifiable` exception on first connection to a reimaged host.

### Pitfall 2: asyncssh Default Client Key Discovery

**What goes wrong:** asyncssh auto-discovers all keys in `~/.ssh/` and tries them all. If a key requires a passphrase, it may prompt or fail.
**Why it happens:** Default `client_keys=()` means "try all default keys."
**How to avoid:** Explicitly pass `client_keys=[str(settings.key_path)]` to limit to the configured key only.
**Warning signs:** `PermissionDenied` after trying wrong keys, or interactive passphrase prompts hanging the process.

### Pitfall 3: create_process stdout Newline Handling

**What goes wrong:** `async for line in process.stdout` includes trailing newlines. Step marker regex may fail if not stripped.
**Why it happens:** asyncssh SSHReader yields lines with `\n` included.
**How to avoid:** `.rstrip("\n")` on each line before parsing.
**Warning signs:** Marker regex matches but captured group has trailing whitespace.

### Pitfall 4: Health Poll Starting Too Early

**What goes wrong:** Health polling starts immediately after `start-vllm.sh` exits, but `podman run -d` returns before vLLM is actually listening on port 8000. Container is still loading the model.
**Why it happens:** `podman run -d` is detached -- it exits as soon as the container starts, not when the application is ready.
**How to avoid:** This is expected behavior. The poll loop handles it naturally -- early polls return connection refused, then eventually 200 OK. Just make sure the first poll failures are logged at debug, not warning.
**Warning signs:** None -- this is the normal flow. But the 10-minute timeout (D-09) must be long enough for large models (72B).

### Pitfall 5: etcd3gw put() Runs in Sync

**What goes wrong:** `EtcdClient.put()` is synchronous (etcd3gw is sync-only). Calling it from an async context blocks the event loop.
**Why it happens:** etcd3gw uses `requests` internally, which is blocking.
**How to avoid:** Wrap in `asyncio.to_thread(etcd_client.put, key, value)` from the provisioner. This matches the existing pattern documented in CLAUDE.md for etcd3gw operations.
**Warning signs:** Event loop stalls during registration -- other async tasks freeze momentarily.

### Pitfall 6: SSH Process Exit Status After Streaming

**What goes wrong:** After iterating stdout, the process exit status may not be immediately available. Accessing `process.exit_status` before `process.wait()` may return `None`.
**Why it happens:** asyncssh process objects resolve exit status asynchronously.
**How to avoid:** After the `async for` loop on stdout completes, await `process.wait()` or check `process.returncode` which blocks until the process exits. Or use the context manager form (`async with conn.create_process(...)`) which waits on exit.
**Warning signs:** Exit status is `None` when checked immediately after stdout iteration.

## Code Examples

### Full SSHClient Pattern

```python
# Source: asyncssh.readthedocs.io + EtcdClient pattern from codebase
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import asyncssh
import structlog

from inference_proxy.config.settings import SSHSettings

logger = structlog.get_logger()


class SSHConnectionError(Exception):
    """Raised when SSH connection fails."""
    def __init__(self, host: str, reason: str) -> None:
        self.host = host
        self.reason = reason
        super().__init__(f"SSH connection to {host} failed: {reason}")


class RemoteCommandError(Exception):
    """Raised when a remote command exits with non-zero status."""
    def __init__(self, host: str, command: str, exit_status: int) -> None:
        self.host = host
        self.command = command
        self.exit_status = exit_status
        super().__init__(
            f"Command '{command}' on {host} exited with status {exit_status}"
        )


class SSHClient:
    """Sole consumer of asyncssh in the codebase (DIP)."""

    def __init__(self, settings: SSHSettings) -> None:
        self._username = settings.username
        self._key_path = settings.key_path
        self._connect_timeout = settings.connect_timeout

    async def run_streaming(
        self, host: str, command: str
    ) -> AsyncIterator[tuple[str, str]]:
        """Run command on host, yield (stream, line) tuples.

        stream is "stdout" or "stderr".
        """
        try:
            async with asyncssh.connect(
                host,
                username=self._username,
                client_keys=[str(self._key_path)],
                known_hosts=None,
                connect_timeout=self._connect_timeout,
            ) as conn:
                async with conn.create_process(command) as process:
                    # Read stdout line by line
                    async for line in process.stdout:
                        yield ("stdout", line.rstrip("\n"))
                    # After stdout exhausted, check exit status
                    if process.exit_status != 0:
                        raise RemoteCommandError(
                            host, command, process.exit_status or -1
                        )
        except asyncssh.PermissionDenied as exc:
            raise SSHConnectionError(host, f"authentication failed: {exc}") from exc
        except asyncssh.DisconnectError as exc:
            raise SSHConnectionError(host, f"disconnected: {exc.reason}") from exc
        except OSError as exc:
            raise SSHConnectionError(host, str(exc)) from exc
```
[CITED: asyncssh.readthedocs.io — connect(), create_process(), exception hierarchy]

### Node Registration Pattern

```python
# Source: existing serializer.py + etcd_client.py patterns
import asyncio
from datetime import datetime, timezone

from inference_proxy.discovery.etcd_client import EtcdClient
from inference_proxy.discovery.serializer import node_to_etcd
from inference_proxy.models.node import Node, NodeCapabilities, NodeStatus


async def register_node(
    etcd_client: EtcdClient,
    hostname: str,
    port: int,
    model: str,
) -> None:
    """Register a healthy node in etcd. Watcher propagates to NodeRegistry."""
    node = Node(
        node_id=hostname,  # D-11
        endpoint=f"{hostname}:{port}",
        status=NodeStatus.HEALTHY,
        model=model,
        last_heartbeat=datetime.now(timezone.utc),
        capabilities=NodeCapabilities(),
    )
    key, value = node_to_etcd(node, etcd_client.prefix)
    await asyncio.to_thread(etcd_client.put, key, value)  # sync -> async
```
[VERIFIED: node_to_etcd() signature from inference_proxy/discovery/serializer.py]

### Settings Sub-Model Pattern

```python
# Source: existing settings.py pattern (EtcdSettings, GatewaySettings, etc.)
from pathlib import Path
from pydantic import BaseModel


class SSHSettings(BaseModel):
    """SSH connection configuration (D-16)."""
    key_path: Path = Path("~/.ssh/id_rsa")  # D-01
    username: str = "root"  # D-02
    connect_timeout: int = 10  # D-04


class ProvisioningSettings(BaseModel):
    """Provisioning health poll configuration (D-17)."""
    health_poll_timeout: int = 600  # D-09: 10 minutes
    health_poll_interval: int = 10
    vllm_port: int = 8000
```
[VERIFIED: existing settings.py sub-model pattern]

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| paramiko (sync SSH) | asyncssh (native asyncio) | asyncssh stable since 2014, asyncio since Python 3.4 | No thread wrapping needed for SSH operations |
| fabric/ansible for provisioning | Direct SSH via asyncssh | Project decision (STATE.md) | Simpler dependency, no orchestration framework overhead |
| Polling then manual registration | Write to etcd, watcher propagates | Established in Phase 2 | Consistent with existing node discovery flow |

**Deprecated/outdated:**
- paramiko: Still maintained but sync-only. asyncssh is the standard for asyncio SSH.
- python-etcd3: Abandoned. etcd3gw is the correct choice (already in use).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | asyncssh `create_process` context manager awaits exit status on `__aexit__` | Pitfall 6 | Process exit status might need explicit `await process.wait()` call |
| A2 | `async for line in process.stdout` yields one line per iteration with trailing newline | Pitfall 3 | Marker parsing could silently miss markers if lines are chunked differently |
| A3 | Health poll interval of 10s with 600s timeout is appropriate for large model loading | Code Examples | Too aggressive polling wastes resources; too short timeout fails on 72B models |

## Open Questions

1. **Model name extraction from start-vllm.sh**
   - What we know: start-vllm.sh selects a model based on GPU detection and prints config info to stdout. The `MODEL` variable is set internally.
   - What's unclear: How does the provisioner know which model was selected for the etcd registration `model` field? start-vllm.sh doesn't output a machine-parseable model name.
   - Recommendation: Parse the `# Model: Qwen/Qwen2.5-72B-Instruct` line from start-vllm.sh stdout. It's printed in the config block. Or pass `VLLM_MODEL` env var explicitly and use that for registration.

2. **stderr handling with create_process**
   - What we know: D-07 says separate stderr from stdout, log stderr at warning. asyncssh `create_process()` has `stderr=PIPE` by default.
   - What's unclear: Whether we can interleave stdout and stderr reads without deadlock. Reading stdout only and collecting stderr after process completion may be simpler.
   - Recommendation: Read stdout in the async for loop (for real-time markers). After process exits, read stderr in bulk via `process.stderr.read()` and log at warning level if non-empty.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | Runtime | Yes | 3.12 | -- |
| uv | Package management | Yes | 0.11+ | -- |
| asyncssh (PyPI) | SSH connections | Not installed yet | 2.24.0 available | -- |
| etcd (service) | Node registration | Not checked | -- | Gateway starts with empty registry per existing pattern |

**Missing dependencies with no fallback:** None (asyncssh is installable via `uv add`).

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 1.4.x |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/provisioning/ -x -q` |
| Full suite command | `uv run pytest -x -q` |

### Phase Requirements -> Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PROV-01 | SSHClient connects with key auth, no known_hosts | unit (mock asyncssh.connect) | `uv run pytest tests/provisioning/test_ssh_client.py -x` | Wave 0 |
| PROV-01 | SSHClient raises SSHConnectionError on auth failure | unit | `uv run pytest tests/provisioning/test_ssh_client.py -x` | Wave 0 |
| PROV-02 | Provisioner runs setup.sh, parses step markers | unit (mock SSHClient) | `uv run pytest tests/provisioning/test_provisioner.py -x` | Wave 0 |
| PROV-02 | Provisioner logs step start/ok/fail via structlog | unit | `uv run pytest tests/provisioning/test_provisioner.py -x` | Wave 0 |
| PROV-03 | Provisioner runs start-vllm.sh after setup.sh | unit (mock SSHClient) | `uv run pytest tests/provisioning/test_provisioner.py -x` | Wave 0 |
| PROV-04 | Health poll returns True on 200 OK | unit (mock httpx) | `uv run pytest tests/provisioning/test_provisioner.py -x` | Wave 0 |
| PROV-04 | Health poll returns False on timeout | unit (mock httpx) | `uv run pytest tests/provisioning/test_provisioner.py -x` | Wave 0 |
| PROV-04 | Provisioner registers node in etcd on healthy | unit (mock EtcdClient) | `uv run pytest tests/provisioning/test_provisioner.py -x` | Wave 0 |
| -- | EtcdClient.put() delegates to etcd3gw | unit (mock Etcd3Client) | `uv run pytest tests/discovery/test_etcd_client.py -x` | Wave 0 |
| -- | SSHSettings/ProvisioningSettings defaults | unit | `uv run pytest tests/config/test_settings.py -x` | Extend existing |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/provisioning/ tests/discovery/test_etcd_client.py tests/config/test_settings.py -x -q`
- **Per wave merge:** `uv run pytest -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/provisioning/__init__.py` -- package marker
- [ ] `tests/provisioning/test_ssh_client.py` -- covers PROV-01
- [ ] `tests/provisioning/test_provisioner.py` -- covers PROV-02, PROV-03, PROV-04

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | SSH key-based auth via asyncssh client_keys (no passwords) |
| V3 Session Management | no | -- |
| V4 Access Control | no | Internal network, no user-facing access control in this phase |
| V5 Input Validation | yes | Hostname validation before SSH connect (prevent injection in shell commands) |
| V6 Cryptography | yes | asyncssh handles SSH crypto. known_hosts=None is accepted risk for internal lab network. |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Command injection via hostname | Tampering | Validate hostname format before interpolating into shell commands |
| SSH key exposure | Information Disclosure | Key path from env/settings, never logged. Key file permissions checked by asyncssh. |
| Man-in-the-middle (known_hosts=None) | Spoofing | Accepted risk per D-03 (internal network only, hosts reimaged frequently) |
| Remote command output injection | Tampering | Step marker parsing uses strict regex, not eval. Non-marker lines are only logged. |

## Sources

### Primary (HIGH confidence)
- asyncssh PyPI: https://pypi.org/project/asyncssh/ -- v2.24.0, 18.4M/month downloads, since 2014 [VERIFIED: PyPI + slopcheck]
- asyncssh docs: https://asyncssh.readthedocs.io/ -- connect(), create_process(), known_hosts, client_keys API [CITED]
- etcd3gw put() method: confirmed via `python3 -c "help(Etcd3Client.put)"` -- `put(key, value, lease=None) -> bool` [VERIFIED: Python import]
- Existing codebase: EtcdClient, NodeSerializer, Node model, Settings patterns [VERIFIED: source code]
- auto-vllm-container/setup.sh: step marker format `[STEP:name:STATUS]` [VERIFIED: source code]

### Secondary (MEDIUM confidence)
- asyncssh GitHub: https://github.com/ronf/asyncssh -- 1.7k stars, active development [CITED]
- asyncssh exception hierarchy: DisconnectError, PermissionDenied, HostKeyNotVerifiable [CITED: asyncssh docs + GitHub discussions]

### Tertiary (LOW confidence)
- None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- asyncssh is the established async SSH library, verified on PyPI with 12 years of history
- Architecture: HIGH -- all patterns mirror existing codebase (EtcdClient, Settings, package-per-domain)
- Pitfalls: HIGH -- verified via asyncssh docs and codebase patterns

**Research date:** 2026-07-01
**Valid until:** 2026-07-31 (stable libraries, unlikely to change)
