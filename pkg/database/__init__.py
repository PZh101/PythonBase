"""Async database infrastructure exports."""

from pkg.database.base import Base
from pkg.database.crud import BaseCrud
from pkg.database.dependencies import (
    create_db_session_dependency,
    create_readonly_db_session_dependency,
)
from pkg.database.dialects import get_async_driver, get_async_drivername
from pkg.database.exceptions import (
    DatabaseDriverNotInstalledError,
    DatabaseError,
    DatabaseInitializationError,
    DatabaseNotInitializedError,
    DatabaseUrlError,
    MissingDatabaseParameterError,
    UnsupportedDatabaseTypeError,
)
from pkg.database.manager import AsyncDatabaseManager, create_manager
from pkg.database.tenant_crud import TenantAwareCrud
from pkg.database.url import (
    build_async_database_url,
    build_connect_args,
    describe_database,
)

__all__ = [
    "AsyncDatabaseManager",
    "Base",
    "BaseCrud",
    "DatabaseDriverNotInstalledError",
    "DatabaseError",
    "DatabaseInitializationError",
    "DatabaseNotInitializedError",
    "DatabaseUrlError",
    "MissingDatabaseParameterError",
    "TenantAwareCrud",
    "UnsupportedDatabaseTypeError",
    "build_async_database_url",
    "build_connect_args",
    "create_db_session_dependency",
    "create_manager",
    "create_readonly_db_session_dependency",
    "describe_database",
    "get_async_driver",
    "get_async_drivername",
]
