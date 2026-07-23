# Domain Pitfalls

**Domain:** llmfit CLI Integration for Hardware-Aware Model Selection in Inference Proxy Gateway
**Researched:** 2026-07-23
**Confidence:** HIGH (verified against llmfit GitHub/docs, existing provisioner codebase, asyncssh issue tracker, NVIDIA driver documentation)

**Scope:** Pitfalls specific to adding llmfit CLI integration (v1.6) to the existing SSH-based provisioning pipeline. Prior pitfalls (v1.0-v1.5) are in git history.

---

## Critical Pitfalls

Mistakes that cause failed installations, incorrect model recommendations, or require provisioning pipeline rework.

### Pitfall 1: Installing Rust/Cargo Toolchain on Remote Servers Instead of Using Prebuilt Binaries

**What goes wrong:** The developer installs llmfit via `cargo install llmfit` on target servers because it seems like the natural Rust installation path. This pulls the full Rust toolchain (`rustup` + `cargo` + `rustc`), downloads and compiles llmfit from source including all dependencies, and takes 5-15 minutes per server on a cold cache. The compilation requires gcc, make, and development headers to already be present. On a fleet of 20 servers, this is 100-300 minutes of build time across the fleet, and any compilation failure (missing openssl-devel, incompatible glibc, disk space exhaustion from the `~/.cargo` registry cache) fails the entire provisioning run for that server.

The existing setup.sh already runs 5+ minutes for system updates, NVIDIA driver install, and vLLM pip install. Adding a Rust toolchain install doubles provisioning time for a single CLI binary.

**Why it happens:** Developers familiar with Rust reach for `cargo install`. The llmfit README mentions it as an installation option. It seems robust because it compiles from source -- but "robust" on a developer workstation is "fragile" in automated provisioning.

**Consequences:**
- Provisioning time doubles or triples per server.
- `rustup` prompts for interactive input by default, hanging the SSH session indefinitely. The `-y` flag is required but easy to forget.
- After `rustup` install, `source $HOME/.cargo/env` must be called in the same shell session, or `cargo` is not on PATH. Separate `ssh_client.run_streaming()` calls each start a fresh shell -- PATH changes from one command do not persist to the next.
- 500MB+ disk usage for the Rust toolchain that is never used again after the single `cargo install`.
- Compilation failures are opaque to the operator: the dashboard shows "Failed at step 'llmfit_install'" with 200 lines of compiler output.

**Prevention:**
- Use the prebuilt binary. llmfit publishes `x86_64-unknown-linux-musl` static binaries on every GitHub release. The official install script (`curl -fsSL https://llmfit.org/install.sh | sh`) downloads the correct binary for the platform and places it in `/usr/local/bin` or `~/.local/bin`. Alternatively, there is a PyPI wrapper (`pip install llmfit`) that bundles the binary.
- For maximum control and reproducibility, download the tarball directly in the provisioning script:
  ```bash
  LLMFIT_VERSION="${LLMFIT_VERSION:-v0.9.38}"
  curl -fsSL "https://github.com/AlexsJones/llmfit/releases/download/${LLMFIT_VERSION}/llmfit-${LLMFIT_VERSION}-x86_64-unknown-linux-musl.tar.gz" \
      -o /tmp/llmfit.tar.gz
  tar -xzf /tmp/llmfit.tar.gz -C /usr/local/bin llmfit
  chmod +x /usr/local/bin/llmfit
  rm /tmp/llmfit.tar.gz
  ```
- Pin the version. Do not use `latest` redirect in automation -- it introduces non-determinism across fleet nodes provisioned at different times.
- The musl-linked binary has no runtime dependencies beyond a Linux 3.2+ kernel. No glibc version concerns, no shared library loading failures.
- Add the version to `ProvisioningSettings` or `LlmfitSettings` so operators can upgrade fleet-wide by changing one env var.

**Detection:** Check the provisioning script for `rustup`, `cargo install`, or `cargo build`. If present, this pitfall is active.

**Phase:** llmfit installation phase. This is the first design decision and must be correct before writing any code.

---

### Pitfall 2: No Command Timeout on `llmfit recommend` via SSH

**What goes wrong:** The existing `SSHClient.run_streaming()` (ssh_client.py lines 69-116) has no command execution timeout. It has a `connect_timeout` (10 seconds for TCP connection), but once connected, `run_streaming()` will block indefinitely waiting for stdout to complete. The `llmfit recommend --json` command runs hardware detection which shells out to `nvidia-smi` (and potentially other probes). If `nvidia-smi` hangs (common when the GPU is in a bad state, driver mismatch, or the I2C bus is stuck), llmfit hangs, the SSH process hangs, and the provisioner's asyncio task hangs forever.

