"""The ``list_pets`` tool: strict adapter over ``GET /api/v1/pets``.

Allowed enum values below mirror the Go backend's real dictionaries
(``GET /api/v1/meta``): species/status/chargeCategories/fields/sortFields.
"""

from __future__ import annotations

import functools
import json
import logging
from time import perf_counter
from typing import Annotated, Any, Literal

from mcp_types import CallToolResult, TextContent
from mcp.server.mcpserver.tools.base import Tool
from mcp.server.mcpserver.utilities.func_metadata import ArgModelBase, FuncMetadata
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from ..errors import AppError, ErrorCode, to_error_dict
from ..logging_config import redact
from ..rest_client import PetHospitalClient

logger = logging.getLogger("pet_hospital_mcp.tools.list_pets")

# --- Real backend allowed values (from GET /api/v1/meta) -------------------

SPECIES = ("犬", "猫", "兔", "鸟", "仓鼠", "爬宠", "其他")
STATUSES = ("待就诊", "就诊中", "住院中", "已康复", "慢性病随访")
SORT_FIELDS = (
    "id", "name", "ownerName", "species", "doctor", "disease",
    "status", "totalCost", "visitCount", "createdAt", "updatedAt",
)
ORDERS = ("asc", "desc")

StrictStr = Annotated[str, Field(strict=True)]
NonNegativeFinite = Annotated[float, Field(strict=True, ge=0, allow_inf_nan=False)]
PositiveInt = Annotated[int, Field(strict=True, ge=1)]
PageSizeInt = Annotated[int, Field(strict=True, ge=1, le=500)]


class ListPetsInput(BaseModel):
    """Strict input model for ``GET /api/v1/pets``.

    Rejects unknown fields, NaN/Infinity, out-of-enum values and
    type-incorrect inputs. Wire names are the Go API's camelCase names.
    """

    model_config = ConfigDict(extra="forbid")

    q: StrictStr | None = None
    name: StrictStr | None = None
    owner_name: StrictStr | None = Field(default=None, alias="ownerName")
    owner_phone: StrictStr | None = Field(default=None, alias="ownerPhone")
    # Explicit literal values (source of truth: the SPECIES/STATUSES/...
    # tuples above, mirrored from the Go backend's /api/v1/meta).
    species: Literal["犬", "猫", "兔", "鸟", "仓鼠", "爬宠", "其他"] | None = None
    doctor: StrictStr | None = None
    disease: StrictStr | None = None
    status: Literal["待就诊", "就诊中", "住院中", "已康复", "慢性病随访"] | None = None
    min: NonNegativeFinite | None = None
    max: NonNegativeFinite | None = None
    sort_by: Literal[
        "id", "name", "ownerName", "species", "doctor", "disease", "status",
        "totalCost", "visitCount", "createdAt", "updatedAt",
    ] | None = Field(default=None, alias="sortBy")
    order: Literal["asc", "desc"] | None = None
    page: PositiveInt | None = None
    page_size: PageSizeInt | None = Field(default=None, alias="pageSize")

    @model_validator(mode="after")
    def _check_min_max(self) -> ListPetsInput:
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("min 不能大于 max")
        return self

    def query_params(self) -> dict[str, Any]:
        """camelCase query params; omitted fields are not forwarded.

        Integral floats (e.g. ``min=100``) are sent as integers so the
        upstream query reads ``min=100``, not ``min=100.0``.
        """
        params = self.model_dump(by_alias=True, exclude_none=True)
        for key in ("min", "max"):
            value = params.get(key)
            if isinstance(value, float) and value.is_integer():
                params[key] = int(value)
        return params


# --- Success output models (the Go response's ``data``) ---------------------

class PetItem(BaseModel):
    """One pet record as returned by the backend. Tolerant on optional fields."""

    model_config = ConfigDict(extra="ignore")

    id: str
    name: str | None = None
    species: str | None = None
    breed: str | None = None
    gender: str | None = None
    age_months: int | None = Field(default=None, alias="ageMonths")
    color: str | None = None
    chip_no: str | None = Field(default=None, alias="chipNo")
    owner_name: str | None = Field(default=None, alias="ownerName")
    owner_phone: str | None = Field(default=None, alias="ownerPhone")
    owner_addr: str | None = Field(default=None, alias="ownerAddr")
    doctor: str | None = None
    disease: str | None = None
    status: str | None = None
    allergy: str | None = None
    note: str | None = None
    # The Go backend really emits ``null`` or arrays for these two.
    records: list[dict[str, Any]] | None = None
    charges: list[dict[str, Any]] | None = None
    total_cost: float | None = Field(default=None, alias="totalCost")
    visit_count: int | None = Field(default=None, alias="visitCount")
    created_at: str | None = Field(default=None, alias="createdAt")
    updated_at: str | None = Field(default=None, alias="updatedAt")


class PetListData(BaseModel):
    """Success output: exactly the Go list response's ``data`` payload."""

    items: list[PetItem]
    total: int
    page: int
    page_size: int = Field(alias="pageSize")
    total_pages: int = Field(alias="totalPages")
    total_cost: float = Field(alias="totalCost")


