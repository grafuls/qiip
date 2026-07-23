#!/bin/bash
set -euo pipefail

# --- Configurable defaults (D-07, D-08) ---
NFS_SERVER="${NFS_SERVER:-rdu-storage02.scalelab.redhat.com:/mnt/SATA/scratch/grafuls/hf-cache}"
NFS_MOUNT_POINT="${NFS_MOUNT_POINT:-/srv/hf-cache}"
NVIDIA_DRIVER_VERSION="${NVIDIA_DRIVER_VERSION:-580.126.09}"
NVIDIA_DRIVER_URL="${NVIDIA_DRIVER_URL:-https://us.download.nvidia.com/tesla/${NVIDIA_DRIVER_VERSION}/NVIDIA-Linux-x86_64-${NVIDIA_DRIVER_VERSION}.run}"
VLLM_PORT="${VLLM_PORT:-8000}"

# --- Step wrapper (D-10) ---
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

# --- Step functions (D-09, D-06 idempotency) ---

install_nvidia_repo() {
    if [ -f /etc/yum.repos.d/nvidia-container-toolkit.repo ]; then
        echo "NVIDIA repo already configured, skipping"
        return 0
    fi
    curl -fsSL https://nvidia.github.io/libnvidia-container/stable/rpm/nvidia-container-toolkit.repo \
        | sudo tee /etc/yum.repos.d/nvidia-container-toolkit.repo > /dev/null
}

run_system_update() {
    sudo dnf -y update
    sudo dnf -y install kernel-devel-"$(uname -r)" kernel-headers-"$(uname -r)" \
        nvidia-container-toolkit podman-plugins gcc make wget podman nfs-utils elfutils-libelf-devel
}

install_nvidia_driver() {
    if nvidia-smi &>/dev/null; then
        echo "NVIDIA driver already installed, skipping"
        return 0
    fi
    # Driver may be installed (e.g. via RPM) but kernel module not loaded
    if modinfo nvidia &>/dev/null; then
        echo "NVIDIA kernel module found but not loaded, loading"
        sudo modprobe nvidia
        nvidia-smi
        return $?
    fi
    # Driver userspace libs exist without kernel module — RPM driver whose
    # kmod isn't built for the running kernel.  The .run installer will
    # refuse ("alternate driver installation"), so rebuild the kmod instead.
    if ls /usr/lib64/libnvidia-ml.so.* &>/dev/null; then
        echo "RPM-installed NVIDIA driver found, kernel module missing for $(uname -r)"
        echo "Rebuilding kernel module"
        sudo dkms autoinstall 2>/dev/null || sudo akmods --force 2>/dev/null || true
        sudo modprobe nvidia
        nvidia-smi
        return $?
    fi
    # No driver at all — install via .run
    echo 'blacklist nouveau' | sudo tee /etc/modprobe.d/blacklist-nouveau.conf
    sudo dracut --force
    sudo modprobe -r nouveau 2>/dev/null || true
    wget -q "${NVIDIA_DRIVER_URL}" -O /tmp/NVIDIA-driver.run
    chmod +x /tmp/NVIDIA-driver.run
    sudo sh /tmp/NVIDIA-driver.run --dkms --no-x-check --no-nouveau-check --ui=none --no-questions
    rm -f /tmp/NVIDIA-driver.run
}

generate_nvidia_cdi() {
    if [ -f /etc/cdi/nvidia.yaml ]; then
        echo "NVIDIA CDI descriptor already exists, skipping"
        return 0
    fi
    sudo nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml
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

# --- Main (D-11: 6 step names) ---
step nvidia_repo install_nvidia_repo
step system_update run_system_update
step nvidia_driver install_nvidia_driver
step nvidia_cdi generate_nvidia_cdi
step nfs_mount mount_nfs_cache
step firewall configure_firewall

echo "Setup complete"
