"""Database layer exceptions."""


class DatabaseError(Exception):
    """Base class for database layer errors."""


class DatabaseInitializationError(DatabaseError):
    """Database infrastructure failed to initialize."""


class UnsupportedDatabaseTypeError(DatabaseInitializationError):
    """Database type is not supported by this database layer."""


class DatabaseDriverNotInstalledError(DatabaseInitializationError):
    """Configured database driver is not installed."""


class MissingDatabaseParameterError(DatabaseInitializationError):
    """Required database connection parameter is missing."""


class DatabaseUrlError(DatabaseInitializationError):
    """Database URL creation failed."""


class DatabaseNotInitializedError(DatabaseError):
    """Database manager has not been initialized."""
