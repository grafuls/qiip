"""LLMFit domain error hierarchy.

Base ``LLMFitError`` with typed subclasses for timeout and parse
failures.  SSH-level errors (``SSHConnectionError``,
``RemoteCommandError``) bubble through unchanged per D-03.
"""

from __future__ import annotations


class LLMFitError(Exception):
    """Base error for llmfit operations."""


class LLMFitTimeoutError(LLMFitError):
    """Raised when llmfit execution exceeds the timeout (D-02, T-25-03)."""

    def __init__(self, host: str, timeout: float) -> None:
        self.host = host
        self.timeout = timeout
        super().__init__(f"llmfit timed out after {timeout}s on {host}")


class LLMFitParseError(LLMFitError):
    """Raised when llmfit stdout cannot be parsed as valid JSON (D-04)."""

    def __init__(self, reason: str, raw_output: str) -> None:
        self.reason = reason
        self.raw_output = raw_output
        super().__init__(f"Failed to parse llmfit output: {reason}")
