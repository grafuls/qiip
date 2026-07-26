# Phase 26: llmfit Installation - Research

**Researched:** 2026-07-26
**Domain:** Shell scripting (setup.sh), Python enum (state.py), provisioning integration
**Confidence:** HIGH

## Summary

This phase adds two things: (1) an `install_llmfit()` function and `soft_step()` wrapper in `auto-vllm/setup.sh`, and (2) a `LLMFIT_INSTALL` member in the `ProvisioningStep` enum. The scope is small -- two files modified, two test files updated.

All patterns already exist in the codebase. `install_llmfit()` follows the `install_nvidia_driver()` idempotent pattern. `soft_step()` is a copy of `step()` with `exit 1` replaced by `return 0` and `FAIL` replaced by `WARN`. The `LLMFIT_VERSION` env var follows the `NVIDIA_DRIVER_VERSION` pattern.

**Primary recommendation:** Follow existing patterns exactly. The only novel element is `soft_step()`, which is 6 lines of bash.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Add `LLMFIT_INSTALL` to `ProvisioningStep` enum so the step appears in dashboard provisioning progress.
- **D-02:** New `soft_step()` wrapper in `setup.sh` that emits `[STEP:name:START]` / `[STEP:name:OK]` / `[STEP:name:WARN]` markers. On failure, prints WARN (not FAIL) and continues -- no `exit 1`. Existing `step()` wrapper stays unchanged.
- **D-03:** Provisioner does NOT parse WARN markers specially. They flow through the raw SSH log buffer (already captured by `LogBuffer`), no special structlog treatment on the Python side.

### Claude's Discretion
- **Download method:** Follow the existing `NVIDIA_DRIVER_VERSION` env-var pattern -- add `LLMFIT_VERSION` with a pinned default and `LLMFIT_URL` derived from it. Download prebuilt binary from GitHub releases.
- **Air-gap handling:** No special SCP pre-staging. Download fails, `soft_step()` emits WARN, provisioning continues.
- **Installation function:** Idempotent `install_llmfit()` -- skip if `/usr/local/bin/llmfit` already exists.

