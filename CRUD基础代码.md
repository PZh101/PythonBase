# PythonBase CRUD 基础代码参考

> 配套规范：[PythonBase CRUD 开发规范](CRUD代码规范.md)

## 1. 文档定位

### 1.1 这份文档解决什么问题

《CRUD 开发规范》定义项目必须遵守的数据库、接口、事务、权限、异常和审计规则。本文件补充规范中引用的基础类型和公共代码，使读者不需要先阅读整个 `pkg/` 目录，也能理解：

- `BaseSchema`、`BaseRequestSchema` 是什么。
- `SafeBigInt`、`SafeId`、`SafeDatetime` 为什么存在。
- `ApiResponse`、`PageRequest`、`PageData` 如何定义。
- 全局异常和 `X-Trace-Id` 如何保持统一。
- JWT 认证完成后，业务代码如何取得当前用户和租户。
- 数据库只读会话、事务会话、审计字段和租户 CRUD 如何实现。
- 雪花 ID、乐观锁和分页查询如何落地。

本文代码是目标实现参考。项目中已经存在同名能力时，应在现有代码上兼容升级，不得机械覆盖。每段代码顶部都标注建议文件路径。

### 1.2 两份文档的职责

| 文档 | 负责 | 不负责 |
| --- | --- | --- |
| `CRUD代码规范.md` | 约束、字段含义、接口契约、正反例、检查清单 | 展开所有公共类的完整实现 |
| `CRUD基础代码.md` | 公共类型、基础组件、可运行代码和测试样例 | 替代具体业务资源的 Schema、Repository 和 Service |

### 1.3 建议模块位置

```text
pkg/
├── common/
│   ├── api.py                 # Pydantic 基类、安全类型、响应和分页模型
│   ├── exceptions.py          # 业务异常与全局异常处理器
│   └── trace.py               # Trace ID 上下文和中间件
├── database/
│   ├── base.py                # SQLAlchemy DeclarativeBase
│   ├── mixins.py              # 固定审计字段 Mixin
│   ├── dependencies.py        # 只读 Session、事务 Session 依赖
│   └── tenant_crud.py         # 租户感知通用 CRUD
├── idgen/
│   └── snowflake.py           # 雪花 ID 生成器
└── security/
    └── current_user.py        # 当前用户和租户上下文
```

业务模块仍按以下结构组织：

```text
app/customer/
├── models.py
├── schemas.py
├── repository.py
├── service.py
└── routes.py
```

---

## 2. Pydantic 公共 API 类型

### 2.1 完整目标代码

建议文件：`pkg/common/api.py`

```python
"""接口基础模型、安全类型和分页模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import (
    AliasGenerator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
    WithJsonSchema,
    computed_field,
    field_validator,
)
from pydantic.alias_generators import to_camel


DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
SIGNED_BIGINT_MAX = 9_223_372_036_854_775_807


def parse_datetime(value: object) -> datetime:
    """把固定格式字符串解析为 datetime。"""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.strptime(value, DATETIME_FORMAT)
        except ValueError as exc:
            raise ValueError(
                f"时间格式必须为 {DATETIME_FORMAT}"
            ) from exc
    raise ValueError("时间必须是 datetime 或固定格式字符串")


def serialize_datetime(value: datetime) -> str:
    """按项目固定格式序列化 datetime。"""
    return value.strftime(DATETIME_FORMAT)


def parse_safe_id(value: object) -> int:
    """只接受有符号 BIGINT 正数范围内的 ASCII 十进制字符串。"""
    if not isinstance(value, str):
        raise ValueError("ID 必须是十进制字符串")
    if not value.isascii() or not value.isdecimal():
        raise ValueError("ID 只能包含 ASCII 数字")
    parsed = int(value)
    if not 0 < parsed <= SIGNED_BIGINT_MAX:
        raise ValueError("ID 超出 BIGINT 正数范围")
    return parsed


SafeBigInt = Annotated[
    int,
    PlainSerializer(
        lambda value: str(value),
        return_type=str,
        when_used="json",
    ),
]

SafeDatetime = Annotated[
    datetime,
    BeforeValidator(parse_datetime),
    PlainSerializer(
        serialize_datetime,
        return_type=str,
        when_used="json",
    ),
]

SAFE_ID_JSON_SCHEMA = {
    "type": "string",
    "pattern": "^[0-9]+$",
    "minLength": 1,
    "maxLength": 19,
    "description": "有符号 BIGINT 正数范围内的十进制字符串",
}

SafeId = Annotated[
    int,
    BeforeValidator(parse_safe_id, json_schema_input_type=str),
    PlainSerializer(
        lambda value: str(value),
        return_type=str,
        when_used="json",
    ),
    WithJsonSchema(SAFE_ID_JSON_SCHEMA, mode="validation"),
    WithJsonSchema(SAFE_ID_JSON_SCHEMA, mode="serialization"),
]


class BaseSchema(BaseModel):
    """响应及内部接口模型基类。"""

    model_config = ConfigDict(
        alias_generator=AliasGenerator(
            validation_alias=to_camel,
            serialization_alias=to_camel,
        ),
        populate_by_name=True,
        serialize_by_alias=True,
        from_attributes=True,
    )


class BaseRequestSchema(BaseSchema):
    """严格请求模型基类，拒绝未知字段。"""

    model_config = ConfigDict(extra="forbid")


DataT = TypeVar("DataT")
FilterT = TypeVar("FilterT")


class ApiResponse(BaseSchema, Generic[DataT]):
    """统一 API 响应。Trace ID 通过响应头返回。"""

    code: int = 0
    msg: str = "success"
    data: DataT | None = None


class SortItem(BaseRequestSchema):
    """分页排序项。"""

    field: str = Field(min_length=1, max_length=64)
    direction: Literal["asc", "desc"]


class PageRequest(BaseRequestSchema, Generic[FilterT]):
    """分页请求基类。具体资源应指定 FilterT。"""

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=200)
    keyword: str | None = Field(default=None, max_length=100)
    filters: FilterT | None = None
    sorts: list[SortItem] = Field(default_factory=list, max_length=3)

    @field_validator("keyword")
    @classmethod
    def normalize_keyword(cls, value: str | None) -> str | None:
        """去除首尾空格，纯空白按未传处理。"""
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class PageData(BaseSchema, Generic[DataT]):
    """统一分页响应数据。"""

    items: list[DataT] = Field(default_factory=list)
    total: int = Field(default=0, ge=0)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1)

    @computed_field(return_type=int)
    @property
    def total_pages(self) -> int:
        """根据总数和每页数量计算总页数。"""
        return (
            (self.total + self.page_size - 1) // self.page_size
            if self.total
            else 0
        )
```

### 2.2 类型含义

| 类型 | Python 内部 | JSON 输入 | JSON 输出 | 用途 |
| --- | --- | --- | --- | --- |
| `SafeId` | `int` | 只允许十进制字符串 | 字符串 | Get/Update/Delete 等外部 ID 请求 |
| `SafeBigInt` | `int` | 兼容 Pydantic 整数解析 | 字符串 | ORM 到响应模型的 BIGINT 字段 |
| `SafeDatetime` | `datetime` | `YYYY-MM-DD HH:mm:ss` | 同格式字符串 | 接口时间字段 |
| `BaseRequestSchema` | Pydantic Model | 支持 camel/snake，拒绝未知字段 | camelCase | 所有请求模型 |
| `BaseSchema` | Pydantic Model | 支持 camel/snake | camelCase | 响应和内部模型 |
| `MISSING` | Pydantic 哨兵 | 表示字段未传 | 自动省略 | Update 的三态字段 |

