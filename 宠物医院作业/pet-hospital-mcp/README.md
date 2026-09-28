# pet-hospital-mcp

将本地 **Go 宠物医院 REST API** 的能力暴露给 AI Agent 的独立 MCP 服务（阶段一）。

- **语言/运行时**：Python 3.11+
- **SDK**：官方 Python SDK `mcp==2.0.0`（`mcp.server.MCPServer`，非 FastMCP）
- **协议版本**：MCP `2026-07-28`
- **传输**：无状态 Streamable HTTP（Stateless Streamable HTTP）
  - 每个请求独立完成：`mcp-protocol-version` + 请求级 `_meta` 信封
  - **不实现**旧协议 `initialize`、`Mcp-Session-Id`、会话存储/过期、`max_sessions`、有状态 SSE 恢复
  - 发现方式：2026-07-28 规定的 `server/discover` 方法

## 前置条件：先启动 Go 服务

MCP 服务只是适配器，唯一业务后端是 Go 宠物医院服务：

```bash
cd windows
pethospital.exe          # 默认 http://127.0.0.1:8080，需带 data/pet.db
```

## 安装与启动

```bash
cd pet-hospital-mcp
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"   # Windows；Linux/macOS 用 .venv/bin/python
.venv\Scripts\python -m pet_hospital_mcp
```

环境变量（均有默认值，全部可选）：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `PET_HOSPITAL_BASE_URL` | `http://127.0.0.1:8080` | 上游 Go REST API 地址 |
| `MCP_HOST` | `127.0.0.1` | MCP 监听地址 |
| `MCP_PORT` | `8000` | MCP 监听端口 |
| `REQUEST_TIMEOUT_SECONDS` | `10.0` | 单次上游请求超时 |
| `REQUEST_MAX_ATTEMPTS` | `3` | 上游调用总尝试次数（超时/连接失败/502/503/504 时重试） |
| `REQUEST_RETRY_BACKOFF_SECONDS` | `0.1` | 重试线性退避基数 |
| `LOG_LEVEL` | `INFO` | 日志级别（JSON 结构化日志） |

## 端点

| 端点 | 说明 |
| --- | --- |
| `POST http://127.0.0.1:8000/mcp` | MCP 端点（无状态 Streamable HTTP，协议 2026-07-28） |
| `GET  http://127.0.0.1:8000/health` | 健康检查 |

## 当前工具（阶段一，仅一个）

### `list_pets` — 宠物档案列表查询

严格适配 `GET /api/v1/pets`，支持且仅支持全部 13 个上游查询参数：
`q` `name` `ownerName` `ownerPhone` `species` `doctor` `disease` `status` `min` `max` `sortBy` `order` `page` `pageSize`。

严格校验（Pydantic 模型，`additionalProperties: false`）：

- `species`/`status`/`sortBy`/`order` 仅接受后端真实枚举值（来自 `GET /api/v1/meta`）；
- `page >= 1`；`1 <= pageSize <= 500`；`min`/`max` 非负且 `min <= max`；
- 拒绝未知字段、NaN、Infinity 与类型不正确的输入。

成功输出即 Go 响应中的 `data`：`items` `total` `page` `pageSize` `totalPages` `totalCost`；兼容 `records`/`charges` 为 `null` 或数组的真实表现。错误统一为：

```json
{"error": {"code": "ERROR_CODE", "message": "可读信息", "details": {}}}
```

错误码：`VALIDATION_ERROR` / `BACKEND_TIMEOUT` / `BACKEND_UNAVAILABLE` / `BACKEND_API_ERROR` / `BACKEND_INVALID_RESPONSE` / `INTERNAL_ERROR`。

## 验证

### 1) MCP Inspector / SDK 2.x 客户端

用 MCP Inspector（或任何 SDK 2.x Streamable HTTP 客户端）连接 `http://127.0.0.1:8000/mcp`，协议版本选 `2026-07-28`：不需要 `initialize` 握手，无需任何会话头，直接发现并调用 `list_pets`。

### 2) curl 示例

```bash
# 健康检查
curl -s http://127.0.0.1:8000/health
# -> {"status":"ok","upstream":"http://127.0.0.1:8080","protocol":"2026-07-28"}

# 发现（2026-07-28 无状态流程，无 initialize、无会话）
curl -s -X POST http://127.0.0.1:8000/mcp \
  -H 'content-type: application/json' -H 'accept: application/json' \
  -H 'mcp-protocol-version: 2026-07-28' -H 'mcp-method: server/discover' \
  -d '{"jsonrpc":"2.0","id":1,"method":"server/discover","params":{"_meta":{"io.modelcontextprotocol/protocolVersion":"2026-07-28","io.modelcontextprotocol/clientCapabilities":{}}}}'

# 工具列表
curl -s -X POST http://127.0.0.1:8000/mcp \
  -H 'content-type: application/json' -H 'accept: application/json' \
  -H 'mcp-protocol-version: 2026-07-28' -H 'mcp-method: tools/list' \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{"_meta":{"io.modelcontextprotocol/protocolVersion":"2026-07-28","io.modelcontextprotocol/clientCapabilities":{}}}}'

# 调用 list_pets
curl -s -X POST http://127.0.0.1:8000/mcp \
  -H 'content-type: application/json' -H 'accept: application/json' \
  -H 'mcp-protocol-version: 2026-07-28' -H 'mcp-method: tools/call' -H 'mcp-name: list_pets' \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"_meta":{"io.modelcontextprotocol/protocolVersion":"2026-07-28","io.modelcontextprotocol/clientCapabilities":{}},"name":"list_pets","arguments":{"species":"犬","sortBy":"totalCost","order":"desc","page":1,"pageSize":5}}}'
```

### 3) 单元测试

```bash
cd pet_hospital_mcp
pytest -q
```

预期结果：**49 passed**。测试全部使用 `httpx.MockTransport`，不会访问真实 Go 服务。

## 项目结构

```text
pet_hospital_mcp/
├── pyproject.toml
├── README.md
├── UPGRADE_PROMPT.md
├── src/pet_hospital_mcp/
│   ├── __init__.py        # 版本号
│   ├── __main__.py        # python -m pet_hospital_mcp 入口
│   ├── config.py          # 环境变量配置
│   ├── errors.py          # 统一结构化错误（错误码/模型）
│   ├── logging_config.py  # JSON 日志 + 敏感字段递归脱敏
│   ├── rest_client.py     # 上游 HTTP 客户端（超时/有限重试）
│   ├── server.py          # MCPServer 装配 + Streamable HTTP App + /health
│   └── tools/
│       ├── __init__.py
│       └── list_pets.py   # list_pets：输入/输出/错误 Pydantic 模型 + 工具实现
└── tests/                 # 49 个测试（MockTransport，不访问真实后端）
```

日志为 JSON 格式，含 `timestamp`、`tool_name`、`params`、`status`、`duration_ms`；
`ownerPhone`/`ownerAddr`/`chipNo`（含 snake_case 写法）在日志中递归脱敏。

> 教学场景：未实现认证、权限、CORS 与 Origin 校验。