### Deferred Ideas (OUT OF SCOPE)
None.

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| INST-01 | llmfit binary is installed on target servers during provisioning via prebuilt binary download | `install_llmfit()` in setup.sh downloads from GitHub releases URL, extracts tarball, installs to `/usr/local/bin/llmfit` |
| INST-02 | llmfit installation is a non-fatal provisioning step (failure doesn't block setup) | `soft_step()` wrapper emits WARN on failure instead of FAIL, does not `exit 1` |

</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| llmfit binary download/install | Remote server (setup.sh) | -- | Runs on target GPU server during SSH provisioning |
| Non-fatal step wrapper | Remote server (setup.sh) | -- | Shell-level control flow, no Python involvement |
| Step tracking in dashboard | Python (state.py enum) | -- | Enum member enables provisioner to track step via existing marker parsing |

## Standard Stack

No new dependencies. This phase modifies:
- `auto-vllm/setup.sh` (bash)
- `inference_proxy/provisioning/state.py` (Python enum)
- `tests/provisioning/test_state.py` (test update)

### External Binary
| Binary | Version | Source | Platform |
|--------|---------|--------|----------|
| llmfit | v1.1.6 (pinned default) | `https://github.com/AlexsJones/llmfit/releases/download/v1.1.6/llmfit-v1.1.6-x86_64-unknown-linux-musl.tar.gz` | x86_64 Linux (static musl) |

[VERIFIED: GitHub API `gh api repos/AlexsJones/llmfit/releases/latest`] -- v1.1.6 is the latest release. Asset `llmfit-v1.1.6-x86_64-unknown-linux-musl.tar.gz` exists with `.sha256` checksum file.

## Architecture Patterns

### Pattern 1: Env-Var Defaults (existing in setup.sh)

**What:** Configurable values with pinned defaults at top of script.
**Source:** Lines 5-9 of `auto-vllm/setup.sh`

```bash
# Existing pattern:
NVIDIA_DRIVER_VERSION="${NVIDIA_DRIVER_VERSION:-580.126.09}"
NVIDIA_DRIVER_URL="${NVIDIA_DRIVER_URL:-https://us.download.nvidia.com/tesla/${NVIDIA_DRIVER_VERSION}/NVIDIA-Linux-x86_64-${NVIDIA_DRIVER_VERSION}.run}"

# New (same pattern):
LLMFIT_VERSION="${LLMFIT_VERSION:-1.1.6}"
LLMFIT_URL="${LLMFIT_URL:-https://github.com/AlexsJones/llmfit/releases/download/v${LLMFIT_VERSION}/llmfit-v${LLMFIT_VERSION}-x86_64-unknown-linux-musl.tar.gz}"
```

### Pattern 2: Idempotent Step Function (existing in setup.sh)

**What:** Check-then-install with early return if already done.
**Source:** `install_nvidia_driver()` at line 32, `install_vllm()` at line 61.

```bash
install_llmfit() {
    if [ -x /usr/local/bin/llmfit ]; then
        echo "llmfit already installed, skipping"
        return 0
    fi
    wget -q "${LLMFIT_URL}" -O /tmp/llmfit.tar.gz
    tar -xzf /tmp/llmfit.tar.gz -C /tmp/
    sudo install -m 755 "$(find /tmp/ -name llmfit -type f -print -quit)" /usr/local/bin/llmfit
    rm -rf /tmp/llmfit.tar.gz /tmp/llmfit-*
}
```

Note: The tarball extraction produces a directory structure. The official install script uses `find` to locate the binary within the archive. This is the correct approach. [CITED: llmfit install.sh at https://llmfit.axjns.dev/install.sh]

### Pattern 3: soft_step() Wrapper (new, modeled on step())

**What:** Same as `step()` but WARN on failure instead of FAIL+exit.
**Source:** `step()` at line 12 of setup.sh.

```bash
# Existing step() for reference:
step() {
    local name="$1"; shift
    echo "[STEP:${name}:START]"
    if "$@"; then
        echo "[STEP:${name}:OK]"
    else
        echo "[STEP:${name}:FAIL]"
        exit 1
    fi
}

# New soft_step():
soft_step() {
    local name="$1"; shift
    echo "[STEP:${name}:START]"
    if "$@"; then
        echo "[STEP:${name}:OK]"
    else
        echo "[STEP:${name}:WARN] (non-fatal, continuing)"
    fi
}
```

### Pattern 4: ProvisioningStep Enum (existing in state.py)

**What:** StrEnum where values match setup.sh step names (snake_case).
**Key constraint:** Provisioner does `ProvisioningStep(step_name)` from parsed `[STEP:name:START]` markers. The enum value must match the step name used in `soft_step "llmfit_install" install_llmfit`.

```python
# Add between FIREWALL and STARTING_VLLM (matching execution order in setup.sh):
LLMFIT_INSTALL = "llmfit_install"
```

### Provisioner Regex Compatibility

**Critical detail:** `STEP_PATTERN = re.compile(r"\[STEP:(\w+):(START|OK|FAIL)\]")` at line 38 of provisioner.py.

- `[STEP:llmfit_install:START]` -- MATCHES. Provisioner calls `ProvisioningStep("llmfit_install")`, updates state. Dashboard shows step.
- `[STEP:llmfit_install:OK]` -- MATCHES. Logged as info.
- `[STEP:llmfit_install:WARN]` -- DOES NOT MATCH. This is correct per D-03. The WARN line flows through as plain stdout text into LogBuffer.

**No changes needed to provisioner.py or its regex.** This is by design (D-03).

### Anti-Patterns to Avoid
- **Piping curl to sh for install:** The official `curl | sh` installer resolves latest version dynamically. We pin `LLMFIT_VERSION` instead for reproducibility across fleet.
- **Using `step()` for llmfit install:** Would make provisioning fail on download errors (air-gap, rate limit). Must use `soft_step()`.
- **Adding WARN to STEP_PATTERN regex:** Per D-03, WARN markers are informational only. Adding them to the regex would require handling code in provisioner for no benefit.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Binary extraction from tarball | Custom path parsing | `find /tmp/ -name llmfit -type f` | Tarball directory structure may vary between releases |

## Common Pitfalls

### Pitfall 1: Tarball Directory Structure
**What goes wrong:** Assuming `tar -xzf` puts the binary at a fixed path like `/tmp/llmfit`.
**Why it happens:** llmfit tarballs contain a directory (e.g., `llmfit-v1.1.6-x86_64-unknown-linux-musl/llmfit`).
**How to avoid:** Use `find` to locate the binary after extraction, same as the official install script.

### Pitfall 2: Test Count Assertion
**What goes wrong:** Adding `LLMFIT_INSTALL` to enum but forgetting to update `test_member_count` and `test_member_values` in `tests/provisioning/test_state.py`.
**Current state:** `test_member_count` asserts `len(ProvisioningStep) == 18`. After adding `LLMFIT_INSTALL`, must be 19. `test_member_values` has an expected dict that must include the new member.

### Pitfall 3: Enum Ordering
**What goes wrong:** Adding `LLMFIT_INSTALL` at the wrong position in the enum. While StrEnum ordering doesn't affect functionality, it should match execution order in setup.sh for readability.
**How to avoid:** Insert after `FIREWALL` and before `STARTING_VLLM`, matching where `soft_step "llmfit_install" install_llmfit` appears in the main section of setup.sh.

### Pitfall 4: set -e Interaction with soft_step
**What goes wrong:** `set -e` (errexit) at the top of setup.sh could cause the script to exit if a command inside `install_llmfit()` fails, even though `soft_step()` is designed to catch failures.
**Why it's safe:** `soft_step()` wraps the function call in an `if` statement. In bash, commands in the condition of `if` are exempt from `set -e`. So a failing `wget` or `tar` inside `install_llmfit()` will cause the `if` to take the else branch, not exit the script. This is the same reason `step()` works with `set -e` today.

## Code Examples

### Complete setup.sh Changes

```bash
# --- Configurable defaults --- (add after VLLM_PORT line)
LLMFIT_VERSION="${LLMFIT_VERSION:-1.1.6}"
LLMFIT_URL="${LLMFIT_URL:-https://github.com/AlexsJones/llmfit/releases/download/v${LLMFIT_VERSION}/llmfit-v${LLMFIT_VERSION}-x86_64-unknown-linux-musl.tar.gz}"

# --- Soft step wrapper --- (add after step() function)
soft_step() {
    local name="$1"; shift
    echo "[STEP:${name}:START]"
    if "$@"; then
        echo "[STEP:${name}:OK]"
    else
        echo "[STEP:${name}:WARN] (non-fatal, continuing)"
    fi
}

# --- New step function ---
install_llmfit() {
    if [ -x /usr/local/bin/llmfit ]; then
        echo "llmfit already installed, skipping"
        return 0
    fi
    wget -q "${LLMFIT_URL}" -O /tmp/llmfit.tar.gz
    tar -xzf /tmp/llmfit.tar.gz -C /tmp/
    sudo install -m 755 "$(find /tmp/ -name llmfit -type f -print -quit)" /usr/local/bin/llmfit
    rm -rf /tmp/llmfit.tar.gz /tmp/llmfit-*
}

# --- Main --- (add after step firewall configure_firewall)
soft_step llmfit_install install_llmfit
```

### Complete state.py Change

```python
# Add after FIREWALL = "firewall":
LLMFIT_INSTALL = "llmfit_install"
```

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio |
| Config file | `pyproject.toml` |
| Quick run command | `uv run pytest tests/provisioning/test_state.py -x` |
| Full suite command | `uv run pytest tests/ -x` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INST-01 | llmfit binary download/install in setup.sh | manual-only | N/A (bash script runs on remote servers via SSH) | N/A |
| INST-02 | Non-fatal step (soft_step emits WARN, no exit) | manual-only | N/A (bash script behavior) | N/A |
| D-01 | LLMFIT_INSTALL in ProvisioningStep enum | unit | `uv run pytest tests/provisioning/test_state.py -x` | Yes (needs update) |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/provisioning/test_state.py -x`
- **Per wave merge:** `uv run pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] Update `tests/provisioning/test_state.py::TestProvisioningStepEnum::test_member_count` -- assert 19 not 18
- [ ] Update `tests/provisioning/test_state.py::TestProvisioningStepEnum::test_member_values` -- add `LLMFIT_INSTALL: llmfit_install`

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `wget` is available on target servers (RHEL/Fedora with `wget` installed in `run_system_update`) | Code Examples | Low -- `wget` is installed by `run_system_update` step which runs before llmfit install. Could use `curl` as alternative. |
| A2 | x86_64-unknown-linux-musl is the correct platform for all target servers | Standard Stack | Low -- all QUADS lab servers are x86_64 Linux. If ARM servers appear, `LLMFIT_URL` env var override handles it. |

## Open Questions

None. All decisions are locked and patterns are established.

## Sources

### Primary (HIGH confidence)
- `auto-vllm/setup.sh` -- existing step(), env-var, and idempotent install patterns (direct codebase read)
- `inference_proxy/provisioning/state.py` -- ProvisioningStep enum with 18 members (direct codebase read)
- `inference_proxy/provisioning/provisioner.py` line 38 -- STEP_PATTERN regex (direct codebase read)
- `tests/provisioning/test_state.py` -- test assertions for member count and values (direct codebase read)
- GitHub API `repos/AlexsJones/llmfit/releases/latest` -- v1.1.6, asset names confirmed
- llmfit install script at `https://llmfit.axjns.dev/install.sh` -- tarball structure, find-based binary extraction

### Secondary (MEDIUM confidence)
- [llmfit GitHub](https://github.com/AlexsJones/llmfit) -- repository structure, release patterns
- [llmfit on lib.rs](https://lib.rs/crates/llmfit) -- Rust crate metadata

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, just bash and one Python enum member
- Architecture: HIGH -- all patterns exist in codebase, direct copy with minor modification
- Pitfalls: HIGH -- verified regex behavior, test assertions, and set-e interaction by reading source

**Research date:** 2026-07-26
**Valid until:** 2026-08-26 (stable -- bash patterns and enum additions don't change)
