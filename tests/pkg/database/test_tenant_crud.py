"""租户感知 CRUD 测试。"""

import asyncio
from unittest.mock import AsyncMock, Mock

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from pkg.database.base import Base
from pkg.database.tenant_crud import TenantAwareCrud
from pkg.tenant.mixins import TenantMixin


class TenantUser(TenantMixin, Base):
    """测试用租户业务模型。"""

    __tablename__ = "tenant_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64))


def run(coro):
    """在同步测试中执行异步 CRUD。"""
    return asyncio.run(coro)


def make_session() -> Mock:
    """构造测试用 AsyncSession mock。"""
    session = Mock()
    session.add = Mock()
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    return session


def test_create_injects_tenant_id() -> None:
    """创建字典对象时应自动写入当前租户 ID。"""
    session = make_session()
    crud = TenantAwareCrud(TenantUser)

    created = run(crud.create(session, tenant_id=10, obj_in={"id": 1, "name": "Ada"}))

    assert created.tenant_id == 10
    session.flush.assert_awaited_once()
    session.refresh.assert_awaited_once_with(created)


def test_get_uses_tenant_filter() -> None:
    """按主键查询时必须附加租户过滤。"""
    session = make_session()
    result = Mock()
    result.scalars.return_value.first.return_value = None
    session.execute.return_value = result
    crud = TenantAwareCrud(TenantUser)

    assert run(crud.get(session, tenant_id=10, id=1)) is None

    statement = session.execute.call_args.args[0]
    assert "tenant_id" in str(statement)
