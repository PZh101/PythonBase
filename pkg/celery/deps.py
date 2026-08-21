"""任务进程级数据库管理器注册表（供 Celery worker 使用）。

Celery worker 是独立进程，需要一套与 HTTP 进程独立的数据库连接管理。
本模块以模块级注册表的形式持有该进程的 :class:`AsyncDatabaseManager`，
由 ``celery_worker.py`` 入口装配一次，任务通过 ``get_task_db_manager()`` 获取。
"""

from pkg.config import DatabaseSettings
from pkg.database import AsyncDatabaseManager, create_manager

_task_db_manager: AsyncDatabaseManager | None = None


def set_task_db_manager(manager: AsyncDatabaseManager) -> None:
    """注册任务使用的数据库管理器。

    Args:
        manager: 进程级共享的数据库管理器。
    """
    global _task_db_manager
    _task_db_manager = manager


def get_task_db_manager() -> AsyncDatabaseManager:
    """返回任务使用的数据库管理器。

    Returns:
        已注册的 :class:`AsyncDatabaseManager`。

    Raises:
        RuntimeError: 尚未通过 ``set_task_db_manager`` 注册。
    """
    if _task_db_manager is None:
        raise RuntimeError(
            "任务数据库管理器未初始化：请在 worker 启动时调用 "
            "pkg.celery.deps.set_task_db_manager / create_task_db_manager"
        )
    return _task_db_manager


def create_task_db_manager(settings: DatabaseSettings) -> AsyncDatabaseManager:
    """按数据库配置创建任务用管理器并注册。

    Args:
        settings: 数据库连接配置。

    Returns:
        已注册的 :class:`AsyncDatabaseManager`。
    """
    manager = create_manager(settings)
    set_task_db_manager(manager)
    return manager


def dispose_task_db_manager() -> None:
    """释放任务用数据库管理器（幂等）。"""
    global _task_db_manager
    manager = _task_db_manager
    _task_db_manager = None
    if manager is not None:
        _dispose_sync(manager)


def _dispose_sync(manager: AsyncDatabaseManager) -> None:
    """在同步上下文中异步释放管理器（asyncio.run 包一层）。"""
    import asyncio

    asyncio.run(manager.dispose())


__all__ = [
    "create_task_db_manager",
    "dispose_task_db_manager",
    "get_task_db_manager",
    "set_task_db_manager",
]
