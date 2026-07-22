# Requirements: v1.5 Node Setup Enhancements

## Power Management

- [x] **PWR-01**: User can power on a node via Redfish API from the admin endpoint
- [x] **PWR-02**: User can power off a node via Redfish API from the admin endpoint
- [x] **PWR-03**: User can restart a node via Redfish API from the admin endpoint
- [x] **PWR-04**: User can query the current power state of a node (On/Off/PoweringOn/PoweringOff)
- [x] **PWR-05**: Provisioning automatically powers on a node before SSH setup if the node is off

## Diagnostics

- [ ] **DIAG-01**: Failed provisioning step name and error details are captured and stored
- [ ] **DIAG-02**: Dashboard displays failure details inline for failed nodes instead of just a state badge
- [x] **DIAG-03**: Redfish error responses are mapped to human-readable messages

## Future Requirements

- Dashboard power buttons (inline power on/off/restart in node fleet UI)
- Per-server BMC credentials lookup
- Power usage monitoring via Redfish telemetry
- Provisioning log download endpoint
- Retry failed provisioning step from point of failure

## Out of Scope

- **Session-based BMC authentication** — Basic auth sufficient for infrequent internal power ops
- **Multi-vendor BMC autodiscovery** — configurable system ID and hostname template covers fleet
- **Power scheduling/automation** — manual and pre-provisioning power ops only

## Traceability

| Requirement | Phase | Plan | Status |
|-------------|-------|------|--------|
| PWR-01 | 22 | — | Pending |
| PWR-02 | 22 | — | Pending |
| PWR-03 | 22 | — | Pending |
| PWR-04 | 22 | — | Pending |
| PWR-05 | 23 | — | Pending |
| DIAG-01 | 24 | — | Pending |
| DIAG-02 | 24 | — | Pending |
| DIAG-03 | 21 | — | Pending |
