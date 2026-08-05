"""业务空间与临时授权 API 路由。"""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.workspace.repository import WorkspaceRepository
from app.workspace.schemas import (
    TempAuthCheckResponse,
    TempAuthGrantRequest,
    TempAuthResponse,
    WorkspaceCreateRequest,
    WorkspaceMemberAddRequest,
    WorkspaceMemberResponse,
    WorkspaceResponse,
)
from app.workspace.service import WorkspaceService
from pkg.common.api import ApiResponse


def _to_schema(schema_type, value):
    """将 ORM 对象转换为响应模型。"""
    return schema_type.model_validate(value, from_attributes=True)


def _to_schema_list(schema_type, values):
    """将 ORM 对象列表转换为响应模型列表。"""
    return [_to_schema(schema_type, value) for value in values]


def create_workspace_router(db_dependency: Callable[..., object]) -> APIRouter:
    """创建业务空间与临时授权路由。

    Args:
        db_dependency: 返回 `AsyncSession` 的 FastAPI 依赖。

    Returns:
        已绑定数据库依赖的 `APIRouter`。
    """

    router = APIRouter(prefix="/workspaces", tags=["业务空间与临时授权"])

    def get_service(db: Annotated[AsyncSession, Depends(db_dependency)]) -> WorkspaceService:
        """构造业务空间服务。"""
        return WorkspaceService(WorkspaceRepository(db))

    @router.post("", response_model=ApiResponse[WorkspaceResponse])
    async def create_workspace(
        body: WorkspaceCreateRequest,
        service: Annotated[WorkspaceService, Depends(get_service)],
    ) -> ApiResponse[WorkspaceResponse]:
        """创建业务空间。"""
        return ApiResponse(data=_to_schema(WorkspaceResponse, await service.create_workspace(body)))

    @router.get("", response_model=ApiResponse[list[WorkspaceResponse]])
    async def list_workspaces(
        service: Annotated[WorkspaceService, Depends(get_service)],
    ) -> ApiResponse[list[WorkspaceResponse]]:
        """查询业务空间列表。"""
        return ApiResponse(data=_to_schema_list(WorkspaceResponse, await service.list_workspaces()))

    @router.post("/{workspace_id}/members", response_model=ApiResponse[WorkspaceMemberResponse])
    async def add_member(
        workspace_id: int,
        body: WorkspaceMemberAddRequest,
        service: Annotated[WorkspaceService, Depends(get_service)],
    ) -> ApiResponse[WorkspaceMemberResponse]:
        """添加业务空间成员。"""
        member = await service.add_member(workspace_id=workspace_id, user_id=body.user_id, role=body.role)
        return ApiResponse(data=_to_schema(WorkspaceMemberResponse, member))

    @router.get("/{workspace_id}/members", response_model=ApiResponse[list[WorkspaceMemberResponse]])
    async def list_members(
        workspace_id: int,
        service: Annotated[WorkspaceService, Depends(get_service)],
    ) -> ApiResponse[list[WorkspaceMemberResponse]]:
        """查询业务空间成员列表。"""
        return ApiResponse(data=_to_schema_list(WorkspaceMemberResponse, await service.list_members(workspace_id)))

    @router.post("/temp-auth", response_model=ApiResponse[TempAuthResponse])
    async def grant_temp_auth(
        body: TempAuthGrantRequest,
        service: Annotated[WorkspaceService, Depends(get_service)],
    ) -> ApiResponse[TempAuthResponse]:
        """授予临时权限。"""
        return ApiResponse(data=_to_schema(TempAuthResponse, await service.grant_temp_auth(body)))

    @router.get("/temp-auth/check", response_model=ApiResponse[TempAuthCheckResponse])
    async def check_temp_auth(
        user_id: Annotated[int, Query()],
        resource_type: Annotated[str, Query()],
        resource_id: Annotated[int, Query()],
        permission: Annotated[str, Query()],
        service: Annotated[WorkspaceService, Depends(get_service)],
    ) -> ApiResponse[TempAuthCheckResponse]:
        """校验临时权限是否有效。"""
        allowed = await service.has_valid_temp_auth(
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            permission=permission,
        )
        return ApiResponse(data=TempAuthCheckResponse(allowed=allowed))

    return router