`SafeId` 与 `SafeBigInt` 不能互换：请求使用 `SafeId` 是为了拒绝已经可能被 JavaScript 舍入的 JSON Number；响应使用 `SafeBigInt` 是为了把 ORM 的 Python `int` 安全输出为字符串。

### 2.3 最小使用示例

```python
from pkg.common.api import (
    ApiResponse,
    BaseRequestSchema,
    BaseSchema,
    SafeBigInt,
    SafeDatetime,
    SafeId,
)


class CustomerGetRequest(BaseRequestSchema):
    """查询客户请求。"""

    id: SafeId


class CustomerResponse(BaseSchema):
    """客户响应。"""

    id: SafeBigInt
    tenant_id: SafeBigInt
    customer_name: str
    created_at: SafeDatetime
```

请求：

```json
{ "id": "1938172456172216320" }
```

以下请求必须返回 422：

```json
{ "id": 1938172456172216320 }
```

### 2.4 Update 字段的省略哨兵

Update 必须区分“字段未传”和“字段显式传入 `null`”。项目已约束 `pydantic>=2.13.4`，统一使用 Pydantic 的 `MISSING` 哨兵，不得用 `None` 冒充字段未传：

```python
from typing import Annotated

from pydantic import Field
from pydantic.experimental.missing_sentinel import MISSING

from pkg.common.api import BaseRequestSchema, SafeId


class CustomerUpdateRequest(BaseRequestSchema):
    """准确表达省略、非空更新值和可空更新值。"""

    id: SafeId
    version: int = Field(ge=1)
    customer_name: (
        Annotated[str, Field(min_length=1, max_length=100)] | MISSING
    ) = MISSING
    description: (
        Annotated[str, Field(max_length=1000)] | None | MISSING
    ) = MISSING
    status: Annotated[int, Field(ge=0, le=1)] | MISSING = MISSING
```

行为约定：

- 省略 `customerName` 或 `status` 时，字段不会出现在 `model_dump()` 和 JSON 序列化结果中。
- 显式传 `customerName: null` 或 `status: null` 时，Pydantic 返回 422。
- `description` 允许显式传 `null`，用于清空可空字段；省略时不更新。
- validation schema 和 serialization schema 都只展示真实业务类型，不会生成“类型为 string 但默认值为 null”的矛盾契约。
- `MISSING` 当前位于 Pydantic experimental 命名空间，升级 Pydantic 时必须运行 Schema 和序列化契约测试。

---

## 3. 资源分页模型

公共 `PageRequest` 只定义固定分页结构。每个业务资源必须定义自己的强类型 Filter，不能让调用方提交任意字段或 SQL 操作符。

建议文件：`app/customer/schemas.py`

```python
from pydantic import Field, model_validator

from pkg.common.api import (
    BaseRequestSchema,
    PageRequest,
    SafeDatetime,
)


class CustomerPageFilter(BaseRequestSchema):
    """客户分页筛选条件。"""

    status: int | None = Field(default=None, ge=0, le=1)
    created_at_start: SafeDatetime | None = None
    created_at_end: SafeDatetime | None = None

    @model_validator(mode="after")
    def validate_time_range(self) -> "CustomerPageFilter":
        """创建时间使用左闭右开区间。"""
        if (
            self.created_at_start is not None
            and self.created_at_end is not None
            and self.created_at_start >= self.created_at_end
        ):
            raise ValueError("createdAtStart 必须早于 createdAtEnd")
        return self


class CustomerPageRequest(PageRequest[CustomerPageFilter]):
    """客户分页请求。"""

    filters: CustomerPageFilter = Field(default_factory=CustomerPageFilter)
```

排序字段在 Repository 中映射，不在公共请求模型中动态反射 ORM：

```python
from app.customer.models import Customer
from pkg.common.api import SortItem
from pkg.common.exceptions import BadRequestException


CUSTOMER_SORT_COLUMNS = {
    "id": Customer.id,
    "customerName": Customer.customer_name,
    "createdAt": Customer.created_at,
    "updatedAt": Customer.updated_at,
}


def build_customer_orders(sorts: list[SortItem]):
    """把已校验的外部排序字段映射为 ORM 排序表达式。"""
    requested = sorts or [
        SortItem(field="createdAt", direction="desc"),
        SortItem(field="id", direction="desc"),
    ]
    orders = []
    has_id = False
    for item in requested:
        column = CUSTOMER_SORT_COLUMNS.get(item.field)
        if column is None:
            raise BadRequestException(f"不支持的排序字段: {item.field}")
        has_id = has_id or item.field == "id"
        orders.append(
            column.asc() if item.direction == "asc" else column.desc()
        )
    if not has_id:
        orders.append(Customer.id.desc())
    return orders
```

模糊检索和结构化过滤同样由资源 Repository 构造：

```python
from sqlalchemy import or_

from app.customer.models import Customer


def escape_like(value: str) -> str:
    """转义 LIKE 中的转义符、百分号和下划线。"""
    return (
        value.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


def build_customer_filters(body: CustomerPageRequest):
    """构造客户分页过滤表达式。"""
    conditions = []
    if body.keyword:
        pattern = f"%{escape_like(body.keyword)}%"
        conditions.append(or_(
            Customer.customer_name.ilike(pattern, escape="\\"),
            Customer.customer_code.ilike(pattern, escape="\\"),
        ))
    if body.filters.status is not None:
        conditions.append(Customer.status == body.filters.status)
    if body.filters.created_at_start is not None:
        conditions.append(
            Customer.created_at >= body.filters.created_at_start
        )
    if body.filters.created_at_end is not None:
        conditions.append(
            Customer.created_at < body.filters.created_at_end
        )
    return conditions
```

这里只检索客户名称和编码。不能反射全部字符串列，也不能把 Agent 生成的字段名或 SQL 片段放入查询。

---

## 4. 统一异常和全局处理器

### 4.1 完整目标代码

建议文件：`pkg/common/exceptions.py`

