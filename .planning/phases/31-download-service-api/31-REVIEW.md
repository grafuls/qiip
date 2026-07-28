---
phase: 31-download-service-api
reviewed: 2026-07-28T22:10:00Z
depth: standard
files_reviewed: 8
files_reviewed_list:
  - inference_proxy/api/admin.py
  - inference_proxy/config/dependencies.py
  - inference_proxy/huggingface/downloader.py
  - inference_proxy/main.py
  - inference_proxy/models/admin.py
  - tests/api/test_admin_downloads.py
  - tests/conftest.py
  - tests/huggingface/test_downloader.py
findings:
  critical: 1
  warning: 3
  total: 4
status: issues_found
---

# Phase 31: Code Review Report

**Reviewed:** 2026-07-28T22:10:00Z
**Depth:** standard
**Files Reviewed:** 8
**Status:** issues_found

## Summary

The download service implementation is well-structured: clean separation between the API layer (`admin.py`), service layer (`downloader.py`), and models (`admin.py`). Thread-safe status tracking, background task lifecycle, and concurrency limiting via semaphore are all handled correctly. Dependency injection wiring in `dependencies.py`, `main.py` lifespan, and test fixtures all connect properly.

However, the endpoint violates its own documented API contract for duplicate requests, the request model lacks input validation that exists on peer models in the same file, and a unit test uses `asyncio.Event` incorrectly in a threaded context.

## Critical Issues

### CR-01: trigger_download always returns 202, even for duplicate in-progress downloads

**File:** `inference_proxy/api/admin.py:126-136`
**Issue:** The route decorator hardcodes `status_code=202`. The docstring and D-10 spec state that duplicate POSTs for an in-progress download should return 200 with the existing status. Since `svc.trigger_download()` returns a `DownloadStatusResponse` in both cases and FastAPI applies the decorator's status code to all model returns, duplicates incorrectly get 202 instead of 200. This breaks the API contract clients may rely on to distinguish "new download started" from "download already running."

**Fix:** Detect the duplicate case in the endpoint and return a `JSONResponse` with explicit 200:
```python
@admin_router.post("/models/download", status_code=202)
async def trigger_download(
    body: DownloadRequest,
    svc: DownloadService = Depends(get_download_service),
) -> DownloadStatusResponse:
    existing = svc.get_status(body.repo_id)
    if existing is not None and existing.status == DownloadState.DOWNLOADING:
        return JSONResponse(
            status_code=200,
            content=existing.model_dump(mode="json"),
        )
    return await svc.trigger_download(body.repo_id)
```

## Warnings

### WR-01: No input validation on DownloadRequest.repo_id

**File:** `inference_proxy/models/admin.py:153-158`
**Issue:** `repo_id` is a bare `str` with no validation. Empty strings, whitespace-only strings, and strings exceeding reasonable length all pass through to `huggingface_hub.snapshot_download`. The peer model `SetupRequest.hostname` in the same file has proper validation (lines 69-77) -- the same pattern should be applied here. While `huggingface_hub` will reject invalid repo IDs, failing at the API boundary with a clear 422 is better than failing deep in a background thread where the error surfaces as a generic `FAILED` status.

**Fix:** Add a field validator matching HuggingFace's `org/model` naming convention:
```python
class DownloadRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    repo_id: str = Field(min_length=1, max_length=256)

    @field_validator("repo_id")
    @classmethod
    def validate_repo_id(cls, v: str) -> str:
        v = v.strip()
        if not v or "/" not in v:
            raise ValueError("repo_id must be in 'owner/model' format")
        return v
```

### WR-02: Test uses asyncio.Event.wait() from a threaded context -- does not actually block

**File:** `tests/huggingface/test_downloader.py:71-72`
**Issue:** The test creates an `asyncio.Event` and sets `mock_sd.side_effect = lambda *a, **kw: event.wait()` intending to block the download so it stays in DOWNLOADING state. However, `asyncio.Event.wait()` returns a coroutine object when called synchronously (confirmed: `type(asyncio.Event().wait())` is `<class 'coroutine'>`). The coroutine is never awaited, so the download completes immediately instead of hanging. The test passes only because `asyncio.create_task` schedules the background task but it has not executed by the time the second `trigger_download` is called (no yield point between them). Additionally, the unawaited coroutine produces a `RuntimeWarning: coroutine 'Event.wait' was never awaited`.

**Fix:** Use `threading.Event` instead, since `snapshot_download` runs in a thread via `asyncio.to_thread`:
```python
event = threading.Event()
mock_sd.side_effect = lambda *a, **kw: event.wait()
# ...
event.set()  # now actually unblocks the thread
```

### WR-03: test_duplicate_returns_status does not assert HTTP status code

**File:** `tests/api/test_admin_downloads.py:50-67`
**Issue:** The test for D-10 duplicate-detection only checks `response.json()["status"] == "downloading"` without asserting the HTTP status code. Per D-10, duplicates should return 200 (not 202). This missing assertion masks CR-01 -- the test passes even though the endpoint returns the wrong status code.

**Fix:** Add status code assertion:
```python
def test_duplicate_returns_status(self, app, client):
    # ... existing setup ...
    response = client.post(
        "/admin/models/download", json={"repo_id": "org/model"}
    )
    assert response.status_code == 200  # D-10: duplicate returns 200, not 202
    assert response.json()["status"] == "downloading"
```

---

_Reviewed: 2026-07-28T22:10:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
