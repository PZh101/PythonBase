"""通用业务异常与全局异常处理器

提供全局统一的异常处理机制，所有业务异常继承自 AppException，
异常被捕获后自动转为统一的 ApiResponse 格式返回。

使用方式:
    from pkg.common.exceptions import NotFoundException

    # 抛出异常
    raise NotFoundException("用户不存在")

    # 在 FastAPI 入口注册
    from pkg.common.exceptions import register_exception_handlers
    register_exception_handlers(app)
"""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from pkg.common.api import ApiResponse
from pkg.common.logging import get_logger

logger = get_logger(__name__)


# ──────────────────────────────────────────────
# 业务异常基类
# ──────────────────────────────────────────────
class AppException(Exception):
    """业务异常基类

    所有业务异常继承此类，包含：
    - code: 业务错误码
    - msg: 错误描述
    - data: 附加数据（可选）
    - http_status_code: HTTP 状态码
    """

    def __init__(
        self,
        msg: str = "服务器内部错误",
        *,
        code: int = 50000,
        data: Any = None,
        http_status_code: int = 400,
    ):
        self.code = code
        self.msg = msg
        self.data = data
        self.http_status_code = http_status_code
        super().__init__(msg)

    def __str__(self) -> str:
        return f"[{self.code}] {self.msg}"


# ──────────────────────────────────────────────
# 常见业务异常
# ──────────────────────────────────────────────
class BadRequestException(AppException):
    """请求参数错误 (400)"""

    def __init__(self, msg: str = "请求参数错误", *, code: int = 40000, data: Any = None):
        super().__init__(msg, code=code, data=data, http_status_code=400)


class UnauthorizedException(AppException):
    """未认证 (401)"""

    def __init__(self, msg: str = "请先登录", *, code: int = 40100, data: Any = None):
        super().__init__(msg, code=code, data=data, http_status_code=401)


class ForbiddenException(AppException):
    """无权限 (403)"""

    def __init__(self, msg: str = "无权限访问", *, code: int = 40300, data: Any = None):
        super().__init__(msg, code=code, data=data, http_status_code=403)


class NotFoundException(AppException):
    """资源不存在 (404)"""

    def __init__(self, msg: str = "资源不存在", *, code: int = 40400, data: Any = None):
        super().__init__(msg, code=code, data=data, http_status_code=404)


class ConflictException(AppException):
    """资源冲突 (409)"""

    def __init__(self, msg: str = "资源冲突", *, code: int = 40900, data: Any = None):
        super().__init__(msg, code=code, data=data, http_status_code=409)


class ValidationException(AppException):
    """数据校验失败 (422)"""

    def __init__(self, msg: str = "数据校验失败", *, code: int = 42200, data: Any = None):
        super().__init__(msg, code=code, data=data, http_status_code=422)


class InternalServerException(AppException):
    """服务器内部错误 (500)"""

    def __init__(self, msg: str = "服务器内部错误", *, code: int = 50000, data: Any = None):
        super().__init__(msg, code=code, data=data, http_status_code=500)


# ──────────────────────────────────────────────
# 全局异常处理器
# ──────────────────────────────────────────────
def register_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理器到 FastAPI 应用

    在应用入口处调用一次即可：
        from pkg.common.exceptions import register_exception_handlers
        register_exception_handlers(app)

    覆盖的异常类型：
    - AppException 及其子类 → 按业务状态码返回
    - Exception（兜底）    → 500 服务器内部错误，详细错误写入日志
    """
    @app.exception_handler(AppException)
    async def _app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
        """处理业务异常：按异常中定义的 HTTP 状态码与业务码返回"""
        return JSONResponse(
            status_code=exc.http_status_code,
            content=ApiResponse(code=exc.code, msg=exc.msg, data=exc.data).model_dump(
                by_alias=True
            ),
        )

    @app.exception_handler(Exception)
    async def _global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """兜底异常处理：记录日志并以 500 返回"""
        logger.exception("未捕获的异常: %s", exc)
        return JSONResponse(
            status_code=500,
            content=ApiResponse(
                code=50000, msg="服务器内部错误，请稍后重试"
            ).model_dump(by_alias=True),
        )
