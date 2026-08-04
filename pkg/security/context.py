"""认证与授权请求上下文。"""

from dataclasses import dataclass, field

from pkg.tenant.context import TenantContext


@dataclass(frozen=True, slots=True)
class Principal:
    """已认证主体。

    Args:
        user_id: 用户 ID。
        username: 用户名或展示名。
        is_platform_admin: 是否为平台管理员。
        authenticated: 是否已经通过认证。
    """

    user_id: int
    username: str | None = None
    is_platform_admin: bool = False
    authenticated: bool = True


@dataclass(frozen=True, slots=True)
class PermissionSet:
    """权限集合，第一阶段仅支持精确权限匹配。"""

    values: frozenset[str] = field(default_factory=frozenset)

    def has(self, permission: str) -> bool:
        """判断是否拥有指定权限。"""
        return permission in self.values

    def has_any(self, permissions: tuple[str, ...]) -> bool:
        """判断是否拥有任意一个权限。"""
        return any(permission in self.values for permission in permissions)


@dataclass(frozen=True, slots=True)
class AuthContext:
    """一次请求的认证与授权快照。"""

    principal: Principal
    tenant: TenantContext | None
    member_id: int | None
    roles: frozenset[str]
    permissions: PermissionSet

    @property
    def is_platform_admin(self) -> bool:
        """返回当前主体是否为平台管理员。"""
        return self.principal.is_platform_admin

    def has_role(self, role: str) -> bool:
        """判断当前租户上下文中是否拥有指定角色。"""
        return role in self.roles

    def has_permission(self, permission: str) -> bool:
        """判断当前租户上下文中是否拥有指定权限。"""
        return self.permissions.has(permission)
