"""Generic async CRUD helpers."""

from collections.abc import Sequence
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel as PydanticBaseModel
from sqlalchemy import and_, delete as sa_delete, func, inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from pkg.database.base import Base

ModelType = TypeVar("ModelType", bound=Base)
PrimaryKeyType = TypeVar("PrimaryKeyType")


class BaseCrud(Generic[ModelType, PrimaryKeyType]):
    """Generic CRUD operations that rely on caller-managed transactions."""

    def __init__(self, model: type[ModelType]) -> None:
        self.model = model
        pk_column = inspect(model).primary_key[0]
        self._pk_name = pk_column.name
        self._pk_type = pk_column.type.python_type

    def _coerce_pk(self, id: Any):
        """Coerce the incoming primary key into the mapped column type."""
        try:
            return self._pk_type(id)
        except Exception as exc:
            raise ValueError(f"Invalid primary key type: {id}") from exc

    async def get(self, db: AsyncSession, id: Any) -> ModelType | None:
        """Get one record by primary key."""
        id = self._coerce_pk(id)
        query = select(self.model).where(self._pk_eq(id))
        result = await db.execute(query)
        return result.scalars().first()

    async def create(
        self,
        db: AsyncSession,
        obj_in: ModelType | dict[str, Any] | PydanticBaseModel,
    ) -> ModelType:
        """Create a record and flush it without committing."""
        if isinstance(obj_in, dict):
            db_obj = self.model(**obj_in)
        elif isinstance(obj_in, PydanticBaseModel):
            db_obj = self.model(**obj_in.model_dump())
        else:
            db_obj = obj_in

        db.add(db_obj)
        await db.flush()
        await db.refresh(db_obj)
        return db_obj

    async def update(
        self,
        db: AsyncSession,
        id: Any,
        obj_update: dict[str, Any] | PydanticBaseModel,
        *,
        exclude_unset: bool = False,
    ) -> ModelType | None:
        """Update one record by primary key and flush without committing."""
        db_obj = await self.get(db, id)
        if not db_obj:
            return None

        if isinstance(obj_update, PydanticBaseModel):
            update_data = obj_update.model_dump(exclude_unset=exclude_unset)
        else:
            update_data = obj_update

        for field, value in update_data.items():
            setattr(db_obj, field, value)

        db.add(db_obj)
        await db.flush()
        await db.refresh(db_obj)
        return db_obj

    async def delete_by_id(self, db: AsyncSession, id: Any) -> bool:
        """Delete one record by primary key and flush without committing."""
        id = self._coerce_pk(id)
        del_query = sa_delete(self.model).where(self._pk_eq(id))
        result = await db.execute(del_query)
        await db.flush()
        return (result.rowcount or 0) > 0

    async def list_page(
        self,
        db: AsyncSession,
        page: int = 1,
        size: int = 20,
        *,
        filters: list | None = None,
        sort_field: str | None = None,
        sort_order: Literal["asc", "desc"] = "desc",
    ) -> tuple[Sequence[ModelType], int]:
        """List one page of records with optional filters and sorting."""
        page = max(page, 1)
        size = min(max(size, 1), 200)

        count_query = select(func.count()).select_from(self.model)
        if filters:
            count_query = count_query.where(and_(*filters))
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        order = self._build_order(sort_field, sort_order)
        stmt = (
            select(self.model)
            .order_by(order)
            .offset((page - 1) * size)
            .limit(size)
        )
        if filters:
            stmt = stmt.where(and_(*filters))
        result = await db.execute(stmt)
        items = result.scalars().all()

        return items, total

    async def get_all(
        self,
        db: AsyncSession,
        *,
        filters: list | None = None,
        sort_field: str | None = None,
        sort_order: Literal["asc", "desc"] = "desc",
        limit: int | None = None,
    ) -> Sequence[ModelType]:
        """Get all records with optional filters, sorting, and limit."""
        order = self._build_order(sort_field, sort_order)
        stmt = select(self.model).order_by(order)
        if filters:
            stmt = stmt.where(and_(*filters))
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await db.execute(stmt)
        return result.scalars().all()

    async def count(self, db: AsyncSession, *, filters: list | None = None) -> int:
        """Count records with optional filters."""
        stmt = select(func.count()).select_from(self.model)
        if filters:
            stmt = stmt.where(and_(*filters))
        result = await db.execute(stmt)
        return result.scalar() or 0

    def _pk_eq(self, id: Any):
        """Build the primary-key equality expression."""
        return getattr(self.model, self._pk_name) == id

    def _build_order(
        self,
        sort_field: str | None,
        sort_order: Literal["asc", "desc"],
    ):
        """Build a SQLAlchemy order expression from field and direction."""
        field_name = sort_field or self._pk_name
        column = getattr(self.model, field_name, None)
        if column is None:
            raise ValueError(
                f"Model '{self.model.__name__}' has no field '{field_name}'"
            )
        return column.asc() if sort_order == "asc" else column.desc()
