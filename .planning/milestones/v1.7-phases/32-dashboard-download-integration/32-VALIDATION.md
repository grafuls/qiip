# Phase 32: Dashboard Download Integration - Validation Architecture

**Created:** 2026-07-28
**Source:** Extracted from 32-RESEARCH.md validation section

## Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio + FastAPI TestClient |
| Config file | `pyproject.toml` (pytest section) |
| Quick run command | `uv run pytest tests/api/test_dashboard.py -x` |
| Full suite command | `uv run pytest` |

## Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DASH-01 | Download button rendered in recommendations table | manual | Browser inspection after loading recommendations | N/A |
| DASH-02 | "Downloaded" badge for models in catalog | manual | Browser inspection with model on NFS | N/A |
| DASH-03 | Download status auto-updates without refresh | manual | Trigger download, observe 4s poll cycle | N/A |

## Rationale

All three DASH requirements are inherently manual — they involve JS-rendered DOM with live API interaction. No server-side testable output is produced. The existing `test_dashboard.py` serves as a regression guard for template structure only.

## Sampling Rate

- **Per task commit:** `uv run pytest tests/api/test_dashboard.py -x` (no template regressions)
- **Per wave merge:** `uv run pytest`
- **Phase gate:** Full suite green + manual browser verification of all three DASH requirements

## Wave 0 Gaps

None — this phase modifies only client-side JS. Existing tests cover template structure.
