# anythingllm-mcp

用 Python 构建的 MCP Server（协议版本 2026-07-28，传输方式 Streamable HTTP），封装本地 AnythingLLM（`http://localhost:3001`），对外暴露唯一一个工具：

- **`ask_workspace(question, mode?)`**：从"唯一工作区"中检索资料，由 AnythingLLM 的 RAG 给出 AI 回答。
  - `mode` 默认 `"query"`（仅依据工作区文档回答），可选 `"chat"`（文档 + 通用知识）。

## 目录结构

```
anythingllm-mcp/
├── README.md
├── PLAN.md
├── requirements.txt
├── .env / .env.example
├── run.py                  # 入口
└── anythingllm_mcp/
    ├── __init__.py
    ├── config.py
    ├── client.py
    └── server.py
```

## 配置

复制 `.env.example` 为 `.env`：

```
ANYTHINGLLM_BASE_URL=http://localhost:3001
ANYTHINGLLM_API_KEY=<你的 API Key>
MCP_HOST=127.0.0.1
MCP_PORT=8000
```

## 启动

在项目根目录执行：

```powershell
.\.venv\Scripts\activate
python run.py
```

或一条命令：

```powershell
.\.venv\Scripts\python.exe run.py
```

默认监听 `http://127.0.0.1:8000/mcp`。

## 停止

按端口找到进程并终止：

```powershell
Get-NetTCPConnection -LocalPort 8000 | Stop-Process -Id {$_.OwningProcess} -Force
```

或按进程 ID 直接停止：

```powershell
Stop-Process -Id <PID>
```

## 接入客户端

opencode 通过 `opencode.json` 连接：

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "anythingllm": {
      "type": "remote",
      "url": "http://127.0.0.1:8000/mcp",
      "enabled": true
    }
  }
}
```

## 验证

```python
from mcp import Client

async with Client("http://127.0.0.1:8000/mcp") as c:
    tools = await c.list_tools()  # 应含 ask_workspace
    r = await c.call_tool("ask_workspace", {"question": "...", "mode": "query"})
```