```python
"""业务异常和 FastAPI 全局异常处理器。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic.alias_generators import to_camel
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from pkg.common.api import ApiResponse
from pkg.common.logging import get_logger
from pkg.common.trace import get_request_trace_id


logger = get_logger(__name__)


class AppException(Exception):
    """业务异常基类。"""

    def __init__(
        self,
        msg: str,
        *,
        code: int,
        http_status_code: int,
        data: Any = None,
    ) -> None:
        self.msg = msg
        self.code = code
        self.http_status_code = http_status_code
        self.data = data
        super().__init__(msg)


class BadRequestException(AppException):
    """请求或业务参数错误。"""

    def __init__(self, msg: str = "请求参数错误", *, code: int = 40000):
        super().__init__(msg, code=code, http_status_code=400)


class UnauthorizedException(AppException):
    """未认证。"""

    def __init__(self, msg: str = "请先登录", *, code: int = 40100):
        super().__init__(msg, code=code, http_status_code=401)


class ForbiddenException(AppException):
    """无权限。"""

    def __init__(self, msg: str = "无权限访问", *, code: int = 40300):
        super().__init__(msg, code=code, http_status_code=403)


class NotFoundException(AppException):
    """资源不存在。"""

    def __init__(self, msg: str = "资源不存在", *, code: int = 40400):
        super().__init__(msg, code=code, http_status_code=404)


class ConflictException(AppException):
    """唯一约束或乐观锁冲突。"""

    def __init__(self, msg: str = "资源冲突", *, code: int = 40900):
        super().__init__(msg, code=code, http_status_code=409)


class ValidationException(AppException):
    """业务数据校验失败。"""

    def __init__(self, msg: str = "数据校验失败", *, code: int = 42200):
        super().__init__(msg, code=code, http_status_code=422)


def _response(
    request: Request,
    *,
    status_code: int,
    code: int,
    msg: str,
    data: Any = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """构造带 Trace ID 的统一 JSON 响应。"""
    trace_id = get_request_trace_id(request)
    payload = ApiResponse(code=code, msg=msg, data=data)
    response_headers = dict(headers or {})
    response_headers["X-Trace-Id"] = trace_id
    return JSONResponse(
        status_code=status_code,
        content=payload.model_dump(mode="json", by_alias=True),
        headers=response_headers,
    )


def register_exception_handlers(app: FastAPI) -> None:
    """注册业务、校验、HTTP、数据库和未知异常处理器。"""

    @app.exception_handler(AppException)
    async def handle_app_exception(
        request: Request,
        exc: AppException,
    ) -> JSONResponse:
        return _response(
            request,
            status_code=exc.http_status_code,
            code=exc.code,
            msg=exc.msg,
            data=exc.data,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_exception(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        errors = []
        for item in exc.errors():
            location = [str(value) for value in item.get("loc", ())]
            field = ".".join(to_camel(value) for value in location[1:])
            errors.append({
                "field": field or "request",
                "message": item.get("msg", "字段校验失败"),
            })
        return _response(
            request,
            status_code=422,
            code=42200,
            msg="数据校验失败",
            data={"errors": errors},
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(
        request: Request,
        exc: StarletteHTTPException,
    ) -> JSONResponse:
        code = exc.status_code * 100
        message = exc.detail if isinstance(exc.detail, str) else "请求处理失败"
        return _response(
            request,
            status_code=exc.status_code,
            code=code,
            msg=message,
            headers=exc.headers,
        )

    @app.exception_handler(IntegrityError)
    async def handle_integrity_error(
        request: Request,
        exc: IntegrityError,
    ) -> JSONResponse:
        logger.bind(exception_type=type(exc).__name__).warning(
            "数据库完整性约束冲突"
        )
        return _response(
            request,
            status_code=409,
            code=40900,
            msg="数据冲突",
        )

    @app.exception_handler(SQLAlchemyError)
    async def handle_database_error(
        request: Request,
        exc: SQLAlchemyError,
    ) -> JSONResponse:
        logger.bind(exception_type=type(exc).__name__).error("数据库操作失败")
        return _response(
            request,
            status_code=500,
            code=50000,
            msg="服务器内部错误，请稍后重试",
        )

    @app.exception_handler(Exception)
    async def handle_unknown_exception(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        logger.opt(exception=exc).error("未捕获异常")
        return _response(
            request,
            status_code=500,
            code=50000,
            msg="服务器内部错误，请稍后重试",
        )
```

### 4.2 注意事项

- Service 应把可预期的唯一约束转换成具体业务消息，例如“客户编码已存在”。全局 `IntegrityError` 只是防止信息泄露的最后兜底。
- 不得把 `str(exc)`、SQL、连接串或堆栈返回调用方。
- 数据库异常日志只记录异常类型、Trace ID 和稳定错误分类；不得记录异常对象、原始 SQL 参数或连接串。Engine 必须同时启用 `hide_parameters=True`，形成双重保护。
- `RequestValidationError` 必须单独注册，否则 FastAPI 会返回默认 `detail` 结构。
- 错误响应和成功响应都必须包含相同的 `X-Trace-Id`。

---

## 5. Trace ID 中间件

建议文件：`pkg/common/trace.py`

```python
"""请求 Trace ID 上下文和中间件。"""

from __future__ import annotations

import re
import secrets
from contextvars import ContextVar

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response


TRACE_HEADER = "X-Trace-Id"
TRACE_PATTERN = re.compile(r"^[0-9a-f]{32}$")
_trace_id_context: ContextVar[str | None] = ContextVar(
    "trace_id",
    default=None,
)


def generate_trace_id() -> str:
    """生成 32 位小写十六进制 Trace ID。"""
    return secrets.token_hex(16)


def normalize_trace_id(value: str | None) -> str:
    """接受合法调用方 Trace ID，否则重新生成。"""
    if value is not None:
        normalized = value.strip().lower()
        if TRACE_PATTERN.fullmatch(normalized):
            return normalized
    return generate_trace_id()


def current_trace_id() -> str:
    """读取当前异步上下文的 Trace ID。"""
    return _trace_id_context.get() or generate_trace_id()


def get_request_trace_id(request: Request) -> str:
    """优先读取 request.state 中间件值。"""
    value = getattr(request.state, "trace_id", None)
    return value if isinstance(value, str) else current_trace_id()


class TraceIdMiddleware(BaseHTTPMiddleware):
    """为每个请求建立 Trace ID 并写入响应头。"""

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        trace_id = normalize_trace_id(request.headers.get(TRACE_HEADER))
        request.state.trace_id = trace_id
        token = _trace_id_context.set(trace_id)
        try:
            response = await call_next(request)
            response.headers[TRACE_HEADER] = trace_id
            return response
        finally:
            _trace_id_context.reset(token)
```

应用装配：

```python
app.add_middleware(TraceIdMiddleware)
register_exception_handlers(app)
```

日志绑定时从 `current_trace_id()` 取值。调用下游 HTTP、消息队列或任务系统时，把 Trace ID 作为元数据继续传递。

---

## 6. 当前用户、租户和权限上下文

JWT 的签名、算法、签发方、过期时间、令牌类型和 token version 必须先由统一认证组件验证。业务 CRUD 不接触原始 JWT，只接收验证后的 `CurrentUser`。

项目已有认证层使用以下概念。它们的关系是：JWT 解析得到主体和租户 ID，认证服务从数据库加载主体、租户、角色和权限，形成 `AuthContext`，最后再转换成普通 CRUD 使用的 `CurrentUser`。

```python
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Principal:
    """已认证主体。"""

    user_id: int
    username: str | None
    authenticated: bool = True
    is_platform_admin: bool = False


@dataclass(frozen=True, slots=True)
class TenantContext:
    """已验证的租户作用域。"""

    tenant_id: int
    tenant_code: str
    tenant_name: str


@dataclass(frozen=True, slots=True)
class PermissionSet:
    """当前作用域权限集合。"""

    values: frozenset[str]


@dataclass(frozen=True, slots=True)
class AuthContext:
    """认证层生成的一次请求授权快照。"""

    principal: Principal
    tenant: TenantContext | None
    roles: frozenset[str]
    permissions: PermissionSet
```

这些对象中的 `tenant_id` 不是直接相信 JWT 后得到的最终结果。认证服务还必须确认用户、租户、成员关系和 token version 当前有效。

建议文件：`pkg/security/current_user.py`

```python
"""面向业务 CRUD 的当前用户上下文。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends

from pkg.common.exceptions import ForbiddenException
from pkg.security.context import AuthContext
from pkg.security.dependencies import get_current_auth_context


@dataclass(frozen=True, slots=True)
class CurrentUser:
    """一次已认证租户请求的不可变用户快照。"""

    user_id: int
    tenant_id: int
    username: str | None
    roles: frozenset[str]
    permissions: frozenset[str]

    def has_permission(self, permission: str) -> bool:
        """判断当前用户是否拥有权限。"""
        return permission in self.permissions


async def get_current_user(
    context: Annotated[AuthContext, Depends(get_current_auth_context)],
) -> CurrentUser:
    """把通用认证上下文转换为普通租户 CRUD 上下文。"""
    if context.tenant is None:
        raise ForbiddenException("当前请求缺少租户上下文")
    return CurrentUser(
        user_id=context.principal.user_id,
        tenant_id=context.tenant.tenant_id,
        username=context.principal.username,
        roles=context.roles,
        permissions=context.permissions.values,
    )
```

