# Phase 24: Provisioning Error Diagnostics - Pattern Map

**Mapped:** 2026-07-22
**Files analyzed:** 10 (modifications only, no new files)
**Analogs found:** 10 / 10

## File Classification

| Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---------------|------|-----------|----------------|---------------|
| `inference_proxy/models/node.py` | model | N/A | self (existing enum) | exact |
| `inference_proxy/models/admin.py` | model | N/A | self (`TaskStatusResponse` pattern) | exact |
| `inference_proxy/provisioning/provisioner.py` | service | event-driven | self (line 277-282 except block) | exact |
| `inference_proxy/services/unified_nodes.py` | service | transform | self (`_STATE_ACTIONS` + `_from_etcd`) | exact |
| `inference_proxy/api/admin.py` | controller | request-response | self (`list_nodes` + `list_provisioning_tasks`) | exact |
| `inference_proxy/static/js/dashboard.js` | component | request-response | `inference_proxy/static/js/node_detail.js` (lines 164-176) | exact |
| `inference_proxy/static/css/dashboard.css` | config | N/A | self (lines 316-320 `badge-failed`) | exact |
| `tests/models/test_node.py` | test | N/A | self (`TestNodeStatusEnumValues`) | exact |
| `tests/models/test_admin.py` | test | N/A | self (`TestAdminNodeResponse`) | exact |
| `tests/services/test_unified_nodes.py` | test | N/A | self (`TestEtcdNodeStates`) | exact |
| `tests/provisioning/test_provisioner.py` | test | N/A | self (`TestStateTracking.test_failed_state`) | exact |

## Pattern Assignments

### `inference_proxy/models/node.py` (model, enum extension)

**Analog:** self -- add one member to existing StrEnum.

**Enum pattern** (lines 20-27):
```python
class NodeStatus(StrEnum):
    """Status of a vLLM inference node."""

    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DRAINING = "draining"
    PROVISIONING = "provisioning"
    UNKNOWN = "unknown"
```

**Change:** Add `FAILED = "failed"` after `PROVISIONING`.

---

### `inference_proxy/models/admin.py` (model, add optional fields)

**Analog:** `TaskStatusResponse` in same file (lines 91-101) -- already has the exact same field pattern.

**Existing pattern to copy** (lines 91-101):
```python
class TaskStatusResponse(BaseModel):
    """Provisioning task status from etcd."""

    model_config = ConfigDict(frozen=True)

    hostname: str
    current_step: str
    started_at: datetime
    updated_at: datetime
    failed_step: str | None = None
    error: str | None = None
```

**Change:** Add `failed_step: str | None = None` and `error: str | None = None` to `AdminNodeResponse` (after line 39, before the closing of the class). Follows exact same type annotation pattern as `TaskStatusResponse`.

---

### `inference_proxy/provisioning/provisioner.py` (service, fix except block)

**Analog:** self -- the teardown except block (lines 429-434) already does the correct pattern for `failed_step`.

**Current bug** (lines 277-282):
```python
        except (RemoteCommandError, SSHConnectionError, ProvisioningError) as exc:
            await self._update_state(
                hostname, ProvisioningStep.FAILED,
                failed_step=type(exc).__name__, error=str(exc),
            )
            raise ProvisioningError(str(exc)) from exc
```

**Correct pattern from teardown** (lines 429-434):
```python
        except (RemoteCommandError, SSHConnectionError) as exc:
            await self._update_state(
                hostname, ProvisioningStep.FAILED,
                failed_step="teardown", error=str(exc),
            )
            raise ProvisioningError(str(exc)) from exc
```

**Change:** In `provision()`, track current step in a local variable before each `_update_state` / await. Use that variable as `failed_step` in the except block instead of `type(exc).__name__`.

