"""IAM API 请求与响应模型。"""

from pkg.common.api import BaseSchema, SafeBigInt


class TenantResponse(BaseSchema):
    """租户响应模型。"""

    tenant_id: SafeBigInt
    tenant_code: str
    tenant_name: str
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
