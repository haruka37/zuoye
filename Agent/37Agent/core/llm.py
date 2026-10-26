"""客户端层：封装对 OpenAI 兼容 /chat/completions 接口的调用。

只负责「发请求、收响应」，不关心对话流程，也不做任何界面输出。
"""

import json
import urllib.request

from . import config


def build_request(payload: dict) -> urllib.request.Request:
    """根据 payload 构造 HTTP 请求对象（含鉴权头）。"""
    headers = {"Content-Type": "application/json"}
    api_key = config.llm.get("api_key", "")
    if api_key and api_key != "your-api-key":
        headers["Authorization"] = "Bearer " + api_key
    url = config.llm["api_base"].rstrip("/") + "/chat/completions"
    return urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
    )


def chat(messages, tools=None, stream: bool = False):
    """调用 LLM 接口。

    Args:
        messages: 完整对话历史。
        tools:    function-calling 工具 schema 列表（可空）。
        stream:   True 时返回原始响应对象（供流式读取），False 时返回解析后的 dict。
    """
    payload = {
        "model": config.llm["model"],
        "messages": messages,
        "temperature": float(config.llm.get("temperature", 0.7)),
        "stream": stream,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    req = build_request(payload)
    with urllib.request.urlopen(req) as resp:
        if stream:
            return resp
        return json.loads(resp.read().decode("utf-8"))
