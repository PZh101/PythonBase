"""Compatibility exports for the migrated database CRUD layer."""

from pkg.database.base import Base
from pkg.database.crud import BaseCrud

__all__ = ["Base", "BaseCrud"]
