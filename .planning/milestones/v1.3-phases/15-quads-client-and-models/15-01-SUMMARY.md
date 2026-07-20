---
phase: 15-quads-client-and-models
plan: 01
subsystem: quads-client
tags: [quads, client, models, settings, di]
dependency_graph:
  requires: []
  provides: [QUADSClient, QUADSHost, QUADSConnectionError, canonical_hostname, QUADSSettings, get_quads_client]
  affects: [inference_proxy/main.py, inference_proxy/config/settings.py, inference_proxy/config/dependencies.py]
tech_stack:
  added: []
  patterns: [frozen-pydantic-model, constructor-injection, di-via-app-state, package-per-domain]
key_files:
  created:
    - inference_proxy/models/quads.py
    - inference_proxy/quads/__init__.py
    - inference_proxy/quads/client.py
    - tests/models/test_quads.py
    - tests/quads/__init__.py
    - tests/quads/test_client.py
  modified:
    - inference_proxy/config/settings.py
    - inference_proxy/config/dependencies.py
    - inference_proxy/main.py
    - tests/config/test_settings.py
decisions:
  - "GPU vendor/model taken from first GPU processor entry (ponytail: handles mixed GPU types when Phase 18 needs full list)"
  - "Dedicated httpx.AsyncClient for QUADS with 10s timeout, separate from 120s proxy client"
  - "Private _get() helper on QUADSClient to DRY the httpx error wrapping"
metrics:
  duration_seconds: 250
  completed: "2026-07-16T09:29:58Z"
  tasks: 3
  tests_added: 19
  total_tests: 361
---

# Phase 15 Plan 01: QUADS Client and Models Summary

QUADS REST API client with GPU host filtering, hostname normalization, typed error handling, and full lifespan/DI wiring

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | QUADSHost model, QUADSSettings, tests | 25c2308 (RED), 7d89f5c (GREEN) | inference_proxy/models/quads.py, inference_proxy/config/settings.py, tests/models/test_quads.py, tests/config/test_settings.py |
| 2 | QUADSClient, canonical_hostname, QUADSConnectionError, tests | 2d0d613 (RED), 42b2370 (GREEN) | inference_proxy/quads/__init__.py, inference_proxy/quads/client.py, tests/quads/__init__.py, tests/quads/test_client.py |
| 3 | Lifespan wiring and DI provider | cfd2181 | inference_proxy/main.py, inference_proxy/config/dependencies.py |

## What Was Built

- **QUADSHost**: Frozen Pydantic model with hostname, gpu_vendor, gpu_model, gpu_count fields
- **QUADSClient**: Async client with get_hosts() (GPU-only, broken/retired excluded) and get_available() (normalized hostname strings)
- **canonical_hostname()**: Strip whitespace, lowercase, strip trailing dots
- **QUADSConnectionError**: Typed exception wrapping httpx.HTTPError
- **QUADSSettings**: base_url (None=disabled) and timeout (10.0s default), configurable via INFERENCE_PROXY_QUADS__* env vars
- **get_quads_client()**: DI provider returning QUADSClient | None
- **Lifespan wiring**: Dedicated httpx.AsyncClient for QUADS, created when configured, closed on shutdown

## Verification

- 42 QUADS-specific tests pass (tests/quads/ + tests/models/test_quads.py + tests/config/test_settings.py)
- 361 total tests pass (full suite, zero regressions)
- mypy clean on all QUADS modules (3 source files, 0 issues)

## Deviations from Plan

None -- plan executed exactly as written.

## TDD Gate Compliance

- RED gate: test(15-01) commits 25c2308, 2d0d613 exist (failing tests committed before implementation)
- GREEN gate: feat(15-01) commits 7d89f5c, 42b2370 exist after RED (implementation passes tests)
- REFACTOR gate: skipped (no refactoring needed, implementation is minimal)
