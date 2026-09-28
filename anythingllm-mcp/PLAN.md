# anythingllm-mcp — MVP 开发计划

## 目标

用 Python 构建一个 MCP Server(协议版本 **2026-07-28**,传输方式 **Streamable HTTP**),
封装本地 AnythingLLM(`http://localhost:3001`),对外暴露唯一一个工具:

- **`ask_workspace(question)`**:从"唯一工作区"中检索资料,由 AnythingLLM 的 RAG 给出 AI 回答。

MVP 只做这一个功能。

## 关键背景(调研结论)

### AnythingLLM Developer API
- Base URL:`http://localhost:3001`,认证头:`Authorization: Bearer <API_KEY>`
- API Key:`MDVACPY-MP544N3-M28M457-12KCH54`
- 列出工作区:`GET /api/v1/workspaces` → 返回数组,每项含 `slug`/`name`
- 同步问答:`POST /api/v1/workspace/{slug}/chat`
  - 请求体:`{"message": "...", "mode": "query", "sessionId": "<可选>"}`
  - `mode: "query"` = 只依据工作区文档 RAG 回答(符合"提取信息进行 ai 回答")
  - `mode: "chat"` = 通用知识 + 文档
- 响应体:`textResponse`(答案)、`sources[]`(引用来源)、`error`、`metrics`

### MCP 2026-07-28 协议要点(与 2025 版的关键差异)
- **无状态核心**:移除 `initialize`/`initialized` 握手,移除 `Mcp-Session-Id`
- 每个请求自描述:协议版本、客户端信息、能力都放在 `params._meta`
  (`io.modelcontextprotocol/protocolVersion` 等)
- 必带请求头:`MCP-Protocol-Version: 2026-07-28`、`Mcp-Method`、`Mcp-Name`
- 无 `initialize`,如需能力发现用新 RPC `server/discover`(可选,非强制)
- 服务端只暴露一个 HTTP POST 端点(如 `/mcp`),响应为单个 JSON 或该请求作用域的 SSE 流
- `tools/list` 结果带 `ttlMs`/`cacheScope`,可被客户端缓存
- 采用 **MCP Python SDK v2**(2026-07-28 随规范同步发布,`pip install mcp` 即 2.x)
  - `FastMCP` 已改名为 `MCPServer`;用 `mcp.streamable_http_app()` 挂到 ASGI/uvicorn
  - 同一 server 兼容 2025 及更早版本客户端,无需配置
  - 服务端无回传通道,MVP 不使用采样/elicitation/MRTR,单次请求返回结果即可

## 技术栈

| 组件 | 选择 | 说明 |
|---|---|---|
| 语言/运行时 | Python 3.13.7(本机已装) | |
| MCP SDK | `mcp>=2.0.0` | 官方 Python SDK v2,原生 2026-07-28 |
| HTTP 服务 | `uvicorn` | 托管 ASGI 的 `streamable_http_app()` |
| HTTP 客户端 | `httpx` | 调用 AnythingLLM REST API |
| 配置 | `.env` + `python-dotenv`(或环境变量) | 含 base url、api key、端口 |
| 依赖管理 | `venv` + `requirements.txt` | `uv` 未安装,用标准工具 |

## 目录结构(拟定)

```
C:\Users\37\anythingllm-mcp\
├── PLAN.md
├── README.md            # 安装/运行/接入客户端说明
├── requirements.txt
├── .env.example         # ANYTHINGLLM_BASE_URL / ANYTHINGLLM_API_KEY / HOST / PORT
├── .gitignore
├── run.py               # 入口:uvicorn.run(app.streamable_http_app(), ...)
└── src\anythingllm_mcp\
    ├── __init__.py
    ├── config.py        # 读取 .env,配置校验
    ├── anythingllm.py   # AnythingLLM 客户端:list_workspaces / chat
    ├── tool.py          # ask_workspace 工具逻辑(含来源整理)
    └── server.py        # MCPServer 定义 + 注册工具 + streamable_http_app
```