权限依赖建议继续使用项目现有接口：

```python
dependencies=[Depends(require_permission("customer:update"))]
```

其核心行为等价于：

```python
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends


def require_permission(permission: str) -> Callable[..., None]:
    """创建单权限校验依赖。"""

    async def dependency(
        context: Annotated[AuthContext, Depends(get_current_auth_context)],
    ) -> None:
        if context.principal.is_platform_admin:
            return
        if permission not in context.permissions.values:
            raise ForbiddenException(f"缺少权限: {permission}")

    return dependency
```

平台管理员绕过必须集中在统一权限依赖中并记录审计，不能散落在业务 Service。

普通 CRUD 不允许 `tenant_id=None`。平台管理员跨租户操作必须使用独立管理接口，将目标租户解析成新的非空作用域上下文，不能通过省略租户条件实现“全租户”。

JWT 载荷中的 BIGINT 也使用字符串：

```json
{
  "sub": "1938172456172216320",
  "tid": "1938172456172216301",
  "ver": 3,
  "type": "access"
}
```

---

## 7. SQLAlchemy 固定字段 Mixin

建议文件：`pkg/database/mixins.py`

```python
"""普通租户业务表的固定字段 Mixin。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, SmallInteger, text
from sqlalchemy.orm import Mapped, mapped_column


class CrudAuditMixin:
    """租户、乐观锁、状态和审计固定字段。"""

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=False,
        comment="雪花算法生成的主键 ID",
    )
    tenant_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="租户 ID",
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
        comment="乐观锁版本号",
    )
    status: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=1,
        server_default=text("1"),
        comment="数据状态",
    )
    created_by: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="创建人用户 ID，系统任务为 0",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        comment="创建时间",
    )
    updated_by: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="最后更新人用户 ID，系统任务为 0",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        comment="最后更新时间",
    )
```

业务模型：

```python
from sqlalchemy import Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from pkg.database import Base
from pkg.database.mixins import CrudAuditMixin


class Customer(CrudAuditMixin, Base):
    """客户主表。"""

    __tablename__ = "biz_customer"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "customer_code",
            name="uk_biz_customer_tenant_code",
        ),
        Index(
            "idx_biz_customer_tenant_status_created",
            "tenant_id",
            "status",
            "created_at",
            "id",
        ),
        {"comment": "客户主表"},
    )

    customer_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="客户名称",
    )
    customer_code: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="租户内客户编码",
    )
    description: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
        comment="客户说明",
    )
```

Mixin 不自动创建索引。每张业务表必须根据唯一约束、过滤和排序方式显式声明带名称的联合索引。通用 `DateTime(timezone=False)` 用于 ORM 类型表达；迁移脚本仍须按数据库方言生成 MySQL `DATETIME(6)` 或 PostgreSQL `TIMESTAMP(6)`，并统一使用项目业务时区。

---

## 8. 雪花 ID 生成器

建议文件：`pkg/idgen/snowflake.py`

```python
"""线程安全的有符号 BIGINT 雪花 ID 生成器。"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable


class ClockRollbackError(RuntimeError):
    """系统时钟发生不可容忍回拨。"""


class SnowflakeIdGenerator:
    """生成 41 位时间、10 位节点、12 位序列的正整数 ID。"""

    TIMESTAMP_BITS = 41
    WORKER_BITS = 10
    SEQUENCE_BITS = 12
    MAX_WORKER_ID = (1 << WORKER_BITS) - 1
    MAX_SEQUENCE = (1 << SEQUENCE_BITS) - 1
    MAX_TIMESTAMP_DELTA = (1 << TIMESTAMP_BITS) - 1

    def __init__(
        self,
        *,
        worker_id: int,
        epoch_ms: int,
        max_clock_backward_ms: int = 5,
        clock_ms: Callable[[], int] | None = None,
    ) -> None:
        if not 0 <= worker_id <= self.MAX_WORKER_ID:
            raise ValueError("worker_id 必须在 0 到 1023 之间")
        if epoch_ms <= 0:
            raise ValueError("epoch_ms 必须为正整数")
        if max_clock_backward_ms < 0:
            raise ValueError("max_clock_backward_ms 不能为负数")
        self.worker_id = worker_id
        self.epoch_ms = epoch_ms
        self.max_clock_backward_ms = max_clock_backward_ms
        self._clock_ms = clock_ms or (lambda: time.time_ns() // 1_000_000)
        self._last_timestamp = -1
        self._sequence = 0
        self._lock = threading.Lock()

    def next_id(self) -> int:
        """生成下一个雪花 ID。"""
        with self._lock:
            timestamp = self._wait_for_valid_clock(self._clock_ms())
            if timestamp == self._last_timestamp:
                self._sequence = (self._sequence + 1) & self.MAX_SEQUENCE
                if self._sequence == 0:
                    timestamp = self._wait_next_millisecond(timestamp)
            else:
                self._sequence = 0

            delta = timestamp - self.epoch_ms
            if not 0 <= delta <= self.MAX_TIMESTAMP_DELTA:
                raise OverflowError("当前时间超出雪花 ID 时间范围")

            self._last_timestamp = timestamp
            return (
                (delta << (self.WORKER_BITS + self.SEQUENCE_BITS))
                | (self.worker_id << self.SEQUENCE_BITS)
                | self._sequence
            )

    def _wait_for_valid_clock(self, timestamp: int) -> int:
        """处理小幅回拨并拒绝大幅回拨。"""
        if timestamp >= self._last_timestamp:
            return timestamp
        backward = self._last_timestamp - timestamp
        if backward > self.max_clock_backward_ms:
            raise ClockRollbackError(f"系统时钟回拨 {backward}ms")
        deadline = time.monotonic() + self.max_clock_backward_ms / 1000
        while timestamp < self._last_timestamp:
            if time.monotonic() >= deadline:
                raise ClockRollbackError("等待系统时钟恢复超时")
            time.sleep(0.0001)
            timestamp = self._clock_ms()
        return timestamp

    def _wait_next_millisecond(self, timestamp: int) -> int:
        """当前毫秒序列耗尽时等待下一毫秒。"""
        current = self._clock_ms()
        while current <= timestamp:
            time.sleep(0.0001)
            current = self._clock_ms()
        return self._wait_for_valid_clock(current)
```

使用方式：

```python
id_generator = SnowflakeIdGenerator(
    worker_id=settings.snowflake.worker_id,
    epoch_ms=settings.snowflake.epoch_ms,
)
```

生成器必须是进程级单例依赖。每个实例的 `worker_id` 必须唯一，不能在代码中统一写死为 `1`。

---

## 9. 数据库 Session 依赖

### 9.1 配置和数据库管理器

规范中的 `DatabaseSettings`、`PoolSettings` 和 `AsyncDatabaseManager` 分别表示强类型连接配置、连接池配置和进程级异步数据库生命周期管理器。项目已有实现，下面给出便于独立理解的目标接口。

建议文件：`pkg/config/models.py`

