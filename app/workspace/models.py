"""业务空间与临时授权 ORM 模型。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from pkg.database.base import Base


class SysTempAuth(Base):
    """临时授权表。"""

    __tablename__ = "sys_temp_auth"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(20), nullable=False)
    resource_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    permission: Mapped[str] = mapped_column(String(100), nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    grant_reason: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class SysWorkspace(Base):
    """业务空间表。"""

    __tablename__ = "sys_workspace"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    space_name: Mapped[str] = mapped_column(String(100), nullable=False)
    space_desc: Mapped[str | None] = mapped_column(String(500))
    owner_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    status: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class SysWorkspaceMember(Base):
    """空间成员表。"""

    __tablename__ = "sys_workspace_member"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id", name="uk_ws_member"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

