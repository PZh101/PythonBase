"""IAM 登录、登出、token 刷新与密码管理服务。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from pkg.common.exceptions import BadRequestException
from pkg.config import PasswordPolicySettings, TokenSettings
from pkg.security import (
    AccessTokenPayload,
    InvalidCredentialException,
    PasswordHasher,
    TokenService,
)
from pkg.security.exceptions import InvalidTokenException

from app.iam.repository import IamRepository


@dataclass(frozen=True, slots=True)
class TokenPair:
    """登录或刷新后返回的访问令牌 + 刷新令牌对。"""

    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    access_expires_in: int = 0
    refresh_expires_in: int = 0
    token_version: int = 0
    user_id: int = 0
    username: str | None = None


class IamAuthService:
    """封装登录、登出、刷新、改密等认证操作。

    Args:
        repository: IAM 数据访问。
        password_hasher: 密码哈希器。
        token_service: JWT 签发与解析服务。
        password_policy: 密码策略（用于锁定时长）。
        token_settings: token 配置（用于读取刷新 token TTL）。
    """

    def __init__(
        self,
        repository: IamRepository,
        password_hasher: PasswordHasher,
        token_service: TokenService,
        password_policy: PasswordPolicySettings,
        token_settings: TokenSettings,
    ) -> None:
        self.repository = repository
        self.password_hasher = password_hasher
        self.token_service = token_service
        self._password_policy = password_policy
        self._token_settings = token_settings

    # ── 登录 ──────────────────────────────────────────────

    async def login(self, *, username: str, password: str) -> TokenPair:
        """校验账号密码并签发 token 对。

        Args:
            username: 登录账号。
            password: 明文密码。

        Returns:
            新签发的访问令牌与刷新令牌。

        Raises:
            InvalidCredentialException: 用户不存在、已停用、密码错误或账号被锁定。
        """
        user = await self.repository.get_user_by_username(username)
        if user is None or not user.is_active:
            # 用户不存在与密码错误统一返回，避免账号枚举。
            raise InvalidCredentialException("账号或密码错误")

        credential = await self.repository.get_credential(user.id)
        if credential is None:
            raise InvalidCredentialException("账号或密码错误")

        if credential.locked_until is not None and credential.locked_until > datetime.utcnow():
            raise InvalidCredentialException("账号已被锁定，请稍后再试")

        if not self.password_hasher.verify(password, credential.password_hash):
            await self._handle_failed_attempt(credential.user_id)
            raise InvalidCredentialException("账号或密码错误")

        await self.repository.mark_login_success(user_id=credential.user_id)
        await self.repository.bump_token_version(user_id=credential.user_id)
        refreshed = await self.repository.get_credential(user.id)
        if refreshed is None:
            raise InvalidCredentialException("账号或密码错误")

        return self._build_token_pair(user_id=user.id, username=user.username, token_version=refreshed.token_version)

    async def _handle_failed_attempt(self, user_id: int) -> None:
        """登录失败时累加计数并在超限时锁定。"""
        threshold = self._password_policy.max_failed_attempts
        lock_seconds = self._password_policy.lock_duration_seconds
        # 即将累加后的失败次数（这里不能直接用 ++ 后再比较阈值，所以先读当前值）
        current = await self.repository.get_credential(user_id)
        next_count = (current.failed_attempts if current else 0) + 1
        lock_until = (
            datetime.utcnow() + timedelta(seconds=lock_seconds)
            if next_count >= threshold and lock_seconds > 0
            else None
        )
        await self.repository.increment_failed_attempts(user_id=user_id, lock_until=lock_until)

    # ── 刷新 ──────────────────────────────────────────────

    async def refresh(self, *, refresh_token: str) -> TokenPair:
        """使用刷新令牌换取新的 token 对，并轮换 token_version。"""
        try:
            payload = self.token_service.decode(refresh_token, expected_type="refresh")
        except InvalidTokenException as exc:
            raise InvalidCredentialException(str(exc.msg)) from exc

        user = await self.repository.get_active_user(payload.user_id)
        if user is None:
            raise InvalidCredentialException("账号或密码错误")

        credential = await self.repository.get_credential(user.id)
        if credential is None:
            raise InvalidCredentialException("账号或密码错误")
        if credential.token_version != payload.token_version:
            raise InvalidCredentialException("刷新令牌已失效，请重新登录")
        if credential.locked_until is not None and credential.locked_until > datetime.utcnow():
            raise InvalidCredentialException("账号已被锁定，请稍后再试")

        await self.repository.bump_token_version(user_id=user.id)
        refreshed = await self.repository.get_credential(user.id)
        if refreshed is None:
            raise InvalidCredentialException("账号或密码错误")

        return self._build_token_pair(
            user_id=user.id,
            username=user.username,
            token_version=refreshed.token_version,
        )

    # ── 登出 ──────────────────────────────────────────────

    async def logout(self, *, user_id: int) -> None:
        """使当前用户的所有历史 token 失效。"""
        credential = await self.repository.get_credential(user_id)
        if credential is None:
            return
        await self.repository.bump_token_version(user_id=user_id)

    # ── 修改密码 ──────────────────────────────────────────

    async def change_password(
        self,
        *,
        user_id: int,
        old_password: str,
        new_password: str,
    ) -> TokenPair:
        """修改当前用户密码，同时吊销历史 token 并签发新 token。"""
        if not new_password or old_password == new_password:
            raise BadRequestException("新密码不能为空或与旧密码相同")

        credential = await self.repository.get_credential(user_id)
        if credential is None:
            raise InvalidCredentialException("账号或密码错误")
        if not self.password_hasher.verify(old_password, credential.password_hash):
            raise InvalidCredentialException("旧密码错误")

        new_hash = self.password_hasher.hash(new_password)
        await self.repository.update_password_hash(user_id=user_id, new_password_hash=new_hash)
        refreshed = await self.repository.get_credential(user_id)
        if refreshed is None:
            raise InvalidCredentialException("账号或密码错误")

        user = await self.repository.get_active_user(user_id)
        return self._build_token_pair(
            user_id=user_id,
            username=user.username if user else None,
            token_version=refreshed.token_version,
        )

    # ── 内部工具 ──────────────────────────────────────────

    def _build_token_pair(
        self,
        *,
        user_id: int,
        username: str | None,
        token_version: int,
    ) -> TokenPair:
        """根据当前配置签发访问令牌与刷新令牌。"""
        access_token = self.token_service.issue_access_token(
            user_id=user_id,
            token_version=token_version,
        )
        refresh_token = self.token_service.issue_refresh_token(
            user_id=user_id,
            token_version=token_version,
        )
        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            access_expires_in=self._token_settings.access_token_ttl_seconds,
            refresh_expires_in=self._token_settings.refresh_token_ttl_seconds,
            token_version=token_version,
            user_id=user_id,
            username=username,
        )


__all__ = ["IamAuthService", "TokenPair"]
