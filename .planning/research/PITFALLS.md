# Domain Pitfalls

**Domain:** HuggingFace Hub Model Download Integration for LLM Inference Gateway
**Researched:** 2026-07-28
**Confidence:** HIGH (verified against huggingface_hub GitHub issues, official docs, existing codebase patterns, NFS operations research)

**Scope:** Pitfalls specific to adding HuggingFace model download capabilities (v1.7) to the existing gateway. Covers downloading large models (10-70GB+), NFS write operations, HF token management, download state tracking in a stateless gateway, NFS model scanning, dashboard integration, and async event loop safety.

---

## Critical Pitfalls

Mistakes that cause data corruption, stuck gateway processes, or require architectural rework.

### Pitfall 1: Blocking the asyncio Event Loop with `snapshot_download`

**What goes wrong:** `huggingface_hub.snapshot_download()` and `hf_hub_download()` are synchronous, blocking calls. They use `requests` internally for HTTP downloads and `tqdm` for progress bars. A developer calls `snapshot_download()` directly from a FastAPI endpoint handler or an `async def` coroutine. This blocks the event loop for the entire duration of the download -- minutes to hours for 10-70GB models. During this time, the gateway cannot serve any inference requests, health checks fail, circuit breakers trip on all nodes, and the dashboard becomes unresponsive.

The existing codebase already handles this pattern correctly for etcd3gw (sync library wrapped in `asyncio.to_thread()` -- see provisioner.py line 102, 454). But a model download is fundamentally different from a quick etcd put/get: it runs for 30-120 minutes, and `asyncio.to_thread()` consumes a thread from the default `ThreadPoolExecutor` (which has a limited pool -- `min(32, os.cpu_count() + 4)` workers) for the entire duration.

**Why it happens:** The `huggingface_hub` library has no native async API. GitHub issue #1123 tracks this; as of mid-2026 there is no asyncio-native download path. Developers see the existing `asyncio.to_thread()` pattern in the codebase and assume it scales to long-running operations without considering thread pool exhaustion.

**Consequences:**
- Single download: event loop itself is unblocked (if `asyncio.to_thread()` is used), but one thread pool slot is consumed for 30-120 minutes.
- Multiple concurrent downloads: 3-4 simultaneous 70GB model downloads exhaust the default thread pool. All subsequent `asyncio.to_thread()` calls (including etcd operations, QUADS polling, health checks) queue behind the downloads and effectively block the gateway.
- If called without `asyncio.to_thread()` (direct `await` in a coroutine): complete gateway freeze. No requests served, no health checks, no dashboard updates.

**Prevention:**
- Use a dedicated `ThreadPoolExecutor` with a small, bounded pool (e.g., 2-3 workers) exclusively for downloads. This isolates download threads from the default pool used by etcd, QUADS, and other sync operations:
  ```python
  import concurrent.futures

  _download_executor = concurrent.futures.ThreadPoolExecutor(
      max_workers=2, thread_name_prefix="hf-download"
  )

  async def download_model(repo_id: str, cache_dir: str, token: str | None) -> str:
      loop = asyncio.get_running_loop()
      return await loop.run_in_executor(
          _download_executor,
          functools.partial(snapshot_download, repo_id=repo_id, cache_dir=cache_dir, token=token),
      )
  ```
- Cap concurrent downloads to match the executor size. The existing `pending_hosts` dedup pattern (admin.py line 67) works: a `pending_downloads: set[str]` guards against duplicate download requests.
- Make `max_concurrent_downloads` configurable in settings. Default to 2 -- enough for operator workflows, low enough to not starve the thread pool.

**Detection:** Start a model download and simultaneously try to use the gateway (inference request, dashboard load, health check). If anything freezes or times out, the event loop or thread pool is blocked.

**Phase:** Architecture phase. The executor isolation must be designed before any download code is written.

---

### Pitfall 2: Double Disk Space from HuggingFace Cache + `local_dir`

**What goes wrong:** `snapshot_download()` with `local_dir="/srv/hf-cache/models/Llama-3.1-70B"` first downloads files to the HuggingFace cache directory (`~/.cache/huggingface/hub/` or `HF_HOME`), then copies them to `local_dir`. A 70GB model consumes 140GB of disk space. On NFS shared storage where space is shared across all vLLM nodes, this can fill the volume and cause all running vLLM instances to fail when they try to write KV cache or logs.

