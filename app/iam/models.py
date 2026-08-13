"""IAM 用户、租户、角色和权限 ORM 模型。"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from pkg.database.base import Base


class IamUser(Base):
    """平台用户。"""

    __tablename__ = "iam_users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(128))
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class IamTenant(Base):
    """租户。"""

    __tablename__ = "iam_tenants"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class IamTenantMember(Base):
    """用户在租户内的成员身份。"""

    __tablename__ = "iam_tenant_members"
    __table_args__ = (UniqueConstraint("tenant_id", "user_id", name="uq_iam_member_tenant_user"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("iam_tenants.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("iam_users.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class IamRole(Base):
    """租户内角色。"""

    __tablename__ = "iam_roles"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_iam_role_tenant_code"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("iam_tenants.id"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class IamPermission(Base):
    """系统权限定义。"""

    __tablename__ = "iam_permissions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    code: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)


class IamTenantMemberRole(Base):
    """成员和角色关系。"""

    __tablename__ = "iam_tenant_member_roles"
    __table_args__ = (UniqueConstraint("member_id", "role_id", name="uq_iam_member_role"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    member_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("iam_tenant_members.id"), nullable=False, index=True)
    role_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("iam_roles.id"), nullable=False, index=True)


class IamRolePermission(Base):
    """角色和权限关系。"""

    __tablename__ = "iam_role_permissions"
    __table_args__ = (UniqueConstraint("role_id", "permission_id", name="uq_iam_role_permission"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    role_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("iam_roles.id"), nullable=False, index=True)
    permission_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("iam_permissions.id"), nullable=False, index=True)


class IamUserCredential(Base):
    """IAM 用户凭证。

    与 :class:`IamUser` 一一对应，仅持有登录态（密码哈希、失败计数、token 版本号等），
    不存放任何与租户/角色/权限相关的业务属性。

    字段语义：

    - ``token_version`` 每次登出或重置密码时 +1，所有版本号低于新值的访问 token 立即失效。
    - ``failed_attempts`` 连续登录失败计数，成功后清零；超过上限后写入 ``locked_until``。
    """

    __tablename__ = "iam_user_credentials"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("iam_users.id", ondelete="CASCADE"), primary_key=True
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    token_version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    failed_attempts: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime)
    password_changed_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
