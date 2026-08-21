"""同步 Celery 任务内执行异步数据库逻辑的辅助工具。"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from pkg.celery.deps import get_task_db_manager

T = TypeVar("T")


def run_async_in_task(
    routine: Callable[[AsyncSession], Awaitable[T]],
    *,
    transaction: bool = True,
) -> T:
    """在同步 Celery 任务中运行一段异步数据库例程。

    复用任务进程内唯一的 :class:`AsyncDatabaseManager`：不新建连接池、不创建额外 engine。
    每次调用通过 ``asyncio.run`` 开启一个独立事件循环执行
    ``initialize()``（幂等）+ ``transaction()``/``session()`` 事务边界。

    关键点:
        异步 engine 绑定创建它的事件循环，而 ``asyncio.run`` 每次都会新建事件循环，
        因此例程结束后必须 ``dispose()`` 释放当前 engine，下一次任务才能在新循环上重建。

    Args:
        routine: 接收 ``AsyncSession`` 的协程函数。
        transaction: 为 ``True`` 时在 ``transaction()`` 事务边界内执行（写路径，
            结束自动提交）；为 ``False`` 时在 ``session()`` 只读边界内执行。

    Returns:
        例程的返回值。

    使用方式:
        在 ``@celery.task`` 装饰的同步任务函数内调用：

            def task(self, user_id: int) -> None:
                def _write(db: AsyncSession) -> None:
                    ...  # 写操作，结束由 transaction() 提交

                run_async_in_task(_write)

    注意:
        本函数不应在已运行的异步上下文中调用（例如从 FastAPI 依赖或 async 任务内部）。
    """
    manager = get_task_db_manager()

    async def _execute() -> T:
        await manager.initialize()
        try:
            if transaction:
                async with manager.transaction() as session:
                    return await routine(session)
            async with manager.session() as session:
                return await routine(session)
        finally:
            await manager.dispose()

    return asyncio.run(_execute())


__all__ = ["run_async_in_task"]
