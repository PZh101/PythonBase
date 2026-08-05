"""业务空间与临时授权业务服务。"""

from datetime import datetime

from pkg.common.exceptions import BadRequestException, NotFoundException

from app.workspace.repository import WorkspaceRepository
from app.workspace.schemas import TempAuthGrantRequest, WorkspaceCreateRequest


class WorkspaceService:
    """业务空间与临时授权业务服务。"""

    def __init__(self, repository: WorkspaceRepository) -> None:
        self.repository = repository

    async def create_workspace(self, body: WorkspaceCreateRequest):
        """创建业务空间。"""
        return await self.repository.create_workspace(body.model_dump())

    async def list_workspaces(self):
        """查询业务空间列表。"""
        return await self.repository.list_workspaces()

    async def add_member(self, *, workspace_id: int, user_id: int, role: str):
        """添加业务空间成员。"""
        await self._require_workspace(workspace_id)
        if role not in {"OWNER", "ADMIN", "MEMBER", "GUEST"}:
            raise BadRequestException("空间角色必须是 OWNER、ADMIN、MEMBER 或 GUEST")
        return await self.repository.add_member(workspace_id=workspace_id, user_id=user_id, role=role)

    async def list_members(self, workspace_id: int):
        """查询业务空间成员列表。"""
        await self._require_workspace(workspace_id)
        return await self.repository.list_members(workspace_id)

    async def grant_temp_auth(self, body: TempAuthGrantRequest):
        """授予临时权限。"""
        if body.end_time <= body.start_time:
            raise BadRequestException("临时授权结束时间必须晚于开始时间")
        return await self.repository.grant_temp_auth(body.model_dump())

    async def has_valid_temp_auth(
        self,
        *,
        user_id: int,
        resource_type: str,
        resource_id: int,
        permission: str,
        at_time: datetime | None = None,
    ) -> bool:
        """校验指定时间点是否存在有效临时授权。"""
        auth = await self.repository.find_valid_temp_auth(
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            permission=permission,
            at_time=at_time or datetime.utcnow(),
        )
        return auth is not None

    async def _require_workspace(self, workspace_id: int) -> None:
        """确认业务空间存在。"""
        if await self.repository.get_workspace(workspace_id) is None:
            raise NotFoundException("业务空间不存在")

