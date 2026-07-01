#!/bin/bash
set -euo pipefail

# ponytail: thin entrypoint -- all config via env vars, no detection logic
exec vllm serve "${VLLM_MODEL}" \
    --host 0.0.0.0 \
    --port "${VLLM_PORT:-8000}" \
    --tensor-parallel-size "${VLLM_TENSOR_PARALLEL:-1}" \
    --gpu-memory-utilization "${VLLM_GPU_MEM_UTIL:-0.90}" \
    --max-model-len "${VLLM_MAX_MODEL_LEN:-32768}" \
    --max-num-batched-tokens "${VLLM_MAX_BATCHED_TOKENS:-32768}" \
    ${VLLM_EXTRA_ARGS:-}