```python
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DatabaseType(StrEnum):
    """支持的数据库类型。"""

    MYSQL = "mysql"
    POSTGRESQL = "postgresql"


class PoolSettings(BaseModel):
    """数据库连接池配置。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    size: int = Field(default=10, ge=1)
    max_overflow: int = Field(default=20, ge=0)
    timeout: float = Field(default=30, gt=0)
    recycle: int = Field(default=1800, ge=0)
    pre_ping: bool = True


class DatabaseSettings(BaseModel):
    """异步数据库连接配置。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    type: DatabaseType = DatabaseType.MYSQL
    host: str = Field(min_length=1)
    port: int = Field(ge=1, le=65535)
    username: str = Field(min_length=1)
    password: str = Field(repr=False)
    database: str = Field(min_length=1)
    charset: Literal["utf8mb4"] = "utf8mb4"
    echo: bool = False
    connect_timeout: float = Field(default=10, gt=0)
    startup_check: bool = True
    ssl_enabled: bool = False
    ssl_ca: str | None = None
    ssl_cert: str | None = None
    ssl_key: str | None = None
    pool: PoolSettings = Field(default_factory=PoolSettings)

    @model_validator(mode="after")
    def validate_tls_files(self) -> "DatabaseSettings":
        """客户端证书和私钥必须成对配置。"""
        if (self.ssl_cert is None) != (self.ssl_key is None):
            raise ValueError("ssl_cert 和 ssl_key 必须同时配置")
        return self
```

建议文件：`pkg/database/manager.py`

```python
"""异步 SQLAlchemy Engine 和 Session 生命周期。"""

import ssl
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import URL, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from pkg.config.models import DatabaseSettings, DatabaseType


def build_database_url(settings: DatabaseSettings) -> URL:
    """使用 SQLAlchemy URL 安全构造连接地址。"""
    drivers = {
        DatabaseType.MYSQL: "mysql+asyncmy",
        DatabaseType.POSTGRESQL: "postgresql+asyncpg",
    }
    return URL.create(
        drivername=drivers[settings.type],
        username=settings.username,
        password=settings.password,
        host=settings.host,
        port=settings.port,
        database=settings.database,
    )


def build_ssl_context(settings: DatabaseSettings) -> ssl.SSLContext | None:
    """创建验证数据库服务端证书的 TLS 上下文。"""
    if not settings.ssl_enabled:
        return None
    context = ssl.create_default_context(cafile=settings.ssl_ca)
    if settings.ssl_cert is not None and settings.ssl_key is not None:
        context.load_cert_chain(settings.ssl_cert, settings.ssl_key)
    return context


def build_connect_args(settings: DatabaseSettings) -> dict[str, object]:
    """按驱动转换连接超时、字符集和 TLS 参数。"""
    key = (
        "connect_timeout"
        if settings.type is DatabaseType.MYSQL
        else "timeout"
    )
    args: dict[str, object] = {key: settings.connect_timeout}
    if settings.type is DatabaseType.MYSQL:
        args["charset"] = settings.charset
    ssl_context = build_ssl_context(settings)
    if ssl_context is not None:
        args["ssl"] = ssl_context
    return args


class AsyncDatabaseManager:
    """每个进程持有一个异步 Engine 和 SessionFactory。"""

    def __init__(self, settings: DatabaseSettings) -> None:
        self.settings = settings
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    async def initialize(self) -> None:
        """初始化连接池并按配置执行启动检查。"""
        if self._engine is not None:
            return
        try:
            self._engine = create_async_engine(
                build_database_url(self.settings),
                echo=self.settings.echo,
                hide_parameters=True,
                connect_args=build_connect_args(self.settings),
                pool_size=self.settings.pool.size,
                max_overflow=self.settings.pool.max_overflow,
                pool_timeout=self.settings.pool.timeout,
                pool_recycle=self.settings.pool.recycle,
                pool_pre_ping=self.settings.pool.pre_ping,
            )
            self._session_factory = async_sessionmaker(
                bind=self._engine,
                class_=AsyncSession,
                expire_on_commit=False,
                autoflush=False,
            )
            if self.settings.startup_check:
                await self.check_connection()
        except Exception:
            await self.dispose()
            raise

    async def check_connection(self) -> None:
        """执行只读连接检查。"""
        if self._engine is None:
            raise RuntimeError("数据库管理器尚未初始化")
        async with self._engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession]:
        """创建不自动提交的 Session。"""
        session = self._create_session()
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[AsyncSession]:
        """创建成功提交、异常回滚的事务 Session。"""
        session = self._create_session()
        try:
            async with session.begin():
                yield session
        finally:
            await session.close()

    async def dispose(self) -> None:
        """释放连接池。"""
        engine = self._engine
        self._engine = None
        self._session_factory = None
        if engine is not None:
            await engine.dispose()

    def _create_session(self) -> AsyncSession:
        """从已初始化的工厂创建 Session。"""
        if self._session_factory is None:
            raise RuntimeError("数据库管理器尚未初始化")
        return self._session_factory()
```

生产环境还必须通过环境变量或密钥服务注入密码，并设置 `ssl_enabled=true`。默认 TLS 上下文会校验服务端证书和主机名；不得通过 `CERT_NONE` 或关闭主机名校验绕过验证。MySQL 固定使用 `utf8mb4`，PostgreSQL 数据库使用 UTF-8。初始化异常应转换为项目数据库基础设施异常。业务代码不得直接调用 `build_database_url()` 或创建第二个 Engine。

### 9.2 FastAPI Session 依赖

建议文件：`pkg/database/dependencies.py`

```python
"""FastAPI 数据库 Session 依赖。"""

from collections.abc import AsyncIterator, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from pkg.database.manager import AsyncDatabaseManager


def create_readonly_db_session_dependency(
    manager: AsyncDatabaseManager,
) -> Callable[[], AsyncIterator[AsyncSession]]:
    """创建不自动提交的只读 Session 依赖。"""

    async def get_readonly_session() -> AsyncIterator[AsyncSession]:
        async with manager.session() as session:
            yield session

    return get_readonly_session


def create_db_session_dependency(
    manager: AsyncDatabaseManager,
) -> Callable[[], AsyncIterator[AsyncSession]]:
    """创建成功提交、异常回滚的事务 Session 依赖。"""

    async def get_transaction_session() -> AsyncIterator[AsyncSession]:
        async with manager.transaction() as session:
            yield session

    return get_transaction_session
```

路由装配时分别提供读写 Service：

```python
read_db_dependency = create_readonly_db_session_dependency(manager)
write_db_dependency = create_db_session_dependency(manager)
```

- `/get`、`/page` 使用只读依赖。
- `/create`、`/update`、`/delete` 使用事务依赖。
- Repository 只能 `flush()`、`refresh()`，不得 `commit()`。

---

## 10. 租户感知通用 CRUD

该基类只接受已经由业务 Repository 构造的 SQLAlchemy 过滤和排序表达式，不接受客户端字段字符串，因此不会绕过白名单。

建议文件：`pkg/database/tenant_crud.py`

