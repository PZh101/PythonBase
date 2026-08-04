"""IAM 认证上下文服务测试。"""

import asyncio
from dataclasses import dataclass

import pytest

from app.iam.service import IamAuthContextService
from pkg.security.exceptions import TenantAccessDeniedException


@dataclass(frozen=True)
class UserRow:
    """测试用户行。"""

    id: int
    username: str
    is_platform_admin: bool
    is_active: bool


@dataclass(frozen=True)
class TenantRow:
    """测试租户行。"""

    id: int
    code: str
    name: str
    status: str


@dataclass(frozen=True)
class MemberRow:
    """测试成员行。"""

    id: int
    tenant_id: int
    user_id: int
    status: str


class FakeRepository:
    """测试用 IAM 仓储。"""

    async def get_active_user(self, user_id: int):
        """返回启用用户。"""
        return UserRow(id=user_id, username="ada", is_platform_admin=False, is_active=True)

    async def get_active_tenant(self, tenant_id: int):
        """返回启用租户。"""
        return TenantRow(id=tenant_id, code="demo", name="演示租户", status="active")

    async def get_active_member(self, *, user_id: int, tenant_id: int):
        """返回用户在租户内的成员身份。"""
        return MemberRow(id=100, tenant_id=tenant_id, user_id=user_id, status="active")

    async def list_role_codes(self, member_id: int):
        """返回成员角色编码集合。"""
        return frozenset({"owner"})

    async def list_permission_codes(self, member_id: int):
        """返回成员权限编码集合。"""
        return frozenset({"user:create"})


def run(coro):
    """在同步测试中执行异步服务。"""
    return asyncio.run(coro)


def test_load_context_builds_tenant_auth_context() -> None:
    """服务应基于用户和租户加载完整认证上下文。"""
    service = IamAuthContextService(FakeRepository())

    context = run(service.load_context(user_id=1, tenant_id=10))

    assert context.principal.user_id == 1
    assert context.tenant is not None
    assert context.tenant.tenant_id == 10
    assert context.member_id == 100
    assert context.roles == frozenset({"owner"})
    assert context.permissions.has("user:create") is True


def test_load_context_rejects_missing_member() -> None:
    """用户不是租户成员时应拒绝访问。"""

    class MissingMemberRepository(FakeRepository):
        async def get_active_member(self, *, user_id: int, tenant_id: int):
            """模拟用户不是租户成员。"""
            return None

    service = IamAuthContextService(MissingMemberRepository())

    with pytest.raises(TenantAccessDeniedException):
        run(service.load_context(user_id=1, tenant_id=10))