**Step tracking pattern** -- follow the existing `_update_state` calls (lines 266-276) to derive variable assignments:
```python
        try:
            current_step = "uploading_scripts"
            await self._update_state(hostname, ProvisioningStep.UPLOADING_SCRIPTS)
            await self._upload_scripts(hostname)
            current_step = "setup"
            await self._run_setup(hostname)
            current_step = "starting_vllm"
            await self._update_state(hostname, ProvisioningStep.STARTING_VLLM)
            # ... etc ...
        except (RemoteCommandError, SSHConnectionError, ProvisioningError) as exc:
            await self._update_state(
                hostname, ProvisioningStep.FAILED,
                failed_step=current_step, error=str(exc),
            )
```

Additionally, update the node entry in etcd to `FAILED` status in the except block so the registry/watcher picks it up (see Research open question 2).

---

### `inference_proxy/services/unified_nodes.py` (service, state/actions mapping + error merge)

**Analog:** self -- `_STATE_ACTIONS` dict (lines 21-27) and `_from_etcd` method (lines 76-96).

**State-actions dispatch pattern** (lines 21-27):
```python
_STATE_ACTIONS: dict[str, list[str]] = {
    "available": ["setup"],
    "healthy": ["teardown"],
    "unhealthy": ["teardown", "retry"],
    "provisioning": ["cancel"],
    "draining": ["force_teardown"],
}
```

**Change:** Add `"failed": ["setup", "teardown"]` entry.

**Node response construction pattern** (lines 76-96):
```python
    def _from_etcd(
        self,
        node: Node,
        host: QUADSHost | None = None,
    ) -> AdminNodeResponse:
        state = node.status.value
        breaker = self._cb_registry.get(node.node_id)
        return AdminNodeResponse(
            node_id=node.node_id,
            endpoint=node.endpoint,
            model=node.model,
            status=node.status.value,
            active_connections=self._tracker.get(node.node_id),
            circuit_breaker_state=breaker.state if breaker else "closed",
            state=state,
            actions=list(_STATE_ACTIONS.get(state, [])),
            gpu_vendor=host.gpu_vendor if host else None,
            gpu_model=host.gpu_model if host else None,
            gpu_count=host.gpu_count if host else None,
            managed=node.managed,
        )
```

**Change:** Accept an optional `task_map: dict[str, TaskStatusResponse]` parameter and populate `failed_step` and `error` from it when `state == "failed"`. The `get_unified_nodes` method signature changes to accept this map. The admin endpoint `list_nodes` fetches tasks and passes the map.

**Admin endpoint pattern for fetching tasks** (`inference_proxy/api/admin.py` lines 146-158):
```python
@admin_router.get("/provisioning/tasks")
async def list_provisioning_tasks(
    provisioner: NodeProvisioner = Depends(get_provisioner),
) -> list[TaskStatusResponse]:
    """Return status of all provisioning/teardown operations from etcd."""
    results = await provisioner.list_tasks_raw()
    tasks: list[TaskStatusResponse] = []
    for value_bytes, _metadata in results:
        try:
            data = json.loads(value_bytes)
            tasks.append(TaskStatusResponse(**data))
        except (json.JSONDecodeError, ValidationError) as exc:
            logger.warning("task_parse_failed", raw=value_bytes[:200], error=str(exc))
    return tasks
```

**Change in `list_nodes`** (`inference_proxy/api/admin.py` lines 71-76): fetch provisioning tasks, build a `dict[str, TaskStatusResponse]` keyed by hostname, pass it to `get_unified_nodes()`.

---

### `inference_proxy/static/js/dashboard.js` (component, expandable sub-row)

**Analog:** `inference_proxy/static/js/node_detail.js` lines 164-176 -- error rendering pattern.

