# Phase 21: Redfish Client & Configuration - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-21
**Phase:** 21-redfish-client-configuration
**Areas discussed:** BMC hostname convention, Idempotency behavior, TLS certificate handling

---

## BMC Hostname Convention

### Question 1: BMC hostname pattern

| Option | Description | Selected |
|--------|-------------|----------|
| mgmt-{hostname} | Prefix pattern: server01 → mgmt-server01. Common in many labs. | ✓ |
| Different prefix pattern | A different template like {hostname}-bmc, idrac-{hostname}, or similar. | |
| You decide | Make the template configurable with mgmt-{hostname} as the default. | |

**User's choice:** mgmt-{hostname}

### Question 2: Fleet-wide vs per-host

| Option | Description | Selected |
|--------|-------------|----------|
| Fleet-wide template | Single INFERENCE_PROXY_REDFISH__BMC_HOST_TEMPLATE env var. Simplest. | ✓ |
| Per-host override | Default fleet template + per-host override in etcd node data. More flexible. | |

**User's choice:** Fleet-wide template

---

## Idempotency Behavior

### Question 1: Already-in-state handling

| Option | Description | Selected |
|--------|-------------|----------|
| Check-before-act, silent success | Query PowerState first. If already in desired state, return success. | ✓ |
| Check-before-act, distinct result | Query PowerState first. Return result indicating 'already in state'. | |
| Fire and handle 400 | Always send reset action. Handle 400 by re-checking state. | |

**User's choice:** Check-before-act, silent success

### Question 2: Post-action polling

| Option | Description | Selected |
|--------|-------------|----------|
| Fire and return immediately | Client sends reset, returns as soon as BMC accepts. Polling is caller's responsibility. | |
| Poll until state reached | Client polls PowerState after reset until target state confirmed, with configurable timeout. | ✓ |
| You decide | Claude picks based on downstream usage patterns. | |

**User's choice:** Poll until state reached

---

## TLS Certificate Handling

### Question 1: Verification approach

| Option | Description | Selected |
|--------|-------------|----------|
| verify=False only | Always skip TLS verification. Matches lab self-signed cert reality. | ✓ |
| verify=False + optional CA path | Default verify=False, support optional ca_bundle_path for proper certs. | |
| You decide | Claude picks simplest approach. | |

**User's choice:** verify=False only

### Question 2: TLS warning suppression

| Option | Description | Selected |
|--------|-------------|----------|
| Suppress the warning | Filter out InsecureRequestWarning entirely. Cleaner logs. | ✓ |
| Let it log once at startup | Single structured warning at startup, then suppress per-request. | |
| You decide | Claude picks based on structlog patterns. | |

**User's choice:** Suppress the warning

---

## Claude's Discretion

- Error message mapping approach for DIAG-03 (user skipped this area — Claude decides)
- RedfishClient internal structure
- RedfishSettings sub-model fields and defaults
- Dependency injection wiring

## Deferred Ideas

None — discussion stayed within phase scope
