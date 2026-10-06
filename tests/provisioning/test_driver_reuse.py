"""Run the real setup boundary against controlled GPU and package commands."""

from __future__ import annotations

import hashlib
import os
import shlex
import subprocess
from pathlib import Path

import pytest

ROOT = Path(
    os.environ.get("AUTOVLLM_TEST_SCRIPT_ROOT", Path(__file__).resolve().parents[2])
)
DRIVER = "580.126.09"
INSTALLER = '#!/bin/sh\ntouch "$FIXTURE_ROOT/repaired"\nexit "${INSTALL_RC:-0}"\n'


def _host(tmp_path: Path, **settings: str) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (tmp_path / "devices").mkdir()
    (tmp_path / "devices" / "nvidia0").touch()
    (tmp_path / "modules").mkdir()
    if settings.get("MODULE_PRESENT") == "1":
        (tmp_path / "modules" / "nvidia").mkdir()
    (tmp_path / "os-release").write_text('ID=rhel\nVERSION_ID="9.5"\n')
    (tmp_path / "boot-id").write_text("boot-one\n")
    dispatcher = bin_dir / "fixture"
    dispatcher.write_text(
        r"""#!/usr/bin/python3
import json, os, pathlib, subprocess, sys
root = pathlib.Path(os.environ["FIXTURE_ROOT"])
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
with (root / "operations").open("a") as log:
    log.write(json.dumps([name, *args]) + "\n")
repaired = (root / "repaired").exists()
working = os.environ.get("DRIVER_WORKING", "1") == "1" or repaired or (root / "loaded").exists() or (root / "rebuilt").exists()
version = os.environ.get("INSTALLED_DRIVER", "580.95.05") if not repaired else "580.126.09"
if name == "nvidia-smi":
    if not working or (repaired and os.environ.get("NEEDS_REBOOT") == "1"):
        sys.exit(1)
    query = " ".join(args)
    if "--query-compute-apps" in query:
        print("1234" if os.environ.get("GPU_BUSY") == "1" else "")
    elif "driver_version" in query: print(version)
    elif "--list-gpus" in query: print("GPU 0: fixture")
    elif "compute_cap" in query: print(os.environ.get("SM", "8.0"))
    elif "memory.total" in query: print("81920")
    elif "name" in query: print("NVIDIA fixture")
elif name == "nvcc":
    if "--version" in args:
        print("V" + os.environ.get("TOOLKIT", "13.0") + ".123")
    elif os.environ.get("COMPILE_RC", "0") != "0": sys.exit(1)
    else:
        out = pathlib.Path(args[args.index("-o") + 1])
        out.write_text('#!/bin/sh\necho CUDA_EXECUTED >> "$FIXTURE_ROOT/operations"\nexit "${PROBE_RC:-0}"\n')
        out.chmod(0o755)
elif name == "lspci": print("0000:00:01.0 0302: 10de:20b0")
elif name == "uname": print("x86_64" if "-m" in args else "5.14.fixture")
elif name == "ldd": print("ldd (GNU libc) 2.34")
elif name == "modinfo":
    if os.environ.get("MODULE_PRESENT") != "1": sys.exit(1)
    print(os.environ.get("INSTALLED_DRIVER", "580.95.05"))
elif name == "rpm":
    if "--qf" in args:
        if os.environ.get("RPM_DRIVER") != "1": sys.exit(1)
        print(version)
    elif any("kernel-" in arg for arg in args): sys.exit(1)
    elif os.environ.get("PACKAGES_PRESENT", "1") != "1": sys.exit(1)
elif name == "wget":
    if os.environ.get("DOWNLOAD_RC", "0") != "0": sys.exit(1)
    pathlib.Path(args[args.index("-O") + 1]).write_text(os.environ["INSTALLER"])
elif name == "sudo":
    command, *rest = args
    if command == "fuser": sys.exit(int(os.environ.get("FUSER_RC", "1")))
    if command == "dnf" and any("kernel-" in arg for arg in rest):
        sys.exit(int(os.environ.get("HEADERS_RC", "0")))
    if command in ("dkms", "akmods"):
        if os.environ.get("REBUILD_RC", "1") == "0": (root / "rebuilt").touch()
        sys.exit(int(os.environ.get("REBUILD_RC", "1")))
    if command == "modprobe":
        if "-r" not in rest and os.environ.get("MODULE_LOAD_WORKS") == "1": (root / "loaded").touch()
        sys.exit(int(os.environ.get("UNLOAD_RC", "0")) if "-r" in rest else 0)
    if command == "sh": sys.exit(subprocess.call(["sh", *rest]))
    if command == "tee":
        content = sys.stdin.read()
        if rest[0].startswith(str(root)): pathlib.Path(rest[0]).write_text(content)
    if command in ("mkdir", "install"):
        if command == "mkdir" or "-d" in rest: pathlib.Path(rest[-1]).mkdir(parents=True, exist_ok=True)
    if command == "rm":
        for arg in rest:
            if not arg.startswith("-") and arg.startswith(str(root)): pathlib.Path(arg).unlink(missing_ok=True)
    if command == "dnf" and "update" in rest: sys.exit(99)
    sys.exit(0)
else: sys.exit(99)
"""
    )
    dispatcher.chmod(0o755)
    for command in (
        "nvidia-smi",
        "nvcc",
        "lspci",
        "uname",
        "ldd",
        "modinfo",
        "rpm",
        "wget",
        "sudo",
        "dkms",
        "akmods",
    ):
        (bin_dir / command).symlink_to(dispatcher)
    return {
        **{key: value for key, value in os.environ.items() if key != "BASH_ENV"},
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "FIXTURE_ROOT": str(tmp_path),
        "AUTOVLLM_NFS_EXPORT": "storage:/cache",
        "AUTOVLLM_TMP_DIR": str(tmp_path),
        "AUTOVLLM_DRIVER_STATE_DIR": str(tmp_path / "state"),
        "PROFILE_OS_RELEASE": str(tmp_path / "os-release"),
        "CUDA_NVCC": str(bin_dir / "nvcc"),
        "INSTALLER": INSTALLER,
        "AUTOVLLM_NVIDIA_DRIVER_SHA256": hashlib.sha256(INSTALLER.encode()).hexdigest(),
        **settings,
    }


