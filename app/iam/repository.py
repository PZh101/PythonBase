"""IAM 数据访问。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.iam.models import (
    IamPermission,
    IamRole,
    IamRolePermission,
    IamTenant,
    IamTenantMember,
    IamTenantMemberRole,
    IamUser,
)


class IamRepository:
    """IAM 查询仓储。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_active_user(self, user_id: int) -> IamUser | None:
        """查询启用状态的用户。"""
        result = await self.db.execute(select(IamUser).where(IamUser.id == user_id, IamUser.is_active.is_(True)))
        return result.scalars().first()

    async def get_active_tenant(self, tenant_id: int) -> IamTenant | None:
        """查询启用状态的租户。"""
        result = await self.db.execute(select(IamTenant).where(IamTenant.id == tenant_id, IamTenant.status == "active"))
        return result.scalars().first()

    async def get_active_member(self, *, user_id: int, tenant_id: int) -> IamTenantMember | None:
        """查询用户在租户内的有效成员身份。"""
        result = await self.db.execute(
            select(IamTenantMember).where(
                IamTenantMember.user_id == user_id,
                IamTenantMember.tenant_id == tenant_id,
                IamTenantMember.status == "active",
            )
        )
        return result.scalars().first()

    async def list_role_codes(self, member_id: int) -> frozenset[str]:
        """查询成员拥有的角色编码。"""
        result = await self.db.execute(
            select(IamRole.code)
            .join(IamTenantMemberRole, IamTenantMemberRole.role_id == IamRole.id)
            .where(IamTenantMemberRole.member_id == member_id)
        )
        return frozenset(result.scalars().all())

    async def list_permission_codes(self, member_id: int) -> frozenset[str]:
        """查询成员通过角色拥有的权限编码。"""
        result = await self.db.execute(
            select(IamPermission.code)
            .join(IamRolePermission, IamRolePermission.permission_id == IamPermission.id)
            .join(IamTenantMemberRole, IamTenantMemberRole.role_id == IamRolePermission.role_id)
            .where(IamTenantMemberRole.member_id == member_id)
        )
        return frozenset(result.scalars().all())
