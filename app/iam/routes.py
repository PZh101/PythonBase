"""IAM 认证与租户管理 API 路由。"""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.iam.repository import IamRepository
from app.iam.schemas import (
    AuthContextResponse,
    PrincipalResponse,
    TenantContextResponse,
    TenantCreateRequest,
    TenantMemberAddRequest,
    TenantMemberResponse,
    TenantResponse,
)
from pkg.common.api import ApiResponse
from pkg.common.exceptions import BadRequestException, NotFoundException
from pkg.security import (
    get_current_auth_context,
    require_permission,
    require_tenant,
)
from pkg.security.context import AuthContext


def _to_tenant_response(tenant) -> TenantResponse:
    """将 IamTenant ORM 转换为响应模型。"""
    return TenantResponse(
        tenant_id=tenant.id,
        tenant_code=tenant.code,
        tenant_name=tenant.name,
        status=tenant.status,
    )


def _to_member_response(member) -> TenantMemberResponse:
    """将 IamTenantMember ORM 转换为响应模型。"""
    return TenantMemberResponse(
        member_id=member.id,
        tenant_id=member.tenant_id,
        user_id=member.user_id,
        status=member.status,
    )


def create_iam_router(
    db_dependency: Callable[..., object],
    auth_dependency: Callable[..., object],
) -> APIRouter:
    """创建 IAM 认证与租户管理路由。

    Args:
        db_dependency: 返回 `AsyncSession` 的 FastAPI 依赖。
        auth_dependency: 返回 `AuthContext` 的 FastAPI 认证依赖。

    Returns:
        已绑定数据库和认证依赖的 `APIRouter`。
    """

    router = APIRouter(
        prefix="/iam",
        tags=["IAM 认证与租户管理"],
        dependencies=[Depends(auth_dependency)],
    )

    def get_repo(db: Annotated[AsyncSession, Depends(db_dependency)]) -> IamRepository:
        """构造 IAM 仓储。"""
        return IamRepository(db)

    # ── 当前认证上下文 ────────────────────────────────────

    @router.get("/me", response_model=ApiResponse[AuthContextResponse])
    async def get_me(
        context: Annotated[AuthContext, Depends(get_current_auth_context)],
    ) -> ApiResponse[AuthContextResponse]:
        """获取当前请求的认证与授权上下文。"""
        return ApiResponse(data=AuthContextResponse(
            principal=PrincipalResponse(
                user_id=context.principal.user_id,
                username=context.principal.username,
                is_platform_admin=context.principal.is_platform_admin,
                authenticated=context.principal.authenticated,
            ),
            tenant=TenantContextResponse(
                tenant_id=context.tenant.tenant_id,
                tenant_code=context.tenant.tenant_code,
                tenant_name=context.tenant.tenant_name,
                tenant_status=context.tenant.tenant_status,
            ) if context.tenant else None,
            member_id=context.member_id,
            roles=list(context.roles),
            permissions=list(context.permissions.values),
        ))

    # ── 租户管理 ──────────────────────────────────────────

    @router.post(
        "/tenants",
        response_model=ApiResponse[TenantResponse],
        dependencies=[Depends(require_permission("tenant:create"))],
    )
    async def create_tenant(
        body: TenantCreateRequest,
        repo: Annotated[IamRepository, Depends(get_repo)],
    ) -> ApiResponse[TenantResponse]:
        """创建新租户（需要 tenant:create 权限）。"""
        tenant = await repo.create_tenant(code=body.code, name=body.name)
        return ApiResponse(data=_to_tenant_response(tenant))

    @router.get(
        "/tenants",
        response_model=ApiResponse[list[TenantResponse]],
        dependencies=[Depends(require_permission("tenant:read"))],
    )
    async def list_tenants(
        repo: Annotated[IamRepository, Depends(get_repo)],
    ) -> ApiResponse[list[TenantResponse]]:
        """查询所有租户（需要 tenant:read 权限）。"""
        tenants = await repo.list_tenants()
        return ApiResponse(data=[_to_tenant_response(t) for t in tenants])

    # ── 租户成员管理 ──────────────────────────────────────

    @router.post(
        "/tenants/{tenant_id}/members",
        response_model=ApiResponse[TenantMemberResponse],
        dependencies=[Depends(require_tenant()), Depends(require_permission("tenant:member:add"))],
    )
    async def add_tenant_member(
        tenant_id: int,
        body: TenantMemberAddRequest,
        repo: Annotated[IamRepository, Depends(get_repo)],
    ) -> ApiResponse[TenantMemberResponse]:
        """向租户添加成员（需要 tenant:member:add 权限）。"""
        # 校验租户存在
        tenant = await repo.get_active_tenant(tenant_id)
        if tenant is None:
            raise NotFoundException("租户不存在或已停用")
        # 校验用户存在
        user = await repo.get_active_user(body.user_id)
        if user is None:
            raise NotFoundException("用户不存在或已停用")
        # 校验是否已经是成员
        existing = await repo.get_active_member(user_id=body.user_id, tenant_id=tenant_id)
        if existing is not None:
            raise BadRequestException("该用户已是租户成员")
        member = await repo.add_member(tenant_id=tenant_id, user_id=body.user_id)
        return ApiResponse(data=_to_member_response(member))

    @router.get(
        "/tenants/{tenant_id}/members",
        response_model=ApiResponse[list[TenantMemberResponse]],
        dependencies=[Depends(require_tenant()), Depends(require_permission("tenant:member:read"))],
    )
    async def list_tenant_members(
        tenant_id: int,
        repo: Annotated[IamRepository, Depends(get_repo)],
    ) -> ApiResponse[list[TenantMemberResponse]]:
        """查询租户成员列表（需要 tenant:member:read 权限）。"""
        members = await repo.list_members(tenant_id)
        return ApiResponse(data=[_to_member_response(m) for m in members])

    return router