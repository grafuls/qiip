---
phase: 17-unified-node-list-and-admin-api
verified: 2026-07-16T18:42:00Z
status: passed
score: 9/9 must-haves verified
overrides_applied: 0
re_verification: false
---

# Phase 17: Unified Node List and Admin API Verification Report

**Phase Goal:** Operators see a single merged view of all systems with state-aware inline actions
**Verified:** 2026-07-16T18:42:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | GET /admin/nodes returns a unified list merging QUADS available hosts with etcd-registered nodes by hostname (NODES-01) | ✓ VERIFIED | UnifiedNodeService.get_unified_nodes() merges poller.hosts with registry.get_all() by canonical_hostname. Test: test_merged_list_with_quads passes. |
| 2 | Each node includes computed state (available, provisioned, healthy, unhealthy) and an actions list (NODES-02) | ✓ VERIFIED | AdminNodeResponse extended with state, actions, gpu_vendor, gpu_model, gpu_count fields. State-to-actions mapping via _STATE_ACTIONS dict. Test: test_each_node_has_state_and_actions passes. |
| 3 | Setup on an available node triggers provisioning, teardown on healthy, teardown+retry on unhealthy (NODES-03) | ✓ VERIFIED | Actions list per state: available→[setup], healthy→[teardown], unhealthy→[teardown,retry], provisioning→[cancel], draining→[force_teardown]. Endpoints wire to provisioner.provision() and provisioner.teardown(). Tests: test_*_state_and_actions pass. |
| 4 | POST /admin/nodes/setup returns 409 when hostname is already in the pending_hosts set (NODES-04) | ✓ VERIFIED | Dedup guard at line 80 in admin.py checks `if hostname in pending_hosts: raise HTTPException(status_code=409)`. Test: test_returns_409_for_pending_hostname passes. |
| 5 | POST /admin/nodes/setup calls QUADSClient.get_available() live, not poller cache; returns 503 if QUADS unreachable (NODES-05) | ✓ VERIFIED | Line 89 calls `await quads_client.get_available()`, raises 503 on QUADSConnectionError (line 91-93), 400 if hostname not available (line 94-98). Tests: test_returns_503_on_quads_connection_error, test_returns_400_for_unavailable_host pass. |
| 6 | Nodes in etcd but absent from QUADS host list are excluded from unified list (D-03) | ✓ VERIFIED | UnifiedNodeService.get_unified_nodes() only iterates quads_map.items(), never adds etcd-only nodes. Test: test_etcd_node_not_in_quads_excluded passes. |
| 7 | Etcd status wins when a host is in both sources (D-05) | ✓ VERIFIED | Line 62-64: `if etcd_node is not None: result.append(self._from_etcd(etcd_node, host))` — etcd node data takes precedence, QUADS only adds GPU fields. Test: test_healthy_state_and_actions passes. |
| 8 | Actions list per state: available→[setup], healthy→[teardown], unhealthy→[teardown,retry], provisioning→[cancel], draining→[force_teardown] (D-07) | ✓ VERIFIED | _STATE_ACTIONS dict at line 21-27 defines exact mapping. Tests: TestEtcdNodeStates class covers all states. |
| 9 | Pending set is module-level in api/admin.py, cleaned up on task completion/failure (D-08) | ✓ VERIFIED | `pending_hosts: set[str] = set()` at line 44. Added at line 100, discarded in finally block at line 106, also discarded on fire_background failure at line 111. |

