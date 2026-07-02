---
phase: 11-ssh-provisioning
verified: 2026-07-02T04:15:00Z
status: passed
score: 15/15 must-haves verified
overrides_applied: 0
re_verification: false
---

# Phase 11: SSH Provisioning Verification Report

**Phase Goal:** Gateway can connect to a remote host over SSH and execute the full provisioning sequence end-to-end

**Verified:** 2026-07-02T04:15:00Z

**Status:** passed

**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | D-03: SSHClient connects to a host using key auth with known_hosts disabled | ✓ VERIFIED | `ssh_client.py:71-76` — asyncssh.connect called with `known_hosts=None`, `client_keys=[str(self._key_path)]`, `username=self._username`. Test: `test_ssh_client.py:63-75` verifies connect params. |
| 2 | D-05: SSHClient streams stdout line-by-line from a remote command | ✓ VERIFIED | `ssh_client.py:79-80` — async for loop yields `("stdout", line.rstrip("\n"))` tuples. Test: `test_ssh_client.py:83-89` verifies stdout streaming. |
| 3 | D-07: SSHClient yields stderr separately from stdout at warning level | ✓ VERIFIED | `ssh_client.py:82-87` — stderr read in bulk after stdout, yielded as `("stderr", line)` tuples. Test: `test_ssh_client.py:97-107` verifies stderr yielded separately. Provisioner logs stderr at warning level: `provisioner.py:87`. |
| 4 | D-09: ProvisioningSettings defaults health_poll_timeout to 600 seconds | ✓ VERIFIED | `settings.py:112` — `health_poll_timeout: int = 600` with comment "D-09: 10 minutes for large model loading". Test: `test_settings.py:120-122` verifies default. |
| 5 | SSHClient raises SSHConnectionError on auth failure or connection timeout | ✓ VERIFIED | `ssh_client.py:93-102` — catches `asyncssh.PermissionDenied`, `asyncssh.DisconnectError`, `OSError` and wraps in `SSHConnectionError`. Tests: `test_ssh_client.py:133-167` verify wrapping. |
| 6 | SSHClient raises RemoteCommandError when remote process exits non-zero | ✓ VERIFIED | `ssh_client.py:89-92` — raises `RemoteCommandError(host, command, exit_status)` when `process.exit_status != 0`. Test: `test_ssh_client.py:115-125` verifies exception raised with correct attributes. |
| 7 | EtcdClient.put() delegates to etcd3gw Etcd3Client.put() | ✓ VERIFIED | `etcd_client.py:72-82` — `self._client.put(key, value)` delegation. Test: `test_etcd_client.py:160-175` verifies delegation with mock. |
| 8 | D-01, D-02, D-04, D-16, D-17: SSHSettings and ProvisioningSettings load defaults and respond to env vars | ✓ VERIFIED | `settings.py:95-115` — SSHSettings has `key_path=Path("~/.ssh/id_rsa")`, `username="root"`, `connect_timeout=10`. ProvisioningSettings has `health_poll_timeout=600`, `health_poll_interval=10`, `vllm_port=8000`. Both registered on root Settings as `ssh: SSHSettings = SSHSettings()` and `provisioning: ProvisioningSettings = ProvisioningSettings()`. Tests: `test_settings.py:100-146` verify defaults and env overrides. |
| 9 | D-05: Provisioner runs setup.sh on remote host and parses step markers from streamed stdout | ✓ VERIFIED | `provisioner.py:71-87` — `_run_setup()` calls `ssh_client.run_streaming(hostname, "bash auto-vllm-container/setup.sh")`, parses stdout with `STEP_PATTERN.search(line)`, logs step_name and status. Test: `test_provisioner.py:94-113` verifies step marker parsing. |
| 10 | D-06: Provisioner logs each step start/ok/fail via structlog with step name and host — no in-memory storage | ✓ VERIFIED | `provisioner.py:77-85` — logs `step_marker` at info level with step, status, hostname. On FAIL, logs at error level. No in-memory storage — lines are processed in async generator and discarded after logging. |
| 11 | Provisioner runs start-vllm.sh on remote host after setup.sh succeeds | ✓ VERIFIED | `provisioner.py:64` — `provision()` calls `_run_start_vllm()` after `_run_setup()`. `_run_start_vllm()` at line 89-105 calls `ssh_client.run_streaming(hostname, "bash auto-vllm-container/start-vllm.sh")`. Test: `test_provisioner.py:46-88` verifies sequence order. |
| 12 | Provisioner extracts model name from start-vllm.sh stdout config block | ✓ VERIFIED | `provisioner.py:91-105` — `MODEL_PATTERN.search(line)` extracts model name from stdout. Raises `ProvisioningError` if model not found. Tests: `test_provisioner.py:120-149` verify extraction and error on missing model. |
| 13 | D-10: Provisioner polls remote /health endpoint via httpx until 200 OK or timeout | ✓ VERIFIED | `provisioner.py:107-127` — `_poll_health()` uses `httpx.AsyncClient` to poll `http://{hostname}:{vllm_port}/health` in loop until 200 OK or deadline exceeded. Tests: `test_provisioner.py:156-184` verify success and timeout. |
| 14 | D-11, D-12: Provisioner registers node in etcd with node_id=hostname, status=healthy, model from script | ✓ VERIFIED | `provisioner.py:129-141` — `_register_node()` constructs `Node(node_id=hostname, endpoint=f"{hostname}:{vllm_port}", status=NodeStatus.HEALTHY, model=model, last_heartbeat=datetime.now(timezone.utc))`, calls `node_to_etcd()`, writes via `etcd_client.put()`. Test: `test_provisioner.py:191-214` verifies Node fields. |
| 15 | Provisioner writes to etcd via asyncio.to_thread (etcd3gw is sync) | ✓ VERIFIED | `provisioner.py:140` — `await asyncio.to_thread(self._etcd_client.put, key, value)` with ponytail comment explaining etcd3gw sync wrapper. Test: `test_provisioner.py:198` mocks `asyncio.to_thread` and verifies call. |

