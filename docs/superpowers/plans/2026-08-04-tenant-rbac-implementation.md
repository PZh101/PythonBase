# Tenant RBAC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reusable multi-tenant RBAC framework where one user can belong to many tenants and hold different roles in each tenant.

**Architecture:** Keep reusable request context, tenant resolution, permission checks, and tenant-aware CRUD in `pkg/`. Put concrete IAM tables, repositories, services, and routes in `app/iam`. Use `X-Tenant-Id` as the first supported tenant resolver and apply row-level isolation with `tenant_id` on tenant-owned business tables.

**Tech Stack:** Python 3.12, FastAPI dependencies, Pydantic v2, SQLAlchemy 2.x async ORM, pytest.

---

## Scope

This plan implements the first production-shaped version of the tenant RBAC framework from `docs/superpowers/specs/2026-08-04-tenant-rbac-design.md`.

Included:

- Immutable auth and tenant context models.
- Security exceptions mapped to existing `AppException`.
- `X-Tenant-Id` resolver.
- Permission and role guard dependency factories.
- Provider protocol so `pkg/` does not depend on `app/iam`.
- Tenant field mixin and tenant-aware CRUD.
- IAM ORM models for users, tenants, members, roles, permissions, and relation tables.
- IAM repository and service for loading an `AuthContext`.
- Focused tests for all reusable behavior.

Excluded from this plan:

- Password login, Token issuing, OAuth2, OIDC, SSO.
- Frontend pages.
- Database migrations and Alembic wiring.
- Platform audit log persistence.
- Distributed permission cache.
- Per-tenant database or schema isolation.

## File Structure

Create reusable framework files:

- `pkg/security/__init__.py`: public exports for security context, exceptions, and dependency factories.
- `pkg/security/context.py`: immutable `Principal`, `PermissionSet`, and `AuthContext`.
- `pkg/security/exceptions.py`: authentication and authorization exceptions built on `pkg.common.exceptions.AppException`.
- `pkg/security/providers.py`: provider protocols used by dependency factories.
- `pkg/security/permissions.py`: pure permission and role matching helpers.
- `pkg/security/dependencies.py`: FastAPI dependency factories.
- `pkg/tenant/__init__.py`: public tenant exports.
- `pkg/tenant/context.py`: immutable `TenantContext`.
- `pkg/tenant/resolver.py`: `X-Tenant-Id` resolver.
- `pkg/tenant/mixins.py`: SQLAlchemy `TenantMixin`.
- `pkg/database/tenant_crud.py`: `TenantAwareCrud`.

Create concrete IAM files:

- `app/iam/__init__.py`: IAM package marker and public exports.
- `app/iam/models.py`: SQLAlchemy ORM models.
- `app/iam/repository.py`: async queries for user, tenant, membership, roles, and permissions.
- `app/iam/service.py`: builds `AuthContext` for a request.
- `app/iam/schemas.py`: `BaseSchema` request and response models.

Create tests:

- `tests/pkg/security/test_context.py`
- `tests/pkg/security/test_permissions.py`
- `tests/pkg/security/test_dependencies.py`
- `tests/pkg/tenant/test_resolver.py`
- `tests/pkg/database/test_tenant_crud.py`
- `tests/app/iam/test_models.py`
- `tests/app/iam/test_service.py`

Modify existing files:

- `pkg/database/__init__.py`: export `TenantAwareCrud`.
- No required changes to `pkg/common`.
- No required changes to `main.py`.

## Task 1: Security Context Models

**Files:**

- Create: `pkg/security/__init__.py`
- Create: `pkg/security/context.py`
- Test: `tests/pkg/security/test_context.py`

- [ ] **Step 1: Write failing context tests**

Create `tests/pkg/security/test_context.py`:

```python
"""安全上下文模型测试。"""

from dataclasses import FrozenInstanceError

import pytest

from pkg.security.context import AuthContext, PermissionSet, Principal
from pkg.tenant.context import TenantContext


def test_permission_set_supports_exact_permissions() -> None:
    """权限集合应支持精确权限判断。"""
    permissions = PermissionSet(values=frozenset({"user:read", "role:assign"}))

    assert permissions.has("user:read") is True
    assert permissions.has("user:create") is False


def test_auth_context_is_immutable() -> None:
    """认证上下文应不可原地修改，避免请求处理中被污染。"""
    context = AuthContext(
        principal=Principal(user_id=1, username="ada"),
        tenant=TenantContext(tenant_id=10),
        member_id=100,
        roles=frozenset({"owner"}),
        permissions=PermissionSet(values=frozenset({"user:create"})),
    )

    with pytest.raises(FrozenInstanceError):
        context.member_id = 200


def test_platform_admin_flag_comes_from_principal() -> None:
    """平台管理员标记应来自认证主体。"""
    context = AuthContext(
        principal=Principal(user_id=1, username="root", is_platform_admin=True),
        tenant=None,
        member_id=None,
        roles=frozenset(),
        permissions=PermissionSet(values=frozenset()),
    )

    assert context.is_platform_admin is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/pkg/security/test_context.py -v
```

