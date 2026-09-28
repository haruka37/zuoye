import uvicorn

from anythingllm_mcp.client import AnythingLLM
from anythingllm_mcp.config import load_config
from anythingllm_mcp.server import build_server


def main() -> None:
    cfg = load_config()
    client = AnythingLLM(cfg.base_url, cfg.api_key)
    print(f"工作区: {client.workspace_slug()}")
    app = build_server(client).streamable_http_app()
    uvicorn.run(app, host=cfg.host, port=cfg.port)


if __name__ == "__main__":
    main()