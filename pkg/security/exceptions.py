"""认证、租户和授权异常。"""

from typing import Any

from pkg.common.exceptions import AppException


class AuthenticationRequiredException(AppException):
    """未认证。"""

    def __init__(self, msg: str = "请先登录", *, code: int = 40100, data: Any = None):
        super().__init__(msg, code=code, data=data, http_status_code=401)


class InvalidCredentialException(AppException):
    """认证凭据无效。"""

    def __init__(self, msg: str = "认证凭据无效", *, code: int = 40101, data: Any = None):
        super().__init__(msg, code=code, data=data, http_status_code=401)


class InvalidTokenException(AppException):
    """JWT 解析或签名校验失败。"""

    def __init__(self, msg: str = "token 无效", *, code: int = 40102, data: Any = None):
        super().__init__(msg, code=code, data=data, http_status_code=401)


class TenantRequiredException(AppException):
    """缺少必需的租户上下文。"""

    def __init__(self, msg: str = "缺少租户上下文", *, code: int = 40310, data: Any = None):
        super().__init__(msg, code=code, data=data, http_status_code=403)


class TenantAccessDeniedException(AppException):
    """无权访问指定租户。"""

    def __init__(self, msg: str = "无权访问该租户", *, code: int = 40311, data: Any = None):
        super().__init__(msg, code=code, data=data, http_status_code=403)


class PermissionDeniedException(AppException):
    """权限不足。"""

    def __init__(self, msg: str = "权限不足", *, code: int = 40300, data: Any = None):
        super().__init__(msg, code=code, data=data, http_status_code=403)
