"""Backend failure mapping: 4xx/5xx, timeout, connection errors, malformed or
model-invalid responses, and the limited-retry behavior."""

from __future__ import annotations

import httpx
import pytest

from pet_hospital_mcp.errors import ErrorCode
from pet_hospital_mcp.tools.list_pets import build_list_pets_tool

from conftest import make_client, make_list_data


def _tool_with(handler):
    return build_list_pets_tool(make_client(handler))


async def test_backend_4xx_maps_to_backend_api_error():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            400,
            json={"code": 400, "message": "page 参数错误", "data": None, "time": "t"},
        )

    result = await _tool_with(handler).fn(page=1)
    assert result.is_error is True
    payload = result.structured_content["error"]
    assert payload["code"] == ErrorCode.BACKEND_API_ERROR.value
    assert payload["details"]["http_status"] == 400
    assert "page 参数错误" in payload["message"]
    assert len(calls) == 1  # 4xx is never retried


async def test_backend_5xx_maps_to_backend_api_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"code": 500, "message": "内部错误", "data": None, "time": "t"})

    result = await _tool_with(handler).fn()
    payload = result.structured_content["error"]
    assert payload["code"] == ErrorCode.BACKEND_API_ERROR.value
    assert payload["details"]["http_status"] == 500


async def test_retryable_503_then_success():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) < 3:
            return httpx.Response(503, json={"code": 503, "message": "busy", "data": None, "time": "t"})
        return httpx.Response(200, json={"code": 200, "message": "ok", "data": make_list_data(), "time": "t"})

    result = await _tool_with(handler).fn()
    assert result.is_error is False
    assert len(calls) == 3  # 2 retries, then success


async def test_timeout_maps_to_backend_timeout_with_retries():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise httpx.ReadTimeout("timed out", request=request)

    result = await _tool_with(handler).fn()
    payload = result.structured_content["error"]
    assert payload["code"] == ErrorCode.BACKEND_TIMEOUT.value
    assert len(calls) == 3  # max_attempts exhausted


async def test_connection_error_maps_to_backend_unavailable():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise httpx.ConnectError("connection refused", request=request)

    result = await _tool_with(handler).fn()
    payload = result.structured_content["error"]
    assert payload["code"] == ErrorCode.BACKEND_UNAVAILABLE.value
    assert len(calls) == 3


async def test_invalid_json_maps_to_backend_invalid_response_no_retry():
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, content=b"<html>not json</html>")

    result = await _tool_with(handler).fn()
    payload = result.structured_content["error"]
    assert payload["code"] == ErrorCode.BACKEND_INVALID_RESPONSE.value
    assert len(calls) == 1  # deterministic failure, not retried


async def test_non_200_envelope_code_maps_to_backend_api_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 500, "message": "db broken", "data": None, "time": "t"})

    result = await _tool_with(handler).fn()
    payload = result.structured_content["error"]
    assert payload["code"] == ErrorCode.BACKEND_API_ERROR.value
    assert payload["details"]["backend_code"] == 500


async def test_data_not_an_object_maps_to_backend_invalid_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 200, "message": "ok", "data": [1, 2], "time": "t"})

    result = await _tool_with(handler).fn()
    assert result.structured_content["error"]["code"] == ErrorCode.BACKEND_INVALID_RESPONSE.value


async def test_data_violating_output_model_maps_to_backend_invalid_response():
    broken = make_list_data()
    del broken["items"]  # envelope is fine, data model is not

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 200, "message": "ok", "data": broken, "time": "t"})

    result = await _tool_with(handler).fn()
    payload = result.structured_content["error"]
    assert payload["code"] == ErrorCode.BACKEND_INVALID_RESPONSE.value
