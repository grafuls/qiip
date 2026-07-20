"""Node provisioning orchestrator.

Runs the full provisioning sequence on a remote host: setup.sh,
start-vllm.sh, health poll, etcd registration.

Per D-15: Concrete class, no protocol/interface.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Coroutine
from datetime import datetime, timezone

import httpx
import structlog

from inference_proxy.config.settings import ProvisioningSettings
from inference_proxy.discovery.etcd_client import EtcdClient
from inference_proxy.discovery.registry import NodeRegistry
from inference_proxy.discovery.serializer import node_to_etcd
from inference_proxy.models.node import Node, NodeStatus
from inference_proxy.provisioning.ssh_client import (
    RemoteCommandError,
    SSHClient,
    SSHConnectionError,
)
from inference_proxy.provisioning.state import ProvisioningState, ProvisioningStep
from inference_proxy.routing.connection_tracker import ConnectionTracker

logger = structlog.get_logger()

STEP_PATTERN = re.compile(r"\[STEP:(\w+):(START|OK|FAIL)\]")
MODEL_PATTERN = re.compile(r"#\s*Model:\s+(.+)")


def _derive_container_name(model: str) -> str:
    """Replicate start-vllm.sh container name derivation."""
    suffix = model.rsplit("/", 1)[-1].lower()
    return f"vllm-{suffix}"


class ProvisioningError(Exception):
    """Raised when any stage of provisioning fails."""


class PreflightError(Exception):
    """Raised when pre-flight validation fails (D-01 through D-04).

    Collects all failures before raising so operators see every problem
    at once (D-03).
    """

    def __init__(self, hostname: str, failures: list[str]) -> None:
        self.hostname = hostname
        self.failures = failures
        super().__init__(f"Pre-flight failed on {hostname}: {'; '.join(failures)}")


class NodeProvisioner:
    """Orchestrates full provisioning of a vLLM node on a remote host.

    Accepts SSHClient, EtcdClient, and ProvisioningSettings via
    constructor injection (DIP).
    """

    def __init__(
        self,
        ssh_client: SSHClient,
        etcd_client: EtcdClient,
        settings: ProvisioningSettings,
        registry: NodeRegistry | None = None,
        connection_tracker: ConnectionTracker | None = None,
    ) -> None:
        self._ssh_client = ssh_client
        self._etcd_client = etcd_client
        self._settings = settings
        self._registry = registry
        self._tracker = connection_tracker
        self._provision_started_at: datetime | None = None
        self._background_tasks: set[asyncio.Task[None]] = set()

    async def list_tasks_raw(self) -> list[tuple[bytes, object]]:
        """Return raw provisioning task entries from etcd."""
        return await asyncio.to_thread(
            self._etcd_client.get_prefix, "/provisioning/"
        )

    async def _update_state(
        self,
        hostname: str,
        step: ProvisioningStep,
        *,
        failed_step: str | None = None,
        error: str | None = None,
    ) -> None:
        """Write provisioning state to etcd (D-05). Best-effort (Pitfall 3)."""
        now = datetime.now(timezone.utc)
        state = ProvisioningState(
            hostname=hostname,
            current_step=step,
            started_at=self._provision_started_at or now,
            updated_at=now,
            failed_step=failed_step,
            error=error,
        )
        key = f"/provisioning/{hostname}"
        value = json.dumps(state.model_dump(mode="json")).encode("utf-8")
        try:
            await asyncio.to_thread(self._etcd_client.put, key, value)
        except Exception:
            logger.warning("state_write_failed", hostname=hostname, step=step)

    async def _ssh_run_command(self, hostname: str, command: str) -> str:
        """Run a command via SSH and return collected stdout as a string."""
        lines: list[str] = []
        async for stream, line in self._ssh_client.run_streaming(hostname, command):
            if stream == "stdout":
                lines.append(line)
        return "\n".join(lines)

    async def preflight(self, hostname: str) -> None:
        """Pre-flight validation: TCP probe + SSH diagnostics (D-01, D-04).

        Stage 1: TCP probe to port 22.  If unreachable, raises immediately
        (cannot proceed to SSH diagnostics).

        Stage 2: GPU and disk checks via SSH.  All failures collected
        before raising a single PreflightError (D-03).
        """
        failures: list[str] = []

        # Stage 1: TCP probe (D-01)
        try:
            # ponytail: hardcoded 10s timeout matches SSHSettings default
            _reader, writer = await asyncio.wait_for(
                asyncio.open_connection(hostname, 22), timeout=10
            )
            writer.close()
            await writer.wait_closed()
        except (OSError, TimeoutError, asyncio.TimeoutError) as exc:
            failures.append(f"SSH port 22 unreachable: {exc}")
            raise PreflightError(hostname, failures) from exc

        # Stage 2: SSH diagnostics (D-01)
        # GPU check
        try:
            gpu_output = await self._ssh_run_command(
                hostname, "nvidia-smi --query-gpu=name --format=csv,noheader"
            )
            gpu_lines = [ln for ln in gpu_output.strip().splitlines() if ln.strip()]
            if len(gpu_lines) == 0:
                failures.append("No GPUs detected")
        except (SSHConnectionError, RemoteCommandError) as exc:
            failures.append(f"SSH diagnostic failed: {exc}")

        # Disk check
        try:
            disk_output = await self._ssh_run_command(
                hostname, "df --output=avail / | tail -1"
            )
            kb = int(disk_output.strip())
            gb = kb / 1024 / 1024
            if gb < self._settings.min_disk_gb:
                failures.append(
                    f"Insufficient disk: {gb:.1f}GB available, {self._settings.min_disk_gb}GB required"
                )
        except (SSHConnectionError, RemoteCommandError) as exc:
            failures.append(f"SSH diagnostic failed: {exc}")
        except (ValueError, IndexError) as exc:
            failures.append(f"SSH diagnostic failed: could not parse disk output: {exc}")

        if failures:
            raise PreflightError(hostname, failures)

    async def provision(self, hostname: str, *, managed: bool = True) -> None:
        """Run full provisioning sequence on *hostname*.

        Sequence: preflight -> register PROVISIONING -> setup.sh ->
        start-vllm.sh -> health poll -> register HEALTHY.
        Tracks state in etcd at each step (D-05 through D-11).
        """
        self._provision_started_at = datetime.now(timezone.utc)
        logger.info("provisioning_start", hostname=hostname)

        await self._update_state(hostname, ProvisioningStep.PENDING)
        await self._update_state(hostname, ProvisioningStep.PREFLIGHT)

        # D-04: preflight before any setup work
        try:
            await self.preflight(hostname)
        except PreflightError:
            await self._update_state(
                hostname, ProvisioningStep.FAILED,
                failed_step="preflight", error="pre-flight validation failed",
            )
            raise

        # D-09: Register node as PROVISIONING before setup
        node = Node(
            node_id=hostname,
            endpoint=f"{hostname}:{self._settings.vllm_port}",
            status=NodeStatus.PROVISIONING,
            model="",
            last_heartbeat=datetime.now(timezone.utc),
            managed=managed,
        )
        key, value = node_to_etcd(node, self._etcd_client.prefix)
        try:
            await asyncio.to_thread(self._etcd_client.put, key, value)
        except Exception:
            logger.warning("provisioning_registration_failed", hostname=hostname)

        try:
            await self._update_state(hostname, ProvisioningStep.UPLOADING_SCRIPTS)
            await self._upload_scripts(hostname)
            await self._run_setup(hostname)
            await self._update_state(hostname, ProvisioningStep.STARTING_VLLM)
            model = await self._run_start_vllm(hostname)
            await self._update_state(hostname, ProvisioningStep.HEALTH_POLL)
            await self._poll_health(hostname)
            await self._update_state(hostname, ProvisioningStep.REGISTERING)
            await self._register_node(hostname, model, managed=managed)
            await self._update_state(hostname, ProvisioningStep.COMPLETE)
        except (RemoteCommandError, SSHConnectionError, ProvisioningError) as exc:
            await self._update_state(
                hostname, ProvisioningStep.FAILED,
                failed_step=type(exc).__name__, error=str(exc),
            )
            raise ProvisioningError(str(exc)) from exc

        logger.info("provisioning_complete", hostname=hostname)

    async def _upload_scripts(self, hostname: str) -> None:
        """Copy provisioning scripts to the remote host via SCP."""
        await self._ssh_client.upload(hostname, self._settings.scripts_dir)

    async def _run_setup(self, hostname: str) -> None:
        """Run setup.sh and parse step markers from stdout (D-05, D-06)."""
        async for stream, line in self._ssh_client.run_streaming(
            hostname, "bash auto-vllm-container/setup.sh"
        ):
            if stream == "stdout":
                match = STEP_PATTERN.search(line)
                if match:
                    step_name, status = match.group(1), match.group(2)
                    if status == "START":
                        # D-06: step_name matches ProvisioningStep member names
                        try:
                            await self._update_state(hostname, ProvisioningStep(step_name))
                        except ValueError:
                            pass  # Unknown step name, skip state update
                    if status == "FAIL":
                        logger.error("step_failed", step=step_name, hostname=hostname)
                    else:
                        logger.info("step_marker", step=step_name, status=status, hostname=hostname)
                else:
                    logger.debug("setup_stdout", line=line, hostname=hostname)
            else:  # stderr
                logger.warning("setup_stderr", line=line, hostname=hostname)

    async def _run_start_vllm(self, hostname: str) -> str:
        """Run start-vllm.sh and extract model name from stdout."""
        model: str | None = None
        async for stream, line in self._ssh_client.run_streaming(
            hostname, "bash auto-vllm-container/start-vllm.sh"
        ):
            logger.debug("start_vllm_output", stream=stream, line=line, hostname=hostname)
            if stream == "stdout":
                match = MODEL_PATTERN.search(line)
                if match:
                    model = match.group(1).strip()

        if model is None:
            raise ProvisioningError(
                f"model name not found in start-vllm.sh output on {hostname}"
            )
        return model

    async def _poll_health(self, hostname: str) -> None:
        """Poll /health endpoint until 200 OK or timeout (D-10, D-09)."""
        url = f"http://{hostname}:{self._settings.vllm_port}/health"
        deadline = asyncio.get_running_loop().time() + self._settings.health_poll_timeout

        async with httpx.AsyncClient() as client:
            while True:
                try:
                    response = await client.get(url)
                    if response.status_code == 200:
                        logger.info("health_poll_success", hostname=hostname)
                        return
                    logger.debug("health_poll_non_200", status=response.status_code, hostname=hostname)
                except httpx.HTTPError as exc:
                    logger.debug("health_poll_retry", hostname=hostname, error=str(exc))

                if asyncio.get_running_loop().time() >= deadline:
                    raise ProvisioningError(
                        f"health poll timed out after {self._settings.health_poll_timeout}s for {hostname}"
                    )
                await asyncio.sleep(self._settings.health_poll_interval)

    async def _register_node(self, hostname: str, model: str, *, managed: bool = True) -> None:
        """Register node in etcd with correct fields (D-11, D-12)."""
        node = Node(
            node_id=hostname,
            endpoint=f"{hostname}:{self._settings.vllm_port}",
            status=NodeStatus.HEALTHY,
            model=model,
            last_heartbeat=datetime.now(timezone.utc),
            managed=managed,
        )
        key, value = node_to_etcd(node, self._etcd_client.prefix)
        # ponytail: etcd3gw is sync, asyncio.to_thread wraps it (Pitfall 5)
        await asyncio.to_thread(self._etcd_client.put, key, value)
        logger.info("node_registered", hostname=hostname, model=model, key=key)

    def fire_background(self, coro: Coroutine[object, object, None]) -> asyncio.Task[None]:
        """Schedule a coroutine as a background task, preventing GC."""
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task

    async def _drain_wait(self, hostname: str) -> None:
        """Wait for active connections to reach zero or timeout (D-08, D-09)."""
        if self._tracker is None:
            logger.warning("drain_skip_no_tracker", hostname=hostname)
            return
        deadline = asyncio.get_running_loop().time() + self._settings.drain_timeout
        while True:
            if self._tracker.get(hostname) == 0:
                return
            if asyncio.get_running_loop().time() >= deadline:
                logger.warning("drain_timeout_expired", hostname=hostname)
                return
            await asyncio.sleep(1)

    async def teardown(self, hostname: str, *, force: bool = False) -> None:
        """Teardown a provisioned node (D-01, D-03).

        Graceful: drain -> stop -> rm -> deregister.
        Force: rm --force -> deregister.
        """
        self._provision_started_at = datetime.now(timezone.utc)
        logger.info("teardown_start", hostname=hostname, force=force)

        # Derive container name from registry model, fallback to hostname
        container_name = f"vllm-{hostname}"
        if self._registry is not None:
            node = self._registry.get(hostname)
            if node and node.model:
                container_name = _derive_container_name(node.model)
            else:
                logger.warning("teardown_model_unknown", hostname=hostname)

        try:
            if not force:
                await self._update_state(hostname, ProvisioningStep.DRAINING)
                if self._registry is not None:
                    self._registry.drain(hostname)
                await self._drain_wait(hostname)

            await self._update_state(hostname, ProvisioningStep.STOPPING_CONTAINER)
            if force:
                await self._ssh_run_command(hostname, f"podman rm --force {container_name}")
            else:
                await self._ssh_run_command(
                    hostname, f"podman stop {container_name} && podman rm {container_name}"
                )

            await self._update_state(hostname, ProvisioningStep.DEREGISTERING)
            await asyncio.to_thread(
                self._etcd_client.delete, f"{self._etcd_client.prefix}{hostname}"
            )

            await self._update_state(hostname, ProvisioningStep.TEARDOWN_COMPLETE)
        except (RemoteCommandError, SSHConnectionError) as exc:
            await self._update_state(
                hostname, ProvisioningStep.FAILED,
                failed_step="teardown", error=str(exc),
            )
            raise ProvisioningError(str(exc)) from exc

        logger.info("teardown_complete", hostname=hostname)
