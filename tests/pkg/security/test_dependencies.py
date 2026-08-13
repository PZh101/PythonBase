"""安全依赖工厂测试。"""

from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from pkg.common.exceptions import register_exception_handlers
from pkg.config import AuthMode, TokenSettings
from pkg.security import (
    AuthContext,
    JwtTokenResolver,
    PermissionSet,
    Principal,
    TokenService,
    create_auth_context_dependency,
    require_permission,
)
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


def _token_resolver() -> JwtTokenResolver:
    """构造一个使用固定 secret 的 token resolver。"""
    settings = TokenSettings(
        secret="test-secret-must-be-long-enough-for-hmac-32-bytes-ok",
        access_token_ttl_seconds=60,
    )
    return JwtTokenResolver(TokenService(settings))


def _token_service() -> TokenService:
    """构造一个使用固定 secret 的 token service。"""
    return TokenService(
        TokenSettings(
            secret="test-secret-must-be-long-enough-for-hmac-32-bytes-ok",
            access_token_ttl_seconds=60,
        )
    )


# ── HEADER 模式 ─────────────────────────────────────


def test_permission_dependency_allows_authorized_request() -> None:
    """HEADER 模式：权限依赖应允许已授权请求进入路由。"""
    app = FastAPI()
    register_exception_handlers(app)
    auth_dependency = create_auth_context_dependency(FakeAuthProvider(), auth_mode=AuthMode.HEADER)

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
    """HEADER 模式：权限依赖应拒绝缺少权限的请求。"""
    app = FastAPI()
    register_exception_handlers(app)
    auth_dependency = create_auth_context_dependency(FakeAuthProvider(), auth_mode=AuthMode.HEADER)

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
    """HEADER 模式：认证头用户 ID 不应与路由路径 user_id 参数冲突。"""
    app = FastAPI()
    register_exception_handlers(app)
    auth_dependency = create_auth_context_dependency(FakeAuthProvider(), auth_mode=AuthMode.HEADER)

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
    """HEADER 模式：认证头租户 ID 不应与路由路径 tenant_id 参数冲突。"""
    app = FastAPI()
    register_exception_handlers(app)
    auth_dependency = create_auth_context_dependency(FakeAuthProvider(), auth_mode=AuthMode.HEADER)

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


def test_auth_dependency_header_mode_rejects_request_without_user_id() -> None:
    """HEADER 模式：缺少 X-User-Id 时应返回 401。"""
    app = FastAPI()
    register_exception_handlers(app)
    auth_dependency = create_auth_context_dependency(FakeAuthProvider(), auth_mode=AuthMode.HEADER)

    @app.get("/me", dependencies=[Depends(auth_dependency)])
    async def read_me(_: Annotated[AuthContext, Depends(auth_dependency)]):
        return {}

    client = TestClient(app)
    response = client.get("/me")

    assert response.status_code == 401
    assert response.json()["code"] == 40100


