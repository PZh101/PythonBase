"""IAM API 请求与响应模型。"""

from pydantic import Field

from pkg.common.api import BaseSchema, SafeBigInt, SafeDatetime


class LoginRequest(BaseSchema):
    """账号密码登录请求。"""

    username: str = Field(..., min_length=1, max_length=64, description="登录账号")
    password: str = Field(..., min_length=1, max_length=128, description="明文密码，仅用于登录请求，传输需 TLS")


class RefreshTokenRequest(BaseSchema):
    """刷新访问令牌请求。"""

    refresh_token: str = Field(..., min_length=1, description="刷新令牌")


class ChangePasswordRequest(BaseSchema):
    """修改当前用户密码请求。"""

    old_password: str = Field(..., min_length=1, max_length=128, description="旧密码")
    new_password: str = Field(..., min_length=8, max_length=128, description="新密码，至少 8 位")


class TokenResponse(BaseSchema):
    """登录或刷新后返回的 token 响应。"""

    access_token: str = Field(..., description="访问令牌")
    refresh_token: str = Field(..., description="刷新令牌")
    token_type: str = Field(default="Bearer", description="token 类型，固定 Bearer")
    access_expires_in: int = Field(..., ge=0, description="访问令牌剩余有效期（秒）")
    refresh_expires_in: int = Field(..., ge=0, description="刷新令牌剩余有效期（秒）")
    user_id: SafeBigInt = Field(..., description="用户 ID")
    username: str | None = Field(default=None, description="登录账号")
    token_version: int = Field(..., ge=0, description="凭证版本号")


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