**Error rendering pattern from node_detail.js** (lines 164-176):
```javascript
        if (task.failed_step) {
          var fb = document.createElement("span"); fb.className = "badge badge-failed"; fb.textContent = "failed at " + task.failed_step; tdStatus.appendChild(fb);
        } else if (task.current_step === "complete" || task.current_step === "teardown_complete") {
          var db = document.createElement("span"); db.className = "badge badge-complete"; db.textContent = task.current_step; tdStatus.appendChild(db);
        } else {
          var pb = document.createElement("span"); pb.className = "badge badge-in-progress"; pb.textContent = "in progress"; tdStatus.appendChild(pb);
        }

        var tdErr = document.createElement("td");
        if (task.error) { tdErr.className = "error-text"; tdErr.textContent = task.error; }
        else { tdErr.textContent = "—"; }
```

**Badge creation pattern from dashboard.js** (lines 206-209):
```javascript
        const tdState = document.createElement("td");
        const stateBadge = document.createElement("span");
        stateBadge.className = `badge badge-${node.state}`;
        stateBadge.textContent = node.state;
        tdState.appendChild(stateBadge);
```

**Expand/collapse pattern from dashboard.js** (lines 272-283 -- manual setup toggle):
```javascript
  const toggle = document.getElementById("manual-setup-toggle");
  const setupRow = document.getElementById("manual-setup-row");
  toggle.addEventListener("click", function (e) {
    e.preventDefault();
    if (setupRow.style.display === "none") {
      setupRow.style.display = "flex";
      toggle.textContent = "- Manual setup";
    } else {
      setupRow.style.display = "none";
      toggle.textContent = "+ Manual setup";
    }
  });
```

**Change:** After `tbody.appendChild(tr)` (line 245), add sub-row logic: if `node.state === "failed"` and `node.failed_step || node.error`, create a hidden `<tr>` with `<td colSpan=7>` containing badge + `<pre>` error text. Make the state badge clickable to toggle `display: none / table-row`. Add `cursor: pointer`, `role="button"`, `tabindex="0"`, `aria-expanded` for accessibility.

---

### `inference_proxy/static/css/dashboard.css` (config, badge-failed already exists)

**Analog:** self -- lines 316-320.

**Existing badge-failed** (lines 316-320):
```css
.badge-unhealthy,
.badge-open,
.badge-failed {
  background: var(--danger-bg);
  color: var(--danger);
}
```

**Change:** Minimal. May need to add `.error-detail` and `.error-message` styles for the sub-row content, plus `cursor: pointer` on clickable failed badges. Follow existing `.error-text` pattern (line 464):
```css
.error-text { color: var(--danger); font-size: 0.8125rem; }
```

---

### `tests/models/test_node.py` (test, enum member assertion)

**Analog:** self -- `TestNodeStatusEnumValues` (lines 13-20).

**Pattern** (lines 13-20):
```python
class TestNodeStatusEnumValues:
    def test_node_status_enum_values(self) -> None:
        assert NodeStatus.HEALTHY == "healthy"
        assert NodeStatus.UNHEALTHY == "unhealthy"
        assert NodeStatus.DRAINING == "draining"
        assert NodeStatus.UNKNOWN == "unknown"
        assert NodeStatus.PROVISIONING == "provisioning"
        assert len(NodeStatus) == 5
```

**Change:** Add `assert NodeStatus.FAILED == "failed"` and update `len(NodeStatus)` to 6.

---

### `tests/models/test_admin.py` (test, model field assertion)

**Analog:** self -- `TestAdminNodeResponse.test_create_with_valid_fields` (lines 21-37).

**Pattern** (lines 21-37):
```python
    def test_create_with_valid_fields(self) -> None:
        """AdminNodeResponse accepts all six fields."""
        response = AdminNodeResponse(
            node_id="node-1",
            endpoint="10.0.1.100:8000",
            model="llama-3",
            status="healthy",
            active_connections=2,
            circuit_breaker_state="closed",
        )
        assert response.node_id == "node-1"
```

**Change:** Add a test that creates `AdminNodeResponse` with `failed_step="uploading_scripts"` and `error="connection refused"` and asserts both fields. Also test defaults are `None`.

---

### `tests/services/test_unified_nodes.py` (test, state/actions assertions)

