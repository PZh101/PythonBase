"""IAM 认证路由端到端测试。"""

from dataclasses import dataclass
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.iam.auth_routes import create_iam_auth_router
from app.iam.models import IamUser
from pkg.common.exceptions import register_exception_handlers
from pkg.config import (
    AuthMode,
    PasswordPolicySettings,
    SecuritySettings,
    TokenSettings,
)
from pkg.security import (
    AuthContext,
    JwtTokenResolver,
    PasswordHasher,
    TokenService,
    create_auth_context_dependency,
)
from pkg.security.context import PermissionSet, Principal


@dataclass
class FakeCredential:
    """测试用凭证行。"""

    user_id: int
    password_hash: str
    token_version: int = 0
    failed_attempts: int = 0
    locked_until: datetime | None = None


class FakeIamRepository:
    """内存版 IAM 仓储，绕过真实 SQLAlchemy 会话。"""

    def __init__(self) -> None:
        self._users: dict[int, IamUser] = {}
        self._credentials: dict[int, FakeCredential] = {}
        self._username_index: dict[str, int] = {}
        self.bump_calls: list[int] = []

    def seed(self, user_id: int, username: str, password: str, hasher: PasswordHasher) -> None:
        """注入 user + credential。"""
        self._users[user_id] = IamUser(id=user_id, username=username, is_active=True)
        self._credentials[user_id] = FakeCredential(
            user_id=user_id, password_hash=hasher.hash(password)
        )
        self._username_index[username] = user_id

    # ── 覆写 auth_service 实际调用的方法 ──────────────────

    async def get_user_by_username(self, username: str):
        user_id = self._username_index.get(username)
        if user_id is None:
            return None
        return self._users.get(user_id)

    async def get_active_user(self, user_id: int):
        user = self._users.get(user_id)
        if user is None or not user.is_active:
            return None
        return user

    async def get_credential(self, user_id: int):
        return self._credentials.get(user_id)

    async def mark_login_success(self, *, user_id: int) -> None:
        credential = self._credentials.get(user_id)
        if credential is not None:
            credential.failed_attempts = 0
            credential.locked_until = None
            credential.last_login_at = datetime.utcnow()

    async def increment_failed_attempts(self, *, user_id: int, lock_until: datetime | None) -> int:
        credential = self._credentials.get(user_id)
        if credential is None:
            return 0
        credential.failed_attempts += 1
        credential.locked_until = lock_until
        return credential.failed_attempts

    async def bump_token_version(self, *, user_id: int) -> int:
        self.bump_calls.append(user_id)
        credential = self._credentials.get(user_id)
        if credential is None:
            return 0
        credential.token_version += 1
        return credential.token_version

    async def update_password_hash(self, *, user_id: int, new_password_hash: str) -> None:
        credential = self._credentials.get(user_id)
        if credential is None:
            return
        credential.password_hash = new_password_hash
        credential.token_version += 1
        credential.failed_attempts = 0
        credential.locked_until = None


def _build_security() -> SecuritySettings:
    """构造测试用 SecuritySettings。"""
    return SecuritySettings(
        enable_password_login=True,
        auth_mode=AuthMode.JWT,
        password=PasswordPolicySettings(
            iterations=1000,
            max_failed_attempts=5,
            lock_duration_seconds=60,
        ),
        token=TokenSettings(
            secret="test-secret-must-be-long-enough-for-hmac-32-bytes-ok",
            access_token_ttl_seconds=60,
            refresh_token_ttl_seconds=600,
        ),
    )


class _StaticAuthProvider:
    """测试用认证上下文 Provider，直接根据入参构造 AuthContext，不依赖 DB。"""

    async def load_context(self, *, user_id: int, tenant_id: int | None) -> AuthContext:
        """按已解析的 (user_id, tenant_id) 构造最小可用上下文。"""
        return AuthContext(
            principal=Principal(user_id=user_id, username="ada", authenticated=True),
            tenant=None,
            member_id=None,
            roles=frozenset(),
            permissions=PermissionSet(values=frozenset()),
        )


