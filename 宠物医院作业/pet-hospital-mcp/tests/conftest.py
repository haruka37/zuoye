"""Shared fixtures. All tests use httpx.MockTransport — the real Go service
is never contacted."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, Callable

import httpx
import pytest

from pet_hospital_mcp.config import Config
from pet_hospital_mcp.rest_client import PetHospitalClient
from pet_hospital_mcp.server import create_app

PROTOCOL_VERSION = "2026-07-28"

# Per-request _meta envelope required by the 2026-07-28 stateless flow.
META = {
    "io.modelcontextprotocol/protocolVersion": PROTOCOL_VERSION,
    "io.modelcontextprotocol/clientCapabilities": {},
}

MODERN_HEADERS = {
    "mcp-protocol-version": PROTOCOL_VERSION,
    "content-type": "application/json",
    "accept": "application/json",
}


def modern_headers(method: str, name: str | None = None) -> dict[str, str]:
    """2026-07-28 routing headers: the ladder requires ``mcp-method`` to match
    the body method, and ``mcp-name`` for name-bearing methods (tools/call)."""
    headers = {"mcp-method": method, **MODERN_HEADERS}
    if name is not None:
        headers["mcp-name"] = name
    return headers


def envelope(**params: Any) -> dict[str, Any]:
    return {"_meta": dict(META), **params}


def rpc(method: str, params: dict[str, Any], rid: int = 1) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": rid, "method": method, "params": params}


def make_list_data(**overrides: Any) -> dict[str, Any]:
    """A valid Go ``GET /api/v1/pets`` ``data`` payload (records/charges null)."""
    data: dict[str, Any] = {
        "items": [
            {
                "id": "PET-000001",
                "name": "旺财",
                "species": "犬",
                "breed": "金毛",
                "gender": "公",
                "ageMonths": 36,
                "color": "金色",
                "chipNo": None,
                "ownerName": "张三",
                "ownerPhone": "13800001111",
                "ownerAddr": "北京市朝阳区幸福路1号",
                "doctor": "李医生",
                "disease": "急性肠胃炎",
                "status": "待就诊",
                "allergy": "无",
                "records": None,
                "charges": None,
                "totalCost": 0,
                "visitCount": 0,
                "createdAt": "2026-09-01T09:00:00+08:00",
                "updatedAt": "2026-09-01T09:00:00+08:00",
            }
        ],
        "total": 1,
        "page": 1,
        "pageSize": 20,
        "totalPages": 1,
        "totalCost": 0,
    }
    data.update(overrides)
    return data


def ok_handler(request: httpx.Request) -> httpx.Response:
    """Default backend stub: 200 with a valid list envelope."""
    return httpx.Response(200, json={"code": 200, "message": "ok", "data": make_list_data(), "time": "2026-09-17T00:00:00+08:00"})


@pytest.fixture
def test_config() -> Config:
    return Config(
        pet_hospital_base_url="http://upstream.test",
        request_timeout_seconds=1.0,
        request_max_attempts=3,
        request_retry_backoff_seconds=0.0,
    )


def make_client(handler: Callable[[httpx.Request], httpx.Response]) -> PetHospitalClient:
    return PetHospitalClient(
        "http://upstream.test",
        timeout=1.0,
        max_attempts=3,
        retry_backoff=0.0,
        transport=httpx.MockTransport(handler),
    )


@pytest.fixture
def mcp_http(test_config: Config):
    """Factory: run the full ASGI app (lifespan included) against a stub backend."""

    @asynccontextmanager
    async def _factory(handler: Callable[[httpx.Request], httpx.Response]):
        client = make_client(handler)
        app = create_app(test_config, client)
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as ac:
                yield ac

    return _factory