def test_auth_dependency_header_mode_ignores_bearer_token() -> None:
    """HEADER 模式：即使提供了有效 Bearer token，也应以 X- 头为准。"""
    app = FastAPI()
    register_exception_handlers(app)
    auth_dependency = create_auth_context_dependency(
        FakeAuthProvider(),
        auth_mode=AuthMode.HEADER,
        token_resolver=_token_resolver(),  # 提供但不生效
    )

    @app.get("/me", dependencies=[Depends(auth_dependency)])
    async def read_me(context: Annotated[AuthContext, Depends(auth_dependency)]):
        return {
            "user_id": context.principal.user_id,
            "tenant_id": context.tenant.tenant_id if context.tenant else None,
        }

    # 签发一个 token，但 header 模式应当忽略它。
    token_service = _token_service()
    access = token_service.issue_access_token(user_id=99, token_version=0, tenant_id=5)

    client = TestClient(app)
    response = client.get(
        "/me",
        headers={
            "Authorization": f"Bearer {access}",
            "X-User-Id": "1",
            "X-Tenant-Id": "10",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"user_id": 1, "tenant_id": 10}


# ── JWT 模式 ────────────────────────────────────────


def test_auth_dependency_jwt_mode_uses_bearer_token() -> None:
    """JWT 模式：应从 Authorization Bearer token 解析主体。"""
    app = FastAPI()
    register_exception_handlers(app)
    auth_dependency = create_auth_context_dependency(
        FakeAuthProvider(),
        auth_mode=AuthMode.JWT,
        token_resolver=_token_resolver(),
    )

    @app.get("/me", dependencies=[Depends(auth_dependency)])
    async def read_me(context: Annotated[AuthContext, Depends(auth_dependency)]):
        return {
            "user_id": context.principal.user_id,
            "tenant_id": context.tenant.tenant_id if context.tenant else None,
        }

    token_service = _token_service()
    access = token_service.issue_access_token(user_id=99, token_version=0, tenant_id=5)

    client = TestClient(app)
    response = client.get("/me", headers={"Authorization": f"Bearer {access}"})

    assert response.status_code == 200
    assert response.json() == {"user_id": 99, "tenant_id": 5}


def test_auth_dependency_jwt_mode_rejects_request_without_bearer() -> None:
    """JWT 模式：缺少 Authorization 头时应返回 401，且忽略 X- 头。"""
    app = FastAPI()
    register_exception_handlers(app)
    auth_dependency = create_auth_context_dependency(
        FakeAuthProvider(),
        auth_mode=AuthMode.JWT,
        token_resolver=_token_resolver(),
    )

    @app.get("/me", dependencies=[Depends(auth_dependency)])
    async def read_me(_: Annotated[AuthContext, Depends(auth_dependency)]):
        return {}

    client = TestClient(app)
    # 即使带 X- 头，jwt 模式也应当忽略并返回 401。
    response = client.get("/me", headers={"X-User-Id": "1", "X-Tenant-Id": "10"})

    assert response.status_code == 401
    assert response.json()["code"] == 40100


def test_auth_dependency_jwt_mode_rejects_invalid_bearer_with_401() -> None:
    """JWT 模式：Authorization 头是非法 token 时应返回 401。"""
    app = FastAPI()
    register_exception_handlers(app)
    auth_dependency = create_auth_context_dependency(
        FakeAuthProvider(),
        auth_mode=AuthMode.JWT,
        token_resolver=_token_resolver(),
    )

    @app.get("/me", dependencies=[Depends(auth_dependency)])
    async def read_me(_: Annotated[AuthContext, Depends(auth_dependency)]):
        return {}

    client = TestClient(app)
    response = client.get("/me", headers={"Authorization": "Bearer not-a-real-jwt"})

    assert response.status_code == 401
    body = response.json()
    assert body["code"] == 40101


def test_auth_dependency_jwt_mode_ignores_x_user_id_header() -> None:
    """JWT 模式：忽略 X-User-Id，主体以 token 为准。"""
    app = FastAPI()
    register_exception_handlers(app)
    auth_dependency = create_auth_context_dependency(
        FakeAuthProvider(),
        auth_mode=AuthMode.JWT,
        token_resolver=_token_resolver(),
    )

    @app.get("/me", dependencies=[Depends(auth_dependency)])
    async def read_me(context: Annotated[AuthContext, Depends(auth_dependency)]):
        return {"user_id": context.principal.user_id}

    token_service = _token_service()
    access = token_service.issue_access_token(user_id=99, token_version=0, tenant_id=5)

    client = TestClient(app)
    response = client.get(
        "/me",
        headers={
            "Authorization": f"Bearer {access}",
            "X-User-Id": "1",  # 应当被忽略
        },
    )

    assert response.status_code == 200
    assert response.json() == {"user_id": 99}


def test_auth_dependency_jwt_mode_ignores_x_tenant_id_header() -> None:
    """JWT 模式：忽略 X-Tenant-Id，租户以 token 内嵌的 tid 为准。"""
    app = FastAPI()
    register_exception_handlers(app)
    auth_dependency = create_auth_context_dependency(
        FakeAuthProvider(),
        auth_mode=AuthMode.JWT,
        token_resolver=_token_resolver(),
    )

    @app.get("/me", dependencies=[Depends(auth_dependency)])
    async def read_me(context: Annotated[AuthContext, Depends(auth_dependency)]):
        return {"tenant_id": context.tenant.tenant_id if context.tenant else None}

    token_service = _token_service()
    access = token_service.issue_access_token(user_id=1, token_version=0, tenant_id=5)

    client = TestClient(app)
    response = client.get(
        "/me",
        headers={
            "Authorization": f"Bearer {access}",
            "X-Tenant-Id": "20",  # 应当被忽略
        },
    )

    assert response.status_code == 200
    assert response.json() == {"tenant_id": 5}


def test_auth_dependency_jwt_mode_requires_token_resolver() -> None:
    """JWT 模式：缺少 token_resolver 时构造应抛 RuntimeError。"""
    with pytest.raises(RuntimeError, match="token_resolver"):
        create_auth_context_dependency(
            FakeAuthProvider(),
            auth_mode=AuthMode.JWT,
            token_resolver=None,
        )
