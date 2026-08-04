"""安全上下文模型测试。"""

from dataclasses import FrozenInstanceError

import pytest

from pkg.security.context import AuthContext, PermissionSet, Principal
from pkg.tenant.context import TenantContext


def test_permission_set_supports_exact_permissions() -> None:
    """权限集合应支持精确权限判断。"""
    permissions = PermissionSet(values=frozenset({"user:read", "role:assign"}))

    assert permissions.has("user:read") is True
    assert permissions.has("user:create") is False


def test_auth_context_is_immutable() -> None:
    """认证上下文应不可原地修改，避免请求处理中被污染。"""
    context = AuthContext(
        principal=Principal(user_id=1, username="ada"),
        tenant=TenantContext(tenant_id=10),
        member_id=100,
        roles=frozenset({"owner"}),
        permissions=PermissionSet(values=frozenset({"user:create"})),
    )

    with pytest.raises(FrozenInstanceError):
        context.member_id = 200


def test_platform_admin_flag_comes_from_principal() -> None:
    """平台管理员标记应来自认证主体。"""
    context = AuthContext(
        principal=Principal(user_id=1, username="root", is_platform_admin=True),
        tenant=None,
        member_id=None,
        roles=frozenset(),
        permissions=PermissionSet(values=frozenset()),
    )

    assert context.is_platform_admin is True
