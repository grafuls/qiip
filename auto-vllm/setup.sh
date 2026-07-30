#!/bin/bash
set -euo pipefail

# --- Configurable defaults ---
NFS_SERVER="${NFS_SERVER:-storage.example.com:/mnt/SATA/scratch/grafuls/hf-cache}"
NFS_MOUNT_POINT="${NFS_MOUNT_POINT:-/srv/hf-cache}"
NVIDIA_DRIVER_VERSION="${NVIDIA_DRIVER_VERSION:-580.126.09}"
NVIDIA_DRIVER_URL="${NVIDIA_DRIVER_URL:-https://us.download.nvidia.com/tesla/${NVIDIA_DRIVER_VERSION}/NVIDIA-Linux-x86_64-${NVIDIA_DRIVER_VERSION}.run}"
VLLM_PORT="${VLLM_PORT:-8000}"
LLMFIT_VERSION="${LLMFIT_VERSION:-1.1.6}"
LLMFIT_URL="${LLMFIT_URL:-https://github.com/AlexsJones/llmfit/releases/download/v${LLMFIT_VERSION}/llmfit-v${LLMFIT_VERSION}-x86_64-unknown-linux-musl.tar.gz}"

# --- Step wrapper ---
step() {
    local name="$1"; shift
    echo "[STEP:${name}:START]"
    if "$@"; then
        echo "[STEP:${name}:OK]"
    else
        echo "[STEP:${name}:FAIL]"
        exit 1
    fi
}

# --- Soft step wrapper (non-fatal) ---
soft_step() {
    local name="$1"; shift
    echo "[STEP:${name}:START]"
    if "$@"; then
        echo "[STEP:${name}:OK]"
    else
        echo "[STEP:${name}:WARN] (non-fatal, continuing)"
    fi
}

# --- Step functions (idempotent) ---

run_system_update() {
    sudo dnf -y update
    sudo dnf -y install kernel-devel-"$(uname -r)" kernel-headers-"$(uname -r)" \
        gcc make wget nfs-utils elfutils-libelf-devel python3.12 python3.12-devel
}

install_nvidia_driver() {
    if nvidia-smi &>/dev/null; then
        echo "NVIDIA driver already installed, skipping"
        return 0
    fi
    if modinfo nvidia &>/dev/null; then
        echo "NVIDIA kernel module found but not loaded, loading"
        sudo modprobe nvidia
    fi
    # RPM driver whose kmod isn't built for the running kernel.
    if ls /usr/lib64/libnvidia-ml.so.* &>/dev/null; then
        echo "RPM-installed NVIDIA driver found, kernel module missing for $(uname -r)"
        echo "Rebuilding kernel module"
        if (sudo dkms autoinstall 2>/dev/null || sudo akmods --force 2>/dev/null) \
            && sudo modprobe nvidia && nvidia-smi; then
            return 0
        fi
        echo "Kernel module rebuild failed, removing broken RPM driver"
        sudo dnf -y remove '*nvidia*driver*' 2>/dev/null || true
        sudo rm -f /etc/modprobe.d/blacklist-nouveau.conf
    fi
    echo 'blacklist nouveau' | sudo tee /etc/modprobe.d/blacklist-nouveau.conf
    sudo dracut --force
    sudo modprobe -r nouveau 2>/dev/null || true
    wget -q "${NVIDIA_DRIVER_URL}" -O /tmp/NVIDIA-driver.run
    chmod +x /tmp/NVIDIA-driver.run
    sudo sh /tmp/NVIDIA-driver.run --dkms --no-x-check --no-nouveau-check --ui=none --no-questions
    rm -f /tmp/NVIDIA-driver.run
}

install_vllm() {
    if [ -x /opt/vllm-venv/bin/vllm ]; then
        echo "vLLM already installed in /opt/vllm-venv, skipping"
        return 0
    fi
    python3.12 -m venv /opt/vllm-venv
    /opt/vllm-venv/bin/pip install --upgrade pip
    /opt/vllm-venv/bin/pip install vllm
}

mount_nfs_cache() {
    if mountpoint -q "${NFS_MOUNT_POINT}"; then
        echo "NFS already mounted at ${NFS_MOUNT_POINT}, skipping"
        return 0
    fi
    sudo mkdir -p "${NFS_MOUNT_POINT}"
    sudo timeout --kill-after=5 30 \
        mount -t nfs -o vers=3,soft,timeo=100,retrans=2 "${NFS_SERVER}" "${NFS_MOUNT_POINT}"
}

configure_firewall() {
    if command -v firewall-cmd &>/dev/null && systemctl is-active --quiet firewalld; then
        if sudo firewall-cmd --query-port="${VLLM_PORT}/tcp" &>/dev/null; then
            echo "Firewall rule already exists for port ${VLLM_PORT}, skipping"
            return 0
        fi
        sudo firewall-cmd --add-port="${VLLM_PORT}/tcp" --permanent
        sudo firewall-cmd --reload
    else
        if sudo iptables -C INPUT -p tcp --dport "${VLLM_PORT}" -j ACCEPT 2>/dev/null; then
            echo "Firewall rule already exists for port ${VLLM_PORT}, skipping"
            return 0
        fi
        sudo iptables -I INPUT -p tcp --dport "${VLLM_PORT}" -j ACCEPT
        sudo iptables-save | sudo tee /etc/sysconfig/iptables > /dev/null
        sudo systemctl restart iptables
    fi
}

install_llmfit() {
    if [ -x /usr/local/bin/llmfit ]; then
        echo "llmfit already installed, skipping"
        return 0
    fi
    wget -q "${LLMFIT_URL}" -O /tmp/llmfit.tar.gz
    tar -xzf /tmp/llmfit.tar.gz -C /tmp/
    sudo install -m 755 "$(find /tmp/ -name llmfit -type f -print -quit)" /usr/local/bin/llmfit
    rm -rf /tmp/llmfit.tar.gz /tmp/llmfit-*
}

# --- Main ---
step system_update run_system_update
step nvidia_driver install_nvidia_driver
step vllm_install install_vllm
step nfs_mount mount_nfs_cache
step firewall configure_firewall
soft_step llmfit_install install_llmfit

echo "Setup complete"
