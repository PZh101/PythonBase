"""租户感知异步 CRUD。"""

from collections.abc import Sequence
from typing import Any, Literal, TypeVar

from pydantic import BaseModel as PydanticBaseModel
from sqlalchemy import and_, delete as sa_delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pkg.database.crud import BaseCrud
from pkg.tenant.mixins import TenantMixin

TenantModelType = TypeVar("TenantModelType", bound=TenantMixin)


class TenantAwareCrud(BaseCrud[TenantModelType, Any]):
    """自动附加 tenant_id 条件的 CRUD。"""

    async def get(self, db: AsyncSession, *, tenant_id: int, id: Any) -> TenantModelType | None:
        """按租户和主键查询单条记录。"""
        coerced_id = self._coerce_pk(id)
        query = select(self.model).where(self._tenant_pk_eq(tenant_id, coerced_id))
        result = await db.execute(query)
        return result.scalars().first()

    async def create(
        self,
        db: AsyncSession,
        *,
        tenant_id: int,
        obj_in: TenantModelType | dict[str, Any] | PydanticBaseModel,
    ) -> TenantModelType:
        """创建租户内记录并自动写入 tenant_id。"""
        if isinstance(obj_in, dict):
            payload = {**obj_in, "tenant_id": tenant_id}
            db_obj = self.model(**payload)
        elif isinstance(obj_in, PydanticBaseModel):
            payload = {**obj_in.model_dump(), "tenant_id": tenant_id}
            db_obj = self.model(**payload)
        else:
            obj_in.tenant_id = tenant_id
            db_obj = obj_in

        db.add(db_obj)
        await db.flush()
        await db.refresh(db_obj)
        return db_obj

    async def update(
        self,
        db: AsyncSession,
        *,
        tenant_id: int,
        id: Any,
        obj_update: dict[str, Any] | PydanticBaseModel,
        exclude_unset: bool = False,
    ) -> TenantModelType | None:
        """按租户和主键更新记录。"""
        db_obj = await self.get(db, tenant_id=tenant_id, id=id)
        if db_obj is None:
            return None

        if isinstance(obj_update, PydanticBaseModel):
            update_data = obj_update.model_dump(exclude_unset=exclude_unset)
        else:
            update_data = obj_update
        update_data.pop("tenant_id", None)

        for field, value in update_data.items():
            setattr(db_obj, field, value)

        db.add(db_obj)
        await db.flush()
        await db.refresh(db_obj)
        return db_obj

    async def delete_by_id(self, db: AsyncSession, *, tenant_id: int, id: Any) -> bool:
        """按租户和主键删除记录。"""
        coerced_id = self._coerce_pk(id)
        query = sa_delete(self.model).where(self._tenant_pk_eq(tenant_id, coerced_id))
        result = await db.execute(query)
        await db.flush()
        return (result.rowcount or 0) > 0

    async def list_page(
        self,
        db: AsyncSession,
        *,
        tenant_id: int,
        page: int = 1,
        size: int = 20,
        filters: list | None = None,
        sort_field: str | None = None,
        sort_order: Literal["asc", "desc"] = "desc",
    ) -> tuple[Sequence[TenantModelType], int]:
        """分页查询租户内记录。"""
        all_filters = [self.model.tenant_id == tenant_id, *(filters or [])]
        return await super().list_page(
            db,
            page=page,
            size=size,
            filters=all_filters,
            sort_field=sort_field,
            sort_order=sort_order,
        )

    async def count(self, db: AsyncSession, *, tenant_id: int, filters: list | None = None) -> int:
        """统计租户内记录数。"""
        all_filters = [self.model.tenant_id == tenant_id, *(filters or [])]
        statement = select(func.count()).select_from(self.model).where(and_(*all_filters))
        result = await db.execute(statement)
        return result.scalar() or 0

    def _tenant_pk_eq(self, tenant_id: int, id: Any):
        """构造租户和主键联合过滤条件。"""
        return and_(self.model.tenant_id == tenant_id, self._pk_eq(id))
