---
status: partial
phase: 32-dashboard-download-integration
source: [32-VERIFICATION.md]
started: 2026-07-29T05:45:00Z
updated: 2026-07-29T05:45:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. Visual Rendering
expected: Load node detail page, click Load for recommendations. Verify 7th "Download" column appears with correct badge/button states — "Downloaded" badge for models on NFS, "Download" button for others.
result: [pending]

### 2. Download Trigger
expected: Click Download on a model. Button should immediately change to "Downloading..." badge. Toast should appear confirming download started.
result: [pending]

### 3. Polling Cycle
expected: After triggering a download, observe network tab for GET /admin/models/downloads requests every 4 seconds. After download completes, badge changes to "Downloaded" and polling stops (no more requests).
result: [pending]

### 4. Failed Download Retry
expected: When a download fails, a red "Failed -- Retry" badge appears. Clicking it re-triggers the download POST.
result: [pending]

## Summary

total: 4
passed: 0
issues: 0
pending: 4
skipped: 0
blocked: 0

## Gaps
