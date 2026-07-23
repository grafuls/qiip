# auto-vllm

Provision and run vLLM directly on bare-metal GPU nodes.

## Prerequisites

- NVIDIA GPU with driver installed (setup.sh handles this)
- NFS-mounted Hugging Face cache at `/srv/hf-cache`

## Setup

Run the setup script to install drivers, Python, vLLM, mount NFS, and open the firewall:

```bash
./setup.sh
```

## Run

Start vLLM (auto-detects GPU and selects model):

```bash
./start-vllm.sh
```

vLLM runs as a background process. PID is written to `/var/run/vllm.pid`, logs to `/var/log/vllm-serve.log`.

## Health check

```bash
curl -s http://{HOSTNAME}:8000/health
```

## Stop

```bash
kill $(cat /var/run/vllm.pid)
```