The existing `start-vllm.sh` (line 125) symlinks `/root/.cache/huggingface` to the NFS mount point (`/srv/hf-cache`). This means vLLM reads models from the HuggingFace cache structure. If the gateway downloads with `local_dir` pointing to a different path, the model exists on disk but vLLM cannot find it because vLLM resolves models through the HuggingFace cache symlink structure, not arbitrary directory paths.

**Why it happens:** The `huggingface_hub` cache system uses a content-addressed blob store with symlinks: `blobs/` stores files by SHA256, `snapshots/` contains revision-specific symlinks. When `local_dir` is used, the library copies from cache to `local_dir`, doubling space. The older `local_dir_use_symlinks` parameter was removed in recent versions. GitHub issue #2284 documents this doubling.

**Consequences:**
- 2x disk consumption per model on NFS. A fleet downloading 3 large models uses 6x the expected space.
- NFS fills up silently (no per-download quota enforcement).
- If NFS hits capacity, running vLLM instances crash when they cannot write.

**Prevention:**
- Download to the HuggingFace cache directory directly. Set `cache_dir` to the NFS mount point and do NOT use `local_dir`:
  ```python
  snapshot_download(
      repo_id="meta-llama/Llama-3.1-70B-Instruct",
      cache_dir="/srv/hf-cache",
      token=token,
  )
  ```
  This downloads blobs once and creates symlinks in `snapshots/`. vLLM on the nodes (which have `/root/.cache/huggingface` symlinked to the same NFS path) will find the model through the standard HuggingFace cache resolution.
- Never use `local_dir` for this use case. The NFS mount IS the cache.
- Add a pre-download disk space check. The HuggingFace API exposes model file sizes before downloading (`HfApi().model_info(repo_id).siblings`). Compare total size against available NFS space:
  ```python
  info = HfApi().model_info(repo_id, token=token)
  total_bytes = sum(s.size for s in info.siblings if s.size)
  ```
- Make the NFS mount path configurable in settings with no default (forces explicit configuration, avoids accidental writes to local disk).

**Detection:** Download a model, then check disk usage with `du -sh /srv/hf-cache/` and compare against the model size. If usage is 2x, this pitfall is active.

**Phase:** First implementation phase. The cache_dir vs local_dir decision must be correct from the start -- it determines the entire NFS layout.

---

### Pitfall 3: HuggingFace Token Leaked via API Response, Logs, or Error Messages

**What goes wrong:** The HF API token is needed for gated models (Llama, Mistral, Gemma, etc.). The developer stores it in settings as a plain `str`, passes it to `snapshot_download(token=token)`, and the token appears in:
1. **Structured logs:** structlog captures function arguments in error tracebacks. A failed download logs the full `snapshot_download()` call including `token="hf_..."`.
2. **API error responses:** A 401 from HuggingFace returns the token in the HTTP request headers, which may be included in the error detail sent to the dashboard.
3. **Settings dump:** The `/admin` debug endpoints or health checks that expose settings show the token in plaintext.
4. **`.env` file committed to git:** Developer adds `INFERENCE_PROXY_HF__TOKEN=hf_...` to `.env`, forgets it is not in `.gitignore`.

The existing codebase handles this correctly for Redfish BMC credentials: `bmc_password: SecretStr | None = None` (settings.py line 155). `SecretStr` masks the value in string representations and serialization. But a developer unfamiliar with this pattern uses a plain `str` for the HF token.

**Why it happens:** HuggingFace tutorials show `token="hf_..."` as a plain string. The developer copies the pattern without considering the gateway's structured logging and API response pipeline.

**Consequences:**
- Token appears in JSON logs shipped to centralized logging (ELK, Splunk). Anyone with log access can impersonate the HF account.
- Token appears in dashboard error messages visible to all operators.
- If the token has write access, an attacker can upload malicious models to the HF account.
- For fine-grained tokens scoped to gated repos, the token grants access to all gated models the account has been approved for (Llama, Mistral, etc.).

**Prevention:**
- Use `SecretStr` for the HF token, matching the existing `RedfishSettings.bmc_password` pattern:
  ```python
  class HuggingFaceSettings(BaseModel):
      token: SecretStr | None = None
  ```
