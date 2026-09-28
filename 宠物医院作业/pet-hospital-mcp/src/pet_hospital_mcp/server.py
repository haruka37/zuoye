"""MCPServer assembly: SDK 2.x MCPServer + stateless Streamable HTTP app.

- Official Python SDK ``mcp==2.0.0``, protocol version 2026-07-28.
- Stateless Streamable HTTP: every request is a single POST with the
  ``mcp-protocol-version: 2026-07-28`` header and the per-request ``_meta``
  envelope. No ``initialize``, no ``Mcp-Session-Id``, no sessions, no SSE
  resume — nothing of the 1.x stateful machinery is implemented here.
- Discovery uses the 2026-07-28 ``server/discover`` method.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from mcp.server import MCPServer
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse

from . import __version__
from .config import Config
from .rest_client import PetHospitalClient
from .tools import build_list_pets_tool

logger = logging.getLogger("pet_hospital_mcp.server")

PROTOCOL_VERSION = "2026-07-28"


def build_server(cfg: Config, client: PetHospitalClient | None = None) -> MCPServer:
    """Create the MCPServer with the phase-1 tool set (``list_pets`` only)."""
    client = client or PetHospitalClient(
        cfg.pet_hospital_base_url,
        timeout=cfg.request_timeout_seconds,
        max_attempts=cfg.request_max_attempts,
        retry_backoff=cfg.request_retry_backoff_seconds,
    )

    @asynccontextmanager
    async def _lifespan(server: MCPServer[Any]) -> Any:
        try:
            yield
        finally:
            await client.close()

    server = MCPServer(
        name="pet-hospital-mcp",
        title="Pet Hospital MCP Service",
        version=__version__,
        description=(
            "宠物医院 MCP 适配服务：将本地 Go 宠物医院 REST API 的能力"
            f"暴露给 AI Agent（SDK mcp 2.0.0，协议 {PROTOCOL_VERSION}，无状态 Streamable HTTP）。"
        ),
        tools=[build_list_pets_tool(client)],
        lifespan=_lifespan,
    )

    @server.custom_route("/health", methods=["GET"])
    async def health(request: Request) -> JSONResponse:
        return JSONResponse(
            {"status": "ok", "upstream": cfg.pet_hospital_base_url, "protocol": PROTOCOL_VERSION}
        )

    logger.info(
        "MCPServer built",
        extra={"tool_count": 1, "upstream": cfg.pet_hospital_base_url, "protocol": PROTOCOL_VERSION},
    )
    return server


def create_app(cfg: Config, client: PetHospitalClient | None = None) -> Starlette:
    """Build the ASGI app: MCP endpoint + ``/health``.

    ``stateless_http=True`` keeps every exchange request-scoped; ``json_response=True``
    makes the MCP endpoint answer with plain ``application/json`` (no SSE needed
    for this query-only tool set).
    """
    server = build_server(cfg, client)
    return server.streamable_http_app(
        streamable_http_path=cfg.mcp_path,
        stateless_http=True,
        json_response=True,
        host=cfg.mcp_host,
    )


__all__ = ["PROTOCOL_VERSION", "build_server", "create_app"]