**Score:** 15/15 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `inference_proxy/provisioning/__init__.py` | D-13: Package marker | ✓ VERIFIED | File exists (empty package marker). |
| `inference_proxy/provisioning/ssh_client.py` | D-14: SSHClient wrapper, SSHConnectionError, RemoteCommandError | ✓ VERIFIED | 103 lines. Exports `SSHClient`, `SSHConnectionError`, `RemoteCommandError`. Contains `class SSHClient`, `class SSHConnectionError`, `class RemoteCommandError`. Module docstring confirms sole asyncssh consumer (DIP). |
| `inference_proxy/config/settings.py` | D-16, D-17: SSHSettings and ProvisioningSettings sub-models on root Settings | ✓ VERIFIED | Lines 95-115 contain `class SSHSettings(BaseModel)` and `class ProvisioningSettings(BaseModel)`. Lines 140-141 register both on root Settings: `ssh: SSHSettings = SSHSettings()`, `provisioning: ProvisioningSettings = ProvisioningSettings()`. |
| `inference_proxy/discovery/etcd_client.py` | put() method on EtcdClient | ✓ VERIFIED | Lines 72-82 contain `def put(self, key: str, value: str | bytes) -> bool` that delegates to `self._client.put(key, value)`. |
| `tests/provisioning/test_ssh_client.py` | Unit tests for SSHClient | ✓ VERIFIED | 211 lines. 6 test classes covering connect params (D-03, D-04), stdout streaming (D-05), stderr streaming (D-07), non-zero exit, connection errors. All tests pass. |
| `tests/discovery/test_etcd_client.py` | Unit test for EtcdClient.put() delegation | ✓ VERIFIED | Lines 156-175 contain `TestEtcdClientPut` class verifying put() delegates to etcd3gw client. Test passes. |
| `tests/config/test_settings.py` | Unit tests for SSHSettings and ProvisioningSettings defaults and env overrides | ✓ VERIFIED | Lines 100-146 contain `TestDefaultSSHSettings`, `TestDefaultProvisioningSettings`, `TestEnvVarOverrideSSHUsername`, `TestEnvVarOverrideProvisioningTimeout`, `TestSSHAndProvisioningAreNotBaseSettings`. All tests pass. |
| `inference_proxy/provisioning/provisioner.py` | D-15: NodeProvisioner orchestrating full provisioning sequence | ✓ VERIFIED | 142 lines. Exports `NodeProvisioner`, `ProvisioningError`. Contains orchestration methods: `provision()`, `_run_setup()`, `_run_start_vllm()`, `_poll_health()`, `_register_node()`. Module docstring confirms concrete class (no protocol/interface). |
| `tests/provisioning/test_provisioner.py` | Unit tests for NodeProvisioner | ✓ VERIFIED | 247 lines. 9 test classes covering sequence order, step marker parsing, model extraction, health polling, node registration, setup failures. All tests pass. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `inference_proxy/provisioning/ssh_client.py` | asyncssh | import asyncssh (sole consumer) | ✓ WIRED | Line 14: `import asyncssh`. Verified sole consumer: `grep -r "import asyncssh" inference_proxy/` returns only ssh_client.py (1 match). DIP compliance confirmed. |
| `inference_proxy/provisioning/ssh_client.py` | `inference_proxy/config/settings.py` | SSHSettings constructor parameter | ✓ WIRED | Line 17: `from inference_proxy.config.settings import SSHSettings`. SSHClient.__init__ accepts `settings: SSHSettings` parameter (line 51). |
| `inference_proxy/discovery/etcd_client.py` | etcd3gw | self._client.put(key, value) | ✓ WIRED | Line 18: `from etcd3gw.client import Etcd3Client`. Line 82: `return self._client.put(key, value)`. Delegation confirmed. |
| `inference_proxy/provisioning/provisioner.py` | `inference_proxy/provisioning/ssh_client.py` | SSHClient dependency injection | ✓ WIRED | Lines 22-26: imports SSHClient, RemoteCommandError, SSHConnectionError. Line 46: `__init__` accepts `ssh_client: SSHClient` parameter. Lines 73, 92: `self._ssh_client.run_streaming()` calls. |
| `inference_proxy/provisioning/provisioner.py` | `inference_proxy/discovery/etcd_client.py` | EtcdClient.put() for registration | ✓ WIRED | Line 19: `from inference_proxy.discovery.etcd_client import EtcdClient`. Line 47: `__init__` accepts `etcd_client: EtcdClient`. Line 140: `await asyncio.to_thread(self._etcd_client.put, key, value)`. |
| `inference_proxy/provisioning/provisioner.py` | `inference_proxy/discovery/serializer.py` | node_to_etcd() for serialization | ✓ WIRED | Line 20: `from inference_proxy.discovery.serializer import node_to_etcd`. Line 138: `key, value = node_to_etcd(node, self._etcd_client.prefix)`. |
| `inference_proxy/provisioning/provisioner.py` | `inference_proxy/models/node.py` | Node and NodeStatus for registration data | ✓ WIRED | Line 21: `from inference_proxy.models.node import Node, NodeStatus`. Line 131: `node = Node(...)`. Line 134: `status=NodeStatus.HEALTHY`. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|-------------------|--------|
| `provisioner.py::_run_setup()` | stdout lines from setup.sh | `ssh_client.run_streaming()` async generator | Yes — streams real SSH output | ✓ FLOWING |
| `provisioner.py::_run_start_vllm()` | model name | Parsed from start-vllm.sh stdout via `MODEL_PATTERN` regex | Yes — extracted from remote script output, raises ProvisioningError if not found | ✓ FLOWING |
| `provisioner.py::_poll_health()` | HTTP response | `httpx.AsyncClient.get()` polling remote /health endpoint | Yes — real HTTP poll loop with timeout/interval | ✓ FLOWING |
| `provisioner.py::_register_node()` | Node object | Constructed with hostname, model (from _run_start_vllm), timestamp | Yes — Node fields populated from real data (hostname arg, extracted model, current timestamp) | ✓ FLOWING |
| `etcd_client.py::put()` | etcd write result | `self._client.put()` delegation to etcd3gw | Yes — real etcd3gw client call (mocked in tests, real in production) | ✓ FLOWING |