The existing provisioner avoids this problem for `setup.sh` and `start-vllm.sh` because those scripts are expected to run for minutes and produce continuous output (step markers). But `llmfit recommend` is expected to complete in seconds. A hang looks identical to "still running" from the provisioner's perspective.

**Why it happens:** asyncssh's `create_process()` (used in `run_streaming()`) does not have a built-in command timeout. The `timeout` parameter on `conn.run()` exists but is not used here because the codebase uses `create_process()` + `async for line in process.stdout` for streaming. There is no equivalent timeout on the streaming path.

**Consequences:**
- A single server with a hung GPU wedges the provisioner's asyncio task pool.
- The dashboard shows the provisioning as "stuck" on the llmfit step indefinitely.
- No error is raised, no cleanup happens, the operator must manually cancel.
- If the gateway is restarted, the orphaned SSH session on the remote server may keep the llmfit process running.

**Prevention:**
- Wrap the llmfit SSH call in `asyncio.wait_for()` with a generous but finite timeout (e.g., 60 seconds). llmfit's hardware detection + recommendation typically completes in 2-5 seconds; 60 seconds catches hangs without false positives.
  ```python
  async def run_llmfit(self, hostname: str) -> str:
      try:
          return await asyncio.wait_for(
              self._ssh_run_command(hostname, "llmfit recommend --json --limit 10"),
              timeout=self._settings.llmfit_timeout,  # e.g., 60
          )
      except asyncio.TimeoutError:
          raise ProvisioningError(
              f"llmfit timed out after {self._settings.llmfit_timeout}s on {hostname} "
              "(possible GPU driver hang)"
          )
  ```
- Add `llmfit_timeout: int = 60` to the settings model (either `ProvisioningSettings` or a new `LlmfitSettings`).
- Consider adding a general command timeout to `SSHClient.run_streaming()` as a broader improvement, but the llmfit-specific timeout is sufficient for v1.6.
- After timeout, the remote llmfit process is still running. asyncssh will close the channel when the connection context exits, which sends SIGHUP to the remote process. This is acceptable cleanup for a read-only command.

**Detection:** Mock `nvidia-smi` on a test server to hang indefinitely (`sleep infinity`), then trigger llmfit via provisioning. If the provisioner hangs rather than timing out, this pitfall is present.

**Phase:** llmfit execution phase. The timeout must wrap every SSH invocation of llmfit.

---

### Pitfall 3: Parsing llmfit JSON Output as a Stable API Contract

**What goes wrong:** The developer parses `llmfit recommend --json` output, extracting fields like `models[].name`, `models[].score`, `models[].quantization`, etc. The parsing code hardcodes field names and assumes a specific JSON structure. llmfit releases every few days (v0.4 to v0.9+ in 5 months, Feb-Jul 2026). The JSON output schema has no stability guarantee -- it is a CLI tool, not a library with a versioned API. A llmfit update changes a field name (e.g., `score` -> `composite_score`, or `models` -> `recommendations`), and the parsing breaks across the entire fleet the next time a server is provisioned with a newer binary.

The existing codebase already has this pattern: `start-vllm.sh` output is parsed via `MODEL_PATTERN = re.compile(r"#\s*Model:\s+(.+)")` in provisioner.py line 39. This works because the gateway controls both ends (it writes setup.sh, it reads the output). With llmfit, the gateway controls neither the output format nor the release cadence.

**Why it happens:** `--json` flags on CLI tools feel like APIs. They are not. They are convenience output formats that change without semver guarantees unless explicitly documented as stable. llmfit's docs describe `--json` output for scripting but do not commit to schema stability.

**Consequences:**
- Fleet-wide recommendation failures when llmfit is updated on new servers (different versions across fleet if not pinned).
- Silent data corruption if a field is renamed but the JSON still parses (e.g., a score field changes meaning from 0-100 to 0.0-1.0).
- Version skew across the fleet: servers provisioned last week have llmfit 0.9.30, servers provisioned today have 0.9.38, and the JSON schemas differ.

**Prevention:**
- Pin the llmfit version in settings (Pitfall 1 prevention). Every server gets the same binary, so the JSON format is consistent across the fleet.
- Parse defensively with Pydantic models that use `model_config = ConfigDict(extra="ignore")`:
  ```python
  class LlmfitRecommendation(BaseModel):
      model_config = ConfigDict(extra="ignore")
      name: str
      # Accept either field name for forward compatibility
      score: float | None = None
      composite_score: float | None = None

      @property
      def effective_score(self) -> float:
          return self.composite_score or self.score or 0.0
  ```
- Validate the parsed output: if the JSON parses but has zero recommendations or missing critical fields, raise a clear error rather than returning empty results.
- Write a version check: after installing llmfit, run `llmfit --version` and compare against the expected version. Log a warning if they differ (the binary may have been installed by a previous provisioning run with a different version).
- When the llmfit version is bumped in settings, test the JSON parsing against the new version's actual output before rolling out fleet-wide.

