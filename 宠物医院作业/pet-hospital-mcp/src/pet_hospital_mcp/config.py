"""Runtime configuration, read from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    """Service configuration.

    Environment variables:

    - ``PET_HOSPITAL_BASE_URL``: upstream Go REST API base URL (no trailing slash).
    - ``MCP_HOST`` / ``MCP_PORT``: bind address of this MCP service.
    - ``REQUEST_TIMEOUT_SECONDS``: per-attempt upstream HTTP timeout.
    - ``REQUEST_MAX_ATTEMPTS``: total attempts per upstream call (1 = no retry).
    - ``REQUEST_RETRY_BACKOFF_SECONDS``: linear backoff base between attempts.
    - ``LOG_LEVEL``: logging level (DEBUG/INFO/WARNING/ERROR).
    """

    pet_hospital_base_url: str = "http://127.0.0.1:8080"
    mcp_host: str = "127.0.0.1"
    mcp_port: int = 8000
    mcp_path: str = "/mcp"
    request_timeout_seconds: float = 10.0
    request_max_attempts: int = 3
    request_retry_backoff_seconds: float = 0.1
    log_level: str = "INFO"

    @classmethod
    def from_env(cls, environ: os._Environ | None = None) -> Config:
        env = os.environ if environ is None else environ
        return cls(
            pet_hospital_base_url=env.get("PET_HOSPITAL_BASE_URL", "http://127.0.0.1:8080").rstrip("/"),
            mcp_host=env.get("MCP_HOST", "127.0.0.1"),
            mcp_port=int(env.get("MCP_PORT", "8000")),
            request_timeout_seconds=float(env.get("REQUEST_TIMEOUT_SECONDS", "10.0")),
            request_max_attempts=int(env.get("REQUEST_MAX_ATTEMPTS", "3")),
            request_retry_backoff_seconds=float(env.get("REQUEST_RETRY_BACKOFF_SECONDS", "0.1")),
            log_level=env.get("LOG_LEVEL", "INFO"),
        )
