"""Strict input validation: bad enums, ranges, NaN/Infinity, wrong types and
unknown fields all produce the unified VALIDATION_ERROR structure."""

from __future__ import annotations

import pytest

from pet_hospital_mcp.errors import ErrorCode
from pet_hospital_mcp.tools.list_pets import _RawArguments, build_list_pets_tool

from conftest import make_client, ok_handler

INVALID_CASES = [
    # enums
    {"species": "恐龙"},
    {"status": "已出院"},
    {"sortBy": "unknownField"},
    {"order": "up"},
    # page bounds / type
    {"page": 0},
    {"page": -3},
    {"page": 2.5},
    {"page": "2"},
    {"page": True},
    # pageSize bounds / type
    {"pageSize": 0},
    {"pageSize": 501},
    {"pageSize": 10.5},
    {"pageSize": "10"},
    # min/max: negative, NaN, Infinity, type
    {"min": -1},
    {"max": -0.01},
    {"min": float("inf")},
    {"max": float("nan")},
    {"min": "100"},
    # cross-field
    {"min": 500, "max": 100},
    # unknown fields / wrong types for strings
    {"unknownField": 1},
    {"name": 123},
    {"q": ["x", "y"]},
]


@pytest.fixture
async def tool():
    yield build_list_pets_tool(make_client(ok_handler))


@pytest.mark.parametrize("arguments", INVALID_CASES)
async def test_invalid_input_rejected(arguments, tool):
    result = await tool.fn(**arguments)
    assert result.is_error is True
    payload = result.structured_content
    assert set(payload.keys()) == {"error"}
    assert payload["error"]["code"] == ErrorCode.VALIDATION_ERROR.value
    assert payload["error"]["message"]
    assert payload["error"]["details"]["errors"], "details.errors must list the violations"


async def test_valid_inputs_accepted(tool):
    for arguments in (
        {},
        {"species": "犬", "status": "待就诊", "sortBy": "totalCost", "order": "desc"},
        {"min": 0, "max": 0},
        {"min": 100, "max": 5000},
        {"page": 1, "pageSize": 500},
    ):
        result = await tool.fn(**arguments)
        assert result.is_error is False, f"should accept {arguments}"


def test_raw_arguments_passthrough_keeps_unknown_fields_for_validation():
    raw = {"species": "犬", "page": 2, "totallyUnknown": 1}
    assert _RawArguments.model_validate(raw).model_dump_one_level() == raw