def _build_auth_dependency(
    token_service: TokenService,
    *,
    auth_mode: AuthMode = AuthMode.JWT,
) -> object:
    """调用生产路径的 auth 依赖工厂，绕过 DB 仓储。

    与生产 :func:`create_auth_dependency` 行为一致：解析主体后由依赖工厂写入
    ``request.state.auth_context``，``get_current_auth_context`` 再读取。
    """
    return create_auth_context_dependency(
        _StaticAuthProvider(),
        auth_mode=auth_mode,
        token_resolver=JwtTokenResolver(token_service),
    )


@pytest.fixture
def hasher() -> PasswordHasher:
    """测试用密码哈希器。"""
    return PasswordHasher(
        PasswordPolicySettings(
            iterations=1000,
            max_failed_attempts=5,
            lock_duration_seconds=60,
        )
    )


@pytest.fixture
def app_under_test(hasher: PasswordHasher, monkeypatch: pytest.MonkeyPatch):
    """构造绑定到 :class:`FakeIamRepository` 的 FastAPI 应用。"""
    security = _build_security()
    token_service = TokenService(security.token)
    fake_repo = FakeIamRepository()
    auth_dependency = _build_auth_dependency(token_service)

    # 让 auth_routes / auth_service 中的 IamRepository(db) 全部返回 fake_repo。
    from app.iam import auth_routes as auth_routes_module
    from app.iam import auth_service as auth_service_module

    monkeypatch.setattr(auth_routes_module, "IamRepository", lambda _db: fake_repo)
    monkeypatch.setattr(auth_service_module, "IamRepository", lambda _db: fake_repo)

    app = FastAPI()
    register_exception_handlers(app)

    def db_dependency():
        """占位 session，真实访问全部被 monkeypatch 走 fake_repo。"""
        yield None

    app.include_router(
        create_iam_auth_router(
            db_dependency=db_dependency,
            auth_dependency=auth_dependency,
            security_settings=security,
            token_service=token_service,
        )
    )

    return app, fake_repo, token_service


# ── /iam/auth/login ───────────────────────────────────


