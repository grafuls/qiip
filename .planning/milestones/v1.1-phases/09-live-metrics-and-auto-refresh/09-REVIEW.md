---
phase: 09-live-metrics-and-auto-refresh
reviewed: 2026-07-01T12:00:00Z
depth: standard
files_reviewed: 7
files_reviewed_list:
  - inference_proxy/config/settings.py
  - inference_proxy/api/dashboard.py
  - inference_proxy/templates/dashboard.html
  - inference_proxy/static/js/dashboard.js
  - inference_proxy/static/css/dashboard.css
  - tests/api/test_dashboard.py
  - tests/config/test_settings.py
findings:
  critical: 1
  warning: 2
  info: 1
  total: 4
status: issues_found
---

# Phase 9: Code Review Report

**Reviewed:** 2026-07-01T12:00:00Z
**Depth:** standard
**Files Reviewed:** 7
**Status:** issues_found

## Summary

Phase 9 adds a live dashboard with polling. The implementation is clean and minimal -- vanilla JS, Jinja2 template, pydantic-settings for config. The main concern is a missing validation constraint on `poll_interval` that allows zero or negative values, causing the browser to hammer the API in a tight loop. Two smaller warnings around test fragility and a stale docstring.

## Critical Issues

### CR-01: Missing minimum bound on `poll_interval` allows API denial-of-service

**File:** `inference_proxy/config/settings.py:90`
**Issue:** `DashboardSettings.poll_interval` is typed as `int` with no minimum constraint. Setting `INFERENCE_PROXY_DASHBOARD__POLL_INTERVAL=0` (or any negative value) passes Pydantic validation and renders `setInterval(refreshDashboard, 0)` in the browser, creating an effectively infinite loop of fetch requests against `/admin/nodes` and `/admin/metrics`. This is a self-inflicted DoS on the gateway from any dashboard tab. Since the env var is operator-controlled and easy to mis-set, this is a realistic failure mode.
**Fix:**
```python
from pydantic import BaseModel, Field, field_validator

class DashboardSettings(BaseModel):
    """Dashboard UI configuration."""

    poll_interval: int = Field(default=10, ge=1)
```
Alternatively, add a `field_validator` that rejects values below 1. Either way the constraint must exist before the value reaches the template.

## Warnings

### WR-01: Env-var override tests do not suppress `.env` file loading

**File:** `tests/config/test_settings.py:44`
**Issue:** Tests `TestEnvVarOverrideGatewayPort`, `TestEnvVarOverrideEtcdPrefix`, `TestEnvVarOverrideRoutingStrategy`, and `TestEnvVarOverrideDashboardPollInterval` (lines 44, 51, 58, 73) call `Settings()` without `_env_file=None`. If a developer has a `.env` file containing other `INFERENCE_PROXY_*` variables, those leak into the `Settings` instance. While each test only asserts on the one variable it patches, a `.env` override of a field that interacts with validation (e.g. `INFERENCE_PROXY_ETCD__ENDPOINTS=[]`) could cause unexpected `ValidationError` failures in unrelated tests. The default-value tests (lines 20, 27, 35, 64) already pass `_env_file=None` correctly -- the override tests should be consistent.
**Fix:**
```python
def test_env_var_override_gateway_port(self, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INFERENCE_PROXY_GATEWAY__PORT", "9090")
    settings = Settings(_env_file=None)
    assert settings.gateway.port == 9090
```
Apply the same pattern to all four env-var override tests.

### WR-02: Test docstring claims 6 column headers but code and template have 7

**File:** `tests/api/test_dashboard.py:9`
**Issue:** The module-level docstring says "Table structure with 6 column headers (NODE-01)" but the table has 7 columns (Node ID, Endpoint, Model, Status, Active Connections, Circuit Breaker, Requests) and the test `test_contains_all_seven_column_headers` on line 70 correctly asserts all 7. The stale docstring will mislead developers reading the test file.
**Fix:** Update line 9 from "Table structure with 6 column headers" to "Table structure with 7 column headers".

## Info

### IN-01: `templates` Jinja2Templates instance is module-level global

**File:** `inference_proxy/api/dashboard.py:19`
**Issue:** `templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))` is resolved at import time using `Path(__file__).resolve().parent.parent`. This works correctly here (the directory is relative to the package), but the object is a module-level singleton that cannot be overridden in tests without monkey-patching the module attribute. Not a bug today, but worth noting if template testing needs grow.
**Fix:** No action required unless template mocking is needed. If so, move to a dependency-injected pattern similar to `get_settings`.

---

_Reviewed: 2026-07-01T12:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
