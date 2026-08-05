"""企业组织与权限服务测试。"""

import asyncio
from dataclasses import dataclass

import pytest

from app.system.service import SystemService
from pkg.common.exceptions import BadRequestException


@dataclass(frozen=True)
class RoleRow:
    """测试角色行。"""

    id: int
    role_key: str


@dataclass(frozen=True)
class UserDeptRow:
    """测试用户部门关联行。"""

    dept_id: int
    is_primary: int


class FakeSystemRepository:
    """测试用系统权限仓储。"""

    async def get_user(self, user_id: int):
        """返回测试用户。"""
        return object()

    async def get_dept(self, dept_id: int):
        """返回测试部门。"""
        return object()

    async def get_role(self, role_id: int):
        """返回测试角色。"""
        return object()

    async def get_menu(self, menu_id: int):
        """返回测试菜单。"""
        return object()

    async def assign_user_dept(self, *, user_id: int, dept_id: int, is_primary: int):
        """返回测试关联关系。"""
        return object()

    async def list_user_depts(self, user_id: int):
        """返回用户部门列表。"""
        return [UserDeptRow(dept_id=10, is_primary=1), UserDeptRow(dept_id=20, is_primary=0)]

    async def list_user_roles(self, user_id: int):
        """返回用户角色列表。"""
        return [RoleRow(id=100, role_key="admin")]

    async def list_permission_codes_by_role_ids(self, role_ids: list[int]):
        """返回权限编码列表。"""
        return ["system:user:add", "system:user:add", "system:role:list"]


def run(coro):
    """在同步测试中执行异步服务。"""
    return asyncio.run(coro)


def test_assign_user_dept_rejects_invalid_primary_flag() -> None:
    """用户关联部门时 is_primary 只能为 0 或 1。"""
    service = SystemService(FakeSystemRepository())

    with pytest.raises(BadRequestException):
        run(service.assign_user_dept(user_id=1, dept_id=10, is_primary=2))


def test_user_access_profile_deduplicates_permissions() -> None:
    """用户权限画像应聚合部门、角色并去重权限编码。"""
    service = SystemService(FakeSystemRepository())

    profile = run(service.get_user_access_profile(1))

    assert profile.primary_dept_id == 10
    assert profile.dept_ids == [10, 20]
    assert profile.role_ids == [100]
    assert profile.permissions == ["system:role:list", "system:user:add"]

