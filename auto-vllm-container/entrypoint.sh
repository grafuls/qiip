#!/bin/bash
set -euo pipefail

if [[ -z "${VLLM_MODEL:-}" ]]; then
    echo "FATAL: VLLM_MODEL environment variable is required (e.g., 'Qwen/Qwen2.5-7B-Instruct')" >&2
    exit 1
fi

set -f
exec vllm serve "${VLLM_MODEL}" \
    --host 0.0.0.0 \
    --port "${VLLM_PORT:-8000}" \
    --tensor-parallel-size "${VLLM_TENSOR_PARALLEL:-1}" \
    --gpu-memory-utilization "${VLLM_GPU_MEM_UTIL:-0.90}" \
    --max-model-len "${VLLM_MAX_MODEL_LEN:-32768}" \
    --max-num-batched-tokens "${VLLM_MAX_BATCHED_TOKENS:-32768}" \
    --enable-auto-tool-choice \
    --tool-call-parser hermes \
    ${VLLM_EXTRA_ARGS:-}
