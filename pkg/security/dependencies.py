"""FastAPI 安全依赖工厂。"""
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Header, Request

from pkg.config import AuthMode
from pkg.security.context import AuthContext
from pkg.security.exceptions import (
    AuthenticationRequiredException,
    InvalidCredentialException,
    InvalidTokenException,
)
from pkg.security.permissions import ensure_any_permission, ensure_permission, ensure_role, ensure_tenant
from pkg.security.providers import AuthContextProvider
from pkg.security.token import TokenResolver, extract_bearer_token


def extract_principal_from_request(
    *,
    auth_mode: AuthMode,
    authorization: str | None,
    auth_user_id: int | None,
    auth_tenant_id: int | None,
    token_resolver: TokenResolver | None,
) -> tuple[int, int | None]:
    """按 ``auth_mode`` 严格从请求中解析出 ``(user_id, tenant_id)``。

    不同模式互不干扰：

    - ``AuthMode.JWT``：只看 ``Authorization: Bearer <token>``，忽略 X- 头；
      ``token_resolver`` 必须提供，缺失时直接抛 :class:`RuntimeError`。
    - ``AuthMode.HEADER``：只看 ``X-User-Id`` / ``X-Tenant-Id``，忽略 ``Authorization``。

    Args:
        auth_mode: 认证模式，决定走哪条解析路径。
        authorization: ``Authorization`` 头原始内容。
        auth_user_id: ``X-User-Id`` 头解析出的用户 ID（可为 None）。
        auth_tenant_id: ``X-Tenant-Id`` 头解析出的租户 ID（可为 None）。
        token_resolver: Bearer token 解析器；JWT 模式下必填。

    Returns:
        解析出的 ``(user_id, tenant_id)`` 元组。

    Raises:
        RuntimeError: ``auth_mode=jwt`` 但未提供 ``token_resolver``。
        AuthenticationRequiredException: 缺少必要的认证信息。
        InvalidCredentialException: token 无效（签名错误、过期等）。
    """
    if auth_mode is AuthMode.JWT:
        if token_resolver is None:
            raise RuntimeError("auth_mode=jwt 但未提供 token_resolver")
        token = extract_bearer_token(authorization)
        if token is None:
            raise AuthenticationRequiredException()
        try:
            user_id, tenant_id, _ = token_resolver.resolve(token)
        except InvalidCredentialException:
            raise
        except InvalidTokenException as exc:
            raise InvalidCredentialException(str(exc.msg)) from exc
        return user_id, tenant_id

    # AuthMode.HEADER：忽略 Authorization，仅看 X- 头。
    if auth_user_id is None:
        raise AuthenticationRequiredException()
    return auth_user_id, auth_tenant_id


def create_auth_context_dependency(
    provider: AuthContextProvider,
    *,
    auth_mode: AuthMode,
    token_resolver: TokenResolver | None = None,
) -> Callable[..., object]:
    """创建认证上下文依赖。

    解析路径由 :class:`AuthMode` **严格** 决定，两种模式互不干扰：

    - ``AuthMode.HEADER``：仅从 ``X-User-Id`` / ``X-Tenant-Id`` 头解析；忽略 ``Authorization``。
    - ``AuthMode.JWT``：仅从 ``Authorization: Bearer <token>`` 头解析；忽略 X- 头；
      此时 ``token_resolver`` 必须提供。

    解析失败统一抛出 :class:`AuthenticationRequiredException`
    （token 非法时会包装为 :class:`InvalidCredentialException`，错误码 40101）。

    Args:
        provider: 由应用层实现的认证上下文加载协议。
        auth_mode: 认证模式，决定走哪条解析路径。
        token_resolver: 仅 ``AuthMode.JWT`` 时需要。

    Returns:
        返回 :class:`AuthContext` 的 FastAPI 依赖函数。

    Raises:
        RuntimeError: ``auth_mode=jwt`` 但未提供 ``token_resolver``。
    """
    if auth_mode is AuthMode.JWT and token_resolver is None:
        raise RuntimeError("auth_mode=jwt 但未提供 token_resolver")

    async def get_auth_context(
        request: Request,
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
        auth_user_id: Annotated[int | None, Header(alias="X-User-Id")] = None,
        auth_tenant_id: Annotated[int | None, Header(alias="X-Tenant-Id")] = None,
    ) -> AuthContext:
        """从请求头中读取主体并加载认证上下文。"""
        user_id, tenant_id = extract_principal_from_request(
            auth_mode=auth_mode,
            authorization=authorization,
            auth_user_id=auth_user_id,
            auth_tenant_id=auth_tenant_id,
            token_resolver=token_resolver,
        )

        context = await provider.load_context(user_id=user_id, tenant_id=tenant_id)
        request.state.auth_context = context
        return context

    return get_auth_context


