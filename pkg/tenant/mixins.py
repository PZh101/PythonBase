"""租户隔离 ORM 混入。"""

from sqlalchemy import BigInteger
from sqlalchemy.orm import Mapped, mapped_column


class TenantMixin:
    """租户业务表混入，提供统一 tenant_id 字段。"""

    tenant_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
