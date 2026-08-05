"""安全依赖工厂测试。"""

from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from pkg.common.exceptions import register_exception_handlers
from pkg.security.context import AuthContext, PermissionSet, Principal
from pkg.security.dependencies import create_auth_context_dependency, require_permission
from pkg.tenant.context import TenantContext


class FakeAuthProvider:
    """测试用认证上下文提供者。"""

    async def load_context(self, *, user_id: int, tenant_id: int | None) -> AuthContext:
        """按请求头中的用户和租户构造测试上下文。"""
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
    register_exception_handlers(app)
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
    register_exception_handlers(app)
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


def test_auth_dependency_header_user_id_does_not_conflict_with_path_user_id() -> None:
    """认证头用户 ID 不应与路由路径 user_id 参数冲突。"""
    app = FastAPI()
    register_exception_handlers(app)
    auth_dependency = create_auth_context_dependency(FakeAuthProvider())

    @app.get(
        "/users/{user_id}",
        dependencies=[Depends(auth_dependency), Depends(require_permission("user:create"))],
    )
    async def read_user(user_id: int):
        return {"path_user_id": user_id}

    client = TestClient(app)
    response = client.get("/users/2", headers={"X-User-Id": "1", "X-Tenant-Id": "10"})

    assert response.status_code == 200
    assert response.json() == {"path_user_id": 2}


def test_auth_dependency_header_tenant_id_does_not_conflict_with_path_tenant_id() -> None:
    """认证头租户 ID 不应与路由路径 tenant_id 参数冲突。"""
    app = FastAPI()
    register_exception_handlers(app)
    auth_dependency = create_auth_context_dependency(FakeAuthProvider())

    @app.get(
        "/tenants/{tenant_id}/members",
        dependencies=[Depends(auth_dependency), Depends(require_permission("user:create"))],
    )
    async def read_tenant_members(tenant_id: int):
        return {"path_tenant_id": tenant_id}

    client = TestClient(app)
    response = client.get("/tenants/20/members", headers={"X-User-Id": "1", "X-Tenant-Id": "10"})

    assert response.status_code == 200
    assert response.json() == {"path_tenant_id": 20}