def _setup(
    env: dict[str, str], engine: str = "vllm"
) -> subprocess.CompletedProcess[str]:
    setup = ROOT / f"auto-{engine}" / "setup.sh"
    command = f"""
source {shlex.quote(str(setup))}
GPU_DEVICE_ROOT="$FIXTURE_ROOT/devices"
GPU_MODULE_ROOT="$FIXTURE_ROOT/modules"
BOOT_ID_FILE="$FIXTURE_ROOT/boot-id"
install_vllm() {{ echo ENGINE_INSTALLED; }}
install_llamacpp() {{ echo ENGINE_INSTALLED; }}
install_vllm_unit() {{ :; }}
mount_nfs_cache() {{ :; }}
configure_firewall() {{ :; }}
install_llmfit() {{ :; }}
main
"""
    return subprocess.run(
        ["bash", "-c", command],
        env=env,
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )


def _operations(tmp_path: Path) -> str:
    return (tmp_path / "operations").read_text()


@pytest.mark.parametrize("engine", ["vllm", "llamacpp"])
@pytest.mark.parametrize("version", [DRIVER, "580.95.05", "590.48.01"])
def test_compatible_driver_runs_without_kernel_headers_or_replacement(
    tmp_path: Path, engine: str, version: str
) -> None:
    env = _host(tmp_path, INSTALLED_DRIVER=version, HEADERS_RC="1")
    result = _setup(env, engine)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ENGINE_INSTALLED" in result.stdout
    operations = _operations(tmp_path)
    assert "CUDA_EXECUTED" in operations
    assert "kernel-" not in operations
    assert '"update"' not in operations
    assert '["wget"' not in operations
    assert '"remove"' not in operations