- When passing to `snapshot_download`, extract the secret value: `token=settings.hf.token.get_secret_value()`.
- Add the HF token env var to `.env.example` as a comment (matching existing conventions) and verify `.env` is in `.gitignore` (it already is).
- In download error handling, never include the raw exception from `huggingface_hub` in API responses. Catch `HfHubHTTPError`, extract the status code and message, strip any headers or auth info, and return a sanitized error.
- Use a read-only, fine-grained token scoped to model downloads only. Never use a write token.
- The convention in CLAUDE.md says: "When adding or changing environment variables in code (settings, config), always update `.env.example` to match." Follow this.

**Detection:** Trigger a download with an invalid token, check the structured log output and API response for the token string. If it appears anywhere, this pitfall is present.

**Phase:** Settings/configuration phase. Token handling must be correct before any download code uses it.

---

### Pitfall 4: NFS Symlinks Not Followed -- Model Appears Downloaded but vLLM Cannot Load It

**What goes wrong:** The HuggingFace cache system relies on symlinks: `snapshots/{revision}/{filename}` -> `../../blobs/{sha256}`. The gateway downloads a model to NFS using `snapshot_download(cache_dir="/srv/hf-cache")`. The symlinks are created on the gateway's NFS client. vLLM nodes mount the same NFS share read-only. But:

1. **NFS server configured with `no_follow_symlinks` or symlinks disabled.** The symlinks exist on disk but NFS does not expose them to clients. vLLM sees empty or missing files.
2. **The symlinks are absolute paths from the gateway host.** If the gateway mounts NFS at `/srv/hf-cache` and the symlinks contain absolute paths like `/srv/hf-cache/hub/models--meta-llama--Llama-3.1-70B/blobs/abc123`, but vLLM nodes mount the same share at a different path (e.g., `/models` or `/root/.cache/huggingface`), the symlinks resolve to nonexistent paths.
3. **`HF_HUB_DISABLE_SYMLINKS=1`** set globally on the gateway. The cache stores files directly in `snapshots/` without symlinks, doubling space and changing the expected layout.

The existing `start-vllm.sh` (line 125) creates a symlink: `ln -sfn "${NFS_MOUNT_POINT}" /root/.cache/huggingface`. This means vLLM resolves `~/.cache/huggingface/hub/models--X/snapshots/rev/file` through two layers of symlinks: the mount symlink and the internal cache symlinks. If either breaks, the model is invisible.

**Why it happens:** `huggingface_hub` creates relative symlinks within the cache directory (blob symlinks are relative: `../../blobs/sha256`). This is correct and portable. But NFS configuration, mount path mismatches, or environment variables can break the chain.

**Consequences:**
- Model shows as "downloaded" in the gateway's NFS scan, but vLLM fails to load it with a file-not-found error.
- The failure happens during provisioning (health poll timeout after vLLM fails to start), not at download time. The operator waited 2 hours for the download, then waits 10 minutes for health poll, then gets a cryptic error.
- Debugging requires SSH into the vLLM node to check symlink resolution, which most operators will not think to do.

**Prevention:**
- After downloading a model, verify the symlink chain resolves correctly from the expected vLLM path. Run a quick sanity check:
  ```python
  import os
  snapshot_path = snapshot_download(repo_id=repo_id, cache_dir=nfs_path, token=token)
  # Verify at least one file in the snapshot resolves
  for entry in os.listdir(snapshot_path):
      full = os.path.join(snapshot_path, entry)
      if os.path.islink(full) and not os.path.exists(full):
          raise DownloadError(f"Symlink broken: {full} -> {os.readlink(full)}")
  ```
- Ensure the NFS mount path on the gateway matches the path vLLM nodes will use to resolve the cache. If they differ, create matching symlinks or configure `HF_HOME` consistently.
- Never set `HF_HUB_DISABLE_SYMLINKS=1` on the gateway. Document this explicitly.
- During NFS model scanning, check that symlinks resolve (use `os.path.exists()` which follows symlinks, not `os.path.lexists()` which does not).

**Detection:** Download a model on the gateway, then SSH to a vLLM node and run `ls -la /root/.cache/huggingface/hub/models--{org}--{name}/snapshots/*/` to verify symlinks resolve.

**Phase:** Integration testing phase. This must be validated end-to-end (gateway download -> vLLM node load) before the feature is considered complete.

---

### Pitfall 5: Download State Lost on Gateway Restart

