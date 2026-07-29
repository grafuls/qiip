---
phase: 31-download-service-api
plan: 02
subsystem: api
tags: [download, admin-api, dependency-injection, endpoints]
dependency_graph:
  requires: [DownloadService, DownloadState, DownloadRequest, DownloadStatusResponse]
  provides: [POST /admin/models/download, GET /admin/models/downloads, get_download_service]
  affects: [inference_proxy/api/admin.py, inference_proxy/config/dependencies.py, inference_proxy/main.py]
tech_stack:
  added: []
  patterns: [fastapi-depends, app-state-lifespan, dependency-override-testing]
key_files:
  created:
    - tests/api/test_admin_downloads.py
  modified:
    - inference_proxy/config/dependencies.py
    - inference_proxy/api/admin.py
    - inference_proxy/main.py
    - tests/conftest.py
decisions:
  - Endpoints placed before /nodes/setup in admin.py to group all /models/ routes together
metrics:
  duration: 3min
  completed: 2026-07-28
  tasks_completed: 2
  tasks_total: 2
requirements: [DL-01, DL-02, DL-03, DL-04]
---

# Phase 31 Plan 02: Download API Endpoints Summary

DI provider, lifespan wiring, POST /admin/models/download (202) and GET /admin/models/downloads with integration tests

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | DI provider, lifespan wiring, and conftest mock | 2d1d590 | inference_proxy/config/dependencies.py, inference_proxy/main.py, tests/conftest.py |
| 2 | Admin download endpoints and integration tests | d47afef | inference_proxy/api/admin.py, tests/api/test_admin_downloads.py |

## Deviations from Plan

None - plan executed exactly as written.

## Verification

```
uv run pytest tests/api/ tests/huggingface/test_downloader.py -x -q
177 passed

uv run pytest tests/api/test_admin_downloads.py -x -q
5 passed
```

Two pre-existing failures exist outside this plan's scope:
- tests/llmfit/test_runner.py::TestRecommend::test_parses_valid_json
- tests/test_app.py::TestLifespanRegistryIntegration::test_lifespan_creates_registry (missing /tmp/test-hf-cache dir)

## Known Stubs

None.

## Self-Check: PASSED
