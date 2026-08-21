"""Celery 任务数据库管理器注册表与异步执行助手测试。"""

from collections.abc import Awaitable, Callable

import pytest

from pkg.celery.deps import (
    create_task_db_manager,
    dispose_task_db_manager,
    get_task_db_manager,
    set_task_db_manager,
)
from pkg.celery.runner import run_async_in_task
from pkg.config import DatabaseSettings
from pkg.database import AsyncDatabaseManager


def test_get_task_db_manager_raises_before_registration() -> None:
    """未注册管理器时调用应抛出 RuntimeError。"""
    dispose_task_db_manager()
    with pytest.raises(RuntimeError):
        get_task_db_manager()


def test_set_and_get_task_db_manager_roundtrip() -> None:
    """注册后应能取回同一管理器。"""
    dispose_task_db_manager()
    try:
        manager = AsyncDatabaseManager(DatabaseSettings(startup_check=False))
        set_task_db_manager(manager)
        assert get_task_db_manager() is manager
    finally:
        dispose_task_db_manager()


def test_create_task_db_manager_registers_manager() -> None:
    """create_task_db_manager 应创建并注册管理器。"""
    dispose_task_db_manager()
    try:
        manager = create_task_db_manager(DatabaseSettings(startup_check=False))
        assert isinstance(manager, AsyncDatabaseManager)
        assert get_task_db_manager() is manager
    finally:
        dispose_task_db_manager()


def test_dispose_task_db_manager_clears_registry() -> None:
    """dispose 后注册表应清空。"""
    dispose_task_db_manager()
    create_task_db_manager(DatabaseSettings(startup_check=False))
    dispose_task_db_manager()
    with pytest.raises(RuntimeError):
        get_task_db_manager()


def test_dispose_task_db_manager_is_idempotent() -> None:
    """重复 dispose 应安全执行。"""
    dispose_task_db_manager()
    dispose_task_db_manager()


def _routine(value: str) -> Callable[[object], Awaitable[str]]:
    """构造一个接受会话并返回固定值的异步例程。"""

    async def _inner(_db: object) -> str:
        return f"done-{value}"

    return _inner


def test_run_async_in_task_returns_routine_value(task_db_manager) -> None:
    """run_async_in_task 应返回例程值并在事务边界内执行。"""
    result = run_async_in_task(_routine("x"))

    assert result == "done-x"
    assert task_db_manager.calls == [
        "initialize",
        "transaction_enter",
        "transaction_exit",
        "dispose",
    ]


def test_run_async_in_task_readonly_uses_session(task_db_manager) -> None:
    """transaction=False 时应走只读 session 边界。"""
    run_async_in_task(_routine("r"), transaction=False)

    assert task_db_manager.calls == [
        "initialize",
        "session_enter",
        "session_exit",
        "dispose",
    ]


def test_run_async_in_task_disposes_on_error(task_db_manager) -> None:
    """例程抛错时也应释放数据库管理器。"""

    async def _boom(_db: object) -> None:
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        run_async_in_task(_boom)

    assert task_db_manager.calls[-1] == "dispose"