def get_current_auth_context(request: Request) -> AuthContext:
    """从请求状态读取已加载的认证上下文。"""
    context = getattr(request.state, "auth_context", None)
    if context is None:
        raise AuthenticationRequiredException()
    return context


def require_tenant() -> Callable[[AuthContext], None]:
    """创建要求租户上下文的依赖。

    Returns:
        FastAPI 依赖函数，用于校验当前请求已经加载租户上下文。

    使用方式:
        在路由上通过 dependencies 声明租户要求：

        ```python
        @router.get("/tenant/resources", dependencies=[Depends(require_tenant())])
        async def list_tenant_resources():
            ...
        ```
    """

    def dependency(context: Annotated[AuthContext, Depends(get_current_auth_context)]) -> None:
        """校验当前请求存在租户上下文。"""
        ensure_tenant(context)

    return dependency


def require_permission(permission: str) -> Callable[[AuthContext], None]:
    """创建要求指定权限的依赖。

    Args:
        permission: 需要校验的权限编码，例如 ``"user:create"``。

    Returns:
        FastAPI 依赖函数，用于校验当前请求拥有指定权限。

    使用方式:
        在路由上通过 dependencies 声明权限要求：

        ```python
        @router.post("/users", dependencies=[Depends(require_permission("user:create"))])
        async def create_user():
            ...
        ```
    """

    def dependency(context: Annotated[AuthContext, Depends(get_current_auth_context)]) -> None:
        """校验当前请求拥有指定权限。"""
        ensure_permission(context, permission)

    return dependency


def require_any_permission(*permissions: str) -> Callable[[AuthContext], None]:
    """创建要求任意权限的依赖。

    Args:
        *permissions: 可接受的权限编码列表，当前请求拥有任意一个即可通过。

    Returns:
        FastAPI 依赖函数，用于校验当前请求拥有任意一个指定权限。

    使用方式:
        在路由上声明多个可选权限：

        ```python
        @router.put("/users/{user_id}", dependencies=[Depends(require_any_permission("user:update", "user:admin"))])
        async def update_user(user_id: int):
            ...
        ```
    """

    def dependency(context: Annotated[AuthContext, Depends(get_current_auth_context)]) -> None:
        """校验当前请求拥有任意一个权限。"""
        ensure_any_permission(context, *permissions)

    return dependency


def require_role(role: str) -> Callable[[AuthContext], None]:
    """创建要求指定角色的依赖。

    Args:
        role: 需要校验的角色编码，例如 ``"tenant_admin"``。

    Returns:
        FastAPI 依赖函数，用于校验当前请求拥有指定角色。

    使用方式:
        在路由上声明角色要求：

        ```python
        @router.post("/roles", dependencies=[Depends(require_role("tenant_admin"))])
        async def create_role():
            ...
        ```
    """

    def dependency(context: Annotated[AuthContext, Depends(get_current_auth_context)]) -> None:
        """校验当前请求拥有指定角色。"""
        ensure_role(context, role)

    return dependency
