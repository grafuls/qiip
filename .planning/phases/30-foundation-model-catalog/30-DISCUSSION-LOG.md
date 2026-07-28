# Phase 30: Foundation & Model Catalog - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-28
**Phase:** 30-Foundation & Model Catalog
**Areas discussed:** Catalog scan strategy, Catalog response detail

---

## Catalog Scan Strategy

### How should the gateway scan NFS for downloaded models?

| Option | Description | Selected |
|--------|-------------|----------|
| On-demand per request | Wrap scan_cache_dir() in asyncio.to_thread on each GET /admin/models/catalog call. Simplest — no background thread, no stale cache. If NFS is slow, add caching later. | ✓ |
| Background poller | Periodic scan (like QUADS poller) with in-memory cache. Faster API responses but adds a background thread and staleness window. | |
| You decide | Claude picks the laziest option that works. | |

**User's choice:** On-demand per request
**Notes:** None

### Where should the catalog service live in the codebase?

| Option | Description | Selected |
|--------|-------------|----------|
| New huggingface/ package | inference_proxy/huggingface/catalog.py — follows the pattern of quads/, llmfit/, redfish/ domain packages. Clean separation for Phase 31 download service to join later. | ✓ |
| Inline in admin.py | Just call scan_cache_dir() directly in the route handler. Minimal files but mixes concerns. | |

**User's choice:** New huggingface/ package
**Notes:** None

### Should the HuggingFace feature be optional or always-on?

| Option | Description | Selected |
|--------|-------------|----------|
| Always-on with required cache_dir | NFS cache path is required config — gateway won't start without it. HF token is optional (only needed for gated models). Simpler since the whole v1.7 milestone depends on NFS. | ✓ |
| Optional via None guard | cache_dir defaults to None, catalog returns empty list when unconfigured. Follows QUADS/Redfish pattern but adds conditional logic everywhere. | |

**User's choice:** Always-on with required cache_dir
**Notes:** None

---

## Catalog Response Detail

### What should each catalog entry include beyond the repo_id?

| Option | Description | Selected |
|--------|-------------|----------|
| Repo ID + size on disk | repo_id and size_on_disk_bytes. Both come free from scan_cache_dir(). Size helps operators gauge NFS usage. | |
| Repo ID only | Absolute minimum — just a list of repo_id strings. Simplest response shape but loses the free metadata. | ✓ |
| Full metadata | repo_id, size_on_disk, last_modified, nb_files, revisions. Maximum info but larger response and more model fields to maintain. | |

**User's choice:** Repo ID only
**Notes:** None

### Should the catalog endpoint return flat strings or objects?

| Option | Description | Selected |
|--------|-------------|----------|
| Objects with repo_id field | List of {"repo_id": "meta-llama/..."} objects. Easy to add fields later without breaking clients. | ✓ |
| Flat string list | ["meta-llama/...", "mistralai/..."] — terser but adding fields later is a breaking change. | |

**User's choice:** Objects with repo_id field
**Notes:** None

---

## Claude's Discretion

None — user made all selections.

## Deferred Ideas

None — discussion stayed within phase scope.
