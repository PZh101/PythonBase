"""Database type to SQLAlchemy async dialect mapping."""

from pkg.config import DatabaseType

from pkg.database.exceptions import UnsupportedDatabaseTypeError


_ASYNC_DRIVERS: dict[DatabaseType, str] = {
    DatabaseType.MYSQL: "asyncmy",
    DatabaseType.POSTGRESQL: "asyncpg",
}


def normalize_database_type(database_type: DatabaseType | str) -> DatabaseType:
    """Normalize a raw database type into the config enum."""
    try:
        return DatabaseType(database_type)
    except ValueError as exc:
        raise UnsupportedDatabaseTypeError(
            f"Unsupported database type: {database_type}"
        ) from exc


def get_async_driver(database_type: DatabaseType | str) -> str:
    """Return the async driver name for a supported database type."""
    normalized = normalize_database_type(database_type)
    try:
        return _ASYNC_DRIVERS[normalized]
    except KeyError as exc:
        raise UnsupportedDatabaseTypeError(
            f"Unsupported database type: {database_type}"
        ) from exc


def get_async_drivername(database_type: DatabaseType | str) -> str:
    """Return the SQLAlchemy async drivername."""
    normalized = normalize_database_type(database_type)
    return f"{normalized.value}+{get_async_driver(normalized)}"
