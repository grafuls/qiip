# vLLM Container

Run vLLM in a Podman container with GPU support and a shared Hugging Face cache.

## Prerequisites

- Podman with NVIDIA GPU support
- Host directory for the Hugging Face cache (e.g. `/srv/hf-cache`)

## Setup

Run the setup script:

```bash
./setup.sh
```

## Build

Build the container image:

```bash
podman build -t auto-vllm -f Containerfile .
```

## Run

Start the container:

```bash
podman run --rm --name auto-vllm \
  --network=host \
  --security-opt=label=disable \
  --device nvidia.com/gpu=all \
  --dns 8.8.8.8 \
  --dns-search redhat.com \
  -p 8000:8000 \
  -v /srv/hf-cache:/root/.cache/huggingface/hub \
  auto-vllm
```

## Health check

Verify the API is ready:

```bash
curl -s http://{HOSTNAME}:8000/health
```

Expect `{"status":"ok"}` when the server is healthy.