**Score:** 9/9 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `inference_proxy/services/unified_nodes.py` | UnifiedNodeService with get_unified_nodes() merge logic | ✓ VERIFIED | Exports UnifiedNodeService class, merge logic in get_unified_nodes() lines 45-69 |
| `inference_proxy/models/admin.py` | Extended AdminNodeResponse with state, actions, gpu_vendor, gpu_model, gpu_count fields | ✓ VERIFIED | Fields added at lines 31-35, all with correct types |
| `inference_proxy/api/admin.py` | Updated GET /admin/nodes using UnifiedNodeService, setup with dedup guard and QUADS re-validation | ✓ VERIFIED | list_nodes() at line 47-52 uses UnifiedNodeService. setup_node() at line 67-113 has dedup guard and QUADS re-validation |
| `inference_proxy/config/dependencies.py` | get_unified_node_service DI provider | ✓ VERIFIED | Exported at line 108-115, wires registry, poller, cb_registry, tracker |
| `tests/services/test_unified_nodes.py` | Unit tests for UnifiedNodeService merge, state computation, filtering | ✓ VERIFIED | 14 tests covering all merge scenarios, state mapping, filtering rules |
| `tests/api/test_admin.py` | Updated admin endpoint tests: unified list, dedup guard, QUADS re-validation | ✓ VERIFIED | TestUnifiedNodeList (3 tests), TestSetupDedupGuard (2 tests), TestSetupQuadsRevalidation (4 tests) all pass |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| inference_proxy/services/unified_nodes.py | inference_proxy/quads/poller.py | QUADSPoller.hosts injected for merge | ✓ WIRED | Constructor accepts QUADSPoller at line 36, accessed at line 56: `for hostname, host in quads_map.items()` |
| inference_proxy/services/unified_nodes.py | inference_proxy/discovery/registry.py | NodeRegistry.get_all() for etcd nodes | ✓ WIRED | Constructor accepts NodeRegistry at line 34, called at line 47: `self._registry.get_all()` |
| inference_proxy/api/admin.py | inference_proxy/quads/client.py | QUADSClient injected via Depends for setup re-validation | ✓ WIRED | Depends(get_quads_client) at line 71, called at line 89: `await quads_client.get_available()` |
| inference_proxy/api/admin.py | inference_proxy/services/unified_nodes.py | UnifiedNodeService injected via Depends | ✓ WIRED | Depends(get_unified_node_service) at line 49, called at line 52: `return service.get_unified_nodes()` |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|-------------------|--------|
| inference_proxy/services/unified_nodes.py | etcd_map | registry.get_all() | Real nodes from NodeRegistry | ✓ FLOWING |
| inference_proxy/services/unified_nodes.py | quads_map | poller.hosts | Real QUADSHost list from poller | ✓ FLOWING |
| inference_proxy/api/admin.py | available | quads_client.get_available() | Live QUADS API call (not cache) | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| UnifiedNodeService returns merged list | `uv run pytest tests/services/test_unified_nodes.py::TestAvailableOnly::test_available_host_state_and_actions -v` | PASSED | ✓ PASS |
| GET /admin/nodes uses UnifiedNodeService | `uv run pytest tests/api/test_admin.py::TestUnifiedNodeList::test_merged_list_with_quads -v` | PASSED | ✓ PASS |
| Setup dedup guard returns 409 | `uv run pytest tests/api/test_admin.py::TestSetupDedupGuard::test_returns_409_for_pending_hostname -v` | PASSED | ✓ PASS |
| Setup QUADS re-validation returns 503 on error | `uv run pytest tests/api/test_admin.py::TestSetupQuadsRevalidation::test_returns_503_on_quads_connection_error -v` | PASSED | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| NODES-01 | 17-01 | Admin API returns a unified node list merging QUADS available hosts with etcd-registered nodes by hostname | ✓ SATISFIED | UnifiedNodeService.get_unified_nodes() merges by hostname. Test: test_merged_list_with_quads |
| NODES-02 | 17-01 | Each node in the unified list shows its state (available, provisioned, healthy, unhealthy) with available actions | ✓ SATISFIED | AdminNodeResponse has state and actions fields. Test: test_each_node_has_state_and_actions |
| NODES-03 | 17-01 | User can trigger Setup on an available node, Teardown on a healthy node, and Teardown+Retry on an unhealthy node via inline actions | ✓ SATISFIED | Actions list provides ["setup"], ["teardown"], ["teardown", "retry"] per state. Endpoints wire to provisioner. Tests: test_*_state_and_actions |
| NODES-04 | 17-01 | Gateway prevents duplicate setup requests for the same host with a pending_hosts guard (409 on duplicate) | ✓ SATISFIED | pending_hosts set with dedup check at line 80. Test: test_returns_409_for_pending_hostname |
| NODES-05 | 17-01 | Gateway re-validates host availability against QUADS at setup time, not from the polling cache | ✓ SATISFIED | Line 89 calls QUADSClient.get_available() live. Tests: test_returns_503_on_quads_connection_error, test_returns_400_for_unavailable_host |

### Anti-Patterns Found

No anti-patterns detected. All modified files are clean:
- No TBD/FIXME/XXX debt markers
- No TODO/HACK/PLACEHOLDER comments
- No empty stub implementations
- No hardcoded empty data
- No console.log-only handlers

### Test Results

**Unit tests:** 14/14 passed in tests/services/test_unified_nodes.py
**Integration tests:** 29/29 passed in tests/api/test_admin.py
**Full suite:** 399/399 passed (no regressions)

Test coverage includes:
- All state-to-actions mappings (available, healthy, unhealthy, provisioning, draining)
- QUADS-only hosts, etcd-only nodes, merged hosts
- Filtering rules (D-03: etcd-without-QUADS excluded)
- Graceful degradation (poller=None returns etcd-only)
- Dedup guard (409 for pending hostname)
- QUADS re-validation (503 on connection error, 400 for unavailable)
- Pending set cleanup on completion/failure
- Active connections and circuit breaker state enrichment

---

_Verified: 2026-07-16T18:42:00Z_
_Verifier: Claude (gsd-verifier)_
