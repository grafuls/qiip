#!/bin/bash
set -euo pipefail

VLLM_PORT="${VLLM_PORT:-8000}"
NFS_MOUNT_POINT="${NFS_MOUNT_POINT:-/srv/hf-cache}"

detect_gpu_info() {
    if ! command -v nvidia-smi &>/dev/null; then
        echo "FATAL: nvidia-smi not found. Run setup.sh first or install NVIDIA drivers." >&2
        exit 1
    fi
    if ! nvidia-smi &>/dev/null; then
        echo "FATAL: nvidia-smi failed. NVIDIA driver may not be loaded." >&2
        exit 1
    fi
    GPU_MODEL=$(nvidia-smi --query-gpu=name --format=csv,noheader -i 0 | xargs)
    GPU_COUNT=$(nvidia-smi --list-gpus | wc -l)
    GPU_VRAM_MB=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits -i 0)
    GPU_VRAM_GB=$(( (GPU_VRAM_MB + 512) / 1024 ))
}

configure_vllm_params() {
    local total_vram=$((GPU_COUNT * GPU_VRAM_GB))

    TENSOR_PARALLEL=$GPU_COUNT
    GPU_MEM_UTIL=0.90
    MAX_MODEL_LEN=32768
    MAX_BATCHED_TOKENS=32768
    EXTRA_ARGS=""

    case "$GPU_MODEL" in
        *"H100"*|*"A100"*)
            echo "High-end GPU detected: optimizing for throughput"
            if [ $total_vram -ge 240 ]; then
                MODEL="Qwen/Qwen2.5-72B-Instruct"
                MAX_MODEL_LEN=32768
            elif [ $total_vram -ge 160 ]; then
                MODEL="Qwen/Qwen2.5-32B-Instruct"
                MAX_MODEL_LEN=131072
            else
                MODEL="Qwen/Qwen2.5-32B-Instruct"
                MAX_MODEL_LEN=32768
                TENSOR_PARALLEL=1
            fi
            GPU_MEM_UTIL=0.90
            ;;

        *"T4"*)
            echo "Tesla T4 detected: optimizing for memory efficiency"
            TENSOR_PARALLEL=1
            GPU_MEM_UTIL=0.75
            MAX_MODEL_LEN=2048
            MAX_BATCHED_TOKENS=2048
            EXTRA_ARGS="--enforce-eager --dtype float16"

            if [ $GPU_VRAM_GB -le 16 ]; then
                MODEL="Qwen/Qwen2.5-3B-Instruct"
            else
                MODEL="Qwen/Qwen2.5-7B-Instruct"
            fi
            ;;

        *"V100"*)
            echo "Tesla V100 detected: balanced configuration"
            TENSOR_PARALLEL=$GPU_COUNT
            GPU_MEM_UTIL=0.85
            MAX_MODEL_LEN=8192

            if [ $total_vram -ge 64 ]; then
                MODEL="Qwen/Qwen2.5-32B-Instruct"
            else
                MODEL="Qwen/Qwen2.5-14B-Instruct"
            fi
            ;;

        *"RTX"*|*"GeForce"*)
            echo "Consumer GPU detected: conservative settings"
            TENSOR_PARALLEL=1
            GPU_MEM_UTIL=0.80
            MAX_MODEL_LEN=4096

            if [ $GPU_VRAM_GB -ge 24 ]; then
                MODEL="Qwen/Qwen2.5-14B-Instruct"
            else
                MODEL="Qwen/Qwen2.5-7B-Instruct"
            fi
            EXTRA_ARGS="--enforce-eager"
            ;;

        *)
            echo "Unknown GPU: using conservative defaults"
            TENSOR_PARALLEL=1
            GPU_MEM_UTIL=0.75
            MAX_MODEL_LEN=4096
            MODEL="Qwen/Qwen2.5-7B-Instruct"
            EXTRA_ARGS="--enforce-eager"
            ;;
    esac

    MODEL="${VLLM_MODEL:-$MODEL}"
    TENSOR_PARALLEL="${VLLM_TENSOR_PARALLEL:-$TENSOR_PARALLEL}"
    GPU_MEM_UTIL="${VLLM_GPU_MEM_UTIL:-$GPU_MEM_UTIL}"
    MAX_MODEL_LEN="${VLLM_MAX_MODEL_LEN:-$MAX_MODEL_LEN}"
    MAX_BATCHED_TOKENS="${VLLM_MAX_BATCHED_TOKENS:-$MAX_BATCHED_TOKENS}"
    EXTRA_ARGS="${VLLM_EXTRA_ARGS:-$EXTRA_ARGS}"
}

run_vllm() {
    cat <<EOF

# vLLM Configuration
# ================================================
# GPU:                $GPU_COUNT x $GPU_MODEL ($GPU_VRAM_GB GB)
# Model:              $MODEL
# Tensor Parallel:    $TENSOR_PARALLEL
# Memory Util:        ${GPU_MEM_UTIL}
# Max Context:        $MAX_MODEL_LEN tokens
# Max Batched Tokens: $MAX_BATCHED_TOKENS tokens
# ================================================

EOF

    mkdir -p /root/.cache
    ln -sfn "${NFS_MOUNT_POINT}" /root/.cache/huggingface

    set -f
    /opt/vllm-venv/bin/vllm serve "$MODEL" \
        --host 0.0.0.0 \
        --port "${VLLM_PORT}" \
        --tensor-parallel-size "$TENSOR_PARALLEL" \
        --gpu-memory-utilization "$GPU_MEM_UTIL" \
        --max-model-len "$MAX_MODEL_LEN" \
        --max-num-batched-tokens "$MAX_BATCHED_TOKENS" \
        --enable-auto-tool-choice \
        --tool-call-parser hermes \
        ${EXTRA_ARGS:-} \
        > /var/log/vllm-serve.log 2>&1 &

    echo $! > /var/run/vllm.pid
    echo "vLLM started (PID $(cat /var/run/vllm.pid))"
}

main() {
    detect_gpu_info
    configure_vllm_params
    run_vllm
}

main
