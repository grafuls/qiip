# Technology Stack

**Project:** QUADS LLM Inference Proxy -- v1.2 Node Provisioning
**Researched:** 2026-07-01
**Overall Confidence:** HIGH
**Scope:** Stack additions for SSH-based node setup/teardown. Existing stack (FastAPI, httpx, etcd3gw, structlog, Pydantic v2, Jinja2) is validated and NOT re-evaluated here.

## New Dependencies for v1.2

### SSH Client

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| asyncssh | >=2.24.0 | Async SSH client | Native asyncio SSH -- connects to QUADS hosts, runs setup/teardown scripts, streams command output. No thread wrapping needed (unlike paramiko). Ships `py.typed` + full type annotations since v2.9.0, compatible with mypy `--strict`. ~18M monthly PyPI downloads. Actively maintained (2.24.0 released Jun 27, 2026). Python >=3.10. | HIGH |

**This is the only new runtime dependency needed for v1.2.**

### Why asyncssh and not the alternatives

| Library | Async | License | Verdict |
|---------|-------|---------|---------|
| **asyncssh** | Native asyncio | EPL-2.0 OR GPL-2.0+ | **USE** -- native async, typed, actively maintained |
| paramiko | No (needs `asyncio.to_thread()`) | LGPL-2.1 | REJECT -- sync-only, would need thread pool per SSH session |
| fabric | No (wraps paramiko) | BSD-2 | REJECT -- CLI/sysadmin tool, not a library for async apps |
| parallel-ssh | Partial (gevent or libssh2) | LGPL-2.1 | REJECT -- gevent conflicts with asyncio event loop |

**asyncssh wins because:**

1. **Native asyncio** -- the app is async FastAPI + httpx. asyncssh uses `async with` / `await` natively. No `asyncio.to_thread()` wrapping, no thread pool sizing, no sync/async impedance mismatch. paramiko would require wrapping every call in `asyncio.to_thread()`, as we already do for etcd3gw -- adding a second threaded subsystem increases complexity for no benefit when a native async option exists.

2. **Connection reuse** -- SSH connections support multiple channels. One `asyncssh.connect()` call to a host can run multiple commands sequentially or in parallel via `conn.run()`. This matters for the setup flow (run setup.sh, then build container, then start vLLM -- all over one connection).

3. **Streaming output** -- `conn.create_process()` provides `process.stdout.readline()` for real-time log streaming. Important for long-running setup scripts (NVIDIA driver install can take minutes). Enables future dashboard log streaming.

4. **Type safety** -- Ships `py.typed` marker and full type annotations. Works with the project's `mypy --strict` configuration out of the box.

5. **18M monthly downloads** -- heavily adopted. Not a niche library.

### License note

asyncssh is dual-licensed: EPL-2.0 OR GPL-2.0-or-later. For internal-only use (no distribution), neither license imposes obligations. This project is explicitly "internal network only" per PROJECT.md constraints, so no licensing concern.

## No New Dependencies Needed For

These capabilities are covered by the existing stack:

| Capability | Covered By | How |
|------------|------------|-----|
| Health polling (POST setup, wait for /health 200) | httpx (already installed) | `httpx.AsyncClient.get(f"http://{host}:8000/health")` in a retry loop |
| etcd registration after setup | etcd3gw (already installed) | Same `EtcdClient.put()` pattern used by the watcher |
| Retry/backoff for health polling | tenacity (already in CLAUDE.md stack) OR stdlib asyncio | `asyncio.sleep()` loop with exponential backoff is 5 lines; tenacity is in the recommended stack but not yet in pyproject.toml -- add only if retry patterns proliferate |
| Background task management | anyio (transitive dep of FastAPI) | Task groups for concurrent provisioning operations |
| Configuration (SSH key path, timeouts) | pydantic-settings (already installed) | New `ProvisioningSettings` sub-model in settings.py |
| Structured logging | structlog (already installed) | Log SSH operations with host/command context |

## What NOT to Add

