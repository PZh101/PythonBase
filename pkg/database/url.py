"""SQLAlchemy URL and connection argument helpers."""

from sqlalchemy.engine import URL

from pkg.config import DatabaseSettings, DatabaseType

from pkg.database.dialects import get_async_drivername, normalize_database_type
from pkg.database.exceptions import DatabaseUrlError, MissingDatabaseParameterError


def _require_text(value: str, field_name: str) -> str:
    if not value.strip():
        raise MissingDatabaseParameterError(f"Database {field_name} is required")
    return value


def build_async_database_url(settings: DatabaseSettings) -> URL:
    """Build a SQLAlchemy async URL without manual credential escaping."""
    try:
        return URL.create(
            drivername=get_async_drivername(settings.type),
            username=_require_text(settings.username, "username"),
            password=settings.password,
            host=_require_text(settings.host, "host"),
            port=settings.port,
            database=_require_text(settings.database, "database"),
        )
    except MissingDatabaseParameterError:
        raise
    except Exception as exc:
        raise DatabaseUrlError(
            f"Failed to build database URL for {describe_database(settings)}"
        ) from exc


def build_connect_args(settings: DatabaseSettings) -> dict[str, float]:
    """Build driver-specific connect timeout arguments."""
    database_type = normalize_database_type(settings.type)
    timeout = float(settings.connect_timeout)
    if database_type is DatabaseType.POSTGRESQL:
        return {"timeout": timeout}
    return {"connect_timeout": timeout}


def describe_database(settings: DatabaseSettings) -> str:
    """Return a credential-free connection description for logs and errors."""
    database_type = normalize_database_type(settings.type)
    return (
        f"{database_type.value}://"
        f"{settings.host}:{settings.port}/{settings.database}"
    )