```python
"""带租户和乐观锁约束的通用异步 CRUD。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Generic, TypeVar

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from pkg.database.base import Base
from pkg.database.mixins import CrudAuditMixin


ModelT = TypeVar("ModelT", bound=Base)


class TenantAwareCrud(Generic[ModelT]):
    """普通租户表的通用 CRUD；事务由调用方管理。"""

    def __init__(self, model: type[ModelT]) -> None:
        if not issubclass(model, CrudAuditMixin):
            raise TypeError("model 必须继承 CrudAuditMixin")
        self.model = model

    async def get(
        self,
        db: AsyncSession,
        *,
        tenant_id: int,
        entity_id: int,
    ) -> ModelT | None:
        """按租户和 ID 查询。"""
        statement = (
            select(self.model)
            .where(
                self.model.id == entity_id,
                self.model.tenant_id == tenant_id,
            )
            .execution_options(populate_existing=True)
        )
        result = await db.execute(statement)
        return result.scalars().first()

    async def create(
        self,
        db: AsyncSession,
        *,
        values: Mapping[str, Any],
    ) -> ModelT:
        """新增并 flush，不提交事务。"""
        entity = self.model(**dict(values))
        db.add(entity)
        await db.flush()
        await db.refresh(entity)
        return entity

    async def update_by_version(
        self,
        db: AsyncSession,
        *,
        tenant_id: int,
        entity_id: int,
        expected_version: int,
        values: Mapping[str, Any],
        updated_by: int,
        updated_at: datetime,
    ) -> ModelT | None:
        """按租户、ID 和版本更新；返回 None 表示未命中。"""
        forbidden = {
            "id",
            "tenant_id",
            "version",
            "created_by",
            "created_at",
            "updated_by",
            "updated_at",
        }
        if forbidden.intersection(values):
            raise ValueError("更新数据包含系统字段")
        statement = (
            update(self.model)
            .where(
                self.model.id == entity_id,
                self.model.tenant_id == tenant_id,
                self.model.version == expected_version,
            )
            .values(
                **dict(values),
                version=self.model.version + 1,
                updated_by=updated_by,
                updated_at=updated_at,
            )
            .execution_options(synchronize_session=False)
        )
        result = await db.execute(statement)
        if (result.rowcount or 0) != 1:
            return None
        await db.flush()
        return await self.get(
            db,
            tenant_id=tenant_id,
            entity_id=entity_id,
        )

    async def delete_by_version(
        self,
        db: AsyncSession,
        *,
        tenant_id: int,
        entity_id: int,
        expected_version: int,
    ) -> bool:
        """按租户、ID 和版本物理删除。"""
        statement = delete(self.model).where(
            self.model.id == entity_id,
            self.model.tenant_id == tenant_id,
            self.model.version == expected_version,
        )
        result = await db.execute(statement)
        await db.flush()
        return (result.rowcount or 0) == 1

    async def page(
        self,
        db: AsyncSession,
        *,
        tenant_id: int,
        page: int,
        page_size: int,
        filters: Sequence[ColumnElement[bool]],
        orders: Sequence[ColumnElement[Any]],
    ) -> tuple[Sequence[ModelT], int]:
        """按同一组条件执行 COUNT 和分页数据查询。"""
        if page < 1 or not 1 <= page_size <= 200:
            raise ValueError("分页参数超出范围")
        if not orders:
            raise ValueError("分页查询必须提供稳定排序")
        conditions = [self.model.tenant_id == tenant_id, *filters]
        count_statement = (
            select(func.count())
            .select_from(self.model)
            .where(*conditions)
        )
        total_result = await db.execute(count_statement)
        total = int(total_result.scalar_one())

        data_statement = (
            select(self.model)
            .where(*conditions)
            .order_by(*orders)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        data_result = await db.execute(data_statement)
        return data_result.scalars().all(), total
```

说明：

- `TenantAwareCrud` 不负责把请求字段转换成 SQL。具体 Repository 必须构建过滤和排序白名单。
- `get()` 使用 `populate_existing=True`，确保 bulk UPDATE 后即使 identity map 中已有同一对象，也会用数据库新值覆盖旧字段。
- `update_by_version()` 返回 `None` 后，Service 再按 `id + tenant_id` 查询：不存在抛 404，存在抛 40901。
- `delete_by_version()` 前必须由 Service 查询、锁定、校验关联关系并记录删除前审计快照。
- MySQL 和 PostgreSQL 对 `RETURNING` 支持不同，因此示例更新后重新查询，保持方言兼容。

---

## 11. Service 基础协作对象

Service 需要统一时钟和 ID 生成协议，避免代码直接依赖全局函数。

建议文件：`pkg/common/protocols.py`

```python
"""便于依赖注入和测试的基础协议。"""

from datetime import datetime
from typing import Protocol


class IdGenerator(Protocol):
    """ID 生成器协议。"""

    def next_id(self) -> int:
        """生成下一个 ID。"""
        ...


class Clock(Protocol):
    """项目统一业务时钟协议。"""

    def now(self) -> datetime:
        """返回项目统一时区的当前时间。"""
        ...
```

客户 Service 构造示例：

```python
class CustomerService:
    """客户业务服务。"""

    def __init__(
        self,
        repository: CustomerRepository,
        id_generator: IdGenerator,
        clock: Clock,
        audit_service: AuditService,
    ) -> None:
        self.repository = repository
        self.id_generator = id_generator
        self.clock = clock
        self.audit_service = audit_service
```

新增固定字段：

```python
now = self.clock.now()
values = {
    **body.model_dump(),
    "id": self.id_generator.next_id(),
    "tenant_id": current_user.tenant_id,
    "version": 1,
    "created_by": current_user.user_id,
    "created_at": now,
    "updated_by": current_user.user_id,
    "updated_at": now,
}
```

---

## 12. Create 幂等基础组件

幂等组件用于处理 Agent、网关或客户端因超时而重试 Create 请求。它只解决“同一个新增请求不得重复执行”，不能代替业务唯一约束。

### 12.1 幂等键和请求指纹

建议把请求头类型放在 `pkg/common/api.py`：

```python
from typing import Annotated

from pydantic import Field


IdempotencyKey = Annotated[
    str,
    Field(
        min_length=16,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
        description="Create 请求幂等键",
    ),
]
```

请求指纹必须由 Pydantic 校验后的请求模型生成，不能直接哈希未经规范化的原始 JSON 字符串：

```python
import hashlib
import json

from pydantic import BaseModel


def build_request_fingerprint(body: BaseModel) -> str:
    """对规范化后的请求数据计算 SHA-256 指纹。"""
    normalized = body.model_dump(
        mode="json",
        by_alias=True,
        exclude_none=False,
    )
    canonical_json = json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
```

正例：同一个 Pydantic 请求对象无论调用方 JSON 字段顺序如何，都会得到相同指纹。

反例：直接对原始请求字节计算指纹。以下两个语义相同的 JSON 会产生不同结果：

```json
{"customerName":"示例客户","status":1}
```

```json
{"status":1,"customerName":"示例客户"}
```

### 12.2 幂等记录模型

建议文件：`pkg/idempotency/models.py`

```python
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    Index,
    JSON,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from pkg.database.base import Base


class IdempotencyRecord(Base):
    """Create 请求的幂等占位和首次成功结果。"""

    __tablename__ = "sys_idempotency_record"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "user_id",
            "resource",
            "idempotency_key",
            name="uk_sys_idempotency_scope_key",
        ),
        Index("idx_sys_idempotency_expires_at", "expires_at"),
        {"comment": "接口幂等记录表"},
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=False,
        comment="雪花算法生成的主键 ID",
    )
    tenant_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="租户 ID",
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        comment="发起请求的用户 ID",
    )
    resource: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="资源名称",
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="调用方提供的幂等键",
    )
    request_fingerprint: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="规范化请求的 SHA-256 指纹",
    )
    state: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        comment="处理状态：processing/completed",
    )
    response_data: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="首次成功响应中的 data",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        comment="创建时间",
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
        comment="处理完成时间",
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        comment="过期清理时间",
    )
```

