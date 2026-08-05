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

    # ── 用户查询 ──────────────────────────────────────────

    async def get_active_user(self, user_id: int) -> IamUser | None:
        """查询启用状态的用户。"""
        result = await self.db.execute(select(IamUser).where(IamUser.id == user_id, IamUser.is_active.is_(True)))
        return result.scalars().first()

    # ── 租户管理 ──────────────────────────────────────────

    async def get_active_tenant(self, tenant_id: int) -> IamTenant | None:
        """查询启用状态的租户。"""
        result = await self.db.execute(select(IamTenant).where(IamTenant.id == tenant_id, IamTenant.status == "active"))
        return result.scalars().first()

    async def create_tenant(self, *, code: str, name: str) -> IamTenant:
        """创建新租户。"""
        tenant = IamTenant(code=code, name=name, status="active")
        self.db.add(tenant)
        await self.db.flush()
        return tenant

    async def list_tenants(self) -> list[IamTenant]:
        """查询所有租户。"""
        result = await self.db.execute(select(IamTenant).order_by(IamTenant.id))
        return list(result.scalars().all())

    # ── 租户成员管理 ──────────────────────────────────────

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

    async def add_member(self, *, tenant_id: int, user_id: int) -> IamTenantMember:
        """向租户添加成员。"""
        member = IamTenantMember(tenant_id=tenant_id, user_id=user_id, status="active")
        self.db.add(member)
        await self.db.flush()
        return member

    async def list_members(self, tenant_id: int) -> list[IamTenantMember]:
        """查询租户的所有成员。"""
        result = await self.db.execute(
            select(IamTenantMember).where(IamTenantMember.tenant_id == tenant_id)
        )
        return list(result.scalars().all())

    # ── 角色与权限查询 ────────────────────────────────────

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
