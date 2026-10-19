import configparser
import json
import os
import subprocess
import platform
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

# 始终从脚本所在目录读取 config.ini，避免在不同工作目录下运行时找不到配置
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
cfg = configparser.ConfigParser()
cfg.read(os.path.join(BASE_DIR, "config.ini"), encoding="utf-8")
llm = cfg["llm"]
messages = []


def getDate():
    """获取当前电脑的日期和时间。

    实现方式：调用本地 date 系统命令（Windows 用 `cmd /c "date /t & time /t"`，
    Linux / macOS 用 `date`），通过 subprocess 拿取命令输出。
    注意：本函数不依赖 Python 内置的 time / datetime 库。
    """
    if platform.system().lower() == "windows":
        # Windows 下裸 `date` 是交互式（会提示修改日期），这里用
        # `date /t`（日期）与 `time /t`（时间）的非交互形式获取当前时间。
        result = subprocess.run(
            ["cmd", "/c", "date /t & time /t"],
            capture_output=True,
        )
        text = result.stdout.decode("gbk", errors="replace")
        return text.strip().replace("\r", " ").replace("\n", " ")
    else:
        # Linux / macOS 下直接调用 date 系统命令
        result = subprocess.run(["date"], capture_output=True)
        return result.stdout.decode("utf-8", errors="replace").strip()


# 工具定义（OpenAI / 兼容接口 function-calling 格式）
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "getDate",
            "description": (
                "获取当前电脑的日期和时间。"
                "当用户想知道现在几点、今天几号、当前日期或时间时调用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]

# 工具名 -> 本地 Python 函数的映射
TOOL_FUNCTIONS = {
    "getDate": getDate,
}


def _build_request(payload):
    headers = {"Content-Type": "application/json"}
    if llm["api_key"] and llm["api_key"] != "your-api-key":
        headers["Authorization"] = "Bearer " + llm["api_key"]
    return urllib.request.Request(
        llm["api_base"].rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
    )


def _chat(messages, tools=None, stream=False):
    """发送一次对话请求，返回原始响应对象（非流式时为解析后的 dict）。"""
    payload = {
        "model": llm["model"],
        "messages": messages,
        "temperature": float(llm.get("temperature", 0.7)),
        "stream": stream,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    req = _build_request(payload)
    with urllib.request.urlopen(req) as resp:
        if stream:
            return resp  # 调用方逐行处理 SSE 流
        return json.loads(resp.read().decode("utf-8"))


def _stream_print(resp):
    """读取 SSE 流并打印增量文本，返回完整回复字符串。"""
    reply = ""
    for line in resp:
        line = line.decode("utf-8").strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            break
        try:
            content = json.loads(data)["choices"][0]["delta"].get("content", "")
        except (KeyError, IndexError, json.JSONDecodeError):
            continue
        if content:
            reply += content
            print(content, end="", flush=True)
    return reply


def main():
    try:
        print("（直接回车或 Ctrl+C 退出）")
        while True:
            text = input("你的问题是：").strip()
            if not text:
                break
            messages.append({"role": "user", "content": text})

            # 第一轮：允许模型调用工具（非流式，便于可靠解析 tool_calls）
            resp = _chat(messages, tools=TOOLS, stream=False)
            msg = resp["choices"][0]["message"]

            # 如果模型决定调用工具
            if msg.get("tool_calls"):
                # 把带 tool_calls 的助手消息原样追加到历史
                messages.append(msg)
                for tc in msg["tool_calls"]:
                    fn_name = tc["function"]["name"]
                    if fn_name in TOOL_FUNCTIONS:
                        tool_result = TOOL_FUNCTIONS[fn_name]()
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc["id"],
                                "name": fn_name,
                                "content": str(tool_result),
                            }
                        )
                # 第二轮：把工具结果喂回模型，流式输出最终答案
                print("（调用工具 getDate 获取时间中…）")
                resp2 = _chat(messages, tools=None, stream=True)
                reply = _stream_print(resp2)
                messages.append({"role": "assistant", "content": reply})
                print()
            else:
                # 没有工具调用，直接输出回复
                content = msg.get("content", "")
                print(content)
                messages.append({"role": "assistant", "content": content})
    except KeyboardInterrupt:
        print("\n已退出")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--self-test":
        # 自检模式：直接验证 getDate 工具（调用系统 date 命令）是否可用
        print("当前电脑时间（由系统 date 命令返回）：", getDate())
    else:
        main()
