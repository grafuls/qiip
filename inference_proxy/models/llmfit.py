"""Pydantic models for llmfit ``recommend --json`` output.

Parses system hardware info and ranked model recommendations into
typed, immutable objects.  ``extra="ignore"`` ensures forward
compatibility when llmfit adds new fields (T-25-01).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SystemInfo(BaseModel):
    """Hardware profile detected by llmfit."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    has_gpu: bool
    gpu_vram_gb: float = 0.0
    gpu_name: str = ""
    cpu_name: str = ""
    total_ram_gb: float = 0.0
    available_ram_gb: float = 0.0
    cpu_cores: int = 0
    unified_memory: bool = False
    backend: str = ""


class ModelRecommendation(BaseModel):
    """A single model recommendation from llmfit."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    name: str
    score: float = 0.0
    fit_level: str = ""
    estimated_tps: float = 0.0
    memory_required_gb: float = 0.0
    provider: str = ""
    best_quant: str = ""
    run_mode: str = ""
    params_b: float = 0.0
    context_length: int = 0
    utilization_pct: float = 0.0
    category: str = ""
    runtime: str = ""


class LLMFitResult(BaseModel):
    """Top-level result from ``llmfit recommend --json``."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    system: SystemInfo
    models: list[ModelRecommendation]
