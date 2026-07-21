# Domain Pitfalls

**Domain:** Redfish Power Management and Provisioning Diagnostics for Inference Proxy Gateway
**Researched:** 2026-07-21
**Confidence:** HIGH (verified against DMTF Redfish specification, MAAS Redfish driver bug reports, OpenBMC implementation, existing provisioner codebase)

**Scope:** Pitfalls specific to adding Redfish power management (v1.5) and step-level error capture/display to the existing provisioning pipeline. Prior pitfalls (v1.0-v1.4) are in git history.

---

## Critical Pitfalls

Mistakes that cause failed power operations, leaked credentials, or require provisioning pipeline rework.

### Pitfall 1: ForceOff on an Already-Off Server Returns HTTP 400

**What goes wrong:** The code issues `POST /redfish/v1/Systems/1/Actions/ComputerSystem.Reset` with `{"ResetType": "ForceOff"}` to a server that is already powered off. The BMC returns HTTP 400 (Bad Request). The retry logic sees a 400, retries the same request, gets 400 again, exhausts retries, and reports a power-off failure -- even though the server is already in the desired state.

This is the single most reported Redfish integration bug. MAAS, OpenShift Ironic, and StarlingX all hit this. The DMTF specification does not require BMCs to be idempotent on power actions; most are not. HPE iLO, Dell iDRAC, and Supermicro BMCs all return 400 when the requested action is a no-op relative to the current state.

**Why it happens:** Developers assume power actions are idempotent ("make it off" = "ensure it is off"). They are not. They are imperative ("turn it off now"), and if it is already off, there is nothing to turn off -- the BMC rejects the request.

**Consequences:**
- Teardown fails on servers that are already powered off (e.g., after a crash or manual shutdown).
- Auto-power-on before provisioning fails if the server happens to already be on (sends On to an already-On server -- some BMCs accept this, some reject it).
- The provisioner marks the operation as FAILED and the dashboard shows an error for a non-error situation.

**Prevention:**
- Always query `PowerState` via `GET /redfish/v1/Systems/1` before issuing any reset action. If the current state matches the desired state, skip the action and return success.
- Handle HTTP 400 on power actions as a soft error: re-query `PowerState` immediately. If the state matches the desired outcome, treat it as success. If it does not match, then it is a real error.
- The check-before-act pattern:
  ```python
  state = await self._get_power_state(hostname)
  if action == "ForceOff" and state == "Off":
      return  # Already off, skip
  if action == "On" and state == "On":
      return  # Already on, skip
  await self._reset_action(hostname, action)
  await self._poll_power_state(hostname, target_state, timeout)
  ```

**Detection:** Call the power-off endpoint on a server that is already off. If it raises an exception instead of succeeding, this pitfall is present.

**Phase:** Core Redfish client phase. This must be in the initial implementation, not a follow-up.

---

### Pitfall 2: BMC Credentials Stored in Settings Model Leak into Logs and Error Responses

**What goes wrong:** BMC username and password are added to the `Settings` Pydantic model (alongside `SSHSettings`, `QUADSSettings`, etc.). Structlog logs the settings at startup for debugging. Pydantic's `model_dump()` serializes the credentials to JSON. An error response includes the settings context. The BMC password appears in application logs, etcd provisioning state records, and potentially the dashboard error display.

This is especially dangerous because BMC credentials grant out-of-band hardware control. Unlike SSH keys (file path stored, not the key itself), BMC credentials are short strings (username/password) that are easily copy-pasted from logs.

**Why it happens:** The existing `SSHSettings` stores a `key_path` (a file path, not the key itself), so credentials never leak from SSH settings. But BMC auth requires username+password strings in-memory. Developers follow the same pattern as `SSHSettings` without realizing the difference.

**Consequences:**
- BMC passwords in application logs (shipped to centralized logging).
- BMC passwords in etcd (if the error message from a failed Redfish call includes the request context).
- BMC passwords in the dashboard error display (the `error` field of `ProvisioningState` is rendered in HTML).
- An attacker with log access can power off every server in the fleet.

