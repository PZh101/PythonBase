"""FastAPI dependency adapters for database sessions."""

from collections.abc import AsyncIterator, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from pkg.database.manager import AsyncDatabaseManager


def create_db_session_dependency(
    manager: AsyncDatabaseManager,
) -> Callable[[], AsyncIterator[AsyncSession]]:
    """Create a transaction-scoped Session dependency for write endpoints."""

    async def get_db_session() -> AsyncIterator[AsyncSession]:
        async with manager.transaction() as session:
            yield session

    return get_db_session


def create_readonly_db_session_dependency(
    manager: AsyncDatabaseManager,
) -> Callable[[], AsyncIterator[AsyncSession]]:
    """Create a non-committing Session dependency for read endpoints."""

    async def get_readonly_db_session() -> AsyncIterator[AsyncSession]:
        async with manager.session() as session:
            yield session

    return get_readonly_db_session
