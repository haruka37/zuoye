"""Async HTTP client for the Go pet hospital REST API.

The Go service is the only business backend; this module is the single place
that talks to it. It returns the parsed ``data`` payload of the Go envelope
(``{"code", "message", "data", "time"}``); tool-specific output models are
validated by the tools themselves.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from .errors import AppError, ErrorCode

logger = logging.getLogger("pet_hospital_mcp.rest_client")

RETRYABLE_STATUS = frozenset({502, 503, 504})


class BackendEnvelope(BaseModel):
    """The Go API's uniform response envelope (unknown fields ignored)."""

    model_config = ConfigDict(extra="ignore")

    code: int
    message: str
    data: Any = None
    time: str | None = None


class PetHospitalClient:
    """Thin async client over ``GET /api/v1/pets`` with timeout and limited retries.

    Retries are only attempted for transient failures: timeouts, connection
    errors and HTTP 502/503/504. Deterministic failures (4xx, malformed
    responses) surface immediately.
    """

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 10.0,
        max_attempts: int = 3,
        retry_backoff: float = 0.1,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url
        self._max_attempts = max(1, max_attempts)
        self._retry_backoff = retry_backoff
        # trust_env=False: keep localhost traffic off proxies.
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(timeout),
            transport=transport,
            trust_env=False,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def list_pets(self, params: dict[str, Any]) -> dict[str, Any]:
        """GET /api/v1/pets and return the parsed ``data`` payload.

        Raises:
            AppError: BACKEND_TIMEOUT / BACKEND_UNAVAILABLE / BACKEND_API_ERROR /
                BACKEND_INVALID_RESPONSE, depending on the failure.
        """
        last_error: AppError | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                response = await self._client.get("/api/v1/pets", params=params)
            except httpx.TimeoutException as exc:
                last_error = AppError(
                    ErrorCode.BACKEND_TIMEOUT,
                    "上游宠物医院服务响应超时，请稍后重试",
                    {"attempt": attempt, "timeout_seconds": self._client.timeout.read},
                )
                logger.warning("upstream timeout", extra={"attempt": attempt})
            except httpx.TransportError as exc:
                last_error = AppError(
                    ErrorCode.BACKEND_UNAVAILABLE,
                    f"无法连接上游宠物医院服务 {self._base_url}，请确认 Go 服务已启动",
                    {"attempt": attempt},
                )
                logger.warning("upstream unavailable", extra={"attempt": attempt, "error": str(exc)})
            else:
                if response.status_code in RETRYABLE_STATUS:
                    last_error = AppError(
                        ErrorCode.BACKEND_API_ERROR,
                        f"上游宠物医院服务暂时不可用（HTTP {response.status_code}）",
                        {"attempt": attempt, "http_status": response.status_code},
                    )
                    logger.warning("upstream retryable status", extra={"attempt": attempt, "status": response.status_code})
                elif response.status_code == 200:
                    try:
                        envelope = BackendEnvelope.model_validate(response.json())
                    except (ValueError, ValidationError):
                        raise AppError(
                            ErrorCode.BACKEND_INVALID_RESPONSE,
                            "上游响应不是合法 JSON 信封",
                            {},
                        ) from None
                    if envelope.code != 200:
                        raise AppError(
                            ErrorCode.BACKEND_API_ERROR,
                            f"上游 API 返回错误（HTTP 200, code={envelope.code}）: {envelope.message}",
                            {"backend_code": envelope.code},
                        )
                    if not isinstance(envelope.data, dict):
                        raise AppError(
                            ErrorCode.BACKEND_INVALID_RESPONSE,
                            "上游成功响应的 data 不是对象",
                            {},
                        )
                    return envelope.data
                else:
                    message = self._extract_backend_message(response)
                    raise AppError(
                        ErrorCode.BACKEND_API_ERROR,
                        f"上游 API 返回错误（HTTP {response.status_code}）: {message}",
                        {"http_status": response.status_code},
                    )
            if attempt < self._max_attempts:
                await asyncio.sleep(self._retry_backoff * attempt)
        assert last_error is not None
        raise last_error

    @staticmethod
    def _extract_backend_message(response: httpx.Response) -> str:
        """Best-effort readable message from the Go envelope, never raw bodies."""
        try:
            return BackendEnvelope.model_validate(response.json()).message
        except (ValueError, ValidationError):
            return "上游服务返回错误"