| Technology | Why Not |
|------------|---------|
| paramiko | Sync-only. Would be the second subsystem (after etcd3gw) needing thread wrapping. asyncssh eliminates this entirely. |
| fabric | CLI deployment tool built on paramiko. Designed for `fab deploy` workflows, not programmatic async API calls. Overkill and wrong paradigm. |
| parallel-ssh | Uses gevent or libssh2 bindings. gevent monkey-patching conflicts with asyncio. Not needed -- asyncssh handles concurrent connections natively via asyncio tasks. |
| ansible-runner | Pulls in the entire Ansible engine. We run 2 shell scripts on bare metal hosts. A 200MB dependency for `ssh host 'bash setup.sh'` is absurd. |
| Celery / dramatiq / arq | No task queue needed. Provisioning is triggered by admin API, runs as an asyncio background task, reports status via polling. The gateway has no persistent job storage requirement in v1.2. |
| subprocess + system ssh | Spawns OS processes, no structured error handling, no connection reuse, no streaming output parsing. asyncssh is a proper library. |

## Integration Pattern with Existing App

### asyncssh fits the existing patterns

The codebase already uses two concurrency models:
- **Async (main):** FastAPI handlers, httpx proxy calls -- all `async/await`
- **Threaded (background):** etcd3gw watcher, health checker -- `threading.Thread` with `stop_event`

asyncssh adds SSH operations to the async side. No new threading needed.

```python
# Typical usage pattern -- fits naturally into FastAPI async handlers
import asyncssh

async def setup_node(host: str, ssh_key_path: str) -> None:
    async with asyncssh.connect(
        host,
        username="root",
        client_keys=[ssh_key_path],
        known_hosts=None,  # Internal lab network, hosts are trusted
        connect_timeout=30,
        login_timeout=30,
        keepalive_interval=60,  # Setup scripts run for minutes
    ) as conn:
        # Run setup script, get full output
        result = await conn.run("bash /tmp/setup.sh", timeout=600)
        if result.exit_status != 0:
            raise SetupError(result.stderr)
```

### Key asyncssh parameters for this use case

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `known_hosts` | `None` | Internal QUADS lab network. Hosts are re-imaged frequently; host keys change. Strict checking would break on every re-provision. |
| `username` | `"root"` | Setup scripts need root for `dnf install`, `modprobe`, `iptables`, NFS mount. QUADS lab servers provide root SSH access. |
| `client_keys` | `[settings.ssh_key_path]` | Pre-configured SSH key. Operator ensures `~/.ssh` access per PROJECT.md. |
| `connect_timeout` | `30` | Fail fast if host is unreachable. |
| `login_timeout` | `30` | Fail fast if auth fails. |
| `keepalive_interval` | `60` | setup.sh installs NVIDIA drivers (several minutes). Keep connection alive during long silent periods. |
| `timeout` on `run()` | `600-1800` | setup.sh: driver install + container build can take 10-30 minutes. |

### New settings sub-model

```python
class ProvisioningSettings(BaseModel):
    """SSH provisioning configuration."""
    ssh_key_path: str = "~/.ssh/id_rsa"
    ssh_username: str = "root"
    connect_timeout: int = 30
    setup_timeout: int = 1800  # 30 min for full setup
    teardown_timeout: int = 120  # 2 min for container stop + deregister
    health_poll_interval: int = 10  # seconds between /health checks
    health_poll_timeout: int = 300  # 5 min max wait for vLLM startup
```

## Installation

```bash
# Only one new dependency
uv add "asyncssh>=2.24.0"
```

No new dev dependencies needed. The existing pytest + pytest-asyncio stack handles async SSH testing. Mock asyncssh connections in tests using standard unittest.mock (AsyncMock for coroutines).

## Key Version Constraints

| Dependency | Minimum | Why This Minimum |
|------------|---------|-----------------|
| asyncssh >= 2.24.0 | Latest release (Jun 2026). Includes py.typed, full type annotations, Python 3.12+ support, keepalive fixes. |

## Sources

- asyncssh PyPI: https://pypi.org/project/asyncssh/ -- v2.24.0 (Jun 27, 2026)
- asyncssh docs: https://asyncssh.readthedocs.io/ -- v2.23.1 docs (latest published)
- asyncssh GitHub: https://github.com/ronf/asyncssh
- asyncssh changelog (py.typed added v2.9.0): https://asyncssh.readthedocs.io/en/latest/changes.html
- asyncssh license (EPL-2.0 OR GPL-2.0+): https://github.com/ronf/asyncssh/issues/161
- paramiko vs asyncssh comparison: https://piptrends.com/compare/paramiko-vs-fabric-vs-asyncssh
- SSH library comparison: https://elegantnetwork.github.io/posts/comparing-ssh/
- asyncssh timeout discussion: https://github.com/ronf/asyncssh/discussions/409
- asyncssh known_hosts=None: https://github.com/ronf/asyncssh/issues/179
