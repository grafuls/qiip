# Phase 23: Auto-Power-On in Provisioner - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-22
**Phase:** 23-auto-power-on-in-provisioner
**Areas discussed:** Redfish-unconfigured behavior, Boot wait strategy, Power-on failure handling

---

## Redfish-Unconfigured Behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Skip power check, proceed to preflight | Matches existing Optional=None pattern. Backward-compatible. | ✓ |
| Block provisioning, return error | Require Redfish for all provisioning. Breaks backward compatibility. | |
| You decide | Let Claude pick based on codebase patterns. | |

**User's choice:** Skip power check, proceed to preflight
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| Info log | Log at INFO: "redfish_not_configured, skipping power check" | ✓ |
| Debug log | Only visible with DEBUG logging. | |
| No log | Silent skip. | |

**User's choice:** Info log
**Notes:** None

---

## Boot Wait Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Dedicated SSH wait loop | Separate TCP-probe retry loop before preflight with configurable timeout. | ✓ |
| Extend preflight with retries | Make preflight's TCP probe retry when preceded by power-on. | |
| You decide | Let Claude pick based on SOLID and existing patterns. | |

**User's choice:** Dedicated SSH wait loop
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| Single POWERING_ON step | One enum member covers power action + SSH wait. | ✓ |
| Split into two steps | POWERING_ON + WAITING_FOR_SSH for more granularity. | |

**User's choice:** Single POWERING_ON step
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| 300 seconds (5 min) | Covers most cold boots with margin. Configurable via settings. | ✓ |
| 180 seconds (3 min) | Tighter. May time out on slower-booting servers. | |
| You decide | Let Claude pick based on hardware context. | |

**User's choice:** 300 seconds (5 min)
**Notes:** None

---

## Power-On Failure Handling

| Option | Description | Selected |
|--------|-------------|----------|
| Log warning, continue to preflight | Best-effort. Server might already be on. | ✓ |
| Fail provisioning immediately | Strict: stop if power-on fails. | |
| You decide | Let Claude pick based on resilience patterns. | |

**User's choice:** Log warning, continue to preflight
**Notes:** None

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, show then move on | State goes POWERING_ON → PREFLIGHT. Operator sees attempt was made. | ✓ |
| No, skip POWERING_ON entirely on failure | Jump straight to PREFLIGHT. | |

**User's choice:** Yes, show then move on
**Notes:** None

---

## Claude's Discretion

- SSH wait loop probe interval
- ProvisioningSettings field naming for boot wait config
- Whether power-on logic is a private method or standalone helper
- Test structure for new logic

## Deferred Ideas

None — discussion stayed within phase scope
