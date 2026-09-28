import json

from mcp.server import MCPServer

from .client import AnythingLLM


def build_server(client: AnythingLLM) -> MCPServer:
    server = MCPServer(name="anythingllm-mcp", version="0.1.0")

    @server.tool(
        name="ask_workspace",
        description=(
            "基于唯一 AnythingLLM 工作区中的资料回答问题。"
            "mode='query'(默认)只依据工作区文档回答,mode='chat' 结合通用知识。"
            "返回回答文本与引用来源列表。"
        ),
    )
    def ask_workspace(question: str, mode: str = "query"):
        data = client.chat(question, mode)
        answer = (data.get("textResponse") or "").strip()
        sources = data.get("sources") or []
        blocks = [answer]
        if sources:
            blocks.append(json.dumps(sources, ensure_ascii=False, indent=2))
        return blocks

    return server