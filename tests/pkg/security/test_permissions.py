"""权限判断与异常测试。"""

import pytest

from pkg.security.context import AuthContext, PermissionSet, Principal
from pkg.security.exceptions import PermissionDeniedException, TenantRequiredException
from pkg.security.permissions import ensure_permission, ensure_role, ensure_tenant
from pkg.tenant.context import TenantContext


def make_context() -> AuthContext:
    """构造包含租户、角色和权限的测试上下文。"""
    return AuthContext(
        principal=Principal(user_id=1, username="ada"),
        tenant=TenantContext(tenant_id=10),
        member_id=100,
        roles=frozenset({"owner"}),
        permissions=PermissionSet(values=frozenset({"user:create"})),
    )


def test_ensure_permission_allows_existing_permission() -> None:
    """拥有权限时不应抛出异常。"""
    ensure_permission(make_context(), "user:create")


def test_ensure_permission_rejects_missing_permission() -> None:
    """缺少权限时应抛出权限不足异常。"""
    with pytest.raises(PermissionDeniedException):
        ensure_permission(make_context(), "user:delete")


def test_ensure_role_allows_existing_role() -> None:
    """拥有角色时不应抛出异常。"""
    ensure_role(make_context(), "owner")


def test_ensure_tenant_rejects_missing_tenant() -> None:
    """接口要求租户上下文但上下文为空时应被拒绝。"""
    context = AuthContext(
        principal=Principal(user_id=1),
        tenant=None,
        member_id=None,
        roles=frozenset(),
        permissions=PermissionSet(values=frozenset()),
    )

    with pytest.raises(TenantRequiredException):
        ensure_tenant(context)
