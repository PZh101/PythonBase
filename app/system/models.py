"""企业组织、用户、角色和资源权限 ORM 模型。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from pkg.database.base import Base


class SysDept(Base):
    """部门表。"""

    __tablename__ = "sys_dept"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    parent_id: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, index=True)
    dept_name: Mapped[str] = mapped_column(String(100), nullable=False)
    dept_path: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    dept_tags: Mapped[list[str] | None] = mapped_column(JSON)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class SysUser(Base):
    """用户基础信息表。"""

    __tablename__ = "sys_user"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    real_name: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class SysUserDept(Base):
    """用户-部门关联表。"""

    __tablename__ = "sys_user_dept"
    __table_args__ = (UniqueConstraint("user_id", "dept_id", name="uk_user_dept"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    dept_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    is_primary: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class SysRole(Base):
    """角色表，包含数据范围策略。"""

    __tablename__ = "sys_role"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    role_name: Mapped[str] = mapped_column(String(50), nullable=False)
    role_key: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    data_scope: Mapped[int] = mapped_column(Integer, nullable=False, default=1, index=True)
    data_scope_rule: Mapped[dict | list | None] = mapped_column(JSON)
    status: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class SysMenu(Base):
    """菜单和资源表。"""

    __tablename__ = "sys_menu"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    parent_id: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, index=True)
    menu_name: Mapped[str] = mapped_column(String(50), nullable=False)
    menu_type: Mapped[str] = mapped_column(String(1), nullable=False)
    permission: Mapped[str | None] = mapped_column(String(100), index=True)
    path: Mapped[str | None] = mapped_column(String(200))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class SysRoleMenu(Base):
    """角色-菜单关联表。"""

    __tablename__ = "sys_role_menu"
    __table_args__ = (UniqueConstraint("role_id", "menu_id", name="uk_role_menu"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    role_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    menu_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)


class SysUserRole(Base):
    """用户-角色关联表。"""

    __tablename__ = "sys_user_role"
    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uk_user_role"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    role_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)


class SysRoleDept(Base):
    """角色-部门关联表，用于自定义数据权限。"""

    __tablename__ = "sys_role_dept"
    __table_args__ = (UniqueConstraint("role_id", "dept_id", name="uk_role_dept"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    role_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    dept_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

