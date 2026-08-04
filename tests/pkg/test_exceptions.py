"""单元测试：pkg/common/exceptions.py 中的异常类与异常处理器"""

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from pkg.common.exceptions import (
    AppException,
    BadRequestException,
    UnauthorizedException,
    ForbiddenException,
    NotFoundException,
    ConflictException,
    ValidationException,
    InternalServerException,
    register_exception_handlers,
)


# ============================================================
# 测试异常类本身
# ============================================================

class TestAppException:
    """测试 AppException 基类"""

    def test_default_values(self):
        """AppException 默认值：code=50000, msg="服务器内部错误", http_status_code=400"""
        exc = AppException()
        assert exc.code == 50000
        assert exc.msg == "服务器内部错误"
        assert exc.data is None
        assert exc.http_status_code == 400

    def test_custom_values(self):
        """AppException 应接受自定义参数"""
        exc = AppException("自定义错误", code=41234, data={"key": "val"}, http_status_code=412)
        assert exc.code == 41234
        assert exc.msg == "自定义错误"
        assert exc.data == {"key": "val"}
        assert exc.http_status_code == 412

    def test_str_representation(self):
        """__str__ 应返回 [code] msg 格式"""
        exc = AppException("测试错误", code=99999)
        assert str(exc) == "[99999] 测试错误"

    def test_is_exception_subclass(self):
        """AppException 应继承 Exception，可使用 raise 抛出"""
        try:
            raise AppException("抛出的异常")
        except AppException as e:
            assert e.msg == "抛出的异常"


class TestSubExceptions:
    """测试各业务异常子类"""

    def test_bad_request(self):
        """BadRequestException：http 400, code 40000"""
        exc = BadRequestException()
        assert exc.http_status_code == 400
        assert exc.code == 40000
        assert exc.msg == "请求参数错误"

    def test_bad_request_custom(self):
        """BadRequestException 支持自定义 msg"""
        exc = BadRequestException("自定义参数错误")
        assert exc.msg == "自定义参数错误"

    def test_unauthorized(self):
        """UnauthorizedException：http 401, code 40100"""
        exc = UnauthorizedException()
        assert exc.http_status_code == 401
        assert exc.code == 40100
        assert exc.msg == "请先登录"

    def test_forbidden(self):
        """ForbiddenException：http 403, code 40300"""
        exc = ForbiddenException()
        assert exc.http_status_code == 403
        assert exc.code == 40300
        assert exc.msg == "无权限访问"

    def test_not_found(self):
        """NotFoundException：http 404, code 40400"""
        exc = NotFoundException()
        assert exc.http_status_code == 404
        assert exc.code == 40400
        assert exc.msg == "资源不存在"

    def test_not_found_custom(self):
        """NotFoundException 支持自定义 msg"""
        exc = NotFoundException("用户不存在")
        assert exc.msg == "用户不存在"

    def test_conflict(self):
        """ConflictException：http 409, code 40900"""
        exc = ConflictException()
        assert exc.http_status_code == 409
        assert exc.code == 40900
        assert exc.msg == "资源冲突"

    def test_validation(self):
        """ValidationException：http 422, code 42200"""
        exc = ValidationException()
        assert exc.http_status_code == 422
        assert exc.code == 42200
        assert exc.msg == "数据校验失败"

    def test_internal_server(self):
        """InternalServerException：http 500, code 50000"""
        exc = InternalServerException()
        assert exc.http_status_code == 500
        assert exc.code == 50000
        assert exc.msg == "服务器内部错误"


# ============================================================
# 测试 register_exception_handlers 注册的异常处理器
# ============================================================