这是基础设施表，不是普通业务资源，不继承 `CrudAuditMixin`，也不开放五个 CRUD 接口。`response_data` 只保存尺寸受控的 Create 响应 `data`；敏感字段必须先脱敏或加密，不得保存 JWT、密码、密钥或完整请求头。过期记录由受控任务分批物理删除，不得在请求链路执行无界清理。

### 12.3 唯一约束抢占和结果复用

建议文件：`pkg/idempotency/store.py`

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from pkg.common.exceptions import ConflictException
from pkg.idempotency.models import IdempotencyRecord


@dataclass(frozen=True, slots=True)
class IdempotencyDecision:
    """本次请求是首次执行，还是复用首次成功结果。"""

    action: Literal["execute", "replay"]
    record: IdempotencyRecord


class IdempotencyStore:
    """事务由调用方管理的数据库幂等存储。"""

    async def reserve(
        self,
        db: AsyncSession,
        *,
        record_id: int,
        tenant_id: int,
        user_id: int,
        resource: str,
        idempotency_key: str,
        request_fingerprint: str,
        now: datetime,
        expires_at: datetime,
    ) -> IdempotencyDecision:
        """依靠唯一约束抢占执行权，不提交外层事务。"""
        record = IdempotencyRecord(
            id=record_id,
            tenant_id=tenant_id,
            user_id=user_id,
            resource=resource,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            state="processing",
            response_data=None,
            created_at=now,
            completed_at=None,
            expires_at=expires_at,
        )
        try:
            # SAVEPOINT 只隔离唯一键冲突，不能提交外层业务事务。
            async with db.begin_nested():
                db.add(record)
                await db.flush()
            return IdempotencyDecision(action="execute", record=record)
        except IntegrityError:
            existing = await self._find(
                db,
                tenant_id=tenant_id,
                user_id=user_id,
                resource=resource,
                idempotency_key=idempotency_key,
            )
            if existing is None:
                # 冲突来自主键等其他约束，交给数据库异常层处理。
                raise
            if existing.request_fingerprint != request_fingerprint:
                raise ConflictException(
                    "幂等键已用于不同请求",
                    code=40902,
                )
            if existing.state == "completed" and existing.response_data is not None:
                return IdempotencyDecision(action="replay", record=existing)
            raise ConflictException("相同请求正在处理中", code=40903)

    async def complete(
        self,
        db: AsyncSession,
        *,
        record: IdempotencyRecord,
        response_data: dict[str, Any],
        completed_at: datetime,
    ) -> None:
        """在业务写入所在事务中保存首次成功结果。"""
        record.state = "completed"
        record.response_data = response_data
        record.completed_at = completed_at
        await db.flush()

    async def _find(
        self,
        db: AsyncSession,
        *,
        tenant_id: int,
        user_id: int,
        resource: str,
        idempotency_key: str,
    ) -> IdempotencyRecord | None:
        statement = select(IdempotencyRecord).where(
            IdempotencyRecord.tenant_id == tenant_id,
            IdempotencyRecord.user_id == user_id,
            IdempotencyRecord.resource == resource,
            IdempotencyRecord.idempotency_key == idempotency_key,
        )
        result = await db.execute(statement)
        return result.scalars().first()
```

MySQL 和 PostgreSQL 都必须通过迁移脚本创建上述唯一约束。并发请求会在唯一键处竞争：首次事务成功后，后续同指纹请求读取并复用结果；首次事务回滚后，后续请求可以重新抢占。生产实现应设置数据库锁等待超时，并把超时转换为稳定的 `40903` 或 `503`，不能无限等待。

### 12.4 Create 事务编排

Route 使用 `IdempotencyKey` 接收请求头，Service 在同一个 `AsyncSession` 中完成占位、业务新增、成功审计和结果保存：

```python
from datetime import timedelta
from typing import Annotated

from fastapi import Header
from sqlalchemy.ext.asyncio import AsyncSession

from pkg.common.api import IdempotencyKey


async def create_customer_idempotently(
    db: AsyncSession,
    *,
    body: CustomerCreateRequest,
    current_user: CurrentUser,
    idempotency_key: Annotated[
        IdempotencyKey,
        Header(alias="X-Idempotency-Key"),
    ],
) -> CustomerResponse:
    """在 Route 的事务 Session 中执行幂等新增。"""
    now = clock.now()
    decision = await idempotency_store.reserve(
        db,
        record_id=id_generator.next_id(),
        tenant_id=current_user.tenant_id,
        user_id=current_user.user_id,
        resource="customers",
        idempotency_key=idempotency_key,
        request_fingerprint=build_request_fingerprint(body),
        now=now,
        expires_at=now + timedelta(hours=24),
    )
    if decision.action == "replay":
        return CustomerResponse.model_validate(decision.record.response_data)

    entity = await customer_service.create_core(
        db,
        body=body,
        current_user=current_user,
    )
    response = CustomerResponse.model_validate(entity, from_attributes=True)
    await audit_service.append_create(db, entity, current_user=current_user)
    await idempotency_store.complete(
        db,
        record=decision.record,
        response_data=response.model_dump(mode="json", by_alias=True),
        completed_at=clock.now(),
    )
    return response
```

上例依赖 `/create` 使用第 9.2 节的事务 Session。任何一步抛出异常，幂等占位、客户数据和成功审计一起回滚。`reserve()`、业务 Repository、审计组件和 `complete()` 均不得调用 `commit()`。

反例：

```python
await idempotency_store.reserve(...)
await db.commit()  # 占位先提交，后续业务失败会留下永久 processing 记录
await customer_repository.create(...)
```

以下做法同样禁止：仅在进程内用字典缓存幂等键、先查询再新增但没有唯一约束、不同载荷复用同一键时返回第一次结果、把当前请求的新 Trace ID 存入并重放旧响应头。

---

## 13. 审计代码边界

审计表不是普通可变业务表，不应套用支持更新和删除的 `TenantAwareCrud`。审计 Repository 只暴露追加写接口：

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """脱敏后的审计事件。"""

    id: int
    tenant_id: int
    trace_id: str
    user_id: int
    action: Literal["create", "get", "update", "delete", "page"]
    resource_type: str
    resource_id: int | None
    request_path: str
    client_ip: str | None
    user_agent: str | None
    result: Literal["success", "failure"]
    error_code: int | None
    duration_ms: int
    before_data: dict[str, Any] | None
    after_data: dict[str, Any] | None
    created_at: datetime


class AuditWriter(Protocol):
    """只允许追加审计事件。"""

    async def append(
        self,
        db: AsyncSession,
        event: AuditEvent,
    ) -> None:
        """追加事件，不提供 update/delete。"""
        ...
```

要求：

- Create、Update、Delete 成功审计必须把业务正在使用的同一个 `AsyncSession` 传给 `append(db, event)`，让审计与业务写入处于同一事务；审计失败必须回滚业务。
- 失败审计在业务事务回滚后使用独立事务或可靠异步通道记录。
- `before_data`、`after_data` 先经过字段白名单和脱敏器。
- 审计存储采用 append-only 权限，普通应用代码不能更新和删除历史审计。
- 数据库 CASCADE 删除如果不能可靠获得实际删除集合，不得用于需要逐条审计的关系。

---

## 14. 应用装配顺序

建议在 `app.web.create_app()` 中按固定顺序装配：

