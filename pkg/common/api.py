from datetime import datetime

from pydantic import AliasGenerator, BaseModel, BeforeValidator, ConfigDict, Field
from pydantic.alias_generators import to_camel, to_pascal
from pydantic.functional_serializers import PlainSerializer
from pydantic import RootModel
from typing import Annotated, Any, Generic, Literal, TypeVar

from pydantic.main import IncEx

"""
    Pydantic 模型
    自动处理bigint，datetime(时间)类型，自动处理驼峰和to_pascal风格
"""
# 定义安全长整型
SafeBigInt = Annotated[
    int,
    PlainSerializer(lambda v: str(v), return_type=str, when_used='json')
]

# 定义时间格式常量，方便全局统一维护
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"

# 自定义入站解析器：将前端传来的 "2024-01-01 09:30:14" 字符串解析为 datetime 对象
def parse_datetime(value):
    if isinstance(value, str):
        return datetime.strptime(value, DATETIME_FORMAT)
    return value  # 如果已经是 datetime 对象则直接返回

# 自定义出站序列化器：将 datetime 对象转为指定格式的字符串
def serialize_datetime(value: datetime):
    return value.strftime(DATETIME_FORMAT)

# 组合成全局通用的时间类型
SafeDatetime = Annotated[
    datetime,
    BeforeValidator(parse_datetime),       # 入站：自动解析字符串为 datetime
    PlainSerializer(serialize_datetime, return_type=str, when_used='json')  # 出站：自动格式化为字符串
]


class BaseSchema(BaseModel):
    model_config = ConfigDict(
        alias_generator=AliasGenerator(
                validation_alias=to_camel,
                serialization_alias=to_camel,
            ),
        populate_by_name=True,
        serialize_by_alias=True,
    )


# ──────────────────────────────────────────────
# 通用泛型类型变量
# ──────────────────────────────────────────────
DataT = TypeVar("DataT")


# ──────────────────────────────────────────────
# 请求数据结构
# ──────────────────────────────────────────────
class PageParams(BaseSchema):
    """分页请求参数（用于 POST 请求的分页参数传递）"""
    page: int = Field(default=1, ge=1, description="当前页码")
    page_size: int = Field(default=10, ge=1, le=1000, description="每页条数")
    sort_by: str | None = Field(default=None, description="排序字段名，例如 'created_at'")
    sort_order: Literal["asc", "desc"] | None = Field(default=None, description="排序方向，配合 sort_by 使用")


# ──────────────────────────────────────────────
# 响应数据结构
# ──────────────────────────────────────────────
class ApiResponse(BaseSchema, Generic[DataT]):
    """通用 API 响应结构

    基于 {code, msg, data} 的通用响应格式，所有业务响应均基于此构建。

    用法:
        # 成功响应
        ApiResponse(data={"id": 1})

        # 失败响应
        ApiResponse(code=40001, msg="参数校验失败")

        # 带泛型的类型标注
        ApiResponse[MyModel](data=my_model_instance)
    """
    code: int = 0
    msg: str = "success"
    data: DataT | None = None


class PageData(BaseSchema, Generic[DataT]):
    """分页数据包装，用于嵌套在 ApiResponse.data 中

    用法:
        ApiResponse[PageData[MyModel]](
            data=PageData(items=[...], total=100, page=1, page_size=10)
        )
    """
    items: list[DataT] = Field(default_factory=list, description="当前页数据列表")
    total: int = Field(default=0, ge=0, description="数据总数")
    page: int = Field(default=1, ge=1, description="当前页码")
    page_size: int = Field(default=10, ge=1, description="当前每页条数")    



