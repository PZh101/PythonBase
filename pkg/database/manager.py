"""Async SQLAlchemy engine and session lifecycle management."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from importlib.util import find_spec

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from pkg.config import DatabaseSettings

from pkg.database.dialects import get_async_driver
from pkg.database.exceptions import (
    DatabaseDriverNotInstalledError,
    DatabaseInitializationError,
    DatabaseNotInitializedError,
)
from pkg.database.url import (
    build_async_database_url,
    build_connect_args,
    describe_database,
)


class AsyncDatabaseManager:
    """Owns one async Engine and its Session factory for a process."""

    def __init__(self, settings: DatabaseSettings) -> None:
        self.settings = settings
        self.engine_factory = create_async_engine
        self.session_factory_builder = async_sessionmaker
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    @property
    def engine(self) -> AsyncEngine | None:
        """Return the initialized async Engine, if any."""
        return self._engine

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession] | None:
        """Return the initialized async session factory, if any."""
        return self._session_factory

    async def initialize(self) -> None:
        """Create the async Engine and SessionFactory once."""
        if self._engine is not None and self._session_factory is not None:
            return

        try:
            self._ensure_driver_installed()
            engine = self.engine_factory(
                build_async_database_url(self.settings),
                echo=self.settings.echo,
                connect_args=build_connect_args(self.settings),
                pool_size=self.settings.pool.size,
                max_overflow=self.settings.pool.max_overflow,
                pool_timeout=self.settings.pool.timeout,
                pool_recycle=self.settings.pool.recycle,
                pool_pre_ping=self.settings.pool.pre_ping,
            )
            self._engine = engine
            self._session_factory = self.session_factory_builder(
                bind=engine,
                class_=AsyncSession,
                expire_on_commit=False,
                autoflush=False,
            )
            if self.settings.startup_check:
                await self.check_connection()
        except DatabaseInitializationError:
            await self.dispose()
            raise
        except ModuleNotFoundError as exc:
            await self.dispose()
            raise DatabaseDriverNotInstalledError(
                f"Database driver is not installed for {describe_database(self.settings)}"
            ) from exc
        except Exception as exc:
            await self.dispose()
            raise DatabaseInitializationError(
                f"Failed to initialize database for {describe_database(self.settings)}"
            ) from exc

    async def check_connection(self) -> None:
        """Execute a lightweight connectivity check."""
        if self._engine is None:
            raise DatabaseNotInitializedError("Database manager is not initialized")

        try:
            async with self._engine.begin() as connection:
                await connection.execute(text("SELECT 1"))
        except SQLAlchemyError as exc:
            raise DatabaseInitializationError(
                f"Database startup check failed for {describe_database(self.settings)}"
            ) from exc

    async def dispose(self) -> None:
        """Dispose the Engine connection pool; safe to call repeatedly."""
        engine = self._engine
        self._engine = None
        self._session_factory = None
        if engine is not None:
            await engine.dispose()

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession]:
        """Yield a Session without automatically committing."""
        session = self._create_session()
        try:
            yield session
        except Exception:
            await self._rollback_active_transaction(session)
            raise
        finally:
            await session.close()

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[AsyncSession]:
        """Yield a Session inside a transaction boundary."""
        session = self._create_session()
        try:
            async with session.begin():
                yield session
        finally:
            await session.close()

    def _create_session(self) -> AsyncSession:
        if self._session_factory is None:
            raise DatabaseNotInitializedError("Database manager is not initialized")
        return self._session_factory()

    async def _rollback_active_transaction(self, session: AsyncSession) -> None:
        transaction = session.get_transaction()
        if transaction is not None and transaction.is_active:
            await session.rollback()

    def _ensure_driver_installed(self) -> None:
        driver = get_async_driver(self.settings.type)
        if find_spec(driver) is None:
            raise DatabaseDriverNotInstalledError(
                f"Database driver '{driver}' is not installed for "
                f"{describe_database(self.settings)}"
            )


def create_manager(settings: DatabaseSettings) -> AsyncDatabaseManager:
    """Create an async database manager for application wiring."""
    return AsyncDatabaseManager(settings)