**Prevention:**
- Use Pydantic's `SecretStr` type for the BMC password field. `SecretStr` masks the value in `repr()`, `str()`, and `model_dump()` unless explicitly called with `model_dump(mode="json")` and `SecretStr.get_secret_value()`.
  ```python
  from pydantic import SecretStr

  class RedfishSettings(BaseModel):
      bmc_username: str = "admin"
      bmc_password: SecretStr
  ```
- Never include `RedfishSettings` in structlog context binds. Log the BMC hostname, never the credentials.
- The `error` field written to etcd (`ProvisioningState.error`) must be sanitized: strip any URL that contains embedded credentials (e.g., `https://user:pass@bmc-host/redfish/...`). Use a sanitizer that redacts credentials from URLs and error messages before writing to etcd or returning to the dashboard.
- Do NOT embed credentials in the Redfish URL. Use httpx's `auth` parameter or the `Authorization` header, never `https://user:pass@host/`.

**Detection:** Dump the settings model at startup and search for the BMC password in the output. If it appears in plaintext, this pitfall is present.

**Phase:** Core Redfish client phase. Credential handling must be correct from the first line of code.

---

### Pitfall 3: Power-On Issued but SSH Preflight Starts Before OS Boots

**What goes wrong:** The provisioning flow becomes: Redfish power on -> preflight (TCP probe port 22 + SSH diagnostics). The power-on action returns HTTP 200/204 immediately (the BMC accepted the command), but the server takes 2-5 minutes to POST, boot the OS, and start sshd. The preflight TCP probe to port 22 fires immediately after the power-on returns, fails ("SSH port 22 unreachable"), and the provisioner marks the host as FAILED.

The existing preflight (provisioner.py lines 124-176) has a 10-second TCP timeout -- sufficient for an already-running server, but far too short for a cold-booting server.

**Why it happens:** The Redfish power-on API is fire-and-forget. HTTP 200 means "the BMC accepted the command," not "the server is ready." The server must go through: BMC power-on -> hardware POST -> BIOS -> bootloader -> kernel -> systemd -> sshd. This takes minutes, not seconds.

**Consequences:**
- Every cold-start provisioning attempt fails on the first try.
- Operators learn to manually power on servers, wait 3 minutes, then click Setup -- defeating the purpose of auto-power-on.
- Retry logic that re-runs the entire provisioning sequence re-sends the power-on (which now gets a 400 because the server is already powering on -- Pitfall 1).

**Prevention:**
- After issuing power on, poll `PowerState` until it reaches `On` (this means the BMC has confirmed power is applied, not that the OS is up). Then poll SSH port 22 with a generous timeout (e.g., 5 minutes with 10-second intervals) before running the full preflight.
- Add a new provisioning step `POWER_ON` between `PENDING` and `PREFLIGHT` in the `ProvisioningStep` enum. The dashboard shows "Powering on..." during the boot wait, so operators know why it is taking time.
- The polling sequence:
  1. Query `PowerState`. If already `On`, skip to preflight.
  2. Issue `{"ResetType": "On"}`.
  3. Poll `PowerState` until `On` (timeout: 60s -- BMC response, not OS boot).
  4. Poll TCP port 22 (timeout: 300s, interval: 10s).
  5. Run existing preflight (GPU check, disk check).
- Do NOT combine the SSH poll with the existing preflight. Preflight assumes SSH is reachable; the SSH poll waits for it to become reachable. These are different concerns.

**Detection:** Power off a server, trigger provisioning with auto-power-on, and verify it waits for SSH instead of immediately failing.

**Phase:** Provisioning integration phase. This is the bridge between Redfish power and the existing SSH provisioner.

---

### Pitfall 4: TLS Verification Disabled Globally via `verify=False`

**What goes wrong:** BMCs use self-signed certificates by default. The developer adds `httpx.AsyncClient(verify=False)` and moves on. The `verify=False` flag disables TLS certificate verification for the entire httpx client instance. If the same client is later reused for other HTTP calls (health checks, QUADS API), those also lose TLS verification. Even if a dedicated client is created for Redfish, `verify=False` becomes the team's "standard pattern" and spreads.

