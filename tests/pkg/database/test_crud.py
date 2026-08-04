"""数据库 CRUD 事务语义和旧导入路径兼容测试。"""

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import BaseModel as PydanticBaseModel
from sqlalchemy import Integer
from sqlalchemy.orm import Mapped, mapped_column

from pkg.common.db_crud import BaseCrud as LegacyBaseCrud
from pkg.common.db_crud import Base as LegacyBase
from pkg.database.base import Base
from pkg.database.crud import BaseCrud


class User(Base):
    """测试用 ORM 模型。"""

    __tablename__ = "test_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str]


class UserPatch(PydanticBaseModel):
    """测试用 Pydantic 更新模型。"""

    name: str = "Grace"


def run(coro):
    """在同步 pytest 中执行异步 CRUD 调用。"""
    return asyncio.run(coro)


def make_session() -> Mock:
    """构造贴近 AsyncSession 的 mock：同步方法同步，异步方法可 await。"""
    session = Mock()
    session.add = Mock()
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


def test_legacy_import_reexports_new_crud_and_base() -> None:
    """迁移期旧导入路径应继续可用。"""
    assert LegacyBaseCrud is BaseCrud
    assert LegacyBase is Base


def test_create_flushes_and_refreshes_without_commit() -> None:
    """create() 应刷新数据库生成值，但不自行提交事务。"""
    session = make_session()
    crud = BaseCrud(User)

    created = run(crud.create(session, {"id": 1, "name": "Ada"}))

    assert created.id == 1
    assert created.name == "Ada"
    session.add.assert_called_once_with(created)
    session.flush.assert_awaited_once()
    session.refresh.assert_awaited_once_with(created)
    session.commit.assert_not_called()
    session.rollback.assert_not_called()


def test_create_accepts_pydantic_model() -> None:
    """create() 应继续兼容 Pydantic 输入。"""
    session = make_session()
    crud = BaseCrud(User)

    created = run(crud.create(session, UserPatch(name="Linus")))

    assert created.name == "Linus"
    session.flush.assert_awaited_once()
    session.refresh.assert_awaited_once_with(created)


def test_update_returns_none_when_missing_and_does_not_commit() -> None:
    """目标记录不存在时 update() 返回 None 且不提交。"""
    session = make_session()
    result = Mock()
    result.scalars.return_value.first.return_value = None
    session.execute.return_value = result
    crud = BaseCrud(User)

    updated = run(crud.update(session, 404, {"name": "Grace"}))

    assert updated is None
    session.flush.assert_not_called()
    session.refresh.assert_not_called()
    session.commit.assert_not_called()


def test_update_flushes_and_refreshes_existing_object_without_commit() -> None:
    """update() 应修改对象并 flush/refresh，不自行提交。"""
    session = make_session()
    user = User(id=1, name="Ada")
    result = Mock()
    result.scalars.return_value.first.return_value = user
    session.execute.return_value = result
    crud = BaseCrud(User)

    updated = run(crud.update(session, 1, UserPatch(name="Grace"), exclude_unset=True))

    assert updated is user
    assert user.name == "Grace"
    session.add.assert_called_once_with(user)
    session.flush.assert_awaited_once()
    session.refresh.assert_awaited_once_with(user)
    session.commit.assert_not_called()


def test_delete_flushes_without_commit() -> None:
    """delete_by_id() 应执行删除并 flush，不自行提交。"""
    session = make_session()
    result = Mock(rowcount=1)
    session.execute.return_value = result
    crud = BaseCrud(User)

    deleted = run(crud.delete_by_id(session, 1))

    assert deleted is True
    session.flush.assert_awaited_once()
    session.commit.assert_not_called()


def test_invalid_primary_key_is_rejected() -> None:
    """主键类型不匹配应继续被严格拒绝。"""
    crud = BaseCrud(User)

    with pytest.raises(ValueError):
        run(crud.get(make_session(), "not-an-int"))
