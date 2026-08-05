"""企业组织、用户、角色和资源权限 API 模型。"""

from typing import Any, Literal

from pkg.common.api import BaseSchema, SafeBigInt, SafeDatetime


class DeptCreateRequest(BaseSchema):
    """创建部门请求。"""

    parent_id: SafeBigInt = 0
    dept_name: str
    dept_path: str
    dept_tags: list[str] | None = None
    sort_order: int = 0
    status: int = 1


class DeptResponse(BaseSchema):
    """部门响应。"""

    id: SafeBigInt
    parent_id: SafeBigInt
    dept_name: str
    dept_path: str
    dept_tags: list[str] | None = None
    sort_order: int
    status: int
    created_at: SafeDatetime
    updated_at: SafeDatetime


class UserCreateRequest(BaseSchema):
    """创建用户请求。"""

    username: str
    real_name: str
    status: int = 1


class UserResponse(BaseSchema):
    """用户响应。"""

    id: SafeBigInt
    username: str
    real_name: str
    status: int
    created_at: SafeDatetime
    updated_at: SafeDatetime


class UserDeptAssignRequest(BaseSchema):
    """用户关联部门请求。"""

    dept_id: SafeBigInt
    is_primary: int = 0


class RoleCreateRequest(BaseSchema):
    """创建角色请求。"""

    role_name: str
    role_key: str
    data_scope: int = 1
    data_scope_rule: dict[str, Any] | list[Any] | None = None
    status: int = 1


class RoleResponse(BaseSchema):
    """角色响应。"""

    id: SafeBigInt
    role_name: str
    role_key: str
    data_scope: int
    data_scope_rule: dict[str, Any] | list[Any] | None = None
    status: int
    created_at: SafeDatetime
    updated_at: SafeDatetime


class MenuCreateRequest(BaseSchema):
    """创建菜单或资源请求。"""

    parent_id: SafeBigInt = 0
    menu_name: str
    menu_type: Literal["M", "C", "F"]
    permission: str | None = None
    path: str | None = None
    sort_order: int = 0
    status: int = 1


class MenuResponse(BaseSchema):
    """菜单或资源响应。"""

    id: SafeBigInt
    parent_id: SafeBigInt
    menu_name: str
    menu_type: str
    permission: str | None = None
    path: str | None = None
    sort_order: int
    status: int


class RoleMenuAssignRequest(BaseSchema):
    """角色关联菜单请求。"""

    menu_id: SafeBigInt


class UserRoleAssignRequest(BaseSchema):
    """用户关联角色请求。"""

    role_id: SafeBigInt


class RoleDeptAssignRequest(BaseSchema):
    """角色关联自定义数据权限部门请求。"""

    dept_id: SafeBigInt


class RelationResponse(BaseSchema):
    """关联关系响应。"""

    id: SafeBigInt


class UserAccessProfileResponse(BaseSchema):
    """用户权限画像响应。"""

    user_id: SafeBigInt
    dept_ids: list[SafeBigInt]
    primary_dept_id: SafeBigInt | None = None
    role_ids: list[SafeBigInt]
    role_keys: list[str]
    permissions: list[str]