```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """初始化并释放进程级数据库连接池。"""
    await manager.initialize()
    app.state.database = manager
    try:
        yield
    finally:
        await manager.dispose()


def create_app() -> FastAPI:
    """创建并装配应用。"""
    app = FastAPI(lifespan=lifespan)

    # 1. 最外层请求追踪。
    app.add_middleware(TraceIdMiddleware)

    # 2. 全局异常必须能读取 Trace ID。
    register_exception_handlers(app)

    # 3. 构造数据库、认证、ID、时钟和审计依赖。
    read_db = create_readonly_db_session_dependency(manager)
    write_db = create_db_session_dependency(manager)

    # 4. 注册业务路由，读写路由使用不同 Session 依赖。
    app.include_router(
        create_customer_router(
            read_db_dependency=read_db,
            write_db_dependency=write_db,
            auth_dependency=auth_dependency,
            id_generator=id_generator,
            clock=clock,
        )
    )
    return app
```

不要在每个路由中重复创建雪花生成器、数据库 Engine、JWT 解析器或日志配置。

---

## 15. 基础代码测试

### 15.1 SafeId 和字段别名

```python
from pydantic import ValidationError


def test_safe_id_schema_and_runtime() -> None:
    """SafeId 的 Schema 和运行时都必须要求字符串。"""
    schema = CustomerGetRequest.model_json_schema(mode="validation")
    assert schema["properties"]["id"]["type"] == "string"
    assert CustomerGetRequest(id="1938172456172216320").id == 1938172456172216320

    with pytest.raises(ValidationError):
        CustomerGetRequest(id=1938172456172216320)


def test_response_uses_camel_case_and_string_bigint() -> None:
    """响应默认输出 camelCase 和字符串 BIGINT。"""
    response = CustomerResponse.model_validate({
        "id": 1938172456172216320,
        "tenant_id": 1938172456172216301,
        "customer_name": "示例客户",
        "created_at": "2026-08-28 18:00:00",
    })
    dumped = response.model_dump(mode="json")
    assert dumped["id"] == "1938172456172216320"
    assert dumped["tenantId"] == "1938172456172216301"
```

### 15.2 分页和 Trace ID

```python
def test_page_data_calculates_total_pages() -> None:
    """分页响应应正确计算总页数。"""
    data = PageData[int](items=[], total=125, page=1, page_size=20)
    assert data.total_pages == 7


def test_trace_id_is_returned_on_validation_error(client) -> None:
    """校验异常响应也必须返回 Trace ID。"""
    response = client.post(
        "/customers/get",
        json={"id": 123},
        headers={"X-Trace-Id": "4bf92f3577b34da6a3ce929d0e0e4736"},
    )
    assert response.status_code == 422
    assert response.headers["X-Trace-Id"] == "4bf92f3577b34da6a3ce929d0e0e4736"
    assert response.json()["code"] == 42200
```

### 15.3 租户和乐观锁

必须测试：

- 所有 Get/Page/Update/Delete SQL 都包含 `tenant_id`。
- 相同 ID 在其他租户不可见。
- 版本一致时更新成功且 `version + 1`。
- 版本不一致时 Service 返回 `40901`。
- 物理删除使用 `id + tenant_id + version`。
- Repository 没有调用 `commit()`。
- 审计追加失败时 Create/Update/Delete 事务回滚。

---

### 15.4 Create 幂等

必须使用两个独立数据库连接并发测试，而不是只测试串行调用：

- 相同作用域、相同幂等键和相同指纹只新增一条业务数据，后续请求复用首次 `data`。
- 相同幂等键但不同指纹返回 `40902`，不泄露第一次响应。
- 首次事务回滚后不存在残留占位，重试可以正常执行。
- 处理中或锁等待超时返回约定错误，不会执行两次业务写入。
- 幂等结果与成功审计任一步写入失败时，整个 Create 事务回滚。
- 当前请求仍返回自己的 `X-Trace-Id`，不重放首次请求的响应头。

---

## 16. 当前项目已有与待补能力

| 能力 | 当前项目 | 按规范目标 |
| --- | --- | --- |
| `BaseSchema` | 已有 | 增加 `from_attributes=True` 或继续显式传参 |
| `SafeBigInt` | 已有 | 保留响应序列化用途 |
| `SafeDatetime` | 已有 | 保留并统一应用时区 |
| `SafeId` | 缺少 | 新增严格字符串请求类型 |
| `BaseRequestSchema` | 缺少 | 新增 `extra="forbid"` |
| `ApiResponse` | 已有 | 保留 `code/msg/data` |
| `PageData` | 已有 | 增加 `total_pages`，上限统一为 200 |
| 多字段 `SortItem` | 缺少 | 新增并由资源白名单映射 |
| 422 全局转换 | 缺少 | 注册 `RequestValidationError` 处理器 |
| Trace ID | 缺少 | 增加上下文、中间件、响应头和日志注入 |
| CurrentUser | 有 `AuthContext` | 增加普通租户 CRUD 的非空作用域适配器 |
| 数据库会话 | 已有读写依赖 | 路由实际区分使用 |
| `TenantAwareCrud` | 已有 | 补充乐观锁和多字段稳定分页能力 |
| 雪花 ID | 缺少 | 增加进程级生成器和节点配置 |
| 审计组件 | 缺少 | 增加 append-only 审计写入与脱敏 |
| Create 幂等 | 缺少 | 增加请求指纹、唯一约束、原子占位和结果复用 |

以上“待补”表示后续实施内容，不代表只阅读文档就已修改项目源码。

---

## 17. 基础类速查

| 名称 | 定义位置 | 谁使用 | 主要作用 |
| --- | --- | --- | --- |
| `BaseSchema` | `pkg/common/api.py` | 响应模型 | camelCase、ORM 转换 |
| `BaseRequestSchema` | `pkg/common/api.py` | 五类请求模型 | camelCase、拒绝未知字段 |
| `SafeId` | `pkg/common/api.py` | 请求 ID | 严格十进制字符串和 BIGINT 范围 |
| `SafeBigInt` | `pkg/common/api.py` | 响应 BIGINT | JSON 输出字符串 |
| `SafeDatetime` | `pkg/common/api.py` | 请求/响应时间 | 固定时间解析和输出 |
| `ApiResponse[T]` | `pkg/common/api.py` | 所有路由 | `code/msg/data` 统一响应 |
| `PageRequest[T]` | `pkg/common/api.py` | Page 请求 | 页码、关键词、Filter、Sort |
| `PageData[T]` | `pkg/common/api.py` | Page 响应 | items、total、totalPages |
| `MISSING` | `pydantic.experimental.missing_sentinel` | Update Request | 区分字段省略与显式 `null` |
| `AppException` | `pkg/common/exceptions.py` | Service | 稳定业务错误语义 |
| `TraceIdMiddleware` | `pkg/common/trace.py` | FastAPI 应用 | 生成和回传 Trace ID |
| `CurrentUser` | `pkg/security/current_user.py` | Route/Service | 当前用户和非空租户作用域 |
| `CrudAuditMixin` | `pkg/database/mixins.py` | ORM 模型 | 八个固定字段 |
| `SnowflakeIdGenerator` | `pkg/idgen/snowflake.py` | Service | 生成 BIGINT 主键 |
| `TenantAwareCrud[T]` | `pkg/database/tenant_crud.py` | Repository | 租户、乐观锁、分页基础 SQL |
| `AuditWriter` | 审计模块 | Service | 只追加脱敏审计事件 |
| `IdempotencyKey` | `pkg/common/api.py` | Create Route | 校验 `X-Idempotency-Key` |
| `IdempotencyStore` | `pkg/idempotency/store.py` | Create Service | 唯一约束抢占和首次结果复用 |

读者看到规范中的公共类名时，可以先在本表定位，再阅读对应章节和代码。
