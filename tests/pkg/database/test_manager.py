"""异步数据库管理器和 FastAPI 依赖适配器测试。"""

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from pkg.config import DatabaseSettings
from pkg.database.dependencies import (
    create_db_session_dependency,
    create_readonly_db_session_dependency,
)
from pkg.database.exceptions import (
    DatabaseDriverNotInstalledError,
    DatabaseNotInitializedError,
)
from pkg.database.manager import AsyncDatabaseManager


def run(coro):
    """在同步 pytest 中执行异步场景。"""
    return asyncio.run(coro)


def patch_driver_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    """让 manager 单测不依赖真实 asyncmy/asyncpg 安装。"""
    monkeypatch.setattr("pkg.database.manager.find_spec", Mock(return_value=object()))


def make_session() -> Mock:
    """构造贴近 AsyncSession 的 mock：同步方法同步，异步方法可 await。"""
    session = Mock()
    session.add = Mock()
    session.begin = Mock(return_value=TransactionContext())
    session.get_transaction = Mock(return_value=None)
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    return session


class TransactionContext:
    """测试用 AsyncSession.begin() 上下文。"""

    def __init__(self) -> None:
        self.entered = False
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self) -> None:
        self.entered = True

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if exc_type is None:
            self.committed = True
        else:
            self.rolled_back = True


class BeginContext:
    """测试用异步 Engine.begin() 上下文。"""

    def __init__(self, connection: Mock | None = None, error: Exception | None = None) -> None:
        self.connection = connection or AsyncMock()
        self.error = error

    async def __aenter__(self):
        if self.error is not None:
            raise self.error
        return self.connection

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


def test_initialize_creates_engine_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """重复初始化不应重复创建 Engine 或 SessionFactory。"""
    patch_driver_installed(monkeypatch)
    engine = Mock()
    engine.dispose = AsyncMock()
    create_engine = Mock(return_value=engine)
    create_factory = Mock(return_value=Mock())
    monkeypatch.setattr("pkg.database.manager.create_async_engine", create_engine)
    monkeypatch.setattr("pkg.database.manager.async_sessionmaker", create_factory)

    manager = AsyncDatabaseManager(DatabaseSettings(startup_check=False))
    run(manager.initialize())
    run(manager.initialize())

    assert manager.engine is engine
    assert create_engine.call_count == 1
    assert create_factory.call_count == 1


def test_initialize_passes_pool_and_connect_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """初始化 Engine 时应传入 SQLAlchemy 池参数和驱动连接参数。"""
    patch_driver_installed(monkeypatch)
    engine = Mock()
    monkeypatch.setattr("pkg.database.manager.create_async_engine", Mock(return_value=engine))
    monkeypatch.setattr("pkg.database.manager.async_sessionmaker", Mock(return_value=Mock()))

    settings = DatabaseSettings(
        connect_timeout=4,
        echo=True,
        startup_check=False,
        pool={"size": 2, "max_overflow": 3, "timeout": 5, "recycle": 9, "pre_ping": False},
    )
    manager = AsyncDatabaseManager(settings)
    run(manager.initialize())

    kwargs = manager.engine_factory.call_args.kwargs
    assert kwargs["echo"] is True
    assert kwargs["connect_args"] == {"connect_timeout": 4.0}
    assert kwargs["pool_size"] == 2
    assert kwargs["max_overflow"] == 3
    assert kwargs["pool_timeout"] == 5
    assert kwargs["pool_recycle"] == 9
    assert kwargs["pool_pre_ping"] is False


def test_startup_check_executes_select_one(monkeypatch: pytest.MonkeyPatch) -> None:
    """开启 startup_check 时初始化应执行连通性检查。"""
    patch_driver_installed(monkeypatch)
    connection = AsyncMock()
    engine = Mock()
    engine.begin.return_value = BeginContext(connection)
    monkeypatch.setattr("pkg.database.manager.create_async_engine", Mock(return_value=engine))
    monkeypatch.setattr("pkg.database.manager.async_sessionmaker", Mock(return_value=Mock()))

    run(AsyncDatabaseManager(DatabaseSettings(startup_check=True)).initialize())

    connection.execute.assert_awaited_once()


def test_initialize_disposes_engine_when_startup_check_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """初始化失败时应释放已经创建的连接池。"""
    patch_driver_installed(monkeypatch)
    engine = Mock()
    engine.begin.return_value = BeginContext(error=RuntimeError("cannot connect"))
    engine.dispose = AsyncMock()
    monkeypatch.setattr("pkg.database.manager.create_async_engine", Mock(return_value=engine))
    monkeypatch.setattr("pkg.database.manager.async_sessionmaker", Mock(return_value=Mock()))

    manager = AsyncDatabaseManager(DatabaseSettings(startup_check=True))
    with pytest.raises(Exception):
        run(manager.initialize())

    engine.dispose.assert_awaited_once()
    assert manager.engine is None


