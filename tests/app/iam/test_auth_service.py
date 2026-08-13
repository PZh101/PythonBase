"""IamAuthService 单元测试。"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import pytest

from app.iam.auth_service import IamAuthService
from pkg.common.exceptions import BadRequestException
from pkg.config import PasswordPolicySettings, TokenSettings
from pkg.security import InvalidCredentialException, PasswordHasher, TokenService


def _settings() -> tuple[PasswordPolicySettings, TokenSettings]:
    """构造测试用的密码与 token 配置。"""
    password = PasswordPolicySettings(
        iterations=1000,
        max_failed_attempts=5,
        lock_duration_seconds=60,
    )
    token = TokenSettings(
        secret="test-secret-must-be-long-enough-for-hmac-32-bytes-ok",
        access_token_ttl_seconds=60,
        refresh_token_ttl_seconds=600,
    )
    return password, token


def _hasher() -> PasswordHasher:
    """构造一个测试用 PasswordHasher。"""
    return PasswordHasher(_settings()[0])


def _token_service() -> TokenService:
    """构造一个测试用 TokenService。"""
    return TokenService(_settings()[1])


def run(coro):
    """在同步测试中执行异步服务。"""
    return asyncio.run(coro)


@dataclass
class FakeUser:
    """测试用用户行。"""

    id: int
    username: str
    is_active: bool = True
    is_platform_admin: bool = False


@dataclass
class FakeCredential:
    """测试用凭证行。"""

    user_id: int
    password_hash: str
    token_version: int = 0
    failed_attempts: int = 0
    locked_until: datetime | None = None
    last_login_at: datetime | None = None


class FakeRepository:
    """测试用 IAM 仓储。

    通过 :func:`set_user` / :func:`set_credential` 注入测试数据。
    跟踪失败计数与 token_version 的变更。
    """

    def __init__(self) -> None:
        self._users: dict[int, FakeUser] = {}
        self._credentials: dict[int, FakeCredential] = {}
        self._username_index: dict[str, int] = {}
        self.bump_token_version_calls: list[int] = []
        self.mark_login_success_calls: list[int] = []
        self.increment_failed_calls: list[tuple[int, datetime | None]] = []
        self.update_password_hash_calls: list[int] = []

    # ── 数据注入 ──────────────────────────────────────────

    def set_user(self, user: FakeUser) -> None:
        """注入用户。"""
        self._users[user.id] = user
        self._username_index[user.username] = user.id

    def set_credential(self, credential: FakeCredential) -> None:
        """注入凭证。"""
        self._credentials[credential.user_id] = credential

    # ── Repository 接口 ──────────────────────────────────

    async def get_user_by_username(self, username: str):
        """按用户名查询用户。"""
        user_id = self._username_index.get(username)
        if user_id is None:
            return None
        return self._users.get(user_id)

    async def get_active_user(self, user_id: int):
        """查询启用用户。"""
        user = self._users.get(user_id)
        if user is None or not user.is_active:
            return None
        return user

    async def get_credential(self, user_id: int):
        """查询凭证。"""
        return self._credentials.get(user_id)

    async def mark_login_success(self, *, user_id: int) -> None:
        """登录成功时清零失败计数。"""
        self.mark_login_success_calls.append(user_id)
        credential = self._credentials.get(user_id)
        if credential is not None:
            credential.failed_attempts = 0
            credential.locked_until = None
            credential.last_login_at = datetime.utcnow()

    async def increment_failed_attempts(self, *, user_id: int, lock_until: datetime | None) -> int:
        """登录失败时累加。"""
        self.increment_failed_calls.append((user_id, lock_until))
        credential = self._credentials.get(user_id)
        if credential is None:
            return 0
        credential.failed_attempts += 1
        credential.locked_until = lock_until
        return credential.failed_attempts

    async def bump_token_version(self, *, user_id: int) -> int:
        """轮换 token 版本号。"""
        self.bump_token_version_calls.append(user_id)
        credential = self._credentials.get(user_id)
        if credential is None:
            return 0
        credential.token_version += 1
        return credential.token_version

    async def update_password_hash(self, *, user_id: int, new_password_hash: str) -> None:
        """重置密码。"""
        self.update_password_hash_calls.append(user_id)
        credential = self._credentials.get(user_id)
        if credential is None:
            return
        credential.password_hash = new_password_hash
        credential.token_version += 1
        credential.failed_attempts = 0
        credential.locked_until = None
        credential.password_changed_at = datetime.utcnow()


def _seed_user(repo: FakeRepository, *, user_id: int, username: str, password: str) -> None:
    """往仓储里塞一个 user + credential。"""
    repo.set_user(FakeUser(id=user_id, username=username))
    repo.set_credential(
        FakeCredential(user_id=user_id, password_hash=_hasher().hash(password))
    )


# ── login ──────────────────────────────────────────────


def test_login_succeeds_and_returns_token_pair() -> None:
    """正确账号密码应签发 token 对。"""
    repo = FakeRepository()
    _seed_user(repo, user_id=1, username="ada", password="correct-pw-1")
    service = IamAuthService(repo, _hasher(), _token_service(), *_settings())

    pair = run(service.login(username="ada", password="correct-pw-1"))

    assert pair.user_id == 1
    assert pair.username == "ada"
    assert pair.access_token
    assert pair.refresh_token
    assert pair.token_version == 1  # login 后 token_version +1
    assert pair.access_expires_in == 60
    assert pair.refresh_expires_in == 600
    assert repo.mark_login_success_calls == [1]
    assert repo.bump_token_version_calls == [1]


def test_login_rejects_unknown_user() -> None:
    """不存在的用户应被拒绝，且不暴露是否存在。"""
    repo = FakeRepository()
    service = IamAuthService(repo, _hasher(), _token_service(), *_settings())

    with pytest.raises(InvalidCredentialException):
        run(service.login(username="ghost", password="anything"))


def test_login_rejects_wrong_password_and_increments_failure() -> None:
    """密码错误应累加失败计数并抛认证失败。"""
    repo = FakeRepository()
    _seed_user(repo, user_id=1, username="ada", password="right-pw")
    service = IamAuthService(repo, _hasher(), _token_service(), *_settings())

    with pytest.raises(InvalidCredentialException):
        run(service.login(username="ada", password="wrong-pw"))

    assert len(repo.increment_failed_calls) == 1
    assert repo.bump_token_version_calls == []  # 失败不轮换 token_version


def test_login_rejects_inactive_user() -> None:
    """已停用用户应被拒绝。"""
    repo = FakeRepository()
    _seed_user(repo, user_id=1, username="ada", password="any")
    repo._users[1].is_active = False  # noqa: SLF001 (test-only mutation)
    service = IamAuthService(repo, _hasher(), _token_service(), *_settings())

    with pytest.raises(InvalidCredentialException):
        run(service.login(username="ada", password="any"))


def test_login_rejects_locked_account() -> None:
    """账号被锁定时直接拒绝，不校验密码。"""
    repo = FakeRepository()
    _seed_user(repo, user_id=1, username="ada", password="any")
    repo._credentials[1].locked_until = datetime.utcnow() + timedelta(minutes=10)  # noqa: SLF001
    service = IamAuthService(repo, _hasher(), _token_service(), *_settings())

    with pytest.raises(InvalidCredentialException):
        run(service.login(username="ada", password="any"))


def test_login_locks_account_after_max_failed_attempts() -> None:
    """连续 max_failed_attempts 次失败后应设置 locked_until。"""
    repo = FakeRepository()
    _seed_user(repo, user_id=1, username="ada", password="right-pw")
    service = IamAuthService(repo, _hasher(), _token_service(), *_settings())

    for _ in range(5):
        with pytest.raises(InvalidCredentialException):
            run(service.login(username="ada", password="wrong-pw"))

    assert repo._credentials[1].locked_until is not None  # noqa: SLF001


# ── refresh ────────────────────────────────────────────


def test_refresh_rotates_token_version() -> None:
    """refresh 应签发新 token 并轮换 token_version。"""
    repo = FakeRepository()
    _seed_user(repo, user_id=1, username="ada", password="any")
    service = IamAuthService(repo, _hasher(), _token_service(), *_settings())
    # 先登录拿到 refresh token
    first = run(service.login(username="ada", password="any"))
    # repo 现在 token_version=1，refresh token 内嵌的 ver 也是 1

    second = run(service.refresh(refresh_token=first.refresh_token))

    assert second.token_version == 2
    assert second.access_token != first.access_token
    assert repo.bump_token_version_calls == [1, 1]


def test_refresh_rejects_stale_version() -> None:
    """凭证版本与 token 不一致时（被吊销）应拒绝。"""
    repo = FakeRepository()
    _seed_user(repo, user_id=1, username="ada", password="any")
    service = IamAuthService(repo, _hasher(), _token_service(), *_settings())
    first = run(service.login(username="ada", password="any"))
    # 模拟 token_version 已被外部推进（如登出或改密）
    repo._credentials[1].token_version = 99  # noqa: SLF001

    with pytest.raises(InvalidCredentialException):
        run(service.refresh(refresh_token=first.refresh_token))


def test_refresh_rejects_malformed_token() -> None:
    """非法 token 应直接抛认证失败。"""
    repo = FakeRepository()
    _seed_user(repo, user_id=1, username="ada", password="any")
    service = IamAuthService(repo, _hasher(), _token_service(), *_settings())

    with pytest.raises(InvalidCredentialException):
        run(service.refresh(refresh_token="not-a-jwt"))


# ── logout ─────────────────────────────────────────────


def test_logout_bumps_token_version() -> None:
    """登出应轮换 token_version 使历史 token 失效。"""
    repo = FakeRepository()
    _seed_user(repo, user_id=1, username="ada", password="any")
    service = IamAuthService(repo, _hasher(), _token_service(), *_settings())

    run(service.logout(user_id=1))

    assert repo.bump_token_version_calls == [1]


def test_logout_for_missing_credential_is_noop() -> None:
    """凭证不存在时登出应静默成功。"""
    repo = FakeRepository()
    service = IamAuthService(repo, _hasher(), _token_service(), *_settings())

    run(service.logout(user_id=999))

    assert repo.bump_token_version_calls == []


# ── change_password ────────────────────────────────────


def test_change_password_success_rotates_tokens() -> None:
    """改密成功应同时重置密码、轮换 token_version、签发新 token。"""
    repo = FakeRepository()
    _seed_user(repo, user_id=1, username="ada", password="old-pass-1")
    service = IamAuthService(repo, _hasher(), _token_service(), *_settings())

    pair = run(
        service.change_password(user_id=1, old_password="old-pass-1", new_password="new-pass-1")
    )

    assert pair.token_version == 1
    assert repo.update_password_hash_calls == [1]
    # 改完密后用新密码能登录
    run(service.login(username="ada", password="new-pass-1"))


def test_change_password_rejects_wrong_old_password() -> None:
    """旧密码错误应拒绝且不更新。"""
    repo = FakeRepository()
    _seed_user(repo, user_id=1, username="ada", password="old-pass-1")
    service = IamAuthService(repo, _hasher(), _token_service(), *_settings())

    with pytest.raises(InvalidCredentialException):
        run(
            service.change_password(
                user_id=1, old_password="wrong-old", new_password="new-pass-1"
            )
        )

    assert repo.update_password_hash_calls == []


def test_change_password_rejects_same_as_old() -> None:
    """新旧密码相同应被业务规则拒绝。"""
    repo = FakeRepository()
    _seed_user(repo, user_id=1, username="ada", password="same-pass-1")
    service = IamAuthService(repo, _hasher(), _token_service(), *_settings())

    with pytest.raises(BadRequestException):
        run(
            service.change_password(
                user_id=1, old_password="same-pass-1", new_password="same-pass-1"
            )
        )
