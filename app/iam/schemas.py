"""IAM API 请求与响应模型。"""

from pydantic import Field

from pkg.common.api import BaseSchema, SafeBigInt


class TenantCreateRequest(BaseSchema):
    """创建租户请求。"""

    code: str = Field(..., description="租户编码，全局唯一", max_length=64)
    name: str = Field(..., description="租户名称", max_length=128)


class TenantResponse(BaseSchema):
    """租户响应模型。"""

    tenant_id: SafeBigInt
    tenant_code: str
    tenant_name: str
    status: str


class TenantMemberAddRequest(BaseSchema):
    """添加租户成员请求。"""

    user_id: SafeBigInt = Field(..., description="用户 ID")


class TenantMemberResponse(BaseSchema):
    """租户成员响应模型。"""

    member_id: SafeBigInt
    tenant_id: SafeBigInt
    user_id: SafeBigInt
    status: str


class RoleResponse(BaseSchema):
    """角色响应模型。"""

    role_id: SafeBigInt
    tenant_id: SafeBigInt
    code: str
    name: str


class PermissionResponse(BaseSchema):
    """权限响应模型。"""

    permission_id: SafeBigInt
    code: str
    name: str


class PrincipalResponse(BaseSchema):
    """已认证主体响应模型。"""

    user_id: SafeBigInt
    username: str | None
    is_platform_admin: bool
    authenticated: bool


class TenantContextResponse(BaseSchema):
    """租户上下文响应模型。"""

    tenant_id: SafeBigInt
    tenant_code: str | None
    tenant_name: str | None
    tenant_status: str | None


class AuthContextResponse(BaseSchema):
    """当前请求的认证与授权上下文响应模型。"""

    principal: PrincipalResponse
    tenant: TenantContextResponse | None
    member_id: SafeBigInt | None
    roles: list[str]
    permissions: list[str]
