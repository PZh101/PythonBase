"""IAM 认证上下文服务。"""

from typing import Protocol

from pkg.security.context import AuthContext, PermissionSet, Principal
from pkg.security.exceptions import AuthenticationRequiredException, TenantAccessDeniedException
from pkg.tenant.context import TenantContext


class IamAuthRepository(Protocol):
    """认证上下文服务依赖的 IAM 仓储协议。"""

    async def get_active_user(self, user_id: int):
        """查询启用状态的用户。"""

    async def get_active_tenant(self, tenant_id: int):
        """查询启用状态的租户。"""

    async def get_active_member(self, *, user_id: int, tenant_id: int):
        """查询用户在租户内的有效成员身份。"""

    async def list_role_codes(self, member_id: int) -> frozenset[str]:
        """查询成员拥有的角色编码。"""

    async def list_permission_codes(self, member_id: int) -> frozenset[str]:
        """查询成员拥有的权限编码。"""


class IamAuthContextService:
    """按用户和租户加载认证上下文。"""

    def __init__(self, repository: IamAuthRepository) -> None:
        self.repository = repository

    async def load_context(self, *, user_id: int, tenant_id: int | None) -> AuthContext:
        """加载当前请求的认证与授权上下文。"""
        user = await self.repository.get_active_user(user_id)
        if user is None:
            raise AuthenticationRequiredException()

        principal = Principal(
            user_id=user.id,
            username=user.username,
            is_platform_admin=user.is_platform_admin,
            authenticated=True,
        )

        if tenant_id is None:
            return AuthContext(
                principal=principal,
                tenant=None,
                member_id=None,
                roles=frozenset(),
                permissions=PermissionSet(values=frozenset()),
            )

        tenant = await self.repository.get_active_tenant(tenant_id)
        if tenant is None:
            raise TenantAccessDeniedException("无权访问该租户或租户不可用")

        member = await self.repository.get_active_member(user_id=user_id, tenant_id=tenant_id)
        if member is None and not user.is_platform_admin:
            raise TenantAccessDeniedException()

        roles = frozenset() if member is None else await self.repository.list_role_codes(member.id)
        permissions = frozenset() if member is None else await self.repository.list_permission_codes(member.id)

        return AuthContext(
            principal=principal,
            tenant=TenantContext(
                tenant_id=tenant.id,
                tenant_code=tenant.code,
                tenant_name=tenant.name,
                tenant_status=tenant.status,
            ),
            member_id=None if member is None else member.id,
            roles=roles,
            permissions=PermissionSet(values=permissions),
        )
