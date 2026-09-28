"""Tool registration: exactly one snake_case tool ``list_pets`` whose JSON
Schema mirrors the real backend allowed values."""

from __future__ import annotations

import pytest

from pet_hospital_mcp.server import build_server
from pet_hospital_mcp.tools.list_pets import (
    ORDERS,
    SORT_FIELDS,
    SPECIES,
    STATUSES,
    ListPetsInput,
)

from conftest import make_client, ok_handler

EXPECTED_PARAMS = {
    "q", "name", "ownerName", "ownerPhone", "species", "doctor", "disease",
    "status", "min", "max", "sortBy", "order", "page", "pageSize",
}


@pytest.fixture
def client():
    return make_client(ok_handler)


async def test_exactly_one_tool_named_list_pets(test_config, client):
    server = build_server(test_config, client)
    tools = await server.list_tools()
    assert [t.name for t in tools] == ["list_pets"]
    tool = tools[0]
    assert tool.name == "list_pets"  # snake_case


async def test_input_schema_matches_backend_params(test_config, client):
    server = build_server(test_config, client)
    schema = (await server.list_tools())[0].input_schema
    assert schema["type"] == "object"
    assert set(schema["properties"]) == EXPECTED_PARAMS
    assert schema["additionalProperties"] is False  # unknown fields rejected
    # all params optional: omitted params are simply not forwarded
    assert not schema.get("required")


def _non_null_arm(schema: dict) -> dict:
    """Optional fields serialize as anyOf [<type schema>, {type: null}]."""
    if "anyOf" in schema:
        return next(arm for arm in schema["anyOf"] if arm.get("type") != "null")
    return schema


async def test_input_schema_uses_real_backend_enum_values(test_config, client):
    server = build_server(test_config, client)
    schema = (await server.list_tools())[0].input_schema
    props = schema["properties"]
    assert _non_null_arm(props["species"])["enum"] == list(SPECIES)
    assert _non_null_arm(props["status"])["enum"] == list(STATUSES)
    assert _non_null_arm(props["sortBy"])["enum"] == list(SORT_FIELDS)
    assert _non_null_arm(props["order"])["enum"] == list(ORDERS)
    assert _non_null_arm(props["page"])["minimum"] == 1
    assert _non_null_arm(props["pageSize"])["minimum"] == 1
    assert _non_null_arm(props["pageSize"])["maximum"] == 500
    assert _non_null_arm(props["min"])["minimum"] == 0
    assert _non_null_arm(props["max"])["minimum"] == 0


async def test_tool_description_covers_purpose_params_scenarios_and_return(test_config, client):
    server = build_server(test_config, client)
    description = (await server.list_tools())[0].description
    assert "用途" in description
    assert "参数" in description
    assert "适用场景" in description
    assert "返回值" in description
    for param in ("pageSize", "sortBy", "ownerPhone", "species", "status"):
        assert param in description


def test_input_model_rejects_unknown_fields_at_model_level():
    # extra="forbid" is the mechanism behind additionalProperties: false
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ListPetsInput.model_validate({"notAParam": 1})