Expected: fail with `ModuleNotFoundError: No module named 'pkg.security'`.

- [ ] **Step 3: Implement context models**

Create `pkg/security/context.py`:

```python
"""认证与授权请求上下文。"""

from dataclasses import dataclass, field

from pkg.tenant.context import TenantContext


@dataclass(frozen=True, slots=True)
class Principal:
    """已认证主体。

    Args:
        user_id: 用户 ID。
        username: 用户名或展示名。
        is_platform_admin: 是否为平台管理员。
        authenticated: 是否已经通过认证。
    """

    user_id: int
    username: str | None = None
    is_platform_admin: bool = False
    authenticated: bool = True


@dataclass(frozen=True, slots=True)
class PermissionSet:
    """权限集合，第一阶段仅支持精确权限匹配。"""

    values: frozenset[str] = field(default_factory=frozenset)

    def has(self, permission: str) -> bool:
        """判断是否拥有指定权限。"""
        return permission in self.values

    def has_any(self, permissions: tuple[str, ...]) -> bool:
        """判断是否拥有任意一个权限。"""
        return any(permission in self.values for permission in permissions)


@dataclass(frozen=True, slots=True)
class AuthContext:
    """一次请求的认证与授权快照。"""

    principal: Principal
    tenant: TenantContext | None
    member_id: int | None
    roles: frozenset[str]
    permissions: PermissionSet

    @property
    def is_platform_admin(self) -> bool:
        """返回当前主体是否为平台管理员。"""
        return self.principal.is_platform_admin

    def has_role(self, role: str) -> bool:
        """判断当前租户上下文中是否拥有指定角色。"""
        return role in self.roles

    def has_permission(self, permission: str) -> bool:
        """判断当前租户上下文中是否拥有指定权限。"""
        return self.permissions.has(permission)
```

Create `pkg/security/__init__.py`:

```python
"""安全上下文、权限校验和 FastAPI 依赖。"""

from pkg.security.context import AuthContext, PermissionSet, Principal

__all__ = ["AuthContext", "PermissionSet", "Principal"]
```

- [ ] **Step 4: Run tests to verify current failure moves to tenant context**

Run:

```bash
uv run pytest tests/pkg/security/test_context.py -v
```

Expected: fail with `ModuleNotFoundError: No module named 'pkg.tenant'`.

- [ ] **Step 5: Commit**

Do not commit yet. This task depends on Task 2 for `TenantContext`.

## Task 2: Tenant Context And Header Resolver

**Files:**

- Create: `pkg/tenant/__init__.py`
- Create: `pkg/tenant/context.py`
- Create: `pkg/tenant/resolver.py`
- Test: `tests/pkg/tenant/test_resolver.py`

- [ ] **Step 1: Write failing tenant resolver tests**

Create `tests/pkg/tenant/test_resolver.py`:

```python
"""租户解析器测试。"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pkg.tenant.context import TenantContext
from pkg.tenant.resolver import resolve_tenant_id_from_header


def test_tenant_context_is_immutable() -> None:
    """租户上下文应不可变。"""
    context = TenantContext(tenant_id=123, tenant_code="demo", tenant_name="演示租户")

    with pytest.raises(Exception):
        context.tenant_id = 456


def test_resolver_reads_x_tenant_id_header() -> None:
    """租户解析器应从 X-Tenant-Id 请求头读取租户 ID。"""
    app = FastAPI()

    @app.get("/tenant")
    async def read_tenant(tenant_id: int | None = resolve_tenant_id_from_header()):
        return {"tenant_id": tenant_id}

    client = TestClient(app)
    response = client.get("/tenant", headers={"X-Tenant-Id": "123"})

    assert response.status_code == 200
    assert response.json() == {"tenant_id": 123}


def test_resolver_allows_missing_header_for_optional_routes() -> None:
    """未提供租户请求头时，解析器应返回 None 供上层决定是否必需。"""
    app = FastAPI()

    @app.get("/tenant")
    async def read_tenant(tenant_id: int | None = resolve_tenant_id_from_header()):
        return {"tenant_id": tenant_id}

    client = TestClient(app)
    response = client.get("/tenant")

    assert response.status_code == 200
    assert response.json() == {"tenant_id": None}
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/pkg/tenant/test_resolver.py -v
```

Expected: fail with `ModuleNotFoundError: No module named 'pkg.tenant'`.

- [ ] **Step 3: Implement tenant context and resolver**

Create `pkg/tenant/context.py`:

```python
"""租户请求上下文。"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TenantContext:
    """当前请求所在租户。"""

    tenant_id: int
    tenant_code: str | None = None
    tenant_name: str | None = None
    tenant_status: str | None = None
    is_required: bool = True
```

Create `pkg/tenant/resolver.py`:

```python
"""当前租户解析器。"""

from typing import Annotated

from fastapi import Header


def resolve_tenant_id_from_header() -> Annotated[int | None, Header(alias="X-Tenant-Id")]:
    """声明从 X-Tenant-Id 请求头读取当前租户 ID。"""
    return Header(default=None, alias="X-Tenant-Id")
```