## 工具设计(MVP 唯一功能)

```
ask_workspace(question: str, mode: str = "query") -> CallToolResult
```
- `question`:用户问题(必填)
- `mode`:默认 `"query"`(仅依据工作区文档回答);可选 `"chat"`(文档+通用知识)
- 流程:
  1. 启动时调用 `GET /api/v1/workspaces`
     - 恰好 1 个工作区 → 记录其 `slug`,后续复用
     - 0 个 → 启动报错;多个 → 报错并提示后续将提供工作区选择(MVP 仅支持"唯一工作区")
  2. 调用 `POST /api/v1/workspace/{slug}/chat`,`mode` 默认为 `query`
  3. 返回 `CallToolResult`:
     - 文本块 = `textResponse`(AI 回答)
     - JSON 块 = `sources[]`(引用来源,便于追溯)
     - 出错时返回结构化错误文本/错误码

## MVP 范围(明确做什么/不做什么)

**做:**
- Streamable HTTP 传输,协议 2026-07-28,Serve 于 `/mcp`
- `server/discover`、`tools/list`、`tools/call` 由 SDK 自动支持
- 上述唯一工具 `ask_workspace`(单次问答,非流式)

**不做(MVP 之后):**
- 流式输出(stream-chat)、多轮会话记忆(`sessionId`)
- 文档上传/管理(update-embeddings、vector-search 等)
- 多工作区选择/切换工具
- MCP 端点鉴权(MVP 仅本地,后续可加 OAuth 等)
- 任务/扩展、客户端采样、MRTR 交互

## 实施步骤(里程碑)

1. **脚手架**:创建目录结构、`venv`、安装 `mcp[cli]`、`uvicorn`、`httpx`、`python-dotenv`;写 `.env.example`
2. **配置模块**:`config.py` 读取并校验 base url / api key / host / port
3. **AnythingLLM 客户端**:`anythingllm.py` 实现 `list_workspaces()`、`chat(slug, message, mode)`;启动自检:发现唯一工作区并缓存 slug
4. **MCP 服务**:`server.py` 用 `MCPServer` 注册 `ask_workspace`;`tool.py` 实现问答+来源整理
5. **HTTP 托管**:`run.py` 用 uvicorn 启动 `streamable_http_app()`
6. **验证**
7. **文档**:README(启动方式 + 客户端接入示例)

## 验证方案

1. 启动:`python run.py`(默认 `http://127.0.0.1:8000/mcp`)
2. 用 SDK 客户端自测(内存/HTTP):
   ```python
   from mcp import Client
   async with Client("http://127.0.0.1:8000/mcp") as c:
       tools = await c.list_tools()          # 应含 ask_workspace
       r = await c.call_tool("ask_workspace", {"question": "...", "mode": "query"})
   ```
3. 手工 curl 模拟 2026-07-28 请求头:
   ```http
   POST http://127.0.0.1:8000/mcp
   MCP-Protocol-Version: 2026-07-28
   Mcp-Method: tools/call
   Mcp-Name: ask_workspace
   Content-Type: application/json
   ```
   body 携带 `jsonrpc/id/method/params.name+arguments+_meta`(`_meta` 含 protocolVersion 与 clientInfo)
4. 断言:对同一问题,`ask_workspace` 返回非空文本与 sources;对"唯一工作区"探测在多工作区场景下给出明确报错

## 风险与备注

- AnythingLLM 端点了鉴权需要正确 Bearer 头;API Key 放 `.env`,不提交仓库
- `mode:"query"` 在无引用命中时模型可能不回答,属 AnythingLLM 预期行为,工具层无需特殊处理
- MCP 端点默认只绑定本机接口(127.0.0.1),防止局域网暴露
- 2026-07-28 无握手、无会话:每次请求自描述,MVP 无跨请求状态(工作区 slug 仅启动时探测一次)