### Behavioral Spot-Checks

Phase 11 produces library code (SSHClient, NodeProvisioner) with no runnable entry points. Behavioral verification is covered by unit tests (46 tests, all passing). No standalone CLI/API endpoints to spot-check.

**Status:** SKIPPED (no runnable entry points; unit tests provide behavioral coverage)

### Probe Execution

No probes defined or declared for Phase 11. This is infrastructure code with unit test coverage (46 tests, 100% pass rate).

**Status:** N/A (no probes found)

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| PROV-01 | 11-01 | Gateway can SSH into a host via asyncssh using pre-configured keys | ✓ SATISFIED | SSHClient.run_streaming() connects via asyncssh with `client_keys=[str(self._key_path)]`, `known_hosts=None`. Test: `test_ssh_client.py::TestSSHClientConnectParams`. |
| PROV-02 | 11-01, 11-02 | Gateway runs setup.sh remotely (NVIDIA drivers, NFS, container toolkit) | ✓ SATISFIED | NodeProvisioner._run_setup() calls `ssh_client.run_streaming(hostname, "bash auto-vllm-container/setup.sh")`, parses step markers. Test: `test_provisioner.py::TestStepMarkerParsing`. |
| PROV-03 | 11-02 | Gateway builds and starts vLLM container on remote host with GPU auto-detection | ✓ SATISFIED | NodeProvisioner._run_start_vllm() calls `ssh_client.run_streaming(hostname, "bash auto-vllm-container/start-vllm.sh")`, extracts model name. Test: `test_provisioner.py::TestModelExtraction`. |
| PROV-04 | 11-02 | Gateway polls remote /health endpoint until vLLM is ready, then registers in etcd | ✓ SATISFIED | NodeProvisioner._poll_health() polls via httpx, then _register_node() writes to etcd via `etcd_client.put()` wrapped in `asyncio.to_thread()`. Tests: `test_provisioner.py::TestHealthPoll`, `test_provisioner.py::TestNodeRegistration`. |