**Analog:** self -- `TestEtcdNodeStates` class (lines 93-137), e.g. `test_provisioning_state_and_actions`.

**Pattern** (lines 118-127):
```python
    def test_provisioning_state_and_actions(self) -> None:
        registry = NodeRegistry()
        registry.add(_node("gpu01", status=NodeStatus.PROVISIONING))
        poller = _poller(hosts=[_host("gpu01")], available=["gpu01"])
        svc = _service(registry=registry, poller=poller)

        n = svc.get_unified_nodes()[0]
        assert n.state == "provisioning"
        assert n.actions == ["cancel"]
```

**Change:** Add `test_failed_state_and_actions` following this exact pattern with `NodeStatus.FAILED` and `assert n.actions == ["setup", "teardown"]`. Add test for error field population from task map.

---

### `tests/provisioning/test_provisioner.py` (test, failed_step verification)

**Analog:** self -- `TestStateTracking.test_failed_state` (lines 501-536).

**Pattern** (lines 501-536):
```python
    @pytest.mark.asyncio
    async def test_failed_state(self) -> None:
        """On failure, last state write has current_step=failed with details."""
        etcd = MagicMock()
        ssh = MagicMock()

        async def mock_streaming(host: str, command: str):
            if "setup.sh" in command:
                raise RemoteCommandError("host1", "bash setup.sh", 1)
                yield  # pragma: no cover

        ssh.run_streaming = mock_streaming
        ssh.upload = AsyncMock()
        etcd.prefix = "/nodes/"
        etcd.put = MagicMock(return_value=True)

        # ... provision call ...

        last_state = state_writes[-1]
        assert last_state["current_step"] == "failed"
        assert last_state["failed_step"] is not None
        assert last_state["error"] is not None
```

**Change:** Strengthen assertion from `is not None` to checking the actual step name value. When setup.sh fails, `failed_step` should be a step name like `"uploading_scripts"` or the setup step marker, NOT `"RemoteCommandError"`. Add a dedicated test that verifies this.

---

## Shared Patterns

### Frozen Pydantic Models
**Source:** All models in `inference_proxy/models/`
**Apply to:** `AdminNodeResponse` changes
```python
model_config = ConfigDict(frozen=True)
# Optional fields use: field_name: type | None = None
```

### StrEnum Members
**Source:** `inference_proxy/models/node.py` lines 20-27, `inference_proxy/provisioning/state.py` lines 19-40
**Apply to:** `NodeStatus` enum
```python
class NodeStatus(StrEnum):
    MEMBER_NAME = "member_value"  # lowercase value matches the string
```

### State-Actions Dispatch
**Source:** `inference_proxy/services/unified_nodes.py` lines 21-27
**Apply to:** Adding "failed" state
```python
_STATE_ACTIONS: dict[str, list[str]] = {
    "state_name": ["action1", "action2"],
}
```

### Test Structure (model tests)
**Source:** `tests/models/test_node.py`, `tests/models/test_admin.py`
**Apply to:** New test assertions
```python
class TestFeatureName:
    def test_specific_behavior(self) -> None:
        # Arrange, Act, Assert -- no fixtures, direct construction
        assert result == expected
```

### Test Structure (async provisioner tests)
**Source:** `tests/provisioning/test_provisioner.py`
**Apply to:** New `failed_step` verification test
```python
class TestClassName:
    @pytest.mark.asyncio
    async def test_name(self) -> None:
        # MagicMock dependencies, patch asyncio.to_thread
        with patch("...asyncio.to_thread", new_callable=AsyncMock) as mock_tt:
            mock_tt.return_value = True
            # ... exercise ...
        # Assert on captured state writes
```

## No Analog Found

No files without analogs. Every modification target has an exact self-analog or sibling-file analog.

## Metadata

**Analog search scope:** `inference_proxy/`, `tests/`
**Files scanned:** 10 modification targets + 1 cross-reference (`node_detail.js`)
**Pattern extraction date:** 2026-07-22
