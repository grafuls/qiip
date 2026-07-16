---
phase: 15-quads-client-and-models
reviewed: 2026-07-16T00:00:00Z
depth: standard
files_reviewed: 8
files_reviewed_list:
  - inference_proxy/models/quads.py
  - inference_proxy/quads/client.py
  - inference_proxy/config/settings.py
  - inference_proxy/config/dependencies.py
  - inference_proxy/main.py
  - tests/models/test_quads.py
  - tests/quads/test_client.py
  - tests/config/test_settings.py
findings:
  critical: 2
  warning: 2
  info: 0
  total: 4
status: issues_found
---

# Phase 15: Code Review Report

**Reviewed:** 2026-07-16
**Depth:** standard
**Files Reviewed:** 8
**Status:** issues_found

## Summary

The QUADS client and model implementation is clean and well-structured overall. The domain model is appropriately frozen, the client correctly filters broken/retired hosts and normalizes hostnames, and settings integration follows the established project pattern. However, the error-handling contract stated in the docstring and design decision D-09 ("all API errors surface as QUADSConnectionError") is violated by two unguarded exception paths in `QUADSClient`. These are correctness bugs that will cause unhandled exceptions to escape into callers instead of the documented error type.

## Critical Issues

### CR-01: `_get()` does not catch `json.JSONDecodeError` -- violates D-09 contract

**File:** `inference_proxy/quads/client.py:80-88`
**Issue:** The `_get` method catches only `httpx.HTTPError`, but `resp.json()` on line 88 raises `json.JSONDecodeError` when the QUADS API returns a non-JSON body (e.g., an HTML error page behind a reverse proxy, or a truncated response). `json.JSONDecodeError` is **not** a subclass of `httpx.HTTPError` (verified empirically), so it escapes the catch block. This violates the stated D-09 contract and will surface as an unhandled `JSONDecodeError` to callers that expect only `QUADSConnectionError`.
**Fix:**
```python
async def _get(self, path: str) -> Any:
    """GET a JSON endpoint, wrapping errors in QUADSConnectionError."""
    url = f"{self._base_url}{path}"
    try:
        resp = await self._client.get(url)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError as exc:
        raise QUADSConnectionError(str(exc)) from exc
    except ValueError as exc:
        # json.JSONDecodeError is a subclass of ValueError
        raise QUADSConnectionError(f"Invalid JSON from {url}: {exc}") from exc
```
Move `resp.json()` inside the try block and add a `ValueError` catch (the parent of `JSONDecodeError`).

### CR-02: Unguarded `raw["name"]` KeyError crashes entire `get_hosts()` call

**File:** `inference_proxy/quads/client.py:66`
**Issue:** If any single host entry in the QUADS API response is missing the `"name"` field, `raw["name"]` raises `KeyError`. This is not caught by the `_get` method (which has already returned successfully), so it propagates as an unhandled `KeyError` -- not a `QUADSConnectionError`. One malformed record in the QUADS inventory prevents the entire host list from being parsed. The error message would also be unhelpful (just the key name).
**Fix:**
```python
for raw in data:
    if raw.get("broken") or raw.get("retired"):
        continue
    name = raw.get("name")
    if not name:
        logger.warning("skipping QUADS host entry with missing name", raw_keys=list(raw.keys()))
        continue
    gpus = [
        p
        for p in raw.get("processors", [])
        if p.get("processor_type") == "GPU"
    ]
    if not gpus:
        continue
    hosts.append(
        QUADSHost(
            hostname=canonical_hostname(name),
            gpu_vendor=gpus[0].get("vendor", ""),
            gpu_model=gpus[0].get("product", ""),
            gpu_count=len(gpus),
        )
    )
```
Use `raw.get("name")` with a guard, log and skip the malformed entry instead of crashing the entire call.

## Warnings

### WR-01: `SSHSettings.key_path` default evaluated at class definition time

**File:** `inference_proxy/config/settings.py:101`
**Issue:** `Path("~/.ssh/id_rsa").expanduser()` executes during module import (class body evaluation), not at instance creation time. If the `HOME` environment variable changes between import and Settings instantiation (common in containerized deployments, CI, or tests using `monkeypatch`), the default will reflect the import-time `HOME`, not the runtime one. In tests that `monkeypatch.setenv("HOME", ...)` after the module is already imported, the default path will be wrong.
**Fix:**
```python
class SSHSettings(BaseModel):
    """SSH connection configuration (D-16)."""

    key_path: Path = Field(default_factory=lambda: Path("~/.ssh/id_rsa").expanduser())
    username: str = "root"
    connect_timeout: int = 10
```
Use `default_factory` to defer `expanduser()` to instantiation time.

### WR-02: `QUADSHost` model accepts `gpu_count=0` or negative values

**File:** `inference_proxy/models/quads.py:22`
**Issue:** The `gpu_count` field has no minimum-value constraint. While `QUADSClient.get_hosts()` only constructs `QUADSHost` after filtering for `len(gpus) > 0`, the model itself accepts `gpu_count=0` or `gpu_count=-1`. Any future caller constructing a `QUADSHost` directly (e.g., tests, admin endpoints, or data imports) would silently accept nonsensical values. Since the model is frozen and used as a domain object, it should enforce its own invariant.
**Fix:**
```python
from pydantic import BaseModel, ConfigDict, Field

class QUADSHost(BaseModel):
    """A GPU host from the QUADS inventory."""

    model_config = ConfigDict(frozen=True)

    hostname: str
    gpu_vendor: str
    gpu_model: str
    gpu_count: int = Field(ge=1)
```

---

_Reviewed: 2026-07-16_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