def test_initialize_raises_when_driver_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真实初始化前应给出清晰的驱动缺失异常。"""
    monkeypatch.setattr("pkg.database.manager.find_spec", Mock(return_value=None))
    manager = AsyncDatabaseManager(DatabaseSettings(startup_check=False))

    with pytest.raises(DatabaseDriverNotInstalledError):
        run(manager.initialize())


def test_session_requires_initialization() -> None:
    """未初始化时不应悄悄创建 Session。"""
    manager = AsyncDatabaseManager(DatabaseSettings(startup_check=False))

    async def scenario() -> None:
        with pytest.raises(DatabaseNotInitializedError):
            async with manager.session():
                pass

    run(scenario())


def test_session_rolls_back_open_transaction_on_exception() -> None:
    """普通 Session 异常退出时应清理尚未结束的事务状态。"""
    session = make_session()
    transaction = Mock()
    transaction.is_active = True
    session.get_transaction.return_value = transaction
    manager = AsyncDatabaseManager(DatabaseSettings(startup_check=False))
    manager._session_factory = Mock(return_value=session)

    async def scenario() -> None:
        with pytest.raises(RuntimeError):
            async with manager.session() as yielded:
                assert yielded is session
                raise RuntimeError("boom")

    run(scenario())

    session.rollback.assert_awaited_once()
    session.close.assert_awaited_once()
    session.commit.assert_not_called()


def test_transaction_commits_and_rolls_back() -> None:
    """事务 Session 正常退出提交，异常退出回滚，并始终关闭。"""
    first_session = make_session()
    second_session = make_session()
    first_context = first_session.begin.return_value
    second_context = second_session.begin.return_value
    factory = Mock(side_effect=[first_session, second_session])
    manager = AsyncDatabaseManager(DatabaseSettings(startup_check=False))
    manager._session_factory = factory

    async def scenario() -> None:
        async with manager.transaction() as yielded:
            assert yielded is first_session

        with pytest.raises(RuntimeError):
            async with manager.transaction() as yielded:
                assert yielded is second_session
                raise RuntimeError("boom")

    run(scenario())

    assert first_context.entered is True
    assert first_context.committed is True
    assert first_context.rolled_back is False
    first_session.close.assert_awaited_once()
    assert second_context.entered is True
    assert second_context.committed is False
    assert second_context.rolled_back is True
    second_session.close.assert_awaited_once()


def test_dispose_is_idempotent() -> None:
    """dispose() 应能重复调用，便于部分启动失败和测试清理。"""
    engine = Mock()
    engine.dispose = AsyncMock()
    manager = AsyncDatabaseManager(DatabaseSettings(startup_check=False))
    manager._engine = engine
    manager._session_factory = Mock()

    run(manager.dispose())
    run(manager.dispose())

    engine.dispose.assert_awaited_once()
    assert manager.engine is None
    assert manager.session_factory is None


def test_dependencies_delegate_to_manager_transaction_and_session() -> None:
    """FastAPI 依赖应只是 manager 上下文管理器的薄适配层。"""
    manager = AsyncDatabaseManager(DatabaseSettings(startup_check=False))
    tx_session = object()
    read_session = object()

    class Ctx:
        def __init__(self, value: object) -> None:
            self.value = value

        async def __aenter__(self) -> object:
            return self.value

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    manager.transaction = Mock(return_value=Ctx(tx_session))  # type: ignore[method-assign]
    manager.session = Mock(return_value=Ctx(read_session))  # type: ignore[method-assign]

    async def scenario() -> None:
        dep = create_db_session_dependency(manager)
        readonly_dep = create_readonly_db_session_dependency(manager)
        assert await dep().__anext__() is tx_session
        assert await readonly_dep().__anext__() is read_session

    run(scenario())


def test_dependency_factory_works_with_fastapi_depends() -> None:
    """工厂返回值应可直接传给 FastAPI Depends。"""
    manager = AsyncDatabaseManager(DatabaseSettings(startup_check=False))
    tx_session = object()

    class Ctx:
        async def __aenter__(self) -> object:
            return tx_session

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    manager.transaction = Mock(return_value=Ctx())  # type: ignore[method-assign]

    app = FastAPI()
    dependency = create_db_session_dependency(manager)

    @app.get("/database/session")
    async def read_session(session=Depends(dependency)):
        return {"same_session": session is tx_session}

    client = TestClient(app)
    response = client.get("/database/session")

    assert response.status_code == 200
    assert response.json() == {"same_session": True}
