from typing import Type, TypeVar, Generic, Any, Optional, Sequence, Literal
from sqlalchemy import select, func, delete as sa_delete, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import inspect
from pydantic import BaseModel

Base = declarative_base()
ModelType = TypeVar("ModelType", bound=Base)  # type: ignore
PrimaryKeyType = TypeVar("PrimaryKeyType")


class BaseCrud(Generic[ModelType, PrimaryKeyType]):
    """通用 CRUD 操作基类"""

    def __init__(self, model: Type[ModelType]):
        self.model = model
        # 运行期反射获取主键字段类型，用于严格的类型匹配
        pk_column = inspect(model).primary_key[0]
        self._pk_name = pk_column.name
        self._pk_type = pk_column.type.python_type

    def _coerce_pk(self, id: Any):
        """将输入的主键值转为模型定义的类型，校验失败时抛出 ValueError"""
        try:
            return self._pk_type(id)
        except Exception:
            raise ValueError(f"Invalid primary key type: {id}")

    async def get(self, db: AsyncSession, id: Any) -> Optional[ModelType]:
        """根据主键获取单条记录"""
        id = self._coerce_pk(id)
        query = select(self.model).where(self._pk_eq(id))
        result = await db.execute(query)
        return result.scalars().first()

    async def create(self, db: AsyncSession, obj_in: ModelType | dict[str, Any] | BaseModel) -> ModelType:
        """创建新记录

        参数支持三种形式：
        - 模型实例 → 直接添加
        - dict → 解包构造模型
        - Pydantic BaseModel → 调用 model_dump() 后构造
        """
        if isinstance(obj_in, dict):
            db_obj = self.model(**obj_in)
        elif isinstance(obj_in, BaseModel):
            db_obj = self.model(**obj_in.model_dump())
        else:
            db_obj = obj_in
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def update(
        self,
        db: AsyncSession,
        id: Any,
        obj_update: dict[str, Any] | BaseModel,
        *,
        exclude_unset: bool = False,
    ) -> Optional[ModelType]:
        """根据主键更新记录，返回更新后的对象；记录不存在时返回 None

        obj_update 支持 dict 或 Pydantic BaseModel；
        exclude_unset=True 时只更新显式设置的字段（对 Pydantic 模型有效）。
        """
        db_obj = await self.get(db, id)
        if not db_obj:
            return None

        if isinstance(obj_update, BaseModel):
            update_data = obj_update.model_dump(exclude_unset=exclude_unset)
        else:
            update_data = obj_update

        for field, value in update_data.items():
            setattr(db_obj, field, value)

        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def delete_by_id(self, db: AsyncSession, id: Any) -> bool:
        """根据主键删除记录，返回是否删除了记录"""
        id = self._coerce_pk(id)
        del_query = sa_delete(self.model).where(self._pk_eq(id))
        result = await db.execute(del_query)
        await db.commit()
        return result.rowcount > 0

    async def list_page(
        self,
        db: AsyncSession,
        page: int = 1,
        size: int = 20,
        *,
        filters: Optional[list] = None,
        sort_field: Optional[str] = None,
        sort_order: Literal["asc", "desc"] = "desc",
    ) -> tuple[Sequence[ModelType], int]:
        """通用分页查询

        参数:
            page: 页码，从 1 开始
            size: 每页条数
            filters: 可选，SQLAlchemy filter 条件列表
            sort_field: 排序字段名（模型属性名，如 "id"、"created_at"）；不传则按主键排序
            sort_order: 排序方向，"asc" 或 "desc"，默认 desc

        返回:
            (当前页记录列表, 总记录数)
        """
        page = max(page, 1)
        size = min(max(size, 1), 200)  # 限制最大 200 条

        # 计数
        count_query = select(func.count()).select_from(self.model)
        if filters:
            count_query = count_query.where(and_(*filters))
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # 排序
        order = self._build_order(sort_field, sort_order)

        # 分页查询
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
        filters: Optional[list] = None,
        sort_field: Optional[str] = None,
        sort_order: Literal["asc", "desc"] = "desc",
        limit: Optional[int] = None,
    ) -> Sequence[ModelType]:
        """获取所有记录（支持过滤、排序、可选上限）"""
        order = self._build_order(sort_field, sort_order)
        stmt = select(self.model).order_by(order)
        if filters:
            stmt = stmt.where(and_(*filters))
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await db.execute(stmt)
        return result.scalars().all()

    async def count(self, db: AsyncSession, *, filters: Optional[list] = None) -> int:
        """统计记录数，可选过滤条件"""
        stmt = select(func.count()).select_from(self.model)
        if filters:
            stmt = stmt.where(and_(*filters))
        result = await db.execute(stmt)
        return result.scalar() or 0

    # ── 内部辅助 ──────────────────────────────────────────

    def _pk_eq(self, id: Any):
        """主键等值条件"""
        return getattr(self.model, self._pk_name) == id

    def _build_order(self, sort_field: Optional[str], sort_order: Literal["asc", "desc"]):
        """将字符串形式的排序参数转为 SQLAlchemy order_by 表达式

        未传入 sort_field 时默认按主键降序。
        """
        field_name = sort_field or self._pk_name
        column = getattr(self.model, field_name, None)
        if column is None:
            raise ValueError(
                f"Model '{self.model.__name__}' has no field '{field_name}'"
            )
        return column.asc() if sort_order == "asc" else column.desc()
