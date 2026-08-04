"""单元测试：pkg/common/api.py 中的 Pydantic 模型"""

from datetime import datetime
from pkg.common.api import (
    SafeBigInt,
    SafeDatetime,
    BaseSchema,
    DATETIME_FORMAT,
    parse_datetime,
    serialize_datetime,
)
from pydantic import BaseModel
from typing import Annotated

### 测试数据
# 接口返回模型
class UserResponse(BaseSchema):
    user_id: SafeBigInt  # 出站时自动转字符串
    user_name: str
    start_time: SafeDatetime

# 接口请求模型
class UserCreate(BaseSchema):
    user_id: SafeBigInt  # 入站时，Pydantic 会自动把前端传来的字符串解析为 int
    user_name: str
    start_time: SafeDatetime


# ============================================================
# 测试 SafeBigInt 和 SafeDatetime 基础类型
# ============================================================

class TestSafeBigInt:
    def test_serialize_int_to_str(self):
        """SafeBigInt 在 JSON 序列化时，int 应自动转为字符串"""
        model = _TestBigIntModel(value=1234567890123456789)
        data = model.model_dump_json()
        print(data)
        assert '"1234567890123456789"' in data

    def test_accept_int(self):
        """SafeBigInt 入站应接受 int 类型"""
        model = _TestBigIntModel(value=42)
        assert model.value == 42


class TestSafeDatetime:
    def test_parse_str(self):
        """SafeDatetime 入站时，字符串应自动解析为 datetime"""
        model = _TestDatetimeModel(ts="2026-08-04 11:42:48")
        assert isinstance(model.ts, datetime)
        assert model.ts.year == 2026
        assert model.ts.month == 8
        assert model.ts.day == 4

    def test_accept_datetime(self):
        """SafeDatetime 入站时，datetime 对象应直接保留"""
        dt = datetime(2026, 8, 4, 11, 42, 48)
        model = _TestDatetimeModel(ts=dt)
        assert model.ts is dt

    def test_serialize_to_str(self):
        """SafeDatetime JSON 序列化时应输出指定格式的字符串"""
        model = _TestDatetimeModel(ts=datetime(2026, 8, 4, 11, 42, 48))
        data = model.model_dump_json()
        assert '"2026-08-04 11:42:48"' in data

    def test_parse_datetime_function(self):
        """parse_datetime 工具函数：传入字符串应返回 datetime"""
        dt = parse_datetime("2026-08-04 11:42:48")
        assert isinstance(dt, datetime)
        assert dt.strftime(DATETIME_FORMAT) == "2026-08-04 11:42:48"

    def test_parse_datetime_passthrough(self):
        """parse_datetime 工具函数：传入 datetime 应原样返回"""
        dt = datetime(2026, 8, 4, 11, 42, 48)
        assert parse_datetime(dt) is dt

    def test_serialize_datetime_function(self):
        """serialize_datetime 工具函数应返回格式化字符串"""
        dt = datetime(2026, 8, 4, 11, 42, 48)
        assert serialize_datetime(dt) == "2026-08-04 11:42:48"


# ============================================================
# 测试 UserCreate（请求模型）
# ============================================================

class TestUserCreate:
    def test_create_with_int_id(self):
        """UserCreate 应接受 int 类型的 user_id"""
        user = UserCreate(user_id=123, user_name="张三", start_time=datetime.now())
        assert user.user_id == 123
        assert user.user_name == "张三"
        assert isinstance(user.start_time, datetime)

    def test_create_with_str_id(self):
        """UserCreate 应接受字符串类型的 user_id 并自动转为 int"""
        user = UserCreate(user_id="456", user_name="李四", start_time=datetime.now())
        assert user.user_id == 456

    def test_json_by_alias(self):
        """UserCreate JSON 序列化（by_alias=True）应使用驼峰命名"""
        user = UserCreate(user_id=123, user_name="张三", start_time=datetime(2026, 8, 4, 11, 42, 48))
        data = user.model_dump_json(by_alias=True)
        assert '"userId"' in data
        assert '"userName"' in data
        assert '"startTime"' in data
        # user_id 应序列化为字符串
        assert '"123"' in data

    def test_json_by_name(self):
        """UserCreate JSON 序列化（by_alias=False）应使用原始字段名"""
        user = UserCreate(user_id=123, user_name="张三", start_time=datetime(2026, 8, 4, 11, 42, 48))
        data = user.model_dump_json(by_alias=False)
        assert '"user_id"' in data
        assert '"user_name"' in data
        assert '"start_time"' in data


# ============================================================
# 测试 UserResponse（响应模型）
# ============================================================

class TestUserResponse:
    def test_validate_with_snake_case(self):
        """UserResponse 应接受蛇形命名（user_id）的输入"""
        user = UserResponse.model_validate({
            "user_id": "123",
            "user_name": "张三",
            "start_time": "2026-08-04 11:42:48",
        })
        assert user.user_id == 123
        assert user.user_name == "张三"
        assert isinstance(user.start_time, datetime)

    def test_validate_with_camel_case(self):
        """UserResponse 应接受驼峰命名（userId）的输入"""
        user = UserResponse.model_validate({
            "userId": "456",
            "userName": "李四",
            "startTime": "2026-08-04 11:42:48",
        })
        assert user.user_id == 456
        assert user.user_name == "李四"
        assert isinstance(user.start_time, datetime)

    def test_serialize_json(self):
        """UserResponse JSON 序列化默认使用驼峰别名"""
        user = UserResponse.model_validate({
            "user_id": "789",
            "user_name": "王五",
            "start_time": "2026-08-04 11:42:48",
        })
        data = user.model_dump_json()
        assert '"userId"' in data
        assert '"userName"' in data
        assert '"startTime"' in data
        assert '"789"' in data  # SafeBigInt 应输出字符串

    def test_serialize_json_by_alias_false(self):
        """UserResponse JSON 序列化 by_alias=False 应使用原始字段名"""
        user = UserResponse.model_validate({
            "user_id": "789",
            "user_name": "王五",
            "start_time": "2026-08-04 11:42:48",
        })
        data = user.model_dump_json(by_alias=False)
        assert '"user_id"' in data
        assert '"user_name"' in data
        assert '"start_time"' in data

    def test_roundtrip(self):
        """UserResponse 完整往返：validate → dump(mode='json')，数据应保持一致"""
        original = {
            "user_id": "999",
            "user_name": "赵六",
            "start_time": "2026-08-04 11:42:48",
        }
        user = UserResponse.model_validate(original)
        dumped = user.model_dump(mode='json', by_alias=True)
        # SafeBigInt 在 JSON 模式下自动转为字符串
        assert dumped["userId"] == "999"
        assert dumped["userName"] == "赵六"
        assert dumped["startTime"] == "2026-08-04 11:42:48"


# ============================================================
# 辅助模型（用于测试 SafeBigInt / SafeDatetime 独立行为）
# ============================================================

class _TestBigIntModel(BaseModel):
    value: SafeBigInt


class _TestDatetimeModel(BaseModel):
    ts: SafeDatetime