**Detection:** Run the parsing code against two different llmfit versions' JSON output. If it breaks on the newer version, this pitfall is present.

**Phase:** llmfit output parsing phase. The Pydantic model for llmfit output must be designed for defensive parsing from the start.

---

### Pitfall 4: llmfit Detects No GPU Because nvidia-smi Is Not on PATH or Driver Not Loaded

**What goes wrong:** llmfit uses `nvidia-smi` to detect NVIDIA GPUs and their VRAM. In the existing provisioning flow, `setup.sh` installs the NVIDIA driver (potentially from a `.run` file). After driver installation, `nvidia-smi` is available. But there are several edge cases where nvidia-smi is present but non-functional:

1. **Driver installed but kernel module not loaded.** The existing `install_nvidia_driver()` in setup.sh handles this (modprobe nvidia), but if setup.sh is skipped on a retry (because the operator thinks "setup already ran"), `nvidia-smi` may fail with "NVIDIA-SMI has failed because it couldn't communicate with the NVIDIA driver."

2. **Driver installed via RPM but kmod not built for running kernel.** The existing setup.sh already handles this case (lines 41-50), but it can still fail if `dkms autoinstall` and `akmods --force` both fail and the fallback `.run` installer is used. After the `.run` installer, `nvidia-smi` may require a reboot that never happens.

3. **nvidia-smi in a non-standard PATH.** The `.run` installer puts nvidia-smi in `/usr/bin/nvidia-smi`. RPM packages put it in `/usr/bin/nvidia-smi`. But some installations put it in `/usr/local/cuda/bin/nvidia-smi` which may not be on the SSH session's PATH (non-login shells get a minimal PATH).

When llmfit cannot find nvidia-smi, it falls back to CPU-only detection and recommends models that fit in RAM only -- completely ignoring the GPU hardware. The recommendations are valid (they will run on CPU), but useless for a GPU inference server.

**Why it happens:** llmfit handles missing nvidia-smi gracefully by design -- it is not a bug in llmfit. The problem is that the provisioner does not verify GPU detection succeeded before trusting the recommendations.

**Consequences:**
- llmfit returns CPU-only model recommendations for a server with 8x A100 GPUs.
- The operator sees "recommended: Qwen2.5-3B-Instruct" for a server that could run a 70B model.
- If the operator does not notice and accepts the recommendation, the server runs a tiny model at a fraction of its capacity.
- No error is raised -- llmfit exits 0 with valid (but wrong) recommendations.

**Prevention:**
- Run llmfit only after the existing `_verify_gpu()` step has confirmed nvidia-smi works. The existing provisioner already runs `nvidia-smi --query-gpu=name --format=csv,noheader` in `_verify_gpu()`. If that passes, llmfit should also detect GPUs.
- After parsing llmfit's JSON output, validate that the detected hardware includes GPU VRAM. If llmfit's system info shows 0 VRAM or no GPU backend, raise an error:
  ```python
  if not recommendations or all(r.run_mode == "cpu_only" for r in recommendations):
      raise ProvisioningError(
          f"llmfit detected no GPU on {hostname} -- nvidia-smi may have failed. "
          "Check driver status."
      )
  ```
- Alternatively, run `llmfit system --json` first, check that it reports CUDA backend and non-zero VRAM, then run `llmfit recommend --json`. This adds one extra SSH call but catches detection failures early with a clear diagnostic.
- Consider passing `--memory` override to llmfit using the VRAM value already captured by `_verify_gpu()` / `detect_gpu_info()` in start-vllm.sh. This makes llmfit's VRAM detection a redundant check rather than the sole source of truth.

**Detection:** Unload the nvidia kernel module (`sudo rmmod nvidia`) and run llmfit. If it returns CPU-only recommendations without any error, this pitfall is present.

**Phase:** llmfit execution phase. GPU detection validation must happen before or immediately after running llmfit.

---

### Pitfall 5: llmfit Installation Step Fails and Blocks Entire Provisioning

**What goes wrong:** llmfit installation is added as a mandatory step in the provisioning sequence (like NVIDIA driver or vLLM install). The GitHub release download fails because: the server has no outbound internet access (common in air-gapped labs), GitHub is rate-limited (unauthenticated API: 60 requests/hour, release downloads may be throttled), DNS resolution fails, or the pinned version no longer exists (release was deleted or renamed).

The provisioner marks the node as FAILED. The operator cannot deploy a model on this server, even though the server is fully capable -- it has GPUs, drivers, vLLM, and NFS all working. The llmfit failure blocks a server that could be serving inference requests with the existing hardcoded model selection in start-vllm.sh.

