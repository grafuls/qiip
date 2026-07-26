# Phase 26: llmfit Installation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-26
**Phase:** 26-llmfit Installation
**Areas discussed:** Step tracking

---

## Step Tracking

### Q1: Should llmfit_install get its own ProvisioningStep enum value?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, add to enum | Add LLMFIT_INSTALL to ProvisioningStep. Emit [STEP:llmfit_install:START/OK/FAIL] markers. Script catches failure internally (log warning, continue) so FAIL marker doesn't exit the script. | ✓ |
| No, keep it invisible | Don't add to enum. llmfit install runs silently inside setup.sh — success/failure only visible in the raw SSH log, not in dashboard step progress. | |
| You decide | Let Claude pick the approach that fits the existing patterns best. | |

**User's choice:** Yes, add to enum
**Notes:** User wants llmfit install visible in dashboard provisioning progress.

### Q2: How should the non-fatal step wrapper work in setup.sh?

| Option | Description | Selected |
|--------|-------------|----------|
| New soft_step() wrapper | Add a soft_step() function that emits [STEP:name:START/OK/WARN] markers. On failure it prints WARN (not FAIL) and continues instead of exit 1. Keeps existing step() untouched. | ✓ |
| Run after main steps | Keep llmfit install outside the step() flow entirely — run it after all critical steps pass, with manual echo of markers and \|\| true to suppress errors. | |
| You decide | Let Claude pick whichever approach produces the smallest, cleanest diff. | |

**User's choice:** New soft_step() wrapper
**Notes:** User prefers a clean abstraction over ad-hoc error suppression.

### Q3: Should the provisioner parse WARN markers?

| Option | Description | Selected |
|--------|-------------|----------|
| Parse and log | Provisioner recognizes WARN markers and emits a structlog warning with step name and reason. | |
| Raw log only | Provisioner ignores WARN markers — visible in SSH log buffer but no special structlog treatment. | ✓ |
| You decide | Claude picks based on existing log patterns. | |

**User's choice:** Raw log only
**Notes:** WARN markers stay in the raw SSH log buffer already captured by LogBuffer.

---

## Claude's Discretion

- **Download & air-gap:** Follow NVIDIA_DRIVER_VERSION env-var pattern. GitHub release download. Air-gapped labs fail non-fatally via soft_step() WARN.
- **Installation function:** Idempotent install_llmfit() — skip if binary already exists.

## Deferred Ideas

None.
