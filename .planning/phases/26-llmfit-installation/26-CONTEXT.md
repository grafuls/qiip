# Phase 26: llmfit Installation - Context

**Gathered:** 2026-07-26
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase adds llmfit binary installation to the provisioning setup script (`auto-vllm/setup.sh`) as a non-fatal step. After provisioning completes, `/usr/local/bin/llmfit` should exist on the target server — but if installation fails, provisioning still succeeds and the failure is logged as a warning.

</domain>

<decisions>
## Implementation Decisions

### Step Tracking
- **D-01:** Add `LLMFIT_INSTALL` to `ProvisioningStep` enum so the step appears in dashboard provisioning progress.
- **D-02:** New `soft_step()` wrapper in `setup.sh` that emits `[STEP:name:START]` / `[STEP:name:OK]` / `[STEP:name:WARN]` markers. On failure, prints WARN (not FAIL) and continues — no `exit 1`. Existing `step()` wrapper stays unchanged.
- **D-03:** Provisioner does NOT parse WARN markers specially. They flow through the raw SSH log buffer (already captured by `LogBuffer`), no special structlog treatment on the Python side.

### Claude's Discretion
- **Download method:** Follow the existing `NVIDIA_DRIVER_VERSION` env-var pattern in setup.sh — add `LLMFIT_VERSION` with a pinned default and `LLMFIT_URL` derived from it. Download prebuilt binary from GitHub releases.
- **Air-gap handling:** No special SCP pre-staging. In air-gapped labs, the download fails, `soft_step()` emits WARN, and provisioning continues without llmfit. INST-02 covers this — failure is non-fatal by design.
- **Installation function:** Idempotent `install_llmfit()` function — skip if `/usr/local/bin/llmfit` already exists (same pattern as `install_vllm()` and `install_nvidia_driver()`).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Provisioning Scripts
- `auto-vllm/setup.sh` — Existing provisioning script with `step()` wrapper, env-var defaults, idempotent step functions. New `soft_step()` and `install_llmfit()` go here.
- `auto-vllm/start-vllm.sh` — Not modified but context for how provisioning scripts are structured.

### Provisioning State
- `inference_proxy/provisioning/state.py` — `ProvisioningStep` StrEnum and `ProvisioningState` model. Add `LLMFIT_INSTALL` to the enum.
- `inference_proxy/provisioning/provisioner.py` — `_run_setup()` method parses `[STEP:name:START/OK/FAIL]` markers from setup.sh output. Lines 329-350 show the parsing pattern.

### Prior Phase Context
- `.planning/phases/25-core-models-and-runner/25-CONTEXT.md` — Phase 25 decisions (D-06: hardcoded `/usr/local/bin/llmfit` path in runner)

### Requirements
- `.planning/REQUIREMENTS.md` — INST-01 (prebuilt binary download), INST-02 (non-fatal step)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `step()` wrapper in `setup.sh`: Model for the new `soft_step()` — same structure, different failure behavior.
- `install_nvidia_driver()` / `install_vllm()`: Idempotent check-then-install pattern to follow for `install_llmfit()`.
- Env-var defaults pattern (`NVIDIA_DRIVER_VERSION`, `NFS_SERVER`, `VLLM_PORT`): Follow for `LLMFIT_VERSION` / `LLMFIT_URL`.

### Established Patterns
- `ProvisioningStep` enum values match setup.sh step names (snake_case) — provisioner does `ProvisioningStep(step_name)` from parsed markers.
- Provisioner only acts on `START` markers to update state — `OK`/`FAIL` from the script are informational.

### Integration Points
- `auto-vllm/setup.sh` — Add `soft_step()` wrapper + `install_llmfit()` function + invocation after critical steps.
- `inference_proxy/provisioning/state.py` — Add `LLMFIT_INSTALL` member to `ProvisioningStep`.

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches. Follow existing patterns in setup.sh.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 26-llmfit Installation*
*Context gathered: 2026-07-26*