Create `pkg/tenant/__init__.py`:

```python
"""租户上下文、解析器和模型混入。"""

from pkg.tenant.context import TenantContext
from pkg.tenant.resolver import resolve_tenant_id_from_header

__all__ = ["TenantContext", "resolve_tenant_id_from_header"]
```

- [ ] **Step 4: Run tenant and security context tests**

Run:

```bash
uv run pytest tests/pkg/tenant/test_resolver.py tests/pkg/security/test_context.py -v
```

Expected: both files pass.

- [ ] **Step 5: Commit**

```bash
git add pkg/security/__init__.py pkg/security/context.py pkg/tenant/__init__.py pkg/tenant/context.py pkg/tenant/resolver.py tests/pkg/security/test_context.py tests/pkg/tenant/test_resolver.py
git commit -m "feat: add auth and tenant contexts"
```

## Task 3: Security Exceptions And Permission Helpers

**Files:**

- Create: `pkg/security/exceptions.py`
- Create: `pkg/security/permissions.py`
- Modify: `pkg/security/__init__.py`
- Test: `tests/pkg/security/test_permissions.py`

- [ ] **Step 1: Write failing permission tests**

Create `tests/pkg/security/test_permissions.py`:

```python
"""权限判断与异常测试。"""

import pytest

from pkg.security.context import AuthContext, PermissionSet, Principal
from pkg.security.exceptions import PermissionDeniedException, TenantRequiredException
from pkg.security.permissions import ensure_permission, ensure_role, ensure_tenant
from pkg.tenant.context import TenantContext


def make_context() -> AuthContext:
    """构造包含租户、角色和权限的测试上下文。"""
    return AuthContext(
        principal=Principal(user_id=1, username="ada"),
        tenant=TenantContext(tenant_id=10),
        member_id=100,
        roles=frozenset({"owner"}),
        permissions=PermissionSet(values=frozenset({"user:create"})),
    )


def test_ensure_permission_allows_existing_permission() -> None:
    """拥有权限时不应抛出异常。"""
    ensure_permission(make_context(), "user:create")


def test_ensure_permission_rejects_missing_permission() -> None:
    """缺少权限时应抛出权限不足异常。"""
    with pytest.raises(PermissionDeniedException):
        ensure_permission(make_context(), "user:delete")


def test_ensure_role_allows_existing_role() -> None:
    """拥有角色时不应抛出异常。"""
    ensure_role(make_context(), "owner")


def test_ensure_tenant_rejects_missing_tenant() -> None:
    """接口要求租户上下文但上下文为空时应被拒绝。"""
    context = AuthContext(
        principal=Principal(user_id=1),
        tenant=None,
        member_id=None,
        roles=frozenset(),
        permissions=PermissionSet(values=frozenset()),
    )

    with pytest.raises(TenantRequiredException):
        ensure_tenant(context)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/pkg/security/test_permissions.py -v
```

Expected: fail with `ModuleNotFoundError` for `pkg.security.exceptions` or `pkg.security.permissions`.

- [ ] **Step 3: Implement exceptions and helpers**

Create `pkg/security/exceptions.py`:

```python
"""认证、租户和授权异常。"""

from typing import Any

from pkg.common.exceptions import AppException


class AuthenticationRequiredException(AppException):
    """未认证。"""

    def __init__(self, msg: str = "请先登录", *, code: int = 40100, data: Any = None):
        super().__init__(msg, code=code, data=data, http_status_code=401)


class InvalidCredentialException(AppException):
    """认证凭据无效。"""

    def __init__(self, msg: str = "认证凭据无效", *, code: int = 40101, data: Any = None):
        super().__init__(msg, code=code, data=data, http_status_code=401)


class TenantRequiredException(AppException):
    """缺少必需的租户上下文。"""

    def __init__(self, msg: str = "缺少租户上下文", *, code: int = 40310, data: Any = None):
        super().__init__(msg, code=code, data=data, http_status_code=403)


class TenantAccessDeniedException(AppException):
    """无权访问指定租户。"""

    def __init__(self, msg: str = "无权访问该租户", *, code: int = 40311, data: Any = None):
        super().__init__(msg, code=code, data=data, http_status_code=403)


class PermissionDeniedException(AppException):
    """权限不足。"""

    def __init__(self, msg: str = "权限不足", *, code: int = 40300, data: Any = None):
        super().__init__(msg, code=code, data=data, http_status_code=403)
```

Create `pkg/security/permissions.py`:

```python
"""纯权限判断工具。"""

from pkg.security.context import AuthContext
from pkg.security.exceptions import PermissionDeniedException, TenantRequiredException


def ensure_tenant(context: AuthContext) -> None:
    """确保当前请求存在租户上下文。"""
    if context.tenant is None or context.member_id is None:
        raise TenantRequiredException()


def ensure_permission(context: AuthContext, permission: str) -> None:
    """确保当前上下文拥有指定权限。"""
    if context.is_platform_admin:
        return
    if not context.has_permission(permission):
        raise PermissionDeniedException()


def ensure_any_permission(context: AuthContext, *permissions: str) -> None:
    """确保当前上下文拥有任意一个权限。"""
    if context.is_platform_admin:
        return
    if not context.permissions.has_any(tuple(permissions)):
        raise PermissionDeniedException()


def ensure_role(context: AuthContext, role: str) -> None:
    """确保当前上下文拥有指定角色。"""
    if context.is_platform_admin:
        return
    if not context.has_role(role):
        raise PermissionDeniedException()
```

