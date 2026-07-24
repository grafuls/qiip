# Phase 25: Core Models and Runner - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-24
**Phase:** 25-Core Models and Runner
**Areas discussed:** SSH execution method, Error handling shape, llmfit command flags

---

## SSH Execution Method

### Q1: How should LLMFitRunner get the full stdout from a remote llmfit command?

| Option | Description | Selected |
|--------|-------------|----------|
| Add run() to SSHClient | New method returns (stdout, stderr, exit_status). Clean separation — streaming for provisioning, run() for capture-all. | ✓ |
| Collect from run_streaming() | Runner iterates run_streaming(), joins stdout lines. No SSHClient change but reassembles what was split. | |
| You decide | Let Claude pick based on codebase patterns. | |

**User's choice:** Add run() to SSHClient
**Notes:** Clean separation between streaming and capture-all use cases. Other future callers benefit.

### Q2: Should run() handle the timeout internally, or should callers wrap with asyncio.wait_for()?

| Option | Description | Selected |
|--------|-------------|----------|
| Timeout param on run() | run(host, command, timeout=60) — SSHClient owns the timeout. Consistent with connect_timeout. | ✓ |
| Caller wraps with wait_for() | SSHClient stays simple. LLMFitRunner does asyncio.wait_for(). Timeout logic in consumer. | |

**User's choice:** Timeout param on run()
**Notes:** Consistent with connect_timeout already being internal to SSHClient.

---

## Error Handling Shape

### Q1: How should llmfit-specific errors be structured?

| Option | Description | Selected |
|--------|-------------|----------|
| Exception hierarchy | LLMFitError base → LLMFitTimeoutError, LLMFitParseError. SSH errors bubble through unchanged. | ✓ |
| Single LLMFitError with reason | One class with reason enum. Simpler but less precise for isinstance() matching. | |
| Reuse SSH errors only | No new types. Existing SSH errors + bare ValueError for parse. Minimal but loses semantics. | |

**User's choice:** Exception hierarchy
**Notes:** Phase 27 maps each exception type to a specific HTTP status and message.

### Q2: Should LLMFitParseError include the raw JSON/stdout that failed to parse?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, include raw output | Stores raw stdout for debugging. Phase 27 decides exposure in API response vs log-only. | ✓ |
| No, just the error message | Raw output goes to structlog, not the exception. Avoids leaking large payloads. | |

**User's choice:** Yes, include raw output
**Notes:** Helps operators and logs diagnose schema mismatches.

---

## llmfit Command Flags

### Q1: Which llmfit flags should be configurable in Phase 25's runner?

| Option | Description | Selected |
|--------|-------------|----------|
| Minimal: --json --force-runtime only | Hardcode these. --limit, --use-case, --memory deferred to Phase 27. | ✓ |
| Full: all flags configurable now | Runner accepts limit, use_case, memory_override params. More upfront work. | |
| Middle: add --limit now | Hardcode --json --force-runtime, make --limit configurable. Other flags deferred. | |

**User's choice:** Minimal: --json --force-runtime only
**Notes:** Keeps runner simple, models focused. Phase 27 adds configurability.

### Q2: Should Phase 25 include LLMFitSettings in config/settings.py?

| Option | Description | Selected |
|--------|-------------|----------|
| Include LLMFitSettings now | Add with command_timeout and binary_path. Phase 27 adds more fields. | |
| Defer settings entirely | Runner uses hardcoded defaults. Phase 27 adds LLMFitSettings when needed. | ✓ |

**User's choice:** Defer settings entirely
**Notes:** Smallest diff. Runner uses hardcoded timeout 60s and binary path /usr/local/bin/llmfit.

---

## Claude's Discretion

None — user made all decisions directly.

## Deferred Ideas

None — discussion stayed within phase scope.