**What goes wrong:** The gateway is stateless -- all state lives in memory (in-memory counters, `pending_hosts` set, provisioning log buffer). Download progress tracking follows the same pattern: a dict mapping `repo_id -> {status, progress, error}`. The gateway restarts (deploy, crash, OOM from a large download's memory overhead), and all download state is lost. An operator sees a download at 80% progress, the gateway restarts, and the dashboard shows no download in progress. The partially downloaded files remain on NFS, consuming 40GB of space, with no record that a download was in progress or how to resume it.

The existing provisioning system mitigates this via etcd state (`/provisioning/{hostname}` -- provisioner.py line 128). But downloads are a different beast: provisioning is a short-lived multi-step orchestration (5-15 minutes) where etcd state is always-current. Downloads are single long-running operations (30-120 minutes) where writing progress to etcd every second would be excessive.

**Why it happens:** The existing architecture explicitly chose "embed in gateway process, no Celery" (PROJECT.md key decisions). This is the correct tradeoff for provisioning (rare, operator-initiated, 5-15 minute operations). It is a worse tradeoff for downloads (potentially concurrent, 30-120 minutes, much more likely to span a restart).

**Consequences:**
- Orphaned partial downloads consume NFS space with no way to identify them from the dashboard.
- Operators lose trust in the download feature after a restart wipes visible progress.
- If the operator retries the download, `snapshot_download` with the default cache will skip already-downloaded blobs, but progress reporting starts from zero (confusing UX even though it is functionally correct).

**Prevention:**
- Accept that in-memory state will be lost on restart. Design for it rather than fighting it:
  1. `snapshot_download()` is resumable. Re-triggering the same download after restart picks up where it left off (completed blobs are not re-downloaded). This is the critical property that makes in-memory state tolerable.
  2. `scan_cache_dir()` handles incomplete downloads -- it reports repos with `warnings` for corrupted/incomplete entries. The catalog can flag these.
  3. On startup, the NFS catalog scan will show partially-downloaded models (directories exist but snapshots are incomplete). Surface this in the dashboard.
- Do NOT add persistence (database, file-based state, etcd) for download tracking. The cost of re-triggering is minimal (resume, not restart). Persistence adds complexity for a rare event.
- Document this behavior: "downloads in progress are interrupted on gateway restart and must be re-triggered."

**Detection:** Start a large download, restart the gateway, re-trigger the download. Verify it resumes rather than re-downloading from scratch.

**Phase:** Architecture phase. The decision to accept in-memory-only state (with resume) must be made explicitly.

---

## Moderate Pitfalls

Mistakes that cause degraded UX, operational friction, or confusing behavior.

### Pitfall 6: Gated Model 401 with Unhelpful Error Messages

**What goes wrong:** Most popular large models (Llama 3, Mistral, Gemma) are "gated" -- they require the HF account to accept a license agreement on the model page AND the token to have gated-repo read access. The download fails with a 401 or 403, and the error from `huggingface_hub` says "Access to model meta-llama/Llama-3.1-70B-Instruct is restricted" or "Repository Not Found" (the error is deliberately vague for security -- you cannot distinguish "does not exist" from "no access"). The operator sees "download failed" with no actionable guidance.

There are three distinct failure modes:
1. **No token configured:** 401 on any gated or private model.
2. **Token valid but license not accepted:** 403 with "You must agree to the terms of use..."
3. **Fine-grained token missing gated-repo scope:** 401 even though the account has accepted the license.

Additionally, model name casing matters: `meta-llama/Llama-3.1-70B-Instruct` works but `meta-llama/llama-3.1-70b-instruct` returns "Repository Not Found."

**Why it happens:** HuggingFace deliberately returns generic errors for security (preventing repo enumeration). The `huggingface_hub` library raises `HfHubHTTPError` with the HTTP status but limited diagnostic detail.

**Consequences:**
- Operators retry the same download multiple times, thinking it is a transient network error.
- Operators add a token but do not accept the license on the HF website, and the error does not guide them.
- Case-sensitivity bugs cause "Repository Not Found" for models that clearly exist.

**Prevention:**
- Before starting a download, validate access with a lightweight API call:
  ```python
  from huggingface_hub import HfApi
  from huggingface_hub.utils import RepositoryNotFoundError, GatedRepoError
  api = HfApi()
  try:
      info = api.model_info(repo_id, token=token)
  except RepositoryNotFoundError:
      raise DownloadError(f"Model '{repo_id}' not found. Check spelling and case sensitivity.")
  except GatedRepoError:
      raise DownloadError(
          f"Model '{repo_id}' requires license acceptance. "
          f"Visit https://huggingface.co/{repo_id} to accept the license, "
          f"then ensure your token has 'Read access to gated repos' permission."
      )
  except HfHubHTTPError as e:
      if e.response.status_code == 401:
          raise DownloadError("HuggingFace token is invalid or missing. Check HF__TOKEN in settings.")
  ```
- Map error codes to operator-friendly messages in the API response. Include the HF model page URL so operators can accept licenses directly.
- Validate the token on gateway startup (a simple `whoami()` call) and log a warning if it is invalid or missing. Do not fail startup -- the token is optional for public models.

**Detection:** Try to download a gated model with (a) no token, (b) valid token but no license acceptance, (c) valid token with acceptance. Check that each failure produces an actionable error message.

**Phase:** Download service implementation. Error mapping must be in place before the dashboard exposes download buttons.

---

### Pitfall 7: NFS Model Scan Returns Incomplete or Stale Results

**What goes wrong:** The gateway scans NFS to determine which models are already downloaded (for the "already downloaded" indicator on llmfit recommendations). The scan walks `/srv/hf-cache/hub/` looking for `models--{org}--{name}` directories. Problems:

1. **Scan is slow on large NFS caches.** A cache with 20 models and thousands of blobs takes 5-30 seconds to walk. If done synchronously on every dashboard poll (default 10s), it blocks the thread pool.
2. **Incomplete downloads appear as "downloaded."** A model directory exists (created at download start) but only 3 of 15 shards are downloaded. The scan sees the directory and reports the model as available.
3. **NFS attribute caching.** NFS clients cache directory listings and file attributes (default `acregmin=3`, `actimeo=60` on some configs). A model downloaded 30 seconds ago may not appear in the scan on the gateway because NFS has not refreshed the directory listing.

**Why it happens:** NFS is designed for shared file access with eventual consistency (caching improves performance). The HuggingFace cache structure uses `.incomplete` marker files during downloads, but these are in the blobs directory, not the top-level model directory. A naive scan checking only for directory existence misses download-in-progress state.

**Consequences:**
- Operator sees "downloaded" badge on a model that is only 20% downloaded. They provision a node with it, vLLM fails to load.
- Scan blocks the thread pool on every dashboard poll, degrading gateway responsiveness.
- Recently completed downloads do not appear for 30-60 seconds due to NFS attribute caching.

**Prevention:**
- Cache the NFS scan result in memory with a configurable TTL (e.g., 60 seconds). Do not re-scan on every dashboard poll. Use a background thread for the scan, same as QUADS polling pattern.
- To detect completeness, use `huggingface_hub.scan_cache_dir()` which reports revision completeness, including warnings for corrupted/incomplete entries:
  ```python
  from huggingface_hub import scan_cache_dir
  cache_info = scan_cache_dir(cache_dir="/srv/hf-cache")
  for repo in cache_info.repos:
      for rev in repo.revisions:
          # rev.nb_files, rev.size_on_disk, etc.
  ```
- For single-model lookups (e.g., "is this recommended model already downloaded?"), use a fast-path: check for the existence of `models--{org}--{name}/snapshots/*/` with resolved symlinks. This is 2-3 stat calls instead of a full cache walk.
- Wrap the scan in `asyncio.to_thread()` (mandatory since it is sync). Use the default executor, NOT the download executor.
- For NFS attribute caching: accept the delay. A 30-60 second delay for a download that took 2 hours is acceptable.

**Detection:** Download a model, immediately check the dashboard. If the model does not appear as "downloaded" for 30-60 seconds, NFS caching is in play. If a partially downloaded model shows as "downloaded," the completeness check is missing.

**Phase:** NFS catalog implementation. The scan strategy directly affects dashboard accuracy.

---

### Pitfall 8: Download Hangs Indefinitely with No Timeout or Cancellation

**What goes wrong:** `snapshot_download()` downloads files sequentially. A single large shard (e.g., `model-00001-of-00015.safetensors` at 5GB) can hang during download due to:
- HuggingFace CDN rate limiting or throttling.
- Network partition between the gateway and HuggingFace servers.
- XET backend hangs (reported in huggingface_hub issues #3429, #4520, #4452 -- downloads get stuck at random percentages with no error).

The download thread blocks indefinitely. The operator sees "downloading" status forever. The NFS `.incomplete` file grows slowly or not at all.

`snapshot_download()` has no overall timeout parameter. Individual file downloads use `HF_HUB_DOWNLOAD_TIMEOUT` (default 10 seconds for connection, but no read timeout). Once a TCP connection is established and some data flows, the timeout does not apply to stalls.

**Why it happens:** The HuggingFace download infrastructure is optimized for throughput, not for guaranteed completion. The XET backend (newer, faster for large files) has known reliability issues as of mid-2026. The older LFS backend is more reliable but slower.

**Consequences:**
- A download thread is consumed indefinitely, eating into the bounded executor pool.
- The operator cannot cancel a stuck download from the dashboard (no cancellation API).
- NFS space is consumed by the partial download with no indication that progress has stalled.

**Prevention:**
- Set environment variables for timeouts: `HF_HUB_DOWNLOAD_TIMEOUT=120` and `HF_HUB_ETAG_TIMEOUT=1800`. These cover connection and initial data timeouts but not mid-transfer stalls.
- Disable XET for reliability until the known hang issues are resolved: set `HF_HUB_DISABLE_XET=1` in the gateway environment. Slower but more reliable. Make this configurable in settings.
- For truly stuck downloads, the operator may need to restart the gateway. Document this as a known limitation for v1.7. Downloads are resumable, so no data is lost.
- Do not attempt to implement download cancellation via thread interruption. Python threads cannot be killed externally. `concurrent.futures.Future.cancel()` only prevents scheduled futures, not running ones.

**Detection:** Simulate a network stall (firewall rule dropping HF CDN traffic after partial download) and observe whether the download eventually times out or hangs forever.

**Phase:** Download service implementation. The timeout environment variables and XET disable flag must be set before the feature goes to operators.

---

### Pitfall 9: Concurrent Downloads of the Same Model Create Confusion or Waste

**What goes wrong:** Two operators (or one operator double-clicking) trigger downloads for the same model simultaneously. Two threads call `snapshot_download("meta-llama/Llama-3.1-70B-Instruct", cache_dir="/srv/hf-cache")` concurrently. The `huggingface_hub` library uses file locks (`filelock`) to prevent corruption, so the data is safe on a local filesystem. However:

1. The second download blocks on the lock until the first completes, consuming a thread pool slot for no benefit.
2. On NFS, `fcntl` advisory locks (used by `filelock`) are notoriously unreliable. The lock files may not provide mutual exclusion, leading to concurrent writes to the same blob files.
3. The in-memory status shows two "downloading" entries for the same model, confusing the operator.

**Why it happens:** No deduplication guard in the download service. The existing provisioner has `pending_hosts: set[str]` (admin.py line 67) for this exact purpose, but downloads are a new operation without an equivalent guard.

**Consequences:**
- Wasted thread pool slot (at minimum).
- On NFS: potential silent corruption from concurrent writers if file locks do not hold.
- Confusing duplicate status entries in the dashboard.

**Prevention:**
- Dedup guard at the API layer, identical to `pending_hosts`:
  ```python
  pending_downloads: set[str] = set()

  async def start_download(repo_id: str) -> ...:
      if repo_id in pending_downloads:
          raise HTTPException(409, f"Download already in progress for '{repo_id}'")
      pending_downloads.add(repo_id)
      try:
          # fire background download
          ...
      except Exception:
          pending_downloads.discard(repo_id)
          raise
  ```
- Clear the guard in the `finally` block of the download task (same pattern as `_provision_and_cleanup` in admin.py line 151).
- Also check against the NFS catalog: if the model is already fully downloaded, return immediately with "already available."
- Single-worker deployment is the safest. If multi-worker is needed later, move the dedup guard to etcd CAS (same upgrade path noted in admin.py line 67 comment).

**Detection:** Click the download button twice in quick succession. If two download tasks start for the same model, the dedup guard is missing.

**Phase:** API endpoint implementation. The dedup guard must be the first line of defense.

---

## Minor Pitfalls

### Pitfall 10: Model Name Mismatch Between llmfit, HuggingFace, and NFS Cache Paths

**What goes wrong:** llmfit recommends models by name (e.g., `meta-llama/Llama-3.1-70B-Instruct`). The HuggingFace cache stores them as `models--meta-llama--Llama-3.1-70B-Instruct`. The NFS scan must translate between these formats. Additionally:
- llmfit may output the model name differently than HuggingFace's canonical `repo_id` (e.g., `Llama-3.1-70B-Instruct` without the org prefix).
- HuggingFace model names are case-sensitive: `meta-llama/Llama-3.1-70B-Instruct` is valid, `meta-llama/llama-3.1-70b-instruct` returns 404.
- The `--` delimiter in cache paths conflicts with model names that contain `--` (rare but possible).

**Prevention:**
- Use the `name` field from llmfit's JSON output, which with `--runtime vllm` returns full HuggingFace repo IDs (verified from existing `ModelRecommendation` model in the codebase).
- For NFS path translation, use `huggingface_hub`'s built-in cache path logic rather than hand-rolling string replacement. `scan_cache_dir()` returns `CachedRepoInfo` objects with the `repo_id` already resolved.
- If displaying a "download" button on a recommended model, validate the `repo_id` against HuggingFace's API (`model_info()`) before showing it. If validation fails, grey out the button with "model not found on HuggingFace."
- Never rely on case-insensitive string comparison for model names.

**Phase:** NFS catalog and dashboard integration phase.

---

### Pitfall 11: Download Progress Not Visible in Dashboard Polling Model

**What goes wrong:** The dashboard uses polling (10-second interval via `setInterval`). Download progress updates (bytes downloaded, percentage, speed) happen continuously. At 10-second polls, the operator sees jerky progress (0% -> 12% -> 25% -> ...) with no indication of activity between polls. For large models with slow connections, the progress may not change between two consecutive polls, making it look stuck even when it is actively downloading.

**Prevention:**
- Keep the polling model. Do not add SSE for download progress -- it is not worth the complexity for v1.7.
- Report coarse-grained status, not byte-level progress: `pending`, `downloading`, `complete`, `failed`. Within `downloading`, show the file count progress (e.g., "3/15 files") rather than byte progress. This changes on a per-file granularity (minutes), which aligns well with 10-second polls.
- Add a "started at" timestamp and elapsed duration to the download status. Even without progress percentage, "downloading for 45 minutes" tells the operator it is still working.

**Phase:** Dashboard integration phase.

---

### Pitfall 12: NFS Write Failures Not Caught Until Download Completes

**What goes wrong:** The NFS share has a disk quota, limited space, or intermittent connectivity. `snapshot_download()` writes files successfully to the NFS client cache (OS page cache), but the data is not flushed to the NFS server. The download reports success, but later, vLLM on a remote node cannot read the files because the NFS server never persisted them. Alternatively, the NFS share fills mid-download, and `snapshot_download()` raises an `OSError` that is not caught gracefully.

**Why it happens:** NFS writes are asynchronous by default (the client caches writes and flushes in the background). `snapshot_download()` does not call `fsync()` on individual files.

**Consequences:**
- Silent data corruption: files appear to exist but contain zeroed or truncated content.
- NFS full: download fails mid-way with an opaque OS error, leaves partial files.
- Gateway crash from unhandled `OSError` if NFS disconnects during download.

**Prevention:**
- Check NFS space before starting the download (Pitfall 2 prevention).
- Catch `OSError` broadly around the `snapshot_download()` call and translate to a user-friendly download failure:
  ```python
  try:
      path = snapshot_download(...)
  except OSError as e:
      if e.errno == errno.ENOSPC:
          raise DownloadError("NFS storage full. Free space before downloading.")
      raise DownloadError(f"NFS write error: {e}")
  ```
- After download completes, verify the snapshot is complete using `scan_cache_dir()` or by checking that expected files exist and have non-zero size.

**Phase:** Download service error handling. Wrap all download calls in comprehensive error handling before exposing to operators.

---

### Pitfall 13: NFS Mount Not Available When Gateway Starts

**What goes wrong:** The gateway starts before the NFS mount is ready (NFS server is slow to respond, mount is not in fstab, systemd mount unit has not triggered). The catalog scan either fails with `FileNotFoundError` or scans an empty directory (the mount point exists but NFS is not mounted). The catalog shows zero models even though models exist on the NFS share.

If the gateway creates the `HuggingFaceSettings.cache_dir` directory when it does not exist (to be "helpful"), it creates a local directory that masks the NFS mount point. When NFS eventually mounts, it mounts over the local directory, but any downloads that started before the mount went to the local disk, not NFS.

**Prevention:**
- Do NOT create `cache_dir` if it does not exist. If the path does not exist, the HF feature is disabled. Return 503 from download endpoints. Same pattern as `QUADSSettings.base_url = None` disabling QUADS.
- Validate at startup: check if `cache_dir` is a mounted filesystem (not just an empty dir). Log a warning if not available.
- Catalog scan is on-demand (per API call) with TTL cache, not a one-time startup scan. If NFS mounts after gateway starts, the next catalog request will see models.

**Detection:** Start the gateway before NFS is mounted. Check catalog response. Mount NFS, check again.

**Phase:** Settings and startup validation phase.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Architecture (executor, state) | Event loop blocking (#1), state loss on restart (#5) | Dedicated ThreadPoolExecutor, accept in-memory state with resume |
| Settings and configuration | Token leak (#3), NFS not mounted (#13), cache path (#2) | SecretStr, validate mount at startup, cache_dir not local_dir |
| Download service | Hung downloads (#8), concurrent corruption (#9), NFS errors (#12) | Timeout env vars, disable XET, dedup guard, OSError handling |
| NFS catalog scan | Incomplete models (#7), slow scan (#7) | scan_cache_dir(), background thread with TTL cache |
| Gated model access | Unhelpful 401 errors (#6) | Pre-flight model_info() check with mapped error messages |
| Dashboard integration | Progress not visible (#11), model name mismatch (#10) | Coarse-grained status polling, repo_id normalization |
| End-to-end integration | Symlinks broken on vLLM nodes (#4) | Post-download symlink verification, consistent mount paths |

---

## Sources

- [huggingface_hub snapshot_download fails on large datasets (>5TB)](https://github.com/huggingface/huggingface_hub/issues/3457) -- timeout and resume issues
- [huggingface_hub snapshot_download checksum mismatch (XET)](https://github.com/huggingface/huggingface_hub/issues/3643) -- silent corruption with XET backend
- [hf download not using XET on NFS volume](https://github.com/huggingface/huggingface_hub/issues/3463) -- NFS + XET incompatibility
- [Symlink snapshot_download files from cache (2x disk space)](https://github.com/huggingface/huggingface_hub/issues/2284) -- local_dir doubles disk usage
- [huggingface_hub async API support request](https://github.com/huggingface/huggingface_hub/issues/1123) -- no native async, thread wrapping required
- [hf download stucks on large download (XET hangs)](https://github.com/huggingface/huggingface_hub/issues/4520) -- XET reliability issues
- [Per-file progress bar for indefinite hangs](https://github.com/huggingface/huggingface_hub/issues/4452) -- download monitoring limitations
- [IncompleteSnapshotError for incomplete cached downloads](https://github.com/huggingface/diffusers/issues/14117) -- completeness detection
- [.incomplete file missing causes download failure](https://github.com/huggingface/huggingface_hub/issues/2374) -- interrupted download recovery
- [HuggingFace download guide](https://huggingface.co/docs/huggingface_hub/guides/download) -- cache_dir, local_dir, resume behavior
- [HuggingFace cache management guide](https://huggingface.co/docs/huggingface_hub/en/guides/manage-cache) -- scan_cache_dir, blob structure, symlinks
- [HuggingFace security tokens](https://huggingface.co/docs/hub/security-tokens) -- fine-grained tokens, gated repo access
- [HuggingFace environment variables](https://huggingface.co/docs/huggingface_hub/package_reference/environment_variables) -- HF_TOKEN, HF_HOME, HF_HUB_DISABLE_XET, HF_HUB_DOWNLOAD_TIMEOUT
- [Gated model 401 troubleshooting](https://discuss.huggingface.co/t/unable-to-access-model-error-401-gated-model-error-although-i-have-access/90042) -- token scope, license acceptance
- [NFS write performance (IBM)](https://www.ibm.com/docs/ssw_aix_72/performance/HT_prftungd_impr_nfs_client_writing_perf.html) -- sequential write degradation
- [NFS performance recommendations (MIT)](https://tig.csail.mit.edu/data-storage/nfs/nfs-performance/) -- block sizes, round-trip overhead, quota hazards
- [Atomic file writing in Python](https://docs.bswen.com/blog/2026-04-04-atomic-file-writing-python/) -- write-then-rename, fsync on NFS
- [FastAPI background tasks limitations](https://github.com/fastapi/fastapi/discussions/7930) -- in-memory state loss on restart
- Existing codebase: `inference_proxy/config/settings.py` -- `SecretStr` pattern for `bmc_password`, env var conventions
- Existing codebase: `inference_proxy/api/admin.py` -- `pending_hosts` dedup guard, background task firing pattern
- Existing codebase: `inference_proxy/provisioning/provisioner.py` -- `asyncio.to_thread()` for sync libs, `fire_background()` pattern
- Existing codebase: `auto-vllm/start-vllm.sh` -- NFS mount at `/srv/hf-cache`, symlink to `~/.cache/huggingface`
