"""Node provisioning orchestrator.

Runs the full provisioning sequence on a remote host: setup.sh,
start-vllm.sh, health poll, etcd registration.

Per D-15: Concrete class, no protocol/interface.
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone

import httpx
import structlog

from inference_proxy.config.settings import ProvisioningSettings
from inference_proxy.discovery.etcd_client import EtcdClient
from inference_proxy.discovery.serializer import node_to_etcd
from inference_proxy.models.node import Node, NodeStatus
from inference_proxy.provisioning.ssh_client import (
    RemoteCommandError,
    SSHClient,
    SSHConnectionError,
)

logger = structlog.get_logger()

STEP_PATTERN = re.compile(r"\[STEP:(\w+):(START|OK|FAIL)\]")
MODEL_PATTERN = re.compile(r"#\s*Model:\s+(.+)")


class ProvisioningError(Exception):
    """Raised when any stage of provisioning fails."""


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
    ) -> None:
        self._ssh_client = ssh_client
        self._etcd_client = etcd_client
        self._settings = settings

    async def provision(self, hostname: str) -> None:
        """Run full provisioning sequence on *hostname*.

        Sequence: setup.sh -> start-vllm.sh -> health poll -> register.
        On failure, raises ProvisioningError with no cleanup (D-08).
        """
        logger.info("provisioning_start", hostname=hostname)
        try:
            await self._run_setup(hostname)
            model = await self._run_start_vllm(hostname)
            await self._poll_health(hostname)
            await self._register_node(hostname, model)
        except (RemoteCommandError, SSHConnectionError) as exc:
            raise ProvisioningError(str(exc)) from exc
        logger.info("provisioning_complete", hostname=hostname)

    async def _run_setup(self, hostname: str) -> None:
        """Run setup.sh and parse step markers from stdout (D-05, D-06)."""
        last_step: str | None = None
        async for stream, line in self._ssh_client.run_streaming(
            hostname, "bash auto-vllm-container/setup.sh"
        ):
            if stream == "stdout":
                match = STEP_PATTERN.search(line)
                if match:
                    step_name, status = match.group(1), match.group(2)
                    last_step = step_name
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
        deadline = asyncio.get_event_loop().time() + self._settings.health_poll_timeout

        async with httpx.AsyncClient() as client:
            while True:
                try:
                    response = await client.get(url)
                    if response.status_code == 200:
                        logger.info("health_poll_success", hostname=hostname)
                        return
                    logger.debug("health_poll_non_200", status=response.status_code, hostname=hostname)
                except (httpx.ConnectError, httpx.TimeoutException) as exc:
                    logger.debug("health_poll_retry", hostname=hostname, error=str(exc))

                if asyncio.get_event_loop().time() >= deadline:
                    raise ProvisioningError(
                        f"health poll timed out after {self._settings.health_poll_timeout}s for {hostname}"
                    )
                await asyncio.sleep(self._settings.health_poll_interval)

    async def _register_node(self, hostname: str, model: str) -> None:
        """Register node in etcd with correct fields (D-11, D-12)."""
        node = Node(
            node_id=hostname,
            endpoint=f"{hostname}:{self._settings.vllm_port}",
            status=NodeStatus.HEALTHY,
            model=model,
            last_heartbeat=datetime.now(timezone.utc),
        )
        key, value = node_to_etcd(node, self._etcd_client.prefix)
        # ponytail: etcd3gw is sync, asyncio.to_thread wraps it (Pitfall 5)
        await asyncio.to_thread(self._etcd_client.put, key, value)
        logger.info("node_registered", hostname=hostname, model=model, key=key)