**Why it happens:** The developer adds llmfit install as a step in the main provisioning pipeline (`setup.sh` or a new step in the provisioner). Failures in any step cascade to FAILED status. llmfit is treated as a hard dependency even though it is an advisory tool (recommends models, does not run them).

**Consequences:**
- A transient network issue during llmfit download blocks server provisioning entirely.
- Air-gapped labs cannot use llmfit without pre-staging the binary.
- The existing hardcoded model selection in start-vllm.sh (which works) is not used as a fallback.

**Prevention:**
- Separate llmfit from the critical provisioning path. llmfit is an advisory tool that helps operators choose the right model. It is not required for the server to serve inference. Two architectural approaches:

  **Option A (recommended): Separate llmfit from provisioning entirely.** llmfit runs on-demand via the admin API (e.g., `GET /admin/nodes/{hostname}/recommendations`), not as part of the setup sequence. The operator clicks "Get Recommendations" in the dashboard after the server is provisioned, or before selecting which model to deploy. If llmfit is not installed, the endpoint returns a 404 or a message saying "install llmfit first."

  **Option B: Install in provisioning, but as a non-fatal step.** If llmfit install fails, log a warning and continue. The server provisions with the existing hardcoded model selection. The operator can install llmfit later and re-run recommendations.

- If llmfit binary must be installed during provisioning, pre-stage the binary: download it once to the gateway host and SCP it to target servers via the existing `ssh_client.upload()` method. This avoids each target server needing outbound internet access.
  ```python
  # Upload pre-staged binary from gateway to target
  await self._ssh_client.upload(hostname, self._settings.llmfit_binary_path, "/usr/local/bin/llmfit")
  await self._ssh_run_command(hostname, "chmod +x /usr/local/bin/llmfit")
  ```
- Make llmfit binary path configurable: `LlmfitSettings.binary_path: Path | None = None`. When None, llmfit features are disabled (same pattern as `QUADSSettings.base_url` and `RedfishSettings.bmc_username`).

**Detection:** Disconnect outbound internet on a target server and trigger provisioning. If provisioning fails at the llmfit step instead of continuing with degraded model selection, this pitfall is present.

**Phase:** Architecture decision phase. Whether llmfit is in-band or out-of-band is the most important design decision for this milestone.

---

## Moderate Pitfalls

Mistakes that cause operational friction, degraded recommendation quality, or confusing behavior.

### Pitfall 6: Multi-GPU VRAM Aggregation Mismatch Between llmfit and vLLM

**What goes wrong:** llmfit aggregates VRAM across all detected GPUs (e.g., 4x A100 80GB = 320GB total VRAM) and recommends models that fit in 320GB. The existing start-vllm.sh also calculates `total_vram=$((GPU_COUNT * GPU_VRAM_GB))`. But llmfit and vLLM disagree on how much VRAM is "available":

- llmfit scores based on total VRAM minus a safety margin.
- vLLM's `--gpu-memory-utilization` defaults to 0.90, meaning only 90% of VRAM is usable.
- The existing start-vllm.sh sets `GPU_MEM_UTIL` between 0.75 and 0.90 depending on GPU model.
- If CUDA context, framework overhead, or other processes consume VRAM, the available amount is lower than total.

llmfit recommends a 70B model that "fits" in 320GB total. vLLM configured with `--gpu-memory-utilization 0.90` only sees 288GB. The model fails to load with OOM at the health poll step -- after the operator already chose it based on llmfit's recommendation.

