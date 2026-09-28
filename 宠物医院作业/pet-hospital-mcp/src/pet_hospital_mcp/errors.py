"""Unified structured error model shared by every tool.

Wire shape (always):

.. code-block:: json

    {"error": {"code": "ERROR_CODE", "message": "human readable", "details": {}}}
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ErrorCode(str, Enum):
    """Error codes surfaced to MCP clients. Never leak SDK/Python internals."""

    VALIDATION_ERROR = "VALIDATION_ERROR"
    BACKEND_TIMEOUT = "BACKEND_TIMEOUT"
    BACKEND_UNAVAILABLE = "BACKEND_UNAVAILABLE"
    BACKEND_API_ERROR = "BACKEND_API_ERROR"
    BACKEND_INVALID_RESPONSE = "BACKEND_INVALID_RESPONSE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class AppError(Exception):
    """Business-level error carrying a machine-readable code."""

    def __init__(self, code: ErrorCode, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class ErrorPayload(BaseModel):
    """Pydantic model for the ``error`` object of the unified structure."""

    code: ErrorCode
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class UnifiedError(BaseModel):
    """Pydantic model for the unified structured error output."""

    error: ErrorPayload


def to_error_dict(code: ErrorCode, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    """Serialize a unified error to a plain dict (validated by the model)."""
    return UnifiedError(error=ErrorPayload(code=code, message=message, details=details or {})).model_dump(
        mode="json"
    )
