import asyncio
import threading

import uvicorn

from anythingllm_mcp.client import AnythingLLM
from anythingllm_mcp.config import load_config
from anythingllm_mcp.server import build_server


async def main() -> None:
    cfg = load_config()
    client = AnythingLLM(cfg.base_url, cfg.api_key)
    app = build_server(client).streamable_http_app()

    uvicorn_server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error"))
    thread = threading.Thread(target=uvicorn_server.run, daemon=True)
    thread.start()
    while not uvicorn_server.started:
        await asyncio.sleep(0.05)
    port = uvicorn_server.servers[0].sockets[0].getsockname()[1]
    url = f"http://127.0.0.1:{port}/mcp"
    print("serving:", url)

    from mcp import Client

    async with Client(url) as c:
        tools = await c.list_tools()
        print("TOOLS:", [t.name for t in tools.tools])
        result = await c.call_tool("ask_workspace", {"question": "你好", "mode": "query"})
        print("IS_ERROR:", result.is_error)
        for item in result.content:
            print("----- content -----")
            print(getattr(item, "text", item))
    uvicorn_server.should_exit = True


if __name__ == "__main__":
    asyncio.run(main())