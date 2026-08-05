"""业务空间与临时授权数据访问。"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.workspace.models import SysTempAuth, SysWorkspace, SysWorkspaceMember


class WorkspaceRepository:
    """业务空间与临时授权仓储。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_workspace(self, data: dict) -> SysWorkspace:
        """创建业务空间。"""
        workspace = SysWorkspace(**data)
        self.db.add(workspace)
        await self.db.flush()
        await self.db.refresh(workspace)
        return workspace

    async def list_workspaces(self) -> list[SysWorkspace]:
        """查询业务空间列表。"""
        result = await self.db.execute(select(SysWorkspace).order_by(SysWorkspace.id.asc()))
        return list(result.scalars().all())

    async def get_workspace(self, workspace_id: int) -> SysWorkspace | None:
        """按 ID 查询业务空间。"""
        result = await self.db.execute(select(SysWorkspace).where(SysWorkspace.id == workspace_id))
        return result.scalars().first()

    async def add_member(self, *, workspace_id: int, user_id: int, role: str) -> SysWorkspaceMember:
        """添加业务空间成员。"""
        member = SysWorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=role)
        self.db.add(member)
        await self.db.flush()
        await self.db.refresh(member)
        return member

    async def list_members(self, workspace_id: int) -> list[SysWorkspaceMember]:
        """查询业务空间成员列表。"""
        result = await self.db.execute(
            select(SysWorkspaceMember)
            .where(SysWorkspaceMember.workspace_id == workspace_id)
            .order_by(SysWorkspaceMember.id.asc())
        )
        return list(result.scalars().all())

    async def grant_temp_auth(self, data: dict) -> SysTempAuth:
        """创建临时授权。"""
        auth = SysTempAuth(**data)
        self.db.add(auth)
        await self.db.flush()
        await self.db.refresh(auth)
        return auth

    async def find_valid_temp_auth(
        self,
        *,
        user_id: int,
        resource_type: str,
        resource_id: int,
        permission: str,
        at_time: datetime,
    ) -> SysTempAuth | None:
        """查询有效临时授权。"""
        result = await self.db.execute(
            select(SysTempAuth).where(
                SysTempAuth.user_id == user_id,
                SysTempAuth.resource_type == resource_type,
                SysTempAuth.resource_id == resource_id,
                SysTempAuth.permission == permission,
                SysTempAuth.start_time <= at_time,
                SysTempAuth.end_time >= at_time,
            )
        )
        return result.scalars().first()

