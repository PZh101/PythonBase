"""业务空间与临时授权 API 模型。"""

from typing import Literal

from pkg.common.api import BaseSchema, SafeBigInt, SafeDatetime


WorkspaceRole = Literal["OWNER", "ADMIN", "MEMBER", "GUEST"]
ResourceType = Literal["MENU", "DEPT", "DOC"]


class WorkspaceCreateRequest(BaseSchema):
    """创建业务空间请求。"""

    space_name: str
    space_desc: str | None = None
    owner_id: SafeBigInt
    status: int = 1


class WorkspaceResponse(BaseSchema):
    """业务空间响应。"""

    id: SafeBigInt
    space_name: str
    space_desc: str | None = None
    owner_id: SafeBigInt
    status: int
    created_at: SafeDatetime


class WorkspaceMemberAddRequest(BaseSchema):
    """添加空间成员请求。"""

    user_id: SafeBigInt
    role: WorkspaceRole


class WorkspaceMemberResponse(BaseSchema):
    """空间成员响应。"""

    id: SafeBigInt
    workspace_id: SafeBigInt
    user_id: SafeBigInt
    role: str
    joined_at: SafeDatetime


class TempAuthGrantRequest(BaseSchema):
    """授予临时权限请求。"""

    user_id: SafeBigInt
    resource_type: ResourceType
    resource_id: SafeBigInt
    permission: str
    start_time: SafeDatetime
    end_time: SafeDatetime
    grant_reason: str | None = None


class TempAuthResponse(BaseSchema):
    """临时授权响应。"""

    id: SafeBigInt
    user_id: SafeBigInt
    resource_type: str
    resource_id: SafeBigInt
    permission: str
    start_time: SafeDatetime
    end_time: SafeDatetime
    grant_reason: str | None = None
    created_at: SafeDatetime


class TempAuthCheckResponse(BaseSchema):
    """临时授权校验响应。"""

    allowed: bool