On internal networks (this project's deployment context), the risk is lower than on the public internet, but it still enables man-in-the-middle attacks between the gateway and BMCs -- which is the power management plane.

**Why it happens:** BMC self-signed certificates are the norm, not the exception. Every Redfish tutorial shows `verify=False` or `requests.get(..., verify=False)`. The DMTF Python Redfish library itself creates an unverified context by default.

**Consequences:**
- MITM attacks on the BMC management plane. An attacker on the management VLAN can intercept BMC credentials and issue arbitrary power commands.
- Python emits `InsecureRequestWarning` on every request, which clutters logs (and developers add `urllib3.disable_warnings()` to suppress it, hiding the problem further).
- Security audits flag it, requiring a retrofit later.

**Prevention:**
- Create a dedicated `httpx.AsyncClient` for Redfish calls with an explicit SSL context that trusts the BMC CA certificate or the specific self-signed certificate. Do not share this client with other HTTP operations.
  ```python
  import ssl
  ctx = ssl.create_default_context(cafile="/path/to/bmc-ca.pem")
  redfish_client = httpx.AsyncClient(verify=ctx)
  ```
- If the CA certificate is not available (common in lab environments), use `verify=False` but:
  1. Scope it to the Redfish client only (not shared with health check or QUADS clients).
  2. Add a `ponytail:` comment: `# ponytail: verify=False scoped to Redfish client only, add CA cert path when available`.
  3. Make it configurable: `RedfishSettings.verify_ssl: bool = False` with a note that `True` + `ca_cert_path` is the production path.
- Do NOT suppress `InsecureRequestWarning` globally. If the warning is noisy, suppress it only within the Redfish client scope.

**Detection:** Search for `verify=False` in the codebase. If it appears outside the Redfish client, or if the Redfish client is shared with other subsystems, this pitfall is present.

**Phase:** Core Redfish client phase. The client instance and its TLS configuration are the first thing built.

---

### Pitfall 5: Redfish Error Messages Rendered as Raw HTML in Dashboard

**What goes wrong:** The existing `ProvisioningState.error` field (state.py line 56) is a `str | None` that stores the error message when provisioning fails. The dashboard renders this field in HTML. When a Redfish error is stored in this field, it may contain:
- JSON with angle brackets or special characters from `@Message.ExtendedInfo`
- Full Redfish error responses with BMC hostnames, IP addresses, URIs
- Stack traces from the Python exception chain
- Embedded credentials if the error was constructed from a URL (Pitfall 2)

The dashboard's Jinja2 template auto-escapes HTML by default, so XSS is not the concern. The concern is information leakage and unreadable error messages: operators see `{"error":{"code":"Base.1.12.GeneralError","message":"A general error has occurred. See ExtendedInfo for more information","@Message.ExtendedInfo":[...]}}` instead of "Power on failed: server did not respond within 60 seconds."

**Why it happens:** The current error handling in `provisioner.py` (line 228-232) stores `str(exc)` as the error message. For SSH errors, `str(exc)` is human-readable. For Redfish HTTP errors, `str(exc)` is the raw httpx exception string, which includes the response body.

**Consequences:**
- Operators cannot understand what failed or what to do about it.
- Internal BMC details (IP addresses, firmware versions, Redfish URIs) leak to the dashboard.
- Error messages are too long to display inline in the dashboard table row.

**Prevention:**
- Create a Redfish-specific exception class (e.g., `RedfishError`) that accepts the raw error and extracts a human-readable summary. Map common Redfish error codes to operator-friendly messages:
  ```python
  REDFISH_ERROR_MAP = {
      "Base.1.12.ActionNotSupported": "This action is not supported by the BMC",
      "Base.1.12.ResourceNotFound": "BMC resource not found (check Redfish URI)",
      "iLO.2.30.PowerOnFailed": "Power on failed (check server hardware status)",
  }
  ```
- Sanitize the error message before writing to etcd: strip JSON, strip URLs, cap at 200 characters. Store the full error in structlog for debugging; store only the summary in `ProvisioningState.error`.
- The error field in `ProvisioningState` is what the dashboard renders. It must be human-readable, not machine-readable.

**Detection:** Trigger a Redfish error (e.g., wrong BMC hostname) and check what appears in the dashboard error column. If it is raw JSON or an httpx exception string, this pitfall is present.

**Phase:** Error capture phase. This is directly about the "step-level error capture" milestone requirement.

---

## Moderate Pitfalls

Mistakes that cause operational friction, degraded reliability, or confusing dashboard behavior.

### Pitfall 6: BMC Session Exhaustion from Leaked Sessions

**What goes wrong:** The Redfish client creates a session (`POST /redfish/v1/SessionService/Sessions`) for each power operation but does not delete it afterward. Most BMCs support a maximum of 4-16 concurrent sessions. After 4-16 power operations (across all servers if a shared BMC manages multiple chassis, or on a single BMC across retries), session creation fails with HTTP 503 or 400. All subsequent Redfish operations fail until sessions expire (30-minute default timeout on most BMCs).

MAAS explicitly documents this as a top issue: "If you do not properly log out from a session and open other sessions, you may reach this limit and will be locked out."

**Why it happens:** Developers use `async with httpx.AsyncClient() as client:` but do not close the Redfish session on the BMC side. The httpx client closing releases the TCP connection but does NOT invalidate the BMC session -- these are separate concerns.

**Consequences:**
- After 4-16 operations, all power management stops working fleet-wide.
- The failure message is confusing: "session limit exceeded" looks like an auth failure.
- Sessions expire after 30 minutes, so the system self-heals eventually, but operators cannot power-manage servers during the lockout.

**Prevention:**
- Use HTTP Basic Auth instead of sessions for simple power operations. Basic auth does not create server-side state and cannot be exhausted. For short-lived operations (query power state, issue reset), Basic auth is simpler and more reliable.
  ```python
  auth = httpx.BasicAuth(username=settings.bmc_username,
                         password=settings.bmc_password.get_secret_value())
  async with httpx.AsyncClient(auth=auth, verify=verify_ctx) as client:
      ...
  ```
- If session auth is preferred (e.g., for performance with many sequential operations), always delete the session in a `finally` block:
  ```python
  try:
      session_uri = await create_session(client, bmc_host, credentials)
      # ... do work ...
  finally:
      await delete_session(client, bmc_host, session_uri)
  ```
- `# ponytail: Basic auth for Redfish, sessions if per-BMC rate limiting needs amortization`

**Detection:** Run 20 consecutive power operations on the same BMC and check if the last ones fail with session/auth errors.

**Phase:** Core Redfish client phase. Auth strategy is a day-one decision.

---

### Pitfall 7: Asynchronous Power State Transitions Treated as Synchronous

**What goes wrong:** The Redfish reset action (`POST .../Actions/ComputerSystem.Reset`) returns HTTP 200/204 immediately. The code treats this as "done" and moves to the next step. But the hardware has not transitioned yet. The server is still powering on (POST, BIOS, bootloader) or powering off (OS shutdown, ACPI). If the next step depends on the new power state (e.g., SSH preflight depends on power being On), it fails because the transition is still in progress.

The DMTF Redfish Use-Case Checkers project documents exactly this: their test suite succeeds at "Reset Performed" but fails at "Power State Check" because the state has not changed yet.

**Why it happens:** HTTP 200 from a REST API universally means "the operation completed." Redfish breaks this convention: 200 means "the command was accepted," not "the state has changed."

**Consequences:**
- Intermittent failures: sometimes the server boots fast enough, sometimes it does not.
- Tests pass locally (single server, fast hardware) but fail in production (many servers, slow POST times).
- "Flaky" provisioning that works on retries -- because by the time the retry runs, the server has finished transitioning.

**Prevention:**
- After every power action, poll `PowerState` until it reaches the expected value or times out. Do not proceed to the next step until the poll confirms the transition.
- Poll intervals and timeouts by action type:
  | Action | Expected State | Poll Interval | Timeout |
  |--------|---------------|---------------|---------|
  | On | On | 5s | 60s |
  | ForceOff | Off | 5s | 30s |
  | GracefulRestart | On | 10s | 180s |
  | ForceRestart | On | 5s | 120s |
- GracefulRestart takes the longest because it includes OS shutdown + POST + OS boot. ForceOff is fastest because it is equivalent to pulling the power cord.
- Handle transitional states (`PoweringOn`, `PoweringOff`) as "in progress, keep polling." Handle `Unknown`, `Null`, `Reset` (returned by HPE Gen11+) as "transitional, keep polling" -- do not treat them as errors.

**Detection:** Issue a power-on action and immediately query `PowerState`. If the code does not poll and instead assumes `On` after the action returns, this pitfall is present.

**Phase:** Core Redfish client phase. The power-action wrapper must include the post-action poll.

---

### Pitfall 8: Vendor-Specific Redfish URI Paths Assumed Universal

**What goes wrong:** The code hardcodes `GET /redfish/v1/Systems/1` for the system resource. This works on Dell iDRAC and HPE iLO. On Supermicro, the system resource is `/redfish/v1/Systems/1`. On Lenovo XCC, it is `/redfish/v1/Systems/1`. But on some multi-chassis servers or blade servers, the system ID is not `1` -- it might be a UUID or a different identifier. The code 404s on these systems.

The MAAS Redfish driver hit this exact issue and had to add trailing-slash handling (Cisco BMCs reject requests without trailing slashes, Dell BMCs reject requests with trailing slashes) as a compatibility workaround.

**Why it happens:** Tutorials and examples always use `/redfish/v1/Systems/1` as the URI. Developers hardcode it because they test against one BMC vendor. The Redfish specification says the system collection is at `/redfish/v1/Systems`, but individual system URIs are opaque -- clients should discover them by reading the collection.

**Consequences:**
- Works on lab hardware (usually one vendor), fails in production (mixed vendors).
- 404 errors that look like auth failures or network issues.
- Requires per-vendor URI configuration, which operators find painful.

**Prevention:**
- Discover the system URI dynamically: `GET /redfish/v1/Systems` returns a `Members` array. Use the first member's `@odata.id` as the system URI.
  ```python
  async def _discover_system_uri(self, bmc_host: str) -> str:
      resp = await self._client.get(f"https://{bmc_host}/redfish/v1/Systems")
      members = resp.json()["Members"]
      if not members:
          raise RedfishError("No systems found in Redfish service")
      return members[0]["@odata.id"]
  ```
- Cache the discovered URI per BMC host for the lifetime of the operation (not across operations -- firmware updates can change URIs).
- If dynamic discovery is too slow for the use case, make the system path configurable with a sensible default: `RedfishSettings.system_path: str = "/redfish/v1/Systems/1"`.
- `# ponytail: hardcode /redfish/v1/Systems/1, add discovery if multi-vendor fleet grows`

**Detection:** Test against two different BMC vendors. If one works and the other 404s, this pitfall is present.

**Phase:** Core Redfish client phase. The URI strategy is a design decision, not a bug fix.

---

### Pitfall 9: ProvisioningStep Enum Not Extended for Power Steps

**What goes wrong:** The existing `ProvisioningStep` enum (state.py lines 19-39) has 17 members covering the SSH provisioning sequence. Redfish power operations are added to the provisioner but no new steps are added to the enum. The dashboard shows `PENDING` -> `PREFLIGHT` with no indication that a power-on is happening in between. If the power-on takes 3 minutes (boot wait), the dashboard shows the provisioning as "stuck on PENDING" or "stuck on PREFLIGHT" for minutes with no progress feedback.

**Why it happens:** Adding steps to the enum requires updating: the enum itself, the provisioner state transitions, the etcd state writer, the dashboard JS rendering, and any tests that assert on step sequences. Developers skip it to reduce scope, planning to "add it later."

**Consequences:**
- Operators see stuck provisioning with no explanation.
- They cancel and retry, creating duplicate operations.
- The error field does not capture power-related failures distinctly from SSH failures.

**Prevention:**
- Add new steps to `ProvisioningStep` for Redfish operations: `POWER_ON`, `POWER_OFF`, `POWER_STATUS_CHECK`. Insert `POWER_ON` before `PREFLIGHT` in the provisioning sequence. Insert `POWER_OFF` into the teardown sequence.
- The dashboard already renders `current_step` as a human-readable string. New step values will display automatically as long as the step names are readable.
- The `failed_step` field should reference the power step name when a Redfish operation fails, not a generic "preflight" or "provisioning" label.

**Detection:** Trigger a provisioning with auto-power-on and watch the dashboard. If the step does not change during the boot wait, this pitfall is present.

**Phase:** Provisioning integration phase. The enum must be extended before integrating Redfish into the provisioner.

---

### Pitfall 10: httpx Timeouts Too Short for BMC Response Times

**What goes wrong:** The existing `ProxySettings` timeout is 120s for read (LLM inference). The developer reuses this client or creates a new one with similar timeouts. But BMC response times are fundamentally different from HTTP API response times:
- `GET /redfish/v1/Systems/1` typically responds in 1-3 seconds.
- But a BMC under load (many sensors being polled, firmware update in progress, or I2C bus stuck) can take 30-60 seconds to respond.
- BMCs return HTTP 503 ("service temporarily unavailable") during internal operations (firmware updates, sensor cache rebuilds) and resume normal operation 30-120 seconds later.

If the httpx connect timeout is 5s (matching `ProxySettings.connect_timeout`) and the BMC is slow, every Redfish call times out.

**Why it happens:** Developers set timeouts based on expected response times of healthy BMCs. They do not account for degraded BMC states, which are common in large fleets.

**Consequences:**
- Power operations fail on servers with slow BMCs, even though the BMC is functional.
- Retry logic amplifies the problem: each retry also times out, consuming more BMC resources.
- False negatives: the system reports "BMC unreachable" when it is just slow.

**Prevention:**
- Set Redfish-specific timeouts in `RedfishSettings`, separate from proxy timeouts:
  ```python
  class RedfishSettings(BaseModel):
      connect_timeout: float = 10.0   # BMC TCP connect
      read_timeout: float = 60.0      # BMC response (can be slow)
      power_poll_timeout: float = 300.0  # Wait for power state transition
      power_poll_interval: float = 5.0   # Poll interval during transition
  ```
- Handle HTTP 503 from the BMC as a retryable error with exponential backoff, not as a failure. The BMC is telling you to try again later.
- Do NOT share the httpx client between Redfish and proxy/health-check operations. Different timeout profiles, different TLS contexts, different retry strategies.

**Detection:** Slow down BMC responses (e.g., run a firmware update) and check if power operations time out or succeed with patience.

**Phase:** Core Redfish client phase. Timeout configuration is part of the client setup.

---

## Minor Pitfalls

Issues that cause minor operational friction or developer confusion.

### Pitfall 11: BMC Hostname vs OS Hostname Mismatch

**What goes wrong:** The existing provisioner uses the OS hostname as the node identifier (the `hostname` parameter throughout `provisioner.py`). BMC management interfaces have their own hostname or IP, typically on a separate management VLAN (e.g., OS hostname `gpu-server-01.lab.example.com`, BMC hostname `gpu-server-01-bmc.mgmt.example.com` or IP `10.0.1.101`). The Redfish client needs the BMC address, but the provisioner passes the OS hostname.

**Why it happens:** The existing provisioning flow only needs the OS hostname (SSH connects to it directly). Adding Redfish requires a second address for the same physical server.

**Consequences:**
- Redfish calls fail with DNS resolution errors or connect to the wrong host.
- If the developer "fixes" this by adding a BMC address column to QUADS, it creates a data model mismatch.

**Prevention:**
- Add a BMC address resolution strategy. Options (simplest first):
  1. Convention: BMC address is `{hostname}-bmc.{domain}` or `{hostname}-mgmt.{domain}`. A string template in settings: `RedfishSettings.bmc_host_template: str = "{hostname}-mgmt"`.
  2. Lookup: A mapping dict in settings or environment: `INFERENCE_PROXY_REDFISH__BMC_HOSTS='{"gpu-01": "10.0.1.101"}'`.
  3. Discovery: Query QUADS API for the BMC address (if QUADS tracks it).
- Start with the convention approach. It covers 90% of lab environments where BMC hostnames follow a naming pattern.
- `# ponytail: hostname template, explicit mapping if convention breaks`

**Detection:** Log the BMC address used for each Redfish call. If it matches the OS hostname (instead of the BMC address), this pitfall is present.

**Phase:** Configuration phase. The BMC address strategy must be decided before the Redfish client can make its first call.

---

### Pitfall 12: Error Field in ProvisioningState Too Short for Diagnostic Value

**What goes wrong:** The current `ProvisioningState.error` field (state.py line 56) is `str | None`. Redfish errors from different steps need different error context: a power-on failure needs the BMC response code and `PowerState`; an SSH failure needs the command output and exit code; a health poll failure needs the HTTP response from vLLM.

Storing everything in a single `error` string loses structure. The dashboard cannot distinguish between error types or offer step-specific guidance. Operators see "power on failed" with no information about whether the BMC was unreachable, the credentials were wrong, or the server hardware is broken.

**Why it happens:** The v1.2 design assumed errors would be rare and simple (SSH connection failures). Redfish adds a second failure domain with its own error taxonomy.

**Consequences:**
- Operators cannot self-diagnose failures from the dashboard.
- Every failure requires SSH-ing to the gateway and reading structlog output.
- The milestone explicitly requires "step-level error capture" -- a single string per provisioning attempt does not meet this.

**Prevention:**
- Keep the `error` field as a short human-readable summary (what Pitfall 5 recommends).
- Add a `failed_step` that clearly identifies which step failed (already exists, but should use the new Redfish step names).
- For v1.5, the error field is sufficient if it contains a good summary. Do not over-engineer a structured error model until the need is demonstrated.
- Log the full error context (Redfish response body, HTTP status, BMC hostname) to structlog. The dashboard shows the summary; operators who need details check logs.
- `# ponytail: summary in error field, full context in structlog, structured error model if dashboard needs drill-down`

**Detection:** Trigger three different failure modes (BMC unreachable, wrong credentials, hardware fault) and verify the dashboard error messages are distinguishable.

**Phase:** Error capture phase. The error message quality is the entire point of the diagnostics feature.

---

### Pitfall 13: Retry Logic Interferes with Power State Machine

**What goes wrong:** The provisioner has retry logic for SSH operations (the admin API setup endpoint fires the provisioner as a background task, and the operator clicks "Retry" to re-run the entire sequence). If Redfish power-on is added as the first step and the provisioning fails at a later step (e.g., NVIDIA driver install), the retry re-runs the entire sequence including the power-on. The server is already on. The power-on either no-ops (if Pitfall 1 is handled) or fails (if not). Either way, the server reboots unnecessarily if `ForceRestart` is used instead of `On`.

**Why it happens:** The provisioner does not track which steps completed successfully. Retry = re-run everything from the beginning.

**Consequences:**
- Unnecessary server reboots kill any partially-installed state.
- Power cycling a running vLLM container (from a previous partial provisioning) drops in-flight inference requests.
- Operators lose confidence in the retry mechanism.

**Prevention:**
- The power-on step should be idempotent by design (Pitfall 1 prevention): if the server is already on, skip the power-on. This makes re-running the full sequence safe.
- For v1.5, do NOT add step-level resume to the provisioner. The complexity is not justified until the provisioning failure rate warrants it. The idempotent power-on check is sufficient.
- `# ponytail: idempotent power check makes full-sequence retry safe, step-level resume if failure rate > 10%`

**Detection:** Run provisioning, let it fail at a late step (e.g., health poll timeout), retry, and verify the server is not rebooted.

**Phase:** Provisioning integration phase. The idempotent power check is part of the provisioner's power-on step.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Redfish client (HTTP wrapper) | TLS verify=False leak (#4), session exhaustion (#6), timeout too short (#10), hardcoded URIs (#8) | Scoped httpx client with Redfish-specific TLS and timeouts, Basic auth, discover system URI |
| Power actions (on/off/restart) | ForceOff on off server (#1), async transitions (#7) | Check-before-act pattern, post-action power state polling |
| Credential management | Password in logs (#2) | SecretStr, sanitize error messages, never log credentials |
| Provisioner integration | SSH before boot (#3), enum not extended (#9), retry reboots server (#13) | Boot wait polling, new ProvisioningStep members, idempotent power check |
| Error capture & display | Raw Redfish JSON in dashboard (#5), error field too terse (#12) | Human-readable error summaries, map Redfish error codes, full context in structlog |
| BMC addressing | Hostname mismatch (#11) | BMC host template or mapping in settings |

---

## Sources

- [MAAS Redfish power driver quirks (Canonical Discourse)](https://discourse.maas.io/t/redfish-power-driver-quirks/512) -- vendor compatibility, trailing slashes, HTTP 400 on transitional states
- [MAAS Redfish power driver source (GitHub)](https://github.com/canonical/maas/blob/master/src/provisioningserver/drivers/power/redfish.py) -- retry logic, session management, ETag handling, state polling
- [MAAS Bug 2092172: Redfish I/O operation on closed file](https://bugs.launchpad.net/maas/+bug/2092172) -- race conditions in power state transitions, lag between command and state change
- [MAAS Bug 2117200: Machines get into inconsistent power state](https://launchpad.net/maas/+bug/2117200) -- power type switching during commissioning
- [DMTF Redfish Use-Case Checkers Issue #40](https://github.com/DMTF/Redfish-Use-Case-Checkers/issues/40) -- PowerState check fails after reset actions
- [OpenBMC state management design doc (GitHub)](https://github.com/openbmc/docs/blob/master/designs/state-management-and-external-interfaces.md) -- ResetType mapping, transitional states
- [OpenBMC bmcweb Issue #158: GracefulRestart flushes sessions](https://github.com/openbmc/bmcweb/issues/158) -- session invalidation on BMC restart
- [HPE Redfish authentication and sessions](https://servermanagementportal.ext.hpe.com/docs/concepts/redfishauthentication) -- session limits (16 max), timeout configuration, token lifecycle
- [Supermicro Redfish User Guide](https://www.supermicro.com/manuals/other/RedfishUserGuide.pdf) -- session timeout 30-86400s, Basic vs session auth
- [DMTF Redfish error responses](https://redfish.redoc.ly/docs/concepts/errorresponses/) -- ExtendedInfo format, MessageId structure, error registries
- [DMTF Python Redfish library (GitHub)](https://github.com/DMTF/python-redfish-library) -- uses requests not httpx, auth patterns, proxy config
- [Dell PowerEdge: Graceful Shutdown/Restart fails](https://www.dell.com/support/kbdoc/en-us/000224986/poweredge-graceful-shutdown-or-graceful-restart-operations-using-redfish-fails-for-windows-server) -- GracefulShutdown requires active OS session
- [DMTF Redfish Resource and Schema Guide](https://www.dmtf.org/sites/default/files/standards/documents/DSP2046_2024.2.html) -- ResetType enum, AllowableValues, PowerState values
- [Redfish server states (SourceForge)](https://sourceforge.net/p/redfish-lab/wiki/Master-the-Redfish-Server-States/) -- PostState progression, boot wait monitoring
- [httpx SSL documentation](https://www.python-httpx.org/advanced/ssl/) -- custom SSL context, verify parameter, truststore
- [OpenBMC TLS configuration (GitHub)](https://github.com/openbmc/docs/blob/master/security/TLS-configuration.md) -- self-signed cert defaults, certificate replacement
- [BMC Communication guide (THNKBIG)](https://www.thnkbig.com/blog/bmc-communication-ipmi-redfish/) -- protocol mixing, clock issues, 503 from sensor polling
- Existing codebase: `inference_proxy/provisioning/provisioner.py` (state machine, error handling, SSH operations)
- Existing codebase: `inference_proxy/provisioning/state.py` (ProvisioningStep enum, ProvisioningState model)
- Existing codebase: `inference_proxy/config/settings.py` (SSHSettings pattern, ProvisioningSettings)
- Existing codebase: `inference_proxy/models/admin.py` (TaskStatusResponse with error field)