Update `pkg/security/__init__.py`:

```python
"""安全上下文、权限校验和 FastAPI 依赖。"""

from pkg.security.context import AuthContext, PermissionSet, Principal
from pkg.security.exceptions import (
    AuthenticationRequiredException,
    InvalidCredentialException,
    PermissionDeniedException,
    TenantAccessDeniedException,
    TenantRequiredException,
)
from pkg.security.permissions import ensure_any_permission, ensure_permission, ensure_role, ensure_tenant

__all__ = [
    "AuthContext",
    "AuthenticationRequiredException",
    "InvalidCredentialException",
    "PermissionDeniedException",
    "PermissionSet",
    "Principal",
    "TenantAccessDeniedException",
    "TenantRequiredException",
    "ensure_any_permission",
    "ensure_permission",
    "ensure_role",
    "ensure_tenant",
]
```

- [ ] **Step 4: Run permission tests**

Run:

```bash
uv run pytest tests/pkg/security/test_permissions.py -v
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add pkg/security tests/pkg/security/test_permissions.py
git commit -m "feat: add permission checks"
```

## Task 4: Provider Protocols And FastAPI Dependencies

**Files:**

- Create: `pkg/security/providers.py`
- Create: `pkg/security/dependencies.py`
- Modify: `pkg/security/__init__.py`
- Test: `tests/pkg/security/test_dependencies.py`

- [ ] **Step 1: Write failing dependency tests**

Create `tests/pkg/security/test_dependencies.py`:

```python
"""安全依赖工厂测试。"""

from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from pkg.security.context import AuthContext, PermissionSet, Principal
from pkg.security.dependencies import create_auth_context_dependency, require_permission
from pkg.tenant.context import TenantContext


class FakeAuthProvider:
    """测试用认证上下文提供者。"""

    async def load_context(self, *, user_id: int, tenant_id: int | None) -> AuthContext:
        return AuthContext(
            principal=Principal(user_id=user_id, username="ada"),
            tenant=TenantContext(tenant_id=tenant_id) if tenant_id is not None else None,
            member_id=100 if tenant_id is not None else None,
            roles=frozenset({"owner"}),
            permissions=PermissionSet(values=frozenset({"user:create"})),
        )


def test_permission_dependency_allows_authorized_request() -> None:
    """权限依赖应允许已授权请求进入路由。"""
    app = FastAPI()
    auth_dependency = create_auth_context_dependency(FakeAuthProvider())

    @app.get("/users")
    async def read_users(
        context: Annotated[AuthContext, Depends(auth_dependency)],
        _: Annotated[None, Depends(require_permission("user:create"))],
    ):
        return {"user_id": context.principal.user_id}

    client = TestClient(app)
    response = client.get("/users", headers={"X-User-Id": "1", "X-Tenant-Id": "10"})

    assert response.status_code == 200
    assert response.json() == {"user_id": 1}


def test_permission_dependency_rejects_missing_permission() -> None:
    """权限依赖应拒绝缺少权限的请求。"""
    app = FastAPI()
    auth_dependency = create_auth_context_dependency(FakeAuthProvider())

    @app.get("/users")
    async def read_users(
        context: Annotated[AuthContext, Depends(auth_dependency)],
        _: Annotated[None, Depends(require_permission("user:delete"))],
    ):
        return {"user_id": context.principal.user_id}

    client = TestClient(app)
    response = client.get("/users", headers={"X-User-Id": "1", "X-Tenant-Id": "10"})

    assert response.status_code == 403
    assert response.json()["msg"] == "权限不足"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/pkg/security/test_dependencies.py -v
```

Expected: fail with `ModuleNotFoundError` for `pkg.security.dependencies`.

- [ ] **Step 3: Implement provider protocol and dependencies**

Create `pkg/security/providers.py`:

```python
"""安全上下文 Provider 协议。"""

from typing import Protocol

from pkg.security.context import AuthContext


class AuthContextProvider(Protocol):
    """由应用层实现的认证上下文加载协议。"""

    async def load_context(self, *, user_id: int, tenant_id: int | None) -> AuthContext:
        """按用户和租户加载请求上下文。"""
```

Create `pkg/security/dependencies.py`:

