---
phase: 30-foundation-model-catalog
plan: 01
subsystem: huggingface
tags: [config, catalog, huggingface-hub, pydantic]
dependency_graph:
  requires: []
  provides: [HuggingFaceSettings, CatalogEntry, ModelCatalogResponse, ModelCatalogService]
  affects: [inference_proxy/config/settings.py, tests/conftest.py]
tech_stack:
  added: [huggingface-hub>=1.25,<2.0]
  patterns: [asyncio.to_thread for blocking I/O, BaseModel sub-settings, SecretStr for tokens]
key_files:
  created:
    - inference_proxy/huggingface/__init__.py
    - inference_proxy/huggingface/catalog.py
    - tests/huggingface/__init__.py
    - tests/huggingface/test_catalog.py
  modified:
    - inference_proxy/config/settings.py
    - .env.example
    - pyproject.toml
    - uv.lock
    - tests/conftest.py
    - tests/config/test_settings.py
decisions:
  - "Required cache_dir field on HuggingFaceSettings (no default) -- gateway fails-fast without NFS path"
  - "os.environ.setdefault in conftest.py for module-level Settings() in main.py"
metrics:
  duration: 4min
  completed: 2026-07-28T15:41:54Z
  tasks_completed: 2
  tasks_total: 2
  files_changed: 10
---

# Phase 30 Plan 01: HuggingFace Settings & Model Catalog Service Summary

HuggingFaceSettings sub-model with required cache_dir and optional SecretStr api_token; ModelCatalogService scanning HF cache via asyncio.to_thread, filtering to model repos only.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | HuggingFaceSettings sub-model and huggingface package | 878db7c | settings.py, catalog.py, pyproject.toml |
| 2 | Unit tests for settings and catalog service | 21aea3f | test_catalog.py, test_settings.py |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Module-level Settings() in main.py breaks on required field**
- **Found during:** Task 1
- **Issue:** `app = create_app()` at module level in `main.py` calls `Settings()` at import time. Adding a required `huggingface.cache_dir` field broke all test collection since conftest.py imports trigger this path before any fixture can set env vars.
- **Fix:** Added `os.environ.setdefault("INFERENCE_PROXY_HUGGINGFACE__CACHE_DIR", "/tmp/test-hf-cache")` at the top of `tests/conftest.py` before any app imports. Also added `HuggingFaceSettings` to the `test_settings` fixture constructor.
- **Files modified:** tests/conftest.py
- **Commit:** 878db7c

**2. [Rule 2 - Missing] .env.example not updated with new env vars**
- **Found during:** Task 1
- **Issue:** CLAUDE.md mandates updating .env.example when env vars change in code.
- **Fix:** Added HUGGINGFACE section to .env.example with cache_dir and api_token.
- **Files modified:** .env.example
- **Commit:** 878db7c

## Out of Scope

Pre-existing test failure in `tests/llmfit/test_runner.py::TestRecommend::test_parses_valid_json` -- the runner command was changed from `--force-runtime vllm` to `--runtime vllm -n 30` but the test assertion was not updated. Not related to this plan.

## Verification

- `uv run pytest tests/huggingface/ tests/config/test_settings.py -x -q` -- 48 passed
- All imports verified: CatalogEntry, ModelCatalogResponse, ModelCatalogService, HuggingFaceSettings
