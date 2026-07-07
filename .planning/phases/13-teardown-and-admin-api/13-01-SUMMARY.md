---
phase: 13-teardown-and-admin-api
plan: 01
status: complete
started: 2026-07-07
completed: 2026-07-07
---

## Summary

Implemented the teardown lifecycle on NodeProvisioner: extended ProvisioningStep enum with DRAINING, STOPPING_CONTAINER, DEREGISTERING, and TEARDOWN_COMPLETE steps; added drain_timeout (30s default) to ProvisioningSettings; added EtcdClient.delete() and parameterized get_prefix(); built teardown() with graceful drain-wait, force mode, SSH container stop, and etcd deregistration.

## Self-Check: PASSED

- All 325 tests pass (12 new teardown tests)
- Existing provisioner tests unchanged and passing
- Type checking: Coroutine import for fire_background typed correctly

## Key Changes

### key-files.created

- `_derive_container_name()` module-level function in provisioner.py
- `fire_background()` method on NodeProvisioner
- `_drain_wait()` async method on NodeProvisioner
- `teardown()` async method on NodeProvisioner

### key-files.modified

- `inference_proxy/provisioning/state.py` — 4 new enum members
- `inference_proxy/config/settings.py` — drain_timeout field
- `inference_proxy/discovery/etcd_client.py` — delete() method, parameterized get_prefix()
- `inference_proxy/provisioning/provisioner.py` — teardown lifecycle, DI for registry/tracker
- `tests/provisioning/test_provisioner.py` — 12 new tests across 6 test classes
- `tests/discovery/test_etcd_client.py` — delete and custom prefix tests

## Deviations

None.

## Issues

None.
