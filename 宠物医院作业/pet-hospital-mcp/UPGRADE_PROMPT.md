# 阶段二升级说明（UPGRADE_PROMPT）

阶段一仅实现 `list_pets`。阶段二新增工具时按以下约定执行，无需改动既有架构。

## 新增一个工具的步骤

1. 在 `src/pet_hospital_mcp/tools/` 新建模块（如 `get_pet.py`、`create_pet.py`、`stats.py`），
   按 `list_pets.py` 的模式实现：
   - 用 Pydantic 定义**输入模型**（`extra="forbid"`、`strict` 类型、`allow_inf_nan=False`、
     `Literal` 枚举取上游真实允许值）与**输出模型**（对应 Go 响应的 `data`）；
   - 工具名 `snake_case`；描述必须说明用途、参数、适用场景、返回值；
   - 工具体负责：严格校验输入 → 调 `PetHospitalClient` → 校验输出模型；
   - 所有失败路径返回统一错误结构（`errors.to_error_dict`），成功返回
     `CallToolResult(content=[TextContent(...)], structured_content=..., is_error=False)`；
   - 日志必须带 `tool_name`、`params`（经 `redact` 脱敏）、`status`、`duration_ms`。
2. `PetHospitalClient` 中新增对应方法（超时 + 有限重试 + 错误映射，禁止向客户端泄漏
   httpx/Pydantic/Python 堆栈）。
3. 在 `src/pet_hospital_mcp/server.py` 的 `build_server` 中把新工具加入 `tools=[...]`。
4. 在 `tests/` 新增对应测试（httpx.MockTransport，禁止访问真实 Go 服务），
   覆盖：参数转发、校验失败、4xx/5xx、超时/连接异常、非法响应、Schema 与 HTTP 流程。

## 上游接口速查

- 信封：`{"code":200,"message":"ok","data":{...},"time":"..."}`
- 枚举字典：`GET /api/v1/meta`（species/status/sortFields/gender/chargeCategories）
- 列表：`GET /api/v1/pets`（13 参数，已实现）
- 档案：`GET/PUT/PATCH/DELETE /api/v1/pets/{id}`、`POST /api/v1/pets`
- 病历/收费：`GET/POST /api/v1/pets/{id}/records`、`GET/POST /api/v1/pets/{id}/charges`
- 统计与高级查询：`GET /api/v1/stats`、`/api/v1/pets/search?q=`、
  `/api/v1/pets/by-owner`、`/by-doctor`、`/by-species`、`/by-disease`、`/by-status`、
  `/top-spenders?limit=`、`/cost-range?min=&max=`

## 保持不变的部分

- `rest_client.py`、`errors.py`、`logging_config.py`、`config.py` 直接复用；
- 无状态 Streamable HTTP、协议 2026-07-28、`MCPServer`、`server/discover` 发现方式不变；
- 不引入 FastMCP、不实现旧协议 `initialize`/会话机制、不新增适配器私有业务参数。
