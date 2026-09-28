"""Normal path: all 13 query params are forwarded to GET /api/v1/pets
and the success output maps to the Go response's ``data``."""

from __future__ import annotations

import json

import httpx
import pytest

from pet_hospital_mcp.tools.list_pets import build_list_pets_tool

from conftest import make_client, make_list_data


def _capturing_handler(calls: list, data: dict | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            json={"code": 200, "message": "ok", "data": data if data is not None else make_list_data(), "time": "t"},
        )

    return handler


async def test_all_params_forwarded(test_config):
    calls: list[httpx.Request] = []
    tool = build_list_pets_tool(make_client(_capturing_handler(calls)))
    arguments = {
        "q": "肠胃炎",
        "name": "旺财",
        "ownerName": "张三",
        "ownerPhone": "13800001111",
        "species": "犬",
        "doctor": "李医生",
        "disease": "骨折",
        "status": "住院中",
        "min": 100,
        "max": 5000,
        "sortBy": "totalCost",
        "order": "desc",
        "page": 2,
        "pageSize": 10,
    }
    result = await tool.fn(**arguments)

    assert result.is_error is False
    request = calls[0]
    assert request.method == "GET"
    assert request.url.path == "/api/v1/pets"
    assert dict(request.url.params) == {
        "q": "肠胃炎",
        "name": "旺财",
        "ownerName": "张三",
        "ownerPhone": "13800001111",
        "species": "犬",
        "doctor": "李医生",
        "disease": "骨折",
        "status": "住院中",
        "min": "100",
        "max": "5000",
        "sortBy": "totalCost",
        "order": "desc",
        "page": "2",
        "pageSize": "10",
    }


async def test_no_optional_params_forwards_nothing(test_config):
    calls: list[httpx.Request] = []
    tool = build_list_pets_tool(make_client(_capturing_handler(calls)))
    result = await tool.fn()
    assert result.is_error is False
    assert dict(calls[0].url.params) == {}


async def test_success_output_matches_backend_data(test_config):
    data = make_list_data(
        items=[
            {
                "id": "PET-000002",
                "name": "陈皮",
                "species": "猫",
                "records": [{"id": "MR-1", "visitDate": "2026-01-01", "diagnosis": "感冒"}],
                "charges": [{"id": "CH-1", "item": "检查", "amount": 180.5, "date": "2026-01-01"}],
                "totalCost": 180.5,
                "visitCount": 1,
            }
        ],
        total=308,
        page=3,
        pageSize=50,
        totalPages=7,
        totalCost=12345.6,
    )
    tool = build_list_pets_tool(make_client(_capturing_handler([], data)))
    result = await tool.fn(species="猫", page=3)

    assert result.is_error is False
    structured = result.structured_content
    assert structured["items"][0]["id"] == "PET-000002"
    assert structured["items"][0]["records"][0]["id"] == "MR-1"  # array form
    assert structured["items"][0]["charges"][0]["amount"] == 180.5  # array form
    assert structured["total"] == 308
    assert structured["page"] == 3
    assert structured["pageSize"] == 50
    assert structured["totalPages"] == 7
    assert structured["totalCost"] == 12345.6
    # text content carries the same payload for the LLM
    assert json.loads(result.content[0].text)["total"] == 308


async def test_records_and_charges_may_be_null(test_config):
    calls: list[httpx.Request] = []
    tool = build_list_pets_tool(make_client(_capturing_handler(calls)))
    result = await tool.fn(pageSize=1)
    assert result.is_error is False
    item = result.structured_content["items"][0]
    assert item["records"] is None
    assert item["charges"] is None


def test_sensitive_fields_are_redacted_recursively():
    from pet_hospital_mcp.logging_config import redact

    raw = {"ownerPhone": "13800001111", "ownerAddr": "地址", "chipNo": "CHIP-1", "name": "旺财"}
    assert redact(raw) == {"ownerPhone": "***", "ownerAddr": "***", "chipNo": "***", "name": "旺财"}
    nested = {"items": [{"owner_phone": "x"}]}
    assert redact(nested) == {"items": [{"owner_phone": "***"}]}
