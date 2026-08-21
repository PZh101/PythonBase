"""Celery 测试共享 fixture（eager 模式，无需真实 Redis/DB）。"""

import importlib

import pytest

from pkg.celery.app import get_celery_app, reset_celery_app
from pkg.celery.deps import dispose_task_db_manager, set_task_db_manager
from pkg.config import CelerySettings, DatabaseSettings, RuntimeSettings


class StubTransaction:
    """记录进入/退出次数的异步上下文管理器（模拟事务边界）。"""

    def __init__(self, manager: "StubTaskDbManager", name: str) -> None:
        self._manager = manager
        self._name = name

    async def __aenter__(self):
        self._manager.calls.append(f"{self._name}_enter")
        return StubSession()

    async def __aexit__(self, *_exc) -> bool:
        self._manager.calls.append(f"{self._name}_exit")
        return False


class StubSession:
    """最小可用的异步会话桩。"""

    async def execute(self, *_args, **_kwargs):
        return None


class StubTaskDbManager:
    """记录调用序列的数据库管理器桩（不真正连接数据库）。"""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def initialize(self) -> None:
        self.calls.append("initialize")

    def transaction(self) -> StubTransaction:
        return StubTransaction(self, "transaction")

    def session(self) -> StubTransaction:
        return StubTransaction(self, "session")

    async def dispose(self) -> None:
        self.calls.append("dispose")


@pytest.fixture()
def celery_settings() -> CelerySettings:
    """默认启用 eager 模式的测试配置。

    使用 ``result_backend=None``：eager 结果直接保存在进程内，
    无需也避免连接 Redis 存储结果。
    """
    return CelerySettings(
        task_always_eager=True,
        task_store_eager_result=True,
        task_eager_propagates=False,
        result_backend=None,
    )


@pytest.fixture()
def celery_app(celery_settings: CelerySettings):
    """构建并注册测试 Celery 应用；测试结束清空进程级持有器。

    - 先用 :func:`reset_celery_app` 清空，确保测试间隔离。
    - 重载 ``pkg.celery.tasks`` 模块，使其中的示例任务绑定到本测试应用。
    - teardown 再次清空，并重载任务模块绑定回默认应用。
    """
    import pkg.celery.tasks as tasks_module

    reset_celery_app()
    app = get_celery_app(RuntimeSettings(
        database=DatabaseSettings(startup_check=False),
        celery=celery_settings,
    ))
    importlib.reload(tasks_module)
    yield app
    reset_celery_app()
    importlib.reload(tasks_module)


@pytest.fixture()
def task_db_manager():
    """注册一个桩数据库管理器（不真正连接数据库）。

    通过断言 :attr:`StubTaskDbManager.calls` 验证调用序列。
    teardown 调用 :func:`dispose_task_db_manager` 清理注册表。
    """
    manager = StubTaskDbManager()
    set_task_db_manager(manager)
    yield manager
    dispose_task_db_manager()