```python
"""FastAPI 安全依赖工厂。"""

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Header, Request

from pkg.security.context import AuthContext
from pkg.security.exceptions import AuthenticationRequiredException
from pkg.security.permissions import ensure_any_permission, ensure_permission, ensure_role, ensure_tenant
from pkg.security.providers import AuthContextProvider


def create_auth_context_dependency(provider: AuthContextProvider) -> Callable[..., object]:
    """创建认证上下文依赖。"""

    async def get_auth_context(
        request: Request,
        user_id: Annotated[int | None, Header(alias="X-User-Id")] = None,
        tenant_id: Annotated[int | None, Header(alias="X-Tenant-Id")] = None,
    ) -> AuthContext:
        if user_id is None:
            raise AuthenticationRequiredException()
        context = await provider.load_context(user_id=user_id, tenant_id=tenant_id)
        request.state.auth_context = context
        return context

    return get_auth_context


def get_current_auth_context(request: Request) -> AuthContext:
    """从请求状态读取已加载的认证上下文。"""
    context = getattr(request.state, "auth_context", None)
    if context is None:
        raise AuthenticationRequiredException()
    return context


def require_tenant() -> Callable[[AuthContext], None]:
    """创建要求租户上下文的依赖。"""

    def dependency(context: Annotated[AuthContext, Depends(get_current_auth_context)]) -> None:
        ensure_tenant(context)

    return dependency


def require_permission(permission: str) -> Callable[[AuthContext], None]:
    """创建要求指定权限的依赖。"""

    def dependency(context: Annotated[AuthContext, Depends(get_current_auth_context)]) -> None:
        ensure_permission(context, permission)

    return dependency


def require_any_permission(*permissions: str) -> Callable[[AuthContext], None]:
    """创建要求任意权限的依赖。"""

    def dependency(context: Annotated[AuthContext, Depends(get_current_auth_context)]) -> None:
        ensure_any_permission(context, *permissions)

    return dependency


def require_role(role: str) -> Callable[[AuthContext], None]:
    """创建要求指定角色的依赖。"""

    def dependency(context: Annotated[AuthContext, Depends(get_current_auth_context)]) -> None:
        ensure_role(context, role)

    return dependency
```

- [ ] **Step 4: Register exception handlers in the test app**

Modify `tests/pkg/security/test_dependencies.py` so each `FastAPI()` app calls:

```python
from pkg.common.exceptions import register_exception_handlers

register_exception_handlers(app)
```

This makes `AppException` subclasses return `ApiResponse`.

- [ ] **Step 5: Run dependency tests**

Run:

```bash
uv run pytest tests/pkg/security/test_dependencies.py -v
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add pkg/security tests/pkg/security/test_dependencies.py
git commit -m "feat: add security dependencies"
```

## Task 5: Tenant Mixin And Tenant-Aware CRUD

**Files:**

- Create: `pkg/tenant/mixins.py`
- Create: `pkg/database/tenant_crud.py`
- Modify: `pkg/tenant/__init__.py`
- Modify: `pkg/database/__init__.py`
- Test: `tests/pkg/database/test_tenant_crud.py`

- [ ] **Step 1: Write failing tenant CRUD tests**

Create `tests/pkg/database/test_tenant_crud.py`:

```python
"""租户感知 CRUD 测试。"""

import asyncio
from unittest.mock import AsyncMock, Mock

from sqlalchemy import BigInteger, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from pkg.database.base import Base
from pkg.database.tenant_crud import TenantAwareCrud
from pkg.tenant.mixins import TenantMixin


class TenantUser(TenantMixin, Base):
    """测试用租户业务模型。"""

    __tablename__ = "tenant_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64))


def run(coro):
    """在同步测试中执行异步 CRUD。"""
    return asyncio.run(coro)


def make_session() -> Mock:
    """构造测试用 AsyncSession mock。"""
    session = Mock()
    session.add = Mock()
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    return session


def test_create_injects_tenant_id() -> None:
    """创建字典对象时应自动写入当前租户 ID。"""
    session = make_session()
    crud = TenantAwareCrud(TenantUser)

    created = run(crud.create(session, tenant_id=10, obj_in={"id": 1, "name": "Ada"}))

    assert created.tenant_id == 10
    session.flush.assert_awaited_once()
    session.refresh.assert_awaited_once_with(created)


def test_get_uses_tenant_filter() -> None:
    """按主键查询时必须附加租户过滤。"""
    session = make_session()
    result = Mock()
    result.scalars.return_value.first.return_value = None
    session.execute.return_value = result
    crud = TenantAwareCrud(TenantUser)

    assert run(crud.get(session, tenant_id=10, id=1)) is None

    statement = session.execute.call_args.args[0]
    assert "tenant_id" in str(statement)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/pkg/database/test_tenant_crud.py -v
```

Expected: fail with `ModuleNotFoundError` for `pkg.database.tenant_crud` or `pkg.tenant.mixins`.

- [ ] **Step 3: Implement mixin and CRUD**

Create `pkg/tenant/mixins.py`:

```python
"""租户隔离 ORM 混入。"""

from sqlalchemy import BigInteger
from sqlalchemy.orm import Mapped, mapped_column


class TenantMixin:
    """租户业务表混入，提供统一 tenant_id 字段。"""

    tenant_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
```

Create `pkg/database/tenant_crud.py`:

