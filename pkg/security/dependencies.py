"""FastAPI 安全依赖工厂。"""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Header, Request

from pkg.security.context import AuthContext
from pkg.security.exceptions import AuthenticationRequiredException
from pkg.security.permissions import ensure_any_permission, ensure_permission, ensure_role, ensure_tenant
from pkg.security.providers import AuthContextProvider


def create_auth_context_dependency(provider: AuthContextProvider) -> Callable[..., object]:
    """创建认证上下文依赖。"""

    async def get_auth_context(
        request: Request,
        auth_user_id: Annotated[int | None, Header(alias="X-User-Id")] = None,
        auth_tenant_id: Annotated[int | None, Header(alias="X-Tenant-Id")] = None,
    ) -> AuthContext:
        """从请求头读取用户和租户，并加载认证上下文。"""
        if auth_user_id is None:
            raise AuthenticationRequiredException()
        context = await provider.load_context(user_id=auth_user_id, tenant_id=auth_tenant_id)
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
        """校验当前请求拥有任意一个指定权限。"""
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
