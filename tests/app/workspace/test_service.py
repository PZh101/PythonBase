"""业务空间与临时授权服务测试。"""

import asyncio
from datetime import datetime, timedelta

import pytest

from app.workspace.schemas import TempAuthGrantRequest
from app.workspace.service import WorkspaceService
from pkg.common.exceptions import BadRequestException


class FakeWorkspaceRepository:
    """测试用业务空间仓储。"""

    async def get_workspace(self, workspace_id: int):
        """返回测试业务空间。"""
        return object()

    async def add_member(self, *, workspace_id: int, user_id: int, role: str):
        """返回测试成员。"""
        return object()

    async def grant_temp_auth(self, data: dict):
        """返回测试临时授权。"""
        return data

    async def find_valid_temp_auth(self, **kwargs):
        """返回命中的测试临时授权。"""
        return object()


def run(coro):
    """在同步测试中执行异步服务。"""
    return asyncio.run(coro)


def test_add_member_rejects_invalid_workspace_role() -> None:
    """空间成员角色必须属于允许枚举。"""
    service = WorkspaceService(FakeWorkspaceRepository())

    with pytest.raises(BadRequestException):
        run(service.add_member(workspace_id=1, user_id=10, role="UNKNOWN"))


def test_grant_temp_auth_rejects_invalid_time_range() -> None:
    """临时授权结束时间必须晚于开始时间。"""
    service = WorkspaceService(FakeWorkspaceRepository())
    now = datetime.utcnow()
    body = TempAuthGrantRequest(
        user_id=1,
        resource_type="MENU",
        resource_id=10,
        permission="system:user:add",
        start_time=now,
        end_time=now - timedelta(seconds=1),
    )

    with pytest.raises(BadRequestException):
        run(service.grant_temp_auth(body))


def test_has_valid_temp_auth_returns_true_when_repository_hits() -> None:
    """仓储命中有效临时授权时应返回 True。"""
    service = WorkspaceService(FakeWorkspaceRepository())

    assert run(service.has_valid_temp_auth(
        user_id=1,
        resource_type="MENU",
        resource_id=10,
        permission="system:user:add",
    )) is True