```python
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
        tenant_filter = self.model.tenant_id == tenant_id
        all_filters = [tenant_filter, *(filters or [])]
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
```

- [ ] **Step 4: Export new APIs**

Update `pkg/tenant/__init__.py`:

```python
"""租户上下文、解析器和模型混入。"""

from pkg.tenant.context import TenantContext
from pkg.tenant.mixins import TenantMixin
from pkg.tenant.resolver import resolve_tenant_id_from_header

__all__ = ["TenantContext", "TenantMixin", "resolve_tenant_id_from_header"]
```

Update `pkg/database/__init__.py` to include:

```python
from pkg.database.tenant_crud import TenantAwareCrud
```

and add `"TenantAwareCrud"` to `__all__`.

- [ ] **Step 5: Run tenant CRUD tests**

Run:

```bash
uv run pytest tests/pkg/database/test_tenant_crud.py -v
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add pkg/tenant pkg/database/tenant_crud.py pkg/database/__init__.py tests/pkg/database/test_tenant_crud.py
git commit -m "feat: add tenant aware crud"
```

## Task 6: IAM ORM Models

**Files:**

- Create: `app/iam/__init__.py`
- Create: `app/iam/models.py`
- Test: `tests/app/iam/test_models.py`

- [ ] **Step 1: Write failing IAM model tests**

Create `tests/app/iam/test_models.py`:

```python
"""IAM ORM 模型测试。"""

from app.iam.models import (
    IamPermission,
    IamRole,
    IamTenant,
    IamTenantMember,
    IamUser,
)


def test_table_names_are_stable() -> None:
    """IAM 表名应稳定，便于迁移脚本和运维识别。"""
    assert IamUser.__tablename__ == "iam_users"
    assert IamTenant.__tablename__ == "iam_tenants"
    assert IamTenantMember.__tablename__ == "iam_tenant_members"
    assert IamRole.__tablename__ == "iam_roles"
    assert IamPermission.__tablename__ == "iam_permissions"


def test_role_and_permission_are_tenant_scoped() -> None:
    """角色和成员关系应包含 tenant_id 以支持租户内差异化授权。"""
    assert "tenant_id" in IamRole.__table__.columns
    assert "tenant_id" in IamTenantMember.__table__.columns
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/app/iam/test_models.py -v
```

Expected: fail with `ModuleNotFoundError: No module named 'app.iam'`.

- [ ] **Step 3: Implement IAM models**

Create `app/iam/models.py`:

```python
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
```

Create `app/iam/__init__.py`:

```python
"""IAM 业务模块。"""
```

- [ ] **Step 4: Run model tests**

Run:

```bash
uv run pytest tests/app/iam/test_models.py -v
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add app/iam tests/app/iam/test_models.py
git commit -m "feat: add iam orm models"
```

## Task 7: IAM Repository And Auth Context Service

**Files:**

- Create: `app/iam/repository.py`
- Create: `app/iam/service.py`
- Test: `tests/app/iam/test_service.py`

- [ ] **Step 1: Write service tests with mocked repository**

Create `tests/app/iam/test_service.py`:

```python
"""IAM 认证上下文服务测试。"""

import asyncio
from dataclasses import dataclass

import pytest

from app.iam.service import IamAuthContextService
from pkg.security.exceptions import TenantAccessDeniedException


@dataclass(frozen=True)
class UserRow:
    """测试用户行。"""

    id: int
    username: str
    is_platform_admin: bool
    is_active: bool


@dataclass(frozen=True)
class TenantRow:
    """测试租户行。"""

    id: int
    code: str
    name: str
    status: str


@dataclass(frozen=True)
class MemberRow:
    """测试成员行。"""

    id: int
    tenant_id: int
    user_id: int
    status: str


class FakeRepository:
    """测试用 IAM 仓储。"""

    async def get_active_user(self, user_id: int):
        return UserRow(id=user_id, username="ada", is_platform_admin=False, is_active=True)

    async def get_active_tenant(self, tenant_id: int):
        return TenantRow(id=tenant_id, code="demo", name="演示租户", status="active")

    async def get_active_member(self, *, user_id: int, tenant_id: int):
        return MemberRow(id=100, tenant_id=tenant_id, user_id=user_id, status="active")

    async def list_role_codes(self, member_id: int):
        return frozenset({"owner"})

    async def list_permission_codes(self, member_id: int):
        return frozenset({"user:create"})


def run(coro):
    """在同步测试中执行异步服务。"""
    return asyncio.run(coro)


def test_load_context_builds_tenant_auth_context() -> None:
    """服务应基于用户和租户加载完整认证上下文。"""
    service = IamAuthContextService(FakeRepository())

    context = run(service.load_context(user_id=1, tenant_id=10))

    assert context.principal.user_id == 1
    assert context.tenant.tenant_id == 10
    assert context.member_id == 100
    assert context.roles == frozenset({"owner"})
    assert context.permissions.has("user:create") is True


def test_load_context_rejects_missing_member() -> None:
    """用户不是租户成员时应拒绝访问。"""

    class MissingMemberRepository(FakeRepository):
        async def get_active_member(self, *, user_id: int, tenant_id: int):
            return None

    service = IamAuthContextService(MissingMemberRepository())

    with pytest.raises(TenantAccessDeniedException):
        run(service.load_context(user_id=1, tenant_id=10))
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/app/iam/test_service.py -v
```

