"""LLMFit remote execution via SSH.

Runs ``llmfit recommend --json --force-runtime vllm`` on a remote host
and returns a typed ``LLMFitResult``.  SSH transport is injected via
constructor (DIP).
"""

from __future__ import annotations

import asyncio
import json

import structlog
from pydantic import ValidationError

from inference_proxy.llmfit.errors import LLMFitParseError, LLMFitTimeoutError
from inference_proxy.models.llmfit import LLMFitResult
from inference_proxy.provisioning.ssh_client import SSHClient

logger = structlog.get_logger()


class LLMFitRunner:
    """Run llmfit on a remote host and parse the result.

    Constructor-injected ``SSHClient`` keeps this testable without SSH.
    """

    # ponytail: hardcoded per D-05/D-06, Phase 27 adds LLMFitSettings
    _BINARY = "/usr/local/bin/llmfit"
    _COMMAND = f"{_BINARY} recommend --json --force-runtime vllm"
    _TIMEOUT = 60.0

    def __init__(self, ssh_client: SSHClient) -> None:
        self._ssh = ssh_client

    async def recommend(self, hostname: str) -> LLMFitResult:
        """Run llmfit on *hostname* and return parsed recommendations.

        Raises:
            LLMFitTimeoutError: When execution exceeds ``_TIMEOUT``.
            LLMFitParseError: When stdout is empty, not valid JSON,
                or fails Pydantic validation.  Stores raw stdout.
            SSHConnectionError: Bubbles unchanged from SSHClient (D-03).
            RemoteCommandError: Bubbles unchanged from SSHClient (D-03).
        """
        log = logger.bind(host=hostname)
        log.debug("llmfit_recommend_start")

        try:
            stdout, _stderr, _exit = await self._ssh.run(
                hostname, self._COMMAND, timeout=self._TIMEOUT,
            )
        except asyncio.TimeoutError:
            raise LLMFitTimeoutError(hostname, self._TIMEOUT)

        if not stdout.strip():
            raise LLMFitParseError("empty output", raw_output=stdout)

        try:
            data = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise LLMFitParseError(str(exc), raw_output=stdout) from exc

        try:
            result = LLMFitResult.model_validate(data)
        except ValidationError as exc:
            raise LLMFitParseError(str(exc), raw_output=stdout) from exc

        log.debug("llmfit_recommend_complete", model_count=len(result.models))
        return result
