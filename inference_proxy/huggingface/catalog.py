"""HuggingFace model catalog service.

Scans a local HuggingFace cache directory (typically NFS-mounted) and
returns the list of cached model repositories.
"""

from __future__ import annotations

import asyncio

import structlog
from huggingface_hub import scan_cache_dir
from pydantic import BaseModel

logger = structlog.get_logger()


class CatalogEntry(BaseModel):
    """A single cached model repository."""

    repo_id: str


class ModelCatalogResponse(BaseModel):
    """Response payload for the model catalog endpoint."""

    models: list[CatalogEntry]


class ModelCatalogService:
    """Lists model repos found in a HuggingFace cache directory.

    Wraps ``scan_cache_dir`` in ``asyncio.to_thread`` so the blocking
    filesystem scan does not stall the event loop.
    """

    def __init__(self, cache_dir: str) -> None:
        self._cache_dir = cache_dir

    async def list_models(self) -> list[CatalogEntry]:
        """Return catalog entries for every *model* repo in the cache."""
        cache_info = await asyncio.to_thread(scan_cache_dir, self._cache_dir)
        return [
            CatalogEntry(repo_id=repo.repo_id)
            for repo in cache_info.repos
            if repo.repo_type == "model"
        ]
