# Phase 28: Model Selection - Pattern Map

**Mapped:** 2026-07-26
**Files analyzed:** 6 (3 source, 3 test -- all modifications)
**Analogs found:** 6 / 6

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `inference_proxy/models/admin.py` | model | request-response | self (SetupRequest.managed field) | exact |
| `inference_proxy/provisioning/provisioner.py` | service | request-response | self (provision managed param) | exact |
| `inference_proxy/api/admin.py` | controller | request-response | self (setup_node managed passthrough) | exact |
| `tests/models/test_admin.py` | test | unit | self (existing SetupRequest tests) | exact |
| `tests/provisioning/test_provisioner.py` | test | unit | self (TestModelExtraction class) | exact |
| `tests/api/test_admin.py` | test | integration | self (setup endpoint tests) | exact |

## Pattern Assignments

### `inference_proxy/models/admin.py` (model, request-response)

**Analog:** self -- `SetupRequest.managed` field at line 66

**Existing field pattern** (lines 60-76):
```python
class SetupRequest(BaseModel):
    """Request body for POST /admin/nodes/setup."""

    model_config = ConfigDict(frozen=True)

    hostname: str
    managed: bool = True

    @field_validator("hostname")
    @classmethod
    def validate_hostname(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > 253:
            raise ValueError("hostname must be 1-253 characters")
        if not re.fullmatch(r"[a-zA-Z0-9]([a-zA-Z0-9\-\.]*[a-zA-Z0-9])?", v):
            raise ValueError("hostname contains invalid characters")
        return v
```

**What to copy:** Add `model: str | None = None` after `managed: bool = True` (line 66). Same pattern as `managed` -- optional field with a default. Pydantic `max_length` via `Field(max_length=256)` for DoS protection per RESEARCH.md.

---

### `inference_proxy/provisioning/provisioner.py` (service, request-response)

**Analog:** self -- `provision()` managed kwarg at line 229, `_run_start_vllm()` at line 365

**provision() signature pattern** (line 229):
```python
async def provision(self, hostname: str, *, managed: bool = True) -> None:
```

**What to copy:** Add `model: str | None = None` after `managed` in kwargs. Thread to `_run_start_vllm` call at line 286:
```python
model = await self._run_start_vllm(hostname)
# becomes:
model_name = await self._run_start_vllm(hostname, model=model)
```

**_run_start_vllm command construction** (lines 365-383):
```python
async def _run_start_vllm(self, hostname: str) -> str:
    """Run start-vllm.sh and extract model name from stdout."""
    model: str | None = None
    async for stream, line in self._ssh_client.run_streaming(
        hostname, "bash auto-vllm/start-vllm.sh"
    ):
```

**What to copy:** Add `model: str | None = None` kwarg. Before `run_streaming`, conditionally prepend env var using `shlex.quote()`:
```python
command = "bash auto-vllm/start-vllm.sh"
if model:
    command = f"VLLM_MODEL={shlex.quote(model)} {command}"
```

---

### `inference_proxy/api/admin.py` (controller, request-response)

**Analog:** self -- `setup_node()` provisioner call at line 153

**Existing call pattern** (line 153):
```python
await provisioner.provision(hostname, managed=body.managed)
```

**What to copy:** Add `model=body.model` kwarg:
```python
await provisioner.provision(hostname, managed=body.managed, model=body.model)
```

---

### `tests/models/test_admin.py` (test, unit)

**Analog:** self -- no existing SetupRequest tests in this file (tests cover AdminNodeResponse/AdminMetricsResponse only)

**Test class pattern** (lines 19-76):
```python
class TestAdminNodeResponse:
    """AdminNodeResponse model validation and behavior."""

    def test_create_with_valid_fields(self) -> None:
        """AdminNodeResponse accepts all six fields."""
        response = AdminNodeResponse(...)
        assert response.node_id == "node-1"

    def test_frozen_rejects_mutation(self) -> None:
        """AdminNodeResponse is immutable -- assigning to a field raises ValidationError."""
        response = AdminNodeResponse(...)
        with pytest.raises(ValidationError):
            response.status = "unhealthy"  # type: ignore[misc]
```

**What to copy:** Add `TestSetupRequest` class following same pattern -- test default None, test explicit value, test frozen.

---

### `tests/provisioning/test_provisioner.py` (test, unit)

**Analog:** self -- `TestModelExtraction` at line 198

**Mock streaming pattern** (lines 200-217):
```python
class TestModelExtraction:
    @pytest.mark.asyncio
    async def test_extracts_model_name(self) -> None:
        ssh = MagicMock()

        async def mock_streaming(host: str, command: str):
            for item in [
                ("stdout", "Starting container..."),
                ("stdout", "# Model:              Qwen/Qwen2.5-72B-Instruct"),
                ("stdout", "Container started"),
            ]:
                yield item

        ssh.run_streaming = mock_streaming
        provisioner = _make_provisioner(ssh_client=ssh)

        model = await provisioner._run_start_vllm("host1")
        assert model == "Qwen/Qwen2.5-72B-Instruct"
```

**What to copy:** Add tests that call `_run_start_vllm("host1", model="some/model")` and assert `mock_streaming` received a command containing `VLLM_MODEL=`. Also test omission case (no model -> command is plain `bash auto-vllm/start-vllm.sh`). Capture the command arg in mock_streaming to verify.

---

### `tests/api/test_admin.py` (test, integration)

**Analog:** self -- existing setup endpoint tests using `TestClient`

**Test fixture/client pattern** (lines 47-59):
```python
def _make_node(
    node_id: str = "node-1",
    endpoint: str = "10.0.1.100:8000",
    status: NodeStatus = NodeStatus.HEALTHY,
    model: str = "llama-3",
) -> Node:
    return Node(node_id=node_id, endpoint=endpoint, status=status, model=model)
```

**What to copy:** POST to `/admin/nodes/setup` with `{"hostname": "host1", "model": "org/model"}` and verify provisioner.provision called with `model="org/model"`.

---

## Shared Patterns

### Shell Safety
**Source:** Python stdlib `shlex.quote()`
**Apply to:** `inference_proxy/provisioning/provisioner.py` `_run_start_vllm()`
```python
import shlex
# ...
command = f"VLLM_MODEL={shlex.quote(model)} {command}"
```

### Optional Kwarg Threading
**Source:** `provisioner.py` line 229 (`managed: bool = True` pattern)
**Apply to:** `provision()` and `_run_start_vllm()` signatures
```python
async def provision(self, hostname: str, *, managed: bool = True, model: str | None = None) -> None:
```

### Pydantic Optional Field
**Source:** `models/admin.py` line 66 (`managed: bool = True`)
**Apply to:** `SetupRequest.model` field
```python
model: str | None = Field(default=None, max_length=256)
```

## No Analog Found

None -- all changes follow existing patterns in the same files.

## Metadata

**Analog search scope:** `inference_proxy/`, `tests/`
**Files scanned:** 6 (targeted -- all files are self-analogs)
**Pattern extraction date:** 2026-07-26
