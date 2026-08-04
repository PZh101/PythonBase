"""纯权限判断工具。"""

from pkg.security.context import AuthContext
from pkg.security.exceptions import PermissionDeniedException, TenantRequiredException


def ensure_tenant(context: AuthContext) -> None:
    """确保当前请求存在租户上下文。"""
    if context.tenant is None or context.member_id is None:
        raise TenantRequiredException()


def ensure_permission(context: AuthContext, permission: str) -> None:
    """确保当前上下文拥有指定权限。"""
    if context.is_platform_admin:
        return
    if not context.has_permission(permission):
        raise PermissionDeniedException()


def ensure_any_permission(context: AuthContext, *permissions: str) -> None:
    """确保当前上下文拥有任意一个权限。"""
    if context.is_platform_admin:
        return
    if not context.permissions.has_any(tuple(permissions)):
        raise PermissionDeniedException()


def ensure_role(context: AuthContext, role: str) -> None:
    """确保当前上下文拥有指定角色。"""
    if context.is_platform_admin:
        return
    if not context.has_role(role):
        raise PermissionDeniedException()