class TestExceptionHandlers:
    """测试通过 FastAPI TestClient 发出的异常响应"""

    def setup_method(self):
        """每个测试方法前创建独立的 FastAPI 应用并注册处理器"""
        self.app = FastAPI()
        register_exception_handlers(self.app)
        self.client = TestClient(self.app, raise_server_exceptions=False)

    def _assert_api_response(self, response, expected_code: int, expected_msg: str, expected_status: int):
        """公共断言：验证响应符合 ApiResponse 格式"""
        assert response.status_code == expected_status
        body = response.json()
        assert body["code"] == expected_code
        assert body["msg"] == expected_msg
        # data 字段必须存在，可以是 null
        assert "data" in body

    # ── 业务异常 → ApiResponse ──────────────────────────────

    def test_route_raises_not_found(self):
        """路由抛出 NotFoundException → HTTP 404 + ApiResponse 格式"""
        @self.app.get("/test/not-found")
        async def _raise_not_found():
            raise NotFoundException()

        resp = self.client.get("/test/not-found")
        self._assert_api_response(resp, expected_code=40400, expected_msg="资源不存在", expected_status=404)

    def test_route_raises_bad_request(self):
        """路由抛出 BadRequestException → HTTP 400 + ApiResponse 格式"""
        @self.app.get("/test/bad-request")
        async def _raise_bad_request():
            raise BadRequestException("参数无效")

        resp = self.client.get("/test/bad-request")
        self._assert_api_response(resp, expected_code=40000, expected_msg="参数无效", expected_status=400)

    def test_route_raises_unauthorized(self):
        """路由抛出 UnauthorizedException → HTTP 401 + ApiResponse 格式"""
        @self.app.get("/test/unauthorized")
        async def _raise_unauthorized():
            raise UnauthorizedException()

        resp = self.client.get("/test/unauthorized")
        self._assert_api_response(resp, expected_code=40100, expected_msg="请先登录", expected_status=401)

    def test_route_raises_forbidden(self):
        """路由抛出 ForbiddenException → HTTP 403 + ApiResponse 格式"""
        @self.app.get("/test/forbidden")
        async def _raise_forbidden():
            raise ForbiddenException("禁止访问该资源")

        resp = self.client.get("/test/forbidden")
        self._assert_api_response(resp, expected_code=40300, expected_msg="禁止访问该资源", expected_status=403)

    def test_route_raises_conflict(self):
        """路由抛出 ConflictException → HTTP 409 + ApiResponse 格式"""
        @self.app.get("/test/conflict")
        async def _raise_conflict():
            raise ConflictException("数据已存在")

        resp = self.client.get("/test/conflict")
        self._assert_api_response(resp, expected_code=40900, expected_msg="数据已存在", expected_status=409)

    def test_route_raises_validation(self):
        """路由抛出 ValidationException → HTTP 422 + ApiResponse 格式"""
        @self.app.get("/test/validation")
        async def _raise_validation():
            raise ValidationException("邮箱格式错误")

        resp = self.client.get("/test/validation")
        self._assert_api_response(resp, expected_code=42200, expected_msg="邮箱格式错误", expected_status=422)

    def test_route_raises_internal_server(self):
        """路由抛出 InternalServerException → HTTP 500 + ApiResponse 格式"""
        @self.app.get("/test/internal-error")
        async def _raise_internal():
            raise InternalServerException("数据库连接失败")

        resp = self.client.get("/test/internal-error")
        self._assert_api_response(resp, expected_code=50000, expected_msg="数据库连接失败", expected_status=500)

    def test_route_raises_app_exception_with_data(self):
        """AppException 携带 data → 响应中应包含 data 字段"""
        @self.app.get("/test/with-data")
        async def _raise_with_data():
            raise AppException("已处理", code=40001, data={"detail": "详细信息"})

        resp = self.client.get("/test/with-data")
        body = resp.json()
        assert body["code"] == 40001
        assert body["data"]["detail"] == "详细信息"

    # ── 未捕获异常兜底 ────────────────────────────────────

    def test_unhandled_exception_returns_500(self):
        """未捕获的 Exception → HTTP 500 + 通用错误信息"""
        @self.app.get("/test/crash")
        async def _crash():
            raise ValueError("未知错误")

        resp = self.client.get("/test/crash")
        self._assert_api_response(resp, expected_code=50000, expected_msg="服务器内部错误，请稍后重试", expected_status=500)

    # ── 响应体字段名校验（驼峰） ─────────────────────────────

    def test_response_fields_are_camel_case(self):
        """异常响应的 JSON 字段名应使用驼峰命名"""
        @self.app.get("/test/camel-case")
        async def _raise_for_camel():
            raise BadRequestException()

        resp = self.client.get("/test/camel-case")
        body = resp.json()
        # 应使用驼峰：code, msg, data（而非 snake_case）
        assert "code" in body
        assert "msg" in body
        assert "data" in body