Expected: fail with `ModuleNotFoundError` for `app.iam.service`.

- [ ] **Step 3: Implement repository**

Create `app/iam/repository.py`:

```python
"""IAM 数据访问。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.iam.models import (
    IamPermission,
    IamRole,
    IamRolePermission,
    IamTenant,
    IamTenantMember,
    IamTenantMemberRole,
    IamUser,
)


class IamRepository:
    """IAM 查询仓储。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_active_user(self, user_id: int) -> IamUser | None:
        """查询启用状态的用户。"""
        result = await self.db.execute(
            select(IamUser).where(IamUser.id == user_id, IamUser.is_active.is_(True))
        )
        return result.scalars().first()

    async def get_active_tenant(self, tenant_id: int) -> IamTenant | None:
        """查询启用状态的租户。"""
        result = await self.db.execute(
            select(IamTenant).where(IamTenant.id == tenant_id, IamTenant.status == "active")
        )
        return result.scalars().first()

    async def get_active_member(self, *, user_id: int, tenant_id: int) -> IamTenantMember | None:
        """查询用户在租户内的有效成员身份。"""
        result = await self.db.execute(
            select(IamTenantMember).where(
                IamTenantMember.user_id == user_id,
                IamTenantMember.tenant_id == tenant_id,
                IamTenantMember.status == "active",
            )
        )
        return result.scalars().first()

    async def list_role_codes(self, member_id: int) -> frozenset[str]:
        """查询成员拥有的角色编码。"""
        result = await self.db.execute(
            select(IamRole.code)
            .join(IamTenantMemberRole, IamTenantMemberRole.role_id == IamRole.id)
            .where(IamTenantMemberRole.member_id == member_id)
        )
        return frozenset(result.scalars().all())

    async def list_permission_codes(self, member_id: int) -> frozenset[str]:
        """查询成员通过角色拥有的权限编码。"""
        result = await self.db.execute(
            select(IamPermission.code)
            .join(IamRolePermission, IamRolePermission.permission_id == IamPermission.id)
            .join(IamTenantMemberRole, IamTenantMemberRole.role_id == IamRolePermission.role_id)
            .where(IamTenantMemberRole.member_id == member_id)
        )
        return frozenset(result.scalars().all())
```

- [ ] **Step 4: Implement service**

Create `app/iam/service.py`:

```python
"""IAM 认证上下文服务。"""

from pkg.security.context import AuthContext, PermissionSet, Principal
from pkg.security.exceptions import AuthenticationRequiredException, TenantAccessDeniedException
from pkg.tenant.context import TenantContext


class IamAuthContextService:
    """按用户和租户加载认证上下文。"""

    def __init__(self, repository) -> None:
        self.repository = repository

    async def load_context(self, *, user_id: int, tenant_id: int | None) -> AuthContext:
        """加载当前请求的认证与授权上下文。"""
        user = await self.repository.get_active_user(user_id)
        if user is None:
            raise AuthenticationRequiredException()

        principal = Principal(
            user_id=user.id,
            username=user.username,
            is_platform_admin=user.is_platform_admin,
            authenticated=True,
        )

        if tenant_id is None:
            return AuthContext(
                principal=principal,
                tenant=None,
                member_id=None,
                roles=frozenset(),
                permissions=PermissionSet(values=frozenset()),
            )

        tenant = await self.repository.get_active_tenant(tenant_id)
        if tenant is None:
            raise TenantAccessDeniedException("无权访问该租户或租户不可用")

        member = await self.repository.get_active_member(user_id=user_id, tenant_id=tenant_id)
        if member is None and not user.is_platform_admin:
            raise TenantAccessDeniedException()

        roles = frozenset() if member is None else await self.repository.list_role_codes(member.id)
        permissions = frozenset() if member is None else await self.repository.list_permission_codes(member.id)

        return AuthContext(
            principal=principal,
            tenant=TenantContext(
                tenant_id=tenant.id,
                tenant_code=tenant.code,
                tenant_name=tenant.name,
                tenant_status=tenant.status,
            ),
            member_id=None if member is None else member.id,
            roles=roles,
            permissions=PermissionSet(values=permissions),
        )
```

- [ ] **Step 5: Run service tests**

Run:

```bash
uv run pytest tests/app/iam/test_service.py -v
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add app/iam/repository.py app/iam/service.py tests/app/iam/test_service.py
git commit -m "feat: load iam auth context"
```

## Task 8: IAM Schemas

**Files:**

- Create: `app/iam/schemas.py`
- Test: `tests/app/iam/test_schemas.py`

- [ ] **Step 1: Write schema tests**

Create `tests/app/iam/test_schemas.py`:

