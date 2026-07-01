---
phase: 11-ssh-provisioning
plan: 01
subsystem: provisioning
tags: [asyncssh, ssh, etcd, pydantic-settings, streaming]

# Dependency graph
requires:
  - phase: 02-service-discovery
    provides: EtcdClient wrapper, etcd3gw integration
  - phase: 01-foundation
    provides: Settings/pydantic-settings pattern, structlog logging
provides:
  - SSHClient wrapper (sole asyncssh consumer, DIP)
  - SSHConnectionError and RemoteCommandError exception types
  - SSHSettings and ProvisioningSettings on root Settings
  - EtcdClient.put() for node registration
affects: [11-02-provisioner, 11-03-admin-api]

# Tech tracking
tech-stack:
  added: [asyncssh]
  patterns: [async-streaming-generator, thin-wrapper-dip]

key-files:
  created:
    - inference_proxy/provisioning/__init__.py
    - inference_proxy/provisioning/ssh_client.py
    - tests/provisioning/__init__.py
    - tests/provisioning/test_ssh_client.py
  modified:
    - inference_proxy/config/settings.py
    - inference_proxy/discovery/etcd_client.py
    - tests/config/test_settings.py
    - tests/discovery/test_etcd_client.py
    - pyproject.toml
    - uv.lock

key-decisions:
  - "Extract SSHSettings fields into private attrs (not store settings object) per EtcdClient pattern"
  - "Read stderr in bulk after stdout exhausted to avoid interleave deadlock"

patterns-established:
  - "Async streaming generator: run_streaming yields (stream, line) tuples for real-time output"
  - "Typed exception hierarchy: SSHConnectionError/RemoteCommandError with structured attributes"

requirements-completed: [PROV-01, PROV-02]

# Metrics
duration: 5min
completed: 2026-07-01
---

# Phase 11 Plan 01: SSH Infrastructure Summary

**SSHClient wrapper around asyncssh with streaming stdout/stderr, typed errors, settings sub-models, and EtcdClient.put() for node registration**

## Performance

- **Duration:** 5 min
- **Started:** 2026-07-01T21:08:53Z
- **Completed:** 2026-07-01T21:14:21Z
- **Tasks:** 2
- **Files modified:** 10

## Accomplishments
- SSHClient as sole asyncssh consumer (DIP) with async streaming generator
- SSHSettings (key_path, username, connect_timeout) and ProvisioningSettings (health_poll_timeout, interval, vllm_port) on root Settings
- EtcdClient.put() delegating to etcd3gw for node registration writes
- 17 new tests (37 total for plan scope, 282 full suite)

## Task Commits

Each task was committed atomically:

1. **Task 1: Settings, EtcdClient.put(), and their tests**
   - `24d3f50` test(11-01): add failing tests for SSHSettings, ProvisioningSettings, EtcdClient.put()
   - `74143f8` feat(11-01): add SSHSettings, ProvisioningSettings, and EtcdClient.put()
2. **Task 2: SSHClient wrapper with streaming and tests**
   - `da0ec93` test(11-01): add failing tests for SSHClient wrapper
   - `a0ede3d` feat(11-01): implement SSHClient wrapper with streaming and error handling

**Dependency commit:** `84efb23` chore(11-01): add asyncssh dependency for SSH provisioning

_TDD: Each task followed RED (failing tests) then GREEN (implementation) cycle._

## Files Created/Modified
- `inference_proxy/provisioning/__init__.py` - Package marker (D-13)
- `inference_proxy/provisioning/ssh_client.py` - SSHClient, SSHConnectionError, RemoteCommandError (D-14)
- `inference_proxy/config/settings.py` - SSHSettings, ProvisioningSettings sub-models (D-16, D-17)
- `inference_proxy/discovery/etcd_client.py` - put() method for node registration
- `tests/provisioning/test_ssh_client.py` - 6 tests covering connect params, streaming, errors
- `tests/config/test_settings.py` - 11 new tests for SSH/provisioning settings defaults and env overrides
- `tests/discovery/test_etcd_client.py` - 1 new test for put() delegation
- `pyproject.toml` - asyncssh>=2.20,<3.0 dependency
- `uv.lock` - lockfile updated

## Decisions Made
- Extracted SSHSettings fields into private attributes (_username, _key_path, _connect_timeout) rather than storing the settings object, matching EtcdClient's constructor pattern
- Read stderr in bulk after stdout loop completes (process.stderr.read()) to avoid interleave deadlock -- stdout is real-time, stderr is deferred

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Mock setup for asyncssh required real exception classes (PermissionDenied, DisconnectError) set on the mock module since Python's `except` clause validates against BaseException -- resolved by using `type()` to create proper exception subclasses on the mock

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- SSHClient ready for NodeProvisioner (Plan 02) to orchestrate setup/container/health-poll/register flow
- EtcdClient.put() ready for node registration after health poll succeeds
- Settings ready for env var configuration of SSH and provisioning parameters

## TDD Gate Compliance

- RED gate: `24d3f50` (test) and `da0ec93` (test) commits exist
- GREEN gate: `74143f8` (feat) and `a0ede3d` (feat) commits exist after respective RED commits

---
*Phase: 11-ssh-provisioning*
*Completed: 2026-07-01*