# --- Tool wiring ------------------------------------------------------------

class _RawArguments(ArgModelBase):
    """Argument model that captures the wire arguments verbatim.

    SDK validation is bypassed on purpose: strict validation (unknown fields,
    NaN/Infinity, types, cross-field rules) happens inside the tool body so
    failures are reported through the unified error structure.
    """

    model_config = ConfigDict(extra="allow")

    def model_dump_one_level(self) -> dict[str, Any]:
        return dict(self.__pydantic_extra__ or {})


LIST_PETS_DESCRIPTION = (
    "查询宠物医院档案列表（list_pets）。"
    "用途：检索宠物就诊档案，支持关键词搜索、按宠物姓名/主人姓名/主人电话/种类/"
    "主治医生/疾病/就诊状态过滤、按总花费区间过滤、排序与分页。"
    "适用场景：回答“医院有哪些档案”“某主人的宠物”“某种类的宠物”“某医生的病例”"
    "“花费最高的档案”等检索与统计问题，以及分页浏览大规模档案。"
    "参数：q 关键词全文搜索；name 宠物姓名；ownerName 主人姓名；ownerPhone 主人电话；"
    "species 种类（犬/猫/兔/鸟/仓鼠/爬宠/其他）；doctor 主治医生；disease 疾病；"
    "status 就诊状态（待就诊/就诊中/住院中/已康复/慢性病随访）；"
    "min/max 总花费区间（元，非负，min<=max）；"
    "sortBy 排序字段（id/name/ownerName/species/doctor/disease/status/totalCost/"
    "visitCount/createdAt/updatedAt）；order 排序方向（asc/desc）；"
    "page 页码（>=1）；pageSize 每页条数（1-500）。所有参数均可省略。"
    "返回值：Go API 成功响应的 data 对象，包含 items（宠物档案数组，每条含历史病历 "
    "records 与消费明细 charges，可能为 null 或数组）、total、page、pageSize、"
    "totalPages、totalCost（当前筛选条件下的总花费合计）。"
    "出错时返回统一结构化错误 {\"error\": {\"code\", \"message\", \"details\"}}。"
)


def _format_validation_errors(exc: ValidationError) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    for err in exc.errors():
        message = str(err["msg"])
        if message.startswith("Value error, "):
            message = message[len("Value error, ") :]
        errors.append({"field": ".".join(str(part) for part in err["loc"]), "reason": message})
    return errors


async def _list_pets_impl(client: PetHospitalClient, **kwargs: Any) -> CallToolResult:
    started = perf_counter()

    def _elapsed_ms() -> float:
        return round((perf_counter() - started) * 1000, 1)

    def _error_result(payload: dict[str, Any], status: str) -> CallToolResult:
        logger.warning(
            "list_pets failed",
            extra={
                "tool_name": "list_pets",
                "params": redact(kwargs),
                "status": status,
                "duration_ms": _elapsed_ms(),
            },
        )
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))],
            structured_content=payload,
            is_error=True,
        )

    # 1. Strict input validation (unknown fields, NaN/Infinity, types, enums).
    try:
        params = ListPetsInput.model_validate(kwargs)
    except ValidationError as exc:
        payload = to_error_dict(
            ErrorCode.VALIDATION_ERROR,
            "list_pets 参数校验失败",
            {"errors": _format_validation_errors(exc)},
        )
        return _error_result(payload, "VALIDATION_ERROR")

    # 2. Call the Go backend.
    try:
        data = await client.list_pets(params.query_params())
        pet_list = PetListData.model_validate(data)
    except AppError as exc:
        return _error_result(to_error_dict(exc.code, exc.message, exc.details), exc.code.value)
    except ValidationError:
        return _error_result(
            to_error_dict(ErrorCode.BACKEND_INVALID_RESPONSE, "上游响应不符合预期数据模型", {}),
            "BACKEND_INVALID_RESPONSE",
        )
    except Exception:  # pragma: no cover - last line of defense
        logger.exception("list_pets internal error", extra={"tool_name": "list_pets"})
        return _error_result(
            to_error_dict(ErrorCode.INTERNAL_ERROR, "内部错误：处理请求时发生异常", {}),
            "INTERNAL_ERROR",
        )

    # 3. Success.
    dumped = pet_list.model_dump(mode="json", by_alias=True)
    logger.info(
        "list_pets ok",
        extra={
            "tool_name": "list_pets",
            "params": redact(kwargs),
            "status": "ok",
            "duration_ms": _elapsed_ms(),
        },
    )
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(dumped, ensure_ascii=False))],
        structured_content=dumped,
        is_error=False,
    )


def build_list_pets_tool(client: PetHospitalClient) -> Tool:
    """Build the registered ``list_pets`` Tool bound to the REST client."""
    return Tool(
        fn=functools.partial(_list_pets_impl, client),
        name="list_pets",
        title="宠物档案列表查询",
        description=LIST_PETS_DESCRIPTION,
        parameters=ListPetsInput.model_json_schema(by_alias=True),
        fn_metadata=FuncMetadata(arg_model=_RawArguments),
        is_async=True,
    )