```python
"""IAM Pydantic 模型测试。"""

from app.iam.schemas import TenantResponse
from pkg.common.api import BaseSchema


def test_tenant_response_extends_base_schema_and_serializes_camel_case() -> None:
    """租户响应模型必须继承 BaseSchema 并输出驼峰字段。"""
    response = TenantResponse(tenant_id=123, tenant_code="demo", tenant_name="演示租户", status="active")

    assert isinstance(response, BaseSchema)
    assert response.model_dump(mode="json") == {
        "tenantId": "123",
        "tenantCode": "demo",
        "tenantName": "演示租户",
        "status": "active",
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/app/iam/test_schemas.py -v
```

Expected: fail with `ModuleNotFoundError` or missing `TenantResponse`.

- [ ] **Step 3: Implement schemas**

Create `app/iam/schemas.py`:

```python
"""IAM API 请求与响应模型。"""

from pkg.common.api import BaseSchema, SafeBigInt


class TenantResponse(BaseSchema):
    """租户响应模型。"""

    tenant_id: SafeBigInt
    tenant_code: str
    tenant_name: str
    status: str


class RoleResponse(BaseSchema):
    """角色响应模型。"""

    role_id: SafeBigInt
    tenant_id: SafeBigInt
    code: str
    name: str


class PermissionResponse(BaseSchema):
    """权限响应模型。"""

    permission_id: SafeBigInt
    code: str
    name: str
```

- [ ] **Step 4: Run schema tests**

Run:

```bash
uv run pytest tests/app/iam/test_schemas.py -v
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add app/iam/schemas.py tests/app/iam/test_schemas.py
git commit -m "feat: add iam schemas"
```

## Task 9: Integration Test Pass And Documentation

**Files:**

- Modify: `README.md`
- Modify: `docs/TEST.md`

- [ ] **Step 1: Run focused tenant RBAC tests**

Run:

```bash
uv run pytest tests/pkg/security tests/pkg/tenant tests/pkg/database/test_tenant_crud.py tests/app/iam -v
```

Expected: all new tenant RBAC tests pass.

- [ ] **Step 2: Run existing unaffected tests**

Run:

```bash
uv run pytest tests/pkg/test_api.py tests/pkg/test_exceptions.py tests/pkg/config/test_environment.py tests/pkg/config/test_models.py tests/pkg/database -v
```

Expected: pass. If `tests/pkg/database/test_tenant_crud.py` is included twice by this command, pytest should still run it normally.

- [ ] **Step 3: Update README feature summary**

Modify `README.md` tenant or security section with:

```markdown
## 多租户与权限

项目提供可复用的租户 RBAC 基础能力：

- 一个用户可以加入多个租户。
- 用户在不同租户内可以拥有不同角色。
- 当前租户通过 `X-Tenant-Id` 请求头解析。
- 权限通过 `require_permission()`、`require_role()` 等 FastAPI 依赖校验。
- 租户业务数据通过 `TenantAwareCrud` 按 `tenant_id` 隔离。
```

- [ ] **Step 4: Update docs/TEST.md**

Append:

````markdown
## 多租户 RBAC 测试

```bash
uv run pytest tests/pkg/security tests/pkg/tenant tests/pkg/database/test_tenant_crud.py tests/app/iam -v
```

这些测试覆盖认证上下文、租户解析、权限依赖、租户感知 CRUD 和 IAM 上下文加载。
````

- [ ] **Step 5: Commit docs**

```bash
git add README.md docs/TEST.md
git commit -m "docs: document tenant rbac tests"
```

## Final Verification

- [ ] **Step 1: Run full available verification**

Run:

```bash
uv run pytest tests/pkg/test_api.py tests/pkg/test_exceptions.py tests/pkg/config/test_environment.py tests/pkg/config/test_models.py tests/pkg/database tests/pkg/security tests/pkg/tenant tests/app/iam -v
```

Expected: pass.

- [ ] **Step 2: Check full test suite status**

Run:

```bash
uv run pytest -q
```

Expected while `pkg.config.loader` is absent: collection fails only because `tests/pkg/config/test_loader.py` imports `pkg.config.loader`.

- [ ] **Step 3: Confirm git status**

Run:

```bash
git status --short
```

Expected: only unrelated pre-existing workspace changes remain. Tenant RBAC implementation files should be committed.

## Self-Review

Spec coverage:

- Multi-tenant membership is implemented by `IamTenantMember`.
- Different roles per tenant are implemented by `IamRole` and `IamTenantMemberRole`.
- Tenant-scoped permissions are loaded through member roles in `IamRepository`.
- `X-Tenant-Id` is implemented by `pkg/tenant/resolver.py` and consumed by `create_auth_context_dependency`.
- FastAPI permission dependencies are implemented in `pkg/security/dependencies.py`.
- Row-level tenant isolation is implemented by `TenantMixin` and `TenantAwareCrud`.
- Platform admin behavior is represented in `Principal.is_platform_admin` and `IamAuthContextService`.

Known deferred design items:

- Audit persistence is not implemented in this plan.
- Distributed cache is not implemented in this plan.
- Login and Token issuance are not implemented in this plan.
- Database migrations are not implemented in this plan.