**Orphaned requirements:** None. All requirements mapped to Phase 11 in REQUIREMENTS.md are satisfied.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `provisioner.py` | 139 | Ponytail comment | ℹ️ Info | `# ponytail: etcd3gw is sync, asyncio.to_thread wraps it (Pitfall 5)` — deliberate simplification documented per ponytail pattern. Not a debt marker. |

**Debt markers:** None. No TBD, FIXME, XXX, TODO, HACK, or PLACEHOLDER markers found.

**Stub patterns:** None. All methods have real implementations. No empty returns, no hardcoded empty data in production code paths.

**DIP violations:** None. Only `ssh_client.py` imports asyncssh (verified via grep). Only `etcd_client.py` imports etcd3gw. Provisioner depends on wrapper abstractions, not third-party libraries directly.

---

## Summary

**All must-haves verified. Phase goal achieved.**

Phase 11 successfully establishes SSH provisioning infrastructure:

- **SSHClient**: Sole asyncssh consumer, streams stdout/stderr line-by-line, raises typed errors
- **NodeProvisioner**: Orchestrates full sequence (setup.sh → start-vllm.sh → health poll → etcd registration)
- **Settings**: SSHSettings and ProvisioningSettings registered with correct defaults and env var support
- **EtcdClient.put()**: Added for node registration writes via asyncio.to_thread wrapper
- **Tests**: 46 tests, 100% pass rate, covering all observable truths

**Wiring verified at all levels:**
- Level 1 (Exists): All artifacts present
- Level 2 (Substantive): All artifacts contain real implementations
- Level 3 (Wired): All key links connected and imports verified
- Level 4 (Data Flows): All data sources produce real values, no stubs or static returns

**No gaps identified.** Ready to proceed to Phase 12.

---

_Verified: 2026-07-02T04:15:00Z_  
_Verifier: Claude (gsd-verifier)_
