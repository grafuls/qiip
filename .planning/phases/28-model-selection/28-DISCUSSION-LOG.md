# Phase 28: Model Selection - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-26
**Phase:** 28-model-selection
**Areas discussed:** Env var passing

---

## Gray Area Selection

| Option | Description | Selected |
|--------|-------------|----------|
| Model validation | Should SetupRequest validate the model string (format, length), or accept any string and let vLLM fail? | |
| Env var passing | How to thread VLLM_MODEL to start-vllm.sh via SSH — prepend to command, export before, or other? | ✓ |
| Skip — Claude decides | Phase is straightforward wiring. Let Claude handle all implementation choices. | |

**User's choice:** Env var passing only; model validation deferred to Claude's discretion.

---

## Env Var Passing

| Option | Description | Selected |
|--------|-------------|----------|
| Prepend to command | Build command as `VLLM_MODEL=xxx bash auto-vllm/start-vllm.sh`. Zero changes to SSHClient. | ✓ |
| Add env param to SSHClient | Add `env: dict` to run_streaming() signature. Passes env to asyncssh create_process(). | |
| You decide | Let Claude pick the simplest approach. | |

**User's choice:** Prepend to command
**Notes:** Standard shell idiom, no interface changes needed. Use shlex.quote() for safety.

---

## Claude's Discretion

- Model validation approach (basic Pydantic optional field, no cross-validation)
- Provisioner signature threading (model parameter through provision → _run_start_vllm)
- Admin endpoint wiring (single-line body.model passthrough)

## Deferred Ideas

None.