@pytest.mark.parametrize("engine", ["vllm", "llamacpp"])
def test_incompatible_driver_is_replaced_then_proved(
    tmp_path: Path, engine: str
) -> None:
    result = _setup(_host(tmp_path, INSTALLED_DRIVER="570.172.08"), engine)
    assert result.returncode == 0, result.stdout + result.stderr
    operations = _operations(tmp_path)
    assert "kernel-devel-5.14.fixture" in operations
    assert operations.index('["wget"') < operations.index('"remove"')
    assert operations.index('"sh"') < operations.index("CUDA_EXECUTED")
    assert "ENGINE_INSTALLED" in result.stdout


@pytest.mark.parametrize("repair", ["install", "rebuild"])
def test_missing_module_is_repaired_before_profile_and_cuda_proof(
    tmp_path: Path, repair: str
) -> None:
    env = _host(
        tmp_path,
        DRIVER_WORKING="0",
        RPM_DRIVER="1" if repair == "rebuild" else "0",
        REBUILD_RC="0",
    )
    result = _setup(env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "[PROFILE:select:" in result.stdout
    assert "CUDA_EXECUTED" in _operations(tmp_path)
    assert (
        '"dkms"' in _operations(tmp_path)
        if repair == "rebuild"
        else '"sh"' in _operations(tmp_path)
    )


@pytest.mark.parametrize(
    "settings,reason",
    [
        ({"AUTOVLLM_NVIDIA_DRIVER_SHA256": "0" * 64}, "SHA-256"),
        ({"DOWNLOAD_RC": "1"}, ""),
        ({"GPU_BUSY": "1"}, "maintenance_required"),
        ({"FUSER_RC": "2"}, "maintenance_required"),
        ({"HEADERS_RC": "1"}, "maintenance_required"),
        ({"INSTALL_RC": "7"}, "installation failed"),
    ],
)
def test_repair_failures_never_reach_engine(
    tmp_path: Path, settings: dict[str, str], reason: str
) -> None:
    result = _setup(_host(tmp_path, INSTALLED_DRIVER="570.172.08", **settings))
    assert result.returncode != 0
    assert "ENGINE_INSTALLED" not in result.stdout
    assert reason in result.stdout + result.stderr
    if "INSTALL_RC" not in settings:
        assert '"remove"' not in _operations(tmp_path)
        assert '"sh"' not in _operations(tmp_path)


def test_reboot_state_blocks_same_boot_and_resumes_with_revalidation(
    tmp_path: Path,
) -> None:
    env = _host(tmp_path, INSTALLED_DRIVER="570.172.08", NEEDS_REBOOT="1")
    result = _setup(env)
    assert result.returncode != 0
    assert "[RESUME:reboot_required:" in result.stdout
    assert "ENGINE_INSTALLED" not in result.stdout
    first_operations = _operations(tmp_path)
    result = _setup(env)
    assert result.returncode != 0
    assert (
        _operations(tmp_path) == first_operations
    )  # no repeated install on the same boot
    (tmp_path / "boot-id").write_text("boot-two\n")
    env["NEEDS_REBOOT"] = "0"
    result = _setup(env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "CUDA_EXECUTED" in _operations(tmp_path)
    assert "ENGINE_INSTALLED" in result.stdout
    assert not (tmp_path / "state" / "driver-reboot").exists()


def test_nvidia_smi_success_without_cuda_execution_blocks_launch(
    tmp_path: Path,
) -> None:
    result = _setup(_host(tmp_path, PROBE_RC="1"))
    assert result.returncode != 0
    assert "[RESUME:maintenance_required:" in result.stdout
    assert "ENGINE_INSTALLED" not in result.stdout
    assert '"remove"' not in _operations(tmp_path)


def test_compile_failure_does_not_replace_a_compatible_driver(tmp_path: Path) -> None:
    result = _setup(_host(tmp_path, COMPILE_RC="1"))
    assert result.returncode != 0
    assert "ENGINE_INSTALLED" not in result.stdout
    assert '"remove"' not in _operations(tmp_path)
    assert "RESUME:reboot_required" not in result.stdout


def test_unloaded_module_is_loaded_without_kernel_build_dependencies(
    tmp_path: Path,
) -> None:
    result = _setup(
        _host(
            tmp_path,
            DRIVER_WORKING="0",
            MODULE_PRESENT="1",
            MODULE_LOAD_WORKS="1",
            HEADERS_RC="1",
        )
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "CUDA_EXECUTED" in _operations(tmp_path)
    assert "kernel-" not in _operations(tmp_path)


def test_unload_failure_requests_reboot_before_removing_driver(tmp_path: Path) -> None:
    result = _setup(
        _host(
            tmp_path, INSTALLED_DRIVER="570.172.08", MODULE_PRESENT="1", UNLOAD_RC="1"
        )
    )
    assert result.returncode != 0
    assert "[RESUME:reboot_required:" in result.stdout
    assert '"remove"' not in _operations(tmp_path)
    assert '"sh"' not in _operations(tmp_path)


def test_working_driver_does_not_require_replacement_digest(tmp_path: Path) -> None:
    result = _setup(_host(tmp_path, AUTOVLLM_NVIDIA_DRIVER_SHA256=""))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "CUDA_EXECUTED" in _operations(tmp_path)


def test_unreadable_version_evidence_does_not_replace_driver(tmp_path: Path) -> None:
    result = _setup(_host(tmp_path, INSTALLED_DRIVER="unknown"))
    assert result.returncode != 0
    assert "[RESUME:maintenance_required:" in result.stdout
    assert '"remove"' not in _operations(tmp_path)


def test_wrong_toolkit_cannot_prove_profile_readiness(tmp_path: Path) -> None:
    result = _setup(_host(tmp_path, TOOLKIT="12.4"))
    assert result.returncode != 0
    assert "CUDA proof requires toolkit 13.0" in result.stderr
    assert "CUDA_EXECUTED" not in _operations(tmp_path)
    assert "ENGINE_INSTALLED" not in result.stdout


def test_volta_reuses_cuda12_driver_for_llamacpp(tmp_path: Path) -> None:
    result = _setup(
        _host(
            tmp_path,
            SM="7.0",
            TOOLKIT="12.9",
            INSTALLED_DRIVER="575.57.08",
            HEADERS_RC="1",
        ),
        "llamacpp",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "llamacpp-volta" in result.stdout
    assert "kernel-" not in _operations(tmp_path)


def test_volta_missing_module_rebuild_preserves_cuda12_driver(tmp_path: Path) -> None:
    result = _setup(
        _host(
            tmp_path,
            SM="7.0",
            TOOLKIT="12.9",
            INSTALLED_DRIVER="575.57.08",
            DRIVER_WORKING="0",
            RPM_DRIVER="1",
            REBUILD_RC="0",
        ),
        "llamacpp",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "llamacpp-volta" in result.stdout
    assert '"dkms"' in _operations(tmp_path)
    assert '"sh"' not in _operations(tmp_path)
    assert '"remove"' not in _operations(tmp_path)
    assert "CUDA_EXECUTED" in _operations(tmp_path)


def test_unsupported_host_is_rejected_before_driver_or_packages(tmp_path: Path) -> None:
    env = _host(tmp_path, DRIVER_WORKING="0")
    (tmp_path / "os-release").write_text('ID=rhel\nVERSION_ID="10"\n')
    result = _setup(env)
    assert result.returncode == 3
    assert "unsupported_hardware" in result.stderr
    assert not (tmp_path / "operations").exists() or '"sudo"' not in _operations(
        tmp_path
    )