There is also a known llmfit bug (GitHub issue #68): with 2 GPUs, only 1 GPU's VRAM was factored into the calculation. While reportedly fixed, edge cases with mixed GPU types or partially failed GPUs may still exhibit this.

**Why it happens:** llmfit is a standalone tool that does not know about vLLM's memory utilization settings. It recommends based on raw hardware specs. The translation from "llmfit says it fits" to "vLLM can actually load it" requires accounting for the memory utilization multiplier.

**Consequences:**
- Operator selects a model that llmfit says fits, vLLM fails to load it.
- The failure happens at the health poll step (minutes into provisioning), not at recommendation time (seconds).
- Operators lose trust in llmfit recommendations and revert to manual model selection.

**Prevention:**
- Pass `--memory` to llmfit with the effective available VRAM, not the total:
  ```bash
  EFFECTIVE_VRAM_GB=$(python3 -c "print(int(${GPU_COUNT} * ${GPU_VRAM_GB} * ${GPU_MEM_UTIL}))")
  llmfit --memory="${EFFECTIVE_VRAM_GB}G" recommend --json --limit 10
  ```
- When presenting recommendations to the operator, show both llmfit's assessment and the effective VRAM used for scoring, so the operator can sanity-check.
- Filter recommendations to exclude models whose memory requirement exceeds `GPU_COUNT * GPU_VRAM_GB * GPU_MEM_UTIL`. This is a backend filter applied after parsing llmfit output, not a change to llmfit itself.
- Document in the API response that recommendations assume a specific `gpu_memory_utilization` value.

**Detection:** Run llmfit on a 2x A100 server and compare its top recommendation against what vLLM can actually load with `--gpu-memory-utilization 0.90`. If the top recommendation OOMs, this pitfall is present.

**Phase:** llmfit output processing phase. The VRAM adjustment must be applied when translating llmfit output to operator-facing recommendations.

---

### Pitfall 7: llmfit Recommends Models Not Available on NFS Cache

**What goes wrong:** llmfit recommends models from its database of 200+ models. The existing infrastructure serves models from NFS shared storage (`/srv/hf-cache` mounted from `rdu-storage02.scalelab.redhat.com`). Only models that have been pre-downloaded to the NFS share are available. llmfit recommends "Llama-3.1-70B-Instruct" as the best fit, but only "Qwen2.5-72B-Instruct" is on the NFS share. The operator either:
1. Selects a model that is not available, and vLLM fails to load it (404 on HuggingFace or timeout trying to download 150GB).
2. Ignores llmfit's recommendations entirely and picks from what they know is available.

**Why it happens:** llmfit has no knowledge of the deployment environment's model availability. It recommends based on hardware fit and model quality, not model availability.

**Consequences:**
- Misleading recommendations that cannot be acted on.
- Operators start ignoring llmfit, defeating the purpose of the integration.
- If vLLM tries to download the model from HuggingFace (when model is not on NFS), it consumes 50-150GB of bandwidth and takes hours, blocking the server.

**Prevention:**
- After getting llmfit recommendations, filter them against the models actually available on the NFS cache. This requires:
  1. At provisioning time, listing the contents of the NFS mount (or a pre-computed manifest).
  2. Matching llmfit model names to NFS directory names (e.g., `Qwen/Qwen2.5-72B-Instruct` maps to `/srv/hf-cache/models--Qwen--Qwen2.5-72B-Instruct/`).
- Present two lists to the operator: "Recommended and available" (intersection) and "Recommended but not cached" (with a note that deployment would require download).
- Alternatively, restrict llmfit to only score models that are available: use `llmfit search "model-name"` for each known available model rather than open-ended `recommend`. This is slower (one call per model) but guarantees only actionable results.
- The simplest approach: maintain a list of available model names in settings and filter client-side after parsing llmfit output. No NFS probing needed.

**Detection:** Run llmfit on a server and check if the top recommendation is present on the NFS share. If it is not, this pitfall is present.

**Phase:** Recommendation presentation phase. The filtering logic is part of the admin API endpoint, not the llmfit execution.

---

### Pitfall 8: SSH PATH Not Set for Non-Login Shell

**What goes wrong:** asyncssh's `create_process()` runs commands in a non-login, non-interactive shell on the remote server. This means `~/.bash_profile`, `~/.profile`, and `/etc/profile.d/*.sh` are NOT sourced. If llmfit is installed to `/usr/local/bin` (the default from the install script), it may not be on PATH in the minimal shell environment that asyncssh provides.

The existing setup.sh works because it is invoked as `bash auto-vllm/setup.sh` (explicit path). The existing nvidia-smi calls work because nvidia-smi is installed to `/usr/bin/` which is universally on PATH. But `/usr/local/bin` is not guaranteed to be on PATH in all non-login shell configurations.

**Why it happens:** Different Linux distributions have different defaults for PATH in non-login shells. Fedora/RHEL typically include `/usr/local/bin` in the system-wide PATH via `/etc/environment` or compiled-in defaults. But stripped-down server images or containers may not.

**Consequences:**
- "command not found: llmfit" on some servers but not others, depending on OS image.
- Works when the operator SSHes in manually (login shell) but fails from the provisioner (non-login shell).
- Intermittent failures that are hard to reproduce.

**Prevention:**
- Use the absolute path when invoking llmfit via SSH: `/usr/local/bin/llmfit recommend --json` instead of `llmfit recommend --json`. This eliminates PATH dependence entirely.
- Make the remote binary path configurable: `LlmfitSettings.remote_binary_path: str = "/usr/local/bin/llmfit"`.
- If using the SCP upload approach (Pitfall 5 prevention), you control where the binary goes. Upload it to a known absolute path and always invoke it by that path.

**Detection:** Run `ssh root@server 'echo $PATH'` and check if `/usr/local/bin` is included. Then run `ssh root@server 'which llmfit'`. If the first shows `/usr/local/bin` is missing from PATH, this pitfall affects your fleet.

**Phase:** llmfit execution phase. Use absolute paths from the start; do not rely on PATH.

---

### Pitfall 9: llmfit TUI Mode Activated Instead of CLI Mode

**What goes wrong:** llmfit defaults to an interactive TUI (terminal user interface) when run without the `recommend` or `fit` subcommand. If the provisioner accidentally runs `llmfit` without a subcommand (e.g., due to a string formatting bug that drops the arguments), the TUI launches, waits for keyboard input, and the SSH session hangs indefinitely. There is no timeout on TUI mode -- it will wait forever for a keypress.

Even with the correct subcommand, if llmfit detects a TTY-like environment, it may still try to render TUI elements (progress bars, colored output, ANSI escape sequences) that corrupt the JSON output or confuse the line-by-line parser in `run_streaming()`.

**Why it happens:** llmfit is designed as an interactive tool first. The `--json` flag suppresses TUI behavior, but the detection of whether to use TUI mode depends on terminal detection (isatty check). asyncssh's `create_process()` does not allocate a PTY by default (which is correct), but some SSH configurations or shell init scripts may affect terminal detection.

**Consequences:**
- SSH session hangs waiting for TUI input (same effect as Pitfall 2 but different cause).
- JSON output corrupted with ANSI escape codes: `\x1b[32m{...}\x1b[0m` wrapping the JSON, causing parse failures.
- Partial output: TUI mode draws a table, the line parser captures table drawing characters, JSON parsing fails.

**Prevention:**
- Always pass `--json` to llmfit subcommands. The `recommend` subcommand defaults to JSON, but being explicit is safer.
- Always specify the full subcommand: `llmfit recommend --json --limit 10`, never bare `llmfit`.
- Set `TERM=dumb` in the SSH environment to suppress any ANSI output:
  ```python
  await self._ssh_run_command(hostname, "TERM=dumb /usr/local/bin/llmfit recommend --json --limit 10")
  ```
- The command timeout from Pitfall 2 is the safety net: even if TUI mode is accidentally triggered, the 60-second timeout will kill it.

**Detection:** Run `llmfit` (no subcommand) via SSH and observe whether it hangs. Run `llmfit recommend --json` and check the output for ANSI escape codes.

**Phase:** llmfit execution phase. Command construction must be rigorous.

---

### Pitfall 10: Security Risk of Running Unvetted Binaries on Lab Servers

**What goes wrong:** The provisioner downloads a binary from GitHub (a third-party repository) and executes it as root on lab servers that have access to the internal network, NFS storage, and potentially other infrastructure. If the GitHub release is compromised (supply chain attack), the attacker gets root access on every server in the fleet. If the binary has a vulnerability, it runs with full privileges on machines with GPU access.

The existing provisioning flow already runs third-party software (NVIDIA driver `.run` file from nvidia.com, pip packages from PyPI for vLLM). So this is not a new category of risk, but it is an incremental increase in attack surface.

**Why it happens:** The install script curls from GitHub and pipes to sh, or downloads and executes a binary -- standard open-source distribution patterns that are acceptable for development but deserve scrutiny in production infrastructure.

**Consequences:**
- Supply chain compromise: malicious llmfit binary exfiltrates SSH keys, GPU data, or NFS contents.
- The binary runs as root (since SSH provisioning uses the root user, per SSHSettings.username="root").
- Fleet-wide impact: every provisioned server runs the same compromised binary.

**Prevention:**
- Verify checksums. llmfit publishes SHA256 checksums alongside release tarballs. After downloading, verify:
  ```bash
  sha256sum -c llmfit.tar.gz.sha256
  ```
  The install script already does this, but if downloading manually in the provisioner, the checksum step can be skipped accidentally.
- Pin the exact version AND store the expected SHA256 in settings or the provisioning script. This ensures even if the GitHub release is tampered with, the checksum mismatch catches it.
- Pre-stage the binary on the gateway host. Download once, verify once, then SCP to target servers via the internal network. Target servers never access GitHub directly. This also solves the air-gap problem (Pitfall 5).
- Consider running llmfit as a non-root user. It only reads hardware info (nvidia-smi output, /proc/meminfo, /proc/cpuinfo). It does not need root. However, the existing SSH provisioning session is root, so this requires either: `su - llmfit-user -c 'llmfit recommend --json'` or accepting that it runs as root like everything else in the provisioner.
- llmfit's privacy policy states it does not contact external services unless explicitly requested. The `recommend` and `system` subcommands are local-only. But verify this by running it in a network-isolated environment and confirming no outbound connections.

**Detection:** Run `strace -e trace=network llmfit recommend --json` and verify no outbound network connections are made during recommendation.

**Phase:** Architecture decision phase. Security posture (pre-staging, checksum verification, trust model) must be decided before implementation.

---

## Minor Pitfalls

Issues that cause minor operational friction or developer confusion.

### Pitfall 11: ProvisioningStep Enum Not Extended for llmfit Steps

**What goes wrong:** Same pattern as Pitfall 9 from the v1.5 PITFALLS: the `ProvisioningStep` enum (state.py) does not include llmfit-specific steps. The dashboard shows no progress feedback during llmfit installation or recommendation generation. If llmfit is run as part of provisioning, the step appears as the parent step name (e.g., "uploading_scripts" or "starting_vllm") rather than "detecting_hardware" or "getting_recommendations".

**Why it happens:** Same as v1.5: adding enum members requires touching enum, provisioner, state writer, dashboard, and tests.

**Consequences:**
- Operators cannot tell if provisioning is stuck or actively running llmfit.
- If llmfit hangs (Pitfall 2), the dashboard shows the wrong step name, making diagnosis harder.

**Prevention:**
- If llmfit runs as part of provisioning, add steps: `INSTALLING_LLMFIT`, `DETECTING_HARDWARE`, or simply `LLMFIT_RECOMMEND`.
- If llmfit runs on-demand (Option A from Pitfall 5), no enum changes needed -- it is a separate API endpoint, not a provisioning step.

**Detection:** Trigger provisioning with llmfit and watch the dashboard step progression. If there is no llmfit-specific step shown, this pitfall is present.

**Phase:** Provisioning integration phase (only if llmfit is in-band).

---

### Pitfall 12: llmfit Output Includes Models Not Compatible with vLLM

**What goes wrong:** llmfit's model database includes models for Ollama, llama.cpp, MLX, Docker Model Runner, and LM Studio -- not just vLLM. It may recommend GGUF-quantized models (for llama.cpp/Ollama) that vLLM cannot serve, or MLX-format models (for Apple Silicon) that are irrelevant on CUDA servers. The operator sees "recommended: llama-3.1-8b-q4_k_m.gguf" and tries to deploy it on vLLM, which only supports HuggingFace-format models (safetensors/pytorch).

**Why it happens:** llmfit is runtime-agnostic. Its `recommend` output includes models across all supported runtimes. The `--json` output may include a provider/runtime field, but filtering by runtime is the consumer's responsibility.

**Consequences:**
- Operator selects a GGUF model, vLLM fails to load it.
- Confusion about model format compatibility.
- Recommendations include irrelevant entries, diluting the useful ones.

**Prevention:**
- Filter recommendations to vLLM-compatible models only. Check if llmfit supports a provider/runtime filter flag (e.g., `llmfit recommend --provider vllm`). If not, filter in post-processing: only include models whose provider/source is HuggingFace and whose format is safetensors-compatible.
- Cross-reference with vLLM's supported model architectures list to validate that recommended models are actually serveable.
- At minimum, document in the API response which models are vLLM-compatible and which are not.

**Detection:** Run `llmfit recommend --json` on a CUDA server and check if any recommended models are GGUF-format or MLX-only.

**Phase:** Recommendation filtering phase. This is a post-processing step applied to llmfit output.

---

### Pitfall 13: Concurrent llmfit Runs on Same Host Race on nvidia-smi

**What goes wrong:** If two provisioning requests or recommendation requests target the same host simultaneously (e.g., operator clicks "Get Recommendations" twice quickly, or a retry races with the original request), two `llmfit recommend` processes run concurrently on the same server. Both invoke nvidia-smi at the same time. nvidia-smi can handle concurrent queries, but if one of the llmfit processes is run while the other is mid-hardware-detection, they may see different snapshots of GPU state (one sees all GPUs, the other misses one that is briefly busy responding to the first query's NVML call).

More realistically: the provisioner already guards against concurrent provisioning via etcd state (PROVISIONING status prevents a second setup). But if llmfit runs as an on-demand API call (Option A from Pitfall 5), there is no such guard. Two concurrent API calls to `GET /admin/nodes/{hostname}/recommendations` both SSH into the server and run llmfit simultaneously.

**Why it happens:** llmfit is a stateless read-only tool. Running it twice is harmless in isolation. But the SSH sessions and nvidia-smi calls consume resources, and the results may diverge under concurrent access.

**Consequences:**
- Minor: wasted resources from duplicate SSH sessions and nvidia-smi queries.
- Minor: potentially inconsistent recommendations if GPU state changes between the two runs.
- Moderate: if the server is under provisioning and llmfit runs concurrently with nvidia-smi in `_verify_gpu()` or GPU detection in start-vllm.sh, the concurrent probes may interfere.

**Prevention:**
- For the on-demand API approach, add a simple per-host lock (asyncio.Lock per hostname) to prevent concurrent llmfit runs:
  ```python
  self._llmfit_locks: dict[str, asyncio.Lock] = {}

  async def get_recommendations(self, hostname: str) -> list[Recommendation]:
      lock = self._llmfit_locks.setdefault(hostname, asyncio.Lock())
      async with lock:
          return await self._run_llmfit(hostname)
  ```
- Cache recommendations for a configurable TTL (e.g., 5 minutes). Hardware does not change between calls -- there is no reason to re-run llmfit on the same server within minutes.
- `# ponytail: per-host lock + 5min cache, remove lock if cache alone prevents concurrent calls`

**Detection:** Send two concurrent recommendation requests for the same host and check if both SSH into the server simultaneously.

**Phase:** API endpoint phase. The lock/cache is part of the endpoint handler, not the llmfit execution logic.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Architecture decision (in-band vs on-demand) | llmfit failure blocks provisioning (#5), security posture (#10) | Run llmfit on-demand via admin API, not as provisioning step. Pre-stage binary via SCP. |
| Binary installation | Rust toolchain on servers (#1), download failures (#5), PATH issues (#8) | Prebuilt musl binary, pin version, SCP from gateway, use absolute paths |
| SSH execution of llmfit | No command timeout (#2), TUI hang (#9), nvidia-smi not functional (#4) | asyncio.wait_for(), TERM=dumb, absolute path, run after GPU verification |
| JSON output parsing | Unstable schema (#3), non-vLLM models (#12) | Pydantic with extra="ignore", pin version, filter by provider/format |
| VRAM and model matching | Aggregation mismatch (#6), models not on NFS (#7) | Pass effective VRAM via --memory, filter against NFS manifest |
| API endpoint | Concurrent requests (#13), enum not extended (#11) | Per-host asyncio.Lock + cache, add enum steps if in-band |

---

## Sources

- [llmfit GitHub repository (AlexsJones/llmfit)](https://github.com/AlexsJones/llmfit) -- installation methods, CLI commands, JSON output, GPU detection, platform support
- [llmfit official website](https://www.llmfit.org/) -- feature overview, hardware detection, multi-GPU support
- [llmfit install.sh source](https://github.com/AlexsJones/llmfit/blob/main/install.sh) -- platform detection, binary download, checksum verification, install locations
- [llmfit documentation (Mintlify)](https://alexsjones-llmfit.mintlify.app/installation) -- installation methods, platform requirements (kernel >= 3.2, glibc >= 2.17 or musl >= 1.2.5)
- [llmfit-pypi (JEHoctor/llmfit-pypi)](https://github.com/JEHoctor/llmfit-pypi) -- PyPI binary wrapper, pip/uv installation, versioning policy
- [llmfit issue #68: 2 GPUs detected but only 1 factored](https://github.com/AlexsJones/llmfit/issues/68) -- multi-GPU VRAM aggregation bug
- [llmfit issue #303: Integrated GPU detected instead of discrete](https://github.com/AlexsJones/llmfit/issues/303) -- GPU detection edge case
- [asyncssh issue #626: Timeout in run() doesn't always apply](https://github.com/ronf/asyncssh/issues/626) -- timeout applies to wait(), not create_process()
- [asyncssh issue #411: run() does not respect timeout parameter](https://github.com/ronf/asyncssh/issues/411) -- timeout scoping in asyncssh
- [Headless Rust/cargo installation (ctron blog)](https://dentrassi.de/2020/06/17/headless-installation-of-cargo-and-rust/) -- `-y` flag, PATH sourcing, automation pitfalls
- [NVIDIA forums: nvidia-smi not found after driver install](https://forums.developer.nvidia.com/t/newly-installed-drivers-are-not-found-when-nvidia-smi-is-called/82686) -- reboot required, kernel module loading, Secure Boot, PATH issues
- [NVIDIA forums: nvidia-smi failed to communicate with driver](https://forums.developer.nvidia.com/t/nvidia-smi-has-failed-because-it-couldnt-communicate-with-the-nvidia-driver-make-sure-that-the-latest-nvidia-driver-is-installed-and-running/197141) -- driver/kernel mismatch, DKMS
- Existing codebase: `inference_proxy/provisioning/ssh_client.py` -- no command timeout in run_streaming(), connect_timeout only
- Existing codebase: `inference_proxy/provisioning/provisioner.py` -- step markers, _verify_gpu(), MODEL_PATTERN regex, state machine
- Existing codebase: `inference_proxy/provisioning/state.py` -- ProvisioningStep enum (18 members, no llmfit steps)
- Existing codebase: `inference_proxy/config/settings.py` -- SSHSettings, ProvisioningSettings patterns
- Existing codebase: `auto-vllm/setup.sh` -- NVIDIA driver install, kernel module handling, idempotent steps
- Existing codebase: `auto-vllm/start-vllm.sh` -- GPU detection, hardcoded model selection, VRAM calculation, NFS mount dependency
