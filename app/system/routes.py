"""企业组织、用户、角色和资源权限 API 路由。"""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.system.repository import SystemRepository
from app.system.schemas import (
    DeptCreateRequest,
    DeptResponse,
    MenuCreateRequest,
    MenuResponse,
    RelationResponse,
    RoleCreateRequest,
    RoleDeptAssignRequest,
    RoleMenuAssignRequest,
    RoleResponse,
    UserAccessProfileResponse,
    UserCreateRequest,
    UserDeptAssignRequest,
    UserResponse,
    UserRoleAssignRequest,
)
from app.system.service import SystemService
from pkg.common.api import ApiResponse
from pkg.security import require_permission, require_tenant


def _to_schema(schema_type, value):
    """将 ORM 对象转换为响应模型。"""
    return schema_type.model_validate(value, from_attributes=True)


def _to_schema_list(schema_type, values):
    """将 ORM 对象列表转换为响应模型列表。"""
    return [_to_schema(schema_type, value) for value in values]


def create_system_router(
    db_dependency: Callable[..., object],
    auth_dependency: Callable[..., object],
) -> APIRouter:
    """创建企业组织与权限路由。

    Args:
        db_dependency: 返回 ``AsyncSession`` 的 FastAPI 依赖。
        auth_dependency: 返回 ``AuthContext`` 的 FastAPI 认证依赖。

    Returns:
        已绑定数据库和认证依赖的 ``APIRouter``。
    """

    router = APIRouter(
        prefix="/system",
        tags=["企业组织与权限"],
        dependencies=[Depends(auth_dependency)],
    )

    def get_service(db: Annotated[AsyncSession, Depends(db_dependency)]) -> SystemService:
        """构造系统服务。"""
        return SystemService(SystemRepository(db))

    @router.post(
        "/departments",
        response_model=ApiResponse[DeptResponse],
        dependencies=[Depends(require_tenant()), Depends(require_permission("dept:create"))],
    )
    async def create_dept(
        body: DeptCreateRequest,
        service: Annotated[SystemService, Depends(get_service)],
    ) -> ApiResponse[DeptResponse]:
        """创建部门。"""
        return ApiResponse(data=_to_schema(DeptResponse, await service.create_dept(body)))

    @router.get(
        "/departments",
        response_model=ApiResponse[list[DeptResponse]],
        dependencies=[Depends(require_tenant()), Depends(require_permission("dept:read"))],
    )
    async def list_depts(
        service: Annotated[SystemService, Depends(get_service)],
    ) -> ApiResponse[list[DeptResponse]]:
        """查询部门列表。"""
        return ApiResponse(data=_to_schema_list(DeptResponse, await service.list_depts()))

    @router.post(
        "/users",
        response_model=ApiResponse[UserResponse],
        dependencies=[Depends(require_tenant()), Depends(require_permission("user:create"))],
    )
    async def create_user(
        body: UserCreateRequest,
        service: Annotated[SystemService, Depends(get_service)],
    ) -> ApiResponse[UserResponse]:
        """创建用户。"""
        return ApiResponse(data=_to_schema(UserResponse, await service.create_user(body)))

    @router.get(
        "/users",
        response_model=ApiResponse[list[UserResponse]],
        dependencies=[Depends(require_tenant()), Depends(require_permission("user:read"))],
    )
    async def list_users(
        service: Annotated[SystemService, Depends(get_service)],
    ) -> ApiResponse[list[UserResponse]]:
        """查询用户列表。"""
        return ApiResponse(data=_to_schema_list(UserResponse, await service.list_users()))

    @router.post(
        "/users/{user_id}/departments",
        response_model=ApiResponse[RelationResponse],
        dependencies=[Depends(require_tenant()), Depends(require_permission("user:update"))],
    )
    async def assign_user_dept(
        user_id: int,
        body: UserDeptAssignRequest,
        service: Annotated[SystemService, Depends(get_service)],
    ) -> ApiResponse[RelationResponse]:
        """关联用户和部门。"""
        relation = await service.assign_user_dept(user_id=user_id, dept_id=body.dept_id, is_primary=body.is_primary)
        return ApiResponse(data=_to_schema(RelationResponse, relation))

    @router.post(
        "/roles",
        response_model=ApiResponse[RoleResponse],
        dependencies=[Depends(require_tenant()), Depends(require_permission("role:create"))],
    )
    async def create_role(
        body: RoleCreateRequest,
        service: Annotated[SystemService, Depends(get_service)],
    ) -> ApiResponse[RoleResponse]:
        """创建角色。"""
        return ApiResponse(data=_to_schema(RoleResponse, await service.create_role(body)))

    @router.get(
        "/roles",
        response_model=ApiResponse[list[RoleResponse]],
        dependencies=[Depends(require_tenant()), Depends(require_permission("role:read"))],
    )
    async def list_roles(
        service: Annotated[SystemService, Depends(get_service)],
    ) -> ApiResponse[list[RoleResponse]]:
        """查询角色列表。"""
        return ApiResponse(data=_to_schema_list(RoleResponse, await service.list_roles()))

    @router.post(
        "/menus",
        response_model=ApiResponse[MenuResponse],
        dependencies=[Depends(require_tenant()), Depends(require_permission("menu:create"))],
    )
    async def create_menu(
        body: MenuCreateRequest,
        service: Annotated[SystemService, Depends(get_service)],
    ) -> ApiResponse[MenuResponse]:
        """创建菜单或资源。"""
        return ApiResponse(data=_to_schema(MenuResponse, await service.create_menu(body)))

    @router.get(
        "/menus",
        response_model=ApiResponse[list[MenuResponse]],
        dependencies=[Depends(require_tenant()), Depends(require_permission("menu:read"))],
    )
    async def list_menus(
        service: Annotated[SystemService, Depends(get_service)],
    ) -> ApiResponse[list[MenuResponse]]:
        """查询菜单或资源列表。"""
        return ApiResponse(data=_to_schema_list(MenuResponse, await service.list_menus()))

    @router.post(
        "/roles/{role_id}/menus",
        response_model=ApiResponse[RelationResponse],
        dependencies=[Depends(require_tenant()), Depends(require_permission("role:update"))],
    )
    async def assign_role_menu(
        role_id: int,
        body: RoleMenuAssignRequest,
        service: Annotated[SystemService, Depends(get_service)],
    ) -> ApiResponse[RelationResponse]:
        """关联角色和菜单资源。"""
        relation = await service.assign_role_menu(role_id=role_id, menu_id=body.menu_id)
        return ApiResponse(data=_to_schema(RelationResponse, relation))

    @router.post(
        "/users/{user_id}/roles",
        response_model=ApiResponse[RelationResponse],
        dependencies=[Depends(require_tenant()), Depends(require_permission("user:update"))],
    )
    async def assign_user_role(
        user_id: int,
        body: UserRoleAssignRequest,
        service: Annotated[SystemService, Depends(get_service)],
    ) -> ApiResponse[RelationResponse]:
        """关联用户和角色。"""
        relation = await service.assign_user_role(user_id=user_id, role_id=body.role_id)
        return ApiResponse(data=_to_schema(RelationResponse, relation))

    @router.post(
        "/roles/{role_id}/departments",
        response_model=ApiResponse[RelationResponse],
        dependencies=[Depends(require_tenant()), Depends(require_permission("role:update"))],
    )
    async def assign_role_dept(
        role_id: int,
        body: RoleDeptAssignRequest,
        service: Annotated[SystemService, Depends(get_service)],
    ) -> ApiResponse[RelationResponse]:
        """关联角色和自定义数据权限部门。"""
        relation = await service.assign_role_dept(role_id=role_id, dept_id=body.dept_id)
        return ApiResponse(data=_to_schema(RelationResponse, relation))

    @router.get(
        "/users/{user_id}/access-profile",
        response_model=ApiResponse[UserAccessProfileResponse],
        dependencies=[Depends(require_tenant()), Depends(require_permission("user:read"))],
    )
    async def get_user_access_profile(
        user_id: int,
        service: Annotated[SystemService, Depends(get_service)],
    ) -> ApiResponse[UserAccessProfileResponse]:
        """查询用户部门、角色和权限画像。"""
        return ApiResponse(data=await service.get_user_access_profile(user_id))

    return router