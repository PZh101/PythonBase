"""IAM 数据访问。"""

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.iam.models import (
    IamPermission,
    IamRole,
    IamRolePermission,
    IamTenant,
    IamTenantMember,
    IamTenantMemberRole,
    IamUser,
    IamUserCredential,
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

    async def get_user_by_username(self, username: str) -> IamUser | None:
        """按登录账号查询用户（不限启用状态，供登录校验使用）。"""
        result = await self.db.execute(select(IamUser).where(IamUser.username == username))
        return result.scalars().first()

    # ── 用户凭证 ──────────────────────────────────────────

    async def get_credential(self, user_id: int) -> IamUserCredential | None:
        """按用户 ID 查询凭证行。"""
        result = await self.db.execute(
            select(IamUserCredential).where(IamUserCredential.user_id == user_id)
        )
        return result.scalars().first()

    async def create_credential(
        self,
        *,
        user_id: int,
        password_hash: str,
    ) -> IamUserCredential:
        """为用户初始化凭证行。"""
        credential = IamUserCredential(
            user_id=user_id,
            password_hash=password_hash,
            token_version=0,
            failed_attempts=0,
        )
        self.db.add(credential)
        await self.db.flush()
        return credential

    async def update_password_hash(
        self,
        *,
        user_id: int,
        new_password_hash: str,
    ) -> None:
        """更新密码哈希并将 token_version +1，使历史 token 失效。"""
        await self.db.execute(
            update(IamUserCredential)
            .where(IamUserCredential.user_id == user_id)
            .values(
                password_hash=new_password_hash,
                token_version=IamUserCredential.token_version + 1,
                failed_attempts=0,
                locked_until=None,
                password_changed_at=datetime.utcnow(),
            )
        )
        await self.db.flush()

    async def mark_login_success(self, *, user_id: int) -> None:
        """登录成功时清零失败计数并刷新 last_login_at。"""
        await self.db.execute(
            update(IamUserCredential)
            .where(IamUserCredential.user_id == user_id)
            .values(
                failed_attempts=0,
                locked_until=None,
                last_login_at=datetime.utcnow(),
            )
        )
        await self.db.flush()

    async def increment_failed_attempts(
        self,
        *,
        user_id: int,
        lock_until: datetime | None,
    ) -> int:
        """登录失败时累加计数，必要时锁定。返回更新后的失败次数。"""
        await self.db.execute(
            update(IamUserCredential)
            .where(IamUserCredential.user_id == user_id)
            .values(
                failed_attempts=IamUserCredential.failed_attempts + 1,
                locked_until=lock_until,
            )
        )
        await self.db.flush()
        result = await self.db.execute(
            select(IamUserCredential.failed_attempts).where(
                IamUserCredential.user_id == user_id
            )
        )
        return int(result.scalar_one())

    async def bump_token_version(self, *, user_id: int) -> int:
        """登出或重置密码时使历史 token 全部失效，返回新的 token_version。"""
        await self.db.execute(
            update(IamUserCredential)
            .where(IamUserCredential.user_id == user_id)
            .values(token_version=IamUserCredential.token_version + 1)
        )
        await self.db.flush()
        result = await self.db.execute(
            select(IamUserCredential.token_version).where(
                IamUserCredential.user_id == user_id
            )
        )
        return int(result.scalar_one())

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
