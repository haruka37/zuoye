"""SDK 2.x stateless Streamable HTTP flow (protocol 2026-07-28):

- no legacy ``initialize`` handshake (and it is rejected on the modern envelope);
- no ``Mcp-Session-Id`` anywhere;
- discovery via ``server/discover``, tool listing and invocation via HTTP;
- ``/health`` works.
"""

from __future__ import annotations

import httpx

from conftest import envelope, make_list_data, modern_headers, ok_handler, rpc


async def test_discover_works_without_initialize(mcp_http):
    async with mcp_http(ok_handler) as http:
        resp = await http.post(
            "/mcp", headers=modern_headers("server/discover"), json=rpc("server/discover", envelope())
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/json")
        assert "mcp-session-id" not in resp.headers
        body = resp.json()
        assert "result" in body and "error" not in body
        assert "2026-07-28" in body["result"]["supportedVersions"]


async def test_legacy_initialize_is_not_implemented(mcp_http):
    async with mcp_http(ok_handler) as http:
        resp = await http.post(
            "/mcp", headers=modern_headers("initialize"), json=rpc("initialize", envelope())
        )
        body = resp.json()
        assert "error" in body
        assert body["error"]["code"] == -32601  # METHOD_NOT_FOUND


async def test_tools_listable_over_http(mcp_http):
    async with mcp_http(ok_handler) as http:
        resp = await http.post(
            "/mcp", headers=modern_headers("tools/list"), json=rpc("tools/list", envelope())
        )
        assert resp.status_code == 200
        assert "mcp-session-id" not in resp.headers
        tools = resp.json()["result"]["tools"]
        assert [t["name"] for t in tools] == ["list_pets"]
        assert "pageSize" in tools[0]["inputSchema"]["properties"]


async def test_tool_callable_over_http(mcp_http):
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(dict(request.url.params))
        return httpx.Response(
            200, json={"code": 200, "message": "ok", "data": make_list_data(), "time": "t"}
        )

    async with mcp_http(handler) as http:
        resp = await http.post(
            "/mcp",
            headers=modern_headers("tools/call", name="list_pets"),
            json=rpc(
                "tools/call",
                envelope(name="list_pets", arguments={"species": "犬", "page": 1, "pageSize": 5}),
            ),
        )
        assert resp.status_code == 200
        assert "mcp-session-id" not in resp.headers
        result = resp.json()["result"]
        assert result["isError"] is False
        assert result["structuredContent"]["items"][0]["id"] == "PET-000001"
        assert result["structuredContent"]["total"] == 1
        assert result["content"][0]["type"] == "text"
    assert captured == {"species": "犬", "page": "1", "pageSize": "5"}


async def test_invalid_arguments_surface_unified_error_over_http(mcp_http):
    async with mcp_http(ok_handler) as http:
        resp = await http.post(
            "/mcp",
            headers=modern_headers("tools/call", name="list_pets"),
            json=rpc(
                "tools/call",
                envelope(name="list_pets", arguments={"page": 0, "species": "恐龙"}),
            ),
        )
        result = resp.json()["result"]
        assert result["isError"] is True
        payload = result["structuredContent"]
        assert set(payload.keys()) == {"error"}
        assert payload["error"]["code"] == "VALIDATION_ERROR"
        assert payload["error"]["details"]["errors"]


async def test_health_endpoint(mcp_http):
    async with mcp_http(ok_handler) as http:
        resp = await http.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["protocol"] == "2026-07-28"