def test_login_endpoint_returns_token_pair(app_under_test, hasher: PasswordHasher) -> None:
    """正确密码应返回 access + refresh 双 token。"""
    app, fake_repo, _ = app_under_test
    fake_repo.seed(1, "ada", "correct-pw-1", hasher)

    client = TestClient(app)
    response = client.post(
        "/iam/auth/login", json={"username": "ada", "password": "correct-pw-1"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    data = body["data"]
    assert int(data["userId"]) == 1
    assert data["username"] == "ada"
    assert data["tokenType"] == "Bearer"
    assert data["accessExpiresIn"] == 60
    assert data["refreshExpiresIn"] == 600
    assert data["accessToken"]
    assert data["refreshToken"]
    assert data["tokenVersion"] == 1


def test_login_endpoint_rejects_wrong_password_with_401(
    app_under_test, hasher: PasswordHasher
) -> None:
    """错误密码应返回 401。"""
    app, fake_repo, _ = app_under_test
    fake_repo.seed(1, "ada", "correct-pw-1", hasher)

    client = TestClient(app)
    response = client.post("/iam/auth/login", json={"username": "ada", "password": "wrong-pw"})

    assert response.status_code == 401
    assert response.json()["code"] == 40101


def test_login_endpoint_rejects_unknown_user_with_401(app_under_test) -> None:
    """未知用户应返回 401，msg 与错误密码一致以防账号枚举。"""
    app, _, _ = app_under_test

    client = TestClient(app)
    response = client.post("/iam/auth/login", json={"username": "ghost", "password": "x"})

    assert response.status_code == 401


def test_login_endpoint_validates_request_body(app_under_test) -> None:
    """空请求体应被 Pydantic 校验拒绝（422）。"""
    app, _, _ = app_under_test

    client = TestClient(app)
    response = client.post("/iam/auth/login", json={})

    assert response.status_code == 422


# ── /iam/auth/refresh ────────────────────────────────


def test_refresh_endpoint_rotates_token(app_under_test, hasher: PasswordHasher) -> None:
    """刷新令牌应返回新的 token_version。"""
    app, fake_repo, _ = app_under_test
    fake_repo.seed(1, "ada", "correct-pw-1", hasher)

    client = TestClient(app)
    login_resp = client.post(
        "/iam/auth/login", json={"username": "ada", "password": "correct-pw-1"}
    )
    refresh_token = login_resp.json()["data"]["refreshToken"]

    response = client.post("/iam/auth/refresh", json={"refreshToken": refresh_token})

    assert response.status_code == 200
    assert response.json()["data"]["tokenVersion"] == 2


def test_refresh_endpoint_rejects_malformed_token(app_under_test) -> None:
    """非法 refresh token 应被拒绝。"""
    app, _, _ = app_under_test

    client = TestClient(app)
    response = client.post("/iam/auth/refresh", json={"refreshToken": "not-a-jwt"})

    assert response.status_code == 401


# ── /iam/auth/logout & /iam/auth/password ─────────────


def test_logout_endpoint_bumps_token_version(app_under_test, hasher: PasswordHasher) -> None:
    """登出后 token_version 应被推进。"""
    app, fake_repo, _ = app_under_test
    fake_repo.seed(1, "ada", "correct-pw-1", hasher)
    client = TestClient(app)
    login_resp = client.post(
        "/iam/auth/login", json={"username": "ada", "password": "correct-pw-1"}
    )
    access = login_resp.json()["data"]["accessToken"]

    response = client.post("/iam/auth/logout", headers={"Authorization": f"Bearer {access}"})

    assert response.status_code == 200
    assert fake_repo.bump_calls == [1, 1]  # login + logout 各一次


def test_logout_endpoint_requires_auth(app_under_test) -> None:
    """未携带有效凭证的登出请求应返回 401。"""
    app, _, _ = app_under_test
    client = TestClient(app)
    response = client.post("/iam/auth/logout")
    assert response.status_code == 401


def test_change_password_endpoint_returns_new_token_pair(
    app_under_test, hasher: PasswordHasher
) -> None:
    """改密成功应返回新的 token 对。"""
    app, fake_repo, _ = app_under_test
    fake_repo.seed(1, "ada", "old-pass-1", hasher)
    client = TestClient(app)
    login_resp = client.post(
        "/iam/auth/login", json={"username": "ada", "password": "old-pass-1"}
    )
    access = login_resp.json()["data"]["accessToken"]

    response = client.post(
        "/iam/auth/password",
        headers={"Authorization": f"Bearer {access}"},
        json={"oldPassword": "old-pass-1", "newPassword": "new-pass-1"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    # login 阶段 token_version 已经是 1，change_password 再 +1 变成 2。
    assert body["data"]["tokenVersion"] == 2
    # 用新密码应能登录
    login_again = client.post(
        "/iam/auth/login", json={"username": "ada", "password": "new-pass-1"}
    )
    assert login_again.status_code == 200


def test_change_password_rejects_wrong_old_password(
    app_under_test, hasher: PasswordHasher
) -> None:
    """旧密码错误应拒绝。"""
    app, fake_repo, _ = app_under_test
    fake_repo.seed(1, "ada", "old-pass-1", hasher)
    client = TestClient(app)
    login_resp = client.post(
        "/iam/auth/login", json={"username": "ada", "password": "old-pass-1"}
    )
    access = login_resp.json()["data"]["accessToken"]

    response = client.post(
        "/iam/auth/password",
        headers={"Authorization": f"Bearer {access}"},
        json={"oldPassword": "wrong-old", "newPassword": "new-pass-1"},
    )

    assert response.status_code == 401
